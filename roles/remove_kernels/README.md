Remove Kernels
=========

This role removes all Proxmox VE kernels except for the currently running one.

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
    - remove_kernels
```

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2023 by genirohtea.
