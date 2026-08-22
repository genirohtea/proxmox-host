# Disk Health

Installs a periodic physical-disk health report for Proxmox. The report is logged locally and emailed through `proxmox-mail-forward`, so delivery follows the notification target configured in Proxmox.

Every physical disk reported by `lsblk` is checked, excluding loop, zram, device-mapper, and ZFS zvol devices. Reports include:

- device path, model, and size;
- overall SMART health and latest self-test result;
- SATA temperature, power-on hours, wear, reallocated sectors, pending sectors, offline-uncorrectable sectors, and UDMA CRC errors;
- NVMe temperature, available spare, spare threshold, percentage used, data units written, power-on hours, unsafe shutdowns, and media/data-integrity errors.

A device that exposes no SMART data at all -- a USB flash drive behind a bridge with no SAT passthrough, for example -- is still listed, with a health of `SMART not available`, but does not raise a warning and
is skipped for self-tests. Only a disk that reports a health verdict and fails it, or that trips a metric threshold, counts toward the warning total that sets the `OK`/`WARNING` subject line.

Prometheus SMART collection belongs to the `telemetry_agent` role's upstream `smartctl_exporter`. This role remains responsible for the human-readable report and scheduled self-tests, avoiding a second
implementation of SMART metric parsing.

On Sundays, the role starts alternating short and long SMART self-tests. Odd weeks use short tests and even weeks use long tests, preserving the schedule previously owned by the ZFS role.

## Role variables

- `disk_health_on_calendar`: systemd calendar expression. Default: `*-*-* 04:00:00`.
- `disk_health_email_recipient`: report recipient. Default: `root`.
- `disk_health_enable_email`: send each report by email. Default: `true`.
- `disk_health_enable_self_tests`: schedule Sunday SMART tests. Default: `true`.
- `disk_health_log_file`: report log. Default: `/var/log/disk_health.log`.

## Example

```yaml
- hosts: proxmox
  roles:
    - role: disk_health
      disk_health_on_calendar: "*-*-* 05:30:00"
```

## License

BSD-3-Clause
