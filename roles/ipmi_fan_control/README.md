# IPMI Fan Control

A role to control fan speed on servers using IPMI.

Disk access in this role is limited to temperatures, standby state, and the thermal inputs needed for fan control. SMART health, lifetime, wear, and error indicators are owned by the `disk_health` role.

The controller atomically publishes each available IPMI fan's RPM and the CPU and peripheral zone duty ratios to `/var/lib/node_exporter/textfile_collector/proxmox_ipmi_fans.prom`. Alloy's embedded
node_exporter forwards these as `proxmox_ipmi_fan_speed_rpm` and `proxmox_ipmi_fan_duty_ratio`.

## Requirements

- IPMI interface on the server
- ipmitool installed on the server

## Role Variables

Below are the variables that can be configured for this role:

`ipmi_fan_control`: Whether to enable IPMI fan control. Default is `false`.

## Dependencies

This role does not have any dependencies on other Galaxy roles.

## Example Playbook

Here is an example of how to use this role with variables passed in as parameters:

```yaml
- hosts: servers
  roles:
    - { role: ipmi_fan_control, ipmi_fan_control: true }
```

## License

BSD-3-Clause

## Author Information

This role was created in 2023 by genirohtea.
