# Backend Deploy

This repo is already split correctly for production:

- `usebackfill.com` serves the Next.js frontend from Vercel.
- `api.usebackfill.com` should serve the FastAPI backend from a container host.
- a second non-public worker service should run the runtime loop that drains outbox events and background work.

Do not point Retell at `https://usebackfill.com/webhooks/retell` unless the backend is actually mounted there. Right now the clean deployment shape is a separate backend origin.

## Target shape

- Frontend: `https://usebackfill.com`
- Backend API: `https://api.usebackfill.com`
- Backend worker: separate private service from the same image with `BACKFILL_SERVICE_MODE=worker`
- Retell webhook: `https://api.usebackfill.com/webhooks/retell`
- Optional split-mode Twilio SMS webhook: `https://api.usebackfill.com/webhooks/twilio/sms`

## What was added

- Health check: `GET /healthz`
- Optional CORS env: `BACKFILL_ALLOWED_ORIGINS`
- Container image: [`Dockerfile`](./Dockerfile)
- Image hygiene: [`.dockerignore`](./.dockerignore)

## Required backend env vars

Minimum:

```env
DATABASE_URL=/data/backfill.db
BACKFILL_ALLOWED_ORIGINS=https://usebackfill.com,https://www.usebackfill.com
BACKFILL_WEBHOOK_URL=https://api.usebackfill.com

RETELL_API_KEY=...
RETELL_FROM_NUMBER=+14244992663
RETELL_AGENT_ID_INBOUND=...
RETELL_AGENT_ID_OUTBOUND=...
RETELL_CHAT_AGENT_ID=...
RETELL_SMS_ENABLED=true

TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
BACKFILL_PHONE_NUMBER=+14244992663
```

Add scheduling provider credentials only if you are actively using them.

## Deploy the backend

Deploy this repo's root as a Docker service on your preferred container host.

Build behavior:

```bash
docker build -t backfill-api .
docker run -p 8000:8000 --env-file .env backfill-api
```

API mode (`BACKFILL_SERVICE_MODE=api`, default) serves:

- API routes under `/api/*`
- Retell webhook under `/webhooks/retell`
- Twilio webhook under `/webhooks/twilio/sms`
- health check at `/healthz`

Worker mode (`BACKFILL_SERVICE_MODE=worker`) runs the durable background loop directly against Postgres:

- processes schedule publish notification outbox rows
- processes coverage delivery outbox rows
- runs provider callback processing
- runs runtime projection freshness checks
- runs the coverage runtime tick

Recommended worker env:

```env
BACKFILL_SERVICE_MODE=worker
BACKFILL_WORKER_POLL_SECONDS=10
BACKFILL_WORKER_BATCH_LIMIT=20
BACKFILL_WORKER_ERROR_BACKOFF_SECONDS=15
```

Recommended Railway shape:

- `Backfill API` service
  - public networking enabled
  - `BACKFILL_SERVICE_MODE=api`
- `Backfill Worker` service
  - no public networking required
  - same repo / same Docker image
  - `BACKFILL_SERVICE_MODE=worker`

Do not rely on schedule publish notifications, feed projections, or other outbox-driven workflows unless the worker service is running.

## DNS

Create a subdomain:

- `api.usebackfill.com` -> your backend host

After DNS resolves, verify:

```bash
curl https://api.usebackfill.com/healthz
curl https://api.usebackfill.com/api/locations
```

Expected:

- `/healthz` returns `200 {"status":"ok"}`
- `/api/locations` returns `200` with JSON or an empty array

## Frontend env on Vercel

In the Vercel project for the `web` app, set:

```env
BACKFILL_API_BASE_URL=https://api.usebackfill.com
```

That is what the frontend already expects in [`web/lib/api.ts`](./web/lib/api.ts) and [`web/lib/server-api.ts`](./web/lib/server-api.ts).

## Retell after backend deploy

After `api.usebackfill.com` is live:

1. Run `python3 scripts/setup_retell_agents.py` so the live Retell agents pick up the current webhook, tool schema, and prompts.
2. Copy the returned agent IDs into the backend env.
3. Run `python3 scripts/setup_retell_phone_number.py` so the Retell phone number is bound to the current inbound/outbound agents and the inbound webhook is set to `https://api.usebackfill.com/webhooks/retell`.
4. Publish the voice agent
5. Create or update the Retell SMS chat agent with the same webhook
6. Bind that chat agent to the Retell phone number for inbound and outbound SMS
7. Keep the Retell phone number termination URI pointed at `backfill.pstn.twilio.com`

## Persistence note

This repo still uses SQLite. That is acceptable for early-stage testing or a single-instance backend, but only if your backend host gives you persistent disk storage mounted to the `DATABASE_URL` path.

If the host is fully ephemeral, the database will disappear on restart. In that case, move `DATABASE_URL` to a persistent mounted volume path or migrate to Postgres before going live.
