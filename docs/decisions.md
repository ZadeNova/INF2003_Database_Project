# Decision Log (ADRs)

Append-only. One entry per decision, newest at the bottom. Supersede rather than edit:
if a decision changes, add a new ADR and mark the old one `Superseded by ADR-NNN`.

## Entry format

```
## ADR-NNN: <short title>

- **Date:** YYYY-MM-DD
- **Decision:** what we are doing, in one or two sentences.
- **Alternatives considered:** what else was on the table, and why it lost.
- **Rationale:** why this is the right call for this project, at this scale.
- **Approved by:** name(s).
```

---

## ADR-001: No mandatory PR review; CI enforced as the quality gate instead

- **Date:** 2026-09-10
- **Decision:** Pull requests do not require an approving review before merge. CI
  (lint, migrations-apply-cleanly + pytest, secret scan) is the enforced gate. Zade
  acts as sole reviewer on a retroactive/checkpoint basis rather than as a merge gate.
- **Alternatives considered:** Mandatory one-approval-per-PR — rejected as a blocking
  dependency on a single reviewer across a five-person team on a class timeline;
  reviewer availability would become the bottleneck. No gate at all — rejected because
  broken migrations and committed secrets are exactly the failures a class project
  ships by accident.
- **Rationale:** Automated checks catch the failure modes that actually matter here and
  never sleep; human review adds most of its value on design direction, which is better
  applied at checkpoints than per-merge.
- **Approved by:** Zade
