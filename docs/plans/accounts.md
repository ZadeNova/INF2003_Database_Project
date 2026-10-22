# accounts: Three roles, seller registration and approval, operator console, audit log

status: in-progress
plan owner: Chee Long · implementer: Chee Long · reviewer: fresh Claude Code session · estimate: 1.5 to 2 days
· Phase 1B (25 October 2026) · depends on: `olist-import` (custom user with `role`, seller table)

## Contract

**Goal.** Separate customer, seller and operator access; approve seller applications and audit status changes.
Use additive migrations on the Phase 1A schema: do not replace the custom user, rewrite `0001` or reset imported data.

| Area | Deliverable |
|---|---|
| Roles (P1) | One role per user: customer, seller, operator. Extend `HtmxLoginRequiredMixin` with customer/approved-seller/operator access checks. Login routes to shop, seller centre or operator console; pending, rejected and suspended sellers can log in and see only their own status page, with every operational seller page/action denied, including existing sessions. Role navigation and local-only validated `next` redirects |
| Registration | `/register/` creates customer user/profile (optional location); `/sell/apply/` atomically creates seller user/row, initially pending (shop name, city, state, zip prefix). Neither form accepts role/status escalation; CSRF on mutations |
| Seller status | Existing CHECK plus `BEFORE UPDATE … WHEN (OLD.status IS DISTINCT FROM NEW.status)` trigger: pending → approved/rejected, approved → suspended, suspended → approved; rejected is terminal. Unchanged status and shop-name edits are allowed without status audit. Suspension hides products through `purchasable_product`; reinstatement restores otherwise eligible products |
| Operator | `/operator/` seller list by status; approve, reject, suspend, reinstate via POST with nonblank reason. Within `transaction.atomic()`, `select_for_update()` the seller, recheck expected prior state/transition, set audit context, then update. A stale/repeated action fails without another audit row. Product/review take-downs belong to catalogue/reviews |
| Audit | Add `audit_log`: ID, table name, row ID as text (including MongoDB IDs), action, nullable actor FK, before/after JSONB, reason, timestamp. Seller-status trigger records actual changes atomically; snapshots exclude secrets. `/operator/audit/` is operator-only, paginated, newest timestamp then ID, with actor and action filters only; escape output |
| Management/demo | Operators only from `seed_demo` or `create_operator`, password from ignored `DEMO_OPERATOR_PASSWORD`, rejecting missing/placeholders and role collisions; never print or accept passwords on the command line. Add a labelled pending seller using `DEMO_SELLER_PASSWORD`; seed reruns preserve existing demo adjustments and any decided seller status |

**Shared audit boundary (P2–P4).** Audit trigger functions are `SECURITY DEFINER`, owned by the migration owner,
with referenced objects schema-qualified and `search_path` pinned to `public, pg_temp`. The migration explicitly
revokes runtime `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE` on `public.audit_log` and all audit-sequence privileges;
runtime retains table `SELECT`. Runtime cannot own/replace functions, disable triggers or create in trusted schemas;
broad grant helpers must not restore forbidden grants. Revoking PUBLIC/runtime `EXECUTE` on trigger-only functions
is hygiene, not the security control: table/sequence revocations, owner ownership and the pinned search path are.
Catalogue/checkout triggers share this boundary; reviews alone gets the narrow moderation API in its own plan (P3).

Every action sets **both** transaction-local settings with bound `SELECT set_config('mercer.actor_id', %s, true)`
and `SELECT set_config('mercer.audit_reason', %s, true)`, using empty strings for absent values. Triggers read
`NULLIF(current_setting('mercer.actor_id', true), '')::bigint` and
`NULLIF(current_setting('mercer.audit_reason', true), '')`. Missing actor means a system change; operator actions
require a reason. Context clears on commit/rollback. Trust limit: runtime code can still choose the actor it sets;
application authorization and the database owner remain trusted.

**Tests.** Real databases: role/access matrix including all seller statuses and cross-seller identity tampering;
one HTMX access test; registration validation/CSRF/rollback and safe redirects; legal/illegal/unchanged transitions;
exact audit actor/reason/snapshots, system actor, rollback and reused-connection context clearing; one stale/repeated
operator-action test. Connect as the actual runtime role to prove trigger writes and SELECT work while direct
audit INSERT/UPDATE/DELETE/TRUNCATE, sequence access and trigger/function tampering fail, including after all grants.
Cover actor/action filters, pagination/escaping, repeatable seeding and operator credential/role-collision checks;
each new raw-SQL path has an injection negative. Keep existing import, profile-role and demo tests passing.

**Exit check (fresh reviewer).** Register/login a customer; apply/login as pending seller; approve with reason and
show seller access/audit; reject another application; suspend/reinstate and check list/direct-detail visibility;
prove suspended → pending SQL fails. Migrate a disposable copy of an existing Phase 1A database to head without
losing imported data (reviewer step, not an added automated test), and check fresh migrations. Run the full Docker
suite and `check_docs.py`. The 1.5–2 day estimate exceeds the one-day phase window: record overruns, keep required scope.
No product/order pages, take-down implementation or Tier 2/3 additions.

## Decisions

Existing 21 October choices retained; Chee Long accepted P1–P4/P7 on 22 October 2026. Plan approved 22 October 2026.

| ID | Decision |
|---|---|
| a | One role per account; a seller buying uses a separate customer account |
| b | One trigger-written audit table with bound transaction-local actor/reason context and the shared owner/privilege boundary above |
| c | Rejected seller status remains in the existing schema |
| d | Operator accounts only through management tooling and ignored environment credentials |
| P1–P4, P7 | Status-page-only access, secure audit writes/downstream compatibility, bound context and the 25 October scope/date above |

## Review notes

21 October 2026, cross-plan review (fresh session); findings applied: status triggers fire only on a real status change; actor read with `NULLIF`;
`audit_log` row id as text and an explicit `REVOKE`; `rejected` moved into the `0001` schema; the operator command named;
suspension checked through the `purchasable_product` view.

22 October 2026, fix round: P1–P4/P7 applied; status-only access, audit security/context, locking, verification scope and date corrected; draft retained.

22 October 2026: approved by Chee Long (plan owner) after the fresh Claude Code re-review of the fix round.
