Disable Subscription Nag
=========

This role installs a fake subscription package to disable the Proxmox VE subscription nag.

Requirements
------------

Requires a Proxmox Host/Filesystem

Role Variables
--------------

There are no variables required for this role.

Dependencies
------------

No dependencies

Example Playbook
----------------

Here is an example of how to use this role:

```yaml
- hosts: servers
  roles:
    - disable_subscription_nag
```

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2023 by genirohtea.
