---
name: download-summary
description: >-
  Branch-marker skill that exists ONLY on the feat/api-download-summary branch.
  Used to prove the orchestrator resolves a slash-branch instead of falling back
  to the default branch. Trigger words: download summary, branch marker.
---

# Download summary (branch marker)

This skill only exists on the `feat/api-download-summary` branch. If an agent has
it mounted, the orchestrator correctly resolved the slash-containing branch (and
did not silently fall back to `main`, which does not contain this folder).
