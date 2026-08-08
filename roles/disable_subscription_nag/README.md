# Disable Subscription Nag

This role patches the Proxmox desktop and mobile web interfaces to disable the subscription nag. An APT `DPkg::Post-Invoke` hook reapplies the patch after package upgrades replace the affected web-interface
files.

## Requirements

Requires a Proxmox Host/Filesystem

## Role Variables

There are no variables required for this role.

## Dependencies

No dependencies

## Example Playbook

Here is an example of how to use this role:

```yaml
- hosts: servers
  roles:
    - disable_subscription_nag
```

## License

BSD-3-Clause

## Author Information

This role was created in 2023 by genirohtea.
