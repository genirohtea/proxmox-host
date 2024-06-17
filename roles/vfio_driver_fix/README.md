VFIO Driver Fix
===============

This role fixes VFIO driver loading to allow GPU passthrough on a Proxmox host.

Requirements
------------

Any pre-requisites that may not be covered by Ansible itself or the role should be mentioned here. For instance, if the role uses the EC2 module, it may be a good idea to mention in this section that the boto package is required.

Role Variables
--------------

- `allow_reboot`: Boolean to allow the system to reboot after making changes. Default is `false`.

Dependencies
------------

None

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

```yaml
- hosts: servers
  roles:
    - { role: vfio_driver_fix, allow_reboot: true }
```

License
-------

BSD-3-Clause

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
