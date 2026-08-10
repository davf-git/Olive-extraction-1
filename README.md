# Handoff notes

This folder is a starting point, not a working scraper — nobody has
inspected the real item-page HTML yet (I can't reach olivenetwork.org from
where I'm running).

## To run this with Claude Code

1. Copy this folder to Woz's machine (or yours).
2. `cd olive-extraction && python3 -m venv venv && source venv/bin/activate
   && pip install -r requirements.txt`
3. Open the folder in Claude Code and say something like:
   *"Read CLAUDE.md and follow it — start with the pre-checks in step 1,
   then build discover.py."*
4. Let it inspect the real site structure and write the actual parsing
   logic — the field names and file layout in CLAUDE.md are fixed, the
   selectors are for Claude Code to find by looking at the live HTML.

## What "done" looks like

An `articles/` folder of Markdown files, an `images/` folder, and a
`manifest.csv` with every one of ~2,000 items marked `done` or `failed`.
Hand that folder back — that's the whole deliverable for Phase 1.
