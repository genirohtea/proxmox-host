"""Focused metric-output tests for the IPMI fan controller."""

import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest


_SCRIPT = pathlib.Path(__file__).parents[1] / "files" / "spinpid2.py"
_JSONSCHEMA = types.ModuleType("jsonschema")
setattr(_JSONSCHEMA, "ValidationError", Exception)
sys.modules.setdefault(
    "jsonschema",
    _JSONSCHEMA,
)
_YAML = types.ModuleType("yaml")
setattr(_YAML, "YAMLError", Exception)
sys.modules.setdefault(
    "yaml",
    _YAML,
)
_SPEC = importlib.util.spec_from_file_location("spinpid2", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
spinpid2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(spinpid2)


class FanMetricTest(unittest.TestCase):
    """Verify fan RPM and duty metrics use controller-zone labels."""

    def test_prometheus_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "fans.prom"
            settings = spinpid2.Settings(
                ipmitool=["ipmitool"],
                log_file=str(pathlib.Path(directory) / "fan.log"),
                console=False,
                cpu_log_enable=False,
                cpu_log=str(pathlib.Path(directory) / "cpu.log"),
                prometheus_file=str(path),
                zone_cpu=0,
                zone_periph=1,
                duty_cpu_min=5,
                duty_cpu_max=100,
                duty_periph_min=25,
                duty_periph_max=100,
                rpm_cpu_30=500,
                rpm_cpu_max=1500,
                rpm_periph_30=2000,
                rpm_periph_max=4000,
                how_duty=1,
                setpoint=48.0,
                drive_interval=5.0,
                kp=4.0,
                kd=8.0,
                cpu_interval=5.0,
                cpu_ref=54,
                cpu_scale=6,
            )
            controller = spinpid2.FanController(settings)
            controller.fan_rpm = {"FAN1": 900, "FANA": 2700, "FANB": None}
            controller.duty_cpu = 30
            controller.duty_periph = 45
            controller._write_prometheus_metrics()
            output = path.read_text(encoding="utf-8")

        self.assertIn(
            'proxmox_ipmi_fan_speed_rpm{fan="FAN1",zone="cpu"} 900',
            output,
        )
        self.assertIn(
            'proxmox_ipmi_fan_speed_rpm{fan="FANA",zone="peripheral"} 2700',
            output,
        )
        self.assertNotIn('fan="FANB"', output)
        self.assertIn('proxmox_ipmi_fan_duty_ratio{zone="cpu"} 0.3', output)
        self.assertIn('proxmox_ipmi_fan_duty_ratio{zone="peripheral"} 0.45', output)


if __name__ == "__main__":
    unittest.main()
