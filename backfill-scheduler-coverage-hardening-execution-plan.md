# Backfill Scheduler & Coverage Hardening Execution Plan
**Status:** Proposed execution plan  
**Date:** 2026-04-17  
**Purpose:** Harden the scheduler and coverage engine after the recent callout, outbound delivery, reassignment, and board-state incidents.

## 1. Problem Statement

Backfill's core callout-to-coverage flow is working, but it is still too brittle operationally.

Recent failures exposed the same structural weaknesses repeatedly:

- provider callback shape drift
- outbound delivery failures that required log-forensics to understand
- duplicate processing across callback lifecycle events
- board and schedule projections drifting from backend truth
- ranking and candidate exclusion behavior being hard to explain
- worker/runtime failures blocking unrelated work

The goal of this plan is to move the scheduler and coverage engine from "working with supervision" to "operationally durable."

## 2. Goals

- Make the coverage engine replayable, observable, and recoverable.
- Reduce duplicated projection logic across scheduler surfaces.
- Make provider contracts explicit and versioned.
- Decompose the coverage runtime so new policy work does not keep breaking core execution.
- Make candidate ranking explainable to operators.
- Detect invalid or legacy data before it causes runtime misses.
- Close the optional operator/manual-control gaps around manager approval and intervention for flagged cases only.

## 3. Non-Goals

- This plan does not redesign the entire scheduling domain from scratch.
- This plan does not replace the coverage engine with an LLM-driven runtime.
- This plan does not make Backfill the payroll or compliance engine of record.
- This plan does not implement labor-rule ranking directly; that is covered by the separate labor-rules spec.

## 4. Current Failure Surfaces

The most important failure surfaces in the current repo are:

1. **Replay and dead-letter recovery are too weak**
   - failures still require direct inspection of callback rows, outbox rows, or provider payloads
   - there is no first-class operator path to replay a failed callback or a stuck offer delivery

2. **Projection logic is duplicated**
   - scheduler board and employee schedule views both reconstruct published-amendment and historical-artifact behavior
   - duplicated display logic is a regression source

3. **Retell contract drift is still too easy**
   - callback key naming, prompt changes, and dynamic variable shape have all broken execution recently
   - the system is now more tolerant, but not yet formally versioned

4. **Coverage runtime is too concentrated**
   - candidate selection
   - scoring
   - standby progression
   - offer issuance
   - response handling
   - reassignment
   - republish behavior
   all still live too close together

5. **Ranking is not explainable enough**
   - score composition exists
   - but the policy boundary is not explicit enough for future overtime/state rules, operator review, or auditability

6. **Legacy or inconsistent data can still poison execution**
   - missing availability
   - invalid phone numbers
   - stale projection snapshots
   - inconsistent shift amendment metadata
   - mismatched case/offer/assignment states

7. **Operator control is incomplete**
   - `requires_manager_approval` exists in the model
   - but the end-to-end workflow is not yet first-class
   - this should remain an optional gated mode, not the default coverage path

8. **Test coverage is still too unit-heavy**
   - recent bugs were integration bugs, not isolated unit bugs

9. **Operational visibility is too weak**
   - core funnel health needs first-class metrics and alerts

10. **One-shift-one-worker semantics are not fully enforced**
   - compatibility baggage like `seats_requested` / `seats_filled` still leaks into coverage behavior

## 5. Execution Priorities

Execution should happen in this order:

1. Replay and dead-letter tooling
2. Data invariants and backfills
3. Observability and alerts
4. Projection unification
5. Retell contract versioning
6. Coverage state contract and service decomposition
7. Candidate policy engine extraction
8. Manager approval and manual takeover
9. Scenario harness
10. Shift unit-of-work cleanup

That order is intentionally aligned to the rollout phases below so the team is not optimizing against two different sequences.

## 6. Workstream A — Replay, Recovery, and Dead-Letter Tooling

### Why

When a callback or delivery fails, the system should provide a controlled replay path. Right now failures still require direct database inspection or code-level tracing.

### Deliverables

- internal/admin capability to:
  - replay a provider callback row
  - replay a pending or failed outbox event
  - cancel an outbox event safely
  - re-drive a coverage case from its current state
- explicit replay modes:
  - `dry_run`
  - `reprocess_if_preconditions_match`
  - `force_requeue`
- aggregate-version and idempotency protections:
  - replay must check current aggregate state before side effects
  - replayed work must reuse or validate idempotency keys where provider sends are involved
- replay safety rules by event type:
  - provider callback replay
  - outbox event replay
  - coverage case re-drive
- dead-letter inspection payloads that show:
  - aggregate id
  - provider
  - terminal error
  - retry history
  - normalized linkage keys

### Replay Contract

Replay must not mean "blindly run the side effect again."

Use this contract:

- `dry_run`
  - recomputes what would happen
  - writes no state
  - emits no provider side effects
- `reprocess_if_preconditions_match`
  - allowed only if the current aggregate state still matches the replay preconditions
  - must fail closed if the case, offer, assignment, or callback outcome has already advanced
- `force_requeue`
  - creates a new re-drive attempt for operational recovery
  - must never bypass idempotency-key or aggregate-version checks
  - must never re-run already-terminal reassignment logic in place

Event-specific safety rules:

- callback replay:
  - safe only if normalized callback processing has not already advanced the aggregate beyond the replay target
- outbox replay:
  - safe only if the offer is still actionable and no newer successful provider send exists for the same aggregate/idempotency key
- coverage case re-drive:
  - safe only for non-terminal cases unless the operation is `dry_run`
  - filled, exhausted, cancelled, and failed cases may be inspected, but not blindly re-driven

### Repo Touchpoints

- [app/services/provider_callbacks.py](/Users/carcam07/Backfill/app/services/provider_callbacks.py)
- [app/services/delivery.py](/Users/carcam07/Backfill/app/services/delivery.py)
- [app/services/webhooks.py](/Users/carcam07/Backfill/app/services/webhooks.py)
- [app/services/worker_runtime.py](/Users/carcam07/Backfill/app/services/worker_runtime.py)

### Exit Criteria

- an operator can replay a failed Retell callback without database writes
- an operator can replay a failed/stuck coverage offer outbox event
- replay behavior is deterministic and cannot duplicate provider sends or re-run completed reassignment side effects
- dead-letter payloads are sufficient to diagnose most failures without raw DB inspection

## 7. Workstream B — Unified Shift Projection Layer

### Why

Published amendments, callouts, historical reassignment artifacts, and cancelled-shift display behavior are being reconstructed in multiple services.

That logic should live in one place and feed:

- workspace board
- employee schedule links
- any future feed, export, or audit projection

### Deliverables

- shared projection service for:
  - canonical projection payload
  - current visible shift state
  - historical artifacts
  - schedule-break state
  - amendment reason/action
  - renderable employee ownership
- explicit cache/invalidation ownership
- mutation flows emit projection refresh or invalidation events when visible state changes
- remove duplicated logic from board and employee schedule projections

### Projection Contract

The shared projection layer must define one canonical payload shape used by every scheduler-facing view.

Minimum contract:

```json
{
  "shift_id": "uuid",
  "projection_version": "v1",
  "generated_at": "timestamp",
  "display_state": {},
  "current_owner": {},
  "published_amendment": {},
  "historical_artifacts": [],
  "coverage_summary": {},
  "actionability": {}
}
```

Projection ownership rules:

- one service owns projection assembly
- mutation flows that change renderable shift state must emit projection refresh/invalidation events
- board and employee schedule consumers must not reconstruct amendment logic independently

### Repo Touchpoints

- [app/services/workspace_board.py](/Users/carcam07/Backfill/app/services/workspace_board.py)
- [app/services/employee_schedule_links.py](/Users/carcam07/Backfill/app/services/employee_schedule_links.py)
- [app/services/shift_assignments.py](/Users/carcam07/Backfill/app/services/shift_assignments.py)

### Exit Criteria

- the board and employee schedule views use the same underlying projection logic
- there is a single canonical answer to:
  - who currently owns the shift
  - whether the shift is a live callout
  - whether a historical artifact should be shown

## 8. Workstream C — Retell Contract Versioning

### Why

Recent issues were repeatedly caused by drift in:

- callback key names
- outbound metadata fields
- dynamic variable types
- prompt/agent assumptions

Tolerance is good. Unversioned contracts are not.

### Deliverables

- versioned outbound contract for:
  - metadata
  - dynamic variables
  - normalized callback payload
- normalized callback summary persisted per conversation
- explicit contract documentation for inbound and outbound Retell flows
- compatibility layer for known legacy key shapes

### Repo Touchpoints

- [app/services/retell_workflow.py](/Users/carcam07/Backfill/app/services/retell_workflow.py)
- [app/services/delivery.py](/Users/carcam07/Backfill/app/services/delivery.py)
- [app/services/retell.py](/Users/carcam07/Backfill/app/services/retell.py)
- [app/services/provider_callbacks.py](/Users/carcam07/Backfill/app/services/provider_callbacks.py)

### Exit Criteria

- every outbound call stores a normalized linkage block:
  - `offer_id`
  - `coverage_case_id`
  - `shift_id`
  - `employee_id`
  - `contract_version`
- every completed Retell callback produces a normalized intent payload before business logic runs

## 9. Workstream D — Coverage Runtime Decomposition

### Why

The current coverage engine still owns too many responsibilities in one service. That increases blast radius and makes policy work harder.

### Authoritative State Contract

The refactor must start from one canonical transition map. Splitting services without this will only spread implicit coupling around.

Coverage case state contract:

- `queued`
  - case exists but no active dispatch is in flight
- `approval_pending`
  - optional state used only when `requires_manager_approval = true`
  - case is blocked on manager approval before dispatch
- `running`
  - at least one actionable offer, standby activation, or active dispatch attempt exists
- `filled`
  - one offer has been accepted and the shift has been reassigned or filled
- `exhausted`
  - no further eligible progression remains
- `cancelled`
  - the case was intentionally stopped or the shift is no longer actionable
- `failed`
  - runtime failed in a way that requires operational attention

Offer state contract:

- `pending`
- `delivered`
- terminal:
  - `accepted`
  - `declined`
  - `expired`
  - `cancelled`
  - `failed`

Transition rules:

- only one offer may produce the terminal fill transition for a case
- once reassignment/fill completes, sibling actionable offers must be cancelled idempotently
- manager approval must gate dispatch before `running`
- manual takeover must freeze or redirect automation explicitly, not coexist ambiguously with automatic responder logic
- responder logic owns acceptance, sibling-offer cancellation, reassignment completion, and terminal-case closure

Default path:

- a normal coverage case should move through the automatic path without entering `approval_pending`
- `approval_pending` exists only for flagged shifts, roles, or locations where approval is explicitly required

### Target Split

1. **Planner**
   - candidate collection
   - availability/conflict filtering
   - policy scoring
   - phase decisioning

2. **Dispatcher**
   - offer issuance
   - standby activation
   - outbox event creation
   - expiry advancement

3. **Responder**
   - accept/decline/no-answer processing
   - shift reassignment
   - sibling offer cancellation
   - republish behavior

### Repo Touchpoints

- [app/services/coverage.py](/Users/carcam07/Backfill/app/services/coverage.py)
- [app/services/coverage_runtime.py](/Users/carcam07/Backfill/app/services/coverage_runtime.py)
- [app/services/runtime_orchestration.py](/Users/carcam07/Backfill/app/services/runtime_orchestration.py)

### Exit Criteria

- candidate planning can be tested without offer issuance
- response handling can be tested without planner concerns
- standby behavior is isolated behind a narrower contract
- the coverage state machine is defined once and enforced across planner, dispatcher, and responder boundaries

## 10. Workstream E — Candidate Policy Engine

### Why

Coverage ranking is currently built from multiple good inputs, but the policy boundary is still too implicit.

This becomes more important once labor rules, travel rules, cross-location rules, and business-specific preferences expand.

### Deliverables

- dedicated policy engine that returns:
  - candidate status
  - total score
  - explanation object
  - hard blocks
  - soft multipliers
- explanation object persisted to candidate scoring factors
- versioned policy metadata persisted with every explanation
- explicit separation between:
  - eligibility gates
  - outreach guardrails
  - ranking multipliers

### Candidate Explanation Shape

Minimum shape:

```json
{
  "policy_version": "coverage_policy_v1",
  "snapshot_generated_at": "timestamp",
  "inputs_version": "runtime_projection_snapshot_v1",
  "eligibility": {},
  "availability": {},
  "conflicts": {},
  "cooldowns": {},
  "reliability": {},
  "location_affinity": {},
  "overtime_projection": {},
  "final_score": 0.0,
  "hard_blocked": false,
  "reason_codes": []
}
```

### Repo Touchpoints

- [app/services/coverage.py](/Users/carcam07/Backfill/app/services/coverage.py)
- [app/services/runtime_projections.py](/Users/carcam07/Backfill/app/services/runtime_projections.py)

### Exit Criteria

- operators can answer "why did Backfill pick or skip this person?"
- future labor-rule ranking plugs into a stable policy surface instead of ad hoc scoring code
- policy explanations are traceable to the exact policy and snapshot version that generated them

## 11. Workstream F — Data Invariants and Legacy Backfills

### Why

Some runtime failures should have been prevented by earlier data hygiene checks.

### Deliverables

- one-time backfills where needed
- recurring invariant checks for:
  - employees without recurring availability
  - invalid or missing `phone_e164`
  - missing timezone / location eligibility data
  - malformed published amendment metadata
  - coverage cases whose status disagrees with offers/assignments
  - stale score snapshot ratios above threshold

### Repo Touchpoints

- [app/services/workforce.py](/Users/carcam07/Backfill/app/services/workforce.py)
- [app/services/scheduler_sync.py](/Users/carcam07/Backfill/app/services/scheduler_sync.py)
- [app/services/runtime_projections.py](/Users/carcam07/Backfill/app/services/runtime_projections.py)

### Exit Criteria

- nightly invariant job exists
- high-risk invariant failures page or alert cleanly
- legacy employee records are not silently skipped due to missing default setup

## 12. Workstream G — Manager Approval and Manual Takeover

### Why

The data model already acknowledges manager approval, but the operator workflow is not explicit enough yet.

This is an optional safety mode, not the default runtime model.

### Deliverables

- clear manager-approval state machine for coverage cases
- manual takeover actions:
  - approve
  - reject
  - manually assign
  - stop automation
  - resume automation
- board/API visibility for cases waiting on approval

### Repo Touchpoints

- [app/models/scheduling.py](/Users/carcam07/Backfill/app/models/scheduling.py)
- [app/models/coverage.py](/Users/carcam07/Backfill/app/models/coverage.py)
- [app/services/coverage.py](/Users/carcam07/Backfill/app/services/coverage.py)
- scheduler-facing routes and board projections

### Exit Criteria

- a manager can intentionally intervene without bypassing or corrupting the automation state
- "requires manager approval" is operational, not just stored
- approval mode is off by default and only activates for explicitly flagged shifts, roles, or locations

## 13. Workstream H — Scenario Harness

### Why

Recent bugs were end-to-end flow bugs. Unit tests alone will not keep this stable.

### Deliverables

Scenario tests for:

- callout -> queued case -> outbound offer -> accept -> reassignment -> republish
- callout -> decline -> next candidate
- callout -> no answer -> expiry -> next offer
- duplicate `call_ended` / `call_analyzed`
- blocked runtime projections
- stale or failed delivery retry path
- standby accept then later promotion
- draft-conflict republish skip

### Repo Touchpoints

- [tests/test_coverage.py](/Users/carcam07/Backfill/tests/test_coverage.py)
- [tests/test_coverage_runtime.py](/Users/carcam07/Backfill/tests/test_coverage_runtime.py)
- [tests/test_runtime_orchestration.py](/Users/carcam07/Backfill/tests/test_runtime_orchestration.py)
- [tests/test_retell_workflow.py](/Users/carcam07/Backfill/tests/test_retell_workflow.py)
- [tests/test_workspace_board.py](/Users/carcam07/Backfill/tests/test_workspace_board.py)

### Exit Criteria

- there is at least one deterministic integration test for every recent incident class

## 14. Workstream I — Observability and Alerts

### Why

A coverage engine is an operational funnel. It needs funnel-level monitoring.

### Deliverables

Metrics and alerts around:

- queued cases not dispatched within threshold
- pending outbox events older than threshold
- callback dead-letter counts
- exhausted cases with zero candidates
- offer acceptance rate by role/location
- fill time by role/location
- republish success vs skip rate
- stale runtime projection ratio

### Exit Criteria

- on-call or operators can detect a broken flow before a customer reports it

## 15. Workstream J — Shift Unit-of-Work Cleanup

### Why

The coverage model is cleanest when one shift equals one worker. Compatibility fields still make this blurry.

### Deliverables

- decide and document whether Backfill is:
  - fully one-shift-one-worker
  - or supporting true multi-seat coverage
- remove or isolate compatibility semantics that still leak into the runtime

### Repo Touchpoints

- [app/models/scheduling.py](/Users/carcam07/Backfill/app/models/scheduling.py)
- [app/services/coverage.py](/Users/carcam07/Backfill/app/services/coverage.py)
- scheduler sync and publish flows

### Exit Criteria

- the runtime and UI both share the same unit-of-work semantics

## 16. Recommended Rollout Sequence

### Phase 1 — Operational Safety

- replay/dead-letter tooling
- invariant checks
- observability and alerts

### Phase 2 — State Consistency

- unified shift projection layer
- Retell contract versioning

### Phase 3 — Runtime Refactor

- canonical coverage state machine
- coverage runtime decomposition
- candidate policy engine extraction

### Phase 4 — Operator Maturity

- manager approval and manual takeover
- scenario harness completion

### Phase 5 — Domain Cleanup

- shift unit-of-work cleanup
- tighter alignment with labor-rules ranking once that project lands

## 17. Success Criteria

This plan is successful when:

- provider or outbox failures can be replayed without database surgery
- scheduler board and employee schedule views cannot disagree about the same shift state
- provider payload drift no longer silently breaks reassignment
- candidate selection is explainable and reviewable
- stale or malformed data is caught before runtime dispatch
- operators can intervene intentionally without corrupting automation state
- end-to-end incident classes are covered by scenario tests
- operational metrics surface broken flows before customers do

## 18. Final Decision

Backfill does not need a new scheduler architecture right now. It needs hardening around execution, projection, observability, and operator control.

The highest-value work is:

1. recovery tooling
2. invariants and observability
3. projection unification
4. explicit provider contracts
5. canonical coverage state machine and runtime decomposition

That is the shortest path from a promising system to a durable one.
