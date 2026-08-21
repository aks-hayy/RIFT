# Contributing to RIFT

Thank you for helping make local LLM serving more predictable.

## Development Setup

1. Install Python 3.9+, CMake 3.26+, Ninja, a C++17 compiler, and a compatible
   CUDA toolkit for native builds.
2. Create `.venv` and install the project with `python -m pip install -e .` from
   a compiler-enabled shell.
3. Run `npm install` in `seismic-deploy-main/` for canonical operator-interface development.
4. Keep model files under `models/local/`; they are intentionally ignored.

## Change Expectations

- Preserve RIFT's explicit permission gates. A command must never silently
  download, install, launch, stop, expose, or delete resources.
- Keep recommendations evidence-labelled. Metadata is not measured accuracy.
- Mark emulated and fake-backend results as such.
- Add focused tests for behavior changes and run the complete affected suite.
- Update `CHANGELOG.md` and relevant documents for user-visible changes.

## Verification

```powershell
cmake --preset windows-release
cmake --build --preset windows-release
ctest --preset windows-release

cd seismic-deploy-main
npm run lint
npm run build
```

Pull requests should describe the tested platform, backend, model format, and
whether results are measured, emulated, or estimated.

Hosted CI runs the deterministic Python control-plane suites and the complete
dashboard lint/type/build gate. Native C++/CUDA changes must also include CTest
results from real compatible CUDA hardware until a public self-hosted native
matrix is available.
