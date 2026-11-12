"""Countdown logic, rendering and FPP output for fpp-matrixcountdown.

Modules arrive by phase (see DEVELOPMENT_PLAN.md):
  timecalc.py  - resolve_target(), compute_display()   (Phase 2)
  message.py   - the two styled pieces                  (Phase 2)
  render.py    - Pillow frames, the countdown centered  (Phase 3)
  output.py    - overlay buffer writer, model on/off    (Phase 4)
"""
