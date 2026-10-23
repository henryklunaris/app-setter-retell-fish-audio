---
name: add-department
description: Add a new department (Cal.com event type) to the EVENT_TYPES mapping and update the Retell agent. Use when the user wants to add, rename or remove a department.
disable-model-invocation: true
argument-hint: "<department-name>"
---

# Add department: $ARGUMENTS

Never read .env directly. The user edits .env and Render env vars by hand.

1. List event types: `set -a && source .env && set +a && python3 setup/list_event_types.py`. Find the event type for "$ARGUMENTS" (ask the user which one if unclear).
2. Get the current mapping without exposing secrets: `zsh -c 'set -a; source .env; set +a; echo $EVENT_TYPES'`.
3. Check the event type is in Cal.com "Phone" confirmation mode (email not required, phone required):
   ```
   set -a && source .env && set +a && curl -s https://api.cal.com/v2/event-types/<id> -H "Authorization: Bearer $CAL_API_KEY" -H "cal-api-version: 2024-06-14"
   ```
   Look at `bookingFields` for `email` and `attendeePhoneNumber`. If email is required, ask the user to switch Confirmation to Phone in Cal.com and save.
4. Give the user the new EVENT_TYPES value, merged with the existing departments:
   - .env (single quotes): `EVENT_TYPES='{"sales": 123456, "<dept>": <id>}'`
   - Render env var (no quotes): `{"sales": 123456, "<dept>": <id>}`
   The first key is the default department.
5. Once the user confirms Render has redeployed, run /update-retell-agent. The tool enum is built from EVENT_TYPES, so no code change is needed.
