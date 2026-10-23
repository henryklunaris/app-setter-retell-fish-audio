# App Setter

FastAPI backend plus a Retell voice agent that checks and books Cal.com slots.

## Layout

- backend/app.py: FastAPI app (GET /health, POST /check_slots, POST /book_slot)
- setup/update_tools.py: point the Retell agent's tools at the server (URL, bearer token, departments), then publish (`--check` to preview, `--no-publish` to skip)
- setup/list_event_types.py: list Cal.com event type IDs

The agent itself (prompt, voice, greeting) is imported from a Retell template and edited in the Retell dashboard.

## Env vars

Live in .env (never read it). Load with: `set -a && source .env && set +a`. See .env.example for the full list.

## API behaviour

- All endpoints except /health need `Authorization: Bearer $API_BEARER_TOKEN`.
- Body is either Retell wrapped `{name, call, args}` or plain args.
- Args: `requested_time` (ISO, local time), `department`, plus `name` and `reason` for book_slot (reason goes in the Cal.com title and notes).
- book_slot uses `call.from_number` as the attendee phone (fallback FALLBACK_PHONE env var). No email.

## Skills

- /setup: guided first-time setup (Cal.com, Render, Retell)
- /update-retell-agent: verify the live deploy, then update the agent's tools and publish
- /add-department: add a department to EVENT_TYPES
