#!/usr/bin/env bash
# https://betterdev.blog/minimal-safe-bash-script-template/
set -Eeuo pipefail

# script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd -P)

upsearch() {
  slashes=${PWD//[^\/]/}
  directory="$PWD"
  for ((n = ${#slashes}; n > 0; --n)); do
    test -e "$directory/$1" && break
    directory="$directory/.."
  done
  ansible_dir=$(python3 -c "import os;print(os.path.abspath('${directory}'))")
  echo "${ansible_dir}"
}

ansible_dir=$(upsearch ".ansible_root_signpost")
echo "Identified ansible root directory as ${ansible_dir}"

usage() {
  cat <<EOF
Usage: $(basename "${BASH_SOURCE[0]}") [-h] [-v] [-t <tags>] [-r] [-i] [-s <SHA>] -H <host>

This script runs the Ansible playbook for configuring Proxmox hosts with Intel Graphics VT-d support.

Available options:

-h, --help      Print this help and exit
-v, --verbose   Print script debug info
-t, --tags      Specify Ansible tags to run specific tasks
-r, --allow_reboot  Allow the script to reboot the host if necessary
-i, --install_intel_vtd  Install Intel VT-d support
-H, --host      Specify the host from the Ansible inventory to run the playbook on
EOF
  exit
}

die() {
  local msg=$1
  local code=${2-1} # default exit status 1
  msg "$msg"
  exit "$code"
}

allow_reboot='false'
install_intel_vtd='false'
tags=''
parse_params() {
  while :; do
    case "${1-}" in
    -h | --help) usage ;;
    -v | --verbose) set -x ;;
    -t | --tags)
      tags="${2-}"
      shift
      ;;
    -r | --allow_reboot) allow_reboot='true' ;;           # example flag
    -i | --install_intel_vtd) install_intel_vtd='true' ;; # example flag
    -H | --host)
      host="${2-}"
      shift
      ;;

    -?*) die "Unknown option: $1" ;;
    *) break ;;
    esac
    shift
  done

  args=("$@")

  # check required params and arguments
  [[ -z "${allow_reboot-}" ]] && die "Missing required parameter: allow_reboot"
  [[ -z "${install_intel_vtd-}" ]] && die "Missing required parameter: install_intel_vtd"
  [[ -z "${host-}" ]] && die "Missing required parameter: host"

  return 0
}

msg() {
  echo >&2 -e "${1-}"
}

parse_params "$@"

msg "Read parameters:"
msg "- arguments: ${args[*]-}"
msg "- allow_reboot: ${allow_reboot}"
msg "- install_intel_vtd: ${install_intel_vtd}"

read -p "Please confirm arguments: " -n 1 -r
echo # move to a new line
if [[ $REPLY =~ ^[Yy]$ ]]; then
  msg "User accepted arguments"
else
  die "User rejected arguments"
fi

msg "Running playbook on ${host}"

pushd "${ansible_dir}"
if [[ -n "${tags-}" ]]; then
  ansible-playbook main.yml --ask-pass --tags "${tags}" --extra-vars '{"allow_reboot": '\""${allow_reboot}"\"', "install_intel_vtd": '\""${install_intel_vtd}"\"' }' --limit "${host}" -vvv
else
  ansible-playbook main.yml --ask-pass --extra-vars '{"allow_reboot": '\""${allow_reboot}"\"', "install_intel_vtd": '\""${install_intel_vtd}"\"' }' --limit "${host}" -vvv
fi
popd
