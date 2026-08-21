# Release Audit

Before a public release, run:

```powershell
python scripts/audit_release.py --root . --json
```

The audit checks that the source tree does not include model weights, runtime
`.rift` state, virtual environments, build output, frontend dependency output,
secrets, or source ZIP snapshots. It also inventories direct Python and
canonical console npm dependencies and reports missing license metadata.

The audit uses Git-tracked paths when a valid Git checkout is available. In a
source export it falls back to a filesystem scan and treats `models/local/` as
operator-owned storage. A passing audit means repository hygiene and recorded
provenance are complete for the checked tree; it does not clear model,
backend, dataset, or benchmark licenses and is not legal advice.
