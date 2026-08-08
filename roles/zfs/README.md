# ZFS

A role that monitors ZFS pool health, capacity, and scrub results on the Proxmox host. It also enables autoexpand, enables autotrim for pools identified as flash-backed, schedules scrubs, and emails alerts when
a completed scrub repairs data or reports errors.

Physical-disk SMART and NVMe monitoring is provided by the `disk_health` role.

## Requirements

None.

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
