# Developer 3 Projection/Ops Verification Plan

**For:** Developer 3 (Projection Consumers, Read-Heavy Ops Surfaces, and Verification)  
**Based on:** origin/main@a3af3df  
**Date:** 2026-04-11  
**Note:** This is NOT Phase 6/7/8 from the main execution plan (Phase 7=Cost Ledger, Phase 8=Billing Ledger). This is Developer 3's owned projection, ops, and verification work.

---

## Overview

Developer 3 owns projection consumers, read-heavy ops surfaces, and final verification infrastructure. The architect has confirmed that several foundational components ALREADY EXIST on origin/main but may not be visible in the current stale worktree.

---

## Context from Architect's Brief

### What's Already True on origin/main@a3af3df:
- `platform_events` is the canonical event spine
- Worker runtime and orchestration already exist
- Feed projections already exist
- Logical outreach model already exists
- Copilot has LLM-backed planning and one real mutation tool (`roster.update_availability`)
- Cost and billing ledger foundations already exist

### What Developer 3 Does NOT Own:
- No shared schema changes
- No canonical event contracts
- No worker locking/claim semantics
- No finance truth logic
- Not here to redesign the model

---

## Developer 3's Tasks

### 1. Phase 6 Hardening: Projection Health and Rebuild Visibility

Add read-only/internal status endpoints for operators and internal ops surfaces:

- **Projection lag** - how far behind the projection is from real-time events
- **Cursor state** - current position in the event stream
- **Last success** - timestamp of last successful projection rebuild
- **Last error** - any errors encountered during projection processing
- **Rebuild state** - current status of any in-progress rebuilds

**Files to work with:**
- `app/api/routes/ops.py` (if it exists on origin/main)
- `app/services/feed_projections.py` (if it exists on origin/main)
- Need new internal routes for projection health checks

### 2. Phase 6 Hardening: Replay/Rebuild Verification

Add stronger end-to-end tests:

- **Empty-state rebuild** - verify projection builds correctly from zero events
- **Multi-batch replay** - verify projection handles events across multiple batches
- **Cursor catch-up** - verify cursor advances correctly after processing
- **Projection-vs-raw parity** - verify projection data matches raw platform_events

**Files to work with:**
- `tests/test_feed_projections.py` (if it exists on origin/main)
- `tests/test_feed_projections_integration.py` (if it exists on origin/main)
- `tests/test_ops_routes.py` (if it exists on origin/main)

### 3. Ops/Read-Only Reporting Support Work

Add internal or ops-facing reporting on top of stable projection APIs:

- Campaign status surfaces (read-only)
- Outreach status surfaces (read-only)
- Keep it additive and read-only
- **internal or ops-facing only**
- **additive only**
- **no new public campaign/outreach read contract without approval from architect**

**Rules:**
- NO migrations
- NO contract redesign
- NO worker claim changes
- NO finance logic changes
- NO dashboard UI changes unless explicitly approved

---

## Technical Context

### Platform Events (Source of Truth)
From `app/services/platform_events.py`:

- `PlatformEvent.append()` - writes events to the canonical event spine
- `PlatformEvent.list_events()` - reads events with filtering
- Event types include: coverage campaigns, offers, costs, billing, copilot actions

### Feed Projections (Derived Read Model)
Expected to exist on origin/main:
- `app/services/feed_projections.py` - rebuildable read models derived from platform_events
- Should provide efficient queries for dashboard feed consumption

### Dashboard Feed Consumer
Expected to exist on origin/main:
- `web/components/dashboard/DashboardActivityFeedPanel.tsx` - consumes projection-backed events

---

## Execution Steps

### Step 1: Ensure Correct Branch
```bash
git fetch origin
git checkout main
git pull origin main
git checkout -b projection-next-health-and-verification
```

### Step 2: Verify Existing Files
Confirm these files exist on origin/main:
- `app/services/feed_projections.py`
- `app/api/routes/ops.py`
- `app/schemas/ops.py`
- `tests/test_feed_projections.py`
- `tests/test_feed_projections_integration.py`
- `tests/test_ops_routes.py`
- `web/components/dashboard/DashboardActivityFeedPanel.tsx`

### Step 3: Add Projection Health Visibility
- Add read-only `/internal/projections/health` or `/ops/projections/status` endpoint
- Return: cursor position, lag metrics, last success/error timestamps

### Step 4: Add Verification Tests
- Test empty-state rebuild scenarios
- Test multi-batch replay
- Test cursor catch-up behavior
- Test projection vs raw platform_events parity

### Step 5: Add Read-Only Ops Surfaces
- Add internal endpoints for campaign/outreach status
- Keep additive and read-only

---

## Key Constraints

1. **DO NOT touch migrations**
2. **DO NOT redesign canonical event contracts**
3. **DO NOT modify worker claim semantics**
4. **DO NOT change finance truth logic**
5. **DO NOT modify dashboard UI without explicit approval**

If a real contract gap is discovered, route it to the architect instead of creating a second model.

---

## Todo List for Code Mode

- [ ] Branch from origin/main@a3af3df
- [ ] Verify existing feed_projections.py, ops.py, tests exist
- [ ] Add projection health/lag/cursor visibility to ops routes
- [ ] Add empty-state rebuild test
- [ ] Add multi-batch replay test
- [ ] Add cursor catch-up test
- [ ] Add projection-vs-raw parity test
- [ ] Add read-only campaign/outreach status endpoints
- [ ] End-to-end verification with existing components