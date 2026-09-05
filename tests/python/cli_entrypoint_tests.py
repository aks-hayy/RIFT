import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_python_module_entrypoint_prints_help() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy,sys,types; m=types.ModuleType('rift._core'); m.InferenceEngine=object; m.__version__='test'; m.build_info=lambda: {}; m.cuda_device_count=lambda: 0; m.inspect_model=lambda *a,**k: {}; m.parse_model_topology=lambda *a,**k: {}; sys.modules['rift._core']=m; sys.argv=['rift','--help']; runpy.run_module('rift',run_name='__main__')",
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "python")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "RIFT fits LLM deployments" in result.stdout


def main() -> None:
    test_python_module_entrypoint_prints_help()
    print("cli_entrypoint_tests: PASS")


if __name__ == "__main__":
    main()
