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
- remains auditable and centrally correctable
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
- Keep runtime behavior automatic and deterministic without per-location manual overrides.

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

`industry_profile_code` must not remain a loose string. It should resolve to a bounded taxonomy row from `labor_industry_profiles`, or be `null` for general profiles.

### 6.4 Industry taxonomy

Add a first-class bounded industry taxonomy instead of relying on free-form profile hints.

Use a table like:

- `labor_industry_profiles`
  - `code`
  - `display_name`
  - `description`
  - `jurisdiction_code` or `null` for shared cross-jurisdiction concepts
  - `is_active`
  - `metadata_json`

Examples:

- `general`
- `manufacturing`
- `hospitality`
- `healthcare`
- `public_works`

Rule profiles may reference one of these codes. Location-resolution logic may only choose among approved active industry taxonomy rows.

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
- `us_or_manufacturing` (future specialized profile)
- `us_nv_general_under_threshold` (future specialized profile)
- `us_nv_general_over_threshold` (future specialized profile)

### 7.2 `labor_industry_profiles`

Bounded taxonomy of industry-specific profile selectors.

Fields:

- `id`
- `code`
- `display_name`
- `description`
- `jurisdiction_code`
- `metadata_json`
- `is_active`
- `created_at`
- `updated_at`

### 7.3 `labor_rule_profile_versions`

Immutable history of each profile over time.

Fields:

- `id`
- `labor_rule_profile_id`
- `version_no`
- `payload_json`
- `change_summary`
- `created_by`
- `created_at`

Every persisted resolution or runtime evaluation must point back to one exact profile version, not just the mutable profile code.

### 7.4 `labor_rule_source_documents`

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

### 7.5 `labor_rule_update_proposals`

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

### 7.6 `location_labor_rule_resolutions`

Stores which profile a location currently resolves to and why.

Fields:

- `id`
- `location_id`
- `jurisdiction_code`
- `resolved_profile_code`
- `resolved_profile_version_id`
- `resolved_profile_payload_hash`
- `resolution_source`
- `resolution_confidence`
- `resolution_context_json`
- `llm_generation_id`
- `resolved_at`
- `created_at`
- `updated_at`

`resolution_source`:

- `deterministic`
- `llm`
- `fallback`

This table is authoritative runtime state. It should only be written in `primary` mode.

### 7.7 `labor_rule_resolution_runs`

Immutable history for location-profile selection.

Fields:

- `id`
- `location_id`
- `jurisdiction_code`
- `candidate_profile_codes`
- `selected_profile_code`
- `selected_profile_version_id`
- `selected_profile_payload_hash`
- `decision`
- `confidence`
- `reason_codes`
- `input_snapshot_json`
- `llm_generation_id`
- `created_at`

### 7.8 Resolution precedence

Resolution order must be explicit and deterministic.

Use this precedence:

1. **Authoritative location resolution**
   - the row in `location_labor_rule_resolutions` is the current runtime source of truth in `primary` mode
2. **Jurisdiction default deterministic resolution**
   - if no authoritative location resolution exists, derive from the active generic profile set for that jurisdiction
3. **No-profile fallback**
   - if no valid profile can be resolved, runtime must not invent one
   - instead it should emit a neutral unresolved overtime projection and a clear reason code such as `no_matching_labor_rule_profile`

Version lifecycle rules:

- historical runs and prior runtime decisions must always continue to point to the exact immutable version they used
- if an authoritative location resolution references a profile version that is expired, deactivated, or otherwise no longer valid for current runtime use, the runtime must treat that resolution as stale
- a stale authoritative resolution should trigger re-resolution before evaluation
- if re-resolution fails, use jurisdiction default deterministic resolution if available
- if that also fails, use the no-profile fallback and surface the unresolved state explicitly

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

In early phases, that means choosing among already-approved generic profiles only. Specialized Nevada and Oregon selection is deferred until the corresponding specialized profiles exist and are explicitly in scope.

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

## 9. Authoritative Hours Semantics

The deterministic evaluator must have an explicit contract before implementation. It cannot be left to emergent code behavior.

### 9.1 Timezone of record

- The timezone of record for evaluation is the candidate shift location timezone.
- Workday and workweek boundaries are evaluated in that timezone.
- This is not implicitly inherited from scheduler board display settings.
- If a future business needs a different legal workweek anchor, it must be represented explicitly in canonical rule metadata, not by per-location manual override.

### 9.2 Workweek boundary

- Every rule profile must define the authoritative local workweek anchor used for evaluation.
- Initial implementation should use a bounded field or structured `rules_json` value such as:
  - `workweek_start_day_local`
  - optional `workweek_start_time_local`
- If no specialized rule metadata exists, default to local midnight on the configured workweek start day.

### 9.3 Workday boundary

- Initial implementation uses the local calendar day in the candidate shift location timezone.
- If a jurisdiction later requires an alternate day boundary, that must be encoded explicitly in profile semantics and versioned.

### 9.4 Counted hour semantics

The first release should evaluate **gross scheduled hours**, not net payroll hours.

- unpaid breaks are not deducted unless Backfill later adds structured break segments
- completed shifts count full scheduled gross duration
- past assigned/accepted shifts whose scheduled window has ended count full scheduled gross duration
- in-progress shifts count elapsed scheduled duration clipped at the evaluation reference time
- future assigned/accepted shifts count as committed projected hours
- tentative or unaccepted offers do not count

### 9.5 Overlap handling

- Hours must be counted as the union of counted intervals, not the sum of raw assignment rows
- overlapping assignments for the same employee must be de-duplicated before totals are evaluated
- this applies across locations as long as those assignments are included in the same evaluation window

### 9.6 Mixed-jurisdiction limitation

Initial implementation assumes one governing rule profile per evaluation:

- the governing rule profile is the one resolved for the candidate shift location
- all counted intervals are evaluated against that profile’s workday/workweek semantics

If a business has materially mixed-jurisdiction workweeks, that is future specialized handling and should be surfaced as a limitation rather than hidden.

### 9.7 Runtime persistence

Every persisted runtime overtime projection must include:

- `profile_code`
- `profile_version_id`
- `profile_payload_hash`
- `jurisdiction_code`
- `evaluation_reference_time`
- `reason_codes`

### 9.8 Runtime performance contract

The overtime evaluator must not turn candidate ranking into per-candidate history queries.

Required runtime contract:

- candidate ranking works from a **batched hours snapshot** prepared ahead of scoring
- the snapshot is built for the full candidate set in one bounded query set, not ad hoc reads inside the scoring loop
- snapshot inputs must be grouped by the governing evaluation boundary:
  - employee id
  - jurisdiction/profile context
  - location timezone
  - relevant workday/workweek window
- the scoring loop must consume precomputed counted intervals or precomputed hour aggregates, not issue ORM lookups for each candidate
- no lazy-loading inside overtime scoring

Target shape:

```json
{
  "employee_id": "uuid",
  "profile_version_id": "uuid",
  "workday_window": {
    "start": "2026-04-17T07:00:00+00:00",
    "end": "2026-04-18T07:00:00+00:00"
  },
  "workweek_window": {
    "start": "2026-04-13T07:00:00+00:00",
    "end": "2026-04-20T07:00:00+00:00"
  },
  "counted_intervals": [],
  "gross_hours_by_window": {
    "workday": 6.0,
    "workweek": 34.0,
    "projected_with_candidate_shift": 40.0
  }
}
```

Performance objective:

- one coverage planning run should do a bounded number of batch reads for all candidates in that run
- the complexity should be closer to `O(batch fetch + candidate scoring)` than `O(candidates * history lookup)`
- if a future rule requires more expensive evaluation, that cost should be pushed into the snapshot builder, not scattered through ranking code

## 10. Service Architecture

### 10.1 New service: `app/services/labor_rules.py`

Owns:

- loading active rule profiles
- resolving rule profiles for a location
- deterministic profile evaluation
- applying system-level mode and fallback controls

Key functions:

- `resolve_jurisdiction_code(location) -> str`
- `active_profiles_for_jurisdiction(session, jurisdiction_code) -> list[...]`
- `resolve_location_rule_profile(session, location, business) -> ResolutionResult`
- `evaluate_overtime_projection(profile_version, *, candidate_shift, counted_intervals, reference_time) -> dict`

### 10.2 New service: `app/services/labor_rule_maintenance.py`

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

### 10.3 New service: `app/services/labor_rule_resolution.py`

Owns:

- location-level profile selection
- deterministic resolution
- bounded LLM fallback
- immutable run logging

Key functions:

- `resolve_location_profile(...)`
- `run_llm_profile_selection(...)`
- `persist_resolution_run(...)`

## 11. LLM Workflow Design

### 11.1 Rule-maintenance workflow

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

### 11.2 Location-create workflow

1. Location is created with `region`, `country_code`, `timezone`, place metadata, and business classification context.
2. Resolve `jurisdiction_code` from `country_code + region`.
3. Load active profiles for that jurisdiction.
4. If exactly one generic profile applies, resolve deterministically.
5. If multiple profiles are plausible, run bounded LLM profile selection against approved active profile codes only.
6. Persist:
   - in `shadow` mode: immutable resolution run only
   - in `primary` mode: current authoritative resolution row plus immutable resolution run
7. Do not mutate canonical rule tables in this flow.

### 11.3 Coverage-candidate workflow

1. Load location’s resolved profile.
2. Load the exact resolved profile version used by that resolution.
3. Build counted intervals using the authoritative hours semantics:
   - past completed and ended assigned/accepted shifts
   - elapsed portion of in-progress shifts
   - future committed assigned/accepted shifts
   - interval-union de-duplication for overlaps
4. Evaluate the profile version against:
   - workweek window
   - workday window
   - consecutive-hours window
   - special rule conditions
5. Produce:
   - `projected_regular_hours`
   - `projected_ot_hours`
   - `projected_dt_hours`
   - `projected_cost_multiplier`
   - `status`
6. Store in `CoverageCandidate.scoring_factors["overtime_projection"]`.
7. Use that to adjust candidate ranking, not as the sole hard block.

## 12. Runtime Scoring Model

Replace the current generic `_overtime_risk_snapshot()` in [app/services/runtime_projections.py](/Users/carcam07/Backfill/app/services/runtime_projections.py) with a profile-driven evaluator.

Target output:

```json
{
  "profile_code": "us_ca_general_nonexempt",
  "profile_version_id": "3a06f875-2cfe-44b0-9e83-2a0b81e9f2a1",
  "profile_payload_hash": "sha256:2a9f1b...",
  "jurisdiction_code": "US-CA",
  "status": "elevated",
  "projected_regular_hours": 32.0,
  "projected_ot_hours": 8.0,
  "projected_dt_hours": 0.0,
  "projected_cost_multiplier": 1.12,
  "reason_codes": ["daily_ot_triggered", "weekly_ot_not_triggered"],
  "evaluation_source": "deterministic_profile_engine",
  "evaluation_reference_time": "2026-04-17T18:00:00+00:00"
}
```

This belongs inside candidate scoring factors, alongside cooldown, burden, and score-snapshot freshness.

## 13. Runtime Policy Boundary

Per-location manual override is intentionally out of scope.

Backfill is not a payroll engine and should not create a secondary human-managed law-resolution path at runtime.

Instead:

- the canonical labor-rule library is maintained centrally
- location/profile resolution stays automatic
- runtime uses labor rules as a prioritization signal, not a payroll-adjudication engine
- if no valid profile can be resolved, runtime falls back to a neutral unresolved projection instead of inventing or manually forcing a profile

This means Backfill may prioritize a lower-overtime-risk employee ahead of a higher-reliability employee, but it does not hard-disqualify employees solely because they are near overtime thresholds unless an explicit future rule requires that.

## 14. Configuration

Add these settings:

- `BACKFILL_LABOR_RULES_MODE=shadow|primary`
- `BACKFILL_LABOR_RULE_UPDATE_MODEL`
- `BACKFILL_LABOR_RULE_PROFILE_SELECTION_MODEL`
- `BACKFILL_LABOR_RULE_SOURCE_REFRESH_HOURS`
- `BACKFILL_LABOR_RULE_PROPOSAL_AUTOQUEUE=true|false`

Mode semantics:

- `shadow`
  - generate proposals and immutable resolution runs
  - do **not** write `location_labor_rule_resolutions`
  - do not affect runtime ranking
- `primary`
  - write authoritative location resolutions
  - location resolution affects runtime ranking
  - rule maintenance still requires approval before activating profile changes

## 15. Why Not Per-Location Rule Mutation

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

## 16. Rollout Plan

### Phase 0 — Schema and generic profile seeding

Build:

- `labor_rule_profiles`
- `labor_industry_profiles`
- `labor_rule_profile_versions`
- `location_labor_rule_resolutions`
- `labor_rule_resolution_runs`
- initial generic profiles for:
  - FLSA baseline
  - California
  - Alaska
  - Colorado
  - Nevada general fallback
  - Oregon general fallback

Do **not** implement specialized Nevada threshold variants or Oregon industry variants yet.

### Phase 1 — Shadow generic rule resolution

At location create/update:

- resolve generic profile in shadow mode
- persist immutable resolution runs only
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

### Phase 5 — Specialized industry-specific and conditional rules

Expand to:

- Nevada wage-threshold-sensitive profile families
- Oregon industry-specific profile families
- bounded industry profile selection
- future public-works / union / hospital / manufacturing specializations

## 17. Repo Touchpoints

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

## 18. Guardrails

- LLM output must be structured and bounded.
- LLM may propose profile changes; it may not auto-activate them.
- Location creation may select among existing profiles; it may not author new law.
- Runtime scoring must stay deterministic.
- Runtime overtime projections are ranking inputs by default, not automatic hard exclusions.
- There is no per-location manual override path for labor-rule resolution.
- Every automated decision must persist:
  - model
  - confidence
  - reason codes
  - input snapshot
  - selected profile
  - selected profile version id
  - selected profile payload hash
  - fallback reason if applicable

## 19. Final Decision

Use the LLM to keep the labor-rules system current, but **not** by regenerating rules per location.

The durable architecture is:

- one central, versioned labor-rule library
- one bounded LLM maintenance pipeline
- one bounded location-resolution pipeline
- one deterministic runtime evaluator

That gives Backfill a system that can stay current over time without turning onboarding into a law-writing side effect.
