# Backfill Labor Rules Engine Spec
**Status:** Proposed implementation spec  
**Date:** 2026-04-17  
**Purpose:** Introduce a durable, LLM-assisted labor-rules system for coverage ranking without letting the LLM mutate production law tables at onboarding time.

## 1. Problem

Backfill currently uses a generic overtime-risk heuristic during coverage ranking. The current logic lives in [app/services/runtime_projections.py](/Users/carcam07/Backfill/app/services/runtime_projections.py) and scores only on projected hours:

- `>= 40 hours` -> high risk
- `>= 32 hours` -> elevated
- `>= 24 hours` -> watch

That is not enough for state-specific or industry-specific labor rules.

Examples:

- California has daily overtime, weekly overtime, seventh-day rules, and double time.
- Alaska has daily and weekly overtime.
- Colorado has weekly overtime, daily overtime after 12 hours, and overtime after 12 consecutive hours.
- Nevada has conditional daily overtime based on wage threshold.
- Oregon is mostly weekly-only, but some industries have special rules.

Backfill needs a system that:

- keeps jurisdiction rules current
- resolves the correct rule profile for each location
- uses those rules during candidate ranking
- remains auditable and overrideable
- does not rely on per-customer ad hoc law generation

## 2. Core Decision

Do **not** let the LLM create or update labor rule tables during every location creation.

Instead, split the problem into two separate systems:

1. **Central labor-rule maintenance**
   - shared across all customers
   - runs offline
   - ingests official sources
   - produces structured proposals
   - requires review before activation

2. **Location-level profile resolution**
   - runs at location create/update time
   - does **not** invent law
   - selects the best existing rule profile for that location
   - may use LLM only when the choice is conditional or industry-specific

This keeps one canonical legal model for the product while still making onboarding feel automatic.

## 3. Current Repo Anchors

The current repo already has the right foundations:

- jurisdiction anchor at the location layer:
  - [app/models/business.py](/Users/carcam07/Backfill/app/models/business.py)
  - `Location.region`
  - `Location.country_code`
  - `Location.timezone`
- candidate scoring storage:
  - [app/models/coverage.py](/Users/carcam07/Backfill/app/models/coverage.py)
  - `CoverageCandidate.scoring_factors`
- campaign/case metadata:
  - [app/models/coverage.py](/Users/carcam07/Backfill/app/models/coverage.py)
  - `CoverageCase.case_metadata`
- existing LLM orchestration pattern:
  - [app/services/llm_gateway.py](/Users/carcam07/Backfill/app/services/llm_gateway.py)
  - [app/services/business_classification.py](/Users/carcam07/Backfill/app/services/business_classification.py)

The labor-rules system should follow the same architecture as business classification:

- structured tool output
- shadow vs primary modes
- immutable run history
- deterministic fallback and validation

## 4. Goals

- Maintain one canonical library of labor rule profiles for all Backfill tenants.
- Resolve the correct rule profile automatically for most locations.
- Use rule profiles as a ranking signal for coverage outreach.
- Make changes versioned, traceable, reviewable, and reversible.
- Support manual override where the business has special circumstances or counsel guidance.

## 5. Non-Goals

- Backfill is not becoming a payroll or legal-compliance engine of record.
- Backfill will not calculate final wages owed.
- Backfill will not let the LLM create new jurisdictions or production rule rows live at onboarding time.
- Backfill will not rely on free-text legal reasoning at runtime.

## 6. Product Model

### 6.1 Jurisdiction key

Use `jurisdiction_code`, not a plain `state` string.

Examples:

- `US-CA`
- `US-CO`
- `US-NV`

Why:

- supports non-US expansion
- avoids ambiguous state-only keys
- fits location `country_code + region`

### 6.2 Rule buckets

Use these bounded `overtime_mode` values:

- `weekly_only`
- `daily_8_plus_weekly`
- `daily_12_or_consecutive_plus_weekly`
- `daily_8_plus_weekly_plus_7th_day`
- `conditional_daily_plus_weekly`
- `industry_specific`

These are broader and more durable than creating 50 bespoke state engines.

### 6.3 Canonical profile fields

Each rule profile should support:

- `jurisdiction_code`
- `overtime_mode`
- `daily_ot_threshold_hours`
- `weekly_ot_threshold_hours`
- `double_time_threshold_hours`
- `consecutive_hours_threshold_hours`
- `industry_profile_code`
- `rules_json`
- `effective_start_date`
- `effective_end_date`
- `source_urls`
- `source_version`
- `source_hash`
- `is_active`

Do **not** reduce complex concepts to weak flags like:

- `seventh_day_rule: true`
- `industry_profile_required: true`
- `daily_ot_condition: "Nevada pay threshold"`

Those need structured semantics in `rules_json`.

## 7. Proposed Data Model

### 7.1 `labor_rule_profiles`

Canonical active profiles that the runtime evaluates.

Fields:

- `id`
- `code`
- `jurisdiction_code`
- `display_name`
- `overtime_mode`
- `daily_ot_threshold_hours`
- `weekly_ot_threshold_hours`
- `double_time_threshold_hours`
- `consecutive_hours_threshold_hours`
- `industry_profile_code`
- `rules_json`
- `effective_start_date`
- `effective_end_date`
- `source_urls`
- `source_version`
- `source_hash`
- `is_active`
- `created_at`
- `updated_at`

Examples:

- `us_ca_general_nonexempt`
- `us_or_general`
- `us_or_manufacturing`
- `us_nv_general_under_threshold`
- `us_nv_general_over_threshold`

### 7.2 `labor_rule_profile_versions`

Immutable history of each profile over time.

Fields:

- `id`
- `labor_rule_profile_id`
- `version_no`
- `payload_json`
- `change_summary`
- `created_by`
- `created_at`

### 7.3 `labor_rule_source_documents`

Official sources fetched by the maintenance pipeline.

Fields:

- `id`
- `jurisdiction_code`
- `source_url`
- `source_type`
- `fetched_at`
- `http_etag`
- `http_last_modified`
- `raw_text`
- `normalized_text`
- `content_hash`
- `is_active`

### 7.4 `labor_rule_update_proposals`

LLM-generated proposals before activation.

Fields:

- `id`
- `jurisdiction_code`
- `proposal_status`
- `proposal_type`
- `current_profile_codes`
- `proposed_profiles_json`
- `reason_summary`
- `citations_json`
- `llm_provider`
- `llm_model`
- `llm_generation_id`
- `reviewed_by`
- `reviewed_at`
- `created_at`

Statuses:

- `draft`
- `needs_review`
- `approved`
- `rejected`
- `superseded`

### 7.5 `location_labor_rule_resolutions`

Stores which profile a location currently resolves to and why.

Fields:

- `id`
- `location_id`
- `jurisdiction_code`
- `resolved_profile_code`
- `resolution_source`
- `resolution_confidence`
- `manual_override_profile_code`
- `resolution_context_json`
- `llm_generation_id`
- `resolved_at`
- `created_at`
- `updated_at`

`resolution_source`:

- `deterministic`
- `llm`
- `manual_override`
- `fallback`

### 7.6 `labor_rule_resolution_runs`

Immutable history for location-profile selection.

Fields:

- `id`
- `location_id`
- `jurisdiction_code`
- `candidate_profile_codes`
- `selected_profile_code`
- `decision`
- `confidence`
- `reason_codes`
- `input_snapshot_json`
- `llm_generation_id`
- `created_at`

## 8. LLM Responsibilities

### 8.1 Central maintenance LLM

Purpose:

- keep the canonical profile library current
- compare official source text to active profile definitions
- propose profile changes in structured form

This runs:

- on schedule
- on official-source hash change
- in shadow mode first

It does **not**:

- activate profiles directly
- write runtime tables during onboarding
- create arbitrary new schema concepts

### 8.2 Location-resolution LLM

Purpose:

- choose from existing profile codes when deterministic logic is not enough

Examples:

- Oregon general vs Oregon manufacturing
- Nevada conditional profile selection
- future industry-specific regime selection

It should only run when:

- more than one active profile is plausible
- or a profile’s `overtime_mode` requires interpretation from business/location context

It does **not**:

- create new profiles
- alter canonical labor rules

### 8.3 Runtime coverage ranking

The runtime coverage engine should be deterministic.

Do **not** call an LLM inside coverage candidate ranking for each campaign.

Runtime should:

- read the resolved location profile
- evaluate it against recent hours and projected shift hours
- store the result in candidate scoring factors

That keeps execution fast, explainable, and stable.

## 9. Service Architecture

### 9.1 New service: `app/services/labor_rules.py`

Owns:

- loading active rule profiles
- resolving rule profiles for a location
- deterministic profile evaluation
- applying overrides

Key functions:

- `resolve_jurisdiction_code(location) -> str`
- `active_profiles_for_jurisdiction(session, jurisdiction_code) -> list[...]`
- `resolve_location_rule_profile(session, location, business) -> ResolutionResult`
- `evaluate_overtime_projection(profile, *, employee_hours, candidate_shift, historical_assignments) -> dict`

### 9.2 New service: `app/services/labor_rule_maintenance.py`

Owns:

- source fetching
- source normalization
- proposal generation
- rule diffing
- proposal persistence

Key functions:

- `fetch_active_source_documents(session, jurisdiction_code)`
- `detect_source_changes(...)`
- `generate_rule_update_proposal(...)`
- `validate_profile_candidate(...)`

### 9.3 New service: `app/services/labor_rule_resolution.py`

Owns:

- location-level profile selection
- deterministic resolution
- bounded LLM fallback
- immutable run logging

Key functions:

- `resolve_location_profile(...)`
- `run_llm_profile_selection(...)`
- `persist_resolution_run(...)`

## 10. LLM Workflow Design

### 10.1 Rule-maintenance workflow

1. Fetch official source documents for a jurisdiction.
2. Normalize and hash the content.
3. If the source hash changed, run the maintenance LLM.
4. The LLM returns a structured proposal limited to the allowed profile schema.
5. Deterministic validation checks:
   - required fields present
   - legal thresholds structurally sane
   - no unsupported mode
   - no activation outside bounded schema
6. Persist `labor_rule_update_proposals`.
7. Human review approves or rejects.
8. Approved proposal creates a new `labor_rule_profile_versions` row and updates the active profile.

### 10.2 Location-create workflow

1. Location is created with `region`, `country_code`, `timezone`, place metadata, and business classification context.
2. Resolve `jurisdiction_code` from `country_code + region`.
3. Load active profiles for that jurisdiction.
4. If exactly one generic profile applies, resolve deterministically.
5. If multiple profiles are plausible, run bounded LLM profile selection.
6. Persist:
   - current resolution row
   - immutable resolution run
7. Do not mutate canonical rule tables in this flow.

### 10.3 Coverage-candidate workflow

1. Load location’s resolved profile.
2. Aggregate candidate’s recent assigned/accepted/completed hours.
3. Evaluate rule profile against:
   - workweek window
   - workday window
   - consecutive-hours window
   - special rule conditions
4. Produce:
   - `projected_regular_hours`
   - `projected_ot_hours`
   - `projected_dt_hours`
   - `projected_cost_multiplier`
   - `status`
5. Store in `CoverageCandidate.scoring_factors["overtime_projection"]`.
6. Use that to adjust candidate ranking, not as the sole hard block.

## 11. Runtime Scoring Model

Replace the current generic `_overtime_risk_snapshot()` in [app/services/runtime_projections.py](/Users/carcam07/Backfill/app/services/runtime_projections.py) with a profile-driven evaluator.

Target output:

```json
{
  "profile_code": "us_ca_general_nonexempt",
  "jurisdiction_code": "US-CA",
  "status": "elevated",
  "projected_regular_hours": 32.0,
  "projected_ot_hours": 8.0,
  "projected_dt_hours": 0.0,
  "projected_cost_multiplier": 1.12,
  "reason_codes": ["daily_ot_triggered", "weekly_ot_not_triggered"],
  "evaluation_source": "deterministic_profile_engine"
}
```

This belongs inside candidate scoring factors, alongside cooldown, burden, and score-snapshot freshness.

## 12. Manual Override Model

Manual override is required.

Add support for:

- location-specific override to a different approved profile
- location-specific suppression of automatic LLM profile selection
- operator note on why the override exists

This should override automated resolution but not delete resolution history.

## 13. Configuration

Add these settings:

- `BACKFILL_LABOR_RULES_MODE=shadow|primary`
- `BACKFILL_LABOR_RULE_UPDATE_MODEL`
- `BACKFILL_LABOR_RULE_PROFILE_SELECTION_MODEL`
- `BACKFILL_LABOR_RULE_SOURCE_REFRESH_HOURS`
- `BACKFILL_LABOR_RULE_PROPOSAL_AUTOQUEUE=true|false`

Mode semantics:

- `shadow`
  - generate proposals and resolution runs
  - do not affect runtime ranking
- `primary`
  - location resolution affects runtime ranking
  - rule maintenance still requires approval before activating profile changes

## 14. Why Not Per-Location Rule Mutation

Do not use the pattern:

- new location created
- LLM reads state
- LLM writes or updates law rows directly for that customer

Problems:

- duplicates canonical state rules across customers
- creates drift between two California locations onboarded a month apart
- makes legal debugging nearly impossible
- makes source updates inconsistent
- turns law maintenance into onboarding side effects

The right ownership boundary is:

- canonical legal profile library is central
- location-specific selection is local

## 15. Rollout Plan

### Phase 0 — Schema and profile seeding

Build:

- `labor_rule_profiles`
- `labor_rule_profile_versions`
- `location_labor_rule_resolutions`
- `labor_rule_resolution_runs`
- initial seed profiles for:
  - FLSA baseline
  - California
  - Alaska
  - Colorado
  - Nevada
  - Oregon general
  - Oregon manufacturing

### Phase 1 — Shadow rule resolution

At location create/update:

- resolve profile in shadow mode
- persist resolution runs
- do not affect coverage scoring yet

### Phase 2 — Shadow runtime evaluation

During candidate ranking:

- evaluate profile-driven overtime projection
- write to scoring factors
- do not yet change ranking multiplier

### Phase 3 — Primary runtime ranking

Use `overtime_projection.projected_cost_multiplier` and `status` in ranking.

Still:

- no hard exclusion solely because of overtime
- unless a business-specific or rule-specific hard block is explicitly configured

### Phase 4 — Central rule maintenance

Add:

- source document ingestion
- LLM proposal generation
- reviewer workflow
- activation path for approved profile changes

### Phase 5 — Advanced industry-specific and conditional rules

Expand to:

- Nevada wage-threshold-sensitive selection
- Oregon industry-specific selection
- future public-works / union / hospital / manufacturing specializations

## 16. Repo Touchpoints

New files:

- `app/models/labor_rules.py`
- `app/services/labor_rules.py`
- `app/services/labor_rule_maintenance.py`
- `app/services/labor_rule_resolution.py`
- `tests/test_labor_rules.py`
- `tests/test_labor_rule_resolution.py`
- `tests/test_labor_rule_maintenance.py`
- Alembic migrations for the new tables

Existing files to update:

- [app/services/runtime_projections.py](/Users/carcam07/Backfill/app/services/runtime_projections.py)
- [app/services/coverage.py](/Users/carcam07/Backfill/app/services/coverage.py)
- [app/services/businesses.py](/Users/carcam07/Backfill/app/services/businesses.py)
- [app/services/onboarding.py](/Users/carcam07/Backfill/app/services/onboarding.py)
- [app/config.py](/Users/carcam07/Backfill/app/config.py)

## 17. Guardrails

- LLM output must be structured and bounded.
- LLM may propose profile changes; it may not auto-activate them.
- Location creation may select among existing profiles; it may not author new law.
- Runtime scoring must stay deterministic.
- Every automated decision must persist:
  - model
  - confidence
  - reason codes
  - input snapshot
  - selected profile
  - fallback reason if applicable

## 18. Final Decision

Use the LLM to keep the labor-rules system current, but **not** by regenerating rules per location.

The durable architecture is:

- one central, versioned labor-rule library
- one bounded LLM maintenance pipeline
- one bounded location-resolution pipeline
- one deterministic runtime evaluator

That gives Backfill a system that can stay current over time without turning onboarding into a law-writing side effect.
