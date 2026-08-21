# Repository Layout

RIFT is released as a pure-Python control plane. The normal installation does
not require CUDA, CMake, Node.js, a compiler, a model, or a serving backend.

```text
rift/
|-- python/rift/       control plane, adapters, CLI, API, and bundled dashboard
|-- ui/                canonical dashboard source for contributors
|-- deploy/            controller, node, gateway, and test containers
|-- docs/              architecture, API, security, guides, and history
|-- examples/          small distributable rift.yaml examples
|-- scripts/           bootstrap, verification, and release helpers
|-- tests/             Python contract, integration, E2E, and static checks
|-- pyproject.toml     PEP 517 package metadata and console entry point
|-- README.md          clone-to-running quickstart
|-- LICENSE
|-- NOTICE
|-- SECURITY.md
|-- CONTRIBUTING.md
`-- CHANGELOG.md
```

The wheel includes `python/rift/web/static/`, the canonical operator console
served by `rift start` and `rift dashboard`. Node.js is only required when
rebuilding the contributor UI in `ui/`; it is not required by users.

Mutable runtime data is resolved by `RIFT_HOME` and never belongs in the
checkout. Defaults are `%LOCALAPPDATA%/RIFT` on Windows,
`$XDG_STATE_HOME/rift` or `~/.local/state/rift` on Linux, and
`~/Library/Application Support/RIFT` on macOS. Models, logs, certificates,
state, reports, caches, backend environments, and operation records live there.

The historical native CUDA runtime and Android client are experimental
archives, not package dependencies or release-branch runtime requirements.
They must be preserved in an archival tag before removal from the public
release tree. Generated builds, virtual environments, `node_modules`,
checkout-local `.rift/`, and model weights are ignored and are never shipped.
