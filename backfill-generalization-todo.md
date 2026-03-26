# Backfill Vertical Generalization Todo

Backfill should work for any hourly, shift-based operator by location, not just restaurants. That means the product language, data model, prompts, UI, and APIs need to stop assuming every customer is a restaurant.

This is needed. `restaurant` is currently a first-class concept across backend models, routes, web UI, prompts, tests, and planning docs.

## Goal

Reframe Backfill from:

- restaurant coverage infrastructure

to:

- location-based coverage infrastructure for hourly work
- usable by restaurants, healthcare facilities, warehouses, retail stores, hospitality groups, and similar shift-based operators

## Guiding rule

Generalize the platform model without losing support for restaurant-specific integrations like 7shifts and Homebase.

That means:

- generic core domain
- vertical-specific integrations and copy layered on top
- safe migration path instead of a full rename all at once

## Phase 1: Product and copy cleanup

- Replace user-facing `restaurant` language with broader terms like `location`, `business`, `site`, `operator`, or `company location` where the UI is not specifically about a restaurant integration.
- Update homepage and onboarding copy in [web/app/page.tsx](/Users/carcam07/Backfill/web/app/page.tsx), [web/app/setup/connect/page.tsx](/Users/carcam07/Backfill/web/app/setup/connect/page.tsx), [web/app/setup/upload/page.tsx](/Users/carcam07/Backfill/web/app/setup/upload/page.tsx), [web/app/setup/add/page.tsx](/Users/carcam07/Backfill/web/app/setup/add/page.tsx), [web/app/join/page.tsx](/Users/carcam07/Backfill/web/app/join/page.tsx), and dashboard pages under [web/app/dashboard](/Users/carcam07/Backfill/web/app/dashboard).
- Replace labels like `Restaurant dashboard`, `Restaurant detail`, `Restaurant setup`, and `Restaurant name` with generalized equivalents.
- Update API error messages that currently say `Restaurant not found` when they should say `Location not found` or `Account not found`.
- Rewrite prompt text that assumes restaurant-only callers in [app/prompts/inbound_unknown.txt](/Users/carcam07/Backfill/app/prompts/inbound_unknown.txt) and the other inbound/outbound prompt files.
- Update [web/README.md](/Users/carcam07/Backfill/web/README.md) and top-level planning docs so the repo narrative no longer narrows the product prematurely.

## Phase 2: Introduce a vertical-aware core model

- Add an explicit vertical field to the top-level customer entity.
- Recommended values:
  - `restaurant`
  - `healthcare`
  - `warehouse`
  - `retail`
  - `hospitality`
  - `other`
- Add optional fields for generalized classification, for example:
  - `company_name`
  - `location_name`
  - `vertical`
  - `location_type`
  - `department_labels`
  - `site_notes`
- Keep the current `restaurants` table temporarily if needed, but evolve it toward a generic `locations` concept.
- Decide whether `manager_*` fields should become broader `primary_contact_*` fields with compatibility aliases.

## Phase 3: Backend naming refactor

- Create a migration plan for moving from `Restaurant` to `Location` in the backend models.
- Likely targets:
  - [app/models/restaurant.py](/Users/carcam07/Backfill/app/models/restaurant.py)
  - [app/db/database.py](/Users/carcam07/Backfill/app/db/database.py)
  - [app/db/queries.py](/Users/carcam07/Backfill/app/db/queries.py)
  - [app/routes.py](/Users/carcam07/Backfill/app/routes.py)
  - [app/services/caller_lookup.py](/Users/carcam07/Backfill/app/services/caller_lookup.py)
  - [app/services/scheduling.py](/Users/carcam07/Backfill/app/services/scheduling.py)
  - [app/services/agency_router.py](/Users/carcam07/Backfill/app/services/agency_router.py)
- Replace `restaurant_id` with `location_id` in the core domain over time.
- Replace helper names like `get_restaurant`, `insert_restaurant`, `list_restaurants`, and `get_restaurant_status` with generic equivalents.
- Preserve compatibility at the route and query layer during migration if the frontend still expects `/restaurants` and `restaurant_id`.

## Phase 4: API and compatibility strategy

- Decide whether to:
  - keep existing `/api/restaurants` endpoints for compatibility and add `/api/locations`
  - or fully rename endpoints and update the frontend in one pass
- Preferred approach:
  - add `/api/locations`
  - keep `/api/restaurants` as compatibility aliases temporarily
- Add response shapes that expose generalized fields while still supporting current clients.
- Update onboarding and manager actions so they operate on `location_id` semantics instead of restaurant-only assumptions.

## Phase 5: Web app type and route cleanup

- Replace frontend types like `Restaurant` and `RestaurantStatusResponse` in [web/lib/types.ts](/Users/carcam07/Backfill/web/lib/types.ts) with generalized types.
- Update [web/lib/api.ts](/Users/carcam07/Backfill/web/lib/api.ts) and [web/lib/server-api.ts](/Users/carcam07/Backfill/web/lib/server-api.ts) to use generic names.
- Rename dashboard route structure over time from `/dashboard/restaurants/[restaurantId]` to a generic location-oriented path.
- Keep old routes redirecting or aliasing until internal links and bookmarks are updated.

## Phase 6: Workflow generalization

- Audit all copy and logic that assumes restaurant-specific roles, examples, or operating context.
- Replace examples like `line cook`, `Chef Mike`, and `Coastal Grill` with neutral or vertical-aware examples where appropriate.
- Ensure shift requirements and certifications can represent non-restaurant cases like:
  - forklift certification
  - CNA or LPN credentials
  - badge clearance
  - department-specific training
- Review manager notification copy in [app/services/notifications.py](/Users/carcam07/Backfill/app/services/notifications.py) so it works for any location.
- Review outreach copy in [app/services/outreach.py](/Users/carcam07/Backfill/app/services/outreach.py) so it reads naturally for all verticals.

## Phase 7: Integration architecture cleanup

- Separate vertical-neutral scheduling concepts from restaurant-specific integrations.
- Make the integration layer clearly support:
  - generic shift-source adapters
  - vertical-specific adapters
- Keep 7shifts, Homebase, and restaurant-first tools as restaurant adapters, not as proof that the whole product is restaurant-only.
- Define the next likely non-restaurant integration candidates before changing too much copy. This will force the abstraction to be real.
- Add vertical-specific integration availability rules to the setup flow so the UI can say:
  - restaurants: 7shifts, Deputy, When I Work, Homebase
  - healthcare: future integrations
  - warehouse/retail: future integrations

## Phase 8: Prompt and voice-agent cleanup

- Update inbound prompts so callers can identify a business, facility, store, warehouse, clinic, or site instead of only a restaurant.
- Update manager onboarding prompts so they ask for a business location and operating context, not only restaurant details.
- Update worker/job-seeker prompts to avoid assuming restaurant roles.
- Review any function-call descriptions used by Retell setup scripts so tool semantics stay generic.

## Phase 9: Tests and seed data

- Replace restaurant-only fixture names and helper names in tests with generic location-oriented ones where possible.
- Add at least one non-restaurant scenario to the suite, for example:
  - warehouse picker shift
  - healthcare aide shift
- Update seed scripts in [scripts/seed_data.py](/Users/carcam07/Backfill/scripts/seed_data.py) and [scripts/seed_agencies.py](/Users/carcam07/Backfill/scripts/seed_agencies.py) to include multiple verticals.
- Keep restaurant integration tests intact, but make the core engine tests vertical-neutral.

## Phase 10: Planning docs and positioning

- Update [backfill-gameplan-v4.md](/Users/carcam07/Backfill/backfill-gameplan-v4.md) to distinguish:
  - current launch wedge: restaurants
  - long-term platform scope: any hourly workforce by location
- Remove statements that imply restaurants are the permanent scope of the product.
- Keep explicit notes where restaurant specificity is still true today, especially around integrations and go-to-market.

## Recommended implementation order

1. Generalize copy, prompts, labels, and examples first.
2. Add `vertical` and generalized fields to the current data model.
3. Introduce backend and frontend aliases for `Location` while preserving compatibility.
4. Migrate core code paths from `restaurant_*` to `location_*`.
5. Rename routes and types once compatibility shims are in place.
6. Expand tests and seed data to prove non-restaurant workflows.

## Important constraint

Do not break the current restaurant workflow while generalizing.

The safe target is:

- restaurants remain the best-supported launch vertical
- the core product stops hard-coding restaurant assumptions
- future verticals can be onboarded without rewriting the platform model again
