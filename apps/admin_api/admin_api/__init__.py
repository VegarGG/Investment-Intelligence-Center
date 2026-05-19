"""Admin / configuration API (P3).

FastAPI service that exposes a UI-friendly interface over the YAML
configuration files in `docs/prompts/`, `packages/featureflags/`,
`infra/intel/`, and the sops-sealed secrets under `secrets/sealed/`.

Goals:
- Keep YAML as the persistence format so git remains the audit trail.
- Hash-chain every write to `lake.config_audit` so dashboard edits are
  auditable end-to-end.
- Never return decrypted secrets to the dashboard; expose a "rotate"
  surface instead.
"""

from . import audit, config_io, connectors, schedules, secrets

__all__ = ["audit", "config_io", "connectors", "schedules", "secrets"]
