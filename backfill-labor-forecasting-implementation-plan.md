# Backfill Labor Forecasting Implementation Plan
**Status:** Proposed implementation plan  
**Date:** 2026-04-20  
**Purpose:** Define the scalable architecture for labor forecasting so Backfill can move from pattern-based predictive scheduling to a durable, replayable, data-rich forecasting system.

## 1. Problem Statement

Backfill now has the right scheduling seams, but it does not yet have a true forecasting backbone.

Current state:

- predictive scheduling is still primarily pattern-based
- weather is fetched live for the UI, not persisted as a planning input
- POS sales are not yet normalized into forecast features
- labor forecast tables exist, but they are not yet the active upstream producer for schedule generation

That is acceptable for the current release, but it is not the long-term architecture.

If Backfill wants labor forecasts to become accurate, explainable, and durable, the system needs:

- immutable feature snapshots
- provider-normalized operational facts
- a forecast engine interface that can support multiple model backends
- replay and backtesting before broad trust

## 2. Architectural Goals

- Make demand forecasting an upstream producer for shift shaping, not a sidecar or UI-only feature.
- Persist every input needed to explain or replay a forecast.
- Keep forecasting, shift shaping, assignment, and apply as separate services.
- Allow vendor or model swaps later without rewriting scheduler contracts.
- Degrade gracefully when data is sparse or unavailable.
- Build a strong baseline before introducing external ML complexity.

## 3. Non-Goals

- This plan does not replace the current pattern-based predictive scheduler immediately.
- This plan does not let a forecast engine assign employees directly.
- This plan does not hard-couple Backfill to one cloud or one model provider.
- This plan does not require an LLM anywhere on the critical forecasting path.

## 4. Core Design Principles

### 4.1 Immutable planning snapshots

Every predictive run must reference a frozen feature snapshot for its planning window.

That means:

- no live weather calls inside the optimizer path
- no direct POS API reads during schedule generation
- no recomputing feature inputs after the fact without a new snapshot id/hash

### 4.2 Fact tables first, model second

Forecast accuracy will come more from data quality and consistent feature generation than from prematurely choosing a sophisticated model backend.

The system should first build:

- normalized sales facts
- normalized attendance and callout facts
- persisted weather snapshots
- holiday and event facts

Then it can layer better models on top.

### 4.3 Provider abstraction at ingestion and at forecasting

The architecture needs two explicit seams:

1. `ExternalDataProvider` seam
   - POS
   - weather
   - events / holidays

2. `ForecastEngine` seam
   - heuristic baseline
   - internal statistical model
   - external ML backend if adopted later

Neither seam should leak provider-specific behavior into the scheduler.

### 4.4 Replayability over cleverness

Backfill should trust only forecast behavior that can be replayed, versioned, and compared to actual outcomes.

## 5. Target System Shape

The long-term pipeline should be:

1. Ingest external and internal operational facts
2. Normalize and persist those facts
3. Build a frozen feature snapshot for a location + planning window
4. Run demand forecasting on that snapshot
5. Convert demand points into proposed shifts
6. Run assignment optimization using existing labor, availability, and reliability logic
7. Store forecast and downstream schedule outcomes for replay and evaluation

Important boundary:

- forecasting predicts labor demand
- shift shaping converts demand into shifts
- assignment optimization chooses people
- apply persists draft changes

No single service should do all four.

## 6. Recommended Data Model

## 6.1 Source fact tables

These should be first-class persisted facts, not ad hoc JSON blobs buried in run metadata.

### `pos_sales_facts`

Purpose:

- canonical hourly or sub-hourly sales facts for forecasting

Minimum columns:

- `id`
- `business_id`
- `location_id`
- `provider`
- `provider_account_id`
- `provider_location_id`
- `observed_at`
- `bucket_start`
- `bucket_end`
- `gross_sales_cents`
- `net_sales_cents`
- `order_count`
- `guest_count`
- `refund_count`
- `source_payload`
- `ingested_at`
- `dedupe_key`

Rules:

- event time and ingestion time must both be stored
- dedupe must be deterministic by provider record identity
- late-arriving corrections must be supported without corrupting history

### `weather_forecast_snapshots`

Purpose:

- persist the exact weather forecast seen by the planner at run time

Minimum columns:

- `id`
- `business_id`
- `location_id`
- `provider`
- `forecast_generated_at`
- `forecast_valid_at`
- `bucket_start`
- `bucket_end`
- `temperature_f`
- `precipitation_probability`
- `precipitation_inches`
- `wind_speed_mph`
- `weather_code`
- `severity_flag`
- `source_payload`
- `ingested_at`

Rules:

- store the provider's forecast issue time, not just fetch time
- preserve multiple forecast revisions if they differ materially
- never depend on the live provider during predictive schedule generation

### `attendance_history_facts`

Purpose:

- learn true worked demand and staffing outcomes

Minimum columns:

- `id`
- `business_id`
- `location_id`
- `role_id`
- `shift_id`
- `employee_id`
- `starts_at`
- `ends_at`
- `scheduled_hours`
- `worked_hours`
- `attendance_status`
- `late_minutes`
- `left_early_minutes`
- `source_payload`

### `callout_history_facts`

Purpose:

- capture volatility and demand instability by location, role, and time bucket

Minimum columns:

- `id`
- `business_id`
- `location_id`
- `role_id`
- `shift_id`
- `occurred_at`
- `notice_minutes`
- `reason_code`
- `filled`
- `fill_latency_minutes`

### `calendar_event_facts`

Purpose:

- holidays, local events, school breaks, and special business periods

Minimum columns:

- `id`
- `business_id`
- `location_id`
- `source`
- `event_type`
- `event_name`
- `starts_at`
- `ends_at`
- `impact_scope`
- `source_payload`

## 6.2 Feature snapshot tables

These are the real contract boundary between data ingestion and forecasting.

### `demand_feature_snapshots`

Purpose:

- immutable header for a forecastable planning snapshot

Minimum columns:

- `id`
- `business_id`
- `location_id`
- `planning_window_start`
- `planning_window_end`
- `timezone_name`
- `bucket_minutes`
- `bucket_alignment_mode`
- `dst_handling_mode`
- `snapshot_hash`
- `feature_schema_version`
- `snapshot_status`
- `operating_hours_version`
- `source_summary`
- `created_at`

### `demand_feature_snapshot_points`

Purpose:

- row-wise forecast features by location, role, and time bucket

Minimum columns:

- `id`
- `demand_feature_snapshot_id`
- `location_id`
- `role_id`
- `bucket_start`
- `bucket_end`
- `feature_payload`
- `feature_vector_version`

Recommended payload contents:

- trailing sales aggregates
- trailing order counts
- historical scheduled demand
- historical worked demand
- attendance rate
- callout rate
- day-of-week
- week-of-year
- holiday flags
- event flags
- weather features
- operating-hours flags
- labor-target context

Design rule:

- row-wise points make replay and analytics easier than one giant snapshot blob
- `feature_payload` may contain versioned extras, but the table itself should remain queryable

## 6.3 Forecast tables

Existing tables are directionally correct:

- `labor_forecast_runs`
- `labor_forecast_points`

Recommended additions:

- `demand_feature_snapshot_id` foreign key on `labor_forecast_runs`
- `forecast_engine` field
- `baseline_model_family` field
- `confidence_band_metadata`
- `training_data_window_summary`

The existing `feature_snapshot_hash` should remain for contract stability, but a real foreign key should exist as well.

## 6.4 Forecast target contract

This contract must be explicit before implementation starts.

Authoritative shaping target:

- `labor_forecast_points.predicted_headcount`

Supporting audit and budgeting target:

- `labor_forecast_points.predicted_labor_hours`

Rules:

- `predicted_headcount` is the canonical demand target consumed by `shift_shaping`
- `predicted_headcount` represents required concurrent staffing for the bucket, expressed as a numeric value that may be fractional before shaping
- `predicted_labor_hours` is a companion metric used for budgeting, auditability, and accuracy reporting
- `predicted_labor_hours` should equal `predicted_headcount * bucket_duration_hours` unless an engine explicitly documents a different derivation
- if an engine cannot provide both values directly, it must still persist `predicted_headcount` and derive `predicted_labor_hours` deterministically at write time
- `shift_shaping` must never decide on its own whether headcount or labor-hours is authoritative; the contract is fixed here
- `shift_shaping` must apply one explicit materialization rule for fractional `predicted_headcount`, and that rule must be versioned

Fractional materialization note:

- forecast output may remain fractional at the demand layer
- `shift_shaping` is responsible for converting fractional concurrent demand into discrete seats or shifts
- the materialization rule must be explicit, deterministic, and replayable
- examples include ceiling by bucket, thresholded carry-forward, or contiguous demand smoothing, but only one active policy version may govern a run
- forecast accuracy and shaped-schedule evaluation must distinguish:
  - raw forecast error against fractional demand targets
  - shaping loss or inflation introduced when fractional demand is converted into discrete schedule artifacts

Why this contract:

- shift shaping needs a concurrency target to materialize real shifts
- labor-hours remain important, but they are the audit and budget lens, not the primary shaping input

## 6.5 Bucket and timezone contract

Bucket semantics must be fixed across ingestion, forecasting, shaping, and replay.

Rules:

- timezone of record is the location timezone pinned on `demand_feature_snapshots.timezone_name`
- buckets are aligned to local operating time in the location timezone, not to arbitrary UTC hour boundaries
- bucket boundaries should still be stored as timestamps that can be compared in UTC safely
- every snapshot must record `bucket_alignment_mode` and `dst_handling_mode`
- DST spring-forward gaps produce no synthetic local bucket for the missing hour
- DST fall-back overlaps produce two distinct buckets with distinct UTC instants even if the local clock label repeats
- downstream systems must use the snapshot's pinned timezone semantics, not the location's current timezone at replay time

Recommended implementation detail:

- store `bucket_start` / `bucket_end` as timezone-aware instants
- store local rendering fields only as optional helper metadata, never as the canonical identity of the bucket

## 7. Service Boundaries

## 7.1 `forecast_ingestion`

Responsibilities:

- pull POS provider data
- normalize provider payloads into fact tables
- refresh weather snapshots on schedule
- import holidays and events
- backfill missing history

Must not:

- compute forecasts
- shape shifts
- assign employees

## 7.2 `feature_snapshot_builder`

Responsibilities:

- gather all facts required for a planning window
- build consistent bucketed features
- write immutable snapshot header and points
- compute `snapshot_hash`
- fail closed if required minimum inputs are missing

Must not:

- fetch live provider data inline during schedule generation
- write shifts or assignments

## 7.3 `labor_forecasting`

Responsibilities:

- accept a feature snapshot
- run the selected forecast engine
- write `labor_forecast_runs` and `labor_forecast_points`
- record model/version metadata and confidence signals

Must not:

- mutate schedule state directly
- write shift assignments

## 7.4 `shift_shaping`

Responsibilities:

- convert demand points into proposed shifts
- honor business hours, role rules, minimum shift lengths, and operator templates

Must not:

- decide employee assignments

## 7.5 `auto_scheduler_assignment`

Responsibilities:

- optimize assignment against fixed and proposed shifts
- use availability, labor rules, fairness, and reliability inputs

Must not:

- call weather or POS providers
- infer demand from scratch

## 8. Run Contracts

Every predictive schedule preview should capture:

- `authoring_snapshot_hash`
- `demand_feature_snapshot_id`
- `demand_feature_snapshot_hash`
- `labor_forecast_run_id` if a real forecast exists
- `forecast_model_version`
- `forecast_engine`
- `operating_hours_version`
- `role_shift_constraints_version`
- `template_version` if templates influence shaping
- `shaping_policy_hash`
- `shift_shaping_version`
- `assignment_objective_version`

That gives Backfill three replay seams:

1. authoring replay
2. forecast replay
3. assignment replay

Important replay rule:

- forecast replay is not sufficient unless the shaping-policy inputs are also pinned
- a forecast may replay correctly while produced shifts still drift if business hours, role constraints, or templates changed

## 8.1 Shaping policy contract

The shaping layer must treat the following as explicit versioned inputs:

- business hours / operating hours version
- role-level shift constraints version
- template version if templates are enabled
- shift-shaping algorithm version

Those values should be recorded on the predictive run even when the forecast itself is unchanged.

## 9. Accuracy Strategy

Accuracy should be built in phases, not promised all at once.

### Phase 1 baseline

Use deterministic and statistical baselines first:

- historical median demand by location/role/daypart
- same-day-of-week recency weighting
- simple weather adjustments
- holiday/event overrides
- operating-hours-aware smoothing

This baseline is cheap, explainable, and auditable.

### Phase 2 richer statistical model

Once fact quality is stable, add:

- gradient-boosted regression or other tabular forecasting model
- confidence estimation
- sparse-data fallback logic by role/location

### Phase 3 optional external forecasting backend

Only after snapshotting and replay are mature should Backfill consider a heavier external stack.

If a Google-based backend is later used, it should sit behind `ForecastEngine` and consume the same immutable snapshot contract as every other backend.

That keeps vendor choice reversible.

## 10. Reliability Requirements

The forecast system should be treated like production infrastructure, not an analytics side project.

Minimum requirements:

- idempotent ingestion jobs
- deterministic snapshot building
- versioned feature schemas
- versioned forecast model metadata
- run-level structured errors
- stale-data detection
- missing-provider-data fallback paths
- replay and backtest tooling

### Fail-safe rules

- if POS data is stale, fall back to pattern-based demand
- if weather snapshots are unavailable, continue with weather-neutral forecast features
- if snapshot build fails, predictive scheduling must degrade to the existing heuristic path, not return opaque nonsense

## 10.1 Actuals finalization contract

Backtesting and accuracy scoring need a stable definition of when an "actual" is complete enough to score.

Rules:

- forecast accuracy must be computed only against finalized actuals, not against live mutable operational data
- finalization must be explicit and timestamped, not implied by query time
- actuals should be finalized at the bucket or business-day level, depending on the evaluation job design

Minimum finalization inputs:

- shift attendance updates have closed for the scored interval
- no-show and late attendance correction window has expired
- POS corrections for the scored interval have passed the provider-specific watermark
- any same-day manual cleanup jobs for that interval have completed

Recommended baseline policy:

- a bucket becomes scoreable only after `bucket_end + finalization_delay`
- initial `finalization_delay` should be conservative, for example 48 hours, until provider correction patterns are understood
- if provider-specific behavior requires longer windows, the watermark should win over the generic delay

Recommended persistence:

- `actuals_finalized_at`
- `actuals_finalization_policy_version`
- `actuals_completeness_status`

Important metric rule:

- dashboards may show provisional metrics internally, but release-gating accuracy metrics must use finalized actuals only

## 11. Phased Delivery Plan

## Phase A — Foundation

Deliver:

- `weather_forecast_snapshots`
- `pos_sales_facts`
- `attendance_history_facts`
- `callout_history_facts`
- ingestion jobs and cursors

Exit criteria:

- provider data is persisted reliably
- backfills can reconstruct at least 8 to 12 weeks of history per location

## Phase B — Snapshot layer

Deliver:

- `demand_feature_snapshots`
- `demand_feature_snapshot_points`
- snapshot builder service
- snapshot hashing and schema versioning

Exit criteria:

- any predictive run can reference a frozen feature snapshot
- snapshot payloads are inspectable and comparable

## Phase C — Baseline forecasting

Deliver:

- forecast engine interface
- heuristic/statistical baseline engine
- `labor_forecast_runs` linked to feature snapshots
- forecast confidence metadata

Exit criteria:

- demand forecasts are replayable
- baseline accuracy is measurable by location and role

## Phase D — Forecast-driven shift shaping

Deliver:

- shift shaping uses `labor_forecast_points` when available
- shift shaping consumes `predicted_headcount` as the authoritative shaping target
- shaping-policy versions are pinned on the predictive run
- pattern-based generation remains fallback

Exit criteria:

- predictive scheduling can run with or without a forecast provider
- source type is explicit: `historical_pattern`, `template`, or `forecast`
- forecast-driven shaping does not drift under replay when policy versions are held constant

## Phase E — Replay and model evaluation

Deliver:

- backtesting harness
- accuracy dashboards
- override and drift metrics
- actuals finalization and watermarking logic

Track at minimum:

- labor-hour error by bucket
- headcount error by bucket
- overtime delta vs actual
- manager override rate
- assignment match rate vs actual
- forecast confidence calibration

Release gate:

- model and shaping accuracy used for rollout decisions must be computed from finalized actuals only

## 12. Immediate Repo Implications

Likely new services:

- `app/services/forecast_ingestion.py`
- `app/services/feature_snapshot_builder.py`
- `app/services/forecast_engine.py`
- `app/services/forecast_backtesting.py`

Likely new models:

- `app/models/forecast_inputs.py`
- `app/models/forecast_snapshots.py`

Likely reuse points:

- `app/services/labor_forecasting.py`
- `app/services/shift_shaping.py`
- `app/services/auto_scheduler.py`
- `app/services/runtime_projections.py`

## 13. V1 Recommendation

Do this now:

- persist weather snapshots
- normalize POS facts
- build immutable feature snapshots
- attach forecast snapshot identity to future predictive runs
- keep using a baseline non-LLM demand model first

Do not do this yet:

- hardwire the system to one external ML vendor
- call live provider APIs during predictive schedule generation
- let the forecast module write assignments or publish schedules

## 14. Bottom Line

Backfill should optimize for:

- durable data contracts
- immutable snapshots
- replayability
- graceful fallbacks
- explainable baselines

The right long-term architecture is not "pick a fancy forecasting vendor first."

The right long-term architecture is:

- fact tables first
- snapshot contract second
- forecast engine behind an interface
- shift shaping downstream of forecast
- assignment optimization downstream of shift shaping

That is the path to a forecasting system that can get more accurate over time without turning the scheduler into an opaque, fragile black box.
