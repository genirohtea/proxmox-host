# Role Name

Sets up gmail notifications for Proxmox as described in [naturalborncoder's Proxmox Gmail guide](https://www.naturalborncoder.com/linux/2023/05/19/setting-up-email-notifications-in-proxmox-using-gmail/) and
[Techno Tim's Proxmox alerts guide](https://technotim.live/posts/proxmox-alerts/).

## Requirements

- Requires setup of a google account with 2-FA and an app password.
- Requires setup of a bitwarden secrets vault.

## Role Variables

None

## Dependencies

None

## Example Playbook

```yaml
- hosts: servers
  roles:
    - gmail_notifications
```

## License

BSD-3-Clause

## Author Information

This role was created in 2023 by geniroh.
