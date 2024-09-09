# Changelog

## [1.1.0](https://github.com/genirohtea/proxmox-host/compare/v1.0.0...v1.1.0) (2024-09-09)


### Features

* **admin user:** added admin user creation to prevent root usage ([5fc9b94](https://github.com/genirohtea/proxmox-host/commit/5fc9b944ca1d33d17fedf970a0c8a42376fb6355))
* **coral:** added coral firmware installation role ([06c9dac](https://github.com/genirohtea/proxmox-host/commit/06c9dac28928b9ce0023b506737c7807fc2cd4e9))
* **download isos:** added role that downloads common VM images ([0248b62](https://github.com/genirohtea/proxmox-host/commit/0248b62a5e15150c240386000371e3ef59dc463e))
* **download isos:** updated download ISOs to rename downloaded ISOs to be more terraform friendly ([e51a815](https://github.com/genirohtea/proxmox-host/commit/e51a815b7be259a4480d47877e689587d5a5be0d))
* **gpu passthrough:** added full GPU passthrough role ([a5e9eb0](https://github.com/genirohtea/proxmox-host/commit/a5e9eb0a7bcc6b9e72b0af52effc9087c7151f5b))
* **iommu enable:** adds a role that enables IOMMU on the proxmox host ([feb3af6](https://github.com/genirohtea/proxmox-host/commit/feb3af62aec0938e555aefccf9a3b18726e3c52d))
* **ipmi fan control:** adds script PID based IPMI fan control ([d524a19](https://github.com/genirohtea/proxmox-host/commit/d524a19b6c8e4a2253a2badd8bc48c0d0470e543))
* **nvidia vgpu:** added role that enables nvidia vgpu ([c5d20c6](https://github.com/genirohtea/proxmox-host/commit/c5d20c626c1648f1db87b6ecc2dbacd5b0ddd6ab))
* **terraform user:** added role to add the terraform user for use with the terraform provider ([afe4249](https://github.com/genirohtea/proxmox-host/commit/afe42498fc367299709909c02023a57836550d23))
* **vfio drivers:** added vfio drivers role that fixes graphics drivers to allow passthrough ([6a135ec](https://github.com/genirohtea/proxmox-host/commit/6a135eca0befb7bbaf1c889f5f8f93a2cdbcbe4a))
* **zfs:** added ZFS + Smart monitoring for ZFS pools ([b5fd878](https://github.com/genirohtea/proxmox-host/commit/b5fd8782fc7c67f96b1df781e8cbbd4825bfe11c))


### Bug Fixes

* **ansible lint:** fixed lint to ignore line length ([24b8920](https://github.com/genirohtea/proxmox-host/commit/24b8920bfda04202ab165e6122caf23344bb2f86))
* **ansible sudo method:** moved sudo install to after repo fix due to required apt update ([1279fbb](https://github.com/genirohtea/proxmox-host/commit/1279fbbf8eeead3e02cf234e205020053533c231))
* **ansible vars:** fixed issue where feature flags were not being used since they were not in vars ([c81dbbf](https://github.com/genirohtea/proxmox-host/commit/c81dbbf3ed19d69928d09083fbd27f4f7319c6e4))
* **cpu_microcode:** use hostvars to access allow_reboot variable to ensure correct context is used for reboot permission check ([ae84a1f](https://github.com/genirohtea/proxmox-host/commit/ae84a1fbe4f3992adfbf3dde2d170f702b9d3397))
* **gpu passthrough:** fixed iommu and vfio being run regardless of gpu_passthrough ([1c1120c](https://github.com/genirohtea/proxmox-host/commit/1c1120c425774de40acd57da9720bc6b14fce80d))
* **intel graphics:** fixed kernel pinning role not being a correct dependency ([0a3ca62](https://github.com/genirohtea/proxmox-host/commit/0a3ca6241dce59f2cb2f9fcc628b8eb2407f8a3f))
* **intel graphics:** fixed meta kernel pinning that wasnt correctly feature flag scoped ([997566c](https://github.com/genirohtea/proxmox-host/commit/997566c3d4d65d33bba6784f67342f24fbbcdd02))
* **intel sriov:** changed kernel dkms module SHA now that bug has been fixed ([dbb43c4](https://github.com/genirohtea/proxmox-host/commit/dbb43c4680764059aec9ba427a0fde5026af9d16))
* **iommu_enable:** fixed false CPU vendor detection ([2349922](https://github.com/genirohtea/proxmox-host/commit/23499221d596f6bf2bce506b724acfc79b9cb214))
* **ipmi fan control:** fixed autostart ansible to fail correctly using rescue ([9855f8b](https://github.com/genirohtea/proxmox-host/commit/9855f8b5c2d15baceaf5dccb7ea2b2a4e9000516))
* **ipmi fan control:** fixed issue where per-host ipmi installation was installing on all hosts ([3bab259](https://github.com/genirohtea/proxmox-host/commit/3bab2590d862c51b90184eb4af9a133fc117035c))
* **kernel pinning:** fixed case where kernel pinning as a dependent role was ending its parent role ([1bc2ba8](https://github.com/genirohtea/proxmox-host/commit/1bc2ba814efeb0e0c6cc9c96cf85e99b0bbf4231))
* **kernel pinning:** fixed case where the kernel would not get pinned due to ansible var resolution ([1fd60f1](https://github.com/genirohtea/proxmox-host/commit/1fd60f1a2d784a0cd10becc5c052dbe26ac24c60))
* **nvidia vgpu:** fixed kernel pinning required for vGPU + required tooling to install drivers ([30308f1](https://github.com/genirohtea/proxmox-host/commit/30308f179404b82d2f79f891e5446133cfd35ca7))
* **run script:** simplified run script verbosity and tag addtions ([a6b7204](https://github.com/genirohtea/proxmox-host/commit/a6b7204393e7ff5be67ee4170e10a68b64ffb8e1))
* **terraform:** fixed case where terraform role creation fails if it already exists ([77b4ad9](https://github.com/genirohtea/proxmox-host/commit/77b4ad981cf473abb54f780a9ba6c87d604914af))
* **terraform:** updated to bgp/proxmox terraform provider requiring user with sudo ([2e8ea34](https://github.com/genirohtea/proxmox-host/commit/2e8ea34264b973bfde30c79a782738ba9702d8f4))

## 1.0.0 (2024-04-19)


### Features

* **proxmox host:** added initial proxmox host provisioning ansible playbook ([f5fb328](https://github.com/genirohtea/proxmox-host/commit/f5fb328f9bb14a86e6688d3f00193d2ef2233ad3))
