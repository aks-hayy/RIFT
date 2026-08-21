# Security Policy

## Supported Releases

RIFT is currently a preview. Security fixes are applied to the latest source
revision only until stable release branches are published.

## Reporting a Vulnerability

Do not open a public issue containing credentials, model access tokens, private
endpoints, logs with prompts, or exploit details. Contact the project maintainer
privately through the repository's security-advisory channel once the public
repository is published.

Include the affected RIFT version, operating system, backend, reproduction
steps, impact, and whether a public endpoint was involved. Use
`rift system diagnostics` only after reviewing the redacted bundle.

## Security Boundaries

- RIFT binds local control and gateway services to `127.0.0.1` by default.
- Downloads, installations, launches, remote actions, and destructive commands
  require explicit permission.
- Third-party backends execute with the permissions of the RIFT operator.
- API-key records are hash-only, but TLS termination and distributed secret
  management remain deployment responsibilities.
- Model artifacts are untrusted input and must be governed and verified before
  deployment.
