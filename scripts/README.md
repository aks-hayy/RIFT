# Development Scripts

The supported developer path is the pure-Python control plane. It works on
Windows, Linux, and macOS without CUDA or a native compiler.

```powershell
.\scripts\bootstrap.ps1
.\.venv\Scripts\rift.exe start --no-browser
```

```bash
./scripts/bootstrap.sh
./.venv/bin/rift start --no-browser
```

The bootstrap scripts create an isolated `.venv`, install the checked-out
package, and leave model downloads, backend installations, and launches behind
RIFT's explicit permission gates. Use `python scripts/verify_release.py` for
the local package and repository checks.

The native CUDA sources are historical experimental work. They are not part of
the normal package build and should only be rebuilt from the archival source
tag by contributors working on that separate project.
