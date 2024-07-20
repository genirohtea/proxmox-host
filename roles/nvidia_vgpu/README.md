Role Name
=========

Guide from: <https://gitlab.com/polloloco/vgpu-proxmox>

Requirements
------------

None

Role Variables
--------------

- `install_nvidia_vgpu`: Utilize manual way of installing vgpu
- `allow_reboot`: Allow the host to reboot

Dependencies
------------

None

Example Playbook
----------------

```yaml
- hosts: servers
  roles:
    - { role: nvidia_vgpu, allow_reboot: true }
```

License
-------

BSD

Author Information
------------------

This role was created by genirohtea.
