# vfio_rescan_hook

Installs a PVE **`pre-start` hookscript** that removes and re-scans passed-through PCI devices immediately before a guest starts, so they come back in a state their guest drivers can actually use.

## The problem it solves

On `watt`, stopping and starting the NAS guest leaves the LSI SAS2008 and the Intel Arc A310 in a state neither driver recovers from. The guest boots with both devices listed in `lspci` and both useless:

```text
mpt2sas_cm0: Invalid host diagnostic register value        # zero of eight drives
i915 0000:03:00.0: [drm] *ERROR* LMEM not initialized by firmware   # no render node
```

Two ordinary `tofu apply` runs — each restarting the VM — were enough to trigger it.

**The hardware is fine.** After a remove/rescan the Arc bound to the host's own `i915` and initialised completely: GuC 70.53.0 loaded, HuC authenticated, a working `renderD128` on the host. The devices only
need re-enumerating, and nothing in the normal start path does that.

The previously documented recovery was a cold power cycle of the node — a full outage of every guest on it. This is the same recovery in about three seconds, and it is automatic.

## Why `drivers_autoprobe` is disabled around the rescan

This is the part that is easy to get wrong, and it was got wrong once by hand before this role existed.

`/etc/modprobe.d/vfio.conf` carries `softdep i915 pre: vfio-pci` and friends. **`softdep` only orders module loading.** It has no effect at rescan time, and with `i915` and `snd_hda_intel` already resident the
bus rescan handed them the GPU and its audio function within seconds — observed, not theorised.

Setting `driver_override` first does not help either: `remove` destroys the device object, and the override with it.

So the script sets `/sys/bus/pci/drivers_autoprobe` to `0` for the duration. The devices reappear **unbound**, `driver_override` is applied to the fresh objects, and only then are they probed. There is no
window for a native driver to win. An `EXIT` trap restores autoprobe — leaving it off would stop every later hotplugged device from binding a driver, long after the script exited and with nothing pointing back
here.

## Variables

| Variable                          | Default                | Notes                                                                                                                |
| --------------------------------- | ---------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `vfio_rescan_hook_pci_ids`        | `[]`                   | `vendor:device` IDs as `lspci -nn` prints them. **Not** PCI addresses — asserted. Empty means the role does nothing. |
| `vfio_rescan_hook_fail_closed`    | `true`                 | Refuse the start if a device does not come back on `vfio-pci`.                                                       |
| `vfio_rescan_hook_settle_seconds` | `2`                    | Wait after the rescan before re-probing.                                                                             |
| `vfio_rescan_hook_snippets_dir`   | `/var/lib/vz/snippets` | Must be a storage with the `snippets` content type.                                                                  |
| `vfio_rescan_hook_name`           | `vfio-rescan`          | Filename, and the `local:snippets/<name>` reference.                                                                 |

### Why IDs and not addresses

Addresses are neither stable nor guessable. The same HBA is `85:00.0` on the host and `02:00.0` inside the guest — a confusion that cost a debugging step during the original investigation. The script resolves
IDs to current addresses on every run, so re-seating a card changes nothing.

### Why a separate list from `vfio_bind_extra_pci_ids`

Not every passed-through device needs this. On `watt` both Optane drives survive a guest restart untouched, while the SAS2008 and the Arc do not. PCI-removing a live NVMe device that has no problem is added
risk for no benefit, so the blast radius is set to match the demonstrated fault.

Example for `watt`:

```yaml
vfio_rescan_hook_pci_ids:
  - "1000:0072" # LSI SAS2008
  - "8086:56a6" # Arc A310
  - "8086:4f92" # Arc A310 audio function
```

## Attaching it to a guest

The script is host configuration and lives here. The guest that *references* it is declared in `klaus-homelab`:

```hcl
hook_script_file_id = "local:snippets/vfio-rescan"
```

> ⚠ **Cross-repo ordering.** This role must run **before** any `tofu apply` that sets `hook_script_file_id`, or the guest refuses to start with `hookscript ... does not exist`. That only bites on a rebuild —
> precisely when it is least likely to be remembered.

## Fail-closed

If a device does not return on `vfio-pci`, the start is refused. The alternative is a guest that boots with a device it cannot use and reports it hours later as a driver or hardware fault —
`LMEM not initialized by firmware`, or an HBA with no drives behind it. Neither points back here. A refused start names the actual problem.

Set `vfio_rescan_hook_fail_closed: false` only if you would rather have a degraded guest than none.

## Firmware

Not a firmware bug, at least not one that is fixable by updating. The card on `watt` already runs LSI IT-mode **P20.00.07.00** (`FWVersion(20.00.07.00)`, BIOS `07.02.04.00`), which is the version usually
recommended as the fix for SAS2008 reset behaviour. It is on that version and still misbehaves.
