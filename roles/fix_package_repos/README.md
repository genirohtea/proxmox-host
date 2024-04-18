Fix Package Repos
=========

This role configures Proxmox VE package repositories to use the no-subscription sources and ensures Debian default sources are correct.

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

    - hosts: servers
      roles:
         - fix_package_repos

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2023 by genirohtea.
