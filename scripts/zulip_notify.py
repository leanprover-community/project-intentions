#!/usr/bin/env python3
"""Reflect the project board's claim lifecycle into a Zulip channel.

This reconciler reads the whole Projects v2 board, compares each issue's current Status against the
status we last announced (stored per item in a board Text field), and emits the difference to Zulip:

  * a fresh claim            -> a new announcement message (one Zulip topic per issue);
  * In Progress / In Review  -> a status emoji on that announcement (swapped as the status moves);
  * Completed                -> a :tada: on the announcement, plus a new message in the topic;
  * released (expired / disclaimed, i.e. an active claim back to Unclaimed) -> an :hourglass_done:
    on the announcement, plus a new message in the topic;
  * a re-claim after release  -> a new message in the same topic (the original announcement stays).

Because it diffs *observed* board state rather than reacting to a single event, it captures manual
board edits (e.g. a maintainer dragging a card to In Progress) that no issue/PR webhook would carry.
It never changes the board's own lifecycle fields; it only reads them and writes its private state
field, so it can't interfere with the `intentions` action that owns the board.

Idempotency: the announcement for an issue is, by definition, the bot's earliest message in that
issue's topic, so a crash between posting and recording state can't duplicate it — the next run finds
and reuses it. Follow-ups are de-duplicated against the most recent message in the topic. Combined
with the workflow's concurrency group (one run at a time), reruns are safe.

State is kept in a board Text field (default "Zulip State") holding JSON {"mid","topic","status"};
the field is created automatically if absent.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# --- configuration (from the environment) -----------------------------------------------------
GH_TOKEN = os.environ["GITHUB_TOKEN"]
OWNER, REPO = os.environ["GITHUB_REPOSITORY"].split("/", 1)
PROJECT_TITLE = os.environ.get("PROJECT_TITLE", "Project Intentions")

ZULIP_SITE = os.environ["ZULIP_SITE"].rstrip("/")
ZULIP_EMAIL = os.environ["ZULIP_BOT_EMAIL"]
ZULIP_KEY = os.environ["ZULIP_BOT_API_KEY"]
ZULIP_STREAM = os.environ["ZULIP_STREAM"]

# Dry run: log every post/reaction/state write that would happen, but make no changes. Used to
# preview the backfill for existing registrations before anything reaches the channel.
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

STATUS_FIELD = os.environ.get("STATUS_FIELD", "Status")
EXPIRY_FIELD = os.environ.get("EXPIRY_FIELD", "Claim Expires")
STATE_FIELD = os.environ.get("STATE_FIELD", "Zulip State")

# Status option names (must match the board / the intentions action config).
UNCLAIMED, CLAIMED = "Unclaimed", "Claimed"
IN_PROGRESS, IN_REVIEW, COMPLETED = "In Progress", "In Review", "Completed"
ACTIVE = {CLAIMED, IN_PROGRESS, IN_REVIEW}
KNOWN = {UNCLAIMED, CLAIMED, IN_PROGRESS, IN_REVIEW, COMPLETED}

# A status' emoji on the announcement. Claimed is the baseline (no emoji); the rest layer on top.
EMOJI = {IN_PROGRESS: "construction", IN_REVIEW: "eyes", COMPLETED: "tada", UNCLAIMED: "hourglass_done"}

TOPIC_MAX = 60       # Zulip's default maximum topic length
HTTP_TIMEOUT = 30    # seconds


def log(msg: str) -> None:
    print(msg, flush=True)


# --- HTTP helpers ------------------------------------------------------------------------------
def _request(req: urllib.request.Request) -> tuple[int, dict]:
    """Return (status, parsed-json). Raises on transport failure; returns body on HTTP errors so
    callers can inspect application-level error codes (e.g. benign Zulip reaction errors)."""
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body}
    except urllib.error.URLError as e:
        raise RuntimeError(f"transport error contacting {req.full_url}: {e}") from e


def gql(query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "project-intentions-zulip-notify",
        },
        method="POST",
    )
    status, data = _request(req)
    if status != 200 or "errors" in data:
        raise RuntimeError(f"GraphQL error ({status}): {json.dumps(data)[:800]}")
    return data["data"]


def zulip(method: str, path: str, params: dict) -> tuple[int, dict]:
    token = base64.b64encode(f"{ZULIP_EMAIL}:{ZULIP_KEY}".encode()).decode()
    data: bytes | None = urllib.parse.urlencode(params).encode("utf-8")
    url = f"{ZULIP_SITE}/api/v1/{path}"
    if method == "GET":
        url = f"{url}?{data.decode()}"
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("User-Agent", "project-intentions-zulip-notify")
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    return _request(req)


# --- Zulip actions -----------------------------------------------------------------------------
_DRY_MID = [9_000_000_000]  # fake, monotonically increasing message ids for dry-run bookkeeping


def topic_messages(topic: str) -> list[dict]:
    """The bot's own messages in this topic, oldest first. The earliest is the announcement."""
    narrow = [
        {"operator": "stream", "operand": ZULIP_STREAM},
        {"operator": "topic", "operand": topic},
        {"operator": "sender", "operand": ZULIP_EMAIL},
    ]
    status, data = zulip("GET", "messages", {
        "anchor": "newest", "num_before": 200, "num_after": 0,
        "narrow": json.dumps(narrow), "apply_markdown": "false",
    })
    if data.get("result") != "success":
        raise RuntimeError(f"reading topic '{topic}' failed: {data}")
    # The API returns ascending by id, but sort defensively.
    return sorted(({"id": m["id"], "content": m["content"]} for m in data.get("messages", [])),
                  key=lambda m: m["id"])


def _post(topic: str, content: str) -> int:
    if DRY_RUN:
        log(f"  [dry-run] would post to '{topic}':\n      " + content.replace("\n", "\n      "))
        _DRY_MID[0] += 1
        return _DRY_MID[0]
    _, data = zulip("POST", "messages", {
        "type": "stream", "to": ZULIP_STREAM, "topic": topic, "content": content,
    })
    if data.get("result") != "success":
        raise RuntimeError(f"post to '{topic}' failed: {data}")
    return data["id"]


def ensure_announcement(topic: str, content: str, existing: list[dict]) -> int:
    """Reuse the topic's earliest bot message as the announcement, or post it if there is none."""
    if existing:
        return existing[0]["id"]
    return _post(topic, content)


def post_followup(topic: str, content: str, existing: list[dict]) -> int:
    """Post a follow-up unless the most recent bot message in the topic is already identical (which
    means a previous run posted it and then failed before recording state)."""
    if existing and existing[-1]["content"].strip() == content.strip():
        return existing[-1]["id"]
    return _post(topic, content)


def add_reaction(mid: int | None, emoji_name: str | None) -> None:
    if not mid or not emoji_name:
        return
    if DRY_RUN:
        log(f"  [dry-run] would add :{emoji_name}: to {mid}")
        return
    _, data = zulip("POST", f"messages/{mid}/reactions", {"emoji_name": emoji_name})
    if data.get("result") == "success" or data.get("code") == "REACTION_ALREADY_EXISTS":
        return
    raise RuntimeError(f"add :{emoji_name}: to {mid} failed: {data}")


def remove_reaction(mid: int | None, emoji_name: str | None) -> None:
    if not mid or not emoji_name:
        return
    if DRY_RUN:
        log(f"  [dry-run] would remove :{emoji_name}: from {mid}")
        return
    _, data = zulip("DELETE", f"messages/{mid}/reactions", {"emoji_name": emoji_name})
    if data.get("result") == "success" or data.get("code") == "REACTION_DOES_NOT_EXIST":
        return
    raise RuntimeError(f"remove :{emoji_name}: from {mid} failed: {data}")


# --- GitHub project model ----------------------------------------------------------------------
def resolve_project_id() -> str:
    want = PROJECT_TITLE.strip()
    q_repo = """
      query($owner:String!,$repo:String!,$cursor:String){
        repository(owner:$owner,name:$repo){
          projectsV2(first:50,after:$cursor){ nodes{ id title } pageInfo{ hasNextPage endCursor } } } }"""
    q_owner = """
      query($owner:String!,$cursor:String){
        repositoryOwner(login:$owner){ ... on ProjectV2Owner {
          projectsV2(first:50,after:$cursor){ nodes{ id title } pageInfo{ hasNextPage endCursor } } } } }"""
    for query, base, pick in (
        (q_repo, {"owner": OWNER, "repo": REPO}, lambda d: d["repository"]["projectsV2"]),
        (q_owner, {"owner": OWNER}, lambda d: d["repositoryOwner"]["projectsV2"]),
    ):
        cursor = None
        while True:
            page = pick(gql(query, {**base, "cursor": cursor}))
            for n in page["nodes"]:
                if n["title"].strip() == want:
                    return n["id"]
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
    raise RuntimeError(f"No Projects v2 board titled {want!r} for {OWNER}/{REPO}.")


def load_fields(project_id: str) -> dict:
    """Return field ids and status option names; create the state field if it's missing."""
    nodes, cursor = [], None
    query = """
      query($id:ID!,$cursor:String){
        node(id:$id){ ... on ProjectV2 {
          fields(first:50,after:$cursor){
            nodes{
              __typename
              ... on ProjectV2FieldCommon { id name }
              ... on ProjectV2SingleSelectField { options { id name } }
            }
            pageInfo{ hasNextPage endCursor } } } } }"""
    while True:
        page = gql(query, {"id": project_id, "cursor": cursor})["node"]["fields"]
        nodes.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    status = next((n for n in nodes if n.get("name") == STATUS_FIELD and n["__typename"] == "ProjectV2SingleSelectField"), None)
    if not status:
        raise RuntimeError(f"No single-select field named {STATUS_FIELD!r} on the board.")
    names_by_id = {o["id"]: o["name"] for o in status.get("options", [])}

    expiry = next((n for n in nodes if n.get("name") == EXPIRY_FIELD), None)
    state = next((n for n in nodes if n.get("name") == STATE_FIELD), None)
    state_id = state["id"] if state else create_text_field(project_id, STATE_FIELD)

    return {
        "status_field_id": status["id"],
        "status_names_by_id": names_by_id,
        "expiry_field_id": expiry["id"] if expiry else None,
        "state_field_id": state_id,
    }


def create_text_field(project_id: str, name: str) -> str | None:
    if DRY_RUN:
        log(f"  [dry-run] would create board Text field {name!r}.")
        return None
    log(f"Creating board Text field {name!r} for notifier bookkeeping.")
    data = gql(
        """mutation($p:ID!,$n:String!){
          createProjectV2Field(input:{projectId:$p,dataType:TEXT,name:$n}){
            projectV2Field{ ... on ProjectV2FieldCommon { id } } } }""",
        {"p": project_id, "n": name},
    )
    return data["createProjectV2Field"]["projectV2Field"]["id"]


def list_items(project_id: str, fields: dict) -> list[dict]:
    """All issue items with the fields the reconciler needs. Items whose field values don't fit one
    page are skipped (fail closed) rather than acted on with a partial read."""
    out, cursor = [], None
    query = """
      query($id:ID!,$cursor:String){
        node(id:$id){ ... on ProjectV2 {
          items(first:100,after:$cursor){
            nodes{
              id
              content{
                __typename
                ... on Issue {
                  number title url body
                  labels(first:30){ nodes{ name } }
                  assignees(first:10){ nodes{ login } }
                }
              }
              fieldValues(first:100){
                nodes{
                  __typename
                  ... on ProjectV2ItemFieldSingleSelectValue { optionId field{ ... on ProjectV2FieldCommon { id } } }
                  ... on ProjectV2ItemFieldTextValue { text field{ ... on ProjectV2FieldCommon { id } } }
                }
                pageInfo{ hasNextPage }
              }
            }
            pageInfo{ hasNextPage endCursor } } } } }"""
    while True:
        page = gql(query, {"id": project_id, "cursor": cursor})["node"]["items"]
        for it in page["nodes"]:
            c = it.get("content") or {}
            if c.get("__typename") != "Issue":
                continue
            if it["fieldValues"]["pageInfo"]["hasNextPage"]:
                log(f"  ! #{c.get('number')}: more than 100 field values; skipping (partial read).")
                continue
            status_name, expiry_text, state_text = None, None, None
            for fv in it["fieldValues"]["nodes"]:
                fid = (fv.get("field") or {}).get("id")
                if fv["__typename"] == "ProjectV2ItemFieldSingleSelectValue" and fid == fields["status_field_id"]:
                    status_name = fields["status_names_by_id"].get(fv.get("optionId"))
                elif fv["__typename"] == "ProjectV2ItemFieldTextValue":
                    if fid == fields["expiry_field_id"]:
                        expiry_text = fv.get("text")
                    elif fid == fields["state_field_id"]:
                        state_text = fv.get("text")
            out.append({
                "item_id": it["id"],
                "number": c["number"],
                "title": c.get("title") or "",
                "url": c.get("url") or "",
                "body": c.get("body") or "",
                "labels": [l["name"] for l in c.get("labels", {}).get("nodes", [])],
                "assignees": [a["login"] for a in c.get("assignees", {}).get("nodes", [])],
                "status": status_name or UNCLAIMED,
                "expiry": expiry_text,
                "state": state_text,
            })
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return out


def save_state(project_id: str, state_field_id: str | None, item_id: str, state: dict) -> None:
    if DRY_RUN or not state_field_id:
        return
    gql(
        """mutation($p:ID!,$i:ID!,$f:ID!,$t:String!){
          updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,value:{text:$t}}){
            projectV2Item{ id } } }""",
        {"p": project_id, "i": item_id, "f": state_field_id, "t": json.dumps(state, separators=(",", ":"))},
    )


# --- message rendering -------------------------------------------------------------------------
def clean_title(title: str) -> str:
    return re.sub(r"^\s*\[intention\]\s*", "", title, flags=re.IGNORECASE).strip() or "(untitled)"


def topic_for(item: dict) -> str:
    return f"#{item['number']} {clean_title(item['title'])}"[:TOPIC_MAX].rstrip()


def link(item: dict) -> str:
    return f"[#{item['number']} {clean_title(item['title'])}]({item['url']})"


def form_section(body: str, heading: str) -> str | None:
    m = re.search(rf"(?:^|\n)###[ \t]+{re.escape(heading)}[ \t]*\r?\n([\s\S]*?)(?=\r?\n###[ \t]|$)", body)
    if not m:
        return None
    sec = m.group(1).strip()
    return None if not sec or sec == "_No response_" else sec


def format_expiry(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
        return dt.strftime("%b %-d, %Y")
    except ValueError:
        return None


def who(item: dict) -> str:
    return ", ".join(f"@{a}" for a in item["assignees"]) or "(unassigned)"


def announcement(item: dict) -> str:
    lines = [f":new: **New project intention** · {link(item)}", ""]
    desc = form_section(item["body"], "What are you working on?")
    if desc:
        lines += [desc if len(desc) <= 600 else desc[:600].rstrip() + "…", ""]
    meta = [f"Registered by **{who(item)}**"]
    exp = format_expiry(item["expiry"])
    if exp:
        meta.append(f"expires **{exp}**")
    lines.append(" · ".join(meta))
    areas = [l for l in item["labels"] if l.startswith("t-")]
    if areas:
        lines.append("Areas: " + ", ".join(f"`{a}`" for a in areas))
    return "\n".join(lines)


def completed_text(item: dict) -> str:
    return f":tada: **Completed** · {link(item)} — marked completed."


def released_text(item: dict) -> str:
    return (f":hourglass_done: **Released** · {link(item)} — the claim expired or was withdrawn, "
            "so the task is open again.")


def reclaimed_text(item: dict) -> str:
    exp = format_expiry(item["expiry"])
    tail = f" Expires **{exp}**." if exp else ""
    return f":wave: **Re-claimed** · {link(item)} by **{who(item)}** — active again.{tail}"


# --- reconcile ---------------------------------------------------------------------------------
def reconcile() -> None:
    project_id = resolve_project_id()
    fields = load_fields(project_id)
    items = list_items(project_id, fields)
    log(f"Reconciling {len(items)} board item(s) against Zulip{' (dry run)' if DRY_RUN else ''}.")

    for item in items:
        try:
            handle(project_id, fields["state_field_id"], item)
        except Exception as e:  # one bad item must not stop the rest
            log(f"  ! #{item['number']}: {e}")


def reflect_full_state(project_id: str, state_field_id: str | None, item: dict, cur: str) -> None:
    """Bring a not-yet-tracked item up to its current status from scratch: announce it, set the
    status emoji, and post the completion follow-up if it is already Completed. Idempotent."""
    topic = topic_for(item)
    existing = topic_messages(topic)
    mid = ensure_announcement(topic, announcement(item), existing)
    add_reaction(mid, EMOJI.get(cur))
    if cur == COMPLETED:
        existing = topic_messages(topic)
        post_followup(topic, completed_text(item), existing)
        log(f"  ✓ #{item['number']}: announced + completed (first seen as Completed).")
    else:
        log(f"  + #{item['number']}: announced (first seen as {cur}).")
    save_state(project_id, state_field_id, item["item_id"], {"mid": mid, "topic": topic, "status": cur})


def handle(project_id: str, state_field_id: str | None, item: dict) -> None:
    cur = item["status"]
    if cur not in KNOWN:
        log(f"  ? #{item['number']}: unrecognised status {cur!r}; leaving alone.")
        return

    state = None
    if item["state"]:
        try:
            state = json.loads(item["state"])
        except json.JSONDecodeError:
            state = None

    # First time we see this item (also the backfill for existing registrations).
    if state is None:
        if cur in ACTIVE or cur == COMPLETED:
            reflect_full_state(project_id, state_field_id, item, cur)
        else:  # Unclaimed and never tracked: nothing to say, just record the baseline
            save_state(project_id, state_field_id, item["item_id"], {"mid": None, "topic": None, "status": cur})
        return

    prev = state.get("status")
    if prev == cur:
        return

    mid, topic = state.get("mid"), state.get("topic") or topic_for(item)

    # No announcement was ever posted (item was first seen Unclaimed). A move into an active/terminal
    # status starts a fresh claim cycle; a move between non-active statuses just updates the baseline.
    if not mid:
        if cur in ACTIVE or cur == COMPLETED:
            reflect_full_state(project_id, state_field_id, item, cur)
        else:
            save_state(project_id, state_field_id, item["item_id"], {"mid": None, "topic": topic, "status": cur})
        return

    # Swap the announcement's status emoji to match the new status.
    remove_reaction(mid, EMOJI.get(prev))
    add_reaction(mid, EMOJI.get(cur))

    if cur == COMPLETED:
        post_followup(topic, completed_text(item), topic_messages(topic))
        log(f"  ✓ #{item['number']}: {prev} -> Completed.")
    elif cur == UNCLAIMED and prev in ACTIVE:
        post_followup(topic, released_text(item), topic_messages(topic))
        log(f"  ⌛ #{item['number']}: {prev} -> released.")
    elif cur == CLAIMED and prev == UNCLAIMED:
        post_followup(topic, reclaimed_text(item), topic_messages(topic))
        log(f"  + #{item['number']}: re-claimed.")
    else:
        # In Progress / In Review / regression to Claimed, or Completed -> Unclaimed (reopened):
        # the emoji swap above is the whole change.
        log(f"  ~ #{item['number']}: {prev} -> {cur}.")

    save_state(project_id, state_field_id, item["item_id"], {"mid": mid, "topic": topic, "status": cur})


if __name__ == "__main__":
    try:
        reconcile()
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
