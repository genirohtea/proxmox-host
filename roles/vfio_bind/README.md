# vfio_bind

Owns `/etc/modprobe.d/vfio.conf` outright and binds PCI devices to `vfio-pci`.

## Why this role exists

`vfio.conf` must have exactly **one** author.

Before this role, each vendor path in `gpu_passthrough` wrote the file with `lineinfile`, matching on a literal `line:` with no `regexp:`. Adding a second writer — say, to claim an HBA and a pair of NVMe drives
alongside the GPU — does not replace the existing `options vfio-pci ids=` line, because the two lines differ. It **appends a competing one**, and modprobe then has two directives for the same parameter.

The ordering is worse than the ambiguity: re-running the playbook reasserts the GPU-only line, and at the next boot the other devices bind to their native drivers on the host instead of `vfio-pci`. Any VM
holding them as `hostpci` fails to start, or starts and contends with the host for the same disks. Nothing is visibly wrong until that reboot.

Rendering the whole file from a template makes that failure impossible by construction instead of by convention. `lineinfile` cannot express "this file contains exactly these lines", which is the property
actually wanted here.

## Requirements

Proxmox VE with IOMMU enabled (see the `iommu_enable` role).

## Role Variables

| Variable                           | Default                     | Purpose                                                         |
| ---------------------------------- | --------------------------- | --------------------------------------------------------------- |
| `vfio_bind_extra_pci_ids`          | `[]`                        | Non-GPU `vendor:device` IDs to claim, set per host in inventory |
| `vfio_bind_extra_softdeps`         | `[]`                        | Modules that must not claim a device before `vfio-pci`          |
| `vfio_bind_gpu_pci_ids`            | `[]`                        | Contributed by `gpu_passthrough`; not normally set by hand      |
| `vfio_bind_gpu_softdeps`           | `[]`                        | Contributed by `gpu_passthrough`                                |
| `vfio_bind_conf_path`              | `/etc/modprobe.d/vfio.conf` | The file this role owns                                         |
| `vfio_bind_assert_iommu_isolation` | `true`                      | Fail if any claimed device shares its IOMMU group               |
| `vfio_bind_update_initramfs`       | `true`                      | Rebuild initramfs when the file changes                         |

IDs are `vendor:device` as printed in brackets by `lspci -nn` (e.g. `1000:0072`). A PCI **path** such as `85:00.0` is rejected with an explicit message — it would otherwise be written happily and bind nothing.

## Contributing devices

GPUs are discovered automatically. `gpu_passthrough` runs `lspci` for the configured `graphics_card` and sets `vfio_bind_gpu_pci_ids` / `vfio_bind_gpu_softdeps`, then includes this role before its reboot.

Everything else is declared per host in `inventory/hosts.yaml`:

```yaml
watt.internal.klaus.geniroh.com:
  graphics_card: Intel # -> gpu_passthrough discovers 8086:56a6, 8086:4f92
  # LSI SAS2008 HBA and the Intel Optane pair, both passed through to the NAS VM.
  # The nvme softdep delays binding for all NVMe devices, but vfio-pci claims
  # only the matching IDs and the remaining drives bind to nvme normally.
  vfio_bind_extra_pci_ids:
    - "1000:0072"
    - "8086:2700"
  vfio_bind_extra_softdeps:
    - mpt3sas
    - nvme
```

## IOMMU isolation

Before writing anything, the role resolves every configured ID to its PCI address (note one ID can match several devices — the two Intel Optane 900P drives on `watt` share `8086:2700`) and checks that each
address sits alone in its IOMMU group. A shared group means passing one device through drags its group-mates in with it, which is exactly what an ACS override hides.

The check fails loudly rather than working around it. Groups are re-verified on every run rather than trusted from a survey, because a firmware or kernel update can merge them. Set
`vfio_bind_assert_iommu_isolation: false` only after deciding the sharing is acceptable.

## Verifying

The regression test for the single-writer property is to re-run and confirm the file does not change. Use the `vfio_bind` tag: it pulls in the GPU discovery tasks it depends on, but **not** `gpu_passthrough`'s
unconditional reboot, so the check is free on an already-converged host.

```sh
ansible-playbook main.yml --limit <host> --tags vfio_bind
# expect changed=0, and an unchanged md5 for /etc/modprobe.d/vfio.conf
```

`changed=1` here is the alarm: it means something else rewrote the file between runs, which is the exact failure this role exists to prevent.

The tag deliberately includes discovery. Running `vfio_bind` *without* it would render an empty GPU list and silently drop the card from the binding — so the role also asserts that a host with `graphics_card`
set has discovered at least one GPU ID, and fails rather than writing a GPU-less file.

After a reboot, `lspci -nnk` should show `Kernel driver in use: vfio-pci` for every contributed device.

## License

BSD

## Author Information

This role was created by genirohtea.
