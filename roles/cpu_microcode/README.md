CPU Microcode
=========

This role adds non-free repositories and installs CPU microcode packages for Intel or AMD processors.

Requirements
------------

Requires a Proxmox Host/Filesystem

Role Variables
--------------

- `amd_microcode_package`: The name of the AMD microcode package coming from Debian APT repositories.
- `intel_microcode_package`: The name of the Intel microcode package coming from Debian APT repositories.

Dependencies
------------

No dependencies

Example Playbook
----------------

Here is an example of how to use this role:

    - hosts: servers
      roles:
         - cpu_microcode

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2023 by genirohtea.
