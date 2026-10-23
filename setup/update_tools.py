"""Point the Retell agent's check_slots and book_slot tools at your server, then publish.

Only the tools' URL, auth header and department list are changed. The prompt, voice and
everything else stay as they are in Retell.

Usage:
    python3 setup/update_tools.py [--check] [--no-publish]

Needs RETELL_API_KEY, API_BEARER_TOKEN, RENDER_BASE_URL, AGENT_ID and EVENT_TYPES in the environment.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

RETELL_API_BASE = "https://api.retellai.com"
SERVER_TOOLS = ("check_slots", "book_slot")


def api_request(method: str, path: str, api_key: str, payload: dict | None = None) -> dict:
    """Call the Retell API and return the parsed JSON response."""
    req = urllib.request.Request(
        f"{RETELL_API_BASE}/{path}",
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print(f"Retell API error {e.code}: {e.read().decode()}")
        sys.exit(1)


def get_departments() -> list[str]:
    """Department names from EVENT_TYPES, matching the server's config."""
    return [k.lower() for k in json.loads(os.environ["EVENT_TYPES"].strip().strip("'\""))]


def build_tools(tools: list[dict], base_url: str, bearer_token: str, departments: list[str]) -> list[dict]:
    """Return a copy of the tools with the server URL, auth header and departments filled in."""
    tools = json.loads(json.dumps(tools))  # deep copy
    found = set()
    for tool in tools:
        if tool.get("type") != "custom" or tool.get("name") not in SERVER_TOOLS:
            continue
        found.add(tool["name"])
        tool["url"] = f"{base_url.rstrip('/')}/{tool['name']}"
        tool["headers"] = {**(tool.get("headers") or {}), "Authorization": f"Bearer {bearer_token}"}

        params = tool.setdefault("parameters", {"type": "object", "properties": {}})
        props = params.setdefault("properties", {})
        required = [r for r in params.get("required", []) if r != "department"]
        # Only ask for a department when there's a choice, the server defaults to the first
        if len(departments) > 1:
            props["department"] = {
                "type": "string",
                "enum": departments,
                "description": props.get("department", {}).get("description", "The department the caller needs"),
            }
            required.append("department")
        else:
            props.pop("department", None)
        params["required"] = required

    missing = set(SERVER_TOOLS) - found
    if missing:
        print(f"Error: the agent has no custom tool named {', '.join(sorted(missing))}. Import the Retell template first.")
        sys.exit(1)
    return tools


def describe_changes(old: list[dict], new: list[dict]) -> list[str]:
    """List what differs per tool, without printing header values."""
    old_by_name = {t.get("name"): t for t in old}
    changes = []
    for tool in new:
        before = old_by_name.get(tool.get("name"), {})
        if tool == before:
            continue
        name = tool["name"]
        if tool.get("url") != before.get("url"):
            changes.append(f"{name}: url {before.get('url')} -> {tool.get('url')}")
        if tool.get("headers") != before.get("headers"):
            changes.append(f"{name}: Authorization header (value hidden)")
        old_props = before.get("parameters", {}).get("properties", {})
        new_props = tool.get("parameters", {}).get("properties", {})
        if old_props.get("department") != new_props.get("department"):
            new_dept = new_props.get("department", {}).get("enum") if "department" in new_props else "removed"
            changes.append(f"{name}: department {old_props.get('department', {}).get('enum')} -> {new_dept}")
        if before.get("parameters", {}).get("required") != tool.get("parameters", {}).get("required"):
            changes.append(f"{name}: required {before.get('parameters', {}).get('required')} -> {tool['parameters']['required']}")
    return changes


def get_llm(agent: dict, api_key: str) -> dict:
    engine = agent["response_engine"]
    return api_request("GET", f"get-retell-llm/{engine['llm_id']}?version={engine['version']}", api_key)


def update_tools(check: bool = False, publish: bool = True):
    names = ("RETELL_API_KEY", "API_BEARER_TOKEN", "RENDER_BASE_URL", "AGENT_ID", "EVENT_TYPES")
    env = {k: os.environ.get(k) for k in names}
    for var, value in env.items():
        if not value:
            print(f"Error: {var} environment variable is required")
            sys.exit(1)
    api_key, agent_id = env["RETELL_API_KEY"], env["AGENT_ID"]

    agent = api_request("GET", f"get-agent/{agent_id}", api_key)
    llm = get_llm(agent, api_key)
    current = llm.get("general_tools") or []
    tools = build_tools(current, env["RENDER_BASE_URL"], env["API_BEARER_TOKEN"], get_departments())

    changes = describe_changes(current, tools)
    print(f"Agent '{agent.get('agent_name')}' v{agent['version']} (published: {agent.get('is_published')})")
    if not changes:
        print("Tools are already up to date.")
        return
    print("Changes:\n  " + "\n  ".join(changes))
    if check:
        return

    # Edit a draft, published versions can't be changed
    if agent.get("is_published"):
        print("Creating a new draft...")
        api_request("POST", f"create-agent-version/{agent_id}", api_key, {"base_version": agent["version"]})
        agent = api_request("GET", f"get-agent/{agent_id}", api_key)

    engine = agent["response_engine"]
    print(f"Updating tools on agent draft v{agent['version']}...")
    api_request(
        "PATCH",
        f"update-retell-llm/{engine['llm_id']}?version={engine['version']}",
        api_key,
        {"general_tools": tools},
    )

    if publish:
        api_request("POST", f"publish-agent-version/{agent_id}", api_key, {"version": agent["version"]})
        print(f"Published v{agent['version']}.")
    else:
        print("Updated draft (not published).")


if __name__ == "__main__":
    update_tools(check="--check" in sys.argv, publish="--no-publish" not in sys.argv)
