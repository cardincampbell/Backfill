# Backfill Backend Platform Architecture
**Status:** Proposed v1 architecture  
**Date:** 2026-04-09  
**Applies to:** FastAPI monolith launch phase

## 1. Purpose

Backfill is not a scheduler with extra automation. It is a coverage engine with a free scheduling layer attached so the engine has the workforce, role, availability, and labor state it needs to act.

This document defines the canonical backend architecture for that product:

- The Copilot is the primary control plane.
- The coverage campaign is the primary unit of work.
- Events are the primary record of system behavior.
- Cost and billing are first-class platform concerns.
- Launch stays monolithic and Postgres-first, but the seams for future extraction are designed now.

Current codebase note:

- `Business` is the top-level tenant and customer account in the current codebase.
- `CoverageCase` is the closest existing object to the target `CoverageCampaign`.
- `AuditLog` and `OutboxEvent` are useful launch primitives, but they are not yet the full event system this product needs.

## 2. Architectural Decisions

### 2.1 Launch shape

- One FastAPI application.
- One Postgres database via Supabase.
- One worker process for async jobs.
- Postgres-backed queues and timers.
- Redis is already an accepted launch dependency for shared state such as rate limiting and other short-lived coordination where it is already part of the stack.
- Supabase Realtime for feed fanout.
- No Kafka and no service mesh at launch.

### 2.2 Control plane

- The Copilot is the action surface for operators.
- The dashboard is primarily read/visibility plus exception handling.
- All write capabilities exposed to the Copilot must exist as internal application tools with explicit validation and side effects.
- `1-800-BACKFILL` is the primary employee-facing and operator-facing command surface for live callouts and conversational commands.

### 2.3 Revenue object

- `coverage_campaign` is the central aggregate.
- Billing, eventing, outreach, operator visibility, and cost tracking all hang off the campaign.
- A shift may have multiple campaigns over time, but a campaign always belongs to exactly one shift.

### 2.4 Safety model

- LLMs resolve intent and propose actions.
- Application services validate authorization and preconditions.
- Execution happens only through internal tool handlers.
- Every state change emits an event.

### 2.5 Migration discipline

- Do not allow two long-lived canonical models for the same concept.
- Compatibility layers are allowed only as temporary facades with explicit cutover criteria.
- Every compatibility layer must have an owner, an exit condition, and a removal phase in the migration plan.

## 3. System Overview

```text
Channel Input
  -> Channel Adapter
  -> Normalized Message
  -> Copilot Session Loader
  -> Intent Resolver + Tool Planner
  -> Tool Validation Layer
  -> Application Service Execution
  -> Event Emission
  -> Postgres Commit
  -> Realtime / Async Consumers / Feed Projection
  -> Channel-Specific Response Adapter
```

```text
Employee / Operator
  -> calls or texts 1-800-BACKFILL
  -> Twilio carrier/trunk layer
  -> Retell AI conversational runtime
  -> Backfill channel adapter
  -> Copilot / coverage engine / internal tools
```

```text
Callout / Shift Change
  -> Coverage Campaign Service
  -> Candidate Snapshot + PoA Scoring
  -> Outreach Plan
  -> Job Queue / Timers
  -> Twilio / Retell Adapters
  -> Responses / Webhooks
  -> Fill Decision
  -> Assignment Update
  -> Billing + Cost Ledger
  -> Campaign Close
```

## 4. Canonical Domain Model

### 4.1 Core hierarchy

```text
Business
  -> Location
  -> Role
  -> Employee
  -> Operator / Membership

Schedule
  -> Shift
  -> ShiftAssignment
  -> Callout

CoverageCampaign
  -> CampaignRound
  -> CampaignCandidate
  -> OutreachAttempt
  -> FillDecision
  -> CostLedgerEntry
  -> BillingLedgerEntry

CopilotSession
  -> CopilotMessage
  -> CopilotActionRun

PlatformEvent
  -> FeedProjection
```

### 4.2 Existing-to-target mapping

Use these mappings to evolve the current schema without a rewrite:

| Current | Target concept | Direction |
| --- | --- | --- |
| `businesses` | top-level tenant / customer account | keep as canonical tenant object |
| `coverage_cases` | `coverage_campaigns` | promote as canonical aggregate |
| `coverage_case_runs` | `campaign_rounds` | keep semantics, rename later |
| `coverage_candidates` | `campaign_candidates` | keep, expand scoring payload |
| `coverage_offers` + `coverage_contact_attempts` | `outreach_attempts` | merge mentally now, optionally physically later |
| `audit_logs` | `platform_events` / feed projection seed | replace for system-wide event model |
| `outbox_events` | external delivery outbox | keep |

Naming guardrails:

- Current implementation: `coverage_cases`, `coverage_case_runs`, `coverage_candidates`, `coverage_offers`, and `coverage_contact_attempts` are the real storage-backed models that exist today.
- Target naming: `coverage_campaigns`, `campaign_rounds`, `campaign_candidates`, and `outreach_attempts` describe the desired domain language and target logical model.
- Not a second model: these names must not be implemented as parallel canonical models while the current storage-backed models are still active. Compatibility aliases are allowed; dual canonical models are not.

### 4.3 Required schema additions

The current schema is close enough to evolve. Add the following tables and columns before major Copilot expansion.

Storage naming note:

- In the current repo, prefer physical `business_id` columns for new tables so migrations stay consistent with existing schema and RLS policies.
- Treat `Business` as the canonical tenant object. Use `tenant` as the generic explanatory term when needed.

#### `callouts`

Represents the trigger that caused coverage to start.

Key fields:

- `id`
- `business_id`
- `location_id`
- `shift_id`
- `reported_by_employee_id`
- `reported_by_operator_id`
- `source_channel` (`sms`, `voice`, `dashboard`, `api`)
- `reason_code`
- `notes`
- `reported_at`
- `resolved_at`
- `deleted_at`

#### `coverage_campaigns`

Canonical campaign aggregate. Can be implemented initially as an evolved `coverage_cases` table.

Current implementation:

- today this is the existing `coverage_cases` aggregate, promoted into campaign semantics

Not a second model:

- do not build a separate independent `CoverageCampaign` ORM or service aggregate while `CoverageCase` remains the storage-backed source of truth

Key fields:

- `id`
- `business_id`
- `location_id`
- `shift_id`
- `callout_id`
- `status` (`created`, `scoring`, `outreach_active`, `filled`, `escalated`, `exhausted`, `cancelled`, `closed`)
- `mode` (`standard`, `compressed`, `blast`)
- `trigger_source`
- `opened_at`
- `closed_at`
- `filled_at`
- `filled_by_employee_id`
- `fill_source` (`backfill`, `manual_override`, `cancelled`)
- `campaign_metadata`
- `deleted_at`

#### `campaign_rounds`

Each mode transition or strategy step gets a round. The existing `coverage_case_runs` model is a strong base.

Key fields:

- `id`
- `coverage_campaign_id`
- `round_no`
- `mode`
- `strategy`
- `started_at`
- `finished_at`
- `candidate_count`
- `dispatched_count`
- `round_metadata`

#### `campaign_candidates`

Candidate snapshot at scoring time. Existing `coverage_candidates` is a strong base.

Add or ensure:

- `poa_score`
- `scoring_version`
- `eligibility_snapshot`
- `labor_rule_snapshot`
- `distance_miles`
- `historical_accept_rate`
- `last_worked_at`
- `deprioritized_reason`

#### `outreach_attempts`

Make per-candidate outreach state explicit even if current `coverage_offers` and `coverage_contact_attempts` remain separate internally.

Current implementation:

- today outreach state is split across `coverage_offers` and `coverage_contact_attempts`

Target logical model:

- treat `outreach_attempts` as the unified business concept for execution, visibility, and eventing

Not a second model:

- do not create a permanently parallel second outreach system; unify behavior first, then simplify storage when it is safe

Key fields:

- `id`
- `coverage_campaign_id`
- `campaign_round_id`
- `campaign_candidate_id`
- `employee_id`
- `channel` (`sms`, `voice`)
- `status` (`queued`, `sent`, `delivered`, `awaiting_response`, `accepted`, `declined`, `no_response`, `no_answer`, `expired`, `cancelled`, `failed`, `exhausted`)
- `provider`
- `provider_request_id`
- `provider_message_id`
- `idempotency_key`
- `requested_at`
- `sent_at`
- `delivered_at`
- `responded_at`
- `expires_at`
- `cost_cents`
- `attempt_metadata`

#### `platform_events`

Append-only immutable event log. This is the system record. `audit_logs` can continue temporarily as a user-facing subset or compatibility projection.

Key fields:

- `id`
- `event_type`
- `occurred_at`
- `business_id`
- `location_id`
- `actor_type`
- `actor_id`
- `actor_membership_id`
- `entity_type`
- `entity_id`
- `campaign_id`
- `shift_id`
- `session_id`
- `trace_id`
- `channel`
- `payload`
- `metadata`

Indexes:

- `(business_id, occurred_at desc)`
- `(location_id, occurred_at desc)`
- `(entity_type, entity_id, occurred_at desc)`
- `(campaign_id, occurred_at asc)`
- `(event_type, occurred_at desc)`

#### `feed_projections`

Denormalized cards for low-latency dashboard reads.

Key fields:

- `id`
- `business_id`
- `location_id`
- `projection_type` (`location_feed`, `campaign_feed`)
- `entity_type`
- `entity_id`
- `group_key`
- `headline`
- `summary`
- `status`
- `importance`
- `starts_at`
- `occurred_at`
- `payload`

#### `copilot_sessions`

Server-side multi-turn state, channel-independent.

Key fields:

- `id`
- `business_id`
- `location_id`
- `operator_user_id`
- `channel_last_seen`
- `intent_family`
- `state` (`active`, `awaiting_confirmation`, `awaiting_clarification`, `completed`, `expired`)
- `context_profile`
- `working_memory`
- `expires_at`
- `last_message_at`

#### `copilot_messages`

- `id`
- `copilot_session_id`
- `direction` (`inbound`, `outbound`)
- `normalized_channel`
- `raw_text`
- `normalized_text`
- `message_metadata`
- `created_at`

#### `copilot_action_runs`

One record per planned or executed tool action.

- `id`
- `copilot_session_id`
- `tool_name`
- `status` (`planned`, `validated`, `executed`, `failed`, `cancelled`)
- `input_payload`
- `validation_result`
- `result_payload`
- `error_payload`
- `started_at`
- `finished_at`

#### `cost_ledger_entries`

Per-external-call cost record.

- `id`
- `coverage_campaign_id`
- `provider` (`twilio`, `retell`, `openai`, `anthropic`)
- `product` (`sms`, `voice`, `voice_ai`, `llm_input_tokens`, `llm_output_tokens`)
- `reference_type`
- `reference_id`
- `quantity`
- `unit_cost_micros`
- `total_cost_micros`
- `cost_metadata`
- `occurred_at`

#### `billing_ledger_entries`

- `id`
- `coverage_campaign_id`
- `business_id`
- `location_id`
- `shift_id`
- `employee_id`
- `billing_event_type` (`fill_charged`, `fill_capped`, `fill_voided`)
- `billing_cycle_start`
- `amount_cents`
- `cap_applied`
- `occurred_at`
- `billing_metadata`

### 4.4 Soft delete policy

Add `deleted_at` to mutable business entities:

- employees
- locations
- shifts
- callouts
- coverage_campaigns
- outreach_attempts
- tool/session records where recovery matters

Do not soft-delete:

- platform events
- cost ledger entries
- billing ledger entries

## 5. Copilot Architecture

### 5.1 Runtime contract

The Copilot is an agent with tool use, not a free-form assistant with database access.

Execution flow:

1. Normalize inbound channel payload into a `NormalizedMessage`.
2. Load or create `copilot_session`.
3. Resolve intent family.
4. Assemble only the context needed for that family.
5. Plan tool calls.
6. Validate authorization and preconditions in application code.
7. Execute tool handlers transactionally.
8. Emit events.
9. Render a channel-aware response.

Primary channel note:

- Employees use `1-800-BACKFILL` to call out via voice or text.
- Operators can also use that same number for conversational commands and status checks.
- The dashboard remains important, but the phone number is the highest-priority real-time interaction surface.

### 5.2 Tool registry

Every operator capability must exist in a registry definition. Code-first registry is preferred at launch, with optional DB persistence later for admin tooling and docs.

Suggested Python shape:

```python
@dataclass(frozen=True)
class ToolDefinition:
    tool_name: str
    description: str
    parameters_schema: dict
    preconditions: tuple[str, ...]
    side_effects: tuple[str, ...]
    required_roles: tuple[str, ...]
    context_profile: str
```

Representative tools:

- `schedule.publish`
- `schedule.autofix`
- `schedule.open_shift`
- `coverage.start_campaign`
- `coverage.cancel_campaign`
- `coverage.override_fill`
- `coverage.expand_to_cross_location`
- `roster.add_employee`
- `roster.update_availability`
- `labor.override_rule`
- `employee.send_invite`

Rules:

- Tool definitions are static and versioned.
- Tool execution handlers live in application services, not prompt text.
- Preconditions are enforced in code before mutation.
- Failed validation returns why it failed and what can be done next.

### 5.3 Context profiles

Do not hydrate full org state into every prompt. Build intent-family context profiles.

Profiles:

- `scheduling`
- `coverage`
- `roster`
- `analytics`
- `account`

Example `coverage` context:

- operator identity and permissions
- current location
- active campaigns for that location
- target shift summary
- top candidate summary
- recent relevant events
- policy flags and labor-rule blockers

Example `scheduling` context:

- target week
- draft vs published status
- open shifts count
- unresolved labor conflicts
- last publish attempt

### 5.4 Session state

Never depend on prompt history alone.

The session `working_memory` should store:

- inferred target entities
- last tool plan
- unresolved blockers
- pending confirmations
- ordered list of fix options presented to operator
- a compact conversational summary

TTL:

- default 15 minutes inactivity for active sessions
- longer retention for completed summaries if needed for follow-up

### 5.5 Channel abstraction

All channels normalize to the same envelope:

```python
@dataclass
class NormalizedMessage:
    channel: str
    external_message_id: str
    external_conversation_id: str | None
    sender_type: str
    sender_id: str | None
    business_id: UUID | None
    location_id: UUID | None
    text: str
    received_at: datetime
    metadata: dict
```

Adapters:

- `RetellPhoneAdapter`
- `DashboardChatAdapter`

The Copilot never branches on raw provider payload shape.

Transport clarification:

- The operator/employee experience should be modeled as Retell-mediated conversation, not Twilio-mediated conversation.
- Twilio exists underneath the branded number as carrier, SIP trunk, and OTP infrastructure.
- Retell owns conversational voice and text behavior for the `1-800-BACKFILL` surface.

### 5.6 LLM boundaries

Allowed:

- intent classification
- slot filling
- clarification question generation
- tool sequencing proposals
- natural language confirmations and explanations

Not allowed:

- authorization decisions
- labor-rule enforcement
- direct SQL generation for execution
- mutation without a validated tool handler

## 6. Coverage Engine

### 6.1 Campaign lifecycle

```text
callout.received
  -> coverage.campaign.created
  -> coverage.scoring.started
  -> coverage.scoring.completed
  -> coverage.outreach.plan_created
  -> coverage.outreach.attempt_queued
  -> coverage.outreach.sent
  -> coverage.outreach.response_received
  -> coverage.fill.secured | coverage.campaign.exhausted | coverage.campaign.escalated
  -> coverage.campaign.closed
```

Every transition emits an event and updates the campaign aggregate.

### 6.2 Modes

Mode selection is automatic from `time_to_shift`.

- `standard`: 12+ hours
- `compressed`: 4-12 hours
- `blast`: under 4 hours

Implementation rule:

- Store the active mode on the campaign.
- Re-evaluate mode at every round boundary and on timer ticks.
- Emit `coverage.campaign.mode_changed` on escalation.

### 6.3 Candidate eligibility

Eligibility is deterministic and code-based.

Minimum checks:

- correct role/skill/certification
- no conflicting assignment
- available for full shift window
- location eligible
- not disqualified by labor rules
- not already contacted for this campaign
- not locked by another active campaign if exclusion policy applies

### 6.4 PoA scoring

PoA is the sort order for eligible candidates, not the eligibility gate itself.

Inputs:

- availability fit
- historical acceptance rate
- historical response speed
- recency since last shift
- role proficiency
- primary-location affinity
- location proximity
- overtime proximity
- operator preference rank
- time-of-day / day-of-week patterns

Launch design:

- deterministic weighted scoring in Python
- feature snapshot stored on `campaign_candidates`
- scoring version recorded for explainability
- target latency under 100ms for 50 candidates

Do not use an LLM for primary scoring on the critical path at launch.

### 6.5 Outreach orchestration

Use a Postgres-backed job queue with scheduled jobs and row locking.

Job types:

- `campaign_score`
- `campaign_dispatch_round`
- `outreach_send_sms`
- `outreach_send_voice`
- `outreach_expire_attempt`
- `campaign_recheck`
- `campaign_close`

Rules:

- one active acceptance winner per campaign
- immediate cancel of pending jobs on fill
- dedupe by `(campaign_id, employee_id, channel, round_no)`
- isolate concurrent campaigns by candidate lock policy
- job claiming, locking, retry policy, dead-letter behavior, and idempotency are platform concerns implemented once in shared worker infrastructure, not reimplemented per job type

Worker platform requirements:

- `FOR UPDATE SKIP LOCKED` or equivalent row-claim semantics
- bounded retries with retry classification
- idempotency keys on externally visible job effects
- heartbeat / stale-lock recovery
- structured job error payloads
- dead-letter state for exhausted jobs

### 6.6 Per-candidate state machine

```text
queued
  -> sms_sent
  -> awaiting_response
  -> accepted
  -> declined
  -> expired
  -> voice_initiated
  -> no_answer
  -> exhausted
  -> cancelled
```

At launch, this can remain split across `coverage_offers` and `coverage_contact_attempts` so long as service logic treats them as one logical outreach attempt model.

### 6.7 Stop conditions

Campaign closes when:

- an eligible employee accepts and validation still passes
- the shift is cancelled
- manager overrides with another employee
- all configured candidate pools are exhausted

On fill:

- pending jobs are cancelled
- outstanding outreach attempts are marked cancelled
- assignment is written
- fill event emitted
- billing evaluation scheduled

### 6.8 External adapter layer

Each provider gets an adapter with the same concerns:

- request model normalization
- response normalization
- idempotency key support
- timeout handling
- circuit breaker state
- retry classification
- cost capture

Suggested interface:

```python
class SmsProvider(Protocol):
    async def send_message(self, *, idempotency_key: str, to: str, body: str, metadata: dict) -> ProviderSendResult: ...

class VoiceProvider(Protocol):
    async def start_call(self, *, idempotency_key: str, to: str, script_ref: str, metadata: dict) -> ProviderCallResult: ...

class LlmProvider(Protocol):
    async def run(self, *, model: str, purpose: str, messages: list[dict], metadata: dict) -> LlmResult: ...
```

Provider wrappers required:

- Retell conversational voice for inbound and outbound calls
- Retell conversational messaging for inbound and outbound text interactions on `1-800-BACKFILL`
- Twilio Verify for OTP validation
- Twilio carrier / SIP trunk integration only where backend awareness is required for number transport or provisioning
- LLM inference provider

Telephony architecture rule:

- Do not model Twilio as the primary conversational surface for coverage operations.
- Do not route normal employee coverage texts or voice interactions through direct Twilio application logic if those interactions are meant to run through Retell.
- Twilio is infrastructure at the edge of the phone stack; Retell is the conversational runtime.
- If legacy direct-Twilio coverage code exists but is not confirmed live, leave it in place until the Retell delivery path is fully validated and cutover is intentional.

Telephony cutover rule:

- No half-live provider boundary is acceptable long term.
- During transition, one provider path must be declared primary for each interaction class: OTP verification, inbound conversational phone, outbound conversational phone, inbound conversational text, outbound conversational text.
- Legacy paths stay dark behind explicit configuration until removed.

## 7. Event System and Activity Feed

### 7.1 Event contract

Canonical event shape:

```python
@dataclass
class BackfillEvent:
    event_id: str
    event_type: str
    timestamp: datetime
    business_id: str
    location_id: str | None
    actor_type: str
    actor_id: str | None
    entity_type: str
    entity_id: str
    payload: dict
    metadata: dict
```

### 7.2 Taxonomy

Keep dot-notation and reserve the first segment as the domain.

Primary domains:

- `coverage.*`
- `schedule.*`
- `roster.*`
- `copilot.*`
- `billing.*`
- `integration.*`
- `auth.*`

Representative events:

- `coverage.campaign.created`
- `coverage.campaign.mode_changed`
- `coverage.scoring.completed`
- `coverage.outreach.sms_sent`
- `coverage.outreach.sms_delivered`
- `coverage.outreach.voice_initiated`
- `coverage.outreach.response_received`
- `coverage.fill.secured`
- `coverage.fill.manual_override`
- `coverage.campaign.closed`
- `schedule.draft.published`
- `schedule.shift.opened`
- `schedule.shift.swapped`
- `roster.employee.added`
- `roster.employee.availability_updated`
- `copilot.intent.resolved`
- `copilot.action.executed`
- `copilot.action.failed`
- `billing.fill.charged`
- `billing.fill.capped`

### 7.3 Pipeline

Launch pipeline:

```text
Application service executes
  -> emits in-process event objects
  -> persists to platform_events in same transaction
  -> persists outbox items for async side effects where needed
  -> transaction commits
  -> realtime publisher / projection worker fans out
```

Design rule:

- write the event record before any async consumer sees it
- projections may lag
- source-of-truth timeline lives in `platform_events`
- `audit_logs` is a temporary compatibility projection once `platform_events` exists; it must not remain a parallel canonical event store

Event cutover rule:

- New domain features emit `platform_events` first.
- `audit_logs` may be backfilled or projected from `platform_events` during transition.
- Once feed reads, webhook consumers, and operator-visible timelines are sourced from `platform_events` or its projections, direct service writes to `audit_logs` should be removed.

### 7.4 Activity feed

The feed is not raw audit logs. It is a projection optimized for operator visibility.

Feed requirements:

- location-scoped timeline
- campaign detail timeline
- related event grouping
- real-time prepend
- cursor pagination

Grouping examples:

- all outreach attempts for one campaign collapse into one campaign card
- repeated Copilot planning events stay collapsed unless failed

Launch approach:

- materialized feed projection table updated by worker
- fall back to direct event query for low volume if needed

## 8. Billing and Cost Tracking

### 8.1 Billing decision

A fill is billable only if:

- the campaign was triggered by a legitimate callout
- Backfill secured the replacement
- the replacement remained the assignee through shift start or policy-defined cutoff
- the shift was not cancelled before start

Billing evaluator runs after fill and again at a pre-start recheck if needed.

### 8.2 Monthly cap

Track per-location monthly billable total.

Rules:

- charge `$20` until cumulative billed amount reaches `$200`
- after the cap, continue running coverage normally
- record `billing.fill.capped` with `amount_cents = 0`

### 8.3 Cost ledger

Every provider interaction creates a ledger row.

Examples:

- Retell conversational SMS send
- Retell voice minute
- Retell AI minute
- Twilio Verify OTP send / verification
- LLM input tokens
- LLM output tokens

Campaign margin becomes:

```text
campaign_revenue_cents - sum(cost_ledger_entries.total_cost_cents)
```

This must be queryable by:

- campaign
- location
- billing cycle
- provider
- mode

## 9. Security and Multi-Tenancy

### 9.1 Tenant boundary

Every mutable table must include `business_id` or be transitively bound through a parent row that does.

Enforcement:

- Supabase RLS on all production tables
- all service queries scoped by org and, when applicable, location
- internal jobs always carry explicit tenant context
- worker payloads must include tenant identifiers explicitly; workers must never infer tenant scope from ambient process state

Background worker rule:

- Background jobs should execute with an explicit system actor plus explicit `business_id` / `location_id` context in payload and logs.
- If a worker uses database roles that bypass RLS, tenant scoping must be enforced in application code on every query path.
- If a worker uses RLS-bound roles, session context must be established deliberately per job before any query runs.

### 9.2 Authorization

- Copilot tools declare required roles.
- Tool handlers enforce role checks and entity-level scope.
- Precondition failure messages may be generated by the LLM, but the actual decision comes from application code.

### 9.3 Auditability

- immutable platform events
- immutable cost and billing ledgers
- soft deletes for business entities
- no production backdoor bypass of org scope

## 10. Module Boundaries for the Monolith

Recommended internal package layout:

```text
app/
  domain/
    coverage/
    scheduling/
    workforce/
    copilot/
    billing/
    events/
  integrations/
    twilio/
    retell/
    llm/
  workers/
    jobs/
    projections/
  api/
    routes/
```

Practical launch rule:

- keep deployable as one app
- split by domain modules, not by separate services

## 11. Migration Plan from Current Codebase

### Phase A: stabilize names and event model

1. Introduce `platform_events` alongside `audit_logs`.
2. Emit both for critical coverage and scheduling paths.
3. Create an event publisher abstraction so services stop writing `audit_logs` directly.
4. Declare `platform_events` canonical immediately for all new work.
5. Set an exit criterion for `audit_logs`: compatibility only until feed, webhooks, and audit-facing reads are re-pointed.

### Phase B: promote campaign as the aggregate

1. Treat `CoverageCase` as the API-facing campaign object.
2. Rename external schemas and route language from "case" to "campaign".
3. Add missing campaign columns: `callout_id`, `mode`, `filled_by_employee_id`, `fill_source`.
4. Do not create a second independent `CoverageCampaign` service model while `CoverageCase` still exists underneath.
5. Use one storage-backed aggregate with compatibility aliases only, then rename storage later if still worth the migration cost.

### Phase C: formalize outreach orchestration

1. Add a generic Postgres job table if `outbox_events` is not sufficient for timed internal jobs.
2. Move dispatch/expiry/recheck behavior into worker-driven jobs.
3. Add provider adapter wrappers with idempotency and cost logging.
4. Treat direct Twilio coverage-delivery code as dormant compatibility code unless production usage proves otherwise.
5. Only refactor or remove that path after the Retell conversational delivery path is live, verified, and the cutover plan is explicit.
6. Define provider ownership per interaction class and remove ambiguity before enabling production traffic.

### Phase D: introduce Copilot runtime

1. Add `copilot_sessions`, `copilot_messages`, `copilot_action_runs`.
2. Build channel adapters for dashboard, SMS, and Retell.
3. Start with narrow tools: `coverage.start_campaign`, `schedule.publish`, `roster.update_availability`.

### Phase E: feed and billing projections

1. Add `feed_projections`.
2. Add `cost_ledger_entries` and `billing_ledger_entries`.
3. Surface per-campaign cost and monthly cap status in API reads.

## 12. Immediate Implementation Priorities

If execution begins now, the highest-leverage sequence is:

1. Add `platform_events` and an event service abstraction.
2. Rename public coverage concepts to campaign language without breaking storage compatibility.
3. Add cost ledger capture around Retell, Twilio Verify, and LLM calls.
4. Introduce worker-driven timed outreach jobs.
5. Add Copilot session storage and tool registry.

## 13. Non-Negotiable Rules

- The Copilot never mutates state without validated tool execution.
- Conversation state is persisted server-side.
- Every meaningful state change is an event.
- Every external call records cost and uses idempotency.
- Coverage campaign is the central business object.
- Scheduler data model and coverage data model remain one shared model.
- Launch stays monolithic until actual scale demands otherwise.
