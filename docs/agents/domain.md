# Domain docs

## Before exploring

Read root `GLOSSARY.md`, when present, and relevant decisions in `docs/adr/`.
If root `GLOSSARY-MAP.md` exists, follow its pointers to relevant context glossaries instead.
If these files are absent, proceed silently; create terms and decisions lazily when domain modeling resolves them.

## Layout

This project uses one root `GLOSSARY.md` and root `docs/adr/` (single-context).

## Consumer rules

Use the glossary's vocabulary in issues, proposals, hypotheses, and tests.
For a missing concept, reconsider whether existing terminology applies; note a real gap for domain modeling.
Surface a conflict with an existing ADR explicitly, naming the ADR and explaining why it should be reconsidered.
