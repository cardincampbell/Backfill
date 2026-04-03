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
  │     └── Shifts
        └── Roles
  ├── Roles
  └── Employees
        └── Availability
        └── Roles
```

**Key principles:**

- **Employees belong to the Business, not to a Location.** This is the architectural decision that enables cross-location coverage in Phase 2. An employee can fill a shift at any location under their business — their role assignments and availability determine eligibility, not their "home" location.
- **Roles belong to the Business.** A "Server" is a "Server" across all locations. Roles are defined once at the business level, then assigned to locations and employees independently.
- **Shifts belong to Locations.** A shift is a specific demand event — a role needed, at a place, at a time.
- **Availability belongs to Employees.** Availability is the supply signal — when an employee can work, regardless of where.

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
Location level:    locations, location_roles, location_shifts
Employee level:    employees, employee_roles, employee_availability
Operational:       callout_events, call_attempts
```

The supply/demand symmetry is explicit in the naming:

```
DEMAND                    BRIDGE     SUPPLY
────────────────────────────────────────────────
location_roles            Roles      employee_roles
location_shifts           Time       employee_availability
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

### `location_shifts` ← demand side, temporal
```
id                UUID, primary key
location_id       UUID, FK → locations
role_id           UUID, FK → roles
date              DATE
start_time        TIME
end_time          TIME
assigned_employee_id  UUID, FK → employees, NULLABLE
status            ENUM           -- scheduled | open | filling | covered | no-fill
created_at        TIMESTAMP
updated_at        TIMESTAMP
```

This is the demand signal for the temporal relationship. A shift is a specific need — a role, at a location, on a date, between two times.

Status lifecycle:
```
scheduled  →  open  →  filling  →  covered
                                →  no-fill
```

### `employees`
```
id                UUID, primary key
business_id       UUID, FK → businesses
first_name        VARCHAR
last_name         VARCHAR
phone             VARCHAR        -- E.164 format (+13105550100)
email             VARCHAR
status            ENUM           -- active, inactive
reliability_score DECIMAL(4,3)   -- 0.000 to 1.000, see scoring section
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

### `employee_availability` ← supply side, temporal
```
id                UUID, primary key
employee_id       UUID, FK → employees
type              ENUM           -- recurring | exception
day_of_week       ENUM           -- MON TUE WED THU FRI SAT SUN (recurring only)
date              DATE           -- (exception only)
exception_type    ENUM           -- available | unavailable (exception only)
start_time        TIME           -- nullable = all day
end_time          TIME           -- nullable = all day
reason            VARCHAR        -- optional, operator visibility
created_at        TIMESTAMP
```

The supply signal for the temporal relationship. Combined `recurring` and `exception` records in one table, differentiated by `type`. Exceptions always take precedence over recurring records for the same date.

**Recurring example:** Available every Friday 4 PM – midnight  
**Exception example:** Unavailable April 15th (concert) / Available this Saturday despite no recurring Saturday availability

### `callout_events`
```
id                UUID, primary key
shift_id          UUID, FK → location_shifts
reported_by       UUID, FK → employees  -- who called out
reported_at       TIMESTAMP
initiated_by      ENUM           -- employee | manager | system
status            ENUM           -- in-progress | filled | no-fill
created_at        TIMESTAMP
```

### `call_attempts`
```
id                UUID, primary key
callout_event_id  UUID, FK → callout_events
employee_id       UUID, FK → employees
rank              INTEGER        -- position in the call list
called_at         TIMESTAMP
outcome           ENUM           -- no-answer | declined | confirmed | cancelled
response_time_seconds  INTEGER   -- null if no-answer
created_at        TIMESTAMP
```

Every call attempt is logged regardless of outcome. This data feeds the reliability score and probability of acceptance model.

---

## 4. The Coverage Engine

When a callout event is created, the coverage engine executes in this sequence:

### Step 1 — Shift Status Update
```
location_shifts.assigned_employee_id = NULL
location_shifts.status = 'open'
callout_events record created
```

### Step 2 — Candidate Query

**Phase 1 (single location):**
```sql
SELECT e.id, e.phone, e.reliability_score
FROM employees e

-- Capability check (Relationship 1)
JOIN employee_roles er 
  ON er.employee_id = e.id
JOIN location_roles lr 
  ON lr.role_id = er.role_id
  AND lr.location_id = :shift_location_id
  AND lr.role_id = :shift_role_id

-- Availability check (Relationship 2)
WHERE (
  -- Check recurring availability
  EXISTS (
    SELECT 1 FROM employee_availability ea
    WHERE ea.employee_id = e.id
    AND ea.type = 'recurring'
    AND ea.day_of_week = :shift_day_of_week
    AND ea.start_time <= :shift_start_time
    AND ea.end_time >= :shift_end_time
  )
  -- Override: check unavailability exceptions
  AND NOT EXISTS (
    SELECT 1 FROM employee_availability ea
    WHERE ea.employee_id = e.id
    AND ea.type = 'exception'
    AND ea.exception_type = 'unavailable'
    AND ea.date = :shift_date
  )
)
OR EXISTS (
  -- Explicit availability exception (overrides recurring)
  SELECT 1 FROM employee_availability ea
  WHERE ea.employee_id = e.id
  AND ea.type = 'exception'
  AND ea.exception_type = 'available'
  AND ea.date = :shift_date
  AND ea.start_time <= :shift_start_time
  AND ea.end_time >= :shift_end_time
)

-- Conflict check
AND e.id NOT IN (
  SELECT ls.assigned_employee_id FROM location_shifts ls
  WHERE ls.date = :shift_date
  AND ls.start_time < :shift_end_time
  AND ls.end_time > :shift_start_time
  AND ls.status IN ('scheduled', 'covered')
  AND ls.assigned_employee_id IS NOT NULL
)

-- Active employees only
AND e.status = 'active'

-- Exclude the employee who called out
AND e.id != :calling_out_employee_id

ORDER BY e.reliability_score DESC
```

**Phase 2 (cross-location broadcast):**

Same query with the location constraint removed from the capability check:

```sql
-- Phase 2: search entire business employee pool
JOIN employee_roles er 
  ON er.employee_id = e.id
  AND er.role_id = :shift_role_id
WHERE e.business_id = :business_id
-- all other checks remain the same
```

Phase 2 activates when Phase 1 returns zero candidates, or when the operator has enabled cross-location coverage in their settings.

### Step 3 — Rank the Call List

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

See Section 5 for full scoring details.

### Step 4 — Determine Operating Mode

Based on time remaining until shift start:

```
T-minus 4+ hours  →  Mode 1: Standard Queue
T-minus 1-4 hours →  Mode 2: Compressed Queue
T-minus <1 hour   →  Mode 3: Blast
```

### Step 5 — Execute Calls

See Section 5 for mode-specific execution logic.

### Step 6 — Resolution

**On confirmation:**
```
location_shifts.assigned_employee_id = confirmed_employee_id
location_shifts.status = 'covered'
callout_events.status = 'filled'
call_attempts.outcome = 'confirmed' for that employee
All pending call attempts cancelled
Confirmation sent to employee
Notification sent to operator
```

**On exhausting the list:**
```
location_shifts.status = 'no-fill'
callout_events.status = 'no-fill'
Operator notified immediately
```

---

## 5. Three Operating Modes

The engine selects the operating mode automatically based on time-to-shift-start. The operator never sees or selects a mode — they only see outcomes.

---

### Mode 1 — Standard Queue
**Trigger:** Shift starts in 4+ hours  
**Logic:** Sequential offers, one at a time  
**Wait window:** 5 minutes per candidate before moving to next  
**Rate:** Standard hourly rate

```
Call candidate #1
  → Confirmed: done
  → Declined / No answer after 5 min: move to #2
Call candidate #2
  → ...and so on
```

---

### Mode 2 — Compressed Queue
**Trigger:** Shift starts in 1–4 hours  
**Logic:** Sequential offers, tighter windows  
**Wait window:** 2 minutes per candidate  
**Rate:** Standard rate. If operator has pre-authorized a shift premium, it becomes available after 5 failed attempts.

```
Call candidate #1 (2 min window)
  → ...
After 5 declines/no-answers:
  → If operator has set premium_rate: offer premium to remaining candidates
  → If no premium set: continue at standard rate
```

---

### Mode 3 — Blast
**Trigger:** Shift starts in less than 1 hour  
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

## 6. Reliability Score & Probability of Acceptance

### Reliability Score

Stored on the `employees` record. Updated after every call attempt outcome. Uses a **30-day rolling window** — recent behavior weighted more heavily than historical.

```
reliability_score = (
  (confirmed_count / total_attempts) * 0.5     -- acceptance rate
  + response_speed_score * 0.3                  -- how fast they respond
  + recency_score * 0.2                          -- behavior in last 30 days
)
```

**Decay:** Attempts older than 30 days are down-weighted. Attempts older than 90 days are excluded entirely. An employee with a strong 6-month-old track record but who has ghosted the last 5 calls should score lower than one with a shorter but more recent track record.

**Initial score:** New employees start at `0.700` (neutral/slightly positive) until enough call attempts exist to generate a meaningful score. Threshold: 5 attempts minimum before score is fully trusted.

### Probability of Acceptance (PoA)

PoA is calculated at query time — it's not stored. It's the reliability score contextualized for the specific shift being filled:

```
PoA = reliability_score
  * day_of_week_affinity_multiplier    (0.7 – 1.3)
  * time_of_day_affinity_multiplier    (0.7 – 1.3)
  * location_affinity_multiplier       (0.9 – 1.1, Phase 2 only)
```

**Affinity multipliers** are derived from historical call attempt data for that employee:
- If they've accepted 80% of Friday night shifts they've been offered → Friday night multiplier = 1.3
- If they've declined every Sunday morning offer → Sunday morning multiplier = 0.7

Over time PoA becomes a highly personalized signal per employee per shift context. In early operation (few data points), it degrades gracefully to the base reliability score.

---

## 7. Callout Flow — End to End

```
1. CALLOUT RECEIVED
   Employee calls/texts Backfill to report callout
   OR manager marks shift as open in dashboard
   OR integrated scheduler signals a gap

2. SHIFT OPENED
   location_shifts.assigned_employee_id = NULL
   location_shifts.status = 'open'
   callout_events record created

3. CANDIDATE QUERY
   Run capability + availability + conflict check
   Returns ordered list ranked by PoA

4. MODE DETERMINED
   Based on time_to_shift_start
   Mode 1 / Mode 2 / Mode 3 selected

5. ENGINE EXECUTES
   Calls go out per mode logic
   call_attempts logged for every contact

6. RESOLUTION
   Covered → shift assigned, all parties notified
   No-fill → operator notified, shift marked no-fill

7. SCORING UPDATED
   Every call attempt outcome updates:
   - employee reliability_score
   - response_time logged
   - day/time affinity data updated
```

---

## 8. Phase Boundaries

### Phase 1 — Single Location, Internal Pool

**Candidate query scope:** Employees at the same location as the open shift only  
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
- Callout event triggers candidate query
- Engine calls down the list
- Shift confirmed and assigned

---

### Phase 2 — Cross-Location, Internal Pool

**Candidate query scope:** All employees under the Business, regardless of location  
**Trigger:** Phase 1 query returns zero candidates, OR operator has enabled cross-location coverage  
**Cross-location opt-in:** Configured at the Business level. Operators can also flag specific roles or locations as cross-location eligible/ineligible.  
**Candidate ranking addition:** `location_affinity_multiplier` added to PoA — employees who have worked a location before rank higher than those who haven't  
**External workers:** Still not enabled (Phase 3)

**New data considerations for Phase 2:**
- Employee must have worked at (or been explicitly cleared for) the target location to be included
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

## 9. Roster Upload Format

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

Simulate callout by: setting `location_shifts.assigned_employee_id = NULL` and `location_shifts.status = 'open'`, then triggering the coverage engine query. Verify the unassigned available employee appears in the candidate list and receives a call.

---

## 10. Key Design Decisions — Summary

| Decision | Choice | Reason |
|---|---|---|
| Employee placement in hierarchy | Under Business, not Location | Enables cross-location coverage without schema changes |
| Roles placement | Under Business | Single definition shared across all locations |
| Availability model | Recurring + Exceptions | Handles standing availability and one-off changes cleanly |
| Scoring window | 30-day rolling | Recent behavior is more predictive than lifetime average |
| Ranking signal | Probability of Acceptance (PoA) | Context-aware, improves over time, smarter than static sort |
| Operating modes | 3 modes based on time-to-shift | Matches urgency to execution strategy automatically |
| Compensation changes | Operator pre-authorized only | Legal protection, operator control, no autonomous wage decisions |
| Phase 2 trigger | Zero Phase 1 candidates OR operator opt-in | Conservative expansion, operator retains control |
| Cross-location clearance | Explicit clearance required | Prevents sending unknown workers to unfamiliar locations |

---

*This document covers Phase 1 and Phase 2 only. Phase 3 (agency network integration) and Phase 4 (claimable gigs / employee-initiated) are documented separately.*
