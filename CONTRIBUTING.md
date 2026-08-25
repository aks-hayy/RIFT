# Contributing to RIFT

Thank you for helping make local LLM serving more predictable.

## Development Setup

1. Install Python 3.10 or newer.
2. Run `scripts/bootstrap.ps1` on Windows or `scripts/bootstrap.sh` on
   Linux/macOS. These create a local environment and install the pure-Python
   control plane.
3. Run `python -m pip install -e .` when iterating on Python source.
4. Run `npm install` in `ui/` only when developing dashboard source. End users
   do not need Node.js because the packaged dashboard is bundled.
5. Keep model files under `models/local/`; they are intentionally ignored.

## Change Expectations

- Preserve RIFT's explicit permission gates. A command must never silently
  download, install, launch, stop, expose, or delete resources.
- Keep recommendations evidence-labelled. Metadata is not measured accuracy.
- Mark emulated and fake-backend results as such.
- Add focused tests for behavior changes and run the complete affected suite.
- Update `CHANGELOG.md` and the relevant README section for user-visible
  changes. Keep the OpenAPI contracts synchronized with API changes.

## Verification

```powershell
python scripts/verify_release.py
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
python -m pip install --force-reinstall dist\rift_llm-*.whl
rift --version
rift doctor
```

Pull requests should describe the tested platform, backend, model format, and
whether results are measured, emulated, or estimated.

Hosted CI runs the deterministic Python control-plane suites across supported
Python versions, the release audit, package build, and clean installed-wheel
smoke. Dashboard source changes should include reproducible `ui/` build
results when Node.js is available. Native survival and Android experiments
are archived and are not part of the release package.
