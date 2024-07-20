Download ISOs
=========

Downloads common VM ISOs to the proxmox host.

Requirements
------------

None.

Role Variables
--------------

- `iso_folder`: The ISO folder that proxmox looks for ISO's in
- `iso_urls`: A list of ISO template urls and the versions

Dependencies
------------

None

Example Playbook
----------------

```yaml
- hosts: servers
  roles:
    - download_isos
```

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2023 by genirohtea.
