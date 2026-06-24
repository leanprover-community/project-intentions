# Project Intentions

A lightweight, public, **informational** registry for the Lean and Mathlib community. If you're
working on a project, or about to start one, you can open an issue here to say so. The point is to
help people find collaborators and avoid quietly duplicating each other's work.

That's the whole idea. It is not a reservation system, and it has no teeth.

## Please read this first

- **There are no guarantees.** Registering a project here gives you no claim over anything. Nobody is
  obliged to respect your registration, to check this repository before starting their own work, or
  even to read it. Treat everything here as a courtesy, not a contract.
- **A registration is not a queue, a lock, a priority right, or a request for anyone to stop.** It is
  only a statement of what you intend to do, made visible.
- **It's purely informational.** If two people register overlapping work, that's a conversation to
  have, not a dispute to resolve here.
- **Be specific.** "Working on analysis" helps nobody. "Formalising the Radon-Nikodym theorem,
  building on `Mathlib.MeasureTheory.Decomposition.Lebesgue`" tells people exactly what you're doing
  and whether it overlaps with theirs.
- **Give a credible expiry date.** Every registration expires (see below). A credible expiry is one
  you actually believe: a date by which you expect to have made real progress or finished. If you're
  not confident you'll have moved in a month, don't register for six. Stale, optimistic claims are
  worse than no claim at all, because they discourage others without delivering anything.
- **Don't post anything you wouldn't publish.** This repository is public. For private work, describe
  it only at the level you're happy to make public; leave out anything confidential.

## How to register

1. Open a new issue using the **Project intention** template, and fill it in. Say what you're working
   on, whether it's public or private, and the other details the template asks for.
2. **Then comment `claim` on your issue to register yourself, with an expiry.** This is a separate,
   required step: the expiry you wrote in the form is just text until you set it here. A bare `claim`
   uses the default (30 days); `claim 3 months` or `claim 2026-09-01` sets your own, up to the
   six-month maximum.
3. When something changes, just `claim` again to renew or extend. Use `disclaim` to release a
   registration early once you've stopped (or finished).

Registrations that lapse are swept automatically, so the registry reflects what people actually
believe they're still working on, not what they once intended.

## Expiry

- Default: **30 days** (about a month).
- Maximum: **180 days** (about six months).

Renew by claiming again before it lapses. A lapsed registration isn't a judgement on you; it just
means the information went stale, which is exactly when it should stop being shown as current.

## How this works under the hood

The claim/expiry machinery is the
[leanprover-community/intentions](https://github.com/leanprover-community/intentions) GitHub Action,
which tracks each issue on the
[Project Intentions board](https://github.com/orgs/leanprover-community/projects/34) and runs a
scheduled sweep to release expired claims. `claim` and `disclaim` are the two commands you need; see
that repository for the rest. Maintainer setup is recorded in [SETUP.md](SETUP.md).
