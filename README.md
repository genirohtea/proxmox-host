# Proxmox Host

This repo is designed to initialize a proxmox host.

## Proxmox ISO Installation Tips

### `Trying to detect country` bug

- <https://forum.proxmox.com/threads/proxmox-installation-trying-to-detect-country.134301/page-3>
- Solve by `Alt + F3` -> `ps aux | grep traceroute` -> `kill -9 <pid>`

## GPU Passthrough Role

This repository includes an Ansible role `gpu_passthrough` to enable full GPU passthrough to a single VM on a Proxmox host.

### Requirements

- Proxmox VE
- AMD or Nvidia GPU

### Role Variables

- `allow_reboot`: Boolean to allow the system to reboot after making changes. Default is `false`.
- `graphics_card`: The type of graphics card, either `AMD` or `NVIDIA`.

### Dependencies

None

### Example Playbook

Including an example of how to use the `gpu_passthrough` role (for instance, with variables passed in as parameters):

```yaml
- hosts: servers
  roles:
     - { role: gpu_passthrough, allow_reboot: true, graphics_card: 'NVIDIA' }
```

### License

BSD

### Author Information

This role was created by genirohtea.
