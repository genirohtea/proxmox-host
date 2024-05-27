IPMI Fan Control
=========

A role to control fan speed on servers using IPMI.

Requirements
------------

- IPMI interface on the server
- ipmitool installed on the server

Role Variables
--------------

Below are the variables that can be configured for this role:

`ipmi_fan_control`: Whether to enable IPMI fan control. Default is `false`.

Dependencies
------------

This role does not have any dependencies on other Galaxy roles.

Example Playbook
----------------

Here is an example of how to use this role with variables passed in as parameters:

```yaml
- hosts: servers
  roles:
    - { role: ipmi_fan_control, ipmi_fan_control: true }
```

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2023 by genirohtea.
