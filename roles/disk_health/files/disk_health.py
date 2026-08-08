#!/usr/bin/env python3
"""Report SMART and NVMe health for every physical disk on a Proxmox host."""

import argparse
import dataclasses
import datetime
import email.message
import json
import logging
import os
import re
import socket
import subprocess
import sys
from typing import Dict, List, Optional, Sequence

VERSION = "1.0.0"
_LOGGER = logging.getLogger("disk_health")
_DEFAULT_LOG_FILE = "/var/log/disk_health.log"
_MAIL_FORWARD_CANDIDATES = (
    "/usr/libexec/proxmox-mail-forward",
    "/usr/bin/proxmox-mail-forward",
)
_EXCLUDED_DEVICE_PREFIXES = ("loop", "zram", "dm-")
_SUNDAY = 7

_SATA_ATTRIBUTES = {
    "temperature": ("Temperature_Celsius",),
    "power_on_hours": ("Power_On_Hours",),
    "wear": ("Wear_Leveling_Count", "Media_Wearout_Indicator"),
    "reallocated_sectors": ("Reallocated_Sector_Ct",),
    "pending_sectors": ("Current_Pending_Sector",),
    "offline_uncorrectable": ("Offline_Uncorrectable",),
    "udma_crc_errors": ("UDMA_CRC_Error_Count",),
}

_NVME_LABELS = {
    "temperature": ("Temperature",),
    "available_spare": ("Available Spare",),
    "available_spare_threshold": ("Available Spare Threshold",),
    "percentage_used": ("Percentage Used",),
    "data_units_written": ("Data Units Written",),
    "power_on_hours": ("Power On Hours",),
    "unsafe_shutdowns": ("Unsafe Shutdowns",),
    "media_integrity_errors": ("Media and Data Integrity Errors",),
}


@dataclasses.dataclass(frozen=True)
class Disk:
    """A physical block device returned by lsblk."""

    path: str
    model: str
    size_bytes: int


@dataclasses.dataclass
class DiskReport:
    """Parsed health report for one disk."""

    disk: Disk
    protocol: str
    health: str
    metrics: Dict[str, str]
    latest_self_test: str
    warnings: List[str]
    smartctl_exit_status: int


@dataclasses.dataclass(frozen=True)
class Config:
    """Runtime configuration."""

    log_file: str
    recipient: str
    email_enabled: bool
    self_tests_enabled: bool
    mail_forward_bin: Optional[str]
    now: datetime.datetime

    @property
    def week_number(self) -> int:
        return int(self.now.strftime("%U"))

    @property
    def self_test_type(self) -> Optional[str]:
        if not self.self_tests_enabled or self.now.isoweekday() != _SUNDAY:
            return None
        return "short" if self.week_number % 2 == 1 else "long"


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Email SMART and NVMe health for all physical disks.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--log-file", default=_DEFAULT_LOG_FILE)
    parser.add_argument("--recipient", default="root")
    parser.add_argument("--no-email", dest="email_enabled", action="store_false")
    parser.add_argument(
        "--no-self-tests",
        dest="self_tests_enabled",
        action="store_false",
    )
    parser.add_argument("--mail-forward-bin", default=None, metavar="PATH")
    return parser.parse_args(argv)


def _setup_logging(log_file: str) -> None:
    _LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "DISK_HEALTH %(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    _LOGGER.addHandler(file_handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    _LOGGER.addHandler(console_handler)


def _run(command: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command),
        capture_output=True,
        text=True,
        check=False,
    )


def _human_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or unit == "PiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size_bytes} B"


def list_physical_disks() -> List[Disk]:
    """Enumerate physical disks, excluding loop, zram, and device-mapper nodes."""
    result = _run(
        [
            "lsblk",
            "--json",
            "--bytes",
            "--nodeps",
            "--output",
            "NAME,TYPE,MODEL,SIZE",
        ],
    )
    if result.returncode != 0:
        raise RuntimeError(f"lsblk failed: {result.stderr.strip()}")
    try:
        devices = json.loads(result.stdout).get("blockdevices", [])
    except (AttributeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not parse lsblk output: {exc}") from exc

    disks = []
    for device in devices:
        name = str(device.get("name") or "")
        if device.get("type") != "disk":
            continue
        if not name or name.startswith(_EXCLUDED_DEVICE_PREFIXES):
            continue
        try:
            size_bytes = int(device.get("size") or 0)
        except (TypeError, ValueError):
            size_bytes = 0
        disks.append(
            Disk(
                path=f"/dev/{name}",
                model=str(device.get("model") or "Unknown model").strip(),
                size_bytes=size_bytes,
            ),
        )
    return sorted(disks, key=lambda disk: disk.path)


def _parse_health(output: str) -> str:
    for line in output.splitlines():
        if re.search(r"SMART (?:overall-health|Health Status)", line, re.I):
            return line.split(":", 1)[-1].strip()
    return "SMART not available"


def _parse_sata_attribute(output: str, names: Sequence[str]) -> Optional[str]:
    # Preserve the caller's preference order. In particular,
    # Wear_Leveling_Count should win over Media_Wearout_Indicator when a drive
    # happens to expose both.
    lines = output.splitlines()
    for name in names:
        for line in lines:
            fields = line.split()
            if len(fields) >= 10 and fields[1] == name:
                return fields[9]
    return None


def parse_sata_metrics(output: str) -> Dict[str, str]:
    """Parse every SATA metric exposed by the upstream disk-health tool."""
    metrics = {}
    for key, names in _SATA_ATTRIBUTES.items():
        value = _parse_sata_attribute(output, names)
        if value is not None:
            metrics[key] = value
    return metrics


def parse_nvme_metrics(output: str) -> Dict[str, str]:
    """Parse every NVMe metric exposed by the upstream disk-health tool."""
    metrics = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        label, value = (part.strip() for part in line.split(":", 1))
        for key, labels in _NVME_LABELS.items():
            if label in labels and key not in metrics:
                metrics[key] = value
    return metrics


def _latest_self_test(output: str) -> str:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("# 1") or stripped.startswith("#1"):
            return " ".join(stripped.split())
    lowered = output.lower()
    if "no self-tests have been logged" in lowered:
        return "No self-tests have been logged"
    if "not supported" in lowered or not output.strip():
        return "Self-test log unavailable"
    return "No completed self-test entry found"


def _integer(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    match = re.search(r"[\d,]+", value)
    if not match:
        return None
    try:
        return int(match.group().replace(",", ""))
    except ValueError:
        return None


def _percent(value: Optional[str]) -> Optional[int]:
    return _integer(value)


def _metric_warnings(protocol: str, metrics: Dict[str, str]) -> List[str]:
    warnings = []
    if protocol == "NVMe":
        media_errors = _integer(metrics.get("media_integrity_errors"))
        used = _percent(metrics.get("percentage_used"))
        spare = _percent(metrics.get("available_spare"))
        threshold = _percent(metrics.get("available_spare_threshold"))
        if media_errors and media_errors > 0:
            warnings.append(f"Media/data-integrity errors: {media_errors}")
        if used is not None and used >= 100:
            warnings.append(f"Percentage used is {used}%")
        if spare is not None and threshold is not None and spare <= threshold:
            warnings.append(
                f"Available spare {spare}% is at/below threshold {threshold}%",
            )
    else:
        warning_labels = {
            "reallocated_sectors": "Reallocated sectors",
            "pending_sectors": "Pending sectors",
            "offline_uncorrectable": "Offline uncorrectable sectors",
            "udma_crc_errors": "UDMA CRC errors",
        }
        for key, label in warning_labels.items():
            value = _integer(metrics.get(key))
            if value and value > 0:
                warnings.append(f"{label}: {value}")
    return warnings


def inspect_disk(disk: Disk) -> DiskReport:
    """Collect health, attributes, and self-test state for one disk."""
    smart = _run(["smartctl", "-a", disk.path])
    output = "\n".join(part for part in (smart.stdout, smart.stderr) if part)
    protocol = (
        "NVMe" if disk.path.startswith("/dev/nvme") or "NVMe" in output else "SATA"
    )
    metrics = (
        parse_nvme_metrics(output) if protocol == "NVMe" else parse_sata_metrics(output)
    )
    health = _parse_health(output)
    self_test = _run(["smartctl", "-l", "selftest", disk.path])
    warnings = _metric_warnings(protocol, metrics)
    if health.upper() not in ("PASSED", "OK"):
        warnings.append(f"Overall SMART health: {health}")
    # smartctl uses bits 3-7 for failing health, prefail/past-threshold
    # attributes, error-log entries, and self-test errors.
    if smart.returncode & 0xF8:
        warnings.append(f"smartctl failure flags: 0x{smart.returncode & 0xF8:02x}")
    return DiskReport(
        disk=disk,
        protocol=protocol,
        health=health,
        metrics=metrics,
        latest_self_test=_latest_self_test(self_test.stdout),
        warnings=warnings,
        smartctl_exit_status=smart.returncode,
    )


def _format_metric(label: str, value: Optional[str]) -> str:
    return f"  {label}: {value if value is not None else 'Unavailable'}"


def format_report(report: DiskReport) -> str:
    """Format one report with all upstream disk-health metrics."""
    lines = [
        "=" * 68,
        (
            f"{report.disk.path} | {_human_size(report.disk.size_bytes)} | "
            f"{report.disk.model} | {report.protocol}"
        ),
        "=" * 68,
        f"  Health: {report.health}",
        f"  Latest Self-Test: {report.latest_self_test}",
    ]
    if report.protocol == "NVMe":
        labels = (
            ("temperature", "Temperature"),
            ("available_spare", "Available Spare"),
            ("available_spare_threshold", "Available Spare Threshold"),
            ("percentage_used", "Percentage Used"),
            ("data_units_written", "Data Units Written"),
            ("power_on_hours", "Power On Hours"),
            ("unsafe_shutdowns", "Unsafe Shutdowns"),
            ("media_integrity_errors", "Media/Data Integrity Errors"),
        )
    else:
        labels = (
            ("temperature", "Temperature"),
            ("power_on_hours", "Power On Hours"),
            ("wear", "Wear Leveling/Wearout"),
            ("reallocated_sectors", "Reallocated Sectors"),
            ("pending_sectors", "Pending Sectors"),
            ("offline_uncorrectable", "Offline Uncorrectable"),
            ("udma_crc_errors", "UDMA CRC Errors"),
        )
    lines.extend(
        _format_metric(label, report.metrics.get(key)) for key, label in labels
    )
    if report.warnings:
        lines.append("  WARNINGS:")
        lines.extend(f"    - {warning}" for warning in report.warnings)
    else:
        lines.append("  Indicators: OK")
    return "\n".join(lines)


def _find_mail_forward(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit if os.path.exists(explicit) else None
    return next(
        (path for path in _MAIL_FORWARD_CANDIDATES if os.path.exists(path)),
        None,
    )


def send_email(config: Config, subject: str, body: str) -> bool:
    if not config.email_enabled:
        _LOGGER.info("Email disabled; report was not sent")
        return True
    mail_forward = _find_mail_forward(config.mail_forward_bin)
    if mail_forward is None:
        _LOGGER.error("proxmox-mail-forward was not found; report cannot be sent")
        return False
    message = email.message.EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{socket.gethostname()}-disk-health"
    message["To"] = config.recipient
    message.set_content(body)
    result = subprocess.run(
        [mail_forward],
        input=message.as_bytes(),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        _LOGGER.error(
            "proxmox-mail-forward failed (%s): %s",
            result.returncode,
            result.stderr.decode(errors="replace").strip(),
        )
        return False
    return True


def start_self_tests(disks: Sequence[Disk], test_type: Optional[str]) -> List[str]:
    if test_type is None:
        return []
    messages = []
    for disk in disks:
        result = _run(["smartctl", "-t", test_type, disk.path])
        if result.returncode & 0x03:
            messages.append(f"{disk.path}: failed to start {test_type} self-test")
        else:
            messages.append(f"{disk.path}: started {test_type} self-test")
    return messages


def run(config: Config) -> int:
    try:
        disks = list_physical_disks()
    except RuntimeError as exc:
        _LOGGER.error("%s", exc)
        return 1
    if not disks:
        _LOGGER.warning("No physical disks found")
        return 0

    reports = [inspect_disk(disk) for disk in disks]
    test_messages = start_self_tests(disks, config.self_test_type)
    warning_count = sum(len(report.warnings) for report in reports)
    header = (
        f"Disk health report for {socket.gethostname()} at "
        f"{config.now.isoformat(timespec='seconds')}\n"
        f"Disks: {len(reports)}; warnings: {warning_count}\n"
    )
    if test_messages:
        header += "\nScheduled self-tests:\n" + "\n".join(test_messages) + "\n"
    body = header + "\n" + "\n\n".join(format_report(report) for report in reports)
    for line in body.splitlines():
        _LOGGER.warning(line) if warning_count else _LOGGER.info(line)
    status = "WARNING" if warning_count else "OK"
    subject = f"[Disk Health] {status} on {socket.gethostname()}"
    return 0 if send_email(config, subject, body) else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    _setup_logging(args.log_file)
    config = Config(
        log_file=args.log_file,
        recipient=args.recipient,
        email_enabled=args.email_enabled,
        self_tests_enabled=args.self_tests_enabled,
        mail_forward_bin=args.mail_forward_bin,
        now=datetime.datetime.now(),
    )
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
