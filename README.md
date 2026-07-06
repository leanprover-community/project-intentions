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

1. Go to the [Project Intentions board](https://github.com/orgs/leanprover-community/projects/34) and click `Add Item` under any of the four main sections: "Planned", "In Progress", "In Review" or "Completed".
1. In the field that opens at the bottom of your window, type the title of your project, and then "Create a New Issue"
1. Without touching the "Repository" (it should remain `leanprover-community/project-intentions`), select `Project Intention` and fill the template. Say what you're working
   on, whether it's public or private, the credible expiry date, and the other details the template
   asks for. Submitting the form registers you — the bot reads your expiry and comments to confirm,
   with no separate step.

## Expiry

- Default: **90 days** (about three months).
- Maximum: Normally **180 days** (about six months): if you plan that the project will last more than six months (e. g. for a PhD thesis), justify your choice.

Renew by claiming again before it lapses. A lapsed registration isn't a judgement on you; it just
means the information went stale, which is exactly when it should stop being shown as current.

## How this works under the hood

The claim/expiry machinery is the
[leanprover-community/intentions](https://github.com/leanprover-community/intentions) GitHub Action,
which tracks each issue on the
[Project Intentions board](https://github.com/orgs/leanprover-community/projects/34) and runs a
scheduled sweep to release expired claims. `claim` and `disclaim` are the two commands you need; see
that repository for the rest.
