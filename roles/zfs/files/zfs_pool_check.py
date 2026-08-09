#!/usr/bin/env python3
"""ZFS pool health check and scheduled maintenance.

This is a Python 3 port of ``zfs_pool_check.sh``. For every imported ZFS pool
it:

  * Enables ``autotrim`` on flash-backed pools (name contains ``nvme``/``ssd``
    or is ``rpool``) and ``autoexpand`` on every pool.
  * Logs the pool health, size, free space, and capacity (at ``ERROR`` level
    when the pool is not ``ONLINE``).
  * Starts a scrub on Saturdays of odd-numbered weeks and logs the status of
    the most recent scrub (at ``WARNING`` level when it did not finish with
    zero errors).

The schedule matches the original shell script exactly: the day of week comes
from ``date +%u`` (Monday=1 .. Sunday=7) and the week number from ``date +%U``
(Sunday as the first day of the week).

It sends email notifications through Proxmox's
``proxmox-mail-forward`` helper (so they reach whatever the Proxmox
notification system is configured to use):

  * A scrub alert whenever the most recently completed scrub repaired data or
    reported errors. This is de-duplicated via a small state file so the daily
    run does not re-send the same alert until a new scrub completes.

The script is intended to be run once per day from a systemd timer, but it is
idempotent and safe to run more often.

Example:
  sudo ./zfs_pool_check.py --log-file /var/log/zfs_pool_check.log
  sudo ./zfs_pool_check.py --dry-run          # log actions without running them
  sudo ./zfs_pool_check.py --no-email         # skip notifications
"""

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
from typing import Dict, List, Optional, Sequence, Tuple

VERSION = "2024-py.1"

_LOGGER = logging.getLogger("zfs_pool_check")

_DEFAULT_LOG_FILE = "/var/log/zfs_pool_check.log"

# State file used to de-duplicate scrub-repair alerts across daily runs.
_DEFAULT_STATE_FILE = "/var/lib/zfs_pool_check/state.json"
_DEFAULT_PROMETHEUS_FILE = (
    "/var/lib/node_exporter/textfile_collector/proxmox_zfs_vdev_health.prom"
)

# Proxmox's mail forwarder moved from /usr/bin to /usr/libexec in PVE 9.
_MAIL_FORWARD_CANDIDATES = (
    "/usr/libexec/proxmox-mail-forward",  # PVE 9 / trixie
    "/usr/bin/proxmox-mail-forward",  # PVE 8 / bookworm
)

# A pool gets ``autotrim`` enabled when its name contains one of these
# substrings or matches one of the exact names below (flash-backed pools).
_AUTOTRIM_SUBSTRINGS = ("nvme", "ssd")
_AUTOTRIM_EXACT = ("rpool",)

# Day-of-week values as produced by ``date +%u`` / ``datetime.isoweekday()``.
_SATURDAY = 6
_VDEV_STATES = {
    "ONLINE",
    "DEGRADED",
    "FAULTED",
    "OFFLINE",
    "REMOVED",
    "UNAVAIL",
    "AVAIL",
    "INUSE",
    "SUSPENDED",
}
_HEALTHY_VDEV_STATES = {"ONLINE", "AVAIL", "INUSE"}
_VDEV_CLASSES = {"logs", "cache", "spares", "special", "dedup"}


@dataclasses.dataclass(frozen=True)
class VdevHealth:
    """Current health state for one ZFS topology node."""

    pool: str
    vdev: str
    vdev_class: str
    state: str


@dataclasses.dataclass(frozen=True)
class Config:
    """Resolved runtime configuration."""

    log_file: str
    console: bool
    dry_run: bool
    pools: Optional[List[str]]
    email_enabled: bool
    mail_forward_bin: Optional[str]
    state_file: str
    prometheus_file: str
    metrics_only: bool
    now: datetime.datetime

    @property
    def day_of_week(self) -> int:
        """Day of the week, Monday=1 .. Sunday=7 (matches ``date +%u``)."""
        return self.now.isoweekday()

    @property
    def week_number(self) -> int:
        """Week of the year, Sunday as the first day (matches ``date +%U``)."""
        return int(self.now.strftime("%U"))

    @property
    def is_odd_week(self) -> bool:
        return self.week_number % 2 == 1


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parses command line arguments.

    Args:
      argv: Optional list of arguments; defaults to ``sys.argv``.

    Returns:
      The populated argparse namespace.
    """
    parser = argparse.ArgumentParser(
        description="Check ZFS pool health and run scheduled maintenance "
        "(autotrim/autoexpand and scrubs), emailing scrub-repair alerts.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument(
        "--log-file",
        default=_DEFAULT_LOG_FILE,
        help="Path to append log lines to.",
    )
    parser.add_argument(
        "--no-console",
        dest="console",
        action="store_false",
        help="Do not also emit log lines to stdout.",
    )
    parser.add_argument(
        "--pool",
        dest="pools",
        action="append",
        metavar="NAME",
        help="Only operate on this pool (may be repeated). Defaults to all "
        "imported pools.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log the maintenance actions and emails that would run/send "
        "without executing them.",
    )
    parser.add_argument(
        "--no-email",
        dest="email_enabled",
        action="store_false",
        help="Do not send email notifications.",
    )
    parser.add_argument(
        "--mail-forward-bin",
        default=None,
        metavar="PATH",
        help="Path to proxmox-mail-forward. Defaults to auto-detection.",
    )
    parser.add_argument(
        "--state-file",
        default=_DEFAULT_STATE_FILE,
        help="Path used to de-duplicate scrub-repair alerts across runs.",
    )
    parser.add_argument(
        "--prometheus-file",
        default=_DEFAULT_PROMETHEUS_FILE,
        help="Node exporter textfile output for ZFS vdev health.",
    )
    parser.add_argument(
        "--metrics-only",
        action="store_true",
        help="Publish read-only vdev health metrics without running maintenance.",
    )
    return parser.parse_args(argv)


def parse_vdev_health(pool: str, status: str) -> List[VdevHealth]:
    """Parse topology health from ``zpool status -p -P`` output.

    The pool root is omitted because node exporter's ZFS collector already
    publishes it as ``node_zfs_zpool_state``. Topology groups (mirror/raidz)
    and leaf devices are retained so a degraded branch is visible even when
    its parent pool can still serve I/O.
    """
    vdevs: List[VdevHealth] = []
    in_config = False
    root_seen = False
    vdev_class = "data"
    for raw_line in status.splitlines():
        line = raw_line.strip()
        if line == "config:":
            in_config = True
            continue
        if not in_config:
            continue
        if line.startswith("errors:"):
            break
        if not line or line.startswith("NAME "):
            continue
        if line in _VDEV_CLASSES:
            vdev_class = line
            continue

        fields = line.split()
        if len(fields) < 2 or fields[1].upper() not in _VDEV_STATES:
            continue
        name, state = fields[0], fields[1].upper()
        if not root_seen and name == pool:
            root_seen = True
            continue
        if not root_seen:
            continue
        vdevs.append(VdevHealth(pool, name, vdev_class, state))
    return vdevs


def _prometheus_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def write_vdev_metrics(
    path: str,
    vdevs: Sequence[VdevHealth],
    collected_at: datetime.datetime,
) -> None:
    """Atomically publish ZFS vdev health for node exporter's textfile input."""
    lines = [
        "# HELP proxmox_zfs_vdev_healthy Whether the ZFS vdev is in a healthy state.",
        "# TYPE proxmox_zfs_vdev_healthy gauge",
    ]
    for vdev in vdevs:
        labels = {
            "pool": vdev.pool,
            "vdev": vdev.vdev,
            "class": vdev.vdev_class,
            "state": vdev.state,
        }
        rendered_labels = ",".join(
            f'{key}="{_prometheus_escape(value)}"' for key, value in labels.items()
        )
        healthy = int(vdev.state in _HEALTHY_VDEV_STATES)
        lines.append(f"proxmox_zfs_vdev_healthy{{{rendered_labels}}} {healthy}")

    lines.extend(
        [
            "# HELP proxmox_zfs_vdev_last_collection_timestamp_seconds Unix timestamp of the last ZFS vdev collection.",
            "# TYPE proxmox_zfs_vdev_last_collection_timestamp_seconds gauge",
            "proxmox_zfs_vdev_last_collection_timestamp_seconds "
            f"{int(collected_at.timestamp())}",
        ],
    )
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, mode=0o755, exist_ok=True)
    temporary_path = f"{path}.{os.getpid()}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _setup_logging(log_file: str, to_console: bool) -> None:
    """Configures the module logger to append to a file (and optionally stdout).

    Args:
      log_file: Path of the file to append log lines to.
      to_console: Whether to also emit lines to stdout (e.g. the systemd journal).
    """
    _LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "AUTO_ZFS %(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    _LOGGER.addHandler(file_handler)

    if to_console:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        _LOGGER.addHandler(stream_handler)


class PoolChecker:
    """Runs the health check and maintenance for every configured pool."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._hostname = socket.gethostname()
        self._mail_forward_bin = config.mail_forward_bin or self._find_mail_forward()
        self._state = self._load_state()

        # Notifications accumulated during the run and sent at the end.
        self._scrub_alerts: List[str] = []

    # ---------------------------------------------------------------------------
    # Low-level command helpers.
    # ---------------------------------------------------------------------------
    @staticmethod
    def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
        """Runs a command, capturing text output; never raises on non-zero exit."""
        return subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            check=False,
        )

    def _query(self, cmd: Sequence[str]) -> str:
        """Runs a read-only query and returns its stripped stdout."""
        return self._run(cmd).stdout.strip()

    def _mutate(self, description: str, cmd: Sequence[str]) -> None:
        """Runs a state-changing command, honoring ``--dry-run``.

        Args:
          description: Human-readable summary logged before the command runs.
          cmd: The command to execute.
        """
        if self.config.dry_run:
            _LOGGER.info("[dry-run] %s", description)
            return
        _LOGGER.info(description)
        result = self._run(cmd)
        if result.returncode != 0:
            _LOGGER.error(
                "Command failed (%s): %s",
                result.returncode,
                result.stderr.strip(),
            )

    # ---------------------------------------------------------------------------
    # Notification helpers.
    # ---------------------------------------------------------------------------
    @staticmethod
    def _find_mail_forward() -> Optional[str]:
        """Returns the path to proxmox-mail-forward, or None if not installed."""
        for path in _MAIL_FORWARD_CANDIDATES:
            if os.path.exists(path):
                return path
        return None

    def _load_state(self) -> Dict[str, str]:
        """Loads the scrub-alert de-duplication state (empty on any error)."""
        try:
            with open(self.config.state_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return {str(key): str(value) for key, value in data.items()}
        except (OSError, ValueError):
            pass
        return {}

    def _save_state(self) -> None:
        """Persists the scrub-alert de-duplication state (skipped on dry-run)."""
        if self.config.dry_run:
            return
        try:
            os.makedirs(os.path.dirname(self.config.state_file), exist_ok=True)
            with open(self.config.state_file, "w", encoding="utf-8") as handle:
                json.dump(self._state, handle, indent=2, sort_keys=True)
        except OSError as exc:
            _LOGGER.warning(
                "Could not write state file %s: %s",
                self.config.state_file,
                exc,
            )

    def _send_email(self, subject: str, body: str) -> None:
        """Sends an email through proxmox-mail-forward (honors --dry-run).

        Args:
          subject: The email subject line.
          body: The plain-text email body.
        """
        if not self.config.email_enabled:
            _LOGGER.info("Email disabled; not sending: %s", subject)
            return
        if self._mail_forward_bin is None:
            _LOGGER.warning(
                "proxmox-mail-forward not found; cannot send: %s",
                subject,
            )
            return

        message = email.message.EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self._hostname}-zfs"
        message["To"] = "root"
        message.set_content(body)

        if self.config.dry_run:
            _LOGGER.info("[dry-run] would email (subject=%r):\n%s", subject, body)
            return

        result = subprocess.run(
            [self._mail_forward_bin],
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
        else:
            _LOGGER.info("Sent email: %s", subject)

    # ---------------------------------------------------------------------------
    # Per-pool maintenance steps.
    # ---------------------------------------------------------------------------
    def _list_pools(self) -> List[str]:
        """Returns the pools to operate on (explicit selection or every pool)."""
        if self.config.pools:
            return list(self.config.pools)
        output = self._query(["zpool", "list", "-H", "-o", "name"])
        return output.splitlines() if output else []

    def _pool_property(self, prop: str, pool: str) -> str:
        """Returns a single ``zpool get`` property value for a pool."""
        return self._query(["zpool", "get", "-H", "-o", "value", prop, pool])

    def _check_autotrim(self, pool: str) -> None:
        """Enables autotrim on flash-backed pools if it is not already on."""
        autotrim = self._pool_property("autotrim", pool)
        _LOGGER.info("Autotrim for %s: %s", pool, autotrim)

        is_flash = pool in _AUTOTRIM_EXACT or any(
            token in pool for token in _AUTOTRIM_SUBSTRINGS
        )
        if is_flash and autotrim != "on":
            self._mutate(
                f"Enabling autotrim for {pool}",
                ["zpool", "set", "autotrim=on", pool],
            )

    def _check_autoexpand(self, pool: str) -> None:
        """Enables autoexpand on the pool if it is not already on."""
        autoexpand = self._pool_property("autoexpand", pool)
        if autoexpand != "on":
            self._mutate(
                f"Enabling autoexpand for {pool}",
                ["zpool", "set", "autoexpand=on", pool],
            )

    def _log_health(self, pool: str) -> None:
        """Logs pool health/size/free/capacity (ERROR when not ONLINE)."""
        health = self._pool_property("health", pool)
        size, free_space, capacity = self._list_stats(pool)
        message = "%s: Health=%s, Size=%s, Free=%s, Capacity=%s"
        args = (pool, health, size, free_space, capacity)
        if health != "ONLINE":
            _LOGGER.error(message, *args)
        else:
            _LOGGER.info(message, *args)

    def _list_stats(self, pool: str) -> List[str]:
        """Returns ``[size, free, capacity]`` from a single ``zpool list`` call."""
        output = self._query(
            ["zpool", "list", "-H", "-o", "size,free,capacity", pool],
        )
        fields = output.split("\t") if output else []
        # Pad defensively so callers can always unpack three values.
        while len(fields) < 3:
            fields.append("")
        return fields[:3]

    def _maybe_scrub(self, pool: str) -> None:
        """Starts a scrub on Saturdays of odd-numbered weeks."""
        if self.config.day_of_week == _SATURDAY and self.config.is_odd_week:
            self._mutate(f"Starting scrub for {pool}", ["zpool", "scrub", pool])

    def _log_scrub_status(self, pool: str) -> None:
        """Logs the most recent scrub status and alerts on repaired data/errors."""
        status = self._query(["zpool", "status", pool])
        scan_lines = [line.strip() for line in status.splitlines() if "scan" in line]
        if not scan_lines:
            _LOGGER.warning("No previous scrub found for %s", pool)
            return

        last_scrub = scan_lines[0]
        if "with 0 errors" in last_scrub:
            _LOGGER.info("Last scrub status for %s: %s", pool, last_scrub)
        else:
            _LOGGER.warning("Last scrub status for %s: %s", pool, last_scrub)

        # Queue an email (once per distinct scrub) if the most recently completed
        # scrub actually repaired bytes or reported errors.
        repair = self._parse_scrub_repair(last_scrub)
        if repair is None:
            return
        repaired, errors = repair
        if (repaired not in ("0", "0B")) or errors > 0:
            if self._state.get(pool) != last_scrub:
                self._state[pool] = last_scrub
                self._scrub_alerts.append(f"{pool}: {last_scrub}")

    @staticmethod
    def _parse_scrub_repair(scan_line: str) -> Optional[Tuple[str, int]]:
        """Parses a completed-scrub ``scan:`` line into ``(repaired, errors)``.

        Returns None for lines that are not a finished scrub (e.g. a scrub in
        progress or a resilver), which lack the ``repaired ... with N errors`` text.
        """
        match = re.search(r"repaired\s+(\S+)\b.*?with\s+(\d+)\s+errors", scan_line)
        if not match:
            return None
        try:
            return match.group(1), int(match.group(2))
        except ValueError:
            return None

    def _process_pool(self, pool: str) -> None:
        """Runs every maintenance step for a single pool."""
        _LOGGER.info("Checking pool: %s", pool)
        self._check_autotrim(pool)
        self._check_autoexpand(pool)
        self._log_health(pool)
        self._maybe_scrub(pool)
        self._log_scrub_status(pool)

    def _publish_vdev_metrics(self, pools: Sequence[str]) -> None:
        """Collect current topology state without invoking maintenance."""
        vdevs: List[VdevHealth] = []
        for pool in pools:
            result = self._run(["zpool", "status", "-p", "-P", pool])
            if result.returncode != 0:
                raise RuntimeError(
                    f"zpool status failed for {pool}: {result.stderr.strip()}",
                )
            vdevs.extend(parse_vdev_health(pool, result.stdout))
        if self.config.dry_run:
            _LOGGER.info(
                "[dry-run] would publish %s ZFS vdev health metrics",
                len(vdevs),
            )
            return
        write_vdev_metrics(self.config.prometheus_file, vdevs, self.config.now)
        _LOGGER.info("Published health for %s ZFS vdevs", len(vdevs))

    # ---------------------------------------------------------------------------
    # Notifications.
    # ---------------------------------------------------------------------------
    def _send_notifications(self) -> None:
        """Emails a scrub alert when repaired data or errors are detected."""
        if self._scrub_alerts:
            body = (
                f"A ZFS scrub repaired data or reported errors on {self._hostname}:"
                "\n\n" + "\n".join(self._scrub_alerts) + "\n"
            )
            self._send_email(
                f"[ZFS] scrub repaired data/errors on {self._hostname}",
                body,
            )

    def run(self) -> None:
        """Processes every configured pool and sends notifications."""
        _LOGGER.info("Starting ZFS pool check")
        pools = self._list_pools()
        if self.config.metrics_only:
            self._publish_vdev_metrics(pools)
            _LOGGER.info("Finished ZFS vdev metrics collection")
            return
        for pool in pools:
            self._process_pool(pool)
        self._send_notifications()
        self._save_state()
        _LOGGER.info("Finished ZFS pool check")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Program entry point."""
    args = _parse_args(argv)
    _setup_logging(args.log_file, args.console)
    config = Config(
        log_file=args.log_file,
        console=args.console,
        dry_run=args.dry_run,
        pools=args.pools,
        email_enabled=args.email_enabled,
        mail_forward_bin=args.mail_forward_bin,
        state_file=args.state_file,
        prometheus_file=args.prometheus_file,
        metrics_only=args.metrics_only,
        now=datetime.datetime.now(),
    )
    PoolChecker(config).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
