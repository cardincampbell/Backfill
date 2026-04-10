# Backfill Execution Sequencing Plan
**Status:** Working implementation plan  
**Date:** 2026-04-09  
**Purpose:** Translate the platform architecture into a safe execution sequence with clear ownership across the three developers.

## 1. Current Truths

### 1.1 Tenant model today

What exists today:

- `Business` ORM model in [app/models/business.py](/Users/carcam07/Backfill/app/models/business.py#L13)
- physical `businesses` table
- `business_id` on tenant-scoped tables
- `/api/businesses/...` route structure

What that means:

- `Business` is already the tenant boundary
- `Business` is already the top-level customer account
- there is no separate second tenant object to build

Rule:

- do not introduce a parallel second canonical tenant model
- keep `business_id` as the physical storage key for now

### 1.2 Phone stack today

- `1-800-BACKFILL` is the primary conversational command surface
- Retell is the intended conversational runtime for employee/operator voice and text
- Twilio is infrastructure for carrier / trunk / OTP verification concerns
- any direct Twilio coverage-delivery code should be treated as dormant compatibility code unless production usage proves otherwise

### 1.3 Kafka today

Kafka is not the next move.

The current system still needs:

- one canonical campaign aggregate
- one canonical event spine
- one disciplined Postgres worker platform
- one clear Retell cutover

Adding Kafka before those are stable would multiply moving parts without solving the current implementation risk.

## 2. Team Structure

### 2.1 Lead structure

`Codex` is lead architect and integration owner.

Developer 1 is the junior lead:

- capable of owning major backend decisions inside the guardrails
- owns the control plane and user-facing full-stack work
- acts as deputy on rollout sequencing and service-layer discipline

Developer 2 owns the execution platform:

- workers
- orchestration
- projections
- operational backend behavior

### 2.2 Ownership split

#### Lead: shared platform foundation and integration

Own:

- architecture guardrails
- shared model and migration decisions
- canonical naming rules
- event schema rules
- billing invariants
- final integration and review

Primary write scope:

- `alembic/`
- shared model files
- shared event abstractions
- shared billing rules
- architecture and sequencing docs

#### Developer 1: junior lead, control plane, and frontend

Own:

- campaign semantics in service/API contracts
- early event producer rollout from business-critical mutations
- tool registry
- tool validation layer
- Copilot session runtime
- Retell-facing control-plane integration
- all frontend changes

Primary write scope:

- `app/api/routes/*` where campaign/control-plane contracts change
- `app/schemas/*` for campaign and Copilot DTOs
- `app/domain/copilot/` or equivalent modules
- `app/services/*` related to control-plane orchestration
- `web/*`

#### Developer 2: execution platform and worker system

Own:

- Postgres worker platform
- job claiming / retry / idempotency behavior
- campaign dispatch execution
- outreach lifecycle execution
- projection producers
- cost capture pipeline
- billing evaluator after lifecycle trust is established

Primary write scope:

- `app/workers/*`
- `app/services/coverage.py`
- `app/services/delivery.py`
- projection workers
- cost and billing service implementation

### 2.3 Global rules

- Lead owns final say on shared schema and migration order.
- Developer 1 owns all frontend work.
- Developer 1 is not frontend-only.
- Developer 2 does not create independent campaign semantics in parallel with Developer 1.
- No one revives or removes dormant Twilio coverage delivery until Retell cutover is explicit.

## 3. Execution Sequence

The order matters more than the individual design ideas. This plan assumes disciplined sequencing and narrow active workstreams.

## 4. Phase 0: Guardrails First

**Owner:** Lead  
**Support:** Developer 1

Deliverables:

- freeze canonical language: `CoverageCase` is the storage-backed aggregate that will be promoted to campaign semantics
- freeze tenant rule: `Business` is the current tenant object, not a temporary object to be replaced mid-stream
- freeze event rule: `platform_events` becomes canonical as soon as it exists
- freeze telephony rule: Retell is primary for conversational interactions
- freeze worker rule: locking/retries/idempotency are shared platform behavior
- freeze concurrency invariants:
  aggregate versioning / optimistic concurrency
  idempotency keys on every external side effect
  first-confirm-wins semantics backed by database guarantees
  projection freshness targets for engine-critical reads

Exit criteria:

- team agrees on ownership boundaries
- team agrees no dual canonical models will be created
- team agrees no Kafka work starts in this phase

## 5. Phase 1: Canonicalize Campaign Semantics

**Owner:** Developer 1  
**Support:** Lead  
**Developer 2:** read-only on campaign naming until exit

Goal:

- promote `coverage_cases` to campaign semantics in service code and public contracts without creating a second model

Current implementation:

- `CoverageCase` is the real storage-backed aggregate today

Target naming:

- external service and API language should move toward campaign terminology

Not a second model:

- do not create a second independent `CoverageCampaign` model beside `CoverageCase`

Work:

- rename external schema and API language from `case` to `campaign` where safe
- add missing aggregate fields to the existing storage-backed model
- add compatibility aliases instead of parallel implementations
- document one canonical aggregate path through services

Lead responsibilities:

- own migration review
- prevent creation of an independent `CoverageCampaign` ORM or duplicate service model

Exit criteria:

- one aggregate only
- public language can say campaign
- storage still remains `coverage_cases` if physical rename is deferred

## 6. Phase 2: Event Spine

**Owner:** Lead  
**Support:** Developer 1  
**Developer 2:** prepares downstream consumers after schema lands

Goal:

- land `platform_events` and make it canonical before broader feature expansion

Work:

- add `platform_events`
- add event publisher abstraction
- emit events from a small number of critical mutations first
- keep `audit_logs` as compatibility output only

Initial producer set:

- campaign created
- campaign mode changed
- outreach attempt sent
- fill secured
- schedule published

Developer 1 responsibilities:

- wire critical business mutations to the new event publisher

Lead responsibilities:

- define event taxonomy
- define canonical payload shape
- define cutover criteria for removing direct `audit_logs` writes

Exit criteria:

- new critical flows emit `platform_events`
- no new feature writes only `audit_logs`
- feed and webhook follow-on work can depend on the new event spine

## 7. Phase 3: Worker Platform

**Owner:** Developer 2  
**Support:** Lead

Goal:

- build one reusable worker substrate before scattering ad hoc background logic

Work:

- Postgres job table or equivalent shared job substrate
- row claim semantics
- retries
- dead-letter state
- stale-lock recovery
- job error payloads
- explicit tenant context in every job payload
- execution-critical projections needed by the engine:
  candidate eligibility snapshots
  compiled availability windows or equivalent precomputed availability reads
  score snapshots / projections derived from attempt facts

Rules:

- no job-specific custom retry loops
- no implicit tenant inference
- no external side effect without idempotency protection

Exit criteria:

- at least one real campaign job uses shared worker semantics
- the worker platform is reusable, not campaign-specific glue
- engine-critical projections exist early enough that broad outreach execution does not depend forever on expensive runtime joins over authoring tables

## 8. Phase 4: Copilot Tool Framework

**Owner:** Developer 1  
**Support:** Lead

Goal:

- formalize internal tool execution before broad conversational rollout, without coupling Copilot to an unstable coverage execution model

Work:

- tool registry
- validation layer
- `copilot_sessions`
- `copilot_messages`
- `copilot_action_runs`
- narrow first-tool set

First tools:

- `schedule.publish`
- `roster.update_availability`

Coverage-tool rollout rule:

- do not fully ship `coverage.start_campaign` until the outreach logical model and worker-driven execution path are stable
- the framework ships first; the real coverage mutation tool comes later

Frontend in this phase:

- dashboard chat should use the same tool/session pipeline

Exit criteria:

- one shared tool-execution path for dashboard and phone control flows
- no direct LLM-triggered mutation outside the tool path

## 9. Phase 5: Outreach Execution and Logical Model Cleanup

**Owner:** Developer 2  
**Support:** Developer 1 for event and UI contract alignment  
**Lead:** review only

Goal:

- make `outreach_attempts` the logical model, even if compatibility internals remain temporarily split

Current implementation:

- outreach state lives across `coverage_offers` and `coverage_contact_attempts`

Target logical model:

- `outreach_attempts` is the business concept that execution, events, and UI should converge on

Not a second model:

- do not create a permanently parallel second outreach subsystem; unify behavior first and simplify storage later

Work:

- align `coverage_offers` and `coverage_contact_attempts` to one logical outreach state machine
- move dispatch, expiry, recheck, and stop-on-fill behavior onto the worker platform
- enforce candidate dedupe and campaign isolation
- keep dormant direct-Twilio coverage paths untouched unless explicit production evidence requires action

Exit criteria:

- one logical outreach model
- worker-driven campaign execution
- campaign stop conditions are deterministic and observable

## 10. Phase 6: Feed Projections and UI Surfaces

**Backend owner:** Developer 2  
**Frontend owner:** Developer 1  
**Lead:** contract review

Goal:

- surface campaign and platform activity through projections, not raw table reads

Backend work:

- `feed_projections`
- projection workers
- feed query APIs

Frontend work:

- activity feed UI
- campaign status views
- dashboard consumption of campaign/feed APIs

Exit criteria:

- dashboard activity feed is backed by projections
- campaign detail views reflect event-driven state

## 11. Phase 7: Cost Ledger Before Billing Ledger

**Schema and invariant owner:** Lead  
**Implementation owner:** Developer 2  
**Frontend visibility owner:** Developer 1 later

Goal:

- establish cost visibility before monetization logic

Work:

- `cost_ledger_entries`
- provider cost capture around Retell, Twilio Verify, and LLM usage
- campaign-level gross margin visibility

Exit criteria:

- every relevant external call class can produce a cost row
- campaign cost can be computed reliably

## 12. Phase 8: Billing Ledger

**Schema and rules owner:** Lead  
**Implementation owner:** Developer 2  
**UI owner:** Developer 1 when surfaced

Goal:

- layer billing only after campaign lifecycle trust exists

Work:

- `billing_ledger_entries`
- billable fill evaluator
- monthly cap enforcement
- void / capped event paths

Exit criteria:

- billable-fill determination is deterministic
- cap logic is visible and testable

## 13. Phase 9: Retell Cutover Hardening

**Owner:** Developer 1  
**Support:** Developer 2  
**Lead:** signoff required

Goal:

- make provider ownership explicit and remove ambiguity

Interaction classes:

- OTP verification
- inbound conversational phone
- outbound conversational phone
- inbound conversational text
- outbound conversational text

Rules:

- one primary provider path per interaction class
- legacy paths remain dark behind config
- removal of dormant legacy code happens only after explicit cutover verification

Exit criteria:

- no half-live provider boundary
- production owner is clear for each interaction class

## 14. Frontend Ownership

All frontend changes belong to Developer 1.

That includes:

- dashboard chat
- feed UI
- campaign status UI
- any frontend wiring to Copilot or campaign APIs

Developer 1 should be treated as a junior lead full-stack owner, not a frontend-only implementer.

## 15. Kafka Readiness Gates

Kafka becomes worth serious consideration only when the Postgres event/worker model is demonstrably insufficient after tuning and operational discipline.

Do not adopt Kafka because the architecture looks more “real.” Adopt it when the current system can no longer meet required behavior cleanly.

### 15.1 Minimum conditions

Consider Kafka only when all of the following are true:

- `platform_events` is already canonical
- campaign semantics are stable
- worker semantics are disciplined
- provider ownership is no longer ambiguous
- the team can operate another piece of infrastructure reliably

### 15.2 Practical trigger measures

Kafka is justified when several of these are true at the same time for sustained production traffic:

- Postgres-backed job pickup latency is persistently above acceptable SLO even after query/index/partition tuning
- event write volume causes unacceptable contention, replication lag, or operational pain in Postgres
- multiple independent consumers need durable replay from the same event stream
- consumer groups need to scale independently of the monolith and projections
- backfills and reprocessing become a routine operational need rather than an occasional admin task
- more than one separately deployed service depends on the same event stream as a first-class contract

### 15.3 Simple rule of thumb

Do not move to Kafka because one queue is slow once.

Do move when:

- Postgres is now the wrong primitive for both the event stream and the worker backlog
- replayable multi-consumer streaming is a repeated need
- the operational cost of not having Kafka is higher than the cost of running it

## 16. Near-Term PR Order

Recommended order:

1. Lead: shared guardrail doc updates and migration rules
2. Developer 1: campaign semantics cleanup branch
3. Lead: `platform_events` schema and publisher abstraction
4. Developer 1: wire first critical event producers
5. Developer 2: worker platform
6. Developer 1: tool registry and Copilot session runtime
7. Developer 2: outreach execution on worker platform
8. Developer 2: feed projection producers
9. Developer 1: feed and campaign UI
10. Lead + Developer 2: cost ledger
11. Lead + Developer 2: billing ledger
12. Developer 1: Retell cutover hardening and final user-facing control plane polish

## 17. Non-Negotiables

- No dual canonical model for tenant or campaign.
- No Kafka before the current primitives are proven insufficient.
- No ad hoc worker semantics.
- No async job without explicit tenant context.
- No direct LLM mutation path.
- No accidental half-live Twilio / Retell split.
