# Twilio + Retell Setup

This repo now supports two modes:

- Split mode: Retell handles voice, Twilio handles SMS directly.
- Unified mode: Retell handles inbound and outbound calls plus SMS conversations, with Twilio acting as transport underneath the Retell number.

## 1. Choose the telephony shape

You have two practical deployment modes:

1. Fastest path: use a Retell-managed voice number and a Twilio SMS number.
2. Branded single-number path: import your Twilio number into Retell for voice and SMS, with Retell owning the conversation layer.

If your goal is "use my Twilio number in Retell AI," you want the second path.

## 2. Prepare the public backend URL

Backfill needs a public HTTPS URL before you configure anything in Twilio or Retell.

For local development:

```bash
uvicorn main:app --reload
ngrok http 8000
```

Put the public URL into `.env`:

```env
BACKFILL_WEBHOOK_URL=https://your-public-url.ngrok.io
```

The app endpoints you will use are:

- Retell webhook: `POST {BACKFILL_WEBHOOK_URL}/webhooks/retell`
- Twilio inbound SMS webhook: `POST {BACKFILL_WEBHOOK_URL}/webhooks/twilio/sms` in split mode only

## 3. Fill in the core env vars

At minimum, set:

```env
RETELL_API_KEY=...
RETELL_FROM_NUMBER=+18002225345
RETELL_AGENT_ID_INBOUND=
RETELL_AGENT_ID_OUTBOUND=
RETELL_CHAT_AGENT_ID=
RETELL_SMS_ENABLED=true

TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
BACKFILL_PHONE_NUMBER=+18002225345
BACKFILL_WEBHOOK_URL=https://your-public-url.ngrok.io
```

If you are using the same public number for voice and SMS, `RETELL_FROM_NUMBER` and `BACKFILL_PHONE_NUMBER` should be the same E.164 number.

## 4. Configure the Twilio number

In Twilio:

1. Buy or port the number you want to use.
2. If it is a US/Canada toll-free number, complete Twilio toll-free verification before expecting live SMS delivery.
3. Choose one:

Split mode, current Twilio SMS path:

```text
{BACKFILL_WEBHOOK_URL}/webhooks/twilio/sms
```

Use `HTTP POST`.

Unified mode, Retell-owned SMS path:
- point the Twilio number SMS webhook to the Retell Twilio SMS webhook URL shown on the number
- attach inbound and outbound SMS chat agents to the Retell number
- keep Backfill integrated through the Retell agent webhook, not the Twilio SMS webhook

Backfill validates `X-Twilio-Signature` when `TWILIO_AUTH_TOKEN` is configured, so your production webhook should stay on the real Twilio number instead of a test relay.

## 5. Create the Retell agents

Bootstrap the current Backfill voice and chat agents:

```bash
python3 scripts/setup_retell_agents.py
```

Copy the printed IDs into:

```env
RETELL_AGENT_ID_INBOUND=...
RETELL_AGENT_ID_OUTBOUND=...
RETELL_CHAT_AGENT_ID=...
```

The generated tool contracts are location-first and match the handlers in [`app/webhooks/retell_hooks.py`](./app/webhooks/retell_hooks.py).

## 6. Import or update the Twilio number in Retell

If you want your Twilio number to power Retell voice calls, Retell needs the SIP trunk details for that number.

Set these additional env vars:

```env
RETELL_TWILIO_TERMINATION_URI=backfill.pstn.twilio.com
RETELL_TWILIO_TRANSPORT=TLS
RETELL_TWILIO_AUTH_USERNAME=...
RETELL_TWILIO_AUTH_PASSWORD=...
RETELL_PHONE_NICKNAME=Backfill Primary
```

Then run:

```bash
python3 scripts/setup_retell_phone_number.py
```

That script will:

- look up `RETELL_FROM_NUMBER` in Retell
- import it if it does not exist yet
- otherwise update the existing Retell phone-number config
- bind the current inbound/outbound voice agents and inbound/outbound SMS chat agents using the current non-deprecated weighted agent arrays

## 7. Point Retell agent webhooks back to Backfill

`scripts/setup_retell_agents.py` already creates agents with:

```text
{BACKFILL_WEBHOOK_URL}/webhooks/retell
```

That endpoint handles:

- caller lookup
- consent logging
- vacancy creation
- claim / decline / standby flows
- manager-created open shifts
- onboarding-link handoff
- voice and chat agent tool calls

## 8. Smoke-test the live path

Run through these in order:

1. Call the public number and verify Retell answers with the inbound voice agent.
2. Create a vacancy and confirm the app starts the cascade.
3. Send an outbound offer and confirm Retell places a call from `RETELL_FROM_NUMBER`.
4. Send an outbound SMS and confirm Retell starts the text thread from `RETELL_FROM_NUMBER`.
5. Reply `YES`, `NO`, `CANCEL`, and `STOP` from a real handset.
6. Confirm Retell function calls hit `/webhooks/retell`.

## 9. Current repo boundaries

In unified mode, Retell is the conversation control plane for both voice and text. Twilio remains the underlying carrier and SIP trunk, but Backfill talks to Retell for agent-driven voice and SMS flows.
