# Backfill — Data Model & Coverage Engine Spec
**Version:** 1.0  
**Scope:** Phase 1 (single-location internal pool) & Phase 2 (cross-location internal broadcast)  
**Prepared for:** Dev Team

---

## Overview

Backfill is a labor liquidity engine — not a scheduler, not a pager. It matches supply (employees who can work) against demand (shifts that need filling) using two distinct supply/demand relationships and a prioritized coverage engine that gets smarter over time.

This document covers:
1. The core data model
2. The two supply/demand relationships
3. The coverage engine logic
4. The three operational modes
5. The reliability/probability scoring system
6. Phase 1 and Phase 2 scope boundaries

---

## 1. Core Hierarchy

```
Business
  ├── Locations
  ├── Roles
  └── Employees
        ├── Availability
        ├── Roles
        └── Location Eligibility / Clearance

Schedule
  └── Shifts
        └── ShiftAssignments

Callout
  └── CoverageCampaign
        ├── CampaignRounds
        ├── CampaignCandidates
        └── OutreachAttempts
```

**Key principles:**

- **Employees belong to the Business, not to a Location.** This is the architectural decision that enables cross-location coverage in Phase 2. An employee can fill a shift at any location under their business — their role assignments and availability determine eligibility, not their "home" location.
- **Location eligibility is still a first-class permission layer.** Employees belong to the Business, but they may still need explicit clearance to work specific locations. Cross-location eligibility is not implied by mere business membership.
- **Roles belong to the Business.** A "Server" is a "Server" across all locations. Roles are defined once at the business level, then assigned to locations and employees independently.
- **Shifts use canonical intervals.** A shift is a role needed, at a place, over a timezone-aware interval. Do not model the canonical shift window as separate `DATE` + `TIME` fields.
- **Assignments are their own durable model.** Do not rely on a single nullable foreign key on the shift row as the durable assignment record.
- **Availability belongs to Employees.** Availability is the supply signal — when an employee can work, regardless of where.
- **Callout is a trigger, not the canonical aggregate.** The campaign is the operational, billing, and observability object.

---

## 2. The Two Supply/Demand Relationships

There are two distinct matching problems Backfill solves simultaneously. Both must be true for an employee to be a valid coverage candidate.

---

### Relationship 1 — Capability (Structural Match)

> *Can this employee fill this role at this location?*

```
Demand:  Location needs a Role filled
Supply:  Employee holds that Role qualification
Bridge:  Roles (the permission/capability layer)
Nature:  Static, binary — you either qualify or you don't
```

This is established during onboarding and updated when an operator adds or removes role qualifications from an employee. It doesn't change shift-to-shift.

---

### Relationship 2 — Availability (Temporal Match)

> *Can this employee work this specific shift window?*

```
Demand:  Shift (specific date, start time, end time)
Supply:  Employee availability (when they can work)
Bridge:  The shift itself (the scheduling layer)
Nature:  Dynamic — changes week to week, day to day
```

Availability has two sub-layers:

**Recurring availability** — standing weekly template
```
"I'm available Monday, Wednesday, Friday from 4 PM onward"
"I'm never available Sunday mornings"
```

**Explicit exceptions** — one-off overrides to the recurring template
```
"I'm unavailable April 15th — concert"
"I'm available this Saturday even though I usually don't work Saturdays"
```

Exceptions always override the recurring template for that specific date.

---

### The Intersection — Valid Coverage Candidate

```
Valid Candidate =
  Employee holds the required Role           (Relationship 1: Capability)
  AND Employee is available for the window   (Relationship 2: Availability)
  AND Employee is not already on a shift     (Conflict check)
```

Formally:

```
Candidate = (Employee_Role ∩ Location_Role) ∧ (Employee_Availability ∩ Shift_Time)
```

If you only check Capability: you ping people who are asleep or at another job.  
If you only check Availability: you send a dishwasher to cover a bartender shift.  
Both gates must pass.

---

## 3. Database Schema

### Naming Convention

Table names use a prefix to make hierarchy and ownership self-documenting:

```
Business level:    businesses, roles
Location level:    locations, location_roles, shifts
Employee level:    employees, employee_roles, employee_availability_rules, employee_availability_exceptions
Operational:       callouts, coverage_campaigns, outreach_attempts, shift_assignments
```

The supply/demand symmetry is explicit in the naming:

```
DEMAND                    BRIDGE     SUPPLY
────────────────────────────────────────────────
location_roles            Roles      employee_roles
shifts                    Time       employee_availability_rules / employee_availability_exceptions
```

---

### `businesses`
```
id                UUID, primary key
name              VARCHAR
created_at        TIMESTAMP
```

### `locations`
```
id                UUID, primary key
business_id       UUID, FK → businesses
name              VARCHAR
address           VARCHAR
place_id          VARCHAR        -- Google Places ID
city              VARCHAR
state             VARCHAR
is_active         BOOLEAN
created_at        TIMESTAMP
```

### `roles`
```
id                UUID, primary key
business_id       UUID, FK → businesses
name              VARCHAR        -- "Server", "Line Cook", "Bartender"
created_at        TIMESTAMP
```

Roles belong to the Business, not a Location. The same role definition is shared across all locations under that business. `location_roles` scopes which roles are active at which location.

### `location_roles` ← demand side, capability
```
id                UUID, primary key
location_id       UUID, FK → locations
role_id           UUID, FK → roles
```

Defines which roles exist at which location. A role must appear in `location_roles` before a shift can require it at that location. This is the demand signal for the capability relationship.

### `shifts` ← demand side, temporal
```
id                UUID, primary key
location_id       UUID, FK → locations
role_id           UUID, FK → roles
business_id       UUID, FK → businesses
timezone          VARCHAR
starts_at         TIMESTAMPTZ
ends_at           TIMESTAMPTZ
schedule_status   ENUM           -- draft | published | active | completed | cancelled
seats_requested   INTEGER
created_at        TIMESTAMP
updated_at        TIMESTAMP
```

This is the demand signal for the temporal relationship. A shift is a specific need — a role, at a location, over a canonical interval.

Schedule lifecycle:
```
draft  →  published  →  active  →  completed
                         └──────→ cancelled
```

Coverage lifecycle is not stored on `shifts.schedule_status`. Coverage state belongs to `coverage_campaigns`.

### `shift_assignments`
```
id                UUID, primary key
shift_id          UUID, FK → shifts
employee_id       UUID, FK → employees, NULLABLE
status            ENUM           -- proposed | assigned | accepted | declined | cancelled | replaced | completed
sequence_no       INTEGER
assigned_via      VARCHAR        -- manual | campaign | scheduler_sync
replaced_assignment_id UUID, FK → shift_assignments, NULLABLE
accepted_at       TIMESTAMP
cancelled_at      TIMESTAMP
created_at        TIMESTAMP
updated_at        TIMESTAMP
```

`shift_assignments` is the durable assignment history and race-control surface. Do not treat a nullable employee FK on the shift row as sufficient for auditability or blast-mode correctness.

### `employees`
```
id                UUID, primary key
business_id       UUID, FK → businesses
first_name        VARCHAR
last_name         VARCHAR
phone             VARCHAR        -- E.164 format (+13105550100)
email             VARCHAR
status            ENUM           -- active, inactive
reliability_score DECIMAL(4,3)   -- optional cached snapshot, not the authoritative fact source
created_at        TIMESTAMP
```

### `employee_roles` ← supply side, capability
```
id                UUID, primary key
employee_id       UUID, FK → employees
role_id           UUID, FK → roles
assigned_at       TIMESTAMP
```

The supply signal for the capability relationship. An employee can hold multiple roles. Paired with `location_roles` to determine whether an employee is qualified for a specific shift at a specific location.

### `employee_availability_rules` and `employee_availability_exceptions` ← supply side, temporal
```
Recurring rules:
  employee_id
  day_of_week
  start_local_time
  end_local_time
  timezone

Exceptions:
  employee_id
  starts_at
  ends_at
  exception_type    -- available | unavailable
  reason
```

The logical model is recurring rules plus dated exceptions. A temporary combined storage table may be acceptable early, but the engine should treat them as separate concepts and plan for projection-driven eligibility reads over time.

**Recurring example:** Available every Friday 4 PM – midnight  
**Exception example:** Unavailable April 15th (concert) / Available this Saturday despite no recurring Saturday availability

### `callouts`
```
id                UUID, primary key
shift_id          UUID, FK → shifts
reported_by       UUID, FK → employees  -- who called out
reported_at       TIMESTAMP
initiated_by      ENUM           -- employee | manager | system
status            ENUM           -- received | campaign_started | resolved
created_at        TIMESTAMP
```

`callout` is the trigger record. It is not the canonical operational aggregate.

### `coverage_campaigns`
```
id                UUID, primary key
shift_id          UUID, FK → shifts
callout_id        UUID, FK → callouts
location_id       UUID, FK → locations
business_id       UUID, FK → businesses
status            ENUM           -- created | scoring | outreach_active | filled | exhausted | escalated | cancelled | closed
mode              ENUM           -- standard | compressed | blast
filled_by_employee_id UUID, FK → employees, NULLABLE
opened_at         TIMESTAMP
closed_at         TIMESTAMP
created_at        TIMESTAMP
updated_at        TIMESTAMP
```

The campaign is the canonical business object for coverage execution, billing, and observability.

### `outreach_attempts`
```
id                UUID, primary key
coverage_campaign_id UUID, FK → coverage_campaigns
employee_id       UUID, FK → employees
rank              INTEGER        -- position in the ranked list or blast cohort
channel           ENUM           -- sms | voice
provider          VARCHAR        -- retell | twilio_verify | etc.
idempotency_key   VARCHAR
dedupe_key        VARCHAR
attempt_status    ENUM           -- queued | sent | delivered | awaiting_response | accepted | declined | no_response | no_answer | expired | cancelled | failed
requested_at      TIMESTAMP
sent_at           TIMESTAMP
responded_at      TIMESTAMP
expires_at        TIMESTAMP
response_time_seconds  INTEGER   -- null if no response
created_at        TIMESTAMP
```

Every outreach attempt is logged regardless of outcome. This append-only fact stream feeds projections, scoring snapshots, and cost tracking.

---

## 4. Time and Concurrency Invariants

These are platform rules, not implementation details.

### Canonical time model

- Shifts use `starts_at` and `ends_at` as timezone-aware timestamps.
- Local display is derived from `timezone`; it is not the canonical storage format.
- Overlap checks use half-open interval semantics: `[starts_at, ends_at)`.
- Overnight shifts and DST boundaries must be handled by interval math, not by naive `DATE` + `TIME` comparisons.

### Canonical race rules

- One active coverage campaign per shift seat at a time.
- One winning acceptance per campaign.
- Blast mode "first confirm wins" must be enforced by database-backed constraints or compare-and-swap rules, not by application timing alone.
- Provider callbacks must be idempotent.
- Shift assignment writes must be idempotent and concurrency-safe.

### Projection rule

- Early proof-of-concept candidate resolution may read authoring tables directly.
- The target execution model should converge on engine-facing projections for eligibility, compiled availability, and scoring snapshots rather than permanent heavy live joins over authoring tables.

---

## 5. The Coverage Engine

When a callout is received, the coverage engine executes in this sequence:

### Step 1 — Trigger and Campaign Creation
```
current assignment marked replaced/cancelled as appropriate
callouts record created
coverage_campaigns record created
```

### Step 2 — Candidate Resolution

Candidate resolution applies these checks:

- role/certification match
- location eligibility / clearance
- availability over the canonical shift interval
- no conflicting accepted or active assignment
- active employee status
- exclude the employee who called out
- exclude already-contacted candidates for the same campaign

**Phase 1 (single location):**

- resolve from employees eligible for the target location

**Phase 2 (cross-location):**

- resolve from the broader business employee pool
- still require explicit location eligibility / clearance for the target location

Phase 2 activates when Phase 1 returns zero candidates, or when the operator has enabled cross-location coverage in their settings.

### Step 3 — Rank the Candidate List

Candidates are ranked by **Probability of Acceptance (PoA)** — a composite score derived from:

```
PoA = weighted combination of:
  - reliability_score           (historical acceptance rate)
  - avg_response_time           (how quickly they typically respond)
  - day_of_week_affinity        (do they often pick up shifts on this day?)
  - time_of_day_affinity        (do they often pick up shifts at this hour?)
  - recency_bonus               (have they been responsive in the last 30 days?)
  - location_affinity           (Phase 2: have they worked this location before?)
```

See Section 7 for full scoring details.

### Step 4 — Determine Operating Mode

Based on time remaining until shift start:

```
T-minus 12+ hours  →  Mode 1: Standard Queue
T-minus 4-12 hours →  Mode 2: Compressed Queue
T-minus <4 hours   →  Mode 3: Blast
```

### Step 5 — Execute Outreach

See Section 6 for mode-specific execution logic.

### Step 6 — Resolution

**On confirmation:**
```
winning shift_assignment written for confirmed_employee_id
coverage_campaigns.status = 'filled'
callouts.status = 'resolved'
winning outreach_attempts.attempt_status = 'accepted'
all pending outreach attempts cancelled
Confirmation sent to employee
Notification sent to operator
```

**On exhausting the list:**
```
coverage_campaigns.status = 'exhausted'
callouts.status = 'resolved'
Operator notified immediately
```

---

## 6. Three Operating Modes

The engine selects the operating mode automatically based on time-to-shift-start. The operator never sees or selects a mode — they only see outcomes.

---

### Mode 1 — Standard Queue
**Trigger:** Shift starts in 12+ hours  
**Logic:** Sequential outreach, one candidate at a time  
**Wait window:** 5 minutes per candidate before moving to next  
**Rate:** Standard hourly rate

```
Contact candidate #1
  → Confirmed: done
  → Declined / No answer after 5 min: move to #2
Contact candidate #2
  → ...and so on
```

---

### Mode 2 — Compressed Queue
**Trigger:** Shift starts in 4–12 hours  
**Logic:** Sequential outreach, tighter windows  
**Wait window:** 2 minutes per candidate  
**Rate:** Standard rate. If operator has pre-authorized a shift premium, it becomes available after 5 failed attempts.

```
Contact candidate #1 (2 min window)
  → ...
After 5 declines/no-answers:
  → If operator has set premium_rate: offer premium to remaining candidates
  → If no premium set: continue at standard rate
```

---

### Mode 3 — Blast
**Trigger:** Shift starts in less than 4 hours  
**Logic:** Simultaneous broadcast to top N candidates (recommended: top 5–8 by PoA score)  
**Wait window:** None — first to confirm gets the shift  
**Rate:** If operator has pre-authorized a premium, it is automatically included in the blast offer

```
Simultaneously contact candidates #1 through #N
"[Shift details]. First to confirm gets the shift [+ $X bonus if applicable]."
First confirmation received:
  → Shift assigned to that employee
  → All other offers cancelled immediately
  → Remaining candidates notified shift is filled
```

**Important:** Mode 3 is a competitive offer, not a sequential one. The engine must handle simultaneous confirmations gracefully — only the first counts, subsequent confirmations receive a "shift already filled" response.

---

### Operator-Authorized Shift Premiums

Backfill does not set compensation. The operator defines premium rules in advance. The engine deploys them at the right moment.

```
premium_rules (operator-configured)
  └── business_id
  └── trigger: ENUM (attempts_exceeded | mode_escalation | both)
  └── attempts_threshold: INTEGER  (e.g., after 5 no-fills)
  └── premium_amount: DECIMAL      (e.g., $5.00 added to hourly rate)
  └── max_premium: DECIMAL         (ceiling — engine won't exceed this)
```

The AI never autonomously offers compensation beyond what the operator has pre-authorized. This protects the operator legally and financially.

---

## 7. Reliability Score & Probability of Acceptance

### Reliability Score

Derived from append-only outreach attempt facts and maintained as a projection or snapshot. For launch compatibility, a cached snapshot may still be surfaced on the employee record, but the authoritative source is attempt history. Uses a **30-day rolling window** — recent behavior weighted more heavily than historical.

```
reliability_score = (
  (confirmed_count / total_attempts) * 0.5     -- acceptance rate
  + response_speed_score * 0.3                  -- how fast they respond
  + recency_score * 0.2                          -- behavior in last 30 days
)
```

**Decay:** Attempts older than 30 days are down-weighted. Attempts older than 90 days are excluded entirely. An employee with a strong 6-month-old track record but who has ghosted the last 5 calls should score lower than one with a shorter but more recent track record.

**Initial score:** New employees start at `0.700` (neutral/slightly positive) until enough outreach attempt facts exist to generate a meaningful score. Threshold: 5 attempts minimum before score is fully trusted, with smoothing and low-sample safeguards applied.

### Probability of Acceptance (PoA)

PoA is calculated from the reliability/response snapshot plus shift context. The engine may cache or snapshot the result for execution, but it should remain explainable and reproducible from the underlying factors:

```
PoA = reliability_score
  * day_of_week_affinity_multiplier    (0.7 – 1.3)
  * time_of_day_affinity_multiplier    (0.7 – 1.3)
  * location_affinity_multiplier       (0.9 – 1.1, Phase 2 only)
```

**Affinity multipliers** are derived from historical outreach attempt data for that employee:
- If they've accepted 80% of Friday night shifts they've been offered → Friday night multiplier = 1.3
- If they've declined every Sunday morning offer → Sunday morning multiplier = 0.7

Over time PoA becomes a highly personalized signal per employee per shift context. In early operation (few data points), it degrades gracefully to the base reliability score.

---

## 8. Callout Flow — End to End

```
1. CALLOUT RECEIVED
   Employee calls/texts Backfill to report callout
   OR manager marks shift as open in dashboard
   OR integrated scheduler signals a gap

2. CAMPAIGN OPENED
   existing assignment adjusted as needed
   callouts record created
   coverage_campaigns record created

3. CANDIDATE QUERY
   Run capability + location eligibility + availability + conflict check
   Returns ordered list ranked by PoA

4. MODE DETERMINED
   Based on time_to_shift_start
   Mode 1 / Mode 2 / Mode 3 selected

5. ENGINE EXECUTES
   Outreach goes out per mode logic
   outreach_attempts logged for every contact

6. RESOLUTION
   Filled → winning assignment written, all parties notified
   No-fill / exhausted → operator notified, campaign closed accordingly

7. SCORING UPDATED
   Every outreach attempt outcome updates:
   - reliability / response projections
   - response_time logged
   - day/time affinity data updated
```

---

## 9. Phase Boundaries

### Phase 1 — Single Location, Internal Pool

**Candidate query scope:** Employees cleared for the same location as the shift  
**Cross-location:** Not enabled  
**External workers:** Not enabled  
**Premium rules:** Operator-configured, optional  
**Scheduler integrations:** 7shifts, Deputy, When I Work, Homebase (via API sync)  
**Backfill Shifts:** Available for operators without a scheduler

**Definition of done for Phase 1:**
- Location created
- Roles defined
- Employees uploaded with phone numbers and role assignments
- Availability recorded (recurring at minimum)
- At least one shift scheduled
- Callout creates a campaign and triggers candidate resolution
- Engine executes outreach according to mode logic
- Shift confirmed and assigned

---

### Phase 2 — Cross-Location, Internal Pool

**Candidate query scope:** All employees under the Business who are explicitly eligible for the target location  
**Trigger:** Phase 1 query returns zero candidates, OR operator has enabled cross-location coverage  
**Cross-location opt-in:** Configured at the Business level. Operators can also flag specific roles or locations as cross-location eligible/ineligible.  
**Candidate ranking addition:** `location_affinity_multiplier` added to PoA — employees who have worked a location before rank higher than those who haven't  
**External workers:** Still not enabled (Phase 3)

**Location eligibility considerations for Phase 2:**
- Employees still belong to the Business, but location eligibility remains a first-class clearance layer
- Employee must have worked at, been explicitly cleared for, or otherwise been granted access to the target location to be included
- Add `employee_location_clearance` table:

```
employee_location_clearance
  └── employee_id
  └── location_id
  └── cleared_by        -- manager who approved
  └── cleared_at        TIMESTAMP
```

This prevents Backfill from sending an employee to a location they've never been to and the manager doesn't know them.

---

## 10. Roster Upload Format

For Phase 1 testing, the minimum viable roster CSV:

```
first_name, last_name, phone, roles, availability, status
Marcus, Johnson, +13105550101, "Server|Bartender", "MON:16:00-23:00|FRI:16:00-23:00|SAT:14:00-23:00", active
Priya, Kapoor, +13105550102, "Server", "TUE:11:00-22:00|WED:11:00-22:00|THU:11:00-22:00", active
Jordan, Thomas, +13105550103, "Line Cook", "MON:06:00-15:00|TUE:06:00-15:00|WED:06:00-15:00|THU:06:00-15:00", active
```

**Field rules:**
- `phone`: E.164 format required (+1XXXXXXXXXX). Reject and flag any record without a valid phone number — phone is required for Backfill to function.
- `roles`: Pipe-delimited. Must match an existing role name at the business. Case-insensitive match acceptable. Flag unrecognized role names for operator review — do not silently drop them.
- `availability`: Pipe-delimited. Format: `DAY:HH:MM-HH:MM`. 24-hour time. Multiple windows per day acceptable (`MON:06:00-14:00|MON:18:00-23:00`).
- `status`: `active` or `inactive`. Default to `active` if blank.

**Minimum test configuration for callout feature:**
```
- 1 location created
- 1 role defined (e.g., "Server")
- 2+ employees with that role, both with phone numbers
- 1 employee assigned to a shift (the one who will "call out")
- 1+ employees NOT on that shift, available during that window
```

Simulate callout by: creating a `callouts` record and `coverage_campaigns` record for an assigned shift, then triggering the coverage engine. Verify the eligible available employee appears in the candidate list and receives outreach.

---

## 11. Key Design Decisions — Summary

| Decision | Choice | Reason |
|---|---|---|
| Employee placement in hierarchy | Under Business, not Location | Enables cross-location coverage without schema changes |
| Location eligibility model | Explicit clearance / eligibility layer | Prevents sending unknown workers to unfamiliar locations |
| Roles placement | Under Business | Single definition shared across all locations |
| Availability model | Recurring rules + Exceptions | Handles standing availability and one-off changes cleanly while allowing projection-based reads later |
| Shift time model | Canonical interval (`starts_at`, `ends_at`) | Safe across overnight shifts, DST, and timezone math |
| Assignment model | Separate `shift_assignments` table | Durable history, concurrency safety, multi-seat support |
| Coverage aggregate | `coverage_campaigns` | Canonical operational, billing, and observability object |
| Outreach aggregate | `outreach_attempts` | Canonical delivery/execution fact stream |
| Scoring window | 30-day rolling | Recent behavior is more predictive than lifetime average |
| Ranking signal | Probability of Acceptance (PoA) | Context-aware, improves over time, smarter than static sort |
| Operating modes | 3 modes based on time-to-shift | Matches urgency to execution strategy automatically |
| Blast-mode winner rule | First confirm wins, enforced by DB-backed invariants | Prevents race-condition double fills |
| Compensation changes | Operator pre-authorized only | Legal protection, operator control, no autonomous wage decisions |
| Phase 2 trigger | Zero Phase 1 candidates OR operator opt-in | Conservative expansion, operator retains control |
| Event backbone | Append-only campaign and outreach facts | Supports projections, scoring snapshots, auditability, and replay |

---

*This document covers Phase 1 and Phase 2 only. Phase 3 (agency network integration) and Phase 4 (claimable gigs / employee-initiated) are documented separately.*
