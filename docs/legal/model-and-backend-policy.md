# Model And Backend Policy

RIFT is a control plane, not a model distributor. The source release contains
no model weights and no third-party backend binaries.

## User Responsibilities

- Confirm the model repository license, gated-access terms, dataset terms, and
  acceptable-use requirements before downloading or serving a model.
- Confirm the serving backend license and platform requirements before install.
- Keep private model files and credentials outside source control.
- Use explicit RIFT permissions for download, install, launch, remote access,
  and public exposure.

## RIFT Behavior

RIFT records license metadata and uncertainty as recommendation evidence. A
missing license is a deployment warning, not an approval. RIFT does not infer
that a model is legally deployable from popularity, benchmark results, or a
compatible file format. Generated plans retain the model revision, selected
artifact, source, and license warning so an operator can review the decision.

This document is operational guidance, not legal advice.
