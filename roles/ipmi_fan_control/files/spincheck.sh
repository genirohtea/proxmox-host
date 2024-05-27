#!/usr/local/bin/bash
# shellcheck disable=SC2034
# spincheck.sh, logs fan and temperature data
VERSION="2020-06-17"
# Run as superuser. See notes at end.

# Creates logfile and sends all stdout and stderr to the log,
# leaving the previous contents in place. If you want to append to existing log,
# add '-a' to the tee command.
# Change to your desired log location/name:
LOG=$(dirname "${BASH_SOURCE[0]}")/../spincheck.log
exec > >(tee -i "$LOG") 2>&1

SP=33.57    #  Setpoint mean drive temp (C), for information only

# Path to ipmitool.  If you're doing VM
# you may need to add (after first quote) the following to
# remotely execute commands.
#  -H <hostname/ip> -U <username> -P <password>
IPMITOOL=$(which ipmitool)

##############################################
# function get_disk_name
# Get disk name from current LINE of DEVLIST
##############################################
function get_disk_name {
    # Extract the disk name using awk to handle the new lshw output format
    # /0/10f/3.2/0/1            /dev/nvme2n1     disk           4TB NVMe disk
    # /0/116/1.1/0/1            /dev/nvme0n1     disk           960GB NVMe disk
    # /0/116/3.1/0/0.4.0        /dev/sde         disk           18TB WDC WD180EDGZ-11
    # /0/116/3.1/0/0.5.0        /dev/sdf         disk           18TB WDC WD180EDGZ-11
    DEVID=$(echo "$LINE" | awk '{print $2}')
}




############################################################
# function print_header
# Called when script starts and each quarter day
############################################################
function print_header {
   DATE=$(date +"%A, %b %d")
   printf "\n%s \n" "$DATE"
   echo -n "          "
   while read -r LINE ; do
      get_disk_name
      ABBR_DEV_ID=$(echo "$DEVID" | sed -E 's#/dev/nvme([0-9]+n[0-9]+)#\1#g' | sed -E 's#/dev/(sd[a-z])#\1#g')
      printf "%-5s" "$ABBR_DEV_ID"
   done <<< "$DEVLIST"             # while statement works on DEVLIST
   printf "%4s %5s %5s %3s %5s %5s %5s %5s %5s %5s %5s %5s %-7s" "Tmax" "Tmean" "ERRc" "CPU" "FAN1" "FAN2" "FAN3" "FAN4" "FANA" "FANB" "Fan%0" "Fan%1" "MODE"
}

#################################################
# function manage_data: Read, process, print data
#################################################
function manage_data {
   Tmean=$(echo "scale=3; $Tsum / $i" | bc)
   ERRc=$(echo "scale=2; $Tmean - $SP" | bc)
   # Read duty cycle, convert to decimal.
   # May need to disable these 3 lines as some boards apparently return
   # incorrect data. In that case just assume $DUTY hasn't changed.
   DUTY0=$($IPMITOOL raw 0x30 0x70 0x66 0 0) # in hex
   DUTY0=$((0x${DUTY0// /}))   # strip leading space and decimate
   DUTY1=$($IPMITOOL raw 0x30 0x70 0x66 0 1) # in hex
   DUTY1=$((0x${DUTY1// /}))   # strip leading space and decimate
   # Read fan mode, convert to decimal.
   MODE=$($IPMITOOL raw 0x30 0x45 0) # in hex
   MODE=$((0x${MODE// /}))   # strip leading space and decimate
   # Text for mode
   case $MODE in
      0) MODEt="Standard" ;;
      4) MODEt="HeavyIO" ;;
      2) MODEt="Optimal" ;;
      1) MODEt="Full" ;;
   esac
   # Get reported fan speed in RPM.
   # Get reported fan speed in RPM from sensor data repository.
   # Takes the pertinent FAN line, then a number with 3 to 5
   # consecutive digits
   SDR=$($IPMITOOL sdr)
   RPM_FAN1=$(echo "$SDR" | grep "FAN1" | grep -Eo '[0-9]{3,5}')
   RPM_FAN2=$(echo "$SDR" | grep "FAN2" | grep -Eo '[0-9]{3,5}')
   RPM_FAN3=$(echo "$SDR" | grep "FAN3" | grep -Eo '[0-9]{3,5}')
   RPM_FAN4=$(echo "$SDR" | grep "FAN4" | grep -Eo '[0-9]{3,5}')
   RPM_FANA=$(echo "$SDR" | grep "FANA" | grep -Eo '[0-9]{3,5}')
   RPM_FANB=$(echo "$SDR" | grep "FANB" | grep -Eo '[0-9]{3,5}')
   # Get    # print current Tmax, Tmean
   printf "^%-3d %5.2f" "$Tmax" "$Tmean"
}

##############################################
# function DRIVES_check
# Print time on new log line.
# Go through each drive, getting and printing
# status and temp, then call function manage_data.
##############################################
function DRIVES_check {
   echo  # start new line
   TIME=$(date "+%H:%M:%S"); echo -n "$TIME  "
   Tmax=0; Tsum=0  # initialize drive temps for new loop through drives
   i=0  # count number of spinning drives
   while read -r LINE ; do
      get_disk_name
      smartctl -a -n standby "$DEVID" > /var/tempfile
      RETURN=$?  # have to preserve return value or it changes
      BIT0=$((RETURN & 1))
      BIT1=$((RETURN & 2))
      if [ $BIT0 -eq 0 ]; then
         if [ $BIT1 -eq 0 ]; then
            STATUS="*"  # spinning
         else  # drive found but no response, probably standby
            STATUS="_"
         fi
      else   # smartctl returns 1 (00000001) for missing drive
         STATUS="?"
      fi

      TEMP=""
      # Update temperatures each drive; spinners only
      if [ "$STATUS" == "*" ] ; then
         # Taking 10th space-delimited field for most SATA:
         if grep -Fq "Temperature_Celsius" /var/tempfile ; then
            TEMP=$( < /var/tempfile grep "Temperature_Celsius" | awk '{print $10}')

         # SAS output is :
         #     Transport protocol: SAS (SPL-3) . . .
         #     Current Drive Temperature: 45 C
         #  else
         #      TEMP=$( < /var/tempfile grep "Drive Temperature" | awk '{print $4}')

         # NVME output is :
         #     Temperature:                        48 Celsius
         else
            TEMP=$( < /var/tempfile grep "Temperature: " | awk '{print $2}')

         fi
         ((Tsum += TEMP)) || true
         if [[ $TEMP -gt $Tmax ]]; then Tmax=$TEMP; fi;
         ((i++)) || true
      fi
      printf "%s%-2d  " "$STATUS" "$TEMP"
   done <<< "$DEVLIST"
   manage_data  # manage data function
}

#####################################################
# All this happens only at the beginning
# Initializing values, list of drives, print header
#####################################################

# Check if CPU Temp is available via sysctl (will likely fail in a VM)
CPU_TEMP_SYSCTL=$(($(sysctl -a | grep -c "dev.cpu.0.temperature") > 0))
if [[ $CPU_TEMP_SYSCTL == 1 ]]; then
    CORES=$(($(sysctl -n hw.ncpu)-1))
fi

echo "How many whole minutes do you want between spin checks?"
read -r T
SEC=$(bc <<< "$T*60")           # bc is a calculator
# Get list of drives
DEVLIST1=$(lshw -class disk -short)
DEVLIST=$(echo "$DEVLIST1" | grep -e '/dev/nv' -e '/dev/sd' | grep -v 'USB')
DEVCOUNT=$(echo "$DEVLIST" | wc -l)
printf "\n%s\n%s\n%s\n" "NOTE ABOUT DUTY CYCLE (Fan%0 and Fan%1):" \
"Some boards apparently report incorrect duty cycle, and can" \
"report duty cycle for zone 1 when that zone does not exist."

# Before starting, go through the drives to report if
# smartctl return value indicates a problem (>2).
# Use -a so that all return values are available.
while read -r LINE ; do
   get_disk_name
   smartctl -a -n standby "$DEVID" > /var/tempfile
   if [ $? -gt 2 ]; then
      printf "\n"
      printf "*******************************************************\n"
      printf "* WARNING - Drive %-4s has a record of past errors,   *\n" "$DEVID"
      printf "* is currently failing, or is not communicating well. *\n"
      printf "* Use smartctl to examine the condition of this drive *\n"
      printf "* and conduct tests. Status symbol for the drive may  *\n"
      printf "* be incorrect (but probably not).                    *\n"
      printf "*******************************************************\n"
   fi
done <<< "$DEVLIST"

printf "\n%s %36s %s \n" "Key to drive status symbols:  * spinning;  _ standby;  ? unknown" "Version" $VERSION
print_header

###########################################
# Main loop through drives every T minutes
###########################################
while true ; do
    # Print header every quarter day.  Expression removes any
    # leading 0 so it is not seen as octal
    HM=$(date +%k%M); HM=$((HM + 0))
    R=$(( HM % 600 ))  # remainder after dividing by 6 hours
    if (( R < T )); then print_header; fi

      Tmax=0; Tsum=0  # initialize drive temps for new loop through drives
    DRIVES_check

    if [[ $CPU_TEMP_SYSCTL == 1 ]]; then
       # Find hottest CPU core
       MAX_CORE_TEMP=0
       for CORE in $(seq 0 "$CORES")
       do
           CORE_TEMP="$(sysctl -n dev.cpu."${CORE}".temperature | awk -F '.' '{print$1}')"
           if [[ $CORE_TEMP -gt $MAX_CORE_TEMP ]]; then MAX_CORE_TEMP=$CORE_TEMP; fi
       done
       CPU_TEMP=$MAX_CORE_TEMP
   else
       CPU_TEMP=$($IPMITOOL sensor get "CPU Temp" | awk '/Sensor Reading/ {print $4}')
   fi

   # Print data.  If a fan doesn't exist, RPM value will be null.  These expressions
   # substitute a value "---" if null so printing is not messed up.  Duty cycle may be
   # reported incorrectly by boards and they can report duty for zone 1 even if there
   # is no such zone.
    printf "%6.2f %3d %5s %5s %5s %5s %5s %5d %5d %5d %-7s" "$ERRc" "$CPU_TEMP" "${RPM_FAN1:----}" "${RPM_FAN2:----}" "${RPM_FAN3:----}" "${RPM_FAN4:----}" "${RPM_FANA:----}" "${RPM_FANB:----}" $DUTY0 $DUTY1 "$MODEt"

    sleep $((T*60)) # seconds between runs
done

# Logs:
#   - disk status (spinning or standby)
#   - disk temperature (Celsius) if spinning
#   - max and mean disk temperature
#   - current 'error' of Tmean from setpoint (for information only)
#   - CPU temperature
#   - RPM for FAN1-4 and FANA
#   - duty cycle for fan zones 0 and 1
#   - fan mode

# Includes disks on motherboard and on HBA.
# Uses joeschmuck's smartctl method (returns 0 if spinning, 2 in standby)
# https://forums.freenas.org/index.php?threads/how-to-find-out-if-a-drive-is-spinning-down-properly.2068/#post-28451
# Other method (camcontrol cmd -a) doesn't work with HBA
