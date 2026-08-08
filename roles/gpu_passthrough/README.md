# GPU Passthrough

Enables full GPU passthrough to a single VM on a Proxmox host

## Requirements

- Proxmox VE (GRUB or systemd-boot; the bootloader is auto-detected)
- An AMD, NVIDIA, or Intel Arc (Alchemist/DG2 discrete, e.g. Arc A310) GPU

## Role Variables

- `allow_reboot`: Boolean to allow the system to reboot after making changes. Default is `false`.
- `graphics_card`: The type of graphics card, one of `AMD`, `NVIDIA`, or `Intel`.

Per-vendor behaviour:

- **AMD** — builds the `gnif/vendor-reset` DKMS module and installs a systemd service to set the GPU reset method, then binds vfio-pci.

- **NVIDIA** — sets `kvm ignore_msrs=1` and binds vfio-pci. `/etc/modprobe.d/vfio.conf` is **not** written by this role. Each vendor path discovers its card and sets `vfio_bind_gpu_pci_ids` /
  `vfio_bind_gpu_softdeps`; the [`vfio_bind`](../vfio_bind/README.md) role is the file's single author and merges those with any non-GPU devices declared for the host. See that role's README for why a second
  writer is a latent, reboot-deferred failure.

- **Intel** — binds both PCI functions of the Arc card (VGA + HDMI/DP audio) to vfio-pci, with `softdep`s so `i915`/`xe`/`snd_hda_intel` never claim it. No DKMS or reset quirk (recent PVE 6.14/7.0 kernels reset
  Arc via FLR correctly). Note: this is **full** passthrough of the whole card to one VM — the consumer Arc A-series has no working SR-IOV, so the `intel_graphics` (vGPU/SR-IOV) role does not apply to it.

## Dependencies

Uses the in-repo `iommu_enable` and `vfio_driver_fix` roles. No Galaxy dependencies.

## Example Playbook

Including an example of how to use your role (for instance, with variables passed in as parameters) is always nice for users too:

```yaml
- hosts: servers
  roles:
    - { role: gpu_passthrough, allow_reboot: true, graphics_card: 'NVIDIA' }
    - { role: gpu_passthrough, allow_reboot: true, graphics_card: 'Intel' }
```

## License

BSD

## Author Information

This role was created by genirohtea.
