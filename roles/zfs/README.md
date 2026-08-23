# ZFS

A role that monitors ZFS pool health, vdev health, capacity, and scrub results on the Proxmox host. It also enables autoexpand, enables autotrim for pools identified as flash-backed, schedules scrubs, and
emails alerts when a completed scrub repairs data or reports errors.

Alloy's embedded node exporter reports pool state through `node_zfs_zpool_state`. A separate read-only timer publishes per-vdev state as `proxmox_zfs_vdev_healthy` every five minutes. It reuses the existing
Python checker in `--metrics-only` mode, which cannot change pool properties or start a scrub.

Physical-disk SMART health and temperature monitoring is provided by the `telemetry_agent` role's upstream `smartctl_exporter`. The `disk_health` role retains only email reports and scheduled self-tests.

## Requirements

- `zfs_health_prometheus_file`: node-exporter textfile destination. Default: `/var/lib/node_exporter/textfile_collector/proxmox_zfs_vdev_health.prom`.
- `zfs_health_metrics_interval`: per-vdev refresh interval. Default: `5m`.

Verify the read-only collector directly:

```bash
systemctl status zfs_health_metrics.timer
systemctl start zfs_health_metrics.service
cat /var/lib/node_exporter/textfile_collector/proxmox_zfs_vdev_health.prom
```

## Role Variables

None.

## Dependencies

This role does not have any dependencies on other Galaxy roles.

## Example Playbook

Here is an example of how to use this role with variables passed in as parameters:

```yaml
- hosts: servers
  roles:
    - { role: zfs }
```

## License

BSD-3-Clause

## Author Information

This role was created in 2023 by geniroh.
