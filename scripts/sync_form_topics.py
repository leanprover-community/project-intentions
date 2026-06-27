#!/usr/bin/env python3
"""Rewrite the issue form's "Relevant Mathlib topic areas" dropdown to match this repo's `t-` labels.

The labels themselves are mirrored from Mathlib by the Sync topic labels workflow; this keeps the
form's selectable options in step, so a newly added area is actually pickable (the topic-labels
workflow only applies an option if a matching `t-` label exists). Options are listed alphabetically;
the file is left untouched (and nothing is committed) when it already matches.

Reads the repo's labels with `gh` (needs GH_TOKEN); rewrites the dropdown in place.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

FORM = os.environ.get("FORM_PATH", ".github/ISSUE_TEMPLATE/project-intention.yml")
REPO = os.environ["GITHUB_REPOSITORY"]
DROPDOWN_ID = "topics"


def topic_labels() -> list[str]:
    out = subprocess.check_output(
        ["gh", "label", "list", "-R", REPO, "-L", "1000", "--json", "name"], text=True)
    names = [l["name"] for l in json.loads(out)]
    return sorted(n for n in names if n.startswith("t-"))


def rewrite(lines: list[str], options: list[str]) -> list[str] | None:
    """Replace the option lines under the topics dropdown. Returns new lines, or None if unchanged."""
    # Find the dropdown block by its `id: topics`, bound the search to that block (up to the next
    # `  - ` body item), then its `options:` line, then the run of `        - ...` option lines under
    # it. Bounding to the block ensures we never rewrite a different dropdown's options by mistake.
    try:
        i = next(n for n, ln in enumerate(lines) if ln.strip() == f"id: {DROPDOWN_ID}")
    except StopIteration:
        raise RuntimeError(f"No dropdown with id: {DROPDOWN_ID} in {FORM}.")
    block_end = next((n for n in range(i + 1, len(lines)) if lines[n].startswith("  - ")), len(lines))
    j = next((n for n in range(i, block_end) if lines[n] == "      options:"), None)
    if j is None:
        raise RuntimeError(f"No 'options:' under id: {DROPDOWN_ID} in {FORM}.")
    k = j + 1
    while k < block_end and lines[k].startswith("        - "):
        k += 1
    new_block = [f"        - {name}" for name in options]
    if lines[j + 1:k] == new_block:
        return None
    return lines[:j + 1] + new_block + lines[k:]


def main() -> None:
    options = topic_labels()
    if not options:
        raise RuntimeError("No t- labels found on the repo; refusing to empty the dropdown.")
    with open(FORM) as f:
        lines = f.read().split("\n")
    updated = rewrite(lines, options)
    if updated is None:
        print("Form dropdown already matches the t- labels; nothing to do.")
        return
    with open(FORM, "w") as f:
        f.write("\n".join(updated))
    print(f"Updated {FORM} dropdown to {len(options)} topic areas.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
