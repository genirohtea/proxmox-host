# Changelog

## [1.1.0](https://github.com/genirohtea/proxmox-host/compare/v1.0.0...v1.1.0) (2024-06-20)


### Features

* **gpu passthrough:** added full GPU passthrough role ([a5e9eb0](https://github.com/genirohtea/proxmox-host/commit/a5e9eb0a7bcc6b9e72b0af52effc9087c7151f5b))
* **iommu enable:** adds a role that enables IOMMU on the proxmox host ([feb3af6](https://github.com/genirohtea/proxmox-host/commit/feb3af62aec0938e555aefccf9a3b18726e3c52d))
* **ipmi fan control:** adds script PID based IPMI fan control ([d524a19](https://github.com/genirohtea/proxmox-host/commit/d524a19b6c8e4a2253a2badd8bc48c0d0470e543))
* **terraform user:** added role to add the terraform user for use with the terraform provider ([afe4249](https://github.com/genirohtea/proxmox-host/commit/afe42498fc367299709909c02023a57836550d23))
* **vfio drivers:** added vfio drivers role that fixes graphics drivers to allow passthrough ([6a135ec](https://github.com/genirohtea/proxmox-host/commit/6a135eca0befb7bbaf1c889f5f8f93a2cdbcbe4a))


### Bug Fixes

* **ansible lint:** fixed lint to ignore line length ([24b8920](https://github.com/genirohtea/proxmox-host/commit/24b8920bfda04202ab165e6122caf23344bb2f86))
* **ansible sudo method:** moved sudo install to after repo fix due to required apt update ([1279fbb](https://github.com/genirohtea/proxmox-host/commit/1279fbbf8eeead3e02cf234e205020053533c231))
* **cpu_microcode:** use hostvars to access allow_reboot variable to ensure correct context is used for reboot permission check ([ae84a1f](https://github.com/genirohtea/proxmox-host/commit/ae84a1fbe4f3992adfbf3dde2d170f702b9d3397))
* **intel graphics:** fixed kernel pinning role not being a correct dependency ([0a3ca62](https://github.com/genirohtea/proxmox-host/commit/0a3ca6241dce59f2cb2f9fcc628b8eb2407f8a3f))
* **intel sriov:** changed kernel dkms module SHA now that bug has been fixed ([dbb43c4](https://github.com/genirohtea/proxmox-host/commit/dbb43c4680764059aec9ba427a0fde5026af9d16))
* **iommu_enable:** fixed false CPU vendor detection ([2349922](https://github.com/genirohtea/proxmox-host/commit/23499221d596f6bf2bce506b724acfc79b9cb214))
* **ipmi fan control:** fixed autostart ansible to fail correctly using rescue ([9855f8b](https://github.com/genirohtea/proxmox-host/commit/9855f8b5c2d15baceaf5dccb7ea2b2a4e9000516))

## 1.0.0 (2024-04-19)


### Features

* **proxmox host:** added initial proxmox host provisioning ansible playbook ([f5fb328](https://github.com/genirohtea/proxmox-host/commit/f5fb328f9bb14a86e6688d3f00193d2ef2233ad3))
