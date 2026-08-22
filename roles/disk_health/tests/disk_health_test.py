"""Focused parser tests for the disk health reporter."""

import importlib.util
import json
import pathlib
import subprocess
import unittest

_SCRIPT = pathlib.Path(__file__).parents[1] / "files" / "disk_health.py"
_SPEC = importlib.util.spec_from_file_location("disk_health", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
disk_health = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(disk_health)


class DiskHealthParserTest(unittest.TestCase):
    """Verify representative smartctl output from SATA and NVMe devices."""

    def test_sata_metrics(self) -> None:
        output = """
194 Temperature_Celsius     0x0022  100 100 000 Old_age Always - 31
  9 Power_On_Hours          0x0032  099 099 000 Old_age Always - 12345
177 Wear_Leveling_Count     0x0013  095 095 000 Pre-fail Always - 5
  5 Reallocated_Sector_Ct   0x0033  100 100 010 Pre-fail Always - 2
197 Current_Pending_Sector  0x0012  100 100 000 Old_age Always - 3
198 Offline_Uncorrectable   0x0010  100 100 000 Old_age Offline - 4
199 UDMA_CRC_Error_Count    0x003e  200 200 000 Old_age Always - 6
"""
        metrics = disk_health.parse_sata_metrics(output)
        self.assertEqual(metrics["temperature"], "31")
        self.assertEqual(metrics["power_on_hours"], "12345")
        self.assertEqual(metrics["wear"], "5")
        self.assertEqual(metrics["reallocated_sectors"], "2")
        self.assertEqual(metrics["pending_sectors"], "3")
        self.assertEqual(metrics["offline_uncorrectable"], "4")
        self.assertEqual(metrics["udma_crc_errors"], "6")

    def test_sata_media_wearout_fallback(self) -> None:
        output = "233 Media_Wearout_Indicator 0x0032 099 099 000 Old_age Always - 88\n"
        self.assertEqual(disk_health.parse_sata_metrics(output)["wear"], "88")

    def test_nvme_metrics(self) -> None:
        output = """
Temperature:                        42 Celsius
Available Spare:                   98%
Available Spare Threshold:         10%
Percentage Used:                   12%
Data Units Written:                1,234,567 [632 GB]
Power On Hours:                    5,432
Unsafe Shutdowns:                  7
Media and Data Integrity Errors:   2
"""
        metrics = disk_health.parse_nvme_metrics(output)
        self.assertEqual(metrics["temperature"], "42 Celsius")
        self.assertEqual(metrics["available_spare"], "98%")
        self.assertEqual(metrics["available_spare_threshold"], "10%")
        self.assertEqual(metrics["percentage_used"], "12%")
        self.assertEqual(metrics["data_units_written"], "1,234,567 [632 GB]")
        self.assertEqual(metrics["power_on_hours"], "5,432")
        self.assertEqual(metrics["unsafe_shutdowns"], "7")
        self.assertEqual(metrics["media_integrity_errors"], "2")

    def test_warning_indicators(self) -> None:
        sata_warnings = disk_health._metric_warnings(
            "SATA",
            {
                "reallocated_sectors": "1",
                "pending_sectors": "0",
                "offline_uncorrectable": "2",
                "udma_crc_errors": "3",
            },
        )
        self.assertEqual(len(sata_warnings), 3)

        nvme_warnings = disk_health._metric_warnings(
            "NVMe",
            {
                "available_spare": "9%",
                "available_spare_threshold": "10%",
                "percentage_used": "100%",
                "media_integrity_errors": "1",
            },
        )
        self.assertEqual(len(nvme_warnings), 3)

    def test_health_and_self_test_parsing(self) -> None:
        health = disk_health._parse_health(
            "SMART overall-health self-assessment test result: PASSED\n",
        )
        self.assertEqual(health, "PASSED")
        latest = disk_health._latest_self_test(
            "# 1  Short offline Completed without error 00% 1234 -\n",
        )
        self.assertIn("Completed without error", latest)

    def test_disk_without_smart_does_not_warn(self) -> None:
        # A USB flash drive behind a bridge smartctl cannot talk SAT to. It
        # reports no health verdict, which is not a fault -- it must not push
        # the whole report into WARNING.
        output = (
            "/dev/sde: Unknown USB bridge [0x154b:0x1007 (0x110)]\n"
            "Please specify device type with the -d option.\n"
        )
        report = self._inspect_with_smartctl_output(
            disk_health.Disk(path="/dev/sde", model="USB 3.2.2 FD", size_bytes=500),
            output,
            returncode=1,
        )
        self.assertEqual(report.health, "SMART not available")
        self.assertEqual(report.warnings, [])

    def test_failing_smart_health_still_warns(self) -> None:
        report = self._inspect_with_smartctl_output(
            disk_health.Disk(path="/dev/sda", model="Dying SSD", size_bytes=500),
            "SMART overall-health self-assessment test result: FAILED!\n",
            returncode=0,
        )
        self.assertEqual(report.warnings, ["Overall SMART health: FAILED!"])

    def _inspect_with_smartctl_output(
        self,
        disk: "disk_health.Disk",
        output: str,
        returncode: int,
    ) -> "disk_health.DiskReport":
        original_run = getattr(disk_health, "_run")
        setattr(
            disk_health,
            "_run",
            lambda _command: subprocess.CompletedProcess(
                [],
                returncode,
                stdout=output,
                stderr="",
            ),
        )
        try:
            return disk_health.inspect_disk(disk)
        finally:
            setattr(disk_health, "_run", original_run)

    def test_virtual_zvols_are_not_physical_disks(self) -> None:
        devices = {
            "blockdevices": [
                {"name": "sda", "type": "disk", "model": "Physical", "size": 10},
                {"name": "nvme0n1", "type": "disk", "model": "NVMe", "size": 20},
                {"name": "zd0", "type": "disk", "model": None, "size": 1},
                {"name": "zd112", "type": "disk", "model": None, "size": 2},
            ],
        }
        original_run = getattr(disk_health, "_run")
        setattr(
            disk_health,
            "_run",
            lambda _command: subprocess.CompletedProcess(
                [],
                0,
                stdout=json.dumps(devices),
                stderr="",
            ),
        )
        try:
            disks = disk_health.list_physical_disks()
        finally:
            setattr(disk_health, "_run", original_run)
        self.assertEqual([disk.path for disk in disks], ["/dev/nvme0n1", "/dev/sda"])


if __name__ == "__main__":
    unittest.main()
