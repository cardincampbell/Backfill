# PRD: Business Name Canonicalization and Location Suffix Derivation

## Document purpose
Define the backend logic, system behavior, and persistence model required for Backfill to derive a canonical business name from Google location data while safely separating branch- or locality-specific suffixes when confidence is sufficiently high.

This document is intentionally limited to:
- business name canonicalization logic
- locality and branch-label derivation logic
- confidence scoring
- persistence and data models
- APIs and services required to support derivation
- observability and evaluation

This document explicitly excludes:
- end-user experience
- review/edit screens
- admin flows
- product copy
- visual display rules for canonical vs raw names

---

## Problem statement
Backfill pulls business locations from Google Places and may receive names that combine a brand name with a locality or branch identifier, such as "Urth Caffe Pasadena" or "Urth Caffe Santa Monica".

The system needs to derive a stable canonical business name for grouping, analytics, and downstream product logic, while preserving locality-specific naming where appropriate.

The core challenge is ambiguity: some businesses append the city to a shared brand name, while others are genuinely named after a city or region. A naive string-stripper risks corrupting real business names.

---

## Goal
Given one or more Google-derived business locations, Backfill should:

1. preserve the raw Google-provided place name exactly as received
2. derive a canonical business name when confidence is sufficiently high
3. derive an optional location label when a locality or branch suffix is detected
4. store confidence, provenance, and derivation method for every derived output
5. support company- or brand-level grouping across multiple locations
6. support re-derivation as source data changes or better sibling evidence becomes available

---

## Non-goals
This phase will not:
- modify or overwrite the raw Google-provided place name
- define how canonical names are presented in UI
- rely on review text or NLP in the critical path
- use machine learning models in v1
- assign ownership or permissions based on canonicalized names
- assume every place belongs to a multi-location chain

---

## Core principles
1. Raw data is immutable.
2. Canonicalization is additive, never destructive.
3. The default behavior is to not split when confidence is low.
4. Multi-location confirmation is stronger than single-record heuristics.
5. Authoritative merchant-managed data outranks public Places heuristics.

---

## Source priority
The canonicalization engine should use source data in this priority order:

1. Backfill manual override or internal confirmed record
2. Google Business Profile location data, when available
3. Merchant clustering across multiple Google Places records
4. Single-location heuristic inference from Places data
5. Raw place name fallback

---

## Primary inputs

### Authoritative identity inputs
- merchant-provided canonical business name, if any
- Google Business Profile `title`, if connected
- Google Business Profile `storeCode`
- Google Business Profile `labels`
- website URI or domain

### Places inputs
- Places `displayName`
- Places `id` / resource identity
- `addressComponents`
- `formattedAddress`
- `shortFormattedAddress`
- `primaryType`
- `types`
- `websiteUri`
- phone numbers, if available

### Derived address tokens
The normalizer should extract and normalize candidate locality tokens from:
- locality
- sublocality
- neighborhood
- administrative area levels where useful
- common branch-like address identifiers

---

## Required outputs
For each place/location, the system must support the following output fields:

- `raw_place_name`
- `canonical_business_name`
- `location_label` nullable
- `name_derivation_confidence`
- `name_derivation_method`
- `derivation_version`
- `evidence_json`

Example:

```json
{
  "raw_place_name": "Urth Caffe Pasadena",
  "canonical_business_name": "Urth Caffe",
  "location_label": "Pasadena",
  "name_derivation_confidence": 0.94,
  "name_derivation_method": "multi_location_locality_suffix_match",
  "derivation_version": "v1.0"
}
```

---

## Derivation strategy
The engine should use a staged confidence-based pipeline.

### Stage 0: preserve source name
Always persist the exact source name before any derivation.

### Stage 1: authoritative source resolution
If any of the following are available and trusted, use them before heuristics:
- Backfill manual override
- confirmed internal canonical record
- Google Business Profile `title` if consistent across locations

If an authoritative source is accepted:
- set `canonical_business_name` from that source
- optionally derive `location_label` from auxiliary branch fields like `storeCode` or `labels`, if Backfill chooses to use them
- skip lower-confidence stripping logic unless needed for secondary enrichment

### Stage 2: merchant clustering
Before attempting to split names, group likely sibling locations into a merchant cluster.

Potential clustering signals:
- same verified merchant account or Business Profile linkage
- same website root domain
- high token overlap in names
- same primary category or highly similar types
- same phone root or business contact pattern
- same geographic region combined with matching brand tokens

The clustering engine must be conservative. False sibling grouping creates worse downstream errors than leaving names unsplit.

### Stage 3: suffix candidate extraction
Given a raw place name and normalized address tokens, generate candidate suffixes only from trailing tokens or trailing phrases.

Candidate examples:
- exact city/locality at end
- exact multi-word locality at end
- locality in parentheses at end
- locality after a separator such as `-`, `—`, `|`, or `:`

Examples:
- `Urth Caffe Pasadena` -> suffix candidate `Pasadena`
- `Urth Caffe - Pasadena` -> suffix candidate `Pasadena`
- `Urth Caffe (Santa Monica)` -> suffix candidate `Santa Monica`

Non-candidates:
- leading locality tokens such as `Boston Market`
- embedded locality tokens such as `Kansas City BBQ`
- non-terminal city mentions

### Stage 4: guardrails on candidate stripping
A candidate suffix may be stripped only if all minimum guardrails pass.

#### Guardrail A: suffix position
The locality token must appear at the end of the place name after normalization.

#### Guardrail B: exact token match
The suffix must match a normalized address-derived locality token exactly or through an approved alias mapping.

#### Guardrail C: meaningful remainder
The remaining candidate base name must be meaningful.

Initial v1 rules:
- minimum length >= 3 characters
- minimum word count >= 2 words for heuristic single-location stripping
- no empty or generic remainder

#### Guardrail D: separator normalization
The engine should normalize and remove benign separators around the suffix.

Supported separators:
- trailing spaces
- hyphen
- em dash
- pipe
- parentheses
- colon

#### Guardrail E: do-not-strip list
The engine must maintain a protected list and pattern set for risky names and common edge cases where geographic tokens are likely intrinsic to the brand.

Examples:
- `Boston Market`
- `Kansas City BBQ`
- `New York Pizza`
- `California Pizza Kitchen`

This protected layer should be treated as a precision safeguard, not the primary logic.

### Stage 5: sibling confirmation
Sibling confirmation is the strongest non-authoritative signal.

A strip candidate receives high confidence only when:
- multiple locations in the same merchant cluster share a stable base name, and
- each location has a different trailing locality token, and
- each trailing locality token matches that location's address-derived locality

Example:
- `Urth Caffe Pasadena`
- `Urth Caffe Santa Monica`
- `Urth Caffe Beverly Hills`

This pattern strongly supports:
- `canonical_business_name = Urth Caffe`
- `location_label = locality`

### Stage 6: single-location fallback
If sibling confirmation is unavailable, the system may still derive a canonical name using a lower-confidence single-location heuristic only when all of the following are true:
- suffix is at the end
- suffix exactly matches locality
- base remainder is meaningful and multi-word
- no protected-name rule is triggered
- no contradictory merchant evidence exists

Single-location fallback should be marked as medium confidence, never high confidence.

### Stage 7: fallback to raw
If confidence is below threshold, set:
- `canonical_business_name = raw_place_name`
- `location_label = null`

This is the default safe behavior.

---

## Confidence framework
Each derivation must include a confidence score from 0 to 1.

### Inputs to confidence
- authoritative source presence
- suffix exactness
- suffix position at end of string
- sibling confirmation strength
- merchant clustering confidence
- base-name quality after stripping
- address token quality
- contradiction penalties from protected-name rules or inconsistent siblings

### Example scoring model

```text
name_confidence =
  0.35 * authoritative_source_strength
+ 0.20 * sibling_confirmation_strength
+ 0.15 * merchant_cluster_confidence
+ 0.10 * suffix_exact_match
+ 0.10 * suffix_position_score
+ 0.05 * base_name_quality
- 0.05 * protected_name_penalty
```

### Thresholds
- 0.90 to 1.00: high-confidence canonicalization
- 0.70 to 0.89: medium-confidence canonicalization
- below 0.70: fallback to raw place name

Single-location heuristic derivations should generally cap below high-confidence unless reinforced by a trusted upstream source.

---

## Derived methods taxonomy
The system should persist an explicit derivation method.

Supported methods in v1:
- `manual_override`
- `internal_confirmed_record`
- `gbp_title`
- `multi_location_locality_suffix_match`
- `single_location_locality_suffix_match`
- `no_split_raw_fallback`

---

## Data model
The system must preserve both source and derived representations.

### Entities to store

#### 1. raw_location_identity_snapshot
Store the raw identity payload used during derivation.

Fields:
- snapshot_id
- company_id nullable
- location_id
- source_name
- source_record_id
- raw_place_name
- payload_json
- fetched_at
- hash

#### 2. normalized_location_identity_features
Store extracted canonicalization features.

Fields:
- feature_set_id
- location_id
- normalized_display_name
- normalized_address_tokens_json
- normalized_domain
- normalized_phone
- normalized_types_json
- clustering_features_json
- derivation_version
- created_at

#### 3. merchant_cluster
Store a probable merchant grouping used for sibling inference.

Fields:
- merchant_cluster_id
- cluster_confidence
- cluster_method
- created_at
- updated_at

#### 4. merchant_cluster_member
Fields:
- id
- merchant_cluster_id
- location_id
- membership_confidence
- created_at

#### 5. derived_business_identity
Store the derived naming outputs.

Fields:
- derived_identity_id
- location_id
- merchant_cluster_id nullable
- raw_place_name
- canonical_business_name
- location_label nullable
- confidence
- derivation_method
- derivation_version
- evidence_json
- status
- created_at
- updated_at

#### 6. canonical_business_record
Store a stable business-level identity for grouped locations.

Fields:
- canonical_business_id
- merchant_cluster_id nullable
- canonical_business_name
- canonical_name_confidence
- canonical_name_source
- active_location_count
- derivation_version
- created_at
- updated_at

---

## Idempotency and re-derivation
The derivation engine must support reruns without corrupting or duplicating identity records.

### Requirements
- identical source snapshots must not create duplicate active derived identities
- canonicalization runs must be versioned
- improvements in sibling evidence may upgrade a previously unsplit raw fallback to a canonicalized name
- if confidence decreases on rerun, prior values must remain auditable
- raw names must never be overwritten

### Change handling
When re-deriving:
- if output is unchanged, update timestamps only as needed
- if confidence changes materially, persist the new derived record or versioned state
- if a location changes cluster membership, recalculate canonical business identity
- never hard delete historical derivation evidence in v1

---

## APIs and services

### Service boundary
Backfill should expose a dedicated business identity derivation service.

### Required internal operations

#### 1. ingest location identity snapshot
Input:
- location_id
- raw source payload

Output:
- persisted raw snapshot

#### 2. normalize location identity features
Input:
- source snapshot id

Output:
- normalized feature set

#### 3. build or update merchant clusters
Input:
- normalized feature sets

Output:
- merchant clusters and memberships

#### 4. derive canonical business identity for a location
Input:
- location_id
- normalized feature set
- merchant cluster context

Output:
- derived business identity record

#### 5. derive or update canonical business record
Input:
- merchant cluster id

Output:
- canonical business record

#### 6. re-derive identity for a company or cluster
Input:
- company_id or merchant_cluster_id
- derivation_version

Output:
- updated derived identities and canonical business records

#### 7. read derived business identity
Input:
- location_id

Output:
- raw name, canonical name, location label, confidence, method, evidence

---

## Rule engine requirements
V1 should use deterministic rules.

### Requirements
- rules must be versioned
- all reason codes must be explicit and machine-readable
- string normalization must be deterministic
- address token extraction must be deterministic
- protected-name logic must be auditable
- cluster membership should be explainable

### Example reason codes
- `authoritative.gbp_title`
- `suffix.locality_at_end`
- `suffix.multiword_locality_match`
- `cluster.shared_base_name`
- `cluster.multiple_locality_suffixes`
- `guardrail.base_two_plus_words`
- `guardrail.protected_name_triggered`
- `fallback.raw_name_retained`

---

## Protected-name safeguards
The engine must include explicit protection against false stripping when geography is likely intrinsic to the brand.

### Safeguards
- never strip leading locality tokens
- never strip non-terminal locality tokens
- require exact end-position match for heuristic stripping
- require stronger evidence for brands containing common geographic phrases
- optionally maintain a curated exception list for known high-risk names

### Examples
Safe to leave untouched:
- `Boston Market`
- `Kansas City BBQ`
- `Pasadena Chicken`
- `Austin Grill`

Potentially safe to split only with sibling confirmation:
- `New York Pizza Pasadena`
- `California Fish Grill Pasadena`

---

## Observability and analytics
The system must emit structured events.

### Required events
- identity_snapshot_ingested
- identity_features_normalized
- merchant_cluster_updated
- business_identity_derived
- canonical_business_record_updated
- identity_derivation_run_completed
- identity_derivation_run_failed

### Metrics
- percent of locations left unsplit
- percent of high-confidence canonicalizations
- percent of sibling-confirmed canonicalizations
- percent of single-location heuristic canonicalizations
- false-positive correction rate from overrides
- top protected-name triggers
- average merchant cluster size

---

## Quality requirements

### Functional requirements
- preserve every raw Google-provided place name exactly
- derive canonical business names only when thresholds are met
- support optional location-label derivation
- support multi-location sibling confirmation
- expose confidence, method, and evidence for every derived result

### Performance requirements
- derive identity for a single location within 500 ms once normalization and cluster context are available
- process cluster-level re-derivation for up to 500 locations within 60 seconds

### Reliability requirements
- no destructive overwrites of source naming
- no silent canonicalization without evidence
- failures in one location must not corrupt cluster-level records

---

## Risks
- false sibling grouping across unrelated businesses with similar names
- false stripping for geography-based brands
- low-quality or incomplete address component data
- overconfidence in single-location heuristics
- inconsistent upstream naming across Places and Business Profile

---

## Guardrails
- prefer authoritative merchant-managed data over Places heuristics
- use sibling confirmation as the strongest non-authoritative signal
- treat single-location stripping as lower confidence
- preserve raw names always
- default to no split when uncertain
- do not use reviews or NLP in v1

---

## Acceptance criteria
The feature is complete when:

1. the system stores the raw Google-provided place name for every location
2. the system can derive and persist a canonical business name when confidence thresholds are met
3. the system can derive and persist an optional location label when supported by evidence
4. each derived identity includes confidence, method, version, and evidence
5. sibling locations with stable shared bases and locality suffixes canonicalize correctly
6. risky names with leading or embedded geographic terms are preserved when confidence is insufficient
7. rerunning derivation does not create duplicate active identity records

---

## Recommended implementation sequence

### Phase 1
- define normalized identity feature schema
- build raw snapshot ingestion
- build address token extraction
- build suffix candidate extraction and guardrails
- implement raw fallback behavior

### Phase 2
- build merchant clustering
- implement sibling-confirmed canonicalization
- build persistence for derived identity and canonical business records
- implement rerun and versioning behavior

### Phase 3
- add manual override support
- add protected-name exception list management
- add observability dashboards and correction analytics

---

## Summary
Backfill should implement a deterministic business identity derivation engine that preserves raw Google names while safely deriving canonical business names and optional location labels when evidence is strong enough.

The v1 system should prioritize source preservation, authoritative sources, sibling confirmation, explicit confidence scoring, and auditable persistence. When uncertainty remains, the system should retain the raw place name rather than risk corrupting the business identity.

