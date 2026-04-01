# Backfill V2 Architecture

## Goal

Backfill V2 is the Postgres-first rewrite of the backend as a modular monolith. The current SQLite app remains live while V2 is built in parallel.

V2 target domains:

- `identity_access`
- `business_directory`
- `workforce`
- `scheduling`
- `coverage_engine`
- `messaging`
- `audit_analytics`

## Deployment Shape

Keep the current platform split:

- `www.usebackfill.com` on Vercel
- `api.usebackfill.com` on Railway
- `Backfill Postgres` on Railway

Recommended Railway service wiring:

- API service env:
  - `V2_DATABASE_URL=${{Postgres.DATABASE_URL}}`
  - `DATABASE_URL` stays pointed at SQLite only until cutover is deliberate
- Add a dedicated V2 preview service only if we want side-by-side runtime testing before replacing the existing API

## Library Stack

- FastAPI
- SQLAlchemy 2 async
- `asyncpg` for runtime database access
- Alembic for migrations
- `psycopg` for migration/sync tooling

## V2 Schema

Identity and access:

- `users`
- `memberships`
- `manager_invites`
- `otp_challenges`
- `sessions`

Business directory:

- `businesses`
- `locations`
- `roles`
- `location_roles`

Workforce:

- `employees`
- `employee_roles`
- `employee_location_clearances`
- `employee_availability_rules`
- `employee_availability_exceptions`

Scheduling:

- `shifts`
- `shift_assignments`

Coverage engine:

- `coverage_cases`
- `coverage_case_runs`
- `coverage_candidates`
- `coverage_offers`
- `coverage_offer_responses`
- `coverage_contact_attempts`
- `outbox_events`

Audit:

- `audit_logs`

## Modeling Rules

- Users are global identities; memberships attach them to a business or location.
- Employees belong to businesses, not locations.
- Roles belong to businesses.
- Locations activate a subset of business roles through `location_roles`.
- A shift is demand. A shift assignment is staffing history.
- Coverage is explicit and stateful:
  - `coverage_cases`
  - `coverage_case_runs`
- `coverage_candidates`
- `coverage_offers`
- `coverage_offer_responses`
- `coverage_contact_attempts`

## Coverage MVP

Phase 1:

- same-location staffing only
- role match required
- recurring availability + exceptions
- deterministic candidate ranking
- sequential offer orchestration

Phase 2:

- multi-location coverage using `employee_location_clearances`
- blast mode / parallel offer windows
- premium rules
- richer scoring and prioritization
- durable outbox-driven delivery

## Why Postgres Now

SQLite is adequate for the prototype but not for the MVP coverage engine. The MVP needs:

- safe concurrent workers
- transactional claim/accept flows
- stronger indexing
- durable queue/outbox processing
- multi-instance API and worker runtime support

## Cutover Order

1. Land V2 schema and migrations.
2. Build V2 repositories/services for identity and access.
3. Build V2 business/location/workforce APIs.
4. Build scheduling + coverage engine Phase 1.
5. Repoint onboarding and dashboard reads to V2.
6. Build Phase 2 cross-location coverage.
7. Move `DATABASE_URL` on Railway API to Postgres and retire SQLite paths.
