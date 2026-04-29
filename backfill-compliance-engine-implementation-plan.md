# Backfill Compliance Engine — Repo-Native Implementation Plan

## Purpose

Map the broader compliance-engine product spec onto the current Backfill codebase and define the first implementation slice that is technically supportable today.

This plan is intentionally narrower than the product spec. The repo already has a labor-rules foundation and predictive scheduler pipeline; the right move is to extend that deterministic base into a general compliance engine instead of building a second parallel system.

## Current Repo Anchors

The compliance track starts from these existing systems:

- `app/models/labor_rules.py`
  - canonical labor-rule profiles
  - profile version history
  - location-level authoritative rule resolution
- `app/services/labor_rules.py`
  - deterministic overtime projection
  - workday/workweek boundary logic
  - hours snapshot construction
- `app/services/runtime_projections.py`
  - live coverage guardrails
- `app/services/auto_scheduler.py`
  - predictive schedule input construction
  - persisted run inputs, explanations, replay/backtest plumbing
- `app/services/auto_scheduler_optimizer.py`
  - deterministic scheduler optimizer

This means the initial compliance engine should be:

- deterministic
- rule-family based
- built on top of `labor_rule_profiles` and `location_labor_rule_resolutions`
- consumed by both coverage and predictive scheduling

## Architectural Decision

Use the existing labor-rule profile system as the v1 Rule Registry boundary.

That is not the final long-term registry from the product spec, but it is the correct runtime substrate for the current repo. In practice:

- `labor_rule_profiles` remains the canonical legal-profile source for runtime
- `labor_rule_profile_versions` remains the immutable audit version
- `location_labor_rule_resolutions` remains the location-level applicability result
- the new compliance engine becomes the deterministic evaluator that consumes those resolved profiles

This avoids a wasteful rewrite and keeps the “LLM suggests, deterministic engine decides” rule intact.

## Supported v1 Rule Families

The repo can enforce only what it has first-class inputs for.

Supported now:

- overtime / premium exposure
- rest-window / clopening style constraints derived from prior assignments

Explicitly deferred:

- meal break enforcement
- rest break enforcement
- minor labor rules
- reporting pay
- split shift premiums
- predictive scheduling premium calculations
- consent artifact capture workflows
- full legal publish/review pipeline

Reason: the current models do not yet carry the complete factual inputs or approval artifacts those rule families require.

## First Compliance Slice

Implemented in the first slice:

1. `app/services/compliance_engine.py`
   - deterministic compliance evaluator
   - wraps overtime as a non-blocking premium/warning rule
   - adds rest-window / clopening evaluation as a blocking legality rule

2. predictive scheduling integration
   - `ScheduleRunInputContract` now persists `compliance_payload`
   - schedule-run explanations now persist `compliance_payload`
   - scope loading precomputes per-shift, per-employee compliance results
   - optimizer rejects hard compliance violations while still treating overtime as cost pressure

3. coverage integration
   - runtime outreach guardrails now include `compliance`
   - candidates with blocking compliance violations are hard-excluded

## Rule Semantics in v1

### Overtime

Overtime is modeled as a legal premium requirement, not a categorical illegality.

That means:

- it remains a deterministic evaluated rule
- it contributes warning / premium metadata
- it does not hard-block the shift by itself
- optimizer cost pressure still comes from `labor_payload`

This is important because “would incur overtime” and “illegal to schedule” are not the same thing.

### Rest-window / clopening

Rest-window rules are the first true blocking family in the compliance engine.

Current semantics:

- if the resolved labor-rule profile defines `minimum_rest_hours`, `clopening_min_rest_hours`, or `rest_between_shifts_hours`, the engine evaluates the gap between the candidate shift and the worker’s latest counted interval
- if the gap is below the threshold, the evaluation is `block`
- if the rule advertises written consent or premium requirements, those are surfaced in the rule result, but the runtime still blocks because the repo does not yet have an override/consent artifact workflow

This matches the product principle:

- the AI cannot schedule or fill a clearly illegal short-rest assignment
- explicit human override can be added later as a first-class workflow instead of being faked in the engine

## Persistence Contract

Scheduler runs now persist compliance state the same way they already persist reliability and labor state.

New persisted fields:

- `schedule_run_inputs.compliance_payload`
- `schedule_run_explanations.compliance_payload`

That gives:

- replayable predictive behavior
- auditable explanation artifacts
- stable future room for compliance backtesting and manager-facing explanations

## Policy Model

The existing `SchedulePolicyPayload` is extended, not replaced.

Current fields:

- `labor_rule_mode`
- `compliance_rule_mode`

Behavior:

- `labor_rule_mode` continues to govern overtime treatment in the optimizer
- `compliance_rule_mode` governs general compliance blocking/penalty behavior
- default is conservative: `compliance_rule_mode = hard_block`

This is deliberately separate because overtime and legal illegality are different classes of constraint.

## Deferred Architecture

The broader product spec is still directionally right, but these pieces remain future work:

- rule bundle / bundle activation tables distinct from labor-rule profiles
- customer policy bundles as a versioned layer parallel to legal rules
- counsel-reviewed publish pipeline and canary activation flow
- consent and override artifact model
- premium calculator split from evaluator
- explainability/audit service with immutable decision timeline
- compliance backtesting and release gates

## Next Recommended Steps

1. Add manager override + consent artifact primitives
   - required before any “block unless consent” ordinance can become operational instead of purely blocking

2. Add first-class shift segment / break modeling
   - prerequisite for meal/rest enforcement and split-shift premiums

3. Expand the rule profile schema beyond overtime-only semantics
   - ordinance bundle metadata
   - right-to-rest configuration
   - premium descriptors
   - applicability predicates

4. Add compliance decision logging
   - one evaluation record per assignment candidate / shift decision
   - versioned profile id + payload hash + blocking rule codes

5. Add customer policy overlays
   - stricter-than-law rules
   - never weaker-than-law rules

6. Then expand jurisdictional coverage
   - NYC fast food clopening
   - Oregon / Seattle / Philadelphia / Chicago rest-window and predictability families

## Bottom Line

The right long-term architecture is a full compliance platform.

The right current-codebase move is smaller:

- extend the existing labor-rule system into a deterministic compliance evaluator
- make scheduler and coverage consume the same engine
- block what is actually illegal with the data we already have
- defer the rule families that require data models or override artifacts we do not yet support
