---
name: setup
description: Guided first-time setup of the appointment setter (Cal.com, Render server, Retell voice agent). Use when someone has just cloned the repo and wants to get it running.
disable-model-invocation: true
---

# First-time setup

Walk the user through one step at a time. Wait for them to finish each step before moving on.
Never read .env or print secrets. Load it in the shell with `set -a && source .env && set +a`.
Do not commit, push or deploy for the user.

## 1. Create .env
Ask the user to copy `.env.example` to `.env` (e.g. `cp .env.example .env`). They fill in values as you go.

## 2. Cal.com
1. Ask them to create an API key in Cal.com (Settings > Developer > API Keys) and add it as `CAL_API_KEY`.
2. List their event types: `set -a && source .env && set +a && python3 setup/list_event_types.py`
3. Ask which event types to use and what department name each one is (e.g. sales, delivery).
4. Each chosen event type must be in Phone confirmation mode: Event type > Booking form > Confirmation > Phone, then Save. Verify for each ID:
   ```
   set -a && source .env && set +a && curl -s https://api.cal.com/v2/event-types/<id> -H "Authorization: Bearer $CAL_API_KEY" -H "cal-api-version: 2024-06-14"
   ```
   In `bookingFields`, `email` must have required false and `attendeePhoneNumber` required true.
5. Have them set in .env (single quotes needed):
   - `EVENT_TYPES='{"sales": <id>, "delivery": <id>}'` (first one is the default)
   - `TIMEZONE=<IANA zone>` matching their Cal.com availability, e.g. `Australia/Melbourne`

## 3. Bearer token
Ask them to run `! openssl rand -hex 32` and save the output as `API_BEARER_TOKEN` in .env.

## 4. Deploy to Render
1. They push the repo to their own GitHub.
2. In Render: New > Web Service, pick the repo, then:
   - Language: Python 3
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
   - Instance Type: Free works, but sleeps after 15 min idle (first call can take ~50s). Starter avoids that.
   - Health Check Path (Advanced): `/health`
   - Environment Variables: `CAL_API_KEY`, `API_BEARER_TOKEN`, `EVENT_TYPES` (no quotes in Render), `TIMEZONE`, `PYTHON_VERSION=3.12.7`, optional `FALLBACK_PHONE`
3. Once live, have them add `RENDER_BASE_URL=https://<their-app>.onrender.com` to .env.
4. Verify:
   ```
   set -a && source .env && set +a && curl -s $RENDER_BASE_URL/health
   set -a && source .env && set +a && curl -s -o /dev/null -w '%{http_code}' -X POST $RENDER_BASE_URL/check_slots -H 'Content-Type: application/json' -d '{}'
   set -a && source .env && set +a && curl -s -X POST $RENDER_BASE_URL/check_slots -H "Authorization: Bearer $API_BEARER_TOKEN" -H 'Content-Type: application/json' -d '{"args":{"requested_time":"<tomorrow>T10:00"}}'
   ```
   Expect `{"status":"ok"}`, then `401`, then a slots message. If the deploy crashes, check the Render logs (a common cause is EVENT_TYPES missing or not valid JSON).

## 5. Retell agent
1. Ask them to add their Retell API key as `RETELL_API_KEY`.
2. Have them import the Retell agent template they were given in the Retell dashboard, then adjust the prompt, greeting and voice there as they like.
3. Ask for the agent ID (on the agent's page in Retell, starts with `agent_`) and have them add it as `AGENT_ID` in .env.
4. Point the tools at their server: `set -a && source .env && set +a && python3 setup/update_tools.py --check`, then without `--check` once they're happy. This sets the URL, bearer token and department list, and publishes.
5. In the Retell dashboard, under Phone Numbers buy or import a number and set its inbound agent to this agent with version "latest published", so future updates go live.

## 6. Test
Ask them to call the number and book a slot. The booking should show in Cal.com with their phone number. If a booking fails, ask for the `[book_slot] Cal.com response:` line from the Render logs.

From now on, use /update-retell-agent after changes and /add-department to add departments.
