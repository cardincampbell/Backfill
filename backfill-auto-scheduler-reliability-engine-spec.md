# Backfill Auto Scheduler + Reliability Engine Spec

## Status

Draft architecture spec for the first production-grade auto-scheduler and reliability engine.

This spec assumes:

- Backfill is a scheduling and coverage platform, not a payroll system.
- Labor rules primarily influence prioritization and assignment quality.
- The currently shipped foundation optimizes assignment for known future shifts.
- The next predictive-scheduling extension must add demand generation for partially or fully empty weeks.
- Long-term architecture must support true labor forecasting without collapsing forecast, shift shaping, and assignment into one service.
- The system must be auditable, replayable, and safe to roll out incrementally.

## Product Goal

Backfill should be able to:

1. Generate a high-quality weekly draft schedule using available workforce, labor policy, and business policy data.
2. Explain why each employee was assigned or not assigned.
3. Improve over time using reliability and outcome data.
4. Support replay and offline evaluation before live rollout.

## Core Position

The core auto-scheduler should not be LLM-driven.

The assignment engine should be:

- deterministic in constraints
- optimization-driven in assignment selection
- data-driven in scoring
- replayable and benchmarkable

LLMs should be used only as a sidecar for:

- translating natural-language manager policy into structured settings
- explaining optimizer output in plain language
- proposing schedule variants for operator review

LLMs should not directly decide production assignments.

## Problem Split

Do not build "auto scheduler" as one monolithic service.

The long-term system should be split into three separate problems:

1. Labor forecasting
- How much staffing demand is likely needed by role, location, and daypart?
- What headcount or labor-hours envelope is required?

2. Shift shaping / demand generation
- How should demand be converted into actual proposed shifts?
- What roles, locations, start times, durations, and headcounts should be created?

3. Assignment optimization
- Given a set of required or proposed shifts, which employees should be assigned?

Release order:

- Build assignment optimization foundation first.
- Build pattern-based shift shaping next.
- Build true labor forecasting later as an upstream producer for shift shaping.

## First Release Scope

Authoritative rollout definition:

- `V1` means the first externally usable draft-scheduling release.
- `V1` consists of Phase 1 and Phase 2 below.
- Phase 3 replay/backtesting is required before broad rollout, but it is not part of the initial operator-facing V1 surface.

V1 should support:

- existing future shifts as optimizer input
- draft assignment generation for authored future shifts
- explicit draft apply flow from `schedule_run` to draft schedule state
- explanation and audit persistence
- minimal business policy controls required by the optimizer
- reliability-aware scoring using a pinned reliability snapshot consumed by the run
- labor-rule-aware assignment scoring

V1 should not include:

- automatic demand forecasting
- fully autonomous schedule auto-publish
- direct LLM schedule generation
- full operator-facing replay/backtesting workflows
- payroll-grade legal interpretation beyond scheduling policy

The next predictive-scheduling extension after V1 should support:

- mixed authored and generated weekly demand
- fully empty unpublished weeks
- ghost schedule generation for the full week
- apply semantics that create draft shifts before applying assignments

This extension should still be pattern-based first, not model-forecast-first.

## High-Level Architecture

### 0. Demand Pipeline

The long-term upstream architecture is:

1. `labor_forecasting`
- produces demand points, not shifts
- examples:
  - `Monday 07:00-15:00, role=server, headcount=3`
  - `Friday 16:00-22:00, role=barista, labor_hours=18`

2. `shift_shaping`
- converts demand points into actual proposed shifts
- may also operate without a forecast by using:
  - historical schedule patterns
  - location templates
  - business defaults

3. `assignment_optimization`
- assigns employees to fixed and generated shifts

Do not let forecasting create assignments directly.
Do not let assignment optimization guess demand directly.
Do not let one service forecast, shape, assign, and publish in a single pass.

### 0.1 Fixed vs Generated Demand

The system must support mixed weeks.

That means:

- manually authored draft shifts remain fixed demand
- generated proposed shifts fill gaps in the planning window
- empty weeks are just a special case of "no fixed demand"

Do not branch only on:

- "week empty" -> generate demand
- "week not empty" -> optimize existing shifts

Most real weeks will contain a mix of:

- manually authored shifts
- previously generated shifts
- still-missing demand

The orchestrator should merge:

- fixed demand
- generated demand
- assignment feasibility

into one scheduling run.

### 0.2 Mixed-Week Netting Rule

Before predictive scheduling implementation begins, the mixed-week collision rule must be explicit and deterministic.

V1 rule:

- generated demand is netted against existing authored demand by exact normalized demand envelope, not by loose overlap

The normalized demand envelope is the unit identified by `demand_key`.

For V1, `demand_key` must encode:

- `business_id`
- `location_id`
- `role_id`
- local service date
- normalized local `window_start`
- normalized local `window_end`

Netting behavior:

- manually authored draft shifts are normalized into authored demand envelopes
- generated demand is reduced only by authored demand that resolves to the same `demand_key`
- remaining generated headcount is:
  - `max(0, target_headcount - authored_headcount_for_same_demand_key)`

Partial headcount rule:

- if authored demand for the same `demand_key` covers part of the target headcount, only the remaining headcount is generated
- if authored demand for the same `demand_key` meets or exceeds the target headcount, no generated demand is created for that envelope

Partial overlap rule:

- authored shifts that only partially overlap a generated envelope but do not normalize to the same `demand_key` do not reduce generated demand in V1
- those shifts remain fixed demand and are handled separately by assignment optimization

This is intentionally conservative.

Do not implement loose overlap-based netting in V1.
Do not attempt envelope splitting in V1.

Future extension:

- a later version may add overlap-aware envelope splitting or daypart coverage reconciliation
- that should be introduced as a versioned demand-shaping rule, not as implicit behavior drift

### 0.3 Predictive Scheduling V1

The first predictive weekly scheduling release should be:

- pattern-based demand generation
- forecast-compatible architecture
- no true labor forecasting model yet

Inputs for pattern-based demand generation:

- previous published week
- last 2-4 same weekdays
- location templates / defaults
- historical role/daypart patterns
- business hours and operating envelopes

This produces a full ghost week quickly without blocking on a dedicated forecasting stack.

### 1. Scheduling Inputs Layer

This layer resolves the authoring state used by the optimizer.

Inputs include:

- future open shifts for a planning window
- employees eligible by business
- recurring availability rules
- availability exceptions
- employee roles and proficiency
- employee location eligibility
- labor-rule projections
- business scheduling policy
- employee reliability snapshots
- recent assignment burden
- fairness targets
- preference signals

This layer should produce a single immutable scheduling input snapshot for each run.

### 2. Constraint Engine

This layer defines hard feasibility rules.

Examples:

- employee must be active
- role qualification must match
- location eligibility must match
- recurring availability must allow the shift
- exceptions must not block the shift
- overlap rules must pass
- minimum rest rules must pass if enabled
- max shifts/day must pass if configured as hard
- labor rules may be hard or soft depending on business policy

The optimizer never violates hard constraints.

### 3. Scoring / Objective Engine

This layer defines soft objectives.

Examples:

- maximize schedule fill rate
- reduce overtime exposure
- prefer more reliable employees
- balance hours fairly
- balance undesirable shifts fairly
- prefer primary location / role fit
- reduce commute burden
- reduce recent burden concentration
- improve preference satisfaction

This layer should be explicit and versioned.

### 4. Optimizer

Use a bounded optimization solver such as OR-Tools CP-SAT for assignment optimization.

The optimizer should:

- assign employees to candidate shifts
- maximize weighted objective value
- produce a feasible draft schedule
- emit "no feasible assignment" outcomes when constraints prevent assignment

The optimizer should not write live schedules directly.

### 5. Persistence / Audit Layer

Every run must persist:

- immutable input snapshot
- resolved policies and weights
- candidate pools
- chosen assignments
- top rejected alternatives per shift
- explanation payload
- run status and metrics

### 6. Replay / Evaluation Layer

The system must support offline backtesting:

- "Given last week's inputs, what would the optimizer have produced?"
- "How would that compare to the actual schedule and attendance outcomes?"

This layer is required before broad live rollout.

### 7. LLM Sidecar

LLM usage is allowed only for:

- converting operator text into structured scheduling policy
- explaining schedule recommendations
- proposing alternative schedule strategies

The LLM does not own constraints or final assignment decisions.

## Schedule Run Model

Add a first-class `schedule_runs` subsystem from day one.

### schedule_runs

Purpose:

- immutable run header
- authoritative lifecycle for every optimizer run

Fields:

- `id`
- `business_id`
- `location_id` nullable for multi-location runs
- `planning_window_start`
- `planning_window_end`
- `run_type`
  - `draft_generate`
  - `replay`
  - `shadow_compare`
  - `publish_candidate`
- `status`
  - `queued`
  - `running`
  - `completed`
  - `failed`
  - `cancelled`
- `optimizer_engine`
  - example: `ortools_cp_sat_v1`
- `objective_version`
- `constraints_version`
- `policy_version`
- `input_snapshot_version`
- `input_snapshot_hash`
- `run_metadata`
- `started_at`
- `completed_at`
- `created_at`

### schedule_run_inputs

Purpose:

- immutable persisted snapshot of what the solver saw

Fields:

- `schedule_run_id`
- `shift_payload`
- `employee_payload`
- `availability_payload`
- `policy_payload`
- `labor_payload`
- `reliability_payload`
- `reliability_snapshot_generated_at`
- `reliability_snapshot_hash`
- `reliability_snapshot_version`
- `source_metadata`

### schedule_run_assignments

Purpose:

- chosen assignments per shift

Fields:

- `schedule_run_id`
- `shift_id`
- `employee_id`
- `decision_score`
- `decision_rank`
- `assignment_payload`

### schedule_run_rejections

Purpose:

- top rejected alternatives per shift, not full solver search internals

Fields:

- `schedule_run_id`
- `shift_id`
- `employee_id`
- `candidate_rank`
- `rejection_reason_codes`
- `score_payload`
- `constraint_failure_payload`

Store only the top-N rejected candidates by relevance.

Do not attempt to persist every solver branch.

### schedule_run_explanations

Purpose:

- operator-facing explanation payload

Fields:

- `schedule_run_id`
- `summary_payload`
- `fairness_payload`
- `overtime_payload`
- `coverage_payload`
- `unassigned_shift_payload`

### schedule_run_metrics

Purpose:

- performance and quality summary

Fields:

- `schedule_run_id`
- `shift_count`
- `assigned_shift_count`
- `unassigned_shift_count`
- `candidate_considered_count`
- `overtime_assignment_count`
- `fairness_spread_metrics`
- `solver_runtime_ms`
- `objective_value`

### schedule_run_applies

Purpose:

- immutable audit surface for applying a completed `schedule_run` into draft schedule state

Fields:

- `id`
- `schedule_run_id`
- `business_id`
- `location_id` nullable for multi-location runs
- `planning_window_start`
- `planning_window_end`
- `status`
  - `queued`
  - `applied`
  - `stale_rejected`
  - `failed`
  - `no_op`
- `target_snapshot_hash`
- `current_snapshot_hash`
- `stale_reason`
- `apply_metadata`
- `applied_at`
- `created_at`

## Reliability Engine

Reliability should not remain a single opaque scalar.

Build a proper event-sourced reliability subsystem.

### Reliability principles

- reliability is a feature set first, score second
- scores must be decomposable
- sample size must affect confidence
- cold-start handling must be explicit
- recency should matter
- role/location specificity must be possible later

### reliability_events

Purpose:

- append-only source of truth for reliability signals

Event families:

- attendance
  - worked_shift
  - late_arrival
  - missed_shift
  - early_departure
- commitment / follow-through
  - accepted_offer
  - declined_offer
  - accepted_then_cancelled
  - accepted_and_worked
- coverage behavior
  - responded_to_callout
  - no_response_to_offer
  - standby_acceptance
  - standby_promotion_success
- schedule behavior
  - callout_submitted
  - manager_removed
  - reassignment_requested
- response behavior
  - response_time_recorded

Fields:

- `id`
- `business_id`
- `employee_id`
- `shift_id` nullable
- `location_id` nullable
- `role_id` nullable
- `event_type`
- `occurred_at`
- `source`
- `event_payload`

### reliability_snapshots

Purpose:

- current feature vector plus roll-up scores used by scheduling and coverage

Fields:

- `employee_id`
- `business_id`
- `snapshot_at`
- `sample_size`
- `confidence`
- `attendance_score`
- `punctuality_score`
- `commitment_score`
- `response_behavior_score`
- `coverage_reliability_score`
- `overall_reliability_score`
- `snapshot_payload`

Optimizer contract:

- the optimizer must consume a pinned reliability snapshot payload captured inside `schedule_run_inputs`
- replay must never read "latest reliability snapshot" at evaluation time
- each run must persist the reliability snapshot identity it consumed via:
  - `reliability_snapshot_generated_at`
  - `reliability_snapshot_hash`
  - `reliability_snapshot_version`

This keeps run audit and replay stable even if the latest reliability snapshot changes later.

### Reliability dimensions

At minimum:

- attendance reliability
- punctuality reliability
- commitment / follow-through
- response behavior
- coverage-specific reliability

### Cold start / sample size

This must be explicit in v1.

Rules:

- new employees should not be unfairly suppressed
- low sample size should shrink toward business baseline, not toward zero
- confidence should be stored and surfaced
- scoring should prefer "uncertain but viable" over "silently excluded"

Recommended initial approach:

- Bayesian shrinkage or weighted prior toward business/location baseline
- confidence bucket:
  - `low`
  - `medium`
  - `high`

### Reliability for scheduling vs coverage

Do not assume one universal reliability score is sufficient forever.

Persist:

- overall reliability score
- coverage-specific reliability score
- raw dimension scores

Future extension:

- role-specific reliability
- location-specific reliability
- shift-type reliability

## Business Scheduling Policy

Build policy as structured data, not hidden weights.

### Hard/soft rule split

Some businesses will want overtime treated as:

- hard block
- soft penalty

The same is true for:

- max hours/week
- consecutive days
- minimum rest
- same-day second shifts
- cross-location assignments
- undesirable shift balancing

These must be configurable policy decisions.

### Fairness

Fairness must be explicit policy, not a hidden score term.

Examples:

- target weekly hours balance
- weekend balance
- closing/opening balance
- undesirable shift balance
- full-time / part-time target adherence

Persist fairness as named policy inputs and named objective terms.

## Objective Model

Do not store just "weights blob" with no meaning.

Store named objective terms.

Recommended initial objective terms:

- `coverage_completeness`
- `reliability_preference`
- `overtime_minimization`
- `fairness_balance`
- `role_fit`
- `location_fit`
- `preference_satisfaction`
- `commute_minimization`
- `recent_burden_balance`

Each run should persist:

- objective term names
- objective weights
- policy version

## Predictive Demand Extension

The current optimizer foundation handles only existing authored shifts.

To support predictive weekly scheduling, the backend must add first-class proposed demand and proposed shifts.

### Demand source types

Demand must carry explicit source identity.

Allowed source types:

- `manual_authored`
- `historical_pattern`
- `template`
- `forecast`

This is required for:

- auditability
- apply idempotency
- later forecast substitution
- UI ghost-schedule explanation

### schedule_run_inputs extension

Do not overload `shift_payload` forever.

Long-term the run input contract should distinguish:

- `fixed_shift_payload`
  - authored draft shifts already present in the planning window
- `generated_demand_payload`
  - upstream demand units produced by historical pattern, template, or forecast logic
- `employee_payload`
- `availability_payload`
- `policy_payload`
- `labor_payload`
- `reliability_payload`
- `source_metadata`

For incremental rollout, the current `shift_payload` may remain as a compatibility field, but architecturally it should mean:

- fixed authored demand only

### schedule_run_proposed_shifts

Add a first-class persisted model for generated proposed shifts.

Purpose:

- store generated weekly demand at the shift level
- support empty or partially authored weeks
- give apply a deterministic target
- give the UI a stable ghost-schedule surface

Fields:

- `id`
- `schedule_run_id`
- `location_id`
- `role_id`
- `starts_at`
- `ends_at`
- `headcount`
- `demand_key`
- `source_type`
  - `historical_pattern`
  - `template`
  - `forecast`
- `source_run_id` nullable
- `source_point_id` nullable
- `generation_strategy`
- `generation_version`
- `generation_payload`
- `created_at`

Rules:

- `demand_key` must be stable for the planning scope
- generated shifts must be replayable and diffable
- the optimizer consumes proposed shifts alongside fixed authored shifts

### labor_forecast_runs

This is a future subsystem, but the architecture should reserve it now.

Purpose:

- immutable forecast run header

Fields:

- `id`
- `business_id`
- `location_id` nullable
- `planning_window_start`
- `planning_window_end`
- `forecast_model_version`
- `feature_snapshot_hash`
- `status`
- `forecast_metadata`
- `created_at`
- `completed_at`

### labor_forecast_points

Purpose:

- normalized demand units, not shifts

Fields:

- `id`
- `labor_forecast_run_id`
- `location_id`
- `role_id`
- `window_start`
- `window_end`
- `predicted_headcount`
- `predicted_labor_hours` nullable
- `confidence`
- `forecast_payload`

Rules:

- forecast points never assign employees directly
- shift shaping converts forecast points into `schedule_run_proposed_shifts`

## Assignment Optimizer V1

### Initial scope

V1 should optimize assignment for already-authored future shifts.

Inputs:

- draft/open shifts in planning window
- active employees
- eligibility and policy snapshots
- reliability snapshots

Outputs:

- a proposed draft schedule
- unassigned shifts with reasons
- ranked rejected alternatives per shift

### Draft-first rollout

Do not auto-publish live schedules in the first release.

V1 should:

- generate a draft recommendation
- persist it as a schedule run
- allow operator review and apply into draft schedule state
- rely on existing publish flows for live publication after review

Later:

- optional auto-publish modes can be introduced behind business policy

### Apply / Commit Contract

The spec must define exactly how a reviewed `schedule_run` becomes a draft schedule.

Rules:

- apply operates only on draft-authoring state
- apply never publishes live schedules
- apply is a separate explicit operation from optimizer run generation
- apply writes an immutable `schedule_run_applies` record

Preconditions:

- `schedule_run.status` must be `completed`
- the run must target a specific business / location scope and planning window
- the current draft schedule snapshot must match the run's target input snapshot for the mutable authoring entities
- the run must not already have a successful apply for the same target snapshot

Required stale detection:

- the run persists `input_snapshot_hash`
- apply computes a current authoring snapshot hash for the same scope
- if the current hash differs from the run's target hash, apply fails closed with `stale_rejected`

The authoring snapshot hash must include, at minimum:

- target shift rows in scope:
  - shift ids
  - role ids
  - location ids
  - start / end timestamps
  - lifecycle / staffing state
  - premium fields
  - manager-approval flags
  - assignment-relevant shift metadata
- draft assignment rows in scope:
  - assignment ids
  - shift ids
  - employee ids
  - `assigned_via`
  - assignment status
  - `replaced_assignment_id`
  - assignment-relevant metadata
- mutable eligibility inputs that are allowed to affect apply validity:
  - employee role eligibility in scope
  - employee location eligibility in scope
  - availability exceptions in scope
- scope and policy identifiers:
  - business id
  - location scope
  - planning window
  - policy version identifiers used by the run

This hash should represent the exact mutable authoring surface that can invalidate apply.

Idempotency:

- applying the same run twice against the same unchanged target snapshot must be a no-op
- repeated apply requests should return the existing successful `schedule_run_applies` record

Conflict behavior:

- if shifts changed after run generation, apply must not partially mutate the schedule
- apply fails closed and requires a fresh run
- no implicit force-apply in V1

Draft mutation semantics:

- successful apply writes proposed draft assignments for the run's chosen assignments
- successful apply may also create draft shifts from `schedule_run_proposed_shifts`
- assignments written by apply should carry `assigned_via = auto_scheduler`
- draft mutation metadata should include `schedule_run_id` and `schedule_run_apply_id`
- apply may clear and replace prior auto-scheduler draft assignments within scope, but must not mutate manually authored assignments outside the run's target scope
- manually authored draft assignments that already existed at run generation time are treated as locked inputs and excluded from auto-scheduler replacement
- manually authored draft assignment changes made after run generation make the run stale and require a fresh run before apply

Additional rules for generated demand:

- generated draft shifts created by apply must carry metadata:
  - `created_via = auto_scheduler_demand`
  - `schedule_run_id`
  - `schedule_run_apply_id`
  - `demand_key`
  - `source_type`
- if a generated draft shift with the same `demand_key` already exists for the same run/apply scope, apply must reuse or no-op rather than duplicate
- manually authored draft shifts in scope are preserved as fixed demand and are never replaced by generated demand
- mixed weeks must support:
  - preserving authored draft shifts
  - generating missing shifts
  - assigning employees across both sets

### Predictive Scheduling Apply Semantics

For predictive weekly scheduling, apply becomes:

1. validate target scope is not stale
2. preserve locked manual draft shifts
3. materialize `schedule_run_proposed_shifts` into draft shifts where needed
4. apply chosen assignments to:
  - existing authored draft shifts
  - created generated draft shifts

This must remain:

- draft-only
- idempotent
- fail-closed on stale authoring changes
- auditable via `schedule_run_applies`

## Demand Forecasting

Demand forecasting is a separate system and should come after pattern-based predictive scheduling, but the architecture should accommodate it now.

Future demand forecasting inputs may include:

- historical scheduled demand by location/role/daypart
- historical attendance and fill rates
- sales or revenue if ever available
- weather forecasts
- holidays
- events / local seasonality
- labor cost targets

Do not block pattern-based predictive scheduling on this.
Do not let lack of forecasting delay empty-week ghost schedules.
Do design the demand pipeline now so forecasts can become an upstream producer later.

## Replay / Backtesting Harness

This is required before wide rollout.

This is not part of the initial operator-facing V1 surface.

It is a shadow and evaluation requirement that must be in place before broad rollout.

### replay_runs

Purpose:

- compare optimizer output to historical reality using frozen historical inputs

Core questions:

- what schedule would the optimizer have produced?
- how did it differ from the actual schedule?
- how did actual attendance/callout outcomes compare?
- which policy set performed better?

### Replay metrics

Track at least:

- assignment match rate vs actual
- actual attendance outcomes on proposed assignments
- overtime exposure
- fairness spread
- uncovered shift count
- operator override delta

### Replay rules

- inputs must be time-frozen to what was known then
- replays must never mutate live schedules
- replay runs should persist independently from live schedule runs

## LLM Usage

Allowed:

- natural-language scheduling policy -> structured settings
- operator explanation of why someone was assigned
- "show me a lower-overtime variant"
- schedule QA summaries

Not allowed:

- direct final assignment authority
- unsupervised mutation of constraints
- replacing optimization with prompt-only schedule generation

## Recommended Implementation Order

Authoritative sequencing:

- Phase 1 and Phase 2 together make up `V1`
- Phase 3 is required before broad rollout
- later phases extend the system beyond V1

### Phase 1

- `schedule_runs` schema and persistence
- assignment optimizer only
- draft assignment generation for authored future shifts
- draft apply / commit contract
- explanation payloads
- minimal business policy controls required by the optimizer
- pinned reliability snapshot consumption inside `schedule_run_inputs`

### Phase 2

- `reliability_events`
- `reliability_snapshots`
- cold-start handling
- integrate reliability snapshots into optimizer scoring

### Phase 3

- replay / backtesting harness
- historical comparison metrics
- shadow-mode schedule evaluation

### Phase 4

- predictive weekly scheduling
- pattern-based demand generation
- `schedule_run_proposed_shifts`
- mixed fixed/generated demand orchestration
- apply semantics that create draft shifts plus assignments

### Phase 5

- expanded business policy controls
- fairness policy controls
- hard vs soft labor-rule configuration

### Phase 6

- LLM sidecar for policy translation and explanations

### Phase 7

- demand forecasting
- forecast-to-shift generation

## Recommended Parallel Build Split

This project can be parallelized, but only if ownership is explicit.

Do not parallelize the optimizer core and draft apply contract across multiple engineers.

Those remain the critical path and should have a single owner.

### Workstream A: Run + Apply Core

Owner: Codex / primary implementation owner

Scope:

- `schedule_runs`
- `schedule_run_inputs`
- `schedule_run_assignments`
- `schedule_run_rejections`
- `schedule_run_explanations`
- `schedule_run_metrics`
- `schedule_run_applies`
- optimizer service skeleton
- draft apply / commit contract
- idempotency and stale detection
- integration into draft scheduling mutation flow

This is the critical path and should remain single-owner.

### Workstream B: Reliability Engine Foundation

Owner: Developer 1

Scope:

- `reliability_events`
- `reliability_snapshots`
- snapshot calculation jobs
- cold-start and sample-size handling
- pinned snapshot contract used by the optimizer

This can proceed in parallel once the shared input contract is agreed.

### Workstream C: Replay / Backtesting Harness

Owner: Developer 1

Scope:

- replay run models
- frozen input reconstruction
- historical comparison metrics
- offline replay runner
- shadow evaluation support

This depends on the `schedule_run` contract, but can be built in parallel after that contract is fixed.

### Workstream D: Policy Layer

Owner: Codex / primary implementation owner

Scope:

- business policy schema
- defaults and validation
- policy resolution contract
- API/backend settings surfaces required by the optimizer
- fairness and hard-vs-soft policy integration points

This is intentionally paired with Workstream A because policy resolution directly affects optimizer inputs and apply semantics.

### Parallelization Rules

- Workstream A and Workstream D stay with the primary owner
- Workstream B and Workstream C stay with Developer 1
- no dual ownership of optimizer objective code
- no dual ownership of draft apply mutation code
- no competing definitions of run schema or input snapshot schema

### Shared Contracts That Must Be Agreed First

Before parallel implementation starts, the team must lock these contracts:

- `schedule_run` schema
- `schedule_run_apply` schema
- optimizer input payload
- reliability snapshot payload
- policy payload

Once those are fixed:

- Codex owns A + D
- Developer 1 owns B + C

## Predictive Scheduling Extension Split

The next predictive-scheduling build should also be parallelized with explicit ownership.

### Workstream E: Demand Pipeline Contracts + Apply Semantics

Owner: Codex / primary implementation owner

Scope:

- `schedule_run_proposed_shifts`
- fixed-vs-generated demand contract
- `schedule_run_inputs` extension for generated demand
- demand-key identity rules
- apply semantics for creating draft shifts from generated demand
- idempotency and ownership metadata for generated shifts
- future `labor_forecast_runs` / `labor_forecast_points` contract design

This remains the critical architectural seam because it defines how forecasting can plug in later without breaking apply or replay.

### Workstream F: Pattern-Based Demand Generation + Ghost Schedule UX

Owner: Developer 1

Scope:

- historical-pattern demand generation logic
- mixed-week ghost schedule generation
- operator-facing empty-week and partial-week UI behavior
- visual distinction between:
  - fixed authored shifts
  - generated proposed shifts
- explanation surfaces for generated demand

This can proceed in parallel once Workstream E locks:

- `schedule_run_proposed_shifts`
- generated demand payload shape
- demand-key contract
- apply semantics for generated shifts

### Workstream G: Forecasting Subsystem Design + Later Backend Foundation

Owner: Codex / primary implementation owner

Scope:

- `labor_forecast_runs`
- `labor_forecast_points`
- forecast-to-shift interface contract
- feature snapshot and model-version audit contract
- non-LLM forecasting boundaries

This is intentionally upstream and should not block Workstream F's pattern-based weekly ghost scheduling release.

### Predictive Extension Parallelization Rules

- Codex owns the contracts that affect apply, replay, and future forecast compatibility
- Developer 1 owns pattern-based demand generation and the ghost schedule UI layer
- no dual ownership of generated-shift persistence
- no dual ownership of apply semantics for generated shifts
- no UI-driven redefinition of demand-key or source-type contracts

## Repo Touchpoints

New services:

- `app/services/auto_scheduler.py`
- `app/services/auto_scheduler_assignment.py`
- `app/services/shift_shaping.py`
- `app/services/labor_forecasting.py`
- `app/services/reliability_engine.py`
- `app/services/schedule_replay.py`
- `app/services/schedule_policy.py`

New models:

- `app/models/auto_scheduler.py`
- `app/models/reliability.py`
- `app/models/labor_forecasting.py`

Existing seams to reuse:

- employee base and availability in [app/models/workforce.py](app/models/workforce.py)
- runtime projections in [app/services/runtime_projections.py](app/services/runtime_projections.py)
- scheduling mutations and publish flows in [app/services/scheduling.py](app/services/scheduling.py)
- labor rules in [app/services/labor_rules.py](app/services/labor_rules.py)
- coverage ranking patterns in [app/services/coverage.py](app/services/coverage.py)

## Non-Negotiable Guardrails

- no direct LLM assignment authority
- no monolithic "forecast + assign + publish" service
- no forecast module that writes shifts and assignments directly
- no live auto-publish in v1
- all runs are persisted and replayable
- hard vs soft rules are explicit policy
- fairness is explicit policy
- reliability is event-sourced and decomposed

## Bottom Line

The right first system is:

- assignment optimizer first
- schedule run persistence from day one
- reliability events and snapshots early
- offline replay before live rollout
- pattern-based predictive scheduling next
- labor forecasting later as an upstream input to shift shaping

That gives Backfill a durable scheduling engine and a defensible data moat without collapsing into an opaque AI scheduling black box.
