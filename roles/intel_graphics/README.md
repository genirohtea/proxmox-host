# Intel Graphics SR-IOV for Proxmox

Enables Intel GPU SR-IOV (Virtual Functions) on a Proxmox host. Two hardware families are supported, selected per-host with `intel_gpu_driver`:

<!-- markdownlint-disable MD013 -->

| `intel_gpu_driver` | Hardware                                      | SR-IOV source                                                                                                             | Kernel                                         |
| ------------------ | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `i915`             | Intel Gen12 iGPUs (Alder Lake / Alder Lake-N) | out-of-tree [`strongtz/i915-sriov-dkms`](https://github.com/strongtz/i915-sriov-dkms) module; in-tree `xe` is blacklisted | matched to the module release (curie pins 7.0) |
| `xe`               | Intel Arc Battlemage (B-series) dGPUs         | **native** in the `xe` driver — no DKMS                                                                                   | 7.0+ (opt-in PVE 9.1, default 9.2)             |

<!-- markdownlint-enable MD013 -->

Originally based on this [guide](https://www.derekseaman.com/2023/11/proxmox-ve-8-1-windows-11-vgpu-vt-d-passthrough-with-intel-alder-lake.html).

## Requirements

- Intel VT-d enabled in the BIOS
- Proxmox VE 9 (Debian trixie) for the values shipped here
- **GRUB** bootloader (systemd-boot is not yet supported by this role)
- Secure Boot enrolls the DKMS MOK key automatically on the `i915` path when enabled (e.g. ZFS-on-GRUB hosts); a no-op when Secure Boot is disabled

## How it works

`tasks/main.yml` gates on `install_intel_vtd and allow_reboot`, pins the driver-appropriate kernel (via the `kernel_pinning` role), composes the driver-specific kernel command line, then dispatches:

- **`tasks/i915.yml`** — clones the pinned `i915-sriov-dkms` release, reads `PACKAGE_VERSION` / `BUILD_EXCLUSIVE_KERNEL` from its `dkms.conf`, and `dkms add` + `dkms install`s the patched module for the pinned
  kernel. The kernel cmdline gets `i915.enable_guc=3 i915.max_vfs=<n> module_blacklist=xe`.
- **`tasks/xe.yml`** — no build; just writes `/etc/modprobe.d/xe.conf` (`xe_sriov_auto_provisioning`) and rebuilds the initramfs.
- **`tasks/pci_configuration.yml`** — persists `sriov_numvfs` on the PF via `sysfsutils`, reboots, then asserts the VFs and driver are live.

## Role Variables

Common:

- `intel_gpu_driver`: `i915` or `xe`. Default `i915`.
- `pcie_bus_number`: PF PCI address. Default `00:02.0` (Alder Lake-N iGPU).
- `intel_gpu_num_vfs`: number of VFs to expose. Default `7`.
- `install_intel_vtd` / `allow_reboot`: gate the role. Default `false`.
- `has_google_coral_pc`: adds Coral-specific cmdline flags. Default `false`.
- `grub_file`, `sysfs_conf_file`: file paths.

`i915` path:

- `i915_required_kernel_version`: exact PVE kernel to pin. Default `7.0.14-3-pve` (the 7.0 kernel curie's PVE 9 install shipped). Must be a real point-release available in apt and within the module release's
  `BUILD_EXCLUSIVE_KERNEL`.
- `i915_sriov_dkms_git_version`: module release tag. Default `2026.05.06` (supports kernels 6.17–7.0; required for the 7.0 kernel). Use `2026.03.05.1` instead only if pinning a 6.12–6.19 kernel.

`xe` path:

- `xe_required_kernel_version`: exact PVE 7.0 kernel to pin. **Must be set.**
- `xe_sriov_auto_provisioning`: `false` (default) writes `...=0`, disabling the driver's automatic VRAM split so the PF keeps VRAM.

> All tunables live in `defaults/main.yml` (not `vars/main.yml`) so inventory host_vars can override them.

## Example Playbook

```yaml
- hosts: servers
  roles:
    - role: intel_graphics
      install_intel_vtd: true
      allow_reboot: true
```

With per-host inventory (`intel_gpu_driver`, `pcie_bus_number`, and the exact pinned kernel) supplying the hardware specifics.

## Dependencies

Uses the in-repo `kernel_pinning` role. No Galaxy dependencies.

## License

BSD-3-Clause

## Author Information

This role was created in 2023 by genirohtea.
