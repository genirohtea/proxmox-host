Kernel Pinning
==============

This role pins the Proxmox kernel to a specified version to ensure stability and compatibility.

Requirements
------------

Any pre-requisites that may not be covered by Ansible itself or the role should be mentioned here. For instance, if the role uses the EC2 module, it may be a good idea to mention in this section that the boto package is required.

Role Variables
--------------

- `allow_reboot`: Boolean to allow the system to reboot after making changes. Default is `false`.
- `pinned_kernel_version`: The version of the kernel to pin.

Dependencies
------------

None

Example Playbook
----------------

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

```yaml
- hosts: servers
  roles:
    - { role: kernel_pinning, allow_reboot: true, pinned_kernel_version: '5.4.78-2-pve' }
```

License
-------

BSD-3-Clause

Author Information
------------------

An optional section for the role authors to include contact information, or a website (HTML is not allowed).
