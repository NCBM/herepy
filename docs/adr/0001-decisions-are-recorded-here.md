# 1. Decisions are recorded here

**Status**: accepted, 2026-11-16.

## Context

The shape of this project was worked out in discussion: what the Java/Python boundary is, how a unit
of Python code is identified and loaded, who revokes a registration, whether the host thread runs an
event loop. None of it was written down. The repository's `README.md` is still the NeoGradle template
it was generated from, and there is no version control history to consult (the tree has
`.gitignore`/`.gitattributes` but no `.git`), so a decision that stops being true leaves nothing behind
that says why it was made — only code that looks arbitrary.

The neighbouring project `composat` records its decisions this way, and the format is borrowed from it
deliberately: one file per decision, a title that is a claim, and a section for the options that were
refused.

## Decision

Every decision that a future reader could reasonably want to revisit gets one file in `docs/adr`,
numbered in the order it was made, with:

- **Status** — one of `proposed`, `accepted`, `superseded by NNNN`, `rejected`, and the date the
  status last changed.
- **Context** — what made the decision necessary, in terms of the code as it is.
- **Decision** — what was decided, specific enough to check the code against.
- **Consequences** — what follows, including what it costs and what it forbids.
- **Alternatives considered** — every option actually weighed, and why it lost. This is the section
  that earns the file: the decision itself is usually visible in the code, and the reason the other
  options lost is not.

A recorded decision that has entered a commit is fixed: a change arrives as a new record that supersedes it, and both
stay. A record that has never been committed holds no such weight — the tree has no version control yet — so it may be
rewritten, or folded into a later record that subsumes it, while nothing depends on its exact words.

Where a decision could be settled by running something, the record says what was measured. The cases that can be
re-run live in [`tools/checks/check.py`](../../tools/checks/check.py); the rest answered a question once, and the
answer is stated in the record it bears on.

## Consequences

- Reading `docs/adr/README.md` in order is reading the design.
- A decision that gets argued twice is a missing record.
- The records are files, so they survive the repository having no version control at present.
- Nothing enforces them. A record that contradicts the code is a disagreement to resolve, not a build
  error.

## Alternatives considered

- **One design document, rewritten in place.** Cheaper to read once, and it loses exactly what is
  wanted later: the options that were refused and the state of the code that made them lose.
- **Issue and pull-request descriptions.** There is no remote and no history here to hold them, and a
  description attached to a change goes stale in a way a dated record does not.
- **Nothing, and rely on the discussion being remembered.** The current state of this repository.
- **Docstrings only.** They answer "what does this do now" and say nothing about what was refused,
  which is the question that gets re-litigated.
