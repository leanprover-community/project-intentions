#!/usr/bin/env python3
"""Reflect the project board's claim lifecycle into a Zulip channel.

This reconciler reads the whole Projects v2 board and, for each issue, compares its current Status to
the status the channel already shows, then emits the difference to Zulip:

  * a fresh claim            -> a new announcement message (one Zulip topic per issue);
  * In Progress / In Review  -> a status emoji on that announcement (swapped as the status moves);
  * Completed                -> a :tada: on the announcement, plus a new message in the topic;
  * released (an active claim back to Unclaimed: expired or disclaimed) -> an :hourglass_done: on the
    announcement, plus a new message in the topic;
  * a re-claim after release  -> a new message in the same topic (the original announcement stays).

The "status the channel already shows" is read back from Zulip itself: the announcement for an issue
is the bot's message in the channel that links to that issue, and the bot's own reaction on it
encodes the last status it reflected (none = Claimed, :construction: = In Progress, :eyes: = In
Review, :tada: = Completed, :hourglass_done: = released). So there is no bookkeeping stored on the
board — the board carries only the lifecycle fields the `intentions` action owns, untouched here.

Because the reaction *is* the state, every run reconciles toward the board and self-heals: a crash
part-way through a transition is corrected on the next run (messages are posted before the reaction
marker is set, and de-duplicated against the topic, so nothing doubles up). Diffing observed board
state also means manual board moves no webhook would carry are picked up.
"""

from __future__ import annotations

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

# Dry run: log every post/reaction that would happen, but make no changes. Used to preview the
# backfill for existing registrations before anything reaches the channel.
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

STATUS_FIELD = os.environ.get("STATUS_FIELD", "Status")
EXPIRY_FIELD = os.environ.get("EXPIRY_FIELD", "Claim Expires")
# A pre-1.0 version stored state in this board field; it's no longer used and is deleted on sight.
LEGACY_STATE_FIELD = os.environ.get("STATE_FIELD", "Zulip State")

# Status option names (must match the board / the intentions action config).
UNCLAIMED, CLAIMED = "Unclaimed", "Claimed"
IN_PROGRESS, IN_REVIEW, COMPLETED = "In Progress", "In Review", "Completed"
ACTIVE = {CLAIMED, IN_PROGRESS, IN_REVIEW}
KNOWN = {UNCLAIMED, CLAIMED, IN_PROGRESS, IN_REVIEW, COMPLETED}

# A status' marker reaction on the announcement. Claimed is the baseline (no marker); the others
# layer on top. This map is also read backwards (emoji -> status) to recover the last shown status.
EMOJI = {IN_PROGRESS: "construction", IN_REVIEW: "eyes", COMPLETED: "tada", UNCLAIMED: "hourglass_done"}
STATUS_BY_EMOJI = {v: k for k, v in EMOJI.items()}

ISSUE_LINK = re.compile(rf"/{re.escape(OWNER)}/{re.escape(REPO)}/issues/(\d+)\)")
ANNOUNCE_MARK = "New project intention"  # identifies the announcement among the bot's messages

TOPIC_MAX = 60       # Zulip's default maximum topic length
DESC_MAX = 5000      # max chars of the issue description quoted into an announcement
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
    import base64
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


_BOT_ID: list[int | None] = [None]


def bot_id() -> int:
    if _BOT_ID[0] is None:
        _, data = zulip("GET", "users/me", {})
        if data.get("result") != "success":
            raise RuntimeError(f"users/me failed: {data}")
        _BOT_ID[0] = data["user_id"]
    return _BOT_ID[0]


# --- Zulip read: the announcement index ---------------------------------------------------------
class Channel:
    """A snapshot of the bot's own messages in the channel, indexed for this run.

    announcements[issue_number] = {"mid", "topic", "reactions"}  (earliest announcement per issue)
    last_in_topic[topic]        = content of the most recent bot message in that topic
    """

    def __init__(self, announcements: dict[int, dict], last_in_topic: dict[str, str]):
        self.announcements = announcements
        self.last_in_topic = last_in_topic


def fetch_channel() -> Channel:
    narrow = json.dumps([
        {"operator": "channel", "operand": ZULIP_STREAM},
        {"operator": "sender", "operand": ZULIP_EMAIL},
    ])
    by_id: dict[int, dict] = {}
    anchor: str | int = "newest"
    while True:
        status, data = zulip("GET", "messages", {
            "anchor": anchor, "num_before": 1000, "num_after": 0,
            "narrow": narrow, "apply_markdown": "false",
        })
        if data.get("result") != "success":
            raise RuntimeError(f"reading the channel failed: {data}")
        msgs = data.get("messages", [])
        added = False
        for m in msgs:
            if m["id"] not in by_id:
                by_id[m["id"]] = m
                added = True
        # Page from the oldest id seen (include_anchor re-returns it, deduped above) rather than
        # oldest-1, so a message exactly on the boundary is never skipped. Stop on a short or
        # fully-seen page.
        if len(msgs) < 1000 or not added:
            break
        anchor = min(m["id"] for m in msgs)

    bid = bot_id()
    announcements: dict[int, dict] = {}
    last_in_topic: dict[str, str] = {}
    for m in sorted(by_id.values(), key=lambda x: x["id"]):
        topic = m["subject"]
        last_in_topic[topic] = m["content"]  # ascending id, so this ends on the newest
        if ANNOUNCE_MARK not in m["content"]:
            continue
        hit = ISSUE_LINK.search(m["content"])
        if not hit:
            continue
        num = int(hit.group(1))
        if num not in announcements:  # earliest announcement wins
            announcements[num] = {
                "mid": m["id"],
                "topic": topic,
                "reactions": {r["emoji_name"] for r in m.get("reactions", []) if r.get("user_id") == bid},
            }
    return Channel(announcements, last_in_topic)


# --- Zulip write -------------------------------------------------------------------------------
_DRY_MID = [9_000_000_000]


def post(topic: str, content: str, channel: Channel) -> int:
    """Post unless an identical message is already the latest in the topic (idempotent on reruns)."""
    if channel.last_in_topic.get(topic, "").strip() == content.strip():
        log(f"  = '{topic}': identical message already present; not reposting.")
        return 0
    if DRY_RUN:
        log(f"  [dry-run] would post to '{topic}':\n      " + content.replace("\n", "\n      "))
        _DRY_MID[0] += 1
        return _DRY_MID[0]
    _, data = zulip("POST", "messages", {
        "type": "stream", "to": ZULIP_STREAM, "topic": topic, "content": content,
    })
    if data.get("result") != "success":
        raise RuntimeError(f"post to '{topic}' failed: {data}")
    channel.last_in_topic[topic] = content
    return data["id"]


def add_reaction(mid: int, emoji_name: str | None) -> None:
    if not mid or not emoji_name:
        return
    if DRY_RUN:
        log(f"  [dry-run] would add :{emoji_name}: to {mid}")
        return
    _, data = zulip("POST", f"messages/{mid}/reactions", {"emoji_name": emoji_name})
    if data.get("result") == "success" or data.get("code") == "REACTION_ALREADY_EXISTS":
        return
    raise RuntimeError(f"add :{emoji_name}: to {mid} failed: {data}")


def remove_reaction(mid: int, emoji_name: str | None) -> None:
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
    """Resolve the Status single-select and the optional expiry field, and delete the legacy state
    field if it is still on the board (this reconciler no longer keeps any state there)."""
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

    legacy = next((n for n in nodes if n.get("name") == LEGACY_STATE_FIELD), None)
    if legacy:
        delete_field(project_id, legacy["id"], LEGACY_STATE_FIELD)

    expiry = next((n for n in nodes if n.get("name") == EXPIRY_FIELD), None)
    return {
        "status_field_id": status["id"],
        "status_names_by_id": {o["id"]: o["name"] for o in status.get("options", [])},
        "expiry_field_id": expiry["id"] if expiry else None,
    }


def delete_field(project_id: str, field_id: str, name: str) -> None:
    if DRY_RUN:
        log(f"  [dry-run] would delete legacy board field {name!r}.")
        return
    log(f"Deleting unused board field {name!r}.")
    gql("""mutation($f:ID!){ deleteProjectV2Field(input:{fieldId:$f}){ clientMutationId } }""", {"f": field_id})


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
            status_name, expiry_text = None, None
            for fv in it["fieldValues"]["nodes"]:
                fid = (fv.get("field") or {}).get("id")
                if fv["__typename"] == "ProjectV2ItemFieldSingleSelectValue" and fid == fields["status_field_id"]:
                    status_name = fields["status_names_by_id"].get(fv.get("optionId"))
                elif fv["__typename"] == "ProjectV2ItemFieldTextValue" and fid == fields["expiry_field_id"]:
                    expiry_text = fv.get("text")
            out.append({
                "number": c["number"],
                "title": c.get("title") or "",
                "url": c.get("url") or "",
                "body": c.get("body") or "",
                "labels": [l["name"] for l in c.get("labels", {}).get("nodes", [])],
                "assignees": [a["login"] for a in c.get("assignees", {}).get("nodes", [])],
                "status": status_name or UNCLAIMED,
                "expiry": expiry_text,
            })
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return out


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
    lines = [f":new: **{ANNOUNCE_MARK}** · {link(item)}", ""]
    desc = form_section(item["body"], "What are you working on?")
    if desc:
        lines += [desc if len(desc) <= DESC_MAX else desc[:DESC_MAX].rstrip() + "…", ""]
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
    channel = fetch_channel()
    items = list_items(project_id, fields)
    log(f"Reconciling {len(items)} board item(s) against Zulip{' (dry run)' if DRY_RUN else ''}.")
    for item in items:
        try:
            handle(item, channel)
        except Exception as e:  # one bad item must not stop the rest
            log(f"  ! #{item['number']}: {e}")


def announce_from_scratch(item: dict, cur: str, channel: Channel) -> None:
    """No announcement exists yet (a fresh claim, or the backfill of an existing registration): post
    it, then mark the current status. Messages go out before the reaction marker, so a crash leaves
    the next run able to tell the marker is still owed."""
    topic = topic_for(item)
    mid = post(topic, announcement(item), channel)
    if cur == COMPLETED:
        post(topic, completed_text(item), channel)
        add_reaction(mid, EMOJI[COMPLETED])
        log(f"  ✓ #{item['number']}: announced + completed (first seen as Completed).")
    else:
        add_reaction(mid, EMOJI.get(cur))
        log(f"  + #{item['number']}: announced (first seen as {cur}).")


MARKERS = set(STATUS_BY_EMOJI)


def set_marker(mid: int, desired: str | None, present: set[str]) -> None:
    """Make the announcement's marker reactions exactly {desired} (or none). Adds the desired one
    before removing the others so the status is never momentarily blank, and clears any stale
    markers a crash may have left behind."""
    if desired and desired not in present:
        add_reaction(mid, desired)
    for emoji in present:
        if emoji != desired:
            remove_reaction(mid, emoji)


def handle(item: dict, channel: Channel) -> None:
    cur = item["status"]
    if cur not in KNOWN:
        log(f"  ? #{item['number']}: unrecognised status {cur!r}; leaving alone.")
        return

    ann = channel.announcements.get(item["number"])
    if ann is None:
        if cur in ACTIVE or cur == COMPLETED:
            announce_from_scratch(item, cur, channel)
        return  # Unclaimed and never announced: nothing to say

    mid, topic = ann["mid"], ann["topic"]
    present = ann["reactions"] & MARKERS  # marker reactions currently on the announcement
    desired = EMOJI.get(cur)             # marker for the current status (None for Claimed)

    # Reconcile toward the current status. Each branch decides whether a transition just happened
    # from the *specific* markers present (not a single guessed "previous"), so duplicate or stale
    # markers from an interrupted run resolve deterministically. Follow-up messages go out before the
    # marker is set and de-dup against the topic, so a crash between the two repairs cleanly.
    if cur == COMPLETED:
        if EMOJI[COMPLETED] not in present:           # transitioning in (not already completed)
            post(topic, completed_text(item), channel)
            log(f"  ✓ #{item['number']}: -> Completed.")
        set_marker(mid, EMOJI[COMPLETED], present)
    elif cur == UNCLAIMED:
        if EMOJI[UNCLAIMED] in present:               # already shown as released: just tidy markers
            set_marker(mid, EMOJI[UNCLAIMED], present)
        elif EMOJI[COMPLETED] in present:             # Completed -> Unclaimed = reopened, no message
            set_marker(mid, EMOJI[UNCLAIMED], present)
            log(f"  ~ #{item['number']}: reopened (Completed -> Unclaimed).")
        else:                                          # active/Claimed -> Unclaimed = released
            post(topic, released_text(item), channel)
            set_marker(mid, EMOJI[UNCLAIMED], present)
            log(f"  ⌛ #{item['number']}: released.")
    elif cur == CLAIMED:
        if EMOJI[UNCLAIMED] in present:               # released -> Claimed = re-claimed
            post(topic, reclaimed_text(item), channel)
            log(f"  + #{item['number']}: re-claimed.")
        set_marker(mid, None, present)                # Claimed is the baseline: clear all markers
    else:                                              # In Progress / In Review
        if desired not in present:
            log(f"  ~ #{item['number']}: -> {cur}.")
        set_marker(mid, desired, present)


if __name__ == "__main__":
    try:
        reconcile()
    except Exception as e:
        log(f"FATAL: {e}")
        sys.exit(1)
