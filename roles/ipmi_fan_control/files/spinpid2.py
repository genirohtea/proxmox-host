#!/usr/bin/env python3
"""Dual-zone Supermicro fan controller.

This is a Python 3 port of ``spinpid2.sh`` (version 2020-08-20). It controls
the fans of Supermicro motherboards that expose two fan zones:

  * The peripheral (drive) zone is regulated with a PID loop so that the mean
    drive temperature is held at a setpoint.
  * The CPU zone is not held at a setpoint; instead the duty cycle is scaled
    linearly with CPU temperature above a reference temperature.

The behaviour mirrors the original shell script as closely as practical. The
tunables that used to live in ``spinpid2.config`` now live in a YAML settings
file (``spinpid2.settings.yaml``) that is validated at startup against a JSON
Schema (``spinpid2.schema.yaml``).

Note:
  The original ``spinpid2.sh`` was written for FreeBSD/TrueNAS and can read CPU
  temperatures through ``sysctl``. On Linux (e.g. Proxmox) that interface is not
  available, so CPU temperature is read through ``ipmitool`` instead. Both code
  paths are preserved here.

See the "Tuning advice" section at the bottom of this file for how to choose
the setpoint and the KP/KD constants.

Example:
  sudo ./spinpid2.py --settings spinpid2.settings.yaml
"""

import argparse
import dataclasses
import email.message
import logging
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional

import jsonschema  # ty: ignore[unresolved-import]
import yaml  # ty: ignore[unresolved-import]

VERSION = "2020-08-20-py.1"

# Fan mode reported by the "get fan mode" raw command (see below).
_MODE_TEXT = {0: "Standard", 1: "Full", 2: "Optimal", 4: "HeavyIO"}

# ---------------------------------------------------------------------------
# Supermicro OEM IPMI raw commands (all under NetFn 0x30, the OEM group).
# These byte sequences are passed verbatim to ``ipmitool raw``.
#
#   Fan duty:  0x30 0x70 0x66 <0=read | 1=set> <zone> [duty%]
#       read -> returns the zone's current duty cycle as a single hex byte.
#       set  -> writes the zone's duty cycle (0-100, as a decimal argument,
#               matching the original shell script).
#   Fan mode:  0x30 0x45 <0=read | 1=set> [mode]
#       read -> returns the current fan mode (see _MODE_TEXT).
#       set  -> writes the fan mode (we force "Full" so the BMC does not
#               override our duty cycles).
# ---------------------------------------------------------------------------
_RAW_FAN_DUTY = ("0x30", "0x70", "0x66")
_RAW_FAN_MODE = ("0x30", "0x45")
_RAW_READ = "0"
_RAW_SET = "1"
_FAN_MODE_FULL = 1

# Placeholder printed when a value is unavailable (e.g. drive in standby).
_MISSING = "--"

_LOGGER = logging.getLogger("spinpid2")

# Temperature (C) above which a warning email is sent (drives or CPU). To avoid
# noise, at most one temperature email is sent per day.
_TEMP_ALERT_THRESHOLD = 90

# Proxmox's mail forwarder reads an RFC822 message on stdin and hands it to the
# notification system. The binary moved from /usr/bin to /usr/libexec in PVE 9.
_MAIL_FORWARD_CANDIDATES = (
    "/usr/libexec/proxmox-mail-forward",  # PVE 9 / trixie
    "/usr/bin/proxmox-mail-forward",  # PVE 8 / bookworm
)


@dataclasses.dataclass(frozen=True)
class Settings:
    """Validated, resolved settings loaded from the YAML settings file."""

    # Output.
    ipmitool: List[str]
    log_file: str
    console: bool
    cpu_log_enable: bool
    cpu_log: str
    prometheus_file: str
    # Fan.
    zone_cpu: int
    zone_periph: int
    duty_cpu_min: int
    duty_cpu_max: int
    duty_periph_min: int
    duty_periph_max: int
    rpm_cpu_30: int
    rpm_cpu_max: int
    rpm_periph_30: int
    rpm_periph_max: int
    how_duty: int
    # Drive.
    setpoint: float
    drive_interval: float
    kp: float
    kd: float
    # CPU.
    cpu_interval: float
    cpu_ref: int
    cpu_scale: int

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], base_dir: str) -> "Settings":
        """Builds a Settings instance from the parsed YAML mapping.

        Args:
          data: The settings mapping (already validated against the schema).
          base_dir: Directory used to resolve relative log paths.

        Returns:
          A fully resolved Settings instance.
        """
        output = data["output"]
        fan = data["fan"]
        drive = data["drive"]
        cpu = data["cpu"]

        def resolve(path: str) -> str:
            if os.path.isabs(path):
                return path
            return os.path.normpath(os.path.join(base_dir, path))

        ipmitool = output["ipmitool"] or shutil.which("ipmitool") or "ipmitool"

        return cls(
            ipmitool=shlex.split(ipmitool),
            log_file=resolve(output["log_file"]),
            console=output["console"],
            cpu_log_enable=output["cpu_log_enable"],
            cpu_log=resolve(output["cpu_log"]),
            prometheus_file=resolve(output["prometheus_file"]),
            zone_cpu=fan["zone_cpu"],
            zone_periph=fan["zone_periph"],
            duty_cpu_min=fan["duty_cpu_min"],
            duty_cpu_max=fan["duty_cpu_max"],
            duty_periph_min=fan["duty_periph_min"],
            duty_periph_max=fan["duty_periph_max"],
            rpm_cpu_30=fan["rpm_cpu_30"],
            rpm_cpu_max=fan["rpm_cpu_max"],
            rpm_periph_30=fan["rpm_periph_30"],
            rpm_periph_max=fan["rpm_periph_max"],
            how_duty=fan["how_duty"],
            setpoint=float(drive["setpoint"]),
            drive_interval=float(drive["interval_minutes"]),
            kp=float(drive["kp"]),
            kd=float(drive["kd"]),
            cpu_interval=float(cpu["interval_seconds"]),
            cpu_ref=cpu["ref"],
            cpu_scale=cpu["scale"],
        )


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command line arguments.

    Args:
      argv: Optional list of arguments; defaults to ``sys.argv``.

    Returns:
      The populated argparse namespace.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(
        description="Dual-zone Supermicro fan controller (PID for drives, "
        "linear scaling for CPU).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument(
        "--settings",
        default=os.path.join(script_dir, "spinpid2.settings.yaml"),
        help="Path to the YAML settings file.",
    )
    parser.add_argument(
        "--schema",
        default=os.path.join(script_dir, "spinpid2.schema.yaml"),
        help="Path to the JSON Schema used to validate the settings.",
    )
    return parser.parse_args(argv)


def _load_yaml(path: str) -> Any:
    """Loads and parses a YAML document."""
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_settings(settings_path: str, schema_path: str) -> Settings:
    """Loads the settings file, validates it against the schema, and resolves it.

    Args:
      settings_path: Path to the YAML settings file.
      schema_path: Path to the JSON Schema file.

    Returns:
      A resolved Settings instance.

    Raises:
      OSError: If either file cannot be read.
      yaml.YAMLError: If either file is not valid YAML.
      jsonschema.ValidationError: If the settings violate the schema.
    """
    data = _load_yaml(settings_path)
    schema = _load_yaml(schema_path)
    jsonschema.validate(instance=data, schema=schema)
    base_dir = os.path.dirname(os.path.abspath(settings_path))
    return Settings.from_mapping(data, base_dir)


def _setup_logging(log_file: str, to_console: bool) -> None:
    """Configures the module logger to mirror the shell script's ``tee``.

    The formatter emits the bare message so that the tabular monitor output
    stays readable (the original script prints its own timestamps inline).

    Args:
      log_file: Path of the file to append log lines to.
      to_console: Whether to also emit lines to stdout.
    """
    _LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter("%(message)s")

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    _LOGGER.addHandler(file_handler)

    if to_console:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        _LOGGER.addHandler(stream_handler)


def _abbreviate_device(device: str) -> str:
    """Shortens a device path for the column header (e.g. /dev/sde -> sde)."""
    device = re.sub(r"/dev/nvme(\d+n\d+)", r"\1", device)
    device = re.sub(r"/dev/(sd[a-z])", r"\1", device)
    return device


class FanController:
    """Encapsulates fan-control state and the IPMI/smartctl interactions."""

    def __init__(self, settings: Settings) -> None:
        """Initializes controller state from validated settings."""
        self._ipmi_base = settings.ipmitool
        self.settings = settings

        # Convenience aliases for the tunables used throughout.
        self.zone_cpu = settings.zone_cpu
        self.zone_periph = settings.zone_periph
        self.duty_cpu_min = settings.duty_cpu_min
        self.duty_cpu_max = settings.duty_cpu_max
        self.duty_periph_min = settings.duty_periph_min
        self.duty_periph_max = settings.duty_periph_max
        self.how_duty = settings.how_duty
        self.setpoint = settings.setpoint
        self.drive_t = settings.drive_interval
        self.kp = settings.kp
        self.kd = settings.kd
        self.cpu_t = settings.cpu_interval
        self.cpu_ref = settings.cpu_ref
        self.cpu_scale = settings.cpu_scale
        self.cpu_log = settings.cpu_log
        self.cpu_log_enable = settings.cpu_log_enable
        self.prometheus_file = settings.prometheus_file

        # Alter RPM thresholds to allow some slop (matches the shell script,
        # where bc truncates toward zero at scale 0).
        self.rpm_cpu_30 = int(1.2 * settings.rpm_cpu_30)
        self.rpm_cpu_max = int(0.8 * settings.rpm_cpu_max)
        self.rpm_periph_30 = int(1.2 * settings.rpm_periph_30)
        self.rpm_periph_max = int(0.8 * settings.rpm_periph_max)

        # Number of whole CPU loops per drive loop.
        self.cpu_loops = int(self.drive_t * 60 / self.cpu_t)

        # These hold the name of the fan whose RPM represents each zone.
        if self.zone_periph == 0:
            self.rpm_periph_key = "FAN4"
            self.rpm_cpu_key = "FANA"
        else:
            self.rpm_periph_key = "FANA"
            self.rpm_cpu_key = "FAN4"

        # Mutable runtime state.
        self.first_time = True
        self.errc = 0.0
        self.errc_valid = True
        self.duty_cpu: Optional[int] = None
        self.duty_periph: Optional[int] = None
        self.duty_cpu_last: Optional[int] = None
        self.duty_periph_last: Optional[int] = None
        self.cpu_temp: Optional[int] = None
        self.mode: Optional[int] = None
        self.mode_text: str = ""
        self.fan_rpm: Dict[str, Optional[int]] = {}
        self.pd = 0
        self.tmean: Optional[float] = None

        # Display strings for the periodic status line.
        self.tmax_str = _MISSING
        self.tmean_str = _MISSING
        self.errc_str = _MISSING
        self.p_str = _MISSING
        self.d_str = _MISSING

        # Mismatch flags.
        self.mismatch = False
        self.mismatch_cpu = False
        self.mismatch_periph = False

        # CPU temperature source detection (FreeBSD sysctl vs ipmitool).
        self.cpu_temp_sysctl = False
        self.cores = 0

        self.devlist: List[str] = []
        self._sdr_text = ""

        # Email notifications (via proxmox-mail-forward).
        self._hostname = socket.gethostname()
        self._mail_forward_bin = self._find_mail_forward()
        # Rate-limit temperature alerts to at most one per day.
        self._last_temp_email: Optional[datetime] = None

    # ---------------------------------------------------------------------------
    # Low-level command helpers.
    # ---------------------------------------------------------------------------
    def _ipmi(self, *raw_args: str) -> str:
        """Runs ipmitool with the given arguments and returns stdout."""
        result = subprocess.run(
            self._ipmi_base + list(raw_args),
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout

    @staticmethod
    def _raw_to_int(text: str) -> int:
        """Converts a hex ``ipmitool raw`` response (e.g. ' 32') to an int."""
        return int(text.strip().replace(" ", ""), 16)

    def _fan_rpm_from_sdr(self, sdr_text: str, name: str) -> Optional[int]:
        """Extracts the RPM for the named fan from ``ipmitool sdr`` output."""
        for line in sdr_text.splitlines():
            if name in line:
                match = re.search(r"\d{3,5}", line)
                if match:
                    return int(match.group())
        return None

    # ---------------------------------------------------------------------------
    # Notifications (via proxmox-mail-forward).
    # ---------------------------------------------------------------------------
    @staticmethod
    def _find_mail_forward() -> Optional[str]:
        """Returns the path to proxmox-mail-forward, or None if not installed."""
        for path in _MAIL_FORWARD_CANDIDATES:
            if os.path.exists(path):
                return path
        return None

    def _send_email(self, subject: str, body: str) -> None:
        """Sends an email through proxmox-mail-forward (a no-op if unavailable)."""
        if self._mail_forward_bin is None:
            _LOGGER.info("proxmox-mail-forward not found; cannot send: %s", subject)
            return

        message = email.message.EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self._hostname}-spinpid2"
        message["To"] = "root"
        message.set_content(body)

        result = subprocess.run(
            [self._mail_forward_bin],
            input=message.as_bytes(),
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            _LOGGER.info(
                "proxmox-mail-forward failed (%s): %s",
                result.returncode,
                result.stderr.decode(errors="replace").strip(),
            )

    def _maybe_temp_alert(self, over_threshold: List[str]) -> None:
        """Emails when a drive or the CPU is over the threshold (once per day).

        Args:
          over_threshold: One human-readable line per source above the threshold
            (empty = no email).
        """
        if not over_threshold:
            return
        now = datetime.now()
        if (
            self._last_temp_email is not None
            and now - self._last_temp_email < timedelta(days=1)
        ):
            return
        self._last_temp_email = now
        lines = "\n".join(over_threshold)
        cpu = self.cpu_temp if self.cpu_temp is not None else "?"
        body = (
            f"Temperature threshold ({_TEMP_ALERT_THRESHOLD} C) exceeded on "
            f"{self._hostname}:\n\n{lines}\n\n"
            f"Current CPU temperature: {cpu} C\n"
        )
        self._send_email(f"[spinpid2] high temperature on {self._hostname}", body)

    # ---------------------------------------------------------------------------
    # Data acquisition.
    # ---------------------------------------------------------------------------
    def read_fan_data(self) -> None:
        """Reads duty cycles (optional), fan mode, and fan RPMs."""
        # If configured, read duty cycles from the board; otherwise keep the
        # last values we set.
        if self.how_duty == 1:
            # 0x30 0x70 0x66 0 <zone> -> read the zone's current duty cycle.
            self.duty_cpu = self._raw_to_int(
                self._ipmi("raw", *_RAW_FAN_DUTY, _RAW_READ, str(self.zone_cpu)),
            )
            self.duty_periph = self._raw_to_int(
                self._ipmi("raw", *_RAW_FAN_DUTY, _RAW_READ, str(self.zone_periph)),
            )

        # 0x30 0x45 0 -> read the current fan mode.
        self.mode = self._raw_to_int(self._ipmi("raw", *_RAW_FAN_MODE, _RAW_READ))
        self.mode_text = _MODE_TEXT.get(self.mode, "")

        self._sdr_text = self._ipmi("sdr")
        for name in ("FAN1", "FAN2", "FAN3", "FAN4", "FANA", "FANB"):
            self.fan_rpm[name] = self._fan_rpm_from_sdr(self._sdr_text, name)
        try:
            self._write_prometheus_metrics()
        except OSError as exc:
            _LOGGER.warning("Could not publish Prometheus fan metrics: %s", exc)

    def _fan_zone(self, name: str) -> str:
        """Returns the configured controller zone for an IPMI fan sensor."""
        hardware_zone = 0 if name[-1:].isdigit() else 1
        if hardware_zone == self.zone_cpu:
            return "cpu"
        if hardware_zone == self.zone_periph:
            return "peripheral"
        return "unknown"

    def _write_prometheus_metrics(self) -> None:
        """Atomically publish IPMI fan RPM and duty through node_exporter."""
        lines = [
            "# HELP proxmox_ipmi_fan_speed_rpm Current IPMI fan speed in revolutions per minute.",
            "# TYPE proxmox_ipmi_fan_speed_rpm gauge",
        ]
        for fan, rpm in sorted(self.fan_rpm.items()):
            if rpm is None:
                continue
            lines.append(
                f'proxmox_ipmi_fan_speed_rpm{{fan="{fan}",zone="{self._fan_zone(fan)}"}} {rpm}',
            )

        lines.extend(
            [
                "# HELP proxmox_ipmi_fan_duty_ratio Current configured fan-zone duty ratio.",
                "# TYPE proxmox_ipmi_fan_duty_ratio gauge",
            ],
        )
        for zone, duty in (
            ("cpu", self.duty_cpu),
            ("peripheral", self.duty_periph),
        ):
            if duty is not None:
                lines.append(
                    f'proxmox_ipmi_fan_duty_ratio{{zone="{zone}"}} {duty / 100:g}',
                )

        lines.extend(
            [
                "# HELP proxmox_ipmi_fan_last_collection_timestamp_seconds Unix timestamp of the last IPMI fan collection.",
                "# TYPE proxmox_ipmi_fan_last_collection_timestamp_seconds gauge",
                f"proxmox_ipmi_fan_last_collection_timestamp_seconds {int(time.time())}",
            ],
        )

        directory = os.path.dirname(self.prometheus_file) or "."
        os.makedirs(directory, mode=0o755, exist_ok=True)
        temporary_path = f"{self.prometheus_file}.{os.getpid()}.tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.prometheus_file)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def _read_cpu_temp(self) -> int:
        """Returns the current CPU temperature in Celsius."""
        if self.cpu_temp_sysctl:
            # FreeBSD: find the hottest core.
            max_core_temp = 0
            for core in range(self.cores + 1):
                out = subprocess.run(
                    ["sysctl", "-n", f"dev.cpu.{core}.temperature"],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
                try:
                    core_temp = int(out.split(".")[0])
                except (ValueError, IndexError):
                    continue
                max_core_temp = max(max_core_temp, core_temp)
            return max_core_temp

        # Linux / fallback: read via ipmitool.
        out = self._ipmi("sensor", "get", "CPU Temp")
        for line in out.splitlines():
            if "Sensor Reading" in line:
                fields = line.split()
                if len(fields) >= 4:
                    return int(float(fields[3]))
        return 0

    # ---------------------------------------------------------------------------
    # Fan adjustment.
    # ---------------------------------------------------------------------------
    def adjust_fans(self, zone: int, duty: int, duty_last: Optional[int]) -> None:
        """Sets a zone's duty cycle if it changed (or on the first pass)."""
        if duty != duty_last or self.first_time:
            # 0x30 0x70 0x66 1 <zone> <duty> -> set the zone's duty cycle.
            self._ipmi("raw", *_RAW_FAN_DUTY, _RAW_SET, str(zone), str(duty))
        self.first_time = False

    def cpu_check_adjust(self) -> None:
        """Reads CPU temperature and adjusts the CPU zone accordingly."""
        self.cpu_temp = self._read_cpu_temp()
        if self.cpu_temp is not None and self.cpu_temp > _TEMP_ALERT_THRESHOLD:
            self._maybe_temp_alert([f"CPU: {self.cpu_temp} C"])
        self.duty_cpu_last = self.duty_cpu

        # Linear scaling with temperature above the reference (integer math to
        # match the shell script).
        duty_cpu = (self.cpu_temp - self.cpu_ref) * self.cpu_scale + self.duty_cpu_min
        duty_cpu = min(duty_cpu, self.duty_cpu_max)
        duty_cpu = max(duty_cpu, self.duty_cpu_min)
        self.duty_cpu = duty_cpu

        self.adjust_fans(self.zone_cpu, self.duty_cpu, self.duty_cpu_last)

        # Use this short CPU cycle to also let the peripheral fans come down if
        # the PID correction is negative and drives are at least 1 C below the
        # setpoint. This is experimental (see notes in the original script).
        if self.pd < 0 and self.tmean is not None and self.tmean < (self.setpoint - 1):
            self.duty_periph_last = self.duty_periph
            self.duty_periph = max(
                (self.duty_periph or self.duty_periph_min) + self.pd,
                self.duty_periph_min,
            )
            self.adjust_fans(
                self.zone_periph,
                self.duty_periph,
                self.duty_periph_last,
            )

        time.sleep(self.cpu_t)

        if self.cpu_log_enable:
            self._print_interim_cpu()

    def drives_check_adjust(self) -> str:
        """Reads every drive, runs the PID loop, and adjusts the drive zone.

        Returns:
          The formatted per-drive status cells plus the Tmax/Tmean summary, ready
          to be appended to the periodic status line.
        """
        tmax = 0
        tsum = 0
        spinning = 0
        cells = []
        hot_drives: List[str] = []

        for device in self.devlist:
            result = subprocess.run(
                ["smartctl", "-a", "-n", "standby", device],
                capture_output=True,
                text=True,
                check=False,
            )
            bit0 = result.returncode & 1
            bit1 = result.returncode & 2
            if bit0 == 0:
                status = "*" if bit1 == 0 else "_"
            else:
                # smartctl returns 1 (bit 0 set) for a missing drive.
                status = "?"

            temp: Optional[int] = None
            if status == "*":
                temp = self._parse_drive_temp(result.stdout)
                if temp is not None:
                    tsum += temp
                    tmax = max(tmax, temp)
                    spinning += 1
                    if temp > _TEMP_ALERT_THRESHOLD:
                        hot_drives.append(f"{device}: {temp} C")

            # Spinning drives show their temperature; others are left blank.
            cell = "" if temp is None else temp
            cells.append(f"{status}{cell:<2}  ")

        self._maybe_temp_alert(hot_drives)

        self.duty_periph_last = self.duty_periph

        if spinning == 0:
            # No disks spinning: drop the drive zone to its minimum.
            self.tmean = None
            self.tmax_str = _MISSING
            self.tmean_str = _MISSING
            self.errc_str = _MISSING
            self.p_str = _MISSING
            self.d_str = _MISSING
            self.errc_valid = False
            self.pd = 0
            self.duty_periph = self.duty_periph_min
        else:
            errp = self.errc if self.errc_valid else 0.0
            tmean = tsum / spinning
            errc = tmean - self.setpoint
            p = self.kp * errc
            d = self.kd * (errc - errp) / self.drive_t
            pd = int(round(p + d))

            self.tmean = tmean
            self.errc = errc
            self.errc_valid = True
            self.pd = pd

            self.tmax_str = str(tmax)
            self.tmean_str = f"{tmean:.2f}"
            self.errc_str = f"{errc:.2f}"
            self.p_str = f"{p:.2f}"
            self.d_str = f"{d:.2f}"

            duty_periph = (self.duty_periph_last or self.duty_periph_min) + pd
            duty_periph = min(duty_periph, self.duty_periph_max)
            duty_periph = max(duty_periph, self.duty_periph_min)
            self.duty_periph = duty_periph

        self.adjust_fans(self.zone_periph, self.duty_periph, self.duty_periph_last)

        drive_cells = "".join(cells)
        return f"{drive_cells}^{self.tmax_str:<3} {self.tmean_str:>5}"

    @staticmethod
    def _parse_drive_temp(smart_output: str) -> Optional[int]:
        """Extracts a drive temperature from ``smartctl -a`` output."""
        if "Temperature_Celsius" in smart_output:
            # Most SATA drives: take the 10th field of the attribute line.
            for line in smart_output.splitlines():
                if "Temperature_Celsius" in line:
                    fields = line.split()
                    if len(fields) >= 10:
                        try:
                            return int(fields[9])
                        except ValueError:
                            return None
        else:
            # NVMe: "Temperature:   48 Celsius".
            for line in smart_output.splitlines():
                if "Temperature:" in line:
                    fields = line.split()
                    if len(fields) >= 2:
                        try:
                            return int(fields[1])
                        except ValueError:
                            return None
        return None

    def _print_interim_cpu(self) -> None:
        """Appends a CPU temperature/duty line to the interim CPU log."""
        rpm = self._fan_rpm_from_sdr(self._ipmi("sdr"), self.rpm_cpu_key)
        now = datetime.now().strftime("%H:%M:%S")
        rpm_display = _MISSING if rpm is None else rpm
        line = (
            f"{now}  {rpm_display:>7} {self.cpu_temp or 0:>5} {self.duty_cpu or 0:>5}"
        )
        with open(self.cpu_log, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    # ---------------------------------------------------------------------------
    # Mismatch detection and recovery.
    # ---------------------------------------------------------------------------
    def mismatch_test(self) -> None:
        """Detects a mismatch between commanded duty and reported fan RPMs."""
        self.mismatch = False
        self.mismatch_cpu = False
        self.mismatch_periph = False

        rpm_cpu = self.fan_rpm.get(self.rpm_cpu_key) or 0
        rpm_periph = self.fan_rpm.get(self.rpm_periph_key) or 0
        duty_cpu = self.duty_cpu or 0
        duty_periph = self.duty_periph or 0

        if (duty_cpu >= 95 and rpm_cpu < self.rpm_cpu_max) or (
            duty_cpu < 25 and rpm_cpu > self.rpm_cpu_30
        ):
            self.mismatch = True
            self.mismatch_cpu = True
            _LOGGER.info(
                f"\nMismatch between CPU Duty and RPMs -- "
                f"DUTY_CPU={duty_cpu}; RPM_CPU={rpm_cpu}",
            )

        if (duty_periph >= 95 and rpm_periph < self.rpm_periph_max) or (
            duty_periph < 25 and rpm_periph > self.rpm_periph_30
        ):
            self.mismatch = True
            self.mismatch_periph = True
            _LOGGER.info(
                f"\nMismatch between PERIPH Duty and RPMs -- "
                f"DUTY_PERIPH={duty_periph}; RPM_PERIPH={rpm_periph}",
            )

    def force_set_fans(self) -> None:
        """Forces a re-set of any zone whose duty/RPM mismatched."""
        if self.mismatch_cpu and self.duty_cpu is not None:
            self.first_time = True  # Forces adjust_fans to act.
            self.adjust_fans(self.zone_cpu, self.duty_cpu, self.duty_cpu_last)
            _LOGGER.info("Attempting to fix CPU mismatch  ")
            time.sleep(5)
        if self.mismatch_periph and self.duty_periph is not None:
            self.first_time = True
            self.adjust_fans(
                self.zone_periph,
                self.duty_periph,
                self.duty_periph_last,
            )
            _LOGGER.info("Attempting to fix PERIPH mismatch  ")
            time.sleep(5)

    def reset_bmc(self) -> None:
        """Cold-resets the BMC after repeated failures to fix a mismatch."""
        now = datetime.now().strftime("%H:%M:%S")
        _LOGGER.info(
            f"{now}  Resetting BMC after second attempt failed to fix mismatch -- ",
        )
        # "bmc reset cold" performs a full BMC reboot; give it time to come back.
        self._ipmi("bmc", "reset", "cold")
        time.sleep(120)
        self.read_fan_data()

    # ---------------------------------------------------------------------------
    # Header and setup.
    # ---------------------------------------------------------------------------
    def print_header(self) -> None:
        """Prints the table header (called at start and each quarter day)."""
        date = datetime.now().strftime("%A, %b %d")
        spaces = len(self.devlist) * 5 + 42
        _LOGGER.info(
            f"\n{date:<{spaces}} {'CPU':>3} {'New_Fan%':>16} "
            f"{'New_RPM_____________________':>29} ",
        )

        columns = " " * 10
        columns += "".join(f"{_abbreviate_device(d):<5}" for d in self.devlist)
        # Note: the "PER" column keeps its short header to preserve the width of
        # this fixed-layout table (the peripheral duty is printed under it).
        columns += (
            f"{'Tmax':>4} {'Tmean':>5} {'ERRc':>6} {'P':>6} {'D':>6} "
            f"{'TEMP':>3} {'MODE':<7} {'CPU'} {'PER':<4} {'FANA':>5} "
            f"{'FANB':>5} {'FAN1':>5} {'FAN2':>5} {'FAN3':>5} "
            f"{'FAN4':>5}"
        )
        _LOGGER.info(columns)

    def _detect_devices(self) -> None:
        """Populates the drive list from ``lshw`` output."""
        out = subprocess.run(
            ["lshw", "-class", "disk", "-short"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        self.devlist = []
        for line in out.splitlines():
            if ("/dev/nv" in line or "/dev/sd" in line) and "USB" not in line:
                fields = line.split()
                if len(fields) >= 2:
                    self.devlist.append(fields[1])

    def _detect_cpu_temp_source(self) -> None:
        """Detects whether CPU temperature is available via sysctl (FreeBSD)."""
        try:
            out = subprocess.run(
                ["sysctl", "-a"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
        except FileNotFoundError:
            out = ""
        self.cpu_temp_sysctl = out.count("dev.cpu.0.temperature") > 0
        if self.cpu_temp_sysctl:
            _LOGGER.info("Getting CPU temperatures via sysctl ")
            ncpu = subprocess.run(
                ["sysctl", "-n", "hw.ncpu"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            # -1 because numbering starts at 0.
            self.cores = int(ncpu) - 1 if ncpu.isdigit() else 0
        else:
            _LOGGER.info(
                "Getting CPU temperature via ipmitool (sysctl not available) ",
            )

    def setup(self) -> None:
        """Performs one-time initialization: settings, devices, initial duty."""
        duty_source = (
            "Reading fan duty from board "
            if self.how_duty == 1
            else "Assuming fan duty as set "
        )
        _LOGGER.info(
            f"\n****** SETTINGS ******\n"
            f"CPU zone {self.zone_cpu}; Peripheral zone {self.zone_periph}\n"
            f"CPU fans min/max duty cycle: "
            f"{self.duty_cpu_min}/{self.duty_cpu_max}\n"
            f"PERIPH fans min/max duty cycle: "
            f"{self.duty_periph_min}/{self.duty_periph_max}\n"
            f"CPU fans - measured RPMs at 30% and 100% duty cycle: "
            f"{self.settings.rpm_cpu_30}/{self.settings.rpm_cpu_max}\n"
            f"PERIPH fans - measured RPMs at 30% and 100% duty cycle: "
            f"{self.settings.rpm_periph_30}/{self.settings.rpm_periph_max}\n"
            f"Drive temperature setpoint (C): {self.setpoint}\n"
            f"KP={self.kp}, KD={self.kd}\n"
            f"Drive check interval (main cycle; minutes): {self.drive_t}\n"
            f"CPU check interval (seconds): {self.cpu_t}\n"
            f"CPU reference temperature (C): {self.cpu_ref}\n"
            f"CPU scalar: {self.cpu_scale}\n"
            f"{duty_source}",
        )

        self._detect_cpu_temp_source()
        self._detect_devices()
        self.read_fan_data()

        # If mode is not Full, set it so the BMC doesn't override the duty cycle.
        if self.mode != _FAN_MODE_FULL:
            # 0x30 0x45 1 1 -> set fan mode to Full.
            self._ipmi("raw", *_RAW_FAN_MODE, _RAW_SET, str(_FAN_MODE_FULL))
            time.sleep(1)

        # Start the fan duty at a reasonable value if fans are spinning fast or we
        # never read a duty cycle.
        rpm_periph = self.fan_rpm.get(self.rpm_periph_key) or 0
        if rpm_periph >= self.rpm_periph_max or self.duty_periph is None:
            # 0x30 0x70 0x66 1 <zone> 50 -> set the peripheral zone to 50% duty.
            self._ipmi("raw", *_RAW_FAN_DUTY, _RAW_SET, str(self.zone_periph), "50")
            self.duty_periph = 50
            time.sleep(1)

        rpm_cpu = self.fan_rpm.get(self.rpm_cpu_key) or 0
        if rpm_cpu >= self.rpm_cpu_max or self.duty_cpu is None:
            # 0x30 0x70 0x66 1 <zone> 50 -> set the CPU zone to 50% duty.
            self._ipmi("raw", *_RAW_FAN_DUTY, _RAW_SET, str(self.zone_cpu), "50")
            self.duty_cpu = 50
            time.sleep(1)

        key = "Key to drive status symbols:  * spinning;  _ standby;  ? unknown"
        _LOGGER.info(f"\n{key} {'Version':>36} {VERSION} ")
        self.print_header()

        # Seed CPU temperature for the first round of printing.
        cpu_temp_lines = "\n".join(
            line for line in self._sdr_text.splitlines() if "CPU Temp" in line
        )
        match = re.search(r"\d{2,5}", cpu_temp_lines)
        self.cpu_temp = int(match.group()) if match else 0

        if self.cpu_log_enable:
            date = datetime.now().strftime("%A, %b %d")
            with open(self.cpu_log, "w", encoding="utf-8") as handle:
                handle.write(
                    f"{date} \nPrinted every CPU cycle \n"
                    f"{self.rpm_cpu_key:>17} {'Temp':>5} {'Duty':>5} \n",
                )

    # ---------------------------------------------------------------------------
    # Main loop.
    # ---------------------------------------------------------------------------
    def run(self) -> None:
        """Runs the main control loop forever."""
        self.setup()

        while True:
            # Print the header every quarter day.
            now = datetime.now()
            hm = now.hour * 100 + now.minute
            if (hm % 600) < self.drive_t:
                self.print_header()

            time_str = now.strftime("%H:%M:%S")
            drive_line = self.drives_check_adjust()

            # Let fans equilibrate to the new duty before reading them back.
            time.sleep(5)
            self.read_fan_data()

            summary = (
                f"{self.errc_str:>7} {self.p_str:>6} {self.d_str:>6.6} "
                f"{self.cpu_temp or 0:>4} {self.mode_text:<7} "
                f"{self.duty_cpu or 0:>3} {self.duty_periph or 0:>3} "
                f"{self._fan_display('FANA'):>6} {self._fan_display('FANB'):>5} "
                f"{self._fan_display('FAN1'):>5} {self._fan_display('FAN2'):>5} "
                f"{self._fan_display('FAN3'):>5} {self._fan_display('FAN4'):>5}"
            )
            _LOGGER.info(f"{time_str}  {drive_line}{summary}")

            self._recover_from_mismatch()

            for _ in range(self.cpu_loops):
                self.cpu_check_adjust()

    def _fan_display(self, name: str) -> str:
        """Returns a fan RPM for display, or a placeholder if unavailable."""
        value = self.fan_rpm.get(name)
        return _MISSING if value is None else str(value)

    def _recover_from_mismatch(self) -> None:
        """Runs the duty/RPM mismatch recovery loop (with optional BMC reset)."""
        attempts = 0
        self.mismatch_test()

        while True:
            if self.mismatch:
                self.force_set_fans()
                attempts += 1
                self.read_fan_data()
                self.mismatch_test()
            else:
                break

            if attempts == 2:
                if self.mismatch:
                    self.reset_bmc()
                    self.force_set_fans()
                    self.read_fan_data()
                    self.mismatch_test()
                else:
                    break

            if attempts == 3:
                break


def main(argv: Optional[List[str]] = None) -> int:
    """Program entry point."""
    args = _parse_args(argv)
    try:
        settings = load_settings(args.settings, args.schema)
    except (OSError, yaml.YAMLError, jsonschema.ValidationError) as exc:
        print(f"spinpid2: invalid settings: {exc}", file=sys.stderr)
        return 2

    _setup_logging(settings.log_file, settings.console)
    controller = FanController(settings)
    try:
        controller.run()
    except KeyboardInterrupt:
        _LOGGER.info("\nInterrupted; exiting.")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# Tuning advice (copied from spinpid2.sh)
# ---------------------------------------------------------------------------
# PID tuning advice on the internet generally does not work well in this
# application.
#
# First run spincheck.sh and get familiar with your temperature and fan
# variations without any intervention.
#
# Choose a setpoint that is an actual observed Tmean, given the number of
# drives you have. It should be the Tmean associated with the Tmax that you
# want.
#
# Start with KP low. Find the lowest ERRc (which is Tmean - setpoint) in the
# output other than 0 (don't worry about sign +/-). Set KP to 0.5 / ERRc,
# rounded up to an integer. My lowest ERRc is 0.14. 0.5 / 0.14 is 3.6, and I
# find KP = 4 is adequate. Higher KP will give a more aggressive response to
# error, but the downside may be overshooting the setpoint and oscillation.
# KD offsets that, but raising them both makes things unstable and harder to
# tune.
#
# Set KD at about KP*10.
#
# Get Tmean within ~0.3 degree of SP before starting the script.
#
# Start the script and run for a few hours or so. If Tmean oscillates (best to
# graph it), you probably need to reduce KD. If no oscillation but response is
# too slow, raise KD.
#
# Stop the script and get Tmean at least 1 C off SP. Restart. If there is
# overshoot and it goes through some cycles, you may need to reduce KD.
#
# If you have problems, examine P and D in the log and see which is messing
# you up.
