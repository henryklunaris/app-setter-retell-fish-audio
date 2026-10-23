---
name: update-retell-agent
description: Verify the live server and point the Retell agent's tools at it (URL, bearer token, departments), then publish. Use after a deploy, a new bearer token, a Render URL change or a department change.
disable-model-invocation: true
argument-hint: "[--check] [--no-publish]"
---

# Update Retell agent tools

Never read .env. Load it in the shell with `set -a && source .env && set +a`. It must contain RENDER_BASE_URL and AGENT_ID (if not, run /setup first).
The prompt, voice and greeting are edited in the Retell dashboard, not here.

1. If backend/ or requirements.txt changed, ask the user to push (Render auto-deploys) and tell you when it's live. Do not commit or push yourself.
2. Check the deploy is up: `set -a && source .env && set +a && curl -s $RENDER_BASE_URL/health` should return `{"status":"ok"}`. Free plan cold starts can take ~50s.
3. Verify the live endpoints (never print the token):
   ```
   set -a && source .env && set +a && curl -s -X POST $RENDER_BASE_URL/check_slots -H "Authorization: Bearer $API_BEARER_TOKEN" -H "Content-Type: application/json" -d '{"args":{"requested_time":"<tomorrow>T10:00"}}'
   ```
   Expect a slots message, not 401 or 500. Also check a request with no token returns 401.
4. Show what would change: `set -a && source .env && set +a && python3 setup/update_tools.py --check`
5. If there are changes and the user is happy, update and publish (`$ARGUMENTS` may contain `--no-publish`):
   ```
   set -a && source .env && set +a && python3 setup/update_tools.py $ARGUMENTS
   ```
6. Report the published version and what changed. Phone numbers set to "latest published" pick it up straight away.

Notes
- The script edits the agent's latest version. If that's an unpublished draft the user is still working on, publishing it also publishes their other draft changes, so check with them first.
- Retell returns tool headers (including the bearer token) when fetching an LLM. Never print raw get-retell-llm output.
- Do not call update-retell-llm without `?version=`, it edits version 0, not the draft.
- Never call /book_slot without the user's OK, it makes a real booking.
