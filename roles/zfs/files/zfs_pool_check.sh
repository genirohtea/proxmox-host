#!/usr/local/bin/bash

# Log file
LOGFILE="/var/log/zfs_pool_check.log"

# Function to log messages
log() {
  echo "AUTO_ZFS $(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOGFILE"
}

log "Starting ZFS pool check"

# Determine the current week number
week_number=$(date +%U)

# Determine the day of the week
day_of_week=$(date +%u)

# Iterate over all ZFS pools
while IFS= read -r pool; do
  log "Checking pool: $pool"

  # Check and log autotrim status
  autotrim=$(zpool get -H -o value autotrim "$pool")
  log "Autotrim for $pool: $autotrim"

  # Enable autotrim if pool name contains 'nvme', 'ssd', or is 'rpool'
  if [[ "$pool" == *nvme* || "$pool" == *ssd* || "$pool" == "rpool" ]]; then
    if [[ "$autotrim" != "on" ]]; then
      zpool set autotrim=on "$pool"
      log "Enabled autotrim for $pool"
    fi
  fi

  # Check and set autoexpand if not already enabled
  autoexpand=$(zpool get -H -o value autoexpand "$pool")
  if [[ "$autoexpand" != "on" ]]; then
    zpool set autoexpand=on "$pool"
    log "Enabled autoexpand for $pool"
  fi

  # Check and log pool health, size, free space, and capacity
  health=$(zpool get -H -o value health "$pool")
  size=$(zpool list -H -o size "$pool")
  free_space=$(zpool list -H -o free "$pool")
  capacity=$(zpool list -H -o capacity "$pool")

  if [[ "$health" != "ONLINE" ]]; then
    log "$pool: ERROR: Health=$health, Size=$size, Free=$free_space, Capacity=$capacity"
  else
    log "$pool: Health=$health, Size=$size, Free=$free_space, Capacity=$capacity"
  fi

  # Run a scrub if it's Saturday of an odd week
  if [[ "$day_of_week" -eq 6 && $((week_number % 2)) -eq 1 ]]; then
    zpool scrub "$pool"
    log "Started scrub for $pool"
  fi

  # Log the last scrub status
  last_scrub=$(zpool status "$pool" | grep 'scan')
  if [[ -n "$last_scrub" ]]; then
    if echo "$last_scrub" | grep -q "with 0 errors"; then
      log "Last scrub status for $pool: $last_scrub"
    else
      log "WARNING: Last scrub status for $pool: $last_scrub"
    fi
  else
    log "WARNING: No previous scrub found for $pool"
  fi

  # Run a SMART test on all devices in the pool
  drives=$(zpool status -LP "$pool" | grep /dev/ | awk '{print $1}')
  for device in $drives; do
    if [[ "$day_of_week" -eq 7 ]]; then
      if [[ $((week_number % 2)) -eq 0 ]]; then
        # Run a SMART long test on Sunday of even weeks
        smartctl -t long "$device"
        log "Started SMART long test for $device"
      else
        # Run a SMART short test on Sunday of odd weeks
        smartctl -t short "$device"
        log "Started SMART short test for $device"
      fi
    fi
  done
done < <(zpool list -H -o name)

log "Finished ZFS pool check"
