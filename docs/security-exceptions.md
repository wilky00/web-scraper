# Security Exceptions

This document records known vulnerabilities that cannot be immediately patched, along with the accepted risk rationale and planned resolution.

Required by project security baseline (§14). All entries must be reviewed before each production release.

---

## Format

Each entry must include:

- **Package** — affected package and version
- **CVE / Advisory** — identifier
- **Severity** — Critical / High / Medium / Low
- **Description** — what the vulnerability is
- **Reason unpatchable** — why we cannot update right now (dependency conflict, no fix available, etc.)
- **Mitigations** — compensating controls in place
- **Resolution plan** — when and how it will be fixed
- **Added by / date** — who accepted this exception and when

---

## Active Exceptions

_No exceptions at time of writing (2026-05-16). `pip-audit` scan returned clean._

---

## Resolved Exceptions

_None._

---

## Process

1. Run `pip-audit` against the locked dependencies:
   ```bash
   uv run pip-audit
   ```

2. For each finding, attempt to upgrade the affected package:
   ```bash
   uv add <package>@latest
   uv run pytest tests/ -v
   ```

3. If the upgrade breaks tests or creates incompatible dependency constraints, document it here and submit a follow-up ticket.

4. All active exceptions must be re-reviewed at each production release. Any exception older than 90 days without a resolution plan requires escalation.
