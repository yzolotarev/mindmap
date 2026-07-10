# Implementation notes - phase 1 (10.07.2026)

Plan: FOUNDATION.md + rewritten skill (4 copies) + review bug fix + gesture-protocol
+ README/install.sh + onboarding on canvas. Phase 2 (later): sub-canvases with layers,
lasso, brain-dump mode, GRINDE audit, separate session files, stable node IDs.

## Deviations

- **Review lost group arrows.** Found during live use on 10.07: the parser
  mindmap-review.py skipped lines `[Group] -> A` (skip by `startswith("[")`) and did not
  match `A -> [Group]` (regex `\w+`). The user had 2 out of 5 links survive. The plan did not
  provide for this - the fix was added to phase 1 as mandatory.
- **The "Essence of the tool" review was assembled manually** (essence-review.json in scratchpad),
  bypassing the bug. The user's answer to the question "Is mutual understanding a start or a result?" was not received
  (the window was not closed); the essence was taken from his verbal formulation: mutual understanding =
  the goal that the tool achieves. Added to FOUNDATION as a loop.
- **Identical group names are ambiguous** in text export (`[Group] -> A` with
  two groups named "Group"). Resolution - the first group with that name. Known limitation,
  structural fix = stable IDs (phase 2).
- **Pi left WITHOUT --no-signal, intentionally.** The plan required uniformity with Claude
  Code, but in Pi the xdotool phrase is the awakening mechanism (no background tasks
  waking the agent). Conservative choice: do not touch the working circuit.
- **Onboarding hint only in web canvas.** Tk fallback is without it (rare path,
  add during the first real use of Tk).
- **--dry flag added to mindmap-review.py** beyond the plan: without it, the group
  bug fix cannot be verified without opening a window.
- **R = flip selected arrow** added beyond the plan: on live e2e on 10.07
  the user drew an arrow in the wrong direction and found no way to flip it (wrote
  the question right in the link label). Friction exactly in the 60-second gesture - fixed immediately
  (click on line + R/K, hint in status bar, line in README).

