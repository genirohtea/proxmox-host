GPU Passthrough
=========

Enables full GPU passthrough to a single VM on a Proxmox host

Requirements
------------

- Proxmox VE
- AMD or Nvidia GPU

Role Variables
--------------

- `allow_reboot`: Boolean to allow the system to reboot after making changes. Default is `false`.
- `graphics_card`: The type of graphics card, either `AMD` or `NVIDIA`.

Dependencies
------------

None

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

```yaml
- hosts: servers
  roles:
    - { role: gpu_passthrough, allow_reboot: true, graphics_card: 'NVIDIA' }
```

License
-------

BSD

Author Information
------------------

This role was created by genirohtea.
