import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from rift import _fallback_core  # noqa: E402


class FallbackHardwareTests(TestCase):
    def test_hardware_profile_reads_nvidia_smi_when_native_runtime_is_absent(self):
        smi = SimpleNamespace(
            returncode=0,
            stdout=(
                "NVIDIA GeForce RTX 4060 Laptop GPU, 8188, 7590, 581.04\n"
            ),
            stderr="",
        )

        with patch("shutil.which", return_value=r"C:\\Windows\\System32\\nvidia-smi.exe"), patch(
            "subprocess.run", return_value=smi
        ):
            profile = _fallback_core.ControlPlaneRuntime().hardware_profile()

        self.assertTrue(profile["cuda_available"])
        self.assertEqual(profile["device_count"], 1)
        self.assertEqual(profile["device_name"], "NVIDIA GeForce RTX 4060 Laptop GPU")
        self.assertEqual(profile["total_vram_bytes"], 8188 * 1024**2)
        self.assertEqual(profile["free_vram_bytes"], 7590 * 1024**2)
        self.assertEqual(profile["driver_version"], "581.04")
        self.assertFalse(profile["native_cuda_runtime_available"])


if __name__ == "__main__":
    main()
