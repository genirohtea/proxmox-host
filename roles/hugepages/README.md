# Hugepages

Reserves a configurable amount of memory as 2 MiB hugepages through the kernel command line. The role supports the GRUB and systemd-boot configurations used by Proxmox and preserves unrelated kernel parameters.

The reservation is applied the next time the host boots.

## Variables

```yaml
bootloader_type: systemd
hugepages_2mb_gib: 16
```

`hugepages_2mb_gib` defaults to `0`, which leaves the host unchanged. Each GiB requires 512 pages, so 16 GiB configures `hugepages=8192`.
