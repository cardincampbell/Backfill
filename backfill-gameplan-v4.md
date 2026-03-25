# Backfill — US Prototype Gameplan (v4)

## Revised Thesis

Backfill is not scheduling software. Backfill is not a staffing marketplace. Backfill is not an app.

**Backfill is autonomous coverage infrastructure for hourly labor.**

When coverage breaks, Backfill detects the gap, identifies the highest-probability replacement path, communicates through the fastest trusted channel, confirms coverage, and closes the loop — without a manager touching anything.

For restaurants with 7shifts or Deputy, Backfill orchestrates on top of their existing system. For restaurants with read-only tools like Homebase, Backfill runs in companion mode. For restaurants with no scheduling software, Backfill Native Lite acts as the minimum operational ledger. For all of them, the phone number is the command surface.

**The core reframe:** The problem isn't the callout. It's that a human has to solve it. The manager's involvement is the primary source of delay. Backfill removes them from routine coordination entirely. They're only pulled in when the system needs a decision they haven't already pre-authorized.

**Positioning (one sentence):** Backfill is an autonomous coverage engine that turns labor disruptions into confirmed shift coverage through the fastest trusted path — without the manager scramble.

---

## What We're Building

Autonomous coverage infrastructure powered by a single branded toll-free number: **1-800-BACKFILL** (1-800-222-5345). Workers call or text to report an absence. Backfill instantly broadcasts to qualified available staff, confirms coverage, and closes the loop — all before the manager knows there was a problem.

**Three product directions:**

1. **Inbound (call-out):** Worker calls/texts 1-800-BACKFILL → AI agent identifies them and the shift → creates a vacancy → coverage engine fires immediately
2. **Outbound (coverage engine):** Backfill broadcasts to ranked qualified workers simultaneously (Tier 1), escalates to known alumni (Tier 2), then routes to partner agencies (Tier 3) → first confirmed acceptance wins → manager gets one text: "Shift filled."
3. **Inbound (prospecting + onboarding):** Restaurant managers call to set up their restaurant conversationally, workers call looking for shifts (routed to agency partners), owners call to learn about the product — all through the same number

**Demo-ready target:** Employee calls 1-800-BACKFILL to call out → system identifies them and the restaurant → creates a vacancy → simultaneously texts available internal staff → first to accept wins → shift filled → manager gets one notification — all within minutes, zero manager involvement.

**Product philosophy:** 1-800-BACKFILL is the command surface — the operational front door, not the required channel for every piece of structured data. Workers call or text to call out. Managers call or text to start onboarding, post shifts, or check status. But structured data (rosters, schedules, availability) flows through the best channel for the data type: integrations when available, CSV upload as fallback, dashboard for review and exceptions. The phone handles intent and action. Structured systems handle structured data.

---

## Core Strategic Decisions

### Tier 3 is an Agency Partner Network, not a Backfill-owned marketplace

Instead of Backfill employing or directly placing unknown workers, Backfill routes unfilled shifts to pre-vetted staffing partners that already have payroll, workers' comp, active worker rosters, and operational processes. If a partner fills the shift, Backfill earns a fill fee or referral fee.

**Why this is better for launch:**
- Eliminates worker classification exposure (W-2 vs 1099)
- No payroll, workers' comp, or temp-employer obligations
- No staffing agency licensing required for Backfill itself
- No background check pipeline to build and maintain
- Dramatically reduces legal complexity, especially in California
- Backfill can monetize external supply from day one without building a labor pool

**Long-term note:** As Backfill sees which agency-placed workers perform well and which restaurants request them again, a natural on-ramp to a Backfill-owned worker pool may emerge. That's a Phase 5+ consideration — not a launch concern.

### Source-of-Truth Rules

Simple rule for every customer conversation:

**"We use your scheduler if we can write to it. If we can't, Backfill holds the fill workflow state so nothing breaks."**

| Restaurant Setup | Schedule Source of Truth | Vacancy/Fill Source of Truth |
|-----------------|------------------------|----------------------------|
| Uses **7shifts** | 7shifts (read + write via OAuth API) | Backfill orchestrates, writes fill back to 7shifts |
| Uses **Deputy** | Deputy (read + write via OAuth API) | Backfill orchestrates, writes fill back to Deputy |
| Uses **When I Work** | When I Work (read + TBD write via token API) | If writable: Backfill orchestrates on top. If read-only: **Native Lite** companion |
| Uses **Homebase** (read-only API) | Homebase (read for context) | **Backfill Native Lite** holds operational state |
| Uses **no scheduler** | N/A | **Backfill Native Lite** is the full truth |

### Backfill Native Lite — Companion, Not Competitor

Native Lite is the minimum system of record needed to make Backfill work when no scheduler exists or when the scheduler is too limited to write back into.

**Scope (build this):**
- Restaurant profile
- Manager contacts
- Worker roster (name, phone, email, roles, certifications, consent status)
- Shift records
- Vacancy records
- Assignment records
- Outreach history
- Simple dashboard
- CSV import/export

**Out of scope (do NOT build):**
- Payroll
- Time clock
- PTO management
- Labor forecasting
- Wage-and-hour workflows
- Full recurring scheduling suite
- Hiring ATS
- Workforce performance management

This keeps Native Lite in its lane and prevents restaurants from comparing it to 7shifts.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    1-800-BACKFILL                        │
│                  (AT&T Toll-Free)                        │
│              + 1-888-BACKFILL (brand protection)         │
└───────────────────────┬─────────────────────────────────┘
                        │ Ported to
                        ▼
┌─────────────────────────────────────────────────────────┐
│                      TWILIO                              │
│              Elastic SIP Trunking                        │
│         (Telephony pipe — replaceable later)             │
│    Termination URI: backfill.pstn.umatilla.twilio.com   │
│    Transport: TLS (HIPAA-ready)                          │
│    Origination: sip:5t4n6j0wnrl.sip.livekit.cloud      │
│    Toll-free SMS verification required                   │
└───────────────────────┬─────────────────────────────────┘
                        │ SIP Trunk
                        ▼
┌─────────────────────────────────────────────────────────┐
│                    RETELL AI                              │
│         Voice Agent + SMS Agent + AI Brain               │
│    Inbound agents:                                       │
│      - Call-out handler                                  │
│      - Job seeker → agency partner referral              │
│      - Manager onboarding / shift posting                │
│      - Unknown caller routing                            │
│    Outbound agents:                                      │
│      - Tier 1/2 shift-fill (voice + SMS)                │
│    All agents: consent collection + disclosure            │
└───────────────────────┬─────────────────────────────────┘
                        │ Webhooks + API
                        ▼
┌─────────────────────────────────────────────────────────┐
│               BACKFILL BACKEND (FastAPI)                  │
│                                                         │
│    Core Engine:                                          │
│      Caller lookup                                       │
│      Shift/vacancy creation                              │
│      Ranked cascade engine (Tier 1 → 2 → 3)            │
│      Consent ledger                                      │
│      Manager notifications                               │
│      Audit trail                                         │
│                                                         │
│    Integration Layer:                                    │
│      7shifts adapter (read + write via OAuth)            │
│      Deputy adapter (read + write via OAuth)             │
│      When I Work adapter (read + TBD write via token)    │
│      Homebase adapter (read-only context)                │
│      Backfill Native Lite (built-in)                     │
│                                                         │
│    Agency Partner Layer:                                 │
│      Partner directory                                   │
│      Structured request routing                          │
│      SLA timers                                          │
│      Fill confirmation workflow                          │
│      Manager approval gates for external supply          │
└──────────┬──────────────────────────────┬───────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────┐    ┌─────────────────────────────┐
│   SCHEDULING SYNC   │    │     BACKFILL DATABASE       │
│                     │    │                             │
│  ┌───────────────┐  │    │  Restaurants                │
│  │   7shifts     │  │    │  Workers + consent records  │
│  │  OAuth + Hooks│  │    │  Shifts & Vacancies        │
│  ├───────────────┤  │    │  Cascades & Attempts       │
│  │  Homebase     │  │    │  Agency Partners           │
│  │  Read-only    │  │    │  Agency Requests/Confirms  │
│  ├───────────────┤  │    │  Audit log                 │
│  │  Backfill     │  │    │                             │
│  │  Native Lite  │  │    │  SQLite → Supabase         │
│  └───────────────┘  │    └─────────────────────────────┘
└─────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────┐
│              AGENCY PARTNER NETWORK                      │
│                                                         │
│  Structured request routing (not lead dumping):         │
│    → role, shift date/time, pay, location, certs        │
│    → urgency level, acceptance deadline                 │
│    → restaurant notes                                    │
│                                                         │
│  Partner returns:                                        │
│    → accepted / declined / unavailable                  │
│    → candidate confirmation + ETA                        │
│    → final fill confirmation                            │
│                                                         │
│  Transport (start simple, formalize later):             │
│    Phase 1: email + structured SMS                      │
│    Phase 2: agency dashboard/portal                     │
│    Phase 3: API/webhooks                                │
└─────────────────────────────────────────────────────────┘
```

---

## Phone Number Strategy

| Number | Role | Status |
|--------|------|--------|
| **1-800-222-5345** (1-800-BACKFILL) | Primary — all marketing, employee-facing, inbound + outbound | Acquiring from AT&T → port to Twilio |
| **1-888-222-5345** (1-888-BACKFILL) | Brand protection — forward to 800 number | Acquiring → park or forward on Twilio |

---

## Unified Inbound Routing

### Voice Routing (someone calls 1-800-BACKFILL)

```
Inbound call
  │
  ├── Caller ID recognized as EXISTING WORKER
  │     → "Hi Maria, are you calling out of a shift?"
  │         ├── Yes → call-out flow (identify restaurant, shift, create vacancy)
  │         └── No → "What can I help you with?"
  │               ├── "Any shifts available?" → check open shifts matching profile
  │               ├── "Update my availability" → collect new info
  │               └── Other → handle conversationally
  │
  ├── Caller ID recognized as RESTAURANT MANAGER
  │     → "Hi Chef Mike, need to post an open shift?"
  │         ├── Yes → collect shift details, create vacancy, kick off cascade
  │         ├── "Check on a fill" → pull cascade status
  │         └── Other → handle conversationally
  │
  └── Caller ID NOT RECOGNIZED
        → "Thanks for calling Backfill! How can I help you?"
            ├── "I need to call out" → new worker flow (collect name, restaurant)
            ├── "I'm looking for restaurant work" → collect info, refer to 
            │     agency partners in their area
            ├── "I'm a restaurant owner" → sales pitch + onboarding flow
            └── "What is Backfill?" → elevator pitch, route to right flow
```

**Note on job seekers:** When someone calls looking for work, Backfill does NOT onboard them as a Backfill employee. The agent collects basic info (name, experience, area, certs) and refers them to partner staffing agencies. This is a value-add to agency partners (pre-qualified candidate referral) and builds a dataset of labor supply by market. If/when Backfill builds its own worker pool in the future, this data is the foundation.

### SMS Routing (someone texts 1-800-BACKFILL)

```
Inbound text
  │
  ├── Known WORKER texts
  │     "calling out tomorrow" → SMS agent handles call-out
  │     "any shifts?" → check open shifts, text back matches
  │     "yes" / "no" (responding to offer) → handle acceptance/decline
  │
  ├── Known MANAGER texts
  │     "need a line cook tomorrow 6am-2pm $18/hr" → create shift, cascade
  │     "status" → text back current cascade status
  │
  └── UNKNOWN number texts
        "looking for work" → collect basics, refer to agency partners,
            text link: "Complete your profile: backfill.com/join"
        "info" → elevator pitch via text
```

---

## Tiered Fill Model

### Outreach Architecture: Broadcast with Standby Queue

**Key insight from first principles:** The sequential cascade is inherited from how humans make phone calls. An AI system has no such constraint. For urgent internal fills, simultaneous broadcast to qualified workers is faster — potentially reducing fill time from minutes to seconds.

**The confirmed + standby model:**

When Backfill broadcasts to multiple workers simultaneously, the first YES wins — but subsequent YESes don't get dismissed. They enter a ranked standby queue that auto-activates if the confirmed worker cancels or no-shows. This eliminates the most expensive failure mode: restarting outreach from scratch after a last-minute cancellation.

```
BROADCAST to top 5 qualified workers
  │
  ├── Worker A replies YES (fastest) → status: CONFIRMED
  │     → "You're confirmed! Line cook at Coastal Grill, tomorrow 
  │        6am-2pm. See you there."
  │
  ├── Worker B replies YES (second) → status: STANDBY #1
  │     → "That shift just got claimed, but you're on standby — if 
  │        it opens back up, you're first in line. We'll let you know."
  │
  ├── Worker C replies YES (third) → status: STANDBY #2
  │     → same standby message, ranked behind Worker B
  │
  ├── Worker D replies NO → status: DECLINED, released
  │
  └── Worker E no response → status: TIMED_OUT, released
  
IF CONFIRMED WORKER CANCELS OR NO-SHOWS:
  │
  ├── Standby #1 auto-promoted instantly:
  │     → "Good news — that line cook shift at Coastal Grill just 
  │        opened back up and it's yours. Still want it? Reply YES"
  │     ├── YES → CONFIRMED (instant fill, zero new outreach)
  │     └── NO or timeout → promote Standby #2
  │
  └── All standby exhausted → new broadcast to next batch 
      OR escalate to Tier 2/3

STANDBY RULES:
  - Standby ranked by response speed (primary), reliability score as 
    tiebreaker within 60-second window
  - Broadcast recipients selected by reliability score (quality filter 
    for who gets the broadcast in the first place)
  - Standby expires when the shift starts (or configurable buffer before)
  - Standby workers can cancel their standby anytime: "CANCEL"
  - Workers are told their standby position honestly
  - Standby does NOT count as a fill (no charge to restaurant)
  - Promotion from standby DOES count as a fill when confirmed
  - Phase 3+ refinement: standby promotion override — if standby #1 has 
    low show-up rate and standby #2 has high show-up rate, promote #2 
    first (insurance against serial no-shows)

RANKING SUMMARY:
  - Who gets the broadcast → reliability score (quality filter)
  - Who gets confirmed → first YES (speed wins)
  - Who gets standby #1 vs #2 → response order, reliability tiebreaker
  - Who gets promoted (Phase 3+) → show-up rate override available
```

**Broadcast mode (default for urgent fills — shift starts within 4 hours):**
- Text the top 3-5 qualified, available workers simultaneously
- First confirmed YES wins the shift → CONFIRMED
- Subsequent YESes enter standby queue → ranked backup
- If nobody accepts within timeout, broadcast to next batch or escalate

**Cascade mode (for less urgent or preference-sensitive fills):**
- Contact workers one at a time in ranked order
- Wait for response or timeout before moving to next
- Used when manager has set strict priority preferences or for Tier 3 agency routing
- Standby queue still applies: if primary cancels, next-in-line is promoted

**Mode is configurable per restaurant, per urgency level:**
- `urgency: "critical"` (shift starts within 4 hours) → broadcast
- `urgency: "standard"` (shift is tomorrow or later) → cascade
- Manager can override default in dashboard settings

### Tier 1 — Internal Staff

Workers already employed by the restaurant. Pulled from 7shifts, Deputy, When I Work, Homebase (read), or Backfill Native Lite roster.

- **Outreach:** Broadcast SMS to top 3-5 qualified workers → voice escalation if no text responses
- **Fill speed:** Fastest — they already know the restaurant
- **Cost to restaurant:** Per-fill fee (see pricing model)
- **Approval:** Auto-approved (manager's own staff, pre-authorized)
- **Manager involvement:** None. Notified after fill is confirmed.

### Tier 2 — Known Prior Workers / Alumni

Workers who have previously filled a shift at that restaurant through Backfill, or workers on a client-maintained approved flex pool. They know the layout, systems, and team.

- **Outreach:** Broadcast SMS to top qualified alumni → voice escalation
- **Fill speed:** Fast — reduced onboarding friction
- **Cost to restaurant:** Per-fill fee (slightly higher than Tier 1)
- **Approval:** Auto-approved based on prior history and restaurant preference settings
- **Manager involvement:** None by default. Configurable to require approval.

### Tier 3 — Agency Partner Network

If Tier 1 and Tier 2 fail, Backfill routes the shift request to pre-vetted staffing agency partners. The agency fills from its own worker base, handles employment/payroll/admin, and sends confirmation back to Backfill.

- **Outreach:** Structured request to partner agencies (sequential/SLA-ranked, not broadcast)
- **Fill speed:** Slower — agency needs to source and confirm
- **Cost to restaurant:** Per-fill fee (premium rate, includes agency coordination)
- **Approval:** Manager approval gate required before external worker is confirmed
- **Manager involvement:** Approves the fill before it's finalized. This is the exception, not the rule.

### Manager Notification Defaults

**Principle:** The manager is removed from routine coordination, not from governance.

| Event | Default Notification | Why |
|-------|---------------------|-----|
| Shift filled (Tier 1/2) | Yes — one text: "Maria's shift covered by Devon, arrives 5:45am" | They need to know who's coming |
| Shift filled (Tier 3) | Yes — after manager approves the external worker | They authorized it |
| Cascade exhausted (unfilled) | Yes — "Unable to fill Maria's shift. 6 workers contacted, none available." | They need to decide next steps |
| Individual outreach attempts | No | Noise — they don't need to know who declined |
| Worker declines | No | Noise |
| Cascade in progress | No (available on-demand via text: "status") | Only if they ask |

**The restaurant's experience is always the same regardless of tier:**

```
"Coverage in progress"
  → "Shift filled. Devon, Line Cook, arrives 5:45am."
```

---

## Agency Partner Model

Backfill acts as a **structured request router with SLA-aware escalation**, not a lead marketplace.

### What each partner agency receives:

- Role
- Shift date/time
- Pay rate
- Location + address
- Required certifications
- Urgency level
- Restaurant-specific notes (parking, dress code, report to)
- Acceptance deadline

### What each partner returns:

- Accepted / declined / unavailable
- ETA to confirm worker
- Candidate confirmation (name, contact, ETA)
- Final fill confirmation

### Agency Transport (start simple, formalize later):

| Phase | Transport | Description |
|-------|-----------|-------------|
| MVP | Email + structured SMS | Backfill sends formatted shift request via email/SMS, agency replies with confirmation |
| Phase 2 | Agency dashboard | Partners log into a Backfill portal to view/accept requests |
| Phase 3 | API/webhooks | Full programmatic integration for high-volume partners |

### Agency Partner Data Model:

```
AgencyPartner
├── id, name
├── coverage_areas: ["LA - Valley", "LA - Westside", ...]
├── roles_supported: ["line_cook", "server", "dishwasher", ...]
├── certifications_supported: ["food_handler", "servsafe", ...]
├── contact_channel: "email" | "sms" | "api" | "portal"
├── contact_info: email/phone/webhook URL
├── avg_response_time_minutes: int
├── acceptance_rate: decimal
├── fill_rate: decimal
├── billing_model: "referral_fee" | "restaurant_fee" | "both"
├── sla_tier: "standard" | "priority"
├── active: bool

AgencyRequest
├── id, shift_id, agency_partner_id
├── status: "sent" | "acknowledged" | "declined" | "candidate_pending" 
│           | "filled" | "expired"
├── request_timestamp
├── response_deadline
├── notes
├── confirmed_worker_name
├── confirmed_worker_eta
├── agency_reference_id
```

---

## Revenue Model — Utility Pricing (Pay Per Fill)

**Core principle:** Backfill charges when it works. The restaurant pays per successful coverage event — aligned with the value delivered.

### Pricing Structure

**Initiation Fee (one-time per location):**
Setup, onboarding, scheduler connection (if applicable), consent collection for existing workers. Covers the cost of getting the restaurant live.

**Per-Fill Pricing (the ongoing model):**

| Fill Type | Description | Price Point |
|-----------|-------------|-------------|
| **Tier 1 fill** | Internal staff member accepts the shift | Lowest per-fill fee |
| **Tier 2 fill** | Known alumni / approved flex worker accepts | Slightly higher (cross-location coordination) |
| **Tier 3 fill** | Agency partner places a worker | Premium rate (includes agency coordination fee) |

**Why utility pricing wins:**

- **Alignment:** Restaurant only pays when Backfill delivers a confirmed body in the shift. No fills = no charge. That's conviction pricing.
- **Low barrier to start:** No large monthly commitment. A restaurant with few callouts pays little. A restaurant with many callouts pays more — but they're getting more value.
- **Scales with usage:** Multi-location operators with high callout volume become your highest-revenue accounts naturally, without negotiating enterprise contracts.
- **Easy to justify:** "What does it cost to run short-staffed for a shift?" Lost revenue, overtime, burned-out staff. The per-fill fee is always cheaper than the alternative.
- **Self-correcting:** If Backfill's fill rate drops, so does revenue. This forces the product to stay good.

**Revenue model for agency partners:**

Two models to test depending on partner preference:

- **Model A (agency pays):** Agency pays Backfill a referral fee for each filled placement. Restaurant pays the agency directly for the worker.
- **Model B (restaurant pays):** Restaurant pays Backfill a premium per-fill fee that includes the agency coordination. Agency invoices separately for the worker.

Model A may be easier to launch with since the restaurant's cost is simpler. Test both.

**What we do NOT charge for:**
- Inbound call-outs (workers calling in) — this is data intake, not a fill
- Failed coverage attempts (cascade exhausted, shift unfilled) — we didn't deliver value
- Manager checking status — that's a feature, not a billable event
- Onboarding subsequent workers — growing the roster helps fill rates

---

## Compliance

### Consent Ledger (from day one)

The FCC's 2024 ruling confirms AI-generated voices fall under TCPA "artificial or prerecorded voice" restrictions. Twilio requires verified toll-free messaging before live U.S./Canada SMS. Backfill must collect and log explicit worker consent from the start.

**Required fields on every worker record:**

```
sms_consent_status: "granted" | "revoked" | "pending"
voice_consent_status: "granted" | "revoked" | "pending"
consent_text_version: "v1.0"  (tracks which disclosure language was used)
consent_timestamp: datetime
consent_channel: "inbound_call" | "inbound_sms" | "web" | "csv_import"
opt_out_timestamp: datetime (null if active)
opt_out_channel: "sms_reply" | "voice" | "web" | "manual"
```

**Agent disclosure (built into every first interaction):**
> "Just so you know, I'm an AI assistant from Backfill. We'll use this number to text or call you about shift opportunities. You can opt out anytime by replying STOP or telling me. Is that ok?"

Log the consent with timestamp before proceeding.

### What the agency partner model eliminates:

- Worker classification exposure (W-2 vs 1099)
- Payroll administration
- Workers' comp administration
- Temp-employer wage/payment obligations
- Background check pipeline for a Backfill labor pool
- Staffing agency licensing for Backfill itself

### What's still on Backfill:

- SMS opt-in / opt-out handling (TCPA)
- Toll-free verification (Twilio)
- AI call consent/disclosure design (FCC 2024 ruling)
- Data privacy and retention policies
- Contract structure with agencies and restaurants
- Avoiding misleading caller identity practices
- Audit logs for every vacancy/fill action

---

## Scheduling System Integrations

### All Four Platforms — Built in Parallel (Phase 1)

All four integrations are built during Phase 1 alongside Native Lite. They share the same adapter interface, so building one informs the others.

**7shifts (read + write):** Self-service OAuth access. Best-documented restaurant-specific API with webhooks and writable endpoints. Full bidirectional sync — Backfill reads rosters/schedules and writes back fill confirmations. This is the gold standard integration.

**What we sync from 7shifts:**
- Employee roster → Backfill worker database
- Published schedules → Backfill shift records
- Shift changes/call-outs → automatic vacancy creation
- Availability/time-off → exclude unavailable workers from cascade

**What we write back to 7shifts:**
- Fill confirmations (updated shift assignment)
- Vacancy status

**Source of truth:** 7shifts owns the schedule. Backfill owns the fill orchestration. Final assignment writes back to 7shifts.

---

**Deputy (read + write):** OAuth 2.0 auth with full REST API and webhook support (Insert, Update, Delete triggers). Strong in seasonal restaurants, hospitality, and service industries. Follows the same full-integration pattern as 7shifts.

**What we sync from Deputy:**
- Employee roster → Backfill worker database
- Published schedules → Backfill shift records
- Shift changes → automatic vacancy creation via webhooks

**What we write back to Deputy:**
- Fill confirmations (shift assignment updates)
- Vacancy status

**Source of truth:** Deputy owns the schedule. Backfill orchestrates fills on top. Same pattern as 7shifts.

---

**When I Work (read + likely write — TBD):** Token-based developer key auth. Has service APIs per product feature with active development. Popular with hourly restaurant and hospitality workers. Needs testing to confirm write capabilities for shift assignment updates. If writable, follows the 7shifts/Deputy full-integration pattern. If read-only, falls back to Native Lite companion mode like Homebase.

**What we sync from When I Work:**
- Employee roster → Backfill worker database
- Published schedules → Backfill shift records
- Open shifts → automatic vacancy detection

**What we write back (if supported):**
- Fill confirmations (shift assignment updates)
- Vacancy status

**Source of truth:** If write works → When I Work owns the schedule, Backfill orchestrates fills on top. If read-only → Native Lite companion mode.

---

**Homebase (read-only companion):** API key access, read-only. Backfill pulls roster and schedule data for context. All fill operations (vacancies, cascade, outreach, confirmations) run in Native Lite companion layer.

**Source of truth:** Homebase for schedule context. Native Lite for fill operations.

---

**Backfill Native Lite (built-in):** Full system of record for restaurants with no scheduler. Also serves as the companion operational layer for Homebase, When I Work (if read-only), and any future read-only integration.

**Source of truth:** Native Lite is the truth for everything.

---

**Agency partner adapters (Phase 2):** Start with email + structured SMS. Formalize with portals and APIs after demand proves out.

### Integration Architecture (adapter pattern)

```
┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   7shifts     │  │   Deputy     │  │ When I Work  │  │   Homebase   │  │   Backfill   │
│  OAuth + Hooks│  │ OAuth + Hooks│  │  Token-based │  │  Read-only   │  │  Native Lite │
│  (read+write) │  │ (read+write) │  │  (TBD write) │  │              │  │  (full truth)│
└──────┬────────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                  │                 │                  │                  │
       ▼                  ▼                 ▼                  ▼                  ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                           BACKFILL SYNC LAYER                                            │
│                                                                          │
│  Each adapter implements the same interface:                             │
│    sync_roster(restaurant_id) → workers[]                                │
│    sync_schedule(restaurant_id, date_range) → shifts[]                   │
│    on_vacancy(shift) → trigger cascade                                   │
│    push_fill(shift, worker) → update source system                       │
│      (no-op for read-only adapters — fill state stays in Native Lite)    │
│                                                                          │
│  Adding new platforms (HotSchedules, Toast, Sling) = new adapter         │
│  Core engine never changes                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model

```
Restaurants
├── id, name, address
├── manager_name, manager_phone, manager_email
├── scheduling_platform: "7shifts" | "deputy" | "wheniwork" | "homebase" | "backfill_native"
├── scheduling_platform_id: (external ID for API sync)
├── onboarding_info: text (parking, dress code, who to report to)
├── agency_supply_approved: bool (manager opts in to Tier 3)
├── preferred_agency_partners: [agency_partner_ids]

Workers
├── id, name, phone, email
├── worker_type: "internal" | "alumni"
├── preferred_channel: "sms" | "voice" | "both"
├── restaurant_assignments: [
│     { restaurant_id, role, priority_rank, is_active }
│   ]
├── restaurants_worked: [restaurant_ids]  ← enables Tier 2 matching
├── certifications: ["food_handler", "servsafe", ...]
├── rating: decimal (avg from manager reviews)
├── total_shifts_filled: int
├── response_rate: decimal
├── show_up_rate: decimal
├── source: "scheduling_sync" | "inbound_call" | "csv_import" | "agency_fill"
│
│  Consent fields:
├── sms_consent_status: "granted" | "revoked" | "pending"
├── voice_consent_status: "granted" | "revoked" | "pending"
├── consent_text_version: "v1.0"
├── consent_timestamp: datetime
├── consent_channel: "inbound_call" | "inbound_sms" | "web" | "csv_import"
├── opt_out_timestamp: datetime | null
├── opt_out_channel: "sms_reply" | "voice" | "web" | "manual" | null

Shifts
├── id, restaurant_id, role, date, start_time, end_time, pay_rate, requirements
├── status: "scheduled" | "vacant" | "filling" | "filled" | "unfilled"
├── called_out_by: worker_id | null
├── filled_by: worker_id | null
├── fill_tier: "tier1_internal" | "tier2_alumni" | "tier3_agency" | null
├── source_platform: "7shifts" | "homebase" | "backfill_native" | "inbound_call"

Cascades
├── id, shift_id
├── status: "active" | "completed" | "exhausted"
├── outreach_mode: "broadcast" | "cascade"
├── current_tier: 1 | 2 | 3
├── current_batch: int (which broadcast batch, for batch-based escalation)
├── confirmed_worker_id: worker_id | null
├── standby_queue: [worker_ids] (ordered by response time)
├── manager_approved_tier3: bool (gate for external supply)

OutreachAttempts
├── id, cascade_id, worker_id
├── tier: 1 | 2
├── channel: "sms" | "voice"
├── status: "pending" | "sent" | "delivered" | "responded" | "timed_out"
├── outcome: "confirmed" | "standby" | "declined" | "no_response" | "promoted" | "standby_expired"
├── standby_position: int | null (1 = first backup, 2 = second, etc.)
├── promoted_at: datetime | null (when standby was promoted to confirmed)
├── sent_at, responded_at
├── conversation_summary: text

AgencyPartners
├── id, name
├── coverage_areas, roles_supported, certifications_supported
├── contact_channel, contact_info
├── avg_response_time_minutes, acceptance_rate, fill_rate
├── billing_model, sla_tier, active

AgencyRequests
├── id, shift_id, cascade_id, agency_partner_id
├── status: "sent" | "acknowledged" | "declined" | "candidate_pending"
│           | "filled" | "expired"
├── request_timestamp, response_deadline
├── confirmed_worker_name, confirmed_worker_eta
├── agency_reference_id, notes

AuditLog
├── id, timestamp, actor (system | worker_id | manager_id | agency_id)
├── action: "vacancy_created" | "outreach_sent" | "shift_filled" | 
│           "consent_granted" | "consent_revoked" | "agency_request_sent" | ...
├── entity_type, entity_id
├── details: JSON
```

---

## Tech Stack

| Layer | Tool | Role |
|-------|------|------|
| Phone Number | **1-800-BACKFILL** (AT&T → Twilio) | Single branded toll-free number for all restaurants |
| Telephony Pipe | **Twilio Elastic SIP Trunking** | Routes calls via SIP (TLS). Replaceable with Telnyx/jambonz later |
| Voice + SMS Agent | **Retell AI** | AI conversation engine — all inbound/outbound agents |
| Orchestration Backend | **Python (FastAPI)** | Caller lookup, cascade engine, consent ledger, agency routing, audit trail |
| Scheduling Integrations | **7shifts** (OAuth r/w), **Deputy** (OAuth r/w), **When I Work** (token, TBD r/w), **Homebase** (read-only), **Native Lite** (built-in) |
| Agency Partner Layer | **Email/SMS → Portal → API** (progressive formalization) |
| Database | **SQLite → Supabase** | All entities + audit log |
| IDE | **VS Code** | Primary editor |
| AI Coding Assistants | **Claude Code + OpenAI Codex** | Pair-programming, code generation, debugging |

---

## SMS Compliance: Toll-Free Verification

Since we're using a toll-free number, we follow the **toll-free verification** path (not A2P 10DLC).

**What's required:**
- Business name, EIN, address, website
- Use case: "Two-way shift coverage notifications to opted-in restaurant workers"
- Sample messages
- Opt-in/opt-out description

**Timeline:** Toll-free verification through Twilio is typically faster than 10DLC (days rather than weeks).

---

## Development Environment Setup

### VS Code Extensions

**Core:** Python (Microsoft), Pylance, REST Client, SQLite Viewer, GitLens

**API Development:** Thunder Client, dotenv, YAML

**Quality of Life:** Error Lens, Auto Rename Tag, Prettier

### Claude Code Setup

```bash
npm install -g @anthropic-ai/claude-code
cd ~/backfill && claude
```

**When to use Claude Code:** Architecture decisions, system design, multi-file scaffolding, Retell API integration, writing agent prompts, consent/compliance logic.

### OpenAI Codex Setup

```bash
npm install -g @openai/codex
cd ~/backfill && codex
```

**When to use Codex:** Rapid iteration on specific functions, debugging, writing tests, refactors, second opinion on implementation.

**Workflow:** Use them in alternating passes. Claude Code scaffolds a module → Codex writes tests and catches edge cases.

### Project Initialization

```bash
mkdir ~/backfill && cd ~/backfill
git init

python -m venv .venv
source .venv/bin/activate

pip install fastapi uvicorn retell-sdk pydantic python-dotenv httpx aiosqlite
pip install pytest pytest-asyncio ruff

cat > .env << 'EOF'
RETELL_API_KEY=your_retell_api_key_here
TWILIO_ACCOUNT_SID=your_twilio_sid_here
TWILIO_AUTH_TOKEN=your_twilio_auth_token_here
BACKFILL_PHONE_NUMBER=+18002225345
BACKFILL_WEBHOOK_URL=https://your-ngrok-url.ngrok.io
DATABASE_URL=sqlite:///./backfill.db
SEVENSHIFTS_CLIENT_ID=your_7shifts_client_id
SEVENSHIFTS_CLIENT_SECRET=your_7shifts_client_secret
DEPUTY_CLIENT_ID=your_deputy_client_id
DEPUTY_CLIENT_SECRET=your_deputy_client_secret
WHENIWORK_DEVELOPER_KEY=your_wheniwork_developer_key
EOF

cat > .gitignore << 'EOF'
.venv/
.env
__pycache__/
*.db
.DS_Store
EOF

git add . && git commit -m "Initial project setup"
```

### Ngrok Setup

```bash
brew install ngrok
ngrok http 8000
# Copy the https URL into .env as BACKFILL_WEBHOOK_URL
```

---

## Project Structure

```
backfill/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, startup, middleware
│   ├── config.py               # Settings from .env
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── restaurant.py       # Restaurant + manager info + platform config
│   │   ├── worker.py           # Worker + consent fields + behavioral scores
│   │   ├── shift.py            # Shift + vacancy + fill_tier + source_platform
│   │   ├── cascade.py          # Cascade + tier tracking + outreach attempts
│   │   ├── agency.py           # AgencyPartner + AgencyRequest
│   │   └── audit.py            # AuditLog
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── retell.py           # Retell API wrapper
│   │   ├── caller_lookup.py    # Caller ID → worker/restaurant matching
│   │   ├── cascade.py          # Tiered cascade engine (T1 → T2 → T3)
│   │   ├── shift_manager.py    # Shift lifecycle + vacancy creation
│   │   ├── consent.py          # Consent collection, verification, opt-out handling
│   │   ├── agency_router.py    # Route requests to agency partners, track SLAs
│   │   └── audit.py            # Audit trail for every action
│   │
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract adapter interface
│   │   ├── seven_shifts.py     # 7shifts OAuth + webhooks + write-back
│   │   ├── deputy.py           # Deputy OAuth + webhooks + write-back
│   │   ├── when_i_work.py      # When I Work token-based API (TBD write)
│   │   ├── homebase.py         # Homebase read-only context ingestion
│   │   └── native_lite.py      # Built-in system of record
│   │
│   ├── webhooks/
│   │   ├── __init__.py
│   │   ├── retell_hooks.py     # Retell callback events + function calls
│   │   └── scheduling_hooks.py # 7shifts webhook receivers
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py         # Async connection setup
│   │   └── queries.py          # CRUD operations
│   │
│   └── prompts/
│       ├── inbound_callout.txt         # Employee calling out
│       ├── inbound_jobseeker.txt       # Worker looking for work → agency referral
│       ├── inbound_manager.txt         # Manager posting shift or checking status
│       ├── inbound_unknown.txt         # Unknown caller routing
│       ├── outbound_voice_t1t2.txt     # Outbound to internal/alumni (Tier 1/2)
│       ├── outbound_voice_t3_agency.txt# NOT USED YET — future direct-to-worker Tier 3
│       └── outbound_sms.txt            # Outbound SMS (Tier 1/2)
│
├── tests/
│   ├── test_caller_lookup.py
│   ├── test_cascade.py
│   ├── test_consent.py
│   ├── test_agency_router.py
│   ├── test_integrations.py
│   └── test_webhooks.py
│
├── scripts/
│   ├── seed_data.py            # Seed restaurants, workers, shifts
│   └── seed_agencies.py        # Seed agency partner directory
│
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Build Phases

### Phase 1 — 3-Week Build (Coverage Engine + All Four Integrations)

**Principle: conversation-initiated onboarding, integration-preferred ingestion.** The phone starts everything. The system routes to the best data path. All four scheduler integrations ship in Phase 1 because integrations are the preferred onboarding path, not an optimization.

**Day 1:** Start toll-free number porting. Sign up for Retell. Apply for 7shifts developer/partner access, Deputy API sandbox, When I Work developer key, and Homebase API access. Set up VS Code, Claude Code, Codex. Initialize the repo.

---

**Week 1 — Core Engine + Telephony + Onboarding Router**

- Twilio SIP trunk connected to Retell (1-800-BACKFILL rings and agent picks up)
- FastAPI backend with SQLite/Postgres
- Data model: restaurants, workers (with consent fields), shifts, vacancies, coverage events, outreach attempts (with confirmed/standby/promoted statuses), standby queue, audit log
- Retell inbound call-out agent (identifies worker, confirms shift, creates vacancy)
- Retell inbound onboarding agent (collects restaurant basics, determines scheduler status, routes to right path):
  - "Do you use scheduling software?" → Yes: "Which one?" → routes to integration path
  - Recognizes: 7shifts, Deputy, When I Work, Homebase
  - No scheduler → routes to CSV/upload path
  - Agent texts the appropriate next-step link based on the answer
- Caller lookup service
- Consent ledger service (log every consent grant/revoke from day one)
- Webhook endpoints for Retell function calls
- Build base adapter interface (sync_roster, sync_schedule, on_vacancy, push_fill)

**Week 2 — Coverage Engine + All Integrations + Ingestion Paths**

*Coverage engine (primary dev focus):*
- Broadcast outreach engine: simultaneously text top 3-5 qualified workers per vacancy
- First-to-claim logic: lock the shift for first YES
- Standby queue logic: subsequent YESes enter ranked standby, auto-promote if primary cancels/no-shows
- Standby messaging: honest position updates, expiration on shift start
- Cascade fallback: if broadcast times out, move to next batch or voice escalation
- Retell outbound SMS agent (broadcast mode with claim/standby handling)
- Retell outbound voice agent (escalation)
- Manager notification service (outcome-only: fill, standby promotion, or exhaustion)

*Integrations (parallel via Codex or second dev focus):*
- **7shifts:** OAuth handshake, roster sync, schedule sync, webhook listeners, fill write-back
- **Deputy:** OAuth handshake, roster sync, schedule sync, webhook listeners, fill write-back (same pattern as 7shifts)
- **When I Work:** developer key auth, test read/write endpoints, build adapter (full integration if writable, companion mode if read-only)
- **Homebase:** API key auth, read-only roster and schedule ingestion, companion mode via Native Lite

*Non-integration ingestion paths:*
- **CSV upload:** simple upload page (backfill.com/setup), parse CSV into workers + shifts, validate, text each worker for consent
- **Minimal web form:** for restaurants with no data — add workers one by one

**Week 3 — Dashboard + End-to-End Testing + Polish**

- Native Lite dashboard: restaurant profile, worker roster, shift view, vacancy/coverage status
- Integration sync status indicators on dashboard (7shifts, Deputy, WIW connected/syncing)
- Homebase companion mode indicator: "Schedule synced from Homebase · Coverage managed by Backfill"
- Coverage event history: broadcast results, confirmed worker, standby queue, outcomes
- Fill metrics: time-to-fill, fill rate, tier breakdown, standby promotion rate
- CSV export for records
- Audit trail viewer
- End-to-end testing across ALL onboarding paths:
  - 7shifts → call out → broadcast → confirmed + standby → fill → write-back
  - Deputy → same flow
  - When I Work → same flow (or companion mode if read-only)
  - Homebase → companion mode → fill tracked in Native Lite
  - CSV → call out → broadcast → fill → dashboard
  - No data → form → call out → broadcast → fill → dashboard

**Phase 1 Milestones:**

| Path | "It works when..." |
|------|--------------------|
| **7shifts restaurant** | Connects OAuth → imported → vacancy detected → broadcast → confirmed + standby → writes back |
| **Deputy restaurant** | Same gold-standard flow as 7shifts |
| **When I Work restaurant** | Connects → syncs → broadcast fills → writes back (or companion mode) |
| **Homebase restaurant** | Connects → read-only sync → fill runs in Native Lite companion |
| **CSV restaurant** | Uploads roster → consent collected → call out → broadcast → filled |
| **No-data restaurant** | Adds workers via form → call out → broadcast → filled |
| **Standby works** | 3 workers reply YES → first confirmed, others on standby → primary cancels → standby #1 auto-promoted |
| **All paths** | Manager gets one text after the fill. Nothing during the process. |

**Integration Summary:**

| Platform | API | Onboarding Experience | Fill Operations |
|----------|-----|----------------------|----------------|
| **7shifts** | OAuth r/w + webhooks | "Connect your 7shifts" → link → auto-import | 7shifts (source of truth) |
| **Deputy** | OAuth r/w + webhooks | "Connect your Deputy" → link → auto-import | Deputy (source of truth) |
| **When I Work** | Token (TBD r/w) | "Connect your When I Work" → link → auto-import | WIW if writable, else Native Lite |
| **Homebase** | Read-only | "Connect your Homebase" → link → read import | Native Lite companion |
| **CSV** | N/A | "Upload your team list" → link → parse + import | Native Lite |
| **No data** | N/A | "Add your team" → simple form | Native Lite |

---

### Phase 2 — Agency Partner Layer (Tier 3)

- Agency partner directory (data model + seed data)
- Structured request routing (email + structured SMS — not a lead dump)
- Each request: role, shift date/time, pay, location, certs, urgency, acceptance deadline
- SLA timers (auto-escalate to next agency if no response by deadline)
- Manager approval gate before external worker is confirmed
- Per-fill fee logic for Tier 3 (premium rate)
- Agency fill status visible on dashboard

**Goal:** When Tier 1 coverage fails, Backfill routes to agency partners automatically. Manager approves before an external worker shows up.

### Phase 3 — Alumni Network + Behavioral Scoring (Tier 2)

- Track which workers filled shifts at which restaurants
- Tier 2 broadcast: prioritize alumni/known workers before agency route
- Worker behavioral scoring: response rate, acceptance rate, show-up rate, manager rating, repeat requests
- High-scoring workers get first broadcast slot
- Consecutive ghosts → deprioritized → deactivated
- Repeat-booked workers → auto-promoted to Tier 2 for that restaurant

**Goal:** Reduce agency dependence. Build a trust network that improves fill probability over time.

### Phase 4+ — Predictive Coverage + Future Moat

**Predictive coverage (the long-term defensible advantage):**
- Track callout patterns: which workers, which days, which shifts
- Risk-score shifts: "Monday morning line cook has 40% callout probability"
- Pre-stage coverage: notify backup workers the night before
- Standing availability signals: workers text "I'm free tomorrow morning" → auto-matched
- Pre-committed fills: "If Maria calls out Monday, Devon is pre-confirmed"

**Other future considerations:**
- Backfill-owned worker pool (if agency data reveals opportunity)
- HotSchedules/Fourth integration (enterprise, partner-gated)
- Additional adapters (Toast, Sling, Restaurant365)
- Worker-facing mobile experience
- Advanced coverage intelligence dashboard
- Multi-vertical expansion (healthcare, senior care, security, manufacturing)

---

## Agent Prompts

### Inbound Call-Out Agent

```
You are a friendly, professional shift coordinator at Backfill.
Employees call this number when they need to call out of a shift.

IMPORTANT: At the start of every first interaction with a worker, 
include this disclosure: "Just so you know, I'm an AI assistant from 
Backfill. We'll use this number to text or call you about shift 
coverage. You can opt out anytime by replying STOP or telling me. 
Is that ok?"

Wait for consent confirmation before proceeding. Call "log_consent" 
with the result.

WHEN A CALL COMES IN:
1. Call "lookup_caller" with the caller's phone number
2. If found with ONE restaurant:
   - Greet by name, confirm restaurant
   - Ask which shift they're calling out for
   - Confirm details back
   - Call "create_vacancy"
   - "We'll get to work on finding coverage right away. Feel better!"
3. If found with MULTIPLE restaurants:
   - Greet by name, ask which location
   - Then ask which shift, same flow
4. If NOT FOUND:
   - Greet warmly, ask for name and restaurant
   - Try to look up the restaurant
   - Collect shift details, create vacancy
   - Never make them feel guilty for calling out

Keep it under 2 minutes. Always confirm details before creating vacancy.
```

### Inbound Job Seeker Agent (→ agency partner referral)

```
You are a friendly recruiter at Backfill. Someone is calling because 
they're looking for restaurant work.

YOUR GOAL: Collect basic info and connect them with staffing partners 
in their area.

COLLECT:
1. Name
2. Phone (confirm from caller ID)
3. What restaurant roles they do (line cook, server, etc.)
4. Years of experience
5. Certifications (food handler, ServSafe, alcohol service)
6. What area they prefer to work in

THEN:
"Great! I'm going to connect you with one of our staffing partners 
in [their area] who can get you set up with shifts right away. 
They'll reach out to you within [timeframe]. In the meantime, you 
can also complete a profile at backfill.com/join if you want to 
speed things up."

Call "register_job_seeker" to log their info.
Call "match_agency_partners" to find relevant partners in their area.

Keep it warm and encouraging — they're looking for work.
```

### Inbound Manager Onboarding Agent (conversation-initiated, integration-preferred)

```
You are Backfill's onboarding specialist. A restaurant manager or 
owner is calling to set up their restaurant.

YOUR GOAL: Collect their basics through conversation, then route them 
to the right data ingestion path. Do NOT try to collect a full roster 
over the phone — that's what integrations and uploads are for.

STEP 1 — RESTAURANT BASICS (collect via conversation):
"Let's get you set up! What's the name of your restaurant?"
Then collect: address, your name, your phone (confirm from caller ID),
number of locations.

STEP 2 — DETERMINE SCHEDULER STATUS:
"Do you use any scheduling software to manage your team's shifts?"

If YES: "Which one do you use?"
  - 7shifts → "Perfect, I'll text you a link to connect your 7shifts 
    account. Once you authorize it, we'll import your team and schedule 
    automatically."
  - Deputy → same flow
  - When I Work → same flow
  - Homebase → "I'll text you a link to connect Homebase. We'll pull 
    in your team info. Since Homebase is read-only, we'll manage the 
    coverage workflow on our side."
  - Other → "We don't integrate with that one yet, but no problem — 
    I'll text you a link to upload your team list as a spreadsheet."

If NO: "No problem at all. I'll text you a simple link where you can 
add your team — just names, phone numbers, and roles. Takes a few 
minutes."

STEP 3 — SEND THE RIGHT LINK:
Call "send_onboarding_link" with the appropriate path:
  - "integration" + platform name → OAuth connect page
  - "csv_upload" → upload page
  - "manual_form" → simple add-workers form

STEP 4 — SET EXPECTATIONS:
"Once your team is in the system, we'll text each of them to introduce 
Backfill and get their permission to contact them about coverage. 
After that, you're live."

"From then on, when someone can't make a shift, they call or text 
1-800-BACKFILL. We handle finding coverage and text you when it's 
done. That's the whole thing."

Keep it under 3 minutes. The call collects intent and basics. 
The structured data flows through the right channel afterward.
```

### Outbound Voice Agent — Tier 1/2

```
You are a friendly shift coordinator calling from Backfill on behalf 
of {{restaurant_name}}. You're calling {{worker_name}} about an 
available shift.

SHIFT DETAILS:
- Role: {{role}}
- Date: {{shift_date}}
- Time: {{start_time}} to {{end_time}}
- Location: {{restaurant_name}}, {{restaurant_address}}
- Pay Rate: {{pay_rate}}/hr
- Requirements: {{requirements}}

CONVERSATION GUIDELINES:
- Be warm but concise — shift workers are busy
- Lead with role, date, time, pay
- If they ask questions, answer from shift details
- If they ask something you don't know: "Let me have the scheduling 
  team follow up on that"
- If they want to negotiate: note the request, pass to manager
- If they accept: confirm details, mention confirmation text coming
- If they decline: thank them, end politely
- Keep it under 2 minutes

FUNCTION CALLS:
- "accept_shift" when confirmed
- "decline_shift" when declined
- "request_callback" if they want a human to call back
```

### Outbound SMS Agent (broadcast mode with confirmed + standby)

```
You are Backfill's coverage system texting on behalf of 
{{restaurant_name}}, reaching out to {{worker_name}}.

NOTE: This message is being sent to multiple qualified workers at 
once. The first to confirm gets the shift. Others who say YES go 
on standby as ranked backups.

SHIFT DETAILS:
- Role: {{role}}
- Date: {{shift_date}}
- Time: {{start_time}} to {{end_time}}
- Location: {{restaurant_name}}
- Pay Rate: {{pay_rate}}/hr

TEXTING GUIDELINES:
- Keep messages SHORT — 1-3 sentences max
- First message: "Hi {{worker_name}}, Backfill for {{restaurant_name}}: 
  {{role}} shift open {{shift_date}} {{start_time}}-{{end_time}}, 
  {{pay_rate}}/hr. Want it? Reply YES"

HANDLING RESPONSES:
- If they reply YES → call "claim_shift" (atomic check + lock)
  - If shift still open → CONFIRMED:
    "You're confirmed! {{role}} at {{restaurant_name}}, 
    {{shift_date}} {{start_time}}-{{end_time}}. See you there."
  - If already claimed → STANDBY:
    "That shift just got claimed, but you're on standby — if it 
    opens back up, you're first in line. We'll let you know. 
    Reply CANCEL anytime to drop off standby."
- No → "No worries!"
- CANCEL (from standby) → "Got it, you're off standby."
- Questions → answer concisely from shift details
- No emojis, no over-explaining

STANDBY PROMOTION (triggered by system when primary cancels):
- "Good news — that {{role}} shift at {{restaurant_name}} 
  ({{shift_date}} {{start_time}}-{{end_time}}) just opened back 
  up and it's yours. Still want it? Reply YES to confirm."
  - YES → CONFIRMED (call "promote_standby")
  - NO or timeout → system promotes next standby worker

FUNCTION CALLS:
- "claim_shift" → atomic check: if open, lock + confirm; if taken, 
  add to standby queue
- "decline_shift" → worker says no
- "cancel_standby" → worker opts out of standby
- "promote_standby" → standby worker confirms after promotion
```

---

## Website as Support Layer

The website (backfill.com) handles structured data, visibility, and things that don't belong in a phone call. The number starts everything. The website supports everything.

**Onboarding paths (backfill.com/setup):**
- /setup/connect — OAuth connection pages for 7shifts, Deputy, When I Work, Homebase
- /setup/upload — CSV/spreadsheet upload for team roster
- /setup/add — Simple form to add workers manually

**For workers (backfill.com/join):**
- Complete profile (pre-filled from consent text data)
- Upload certification photos
- View upcoming confirmed shifts and history

**For restaurants (backfill.com/dashboard):**
- View active vacancies and cascade status
- Fill history, worker ratings, metrics
- Manage roster (Native Lite users)
- Create/edit shifts (Native Lite users)
- Connect 7shifts / Homebase
- Billing and account settings
- Toggle Tier 3 (agency supply) on/off

**For agency partners (backfill.com/partners):**
- View incoming shift requests
- Accept/decline/confirm fills
- Track fill history and performance metrics

**For prospects (backfill.com):**
- Marketing site: how it works, pricing, testimonials
- Primary CTA: "Call 1-800-BACKFILL to get started"

---

## Marketing Simplicity

Every piece of marketing has one call to action:

- **Break room poster:** "Can't make your shift? Call 1-800-BACKFILL"
- **Business card to restaurant owner:** "Never run short-staffed again. 1-800-BACKFILL"
- **Worker recruitment flyer:** "Looking for restaurant shifts? Call 1-800-BACKFILL"
- **Instagram/TikTok:** "1-800-BACKFILL. Call. We fill."
- **Manager pitch:** "Give this number to your staff. That's the entire setup."

No app download. No QR code. No "create an account." Just the number.

---

## Key Milestones & Checkpoints

| Week | Milestone | "It Works When..." |
|------|-----------|---------------------|
| 1 | Telephony live | You call 1-800-BACKFILL and the agent picks up and identifies you |
| 1 | Smart onboarding | Manager calls → agent routes to 7shifts/Deputy/WIW/Homebase connect, CSV, or form |
| 2 | Coverage engine + standby | Broadcast → first YES confirmed → others on standby → primary cancels → standby auto-promoted |
| 2 | All four integrations | 7shifts, Deputy, When I Work, Homebase adapters functional |
| 3 | Full Phase 1 demo | Any restaurant, any scheduler (or none) → call out → covered → one text to manager. Dashboard tells the full story. |

---

## Cost Estimates (Prototype Phase)

| Item | Cost |
|------|------|
| Twilio toll-free numbers (2) | ~$4/month |
| Twilio SIP trunking minutes | ~$0.007-0.013/min |
| Retell AI voice minutes | $0.07-0.15/min |
| Retell AI SMS | Per-message pricing |
| Toll-free SMS verification | One-time, included in Twilio |
| Ngrok | Free tier |
| **Total prototype budget** | **~$50-100 for the first month** |

**Revenue starts flowing immediately** — per-fill pricing means the first successful coverage event generates revenue. No waiting for monthly subscription cycles.

---

## Scaling Considerations

**Concurrency:** Retell starts at 20 concurrent calls. Upgrade as you grow.

**Telephony costs:** Port to Telnyx or jambonz if Twilio per-minute costs become material.

**Per-location numbers (future):** If clients demand local area codes, buy Twilio numbers programmatically via API. But start with the single toll-free.

**European expansion (future):** Add Twilio international numbers via SIP trunking. Same architecture.

---

## What Was Deferred (and why)

| Item | Reason | Revisit When |
|------|--------|-------------|
| Backfill-owned worker marketplace | Legal/operational complexity; agency model is cleaner | Agency data reveals high-performing workers who want direct relationship |
| Background check pipeline | Not needed if agencies handle their own workers | If/when Backfill builds its own pool |
| Payroll / workers' comp | Not needed in agency model | Never (unless Backfill becomes a staffing employer) |
| Full native scheduling suite | Competes with 7shifts; out of lane | Never — stay as companion tool |
| Staffing agency licensing | Not needed if Backfill routes, not employs | If Backfill builds its own pool |
| HotSchedules/Fourth integration | Partner-gated API, enterprise sales cycle | First HotSchedules restaurant client introduces Backfill to Fourth |
