Intel Graphics VT-d for Proxmox
=========

Installs Intel GPU passthrough based on this [guide](https://www.derekseaman.com/2023/11/proxmox-ve-8-1-windows-11-vgpu-vt-d-passthrough-with-intel-alder-lake.html)

Requirements
------------

- Requires Intel VT-d enabled in the BIOS
- Requires at least Proxmox 8.0
- Secure Boot enabled if using a ZFS boot drive (based on GRUB requirement as listed [here](https://pve.proxmox.com/wiki/Host_Bootloader) )

Role Variables
--------------

Below are the variables that can be configured for this role:

`grub_file`: The path to the GRUB configuration file. Default is `/etc/default/grub`.
`has_google_coral_pc`: Whether the system has a Google Coral PC. Default is `false`.
`sysfs_conf_file`: The path to the sysfs configuration file. Default is `/etc/sysfs.conf`.
`pcie_bus_number`: The PCIe bus number for the graphics card. Default is `00:02.0`.
`install_intel_vtd`: Whether to install Intel VT-d support. Default is `false`.
`i915_sriov_dkms_git_sha`: The Git SHA for the i915 SR-IOV DKMS module. Default is `3d7a1b3fa4706d8da316d8e794d54db96856a2b9`.

Dependencies
------------

This role does not have any dependencies on other Galaxy roles.

Example Playbook
----------------

Here is an example of how to use this role with variables passed in as parameters:

```yaml
- hosts: servers
  roles:
    - { role: intel_graphics, install_intel_vtd: true }
```

License
-------

BSD-3-Clause

Author Information
------------------

This role was created in 2023 by genirohtea.
