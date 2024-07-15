Admin User
=========

Adds an administrative user to a Proxmox host

Requirements
------------

None


Role Variables
--------------

- `admin_username`: The name of the admin user to create
- `admin_password`: The password for the admin user

Dependencies
------------

No dependencies

Example Playbook
----------------

Here is an example of how to use this role:

```yaml
- hosts: servers
  roles:
    - admin_user
```

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2024 by genirohtea.
