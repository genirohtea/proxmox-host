# CPU Scaling Governor

Configures the Linux CPU frequency scaling governor for every CPU and persists the selection across reboots with a systemd oneshot service. On AMD CPUs that support CPPC it also enables the `amd_pstate` scaling
driver via the kernel command line.

The role validates the requested governor against the values exposed by the kernel before changing anything. It fails with a descriptive message when CPU frequency scaling is unavailable, such as in some
virtual machines.

## The governor depends on the scaling driver

The same governor name means different things under different drivers, which makes `powersave` a trap:

| Driver                                 | `powersave` behaviour                                          | `schedutil` available? |
| -------------------------------------- | -------------------------------------------------------------- | ---------------------- |
| `acpi-cpufreq`                         | **Static.** Pins every core to `cpuinfo_min_freq` permanently. | Yes                    |
| `intel_pstate`                         | Dynamic, ramps on demand.                                      | No                     |
| `amd_pstate` guided/passive            | Dynamic, ramps on demand.                                      | Yes                    |
| `amd_pstate` active (`amd-pstate-epp`) | Dynamic, firmware-driven via EPP.                              | No                     |

The default is `amd_pstate=active` with the `powersave` governor: firmware handles frequency selection via the energy performance preference, which is the mode AMD tunes for. Check
`/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver` before choosing anything else -- the governor name alone does not tell you what will happen.

### The acpi-cpufreq guard

Enabling `amd_pstate` takes a reboot, so there is a window where the parameter is on the kernel command line but `acpi-cpufreq` is still the running driver. Applying `powersave` in that window would pin every
core to its minimum frequency. Two guards prevent it:

- The role skips the live governor apply when the requested governor is `powersave` and the running driver is `acpi-cpufreq`, reporting that the change is deferred to the next boot.
- `/usr/local/sbin/set-cpu-scaling-governor`, which runs at every boot, substitutes the first available dynamic governor (`schedutil`, `ondemand`, then `performance`) and logs a warning if it is ever asked for
  `powersave` under `acpi-cpufreq`. This is the backstop for `amd_pstate` failing to load after a kernel or firmware change.

## amd_pstate

Without `amd_pstate`, an AMD host falls back to `acpi-cpufreq`, which only knows the coarse ACPI P-states and cannot reach the CPU's full boost range. The role adds `amd_pstate=<mode>` to `/etc/kernel/cmdline`
(systemd-boot) or `/etc/default/grub` (GRUB) when it detects an AMD CPU advertising the `cppc` flag. It skips the edit, with a message, on Intel CPUs and on AMD CPUs without CPPC.

The edit is additive: existing values are updated in place and a missing parameter is appended. The kernel command line is shared with the `hugepages` role, so neither role may rewrite the line wholesale.

**The parameter only takes effect after a reboot.** This role does not reboot; schedule one separately. Until then the host keeps its current driver, so the requested governor must be valid under both the
current and the intended driver.

## Role variables

- `scaling_governor`: Governor to apply. Must be supported by the host's running scaling driver. Defaults to `powersave`.
- `amd_pstate_epp`: Energy performance preference, defaults to `balance_power`. Under `amd_pstate=active` the governor selects the range and the EPP selects where in it the firmware sits, so `powersave` alone
  does not save power -- the driver's own EPP default is `performance`. Set to an empty string to leave the firmware default alone. Silently skipped under drivers that do not expose it.
- `amd_pstate_enabled`: Whether to enable `amd_pstate` on supported AMD CPUs. Defaults to `true`.
- `amd_pstate_mode`: One of `guided`, `passive`, or `active`. Defaults to `active`. Selecting `active` restricts `scaling_governor` to `performance` or `powersave`, and the role asserts this rather than failing
  at apply time. Choose `guided` or `passive` if you want `schedutil`.
- `bootloader_type`: `grub` or `systemd`. Set per host in the inventory. The kernel command line edit is skipped when this is unknown.

## Example

```yaml
- hosts: proxmox
  roles:
    - role: scaling_governor
      amd_pstate_mode: active
      scaling_governor: powersave
```

Scheduler-driven scaling instead, which needs a mode that keeps the generic governor list:

```yaml
- hosts: proxmox
  roles:
    - role: scaling_governor
      amd_pstate_mode: guided
      scaling_governor: schedutil # `active` mode has no `schedutil`
```

## License

BSD-3-Clause
