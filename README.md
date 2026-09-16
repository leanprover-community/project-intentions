# Project Intentions

This Github repo provides a [Project Intentions board](https://github.com/orgs/leanprover-community/projects/34)  for recording intentions to work on formalization projects in the Lean community.
If you're working on a project, or about to start one, you can open an issue here to say so.
The point is to help people find collaborators and avoid quietly duplicating each other's work.

It's not a reservation system, although credible intentions about student projects should certainly be respected.

It's brand new, and experimental. We'll see if people use it, and iterate as needed to make it more useful. Feedback welcome.

## Please read this first

- **There are no guarantees.** Registering a project here gives you no claim over anything. Nobody is
  obliged to respect your registration, to check this repository before starting their own work, or
  even to read it. Treat everything here as a courtesy, not a contract.
- **A registration is not a queue, a lock, a priority right, or a request for anyone to stop.** It is
  only a statement of what you intend to do, made visible.
- **It's purely informational.** If two people register overlapping work, that's a conversation to
  have, not a dispute to resolve here.
- **Be nice.** We like working in a community. Make use of the information here to make friends, find collaborators,
  and contribute to our collective goals. Don't use it to make things worse by scooping projects!
- **Respect students.** The research training pipeline is critical to the health of mathematics, and formal mathematics.
  Everything has been upended by AI, and we need to collectively work out a good path to the future.
  Look after your students, and other students, and pay special attention to what will help them.
- **Be specific.** "Working on analysis" helps nobody. "Formalising the Radon-Nikodym theorem,
  building on `Mathlib.MeasureTheory.Decomposition.Lebesgue`" tells people exactly what you're doing
  and whether it overlaps with theirs.
- **Give a credible expiry date.** Every registration expires (see below). A credible expiry is one
  you actually believe: a date by which you expect to have made real progress or finished. If you're
  not confident you'll have moved in a month, don't register for six. Stale, optimistic claims are
  worse than no claim at all, because they discourage others without delivering anything.
- **Don't be lazy.** If you've made a registration here, use that as motivation to work hard and get things done. If your plans change, don't hesitate to come back and modify your registration.
- **Don't post anything you wouldn't publish.** This repository is public. For private work, describe
  it only at the level you're happy to make public; leave out anything confidential.

## How to register

1. Open a [new project intention](https://github.com/leanprover-community/project-intentions/issues/new?template=project-intention.yml)
   (the same form is reachable from this repository's **Issues** tab via **New issue**). Any GitHub
   account can do this — no special access is needed.
1. Complete the title after the `[Intention]` prefix, and fill in the template. Say what you're working
   on, whether it's public or private, the credible expiry date, and the other details the template
   asks for. Submitting the form registers you — the bot adds your intention to the
   [board](https://github.com/orgs/leanprover-community/projects/34), reads your expiry, and comments
   to confirm, with no separate step.

Don't look for an "Add item" button on the board itself. The board is the public, read-only view of
these issues: GitHub shows its editing controls (the `+` at the edge of each column) only to the few
accounts with write access to the project, and offers no setting that opens them to everyone.
Registration goes through the issue form above, and the bot keeps the board in sync.

### Registering as a group

If several people are working on the project, list their GitHub handles in the form's
**Participants** field (e.g. `@alice, @bob`; you're included automatically as the author). Keep the
leading `@` on each handle: a name written without it isn't recognised, though the bot will tell you
so rather than quietly registering nobody. The bot registers everyone alongside you, and the board's
Assignees column shows the whole team.

If someone you listed is not a member of the `leanprover-community` organization and has not
commented on the issue, GitHub won't let the bot assign them. The confirmation comment says so and
names them; they can register themselves by commenting `claim` on the issue, since being listed in
the form counts as your invitation.

To add participants after registering, edit the issue body and add their handle under the
`### Participants` heading (add the heading yourself if your issue predates the field), then have
them comment `claim`. Removing a handle from the list doesn't remove someone already registered: a
participant must comment `disclaim` to step back, or a maintainer can unassign them.

### The five columns

Every intention sits in exactly one column of the board:

| Column | What it means |
|---|---|
| **Planned** | Someone has registered themselves, with an expiry date. |
| **In Progress** | Work is actively underway. |
| **In Review** | The work is out for review. |
| **Completed** | Finished, or the issue was closed. |
| **Abandoned** | The work won't be pursued, and anyone is free to pick it up. |

**Only intentions in *Planned* expire.** An intention in any other column is left alone by the
expiry sweep, so moving yours to *In Progress* when you actually start work takes it out of the
expiry system altogether. See [Expiry](#expiry) below.

### Moving your intention between columns

You don't need a maintainer to move your own card. Comment on the issue with one word:

| Comment | Moves the card to |
|---|---|
| `progress` | **In Progress** — you've started work. |
| `review` | **In Review** — it's out for review. |
| `done` | **Completed** — it's finished. |
| `disclaim` | **Abandoned** — you're stepping back and anyone may pick it up. |
| `claim` | **Planned** — registers you again. |

Anyone registered on the intention can use these, as can the author and anyone listed in the
Participants field. The author and listed participants can always `claim`, whatever column the card
is in, so you'll never be told that your own intention is unavailable.

## Expiry

**Expiry applies only to intentions in the *Planned* column.** Once yours is *In Progress* (comment
`progress`), *In Review*, *Completed* or *Abandoned*, it is not subject to expiry at all and the
date recorded against it no longer matters. Nothing is ever taken away from you because you were
busy working: it is the unstarted registration, not the active project, that goes stale.

For an intention that is still *Planned*:

- Default: **90 days** (about three months), used when the form gives no date the bot can use.
- Maximum: normally **180 days** (about six months). If you expect the project to last longer — a
  doctoral thesis, for instance — say so in the issue and ask a maintainer.
- The date comes from the **Credible expiry date** field of the registration form, and must be an
  actual date in `YYYY-MM-DD` form. A duration such as "6 months", or a date beyond the maximum, is
  refused and the 90-day default is recorded instead; the bot says so in the comment it posts when
  it registers you, so it is worth reading that comment.

**To renew or change the date**, comment on the issue with `claim` followed by the date you intend,
for example `claim 2027-01-31`. Any registered participant may do this, not only the author.

**If the date passes** without a renewal, the bot moves the intention to *Abandoned*, removes
everyone assigned to it, clears the note, and comments to say that the registration has lapsed. The
issue itself is not closed and nothing is deleted, but the intention is then free for anyone to take
up, its former holders having no special claim on it. A lapsed registration isn't a judgement on
you; it just means the information went stale, which is exactly when it should stop being shown as
current — and you are welcome to claim it again.

## How this works under the hood

The claim/expiry machinery is the
[leanprover-community/intentions](https://github.com/leanprover-community/intentions) GitHub Action,
which tracks each issue on the
[Project Intentions board](https://github.com/orgs/leanprover-community/projects/34) and runs a
scheduled sweep to release expired claims. `claim` and `disclaim` are the two commands you need; see
that repository for the rest.
