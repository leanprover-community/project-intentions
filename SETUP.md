# Maintainer setup

This repository drives the [leanprover-community/intentions](https://github.com/leanprover-community/intentions)
action. The workflow in `.github/workflows/intentions.yml` is not enough on its own: it needs a
project board and an authenticated bot. Here's everything, so it can be rebuilt or moved.

## The board

A **Projects v2** board titled exactly **Project Intentions** (the `project-title` in the workflow):

<https://github.com/orgs/leanprover-community/projects/34>

It has:

- a single-select **Status** field with options `Unclaimed`, `Claimed`, `In Progress`, `In Review`,
  `Completed`;
- a Text field **Claim Expires** (the action stores each claim's expiry here, as ISO 8601 UTC);
- a Text field **Claim Note** (optional freeform note scraped from `claim` comments).

The board is public, so anyone can browse registrations by status.

## The label

Issues opened through the template carry the `intention` label, and the workflow sets
`auto-add-labels: "intention"` so only those issues land on the board. The label must exist in this
repository, or the template silently can't apply it and nothing gets added.

## Authentication

The default `GITHUB_TOKEN` cannot write an org-level Projects v2 board, so the action runs as a
GitHub App. Create it by hand (the board is org-owned, so Projects R/W goes under *Organization*
permissions):

1. Org -> Settings -> Developer settings -> GitHub Apps -> **New GitHub App**
   (<https://github.com/organizations/leanprover-community/settings/apps>).
2. Name it (e.g. `leanprover-community-intentions`); set any valid homepage URL; under **Webhook**,
   untick **Active**.
3. **Permissions:**
   - Repository permissions -> **Issues**: Read and write; **Pull requests**: Read and write.
   - Organization permissions -> **Projects**: Read and write.
4. **Where can this GitHub App be installed?** -> Only on this account. Create the App.
5. Note the **App ID**, generate a **private key** (`.pem`), and **install** the App on this
   repository (Install App in the App's sidebar).
6. In this repo, Settings -> Secrets and variables -> Actions, add:
   - variable **`INTENTIONS_BOT_APP_ID`** = the App ID;
   - secret **`INTENTIONS_BOT_APP_PRIVATE_KEY`** = the full contents of the `.pem`.

A fine-grained PAT with Projects R/W works too; see the intentions README for that route.

## Checking it works

After the App is installed and the variable/secret are set, run the workflow once by hand
(Actions -> Intentions -> Run workflow), then open a test issue and comment `claim 2w` on it. The bot
should add it to the board, set it to `Claimed`, and record the expiry. `disclaim` should release it.
