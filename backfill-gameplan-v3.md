# Backfill — US Prototype Gameplan (v3)

## Revised Thesis

Backfill is not a staffing agency. Backfill is the **AI coordination layer for shift coverage.**

For restaurants with 7shifts, Backfill orchestrates on top of their existing system. For restaurants with read-only tools like Homebase, Backfill runs in companion mode with its own lightweight operational record. For restaurants with no scheduling software, Backfill Native Lite acts as the minimum system of record needed to make coverage work.

When internal staff can't cover a shift, Backfill escalates to trusted staffing agency partners automatically — keeping the restaurant inside one workflow while avoiding the operational and legal burden of becoming a staffing employer.

**Positioning (one sentence):** Backfill is the AI coverage layer for hourly operations. We sit on top of your scheduler when you have one, provide a lightweight companion record when you don't, and escalate to trusted labor partners when your own team can't cover a shift.

---

## What We're Building

An agentic AI shift-fill system powered by a single branded toll-free number: **1-800-BACKFILL** (1-800-222-5345). Workers call or text to report an absence. Backfill automatically contacts replacement labor through a ranked cascade (internal staff → known alumni → agency partners) and confirms coverage with the manager — all without human intervention.

**Three product directions:**

1. **Inbound (call-out):** Worker calls/texts 1-800-BACKFILL → AI agent identifies them and the shift → creates a vacancy → triggers the tiered fill cascade
2. **Outbound (fill engine):** Backfill reaches out to ranked internal staff first (Tier 1), then known prior workers (Tier 2), then routes to partner staffing agencies (Tier 3) → first confirmed fill wins → manager notified
3. **Inbound (prospecting):** Restaurant managers, owners, and workers looking for shifts can call/text the same number to onboard, post a shift, register for agency partner referral, or ask questions

**Demo-ready target:** Employee calls 1-800-BACKFILL to call out → system identifies them and the restaurant → creates a vacancy → texts the first available internal worker → worker accepts → shift filled → manager notified — all within minutes, zero human involvement.

**Product philosophy:** 1-800-BACKFILL is the front door to everything. Workers call or text to call out, find shifts, or ask questions. Managers call or text to post open shifts or check status. The website exists as a support layer for uploads, dashboards, and billing — but nobody needs to visit a website to get started. Every piece of marketing has one CTA: **Call 1-800-BACKFILL.**

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

### Tier 1 — Internal Staff

Workers already employed by the restaurant. Pulled from 7shifts, Homebase (read), or Backfill Native Lite roster.

- **Outreach:** SMS first → voice escalation if no response
- **Fill speed:** Fastest — they already know the restaurant
- **Cost to restaurant:** Included in Backfill SaaS subscription
- **Approval:** Auto-approved (manager's own staff)

### Tier 2 — Known Prior Workers / Alumni

Workers who have previously filled a shift at that restaurant through Backfill, or workers on a client-maintained approved flex pool. They know the layout, systems, and team.

- **Outreach:** SMS first → voice escalation
- **Fill speed:** Fast — reduced onboarding friction
- **Cost to restaurant:** Per-fill fee or included in premium plans
- **Approval:** Auto-approved based on prior history and restaurant preference settings

### Tier 3 — Agency Partner Network

If Tier 1 and Tier 2 fail, Backfill routes the shift request to pre-vetted staffing agency partners. The agency fills from its own worker base, handles employment/payroll/admin, and sends confirmation back to Backfill.

- **Outreach:** Structured request to partner agencies (not a lead dump)
- **Fill speed:** Slower — agency needs to source and confirm
- **Cost to restaurant:** External supply fee (see revenue model)
- **Approval:** Manager approval gate before external worker is confirmed

**The restaurant's experience is always the same regardless of tier:**

```
"Open shift received"
  → "Coverage in progress"  
    → "Candidate confirmed: Devon, Line Cook, arrives 5:45am"
      → "Shift filled"
```

The supply source is visible but never makes the experience feel fragmented.

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

## Revenue Model

### Core SaaS
Monthly per-location fee for the AI call-out system, internal cascade (Tier 1), and Backfill Native Lite dashboard.

### Fill Fee — Internal / Alumni (Tier 1 + 2)
Per successful fill, or bundled into premium plans.

### External Supply Fee — Agency Partner Route (Tier 3)
Two models to test:

**Model A — Referral fee (agency pays Backfill):**
Agency pays Backfill for each filled lead. Restaurant's cost doesn't change — they pay the agency directly for the worker.
- *Pro:* Easy sell to restaurants, no price increase for them
- *Con:* Depends on agency willingness to share margin

**Model B — Restaurant-side convenience fee (restaurant pays Backfill):**
Restaurant pays Backfill an external-supply fee on top of the agency's worker cost.
- *Pro:* Economics tied to restaurant relationship
- *Con:* If total cost is much higher than calling the agency directly, managers bypass Backfill for Tier 3

**Recommendation:** Test both. Model A may be easier to launch with. Model B works better if Backfill's speed and convenience justify the premium.

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

### Priority 1 — 7shifts (read + write)

Best first integration. Official docs show OAuth-based partner auth, webhooks, and writable endpoints.

**What we sync:**
- Employee roster → Backfill worker database
- Published schedules → Backfill shift records
- Shift changes/call-outs → automatic vacancy creation
- Availability/time-off → exclude unavailable workers from cascade

**What we write back:**
- Fill confirmations (updated shift assignment)
- Vacancy status

**Source of truth:** 7shifts owns the schedule. Backfill owns the fill orchestration. Final assignment writes back to 7shifts.

### Priority 2 — CSV + Backfill Native Lite

Fastest onboarding path for restaurants without 7shifts. Manager uploads a CSV of employees (name, phone, role) or enters them manually. Backfill Native Lite holds all operational state.

**Source of truth:** Backfill Native Lite is the truth for everything.

### Priority 3 — Homebase (read-only companion mode)

Homebase's published API is read-only. Backfill ingests roster and schedule data for context, but runs all vacancy/fill state in Backfill Native Lite.

**Source of truth:** Homebase for schedule context. Backfill Native Lite for fill operations.

### Priority 4 — Agency partner adapters

Start with email + structured SMS. Don't wait for formal APIs from agencies. Formalize with portals and APIs after demand proves out.

### Integration Architecture (adapter pattern)

```
┌───────────────┐  ┌──────────────┐  ┌──────────────┐
│   7shifts     │  │   Homebase   │  │   Backfill   │
│  OAuth + Hooks│  │  Read-only   │  │  Native Lite │
└──────┬────────┘  └──────┬───────┘  └──────┬───────┘
       │                  │                 │
       ▼                  ▼                 ▼
┌─────────────────────────────────────────────────────┐
│              BACKFILL SYNC LAYER                     │
│                                                     │
│  Each adapter implements:                           │
│    sync_roster(restaurant_id) → workers[]           │
│    sync_schedule(restaurant_id, date_range)→shifts[]│
│    on_vacancy(shift) → trigger cascade              │
│    push_fill(shift, worker) → update source         │
│      (no-op for read-only adapters)                 │
│                                                     │
│  Adding new platforms = writing a new adapter       │
│  Core engine never changes                          │
└─────────────────────────────────────────────────────┘
```

---

## Data Model

```
Restaurants
├── id, name, address
├── manager_name, manager_phone, manager_email
├── scheduling_platform: "7shifts" | "homebase" | "backfill_native"
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
├── current_tier: 1 | 2 | 3
├── current_position: int (index within current tier)
├── manager_approved_tier3: bool (gate for external supply)

OutreachAttempts
├── id, cascade_id, worker_id
├── tier: 1 | 2
├── channel: "sms" | "voice"
├── status: "pending" | "sent" | "delivered" | "responded" | "timed_out"
├── outcome: "accepted" | "declined" | "no_response" | "negotiating"
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
| Scheduling Integrations | **7shifts** (OAuth), **Homebase** (read-only), **Native Lite** (built-in) |
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

### Phase 1 — 14-Day MVP

**Build:**
- Toll-free number ported and connected (Twilio → Retell)
- Retell inbound call-out agent
- FastAPI backend with SQLite
- Worker roster with consent fields
- Shift/vacancy model
- SMS-first internal cascade (Tier 1 only)
- Manager notifications (SMS)
- Backfill Native Lite dashboard + CSV upload
- Consent ledger + audit log from day one

**Goal:** Worker calls out → vacancy created → internal worker accepts via SMS → manager notified.

**Test:** Call 1-800-BACKFILL → agent identifies you → creates vacancy → texts another phone you own → accept → shift marked filled → manager phone gets notification text.

### Phase 2 — 7shifts Production Pilot

**Build:**
- 7shifts OAuth connection
- Roster + shift sync (bidirectional where supported)
- Webhook listeners for shift changes/vacancies
- Write-back for fill confirmations
- Audit log + retry logic for sync failures
- Toll-free SMS verification complete → live SMS

**Goal:** Restaurant keeps 7shifts. Backfill handles the scramble layer. Manager sees the fill in 7shifts without leaving their normal tool.

### Phase 3 — Agency Partner Layer

**Build:**
- Agency partner directory (data model + seed data)
- Structured request routing (email/SMS first)
- SLA timers (auto-escalate to next agency if no response by deadline)
- Manager approval gate for external supply
- External supply fee logic
- Agency confirmation → fill workflow
- Agency fill writes back to restaurant dashboard

**Goal:** When internal coverage fails, Backfill routes to agency partners automatically. Restaurant stays inside one workflow. Manager approves before an external worker is confirmed.

### Phase 4 — Alumni Network + Behavioral Scoring

**Build:**
- Track which workers filled shifts at which restaurants (restaurants_worked)
- Tier 2 cascade: prioritize alumni/known workers before agency route
- Worker behavioral scoring:
  - Response rate (do they reply to outreach?)
  - Acceptance rate (do they take shifts?)
  - Show-up rate (did they actually arrive?)
  - Manager rating (post-shift 1-5 stars)
  - Repeat requests (does the restaurant ask for them again?)
- High-scoring workers offered shifts first
- Consecutive ghosts → deprioritized → eventually deactivated
- Repeat-booked workers → auto-promoted to Tier 2 for that restaurant

**Goal:** Reduce agency dependence and improve margins through a trusted alumni network before ever considering a direct Backfill labor pool.

### Phase 5+ — Future Considerations (deferred, not deleted)

- Backfill-owned worker pool (if agency partner data reveals opportunity)
- HotSchedules integration (enterprise sales)
- Additional scheduling platform adapters (Toast, When I Work, Sling)
- Worker-facing mobile experience
- Advanced analytics and reporting
- Multi-vertical expansion (healthcare, security, manufacturing)

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

### Outbound SMS Agent

```
You are a shift coordinator texting from Backfill on behalf of 
{{restaurant_name}}, reaching out to {{worker_name}}.

SHIFT DETAILS:
- Role: {{role}}
- Date: {{shift_date}}
- Time: {{start_time}} to {{end_time}}
- Location: {{restaurant_name}}
- Pay Rate: {{pay_rate}}/hr

TEXTING GUIDELINES:
- Keep messages SHORT — 1-3 sentences max
- First message: "Hi {{worker_name}}, this is Backfill for 
  {{restaurant_name}}. We have a {{role}} shift on {{shift_date}} 
  from {{start_time}}-{{end_time}} at {{pay_rate}}/hr. Can you 
  pick it up? Reply YES or NO."
- Yes → "Great, you're confirmed for {{role}} on {{shift_date}} 
  {{start_time}}-{{end_time}} at {{restaurant_name}}. See you there!"
- No → "No worries, thanks for letting us know!"
- Questions → answer concisely from shift details
- No emojis, no over-explaining
```

---

## Website as Support Layer

The website (backfill.com) handles things that are hard to do over phone/text. Nobody needs to visit the website to get started.

**For workers (backfill.com/join):**
- Complete profile (pre-filled from phone data)
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

| Day | Milestone | "It Works When..." |
|-----|-----------|---------------------|
| 3 | Telephony live | You call 1-800-BACKFILL and Retell's agent picks up |
| 5 | Inbound call-out | Agent greets you by name, confirms restaurant, creates vacancy |
| 7 | Outbound fill (Tier 1) | Vacancy → SMS to worker → accept → shift filled → manager notified |
| 10 | SMS + voice cascade | SMS first → no reply → voice call → decline → next worker |
| 14 | Full Tier 1 loop | Call out → cascade → filled → manager notified. End to end, zero humans. |

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
| HotSchedules integration | Enterprise sales, complex API access | After 7shifts pilot proves the model |
| Full native scheduling suite | Competes with 7shifts; out of lane | Never — stay as companion tool |
| Staffing agency licensing | Not needed if Backfill routes, not employs | If Backfill builds its own pool |
