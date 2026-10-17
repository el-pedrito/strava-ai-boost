# Strength insights on the Coach page

Muscle-group sets, estimated 1RM, a records board and a push/pull balance, built
from the athlete's own parsed strength sets. Scope is the dashboard summary API
and the Coach page only: the pipeline, the coach agent, the parser and the stored
data are unchanged, and DynamoDB is read-only.

## Why

Strava added a workout log and muscle maps in its own app, but its API does not
return those sets, so the figures are built from our own `parsed_sets`. The Coach
page already showed a per-exercise progression chart (top weight or volume) and a
per-session tonnage chart. This adds four things the athlete asked for: how many
sets each muscle group gets per week, an estimated 1RM trend, a records board, and
a push/pull balance.

## Data read

`user_preferences.strength_history.entries`, each entry:

```
date, activity_id, duration_min, description,
parsed_sets[{exercise, sets, reps, weight_kg,
             sets_detail[{reps, weight_kg, duration_s}], sides}],
per_exercise[{exercise, volume_kg, volume_incomplete}],
total_sets, total_reps, volume_kg, volume_kg_incomplete,
sets_source (athlete_text | campus_plan),
body_weight_kg_used, excluded_exercises
```

Numbers come back from DynamoDB as `Decimal`; some legacy rows stored them as
strings (including a French decimal comma). Every read goes through
`shared/numeric.py::to_finite_float`, which accepts `int`, `float`, `Decimal` and
`str`, rejects booleans and `None`, and returns `None` for any non-finite result.

## Modules

| Module | Role |
|---|---|
| `shared/numeric.py` | `to_finite_float`: the one finite-number coercion. |
| `shared/strength_muscles.py` | Exercise → muscle map, pattern, e1RM flag, buckets. |
| `shared/strength_insights.py` | Pure builders for the whole `strength_insights` payload. |
| `api/dashboard_api.py` | Normalises history once and wires the builders in, each guarded. |
| `shared/responses.py` | Recursive non-finite sanitizer before `json.dumps(allow_nan=False)`. |

`shared/strength_progress.py` (the running coach's progression reader) is NOT
touched.

## Muscle map

Lookup key is `_normalization_key(canonicalize_exercise_name(name))`, so case,
accent and alias variants resolve to one entry. Each exercise carries
`group_weights` (a muscle group → fractional set credit), a `pattern`
(`push|pull|legs|core|other`) and an `e1rm` flag.

- **Credit per set**: 1.0 on each primary group, 0.5 on each secondary. One set of
  bench press is pectoraux 1.0, triceps 0.5, epaules 0.5. Unilateral work counts
  once (not doubled like the session `total_sets`).
- **Groups (10)**: pectoraux, dos, epaules, biceps, triceps, quadriceps, ischios,
  fessiers, mollets, abdos. Plus two non-muscle buckets: `explosivite`
  (conditioning / ballistic moves, shown as its own bar) and `autre` (unmapped,
  surfaced so gaps stay visible).
- **Mixed machine**: a single stored `Développé machine` name conflates a chest
  press and a shoulder press (a pre-existing parser limitation, out of this
  read-only scope). It is split pectoraux/epaules/triceps 0.5 each, flagged
  `mixed`, kept out of e1RM and the records board, and the chart shows a
  non-comparable note. A follow-up (separate change) can split the two movements
  in the parser and re-extract history.
- **Ambiguous / conditioning**: a knee-flexion move whose target muscle is
  ambiguous lands in `autre` with reason `to_confirm`; kettlebell swings show on
  the explosiveness bar and credit glutes/hamstrings 0.5; jumps are explosiveness
  only.
- **Resolution order**: exact normalised key, then the longest matching stem
  (`pont fessier`, `gainage`, `fente`, `mollet`), then `autre`. Rep-based Campus
  calf and lunge moves are already renamed to `Mollets` / `Fentes` upstream, so
  the stems mainly catch future hold names.

A test asserts every canonical name resolves to a real entry (except the one
`to_confirm` case), every group used is one of the ten (plus the two buckets), and
every name the Campus plan produces resolves.

## Weekly muscle sets

Eight consecutive ISO weeks ending at the current Europe/Paris week, zero-filled;
the current week is flagged `partial`. Each week carries, per group, a `logged`
and a `campus_plan` segment:

- a set counts when it has `reps > 0` or `duration_s > 0` (holds count);
- the count is the number of valid `sets_detail` rows; a flat `sets` fallback is
  used only when there is no usable detail and the flat row itself is countable;
- Campus-plan sets (sets and reps prescribed by the plan, loads from the athlete's
  text) go to the `campus_plan` segment so performed-and-logged versus
  plan-derived stays visible.

The counting rule is exposed as an i18n key. Warm-ups cannot be told apart from
work sets, so the UI says "logged sets", never "working sets".

## Estimated 1RM

Epley `load × (1 + reps / 30)`, with `reps == 1 → load`, computed per set and
rounded to 0.5 kg. Eligible only when:

- the exercise's map flag `e1rm` is true (compound plate/barbell lifts: the main
  presses on a bar, machine/bar rows, squat, leg press, hip thrust, deadlift);
- the session is not `campus_plan` (reps are prescribed there);
- integer reps 1..10 (above 10 the estimate is unreliable);
- a finite load > 0.

Dumbbell presses, isolation, cable, bodyweight, unilateral, hold and conditioning
moves are not eligible. The best set of a day is that day's point; the chart
merges to the per-day maximum. The label states that the estimate depends on
proximity to failure and is comparable only on the same exercise and the same
equipment.

**Per-side notation hazard.** The extractor doubles a per-side load (`/c`,
`/côté`, `each side`, …), so "40/c" is stored as 80 while "@100" is stored as 100.
If an exercise's history mixes a per-side-noted session and a plain one, switching
notation would fake a record.

An exercise is per-side in a session when every one of its stored loads equals
2 x a number written just before a per-side token in the session text, and that
load is not also written as a plain number. The load link ties the notation to
the lift it belongs to: a first version tainted every exercise of a session as soon
as one line said "/c", which on live data marked 19 of 22 lifts (bench press
included) and emptied the records board. The "not written plain" rule stops a
coincidence such as "dc 80x10" next to "Press inc 40/c" (stored 80).

An exercise with both kinds of session is marked `notation_mixed`, made
e1RM-ineligible, and excluded from the e1RM, top-weight and volume records. The
chart shows a "total load noted, mixed notation" note. Rows with no record at all
(holds, jumps) are left off the board.

## Records board

One row per canonical exercise with at least two sessions, sorted by last session
date, capped at 15.

- **Loaded lifts**: best top weight (max load over valid sets), best e1RM
  (eligible, non-Campus, non-mixed, non-notation-mixed only), best session volume
  (read from `per_exercise.volume_kg`, skipping rows flagged
  `volume_incomplete`). Each with its date; ties keep the earliest date.
  Campus-plan loads are kept for top weight (the loads are the athlete's) but
  excluded from e1RM. `load_label` is `total_noted`.
- **Bodyweight lifts** (pull-ups, dips, push-ups): no top weight; best reps at no
  added load, and the best weighted set as `{reps, added_weight_kg}`.

Record fields are typed and nullable; bodyweight rows null their loaded fields and
loaded rows null the bodyweight fields.

## Push / pull balance

From the `pattern` field only, logged sets only (Campus plan excluded), over the
last four weeks of the window. One set counts 1 for its pattern. The ratio is
`push / pull`, and `null` when there is no pull (never infinity). No judgement
text.

## API payload

`trends.strength_insights`:

```
{
  counting_rule: str,
  weeks: [{week: "YYYY-Www", partial: bool,
           groups: {<group>: {logged, campus_plan}},   // all 10 keys, zero-filled
           explosivite: {logged, campus_plan},
           autre: {logged, campus_plan}}],
  push_pull: [{week, push, pull, ratio|null}],
  records: [{exercise, kind: "loaded"|"bodyweight", last_date, notation_mixed,
             load_label: "total_noted"|null,
             top_weight_kg|null, top_weight_date|null,
             e1rm_kg|null, e1rm_date|null,
             best_volume_kg|null, best_volume_date|null,
             best_reps_bw: {reps, date}|null,
             best_weighted_bw: {reps, added_weight_kg, date}|null}],
  unmapped_exercises: [{exercise, reason: "unknown"|"to_confirm"}],
  mixed_exercises: [{exercise, note_key}]
}
```

Each progression entry gains `e1rm_eligible`, `mixed`, `notation_mixed` and
`load_label`; each point gains `e1rm_kg` (the per-day maximum, or `null`).

`trends.strength_history` is projected to the four fields the UI uses (`date`,
`activity_id`, `duration_min`, `description`) after normalisation, then capped at
the last 20.

## Isolation and JSON safety

- `strength_history` is normalised once: only dict entries with a valid
  `YYYY-MM-DD` date survive; the rest are dropped and counted in a log warning.
- `_build_strength_progression` and `_build_strength_sessions` are hardened
  (`isinstance` checks, numbers via `to_finite_float`) and each wrapped in its own
  `try/except Exception → []` with a warning, the same pattern as the compliance
  block.
- `strength_insights` is built inside its own `try/except Exception → None`.
- The existing error fallback for the whole summary is unchanged. A test asserts
  that garbage history yields HTTP 200, the running trends identical to a clean
  baseline, and a body that parses with a strict JSON parser.
- `shared/responses.py` sanitizes non-finite `float` and `Decimal` to `null`
  recursively over dict/list/tuple, then serialises with `allow_nan=False`, so a
  missed value fails closed (500) rather than producing a body the browser rejects.
  Output is byte-identical for finite payloads. This covers every endpoint that
  uses `create_success_response`.

## Frontend

- `ErrorBoundary` gains optional `fallback` (a compact node) and `resetKey`
  (resets when it changes). The app-level usage is unchanged.
- The progression chart's weight/volume toggle becomes a `weight | volume | e1rm`
  metric map. The e1RM button appears only when the selected exercise is
  `e1rm_eligible`; selecting a non-eligible exercise while on e1RM falls back to
  weight. A metric with fewer than three points shows a metric-level empty state
  instead of hiding the chart. Mixed / notation-mixed / "total load noted" notes
  render under the chart.
- Three new blocks: weekly stacked bars per muscle group (logged vs Campus-plan
  segments, an explosiveness bar, and an "other" bar listing unmapped exercises),
  a records table (horizontal scroll on narrow screens), and a push/pull line.
  Each block, and the existing strength blocks, are wrapped in a local
  `ErrorBoundary` with a "block unavailable" fallback, so one failing block never
  blanks the page.
- All new TypeScript fields are optional and arrays default to `[]`. FR and EN
  i18n keys are added.

## Testing

- Backend: finite coercion; full map coverage (canonical, Campus and plan-fixture
  names); set counting (holds, zero/negative/non-integer/non-finite, flat
  fallback); Epley values and the reps/eligibility rules; records including
  bodyweight typing, earliest-date ties, volume-incomplete exclusion, the mixed
  machine and the per-side notation fixture; weeks zero-fill and the current Paris
  week; push/pull null ratio; the serializer (byte-identical finite output,
  NaN/inf/Decimal sanitised); and garbage history isolation (HTTP 200, running
  trends identical, strict JSON).
- Frontend: each new block renders, missing payload renders nothing, a malformed
  block shows its local fallback while siblings render, and the e1RM toggle and
  metric empty-state rules, with a `ResizeObserver` mock.
