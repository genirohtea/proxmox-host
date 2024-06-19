Terraform User Role
===================

Configures Proxmox for Terraform by creating a user and assigning necessary privileges.

Requirements
------------

- Requires Proxmox VE installed and running.
- Requires appropriate privileges to create users and roles in Proxmox.

Role Variables
--------------

Below are the variables that can be configured for this role:

`proxmox_privileges`: The privileges to assign to the TerraformProv role. Default is a comprehensive list of VM and system privileges.

Dependencies
------------

This role does not have any dependencies on other Galaxy roles.

Example Playbook
----------------

Here is an example of how to use this role with variables passed in as parameters:

```yaml
- hosts: servers
  roles:
    - { role: terraform_user, proxmox_privileges: "VM.Allocate VM.Audit" }
```

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2023 by genirohtea.
