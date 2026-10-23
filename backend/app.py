import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

CAL_BASE_URL = "https://api.cal.com/v2"
if not os.environ.get("EVENT_TYPES"):
    raise RuntimeError('EVENT_TYPES env var is required, e.g. {"sales": 123456, "delivery": 654321}')

# Department name -> Cal.com event type ID, first one is the default
EVENT_TYPES = {
    k.lower(): int(v)
    # Strip stray quotes in case the .env style value is pasted into Render
    for k, v in json.loads(os.environ["EVENT_TYPES"].strip().strip("'\"")).items()
}
DEFAULT_DEPARTMENT = next(iter(EVENT_TYPES))
TIMEZONE = os.environ.get("TIMEZONE", "UTC")
# Used when the caller's number isn't available, e.g. Retell web test calls
FALLBACK_PHONE = os.environ.get("FALLBACK_PHONE", "")
# How many days after the requested day to search when it's full
LOOKAHEAD_DAYS = 3

app = FastAPI(title="appointment-setter")
bearer = HTTPBearer(auto_error=False)


def require_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer)):
    """Reject requests without the correct Authorization: Bearer token."""
    expected = os.environ["API_BEARER_TOKEN"]
    if creds is None or not secrets.compare_digest(creds.credentials, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def cal_headers(version: str) -> dict:
    return {
        "Authorization": f"Bearer {os.environ['CAL_API_KEY']}",
        "cal-api-version": version,
    }


def unwrap(data: dict) -> tuple[dict, dict]:
    """Split a Retell request into (args, call); also accepts plain args."""
    if "args" in data:
        return data.get("args") or {}, data.get("call") or {}
    return data, {}


def resolve_event_type(args: dict) -> int | None:
    """Look up the event type ID for the requested department."""
    department = (args.get("department") or DEFAULT_DEPARTMENT).strip().lower()
    return EVENT_TYPES.get(department)


def unknown_department() -> dict:
    return {"result": f"Unknown department. Please choose one of: {', '.join(EVENT_TYPES)}"}


def parse_local(requested_time: str) -> datetime:
    """Parse an ISO string, assuming the local timezone if none is given."""
    dt = datetime.fromisoformat(requested_time)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
    return dt


def format_date_with_ordinal(date_str: str) -> str:
    """Convert '2025-12-20' to 'Saturday the 20th of December'."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day = dt.day
    if 11 <= day <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{dt.strftime('%A')} the {day}{suffix} of {dt.strftime('%B')}"


def format_slot_times(slots: list, tz: str) -> list[str]:
    """Convert slot times to HH:MM in the target timezone."""
    local_tz = ZoneInfo(tz)
    times = []
    for slot in slots:
        if isinstance(slot, dict):
            time_str = slot.get("start") or slot.get("time", "")
        else:
            time_str = slot
        if time_str:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            times.append(dt.astimezone(local_tz).strftime("%H:%M"))
    return times


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/check_slots", dependencies=[Depends(require_token)])
def check_slots(data: dict):
    args, _ = unwrap(data)
    logger.info(f"[check_slots] INPUT: {args}")

    event_type_id = resolve_event_type(args)
    if event_type_id is None:
        return unknown_department()

    dt = parse_local(args.get("requested_time", ""))
    requested_date = dt.strftime("%Y-%m-%d")
    requested_time = dt.strftime("%H:%M")

    # Midnight on the requested day through the end of the lookahead days
    day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = day_start.astimezone(ZoneInfo("UTC"))
    end_utc = (day_start + timedelta(days=LOOKAHEAD_DAYS + 1)).astimezone(ZoneInfo("UTC"))

    logger.info(f"[check_slots] requested_date={requested_date} start_utc={start_utc.isoformat()} end_utc={end_utc.isoformat()}")

    with httpx.Client(timeout=15) as client:
        resp = client.get(
            f"{CAL_BASE_URL}/slots",
            params={
                "start": start_utc.isoformat(),
                "end": end_utc.isoformat(),
                "eventTypeId": event_type_id,
                "timeZone": TIMEZONE,
            },
            headers=cal_headers("2024-09-04"),
        )

    if resp.status_code != 200:
        logger.error(f"[check_slots] Cal.com error: status={resp.status_code} body={resp.text[:500]}")
        return {"result": "We had an error checking availabilities, try again later"}

    slots_data = resp.json().get("data", {})
    logger.info(f"[check_slots] Cal.com dates={list(slots_data.keys())}")

    requested_label = format_date_with_ordinal(requested_date)
    read_three = (
        f"Read out only the THREE (3) slots that best match the caller's requested time of {requested_time}."
    )

    # Requested day first, then each following day until one has slots
    for offset in range(LOOKAHEAD_DAYS + 1):
        day = (day_start + timedelta(days=offset)).strftime("%Y-%m-%d")
        if not slots_data.get(day):
            continue
        times = ", ".join(format_slot_times(slots_data[day], TIMEZONE))
        if offset == 0:
            result = {"result": f"{read_three} These are all the available slots for {requested_label}: {times}"}
            logger.info(f"[check_slots] OUTPUT (match): {result}")
        else:
            result = {
                "result": (
                    f"We couldn't find any slots for {requested_label}, "
                    f"here are the slots for {format_date_with_ordinal(day)} instead: {times}. {read_three}"
                )
            }
            logger.info(f"[check_slots] OUTPUT (fallback): {result}")
        return result

    result = {
        "result": (
            f"We couldn't find anything for {requested_label} or the next {LOOKAHEAD_DAYS} days. "
            f"Ask the caller to try another day."
        )
    }
    logger.info(f"[check_slots] OUTPUT (empty): {result}")
    return result


@app.post("/book_slot", dependencies=[Depends(require_token)])
def book_slot(data: dict):
    args, call = unwrap(data)
    logger.info(f"[book_slot] INPUT: {args} call_type={call.get('call_type')}")

    event_type_id = resolve_event_type(args)
    if event_type_id is None:
        return unknown_department()

    name = args.get("name", "")
    reason = (args.get("reason") or "").strip()
    # Caller's number on phone calls, fallback for web calls
    phone_number = args.get("phone_number") or call.get("from_number") or FALLBACK_PHONE
    if not phone_number:
        return {"result": "We couldn't get a phone number for this booking, please call from a phone to book"}

    dt = parse_local(args.get("requested_time", ""))
    start_utc = dt.astimezone(ZoneInfo("UTC"))

    payload = {
        "start": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "eventTypeId": event_type_id,
        "attendee": {
            "name": name,
            "phoneNumber": phone_number,
            "timeZone": TIMEZONE,
        },
        "bookingFieldsResponses": {
            "title": f"Phone Booking: {reason}" if reason else "Phone Booking",
            "attendeePhoneNumber": phone_number,
        },
    }
    # Notes show up as "Additional notes" in the calendar event description
    if reason:
        payload["bookingFieldsResponses"]["notes"] = reason

    logger.info(f"[book_slot] Cal.com payload: {payload}")

    with httpx.Client(timeout=15) as client:
        resp = client.post(
            f"{CAL_BASE_URL}/bookings",
            json=payload,
            headers=cal_headers("2026-02-25"),
        )

    logger.info(f"[book_slot] Cal.com response: status={resp.status_code} body={resp.text[:500]}")

    if resp.status_code == 201:
        result = {"result": "Worked, booked"}
        logger.info(f"[book_slot] OUTPUT: {result}")
        return result

    error_text = resp.text.lower()

    if "already has booking" in error_text or "not available" in error_text:
        result = {
            "result": f"The current slot is taken at {dt.strftime('%H:%M')}, please try a different one"
        }
        logger.info(f"[book_slot] OUTPUT (slot taken): {result}")
        return result

    if "in the past" in error_text:
        today = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
        result = {
            "result": (
                f"The slot we're trying to book is in the past, today is {today}, "
                f"make sure to pick a time after this please"
            )
        }
        logger.info(f"[book_slot] OUTPUT (past): {result}")
        return result

    result = {"result": "We had an error making the booking, try again later"}
    logger.info(f"[book_slot] OUTPUT (error): {result}")
    return result
