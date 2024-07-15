# Tests for Ansible configuration of Proxmox hosts

## Local Setup on macOS

- Install docker & colima
- Set docker socket via env

```bash
# Setup Molecule
pip install molecule
pip install molecule-plugins[docker] # Add the docker driver
molecule init scenario <scenario_name> --driver-name=docker


# Setup docker
brew install docker docker-compose colima
colima start
docker run hello-world
DOCKER_HOST=unix:///Users/<user>/.orbstack/run/docker.sock molecule test all
```
