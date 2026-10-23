"""List your Cal.com event types and their IDs.
"""

import json
import os
import sys
import urllib.request


def list_event_types():
    api_key = os.environ.get("CAL_API_KEY")
    if not api_key:
        print("Error: CAL_API_KEY environment variable is required")
        sys.exit(1)

    req = urllib.request.Request(
        "https://api.cal.com/v2/event-types",
        headers={
            "Authorization": f"Bearer {api_key}",
            "cal-api-version": "2024-06-14",
            "User-Agent": "app-setter/1.0",  # Cal.com blocks the default urllib agent
        },
    )
    with urllib.request.urlopen(req) as resp:
        event_types = json.loads(resp.read()).get("data", [])

    print(f"{'ID':<10} {'Minutes':<8} {'Slug':<20} Title")
    for et in event_types:
        print(f"{et['id']:<10} {et.get('lengthInMinutes', ''):<8} {et.get('slug', ''):<20} {et.get('title', '')}")


if __name__ == "__main__":
    list_event_types()
