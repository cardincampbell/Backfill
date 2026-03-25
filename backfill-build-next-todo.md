# Backfill Build-Next Todo

## 1. Stabilize the current Tier 1 flow

- Exclude the calling-out worker from replacement outreach.
- Match Tier 1 candidates by role, certifications, and availability, not just restaurant membership and consent.
- Tune outreach sequencing by urgency and worker preference instead of assuming a universal SMS-first rule.
- Notify the manager when Tier 1 is exhausted and capture the approval gate for Tier 3.
- Prevent duplicate vacancy side effects when the same shift is backfilled twice.

## 2. Make the prototype genuinely testable

- Replace placeholder tests with assertions that exercise the cascade, consent, caller lookup, and webhook flows.
- Add API tests for restaurant, worker, shift, CSV import, and backfill endpoints.
- Add failure-path tests for exhausted cascades, revoked consent, duplicate workers, and invalid webhook payloads.
- Clean up pytest-asyncio fixture usage so the suite does not rely on deprecated behavior.

## 3. Finish Native Lite as the companion record

- Add list/update endpoints for restaurants, workers, shifts, cascades, and audit log.
- Add vacancy, assignment, and outreach-history views for operators.
- Add CSV export for roster and shift data.
- Add a minimal dashboard/status surface for active fills and recent outcomes.

## 4. Implement Retell-driven inbound and outbound workflows

- Complete inbound call-out handling for known worker, known manager, and unknown caller flows.
- Add inbound SMS handling, including STOP/opt-out keywords and basic routing.
- Support open-shift lookup, manager status checks, and manager-created open shifts.
- Formalize Retell function-call payload validation and error handling.

## 5. Build the missing source-of-truth adapter work

- Implement 7shifts roster/schedule sync, webhook intake, and fill write-back.
- Implement Deputy roster/schedule sync, webhook intake, and fill write-back.
- Implement When I Work read path first, then confirm whether write-back is possible.
- Implement Homebase read-only sync and Native Lite companion behavior around it.

## 6. Add Tier 2 alumni support

- Expand the worker model to support multi-restaurant history and restaurant-specific assignments.
- Track prior successful fills and restaurant-approved flex pools.
- Rank alumni candidates using behavioral signals and restaurant familiarity.

## 7. Add Tier 3 agency routing

- Implement agency partner matching by area, role, certifications, and SLA tier.
- Create agency request lifecycle handling with deadlines, responses, and confirmations.
- Support manager approval before external worker confirmation.
- Start with structured email/SMS transport, then portal/API later.

## 8. Improve audit, reporting, and ops visibility

- Expose audit-log reads and filterable event history.
- Track outreach delivery, response timing, accept/decline reasons, and fill outcomes.
- Add metrics needed for response rate, acceptance rate, fill rate, and partner SLA scoring.

## 9. Tighten data model alignment with the gameplan

- Add assignment records instead of relying only on `shift.filled_by`.
- Add explicit vacancy records if shift and vacancy state need to diverge.
- Add manager approval state and agency request references where workflows require them.

## 10. Build the support-layer product surface

- Add the lightweight website/dashboard described in the gameplan for uploads, status, and billing support.
- Add onboarding/import flows for managers who do not use a writable scheduler.
