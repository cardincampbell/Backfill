# Backfill Build-Next Todo

Immediate repo changes required to align the product with [`backfill-gameplan-v4.md`](./backfill-gameplan-v4.md).

## 1. Reframe product copy and metadata around the v4 thesis

- Replace "AI coordination layer" / "AI shift coverage" language with the new positioning: autonomous coverage infrastructure / autonomous coverage engine.
- Update FastAPI app metadata in [`main.py`](./main.py) and site metadata in [`web/app/layout.tsx`](./web/app/layout.tsx).
- Rewrite homepage copy in [`web/app/page.tsx`](./web/app/page.tsx) so it sells the command surface, zero-manager-involvement flow, and one-notification outcome.
- Remove "support-layer placeholder" / "reserved for later" language that now conflicts with the v4 onboarding and partner roadmap in [`web/app/page.tsx`](./web/app/page.tsx), [`web/app/join/page.tsx`](./web/app/join/page.tsx), [`web/app/partners/page.tsx`](./web/app/partners/page.tsx), and [`web/README.md`](./web/README.md).
- Update prompt copy that still describes Backfill as a generic AI service, especially [`app/prompts/inbound_unknown.txt`](./app/prompts/inbound_unknown.txt).

## 2. Replace the sequential Tier 1/Tier 2 engine with broadcast + standby

- Rewrite [`app/services/cascade.py`](./app/services/cascade.py) so urgent fills default to broadcast mode instead of one-worker-at-a-time outreach.
- Add first-to-claim logic so the first YES confirms the shift and later YES responses become ranked standby entries instead of double-filling the shift.
- Add standby promotion flow for cancellation/no-show recovery before escalating to a new batch or the next tier.
- Preserve sequential mode as an explicit fallback for lower-urgency or preference-sensitive fills instead of making it the only engine.
- Update outbound SMS wording in [`app/services/outreach.py`](./app/services/outreach.py) and [`app/prompts/outbound_sms.txt`](./app/prompts/outbound_sms.txt) to explain first-come confirmation and standby honestly.

## 3. Extend the data model for coverage events, standby state, and future billing

- Expand `cascades` in [`app/db/database.py`](./app/db/database.py), [`app/db/queries.py`](./app/db/queries.py), [`app/models/cascade.py`](./app/models/cascade.py), and [`web/lib/types.ts`](./web/lib/types.ts) to include:
  `outreach_mode`, `current_batch`, `confirmed_worker_id`, and standby queue state.
- Expand `outreach_attempts` to support v4 outcomes:
  `confirmed`, `standby`, `declined`, `no_response`, `promoted`, `standby_expired`, plus `standby_position` and `promoted_at`.
- Stop relying only on `shifts.filled_by` as the operational record; add explicit assignment / coverage event records so confirmation and promotion history are queryable.
- Add explicit vacancy records if we want vacancy state to diverge cleanly from shift state.
- Add a fill event / billable event record so utility pricing can be instrumented later without reworking the coverage flow again.

## 4. Rework inbound and outbound webhook/tooling around the v4 conversation model

- Replace `confirm_fill` with atomic claim/standby functions in [`app/webhooks/retell_hooks.py`](./app/webhooks/retell_hooks.py) and [`scripts/setup_retell_agents.py`](./scripts/setup_retell_agents.py):
  `claim_shift`, `cancel_standby`, `promote_standby`, and any helper needed for standby expiration.
- Add manager onboarding routing tools and handlers:
  `send_onboarding_link`, plus a restaurant setup intake function if we want to persist the first call immediately.
- Add stronger function-call validation in [`app/webhooks/retell_hooks.py`](./app/webhooks/retell_hooks.py); the current dispatcher trusts payload shape too much for a larger tool surface.
- Split prompt coverage cleanly across call-out, manager onboarding, job seeker, and unknown caller flows instead of overloading the current inbound prompts.
- Update Twilio inbound SMS handling in [`app/webhooks/twilio_hooks.py`](./app/webhooks/twilio_hooks.py) for broadcast semantics:
  YES can confirm or enter standby, CANCEL can leave standby, STATUS remains available for managers, STOP still revokes consent.

## 5. Add the onboarding router and setup surfaces the gameplan now depends on

- Create setup routes in the Next app for the paths described in v4:
  `/setup/connect`, `/setup/upload`, and `/setup/add`.
- Add a manager onboarding flow that starts by phone and hands structured data collection to the right web path instead of trying to do everything in one channel.
- Add lightweight pages/forms for manual team entry and CSV upload so "no scheduler" restaurants have a real onboarding path.
- Surface integration-specific copy for 7shifts, Deputy, When I Work, and Homebase companion mode instead of generic dashboard copy.
- Keep [`web/app/join/page.tsx`](./web/app/join/page.tsx) aligned with the new worker follow-up flow: consent text -> profile completion -> certifications -> confirmed shifts.

## 6. Tighten manager experience to the new notification defaults

- Keep managers out of routine coordination: no per-attempt noise, no unnecessary progress updates.
- Ensure the default success notification is one concise outcome message from [`app/services/notifications.py`](./app/services/notifications.py): who filled, what role, when they arrive.
- Treat cascade exhaustion and Tier 3 approval as exception paths only.
- Add standby-promotion notifications only when they materially change who is coming to the shift.
- Expose on-demand status checks via phone/SMS/dashboard without making them part of the normal notification stream.

## 7. Make Native Lite explicitly the companion operational ledger

- Rename the product surface in docs/UI from "dashboard support layer" to the v4 framing: Native Lite as the minimum operational ledger.
- Add missing operational views for vacancies, assignments, outreach history, and integration sync state in [`web/app/dashboard/page.tsx`](./web/app/dashboard/page.tsx) and corresponding API payloads.
- Show companion-mode messaging for Homebase and any read-only When I Work path: schedule in external tool, fill workflow in Backfill.
- Make restaurant records capture onboarding path and integration status, not just platform name.

## 8. Align the integration layer with the v4 onboarding promise

- Treat all four scheduler adapters as Phase 1 critical path, not optional follow-on work.
- Finish parity across 7shifts, Deputy, When I Work, and Homebase for roster/schedule ingest, vacancy detection, and correct companion/write-back behavior.
- Add integration-status visibility to the dashboard and API so onboarding can explain what is connected, syncing, read-only, or failing.
- Make the "use your scheduler if we can write to it; otherwise Backfill holds fill state" rule explicit in adapter behavior and UI copy.

## 9. Bring agency partner work out of placeholder mode

- Keep the existing agency router work, but remove repo language that implies partner UX is out of scope.
- Add the minimum partner workflow the v4 plan assumes: request status, response deadline, candidate pending, and final confirmation visibility.
- Keep transport simple for now: structured SMS/email first, portal later.
- Preserve the manager approval gate before any Tier 3 confirmation is finalized.

## 10. Update tests to the new operating model before adding more product surface

- Rewrite cascade tests in [`tests/test_cascade.py`](./tests/test_cascade.py) around broadcast batches, first-YES-wins, standby ranking, standby promotion, and escalation rules.
- Update SMS/webhook tests in [`tests/test_twilio_webhook.py`](./tests/test_twilio_webhook.py) and [`tests/test_retell.py`](./tests/test_retell.py) for `YES` -> confirm-or-standby behavior and `CANCEL` standby exits.
- Add API/UI coverage for the new setup routes and onboarding link handoff.
- Add regression tests so a second YES cannot overwrite the confirmed worker once a shift is locked.
- Add tests for manager notification defaults: filled, exhausted, Tier 3 approval, and status-on-demand.

## Immediate order of operations

1. Update copy, prompts, and metadata so the repo stops contradicting the new thesis.
2. Change the cascade/data model together: broadcast mode, standby state, and atomic claim handling.
3. Update Twilio/Retell tooling to match the new engine.
4. Add `/setup/*` onboarding surfaces and dashboard changes that the phone flow now depends on.
5. Expand tests around the new coverage behavior before doing deeper integrations or pricing work.
