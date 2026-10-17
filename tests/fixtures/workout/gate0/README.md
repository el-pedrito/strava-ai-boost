# Gate 0 goldens

Synthetic Campus sessions (same SHAPE as rows written by `campus_coach_sync.py`). Titles,
step names and paces are invented: neutral ids (`step_1`, ...), paces shifted a few seconds
from any real zone, titles reworded. `TestGate0NoRealContent` in
`tests/unit/test_campus_workout.py` fails if any title, name or pace also appears in a local
dump of real sessions (skipped when the dump is absent).

Each `<case>.json` holds `{"guid": ..., "session": {...}}`; `<case>.workout` is the file
`shared.campus_workout.map_session` produces for it with that fixed GUID.
`tests/unit/test_campus_workout.py` asserts
`map_session(session, guid=guid, range_alerts=spec.get("range_alerts", False)) == golden`.

| Case | Covers |
|---|---|
| `ef_45` | single EF step, no alert |
| `intensity_semi` | WU 15' + block x4 (9' Semi Marathon 4:28 CURRENT alert + 2' Lent) + CD 5' |
| `sl_tempo` | WU, Aerobie (no alert), `1:30 min` recovery, Tempo (alert), CD |
| `ppg_renfo` | strength, 13 flat steps (reps -> OPEN, timed holds), block x3, long-name abbreviation with gender agreement (`lestée`), `PPG` stripped from the title |
| `race_semi` | race `96:42 min`, `course` family, AVERAGE alert |
| `ef_range` | `RANGE_ALERTS_ENABLED` on (`"range_alerts": true`): structured `range` steps, WU 15' + 30' + CD 10' EF, RANGE CURRENT alert on all three, names `EF 5:43-6:08` (value 355.4 +/- 12.4) |

Regenerate (from the repo root, project venv):

    python tests/fixtures/workout/gate0/regenerate.py

**Changing a golden after Gate 0 requires redoing at least Gate 0 step 2b** (checking the
file on the Watch), see `docs/design/apple-watch-workouts.md`.
