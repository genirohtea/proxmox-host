"""Focused tests for ZFS vdev Prometheus reporting."""

import datetime
import importlib.util
import pathlib
import tempfile
import unittest

_SCRIPT = pathlib.Path(__file__).parents[1] / "files" / "zfs_pool_check.py"
_SPEC = importlib.util.spec_from_file_location("zfs_pool_check", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
zfs_pool_check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(zfs_pool_check)


class ZfsVdevMetricsTest(unittest.TestCase):
    def test_parse_vdev_health_omits_pool_and_tracks_classes(self) -> None:
        status = """
  pool: tank
  state: DEGRADED
config:

        NAME                         STATE     READ WRITE CKSUM
        tank                         DEGRADED     0     0     0
          mirror-0                   DEGRADED     0     0     0
            /dev/disk/by-id/disk-a   ONLINE       0     0     0
            /dev/disk/by-id/disk-b   FAULTED      2     0     0
        cache
          /dev/nvme0n1               ONLINE       0     0     0
        spares
          /dev/sdc                   AVAIL

errors: No known data errors
"""
        vdevs = zfs_pool_check.parse_vdev_health("tank", status)
        self.assertEqual(
            [(item.vdev, item.vdev_class, item.state) for item in vdevs],
            [
                ("mirror-0", "data", "DEGRADED"),
                ("/dev/disk/by-id/disk-a", "data", "ONLINE"),
                ("/dev/disk/by-id/disk-b", "data", "FAULTED"),
                ("/dev/nvme0n1", "cache", "ONLINE"),
                ("/dev/sdc", "spares", "AVAIL"),
            ],
        )

    def test_write_vdev_metrics_marks_failed_state_unhealthy(self) -> None:
        vdevs = [
            zfs_pool_check.VdevHealth("tank", "mirror-0", "data", "DEGRADED"),
            zfs_pool_check.VdevHealth("tank", "/dev/sda", "data", "ONLINE"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "zfs.prom"
            zfs_pool_check.write_vdev_metrics(
                str(path),
                vdevs,
                datetime.datetime(2026, 8, 9, tzinfo=datetime.timezone.utc),
            )
            output = path.read_text(encoding="utf-8")
        self.assertIn('vdev="mirror-0",class="data",state="DEGRADED"} 0', output)
        self.assertIn('vdev="/dev/sda",class="data",state="ONLINE"} 1', output)
        self.assertIn(
            "proxmox_zfs_vdev_last_collection_timestamp_seconds 1786233600",
            output,
        )


if __name__ == "__main__":
    unittest.main()
