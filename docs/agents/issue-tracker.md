# Issue tracker: Local Markdown

Issues and specs live as Markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`.
- The spec is `.scratch/<feature-slug>/spec.md`.
- Each implementation ticket is a separate `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`.
- Record triage state as a `Status:` line near the top; use `triage-labels.md` for role strings.
- Append comments and conversation history under `## Comments`.
- Publish to the issue tracker by creating the relevant local file; fetch a ticket by reading its path.

## Wayfinding operations

- Map: `.scratch/<effort>/map.md`, containing Notes, Decisions-so-far, and Fog.
- Child ticket: `.scratch/<effort>/issues/NN-<slug>.md`; record `Type: research`, `prototype`, `grilling`, or `task`.
- Dependencies: `Blocked by: NN, NN`; a ticket is unblocked when all referenced tickets are resolved.
- Frontier: open, unblocked, unclaimed tickets, ordered by number.
- Claim: set `Status: claimed` before work.
- Resolve: append `## Answer`, set `Status: resolved`, and append a result pointer to the map's Decisions-so-far.

`claimed` and `resolved` are wayfinding lifecycle states; the five triage roles apply when classifying tickets.
