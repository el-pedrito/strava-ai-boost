"""Map one Campus Coach session to an Apple ``.workout`` file.

Pure module: no boto3, no environment reads, no logging of Campus text. The caller
(the future ``GET /plan/workouts`` branch) owns I/O and metric emission. Rules come
from ``docs/design/apple-watch-workouts.md`` section B; each one is pinned by
``tests/unit/test_campus_workout.py``.

Input shape: a session row as written by ``webhooks/campus_coach_sync.py``
(``sport``, ``training_type``, ``title``, ``week_date_iso``, ``training_index``,
``intervals``). Intervals use the new per-block shape (``{'type': 'block',
'repeat': N, 'exercises': [...]}``) or the new flat shape. A legacy flat entry with
its own ``repeat > 1`` is refused (``legacy_shape``): that producer copied the block
factor onto every exercise, so the real structure is lost and guessing it would put a
wrong session on the Watch.

Never raises: any malformed row (wrong types, NaN, lone surrogates...) comes back as a
non-encodable ``MapResult`` with a reason code.

Metrics are NOT emitted here. ``MapResult.metrics`` carries counters
(``WorkoutStepOpenFallback``, ``WorkoutUnknownPaceFamily``, ``WorkoutPaceOutOfRange``)
for the caller to flush with its own ``@metrics.log_metrics`` handler. Each counter is
counted per STEP, not per repetition: a 4x block whose step has an unknown pace family
counts 1. Calling ``add_metric`` from a shared helper would make every Lambda handler
responsible for flushing it (see ``tests/unit/test_metrics_flush.py``).
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from shared import workout_file as wf

# ------------------------------------------------------------------- tunables

# Pace alert window around the target speed (+/- 2.5 %). Tuned on the field: one
# constant, one test.
PACE_TOLERANCE = 0.025
# Shorter WORK steps get no pace alert: GPS pace needs time to settle, and an alert on
# a 30 s rep only produces noise.
MIN_PACE_ALERT_SECONDS = 180
# Iterations accepted per block. 98 is the highest value verified on a Watch export
# (dw-format.md section 4). Outside 1..MAX_REPEAT the item is refused, never clamped:
# a clamped repeat silently puts a different session on the Watch.
MIN_REPEAT = 1
MAX_REPEAT = 98
MAX_REPS = 999
MAX_STEPS_PER_BLOCK = 30
MAX_TOTAL_STEPS_PER_WORKOUT = 60
MAX_WORKOUT_BYTES = 8192
MAX_STEP_NAME_CHARS = 32
MAX_WORKOUT_NAME_CHARS = 32
MAX_FILENAME_CHARS = 60
MAX_FILENAME_INDEX = 99
# Plausible running target paces (s/km). A target outside 2:00..15:00 /km is a data
# error: no alert, no pace in the name, and a metric.
MIN_TARGET_SEC_PER_KM = 120
MAX_TARGET_SEC_PER_KM = 900

RACE_TRAINING_TYPES = frozenset({"Competition", "low-priority-race"})
QUALITY_FAMILIES = frozenset({"semi marathon", "tempo", "seuil", "course", "allure", "marathon"})
NO_ALERT_FAMILIES = frozenset({"ef", "lent", "aerobie", "rapide"})

# Applied in order, only while a step name is longer than MAX_STEP_NAME_CHARS.
# A short form ending in "é" is a past participle: it takes an "e" after a feminine
# head noun (FEMININE_HEAD_NOUNS), "Fente bulgare lestée" but "Squat lesté".
STEP_NAME_ABBREVIATIONS: Tuple[Tuple[str, str], ...] = (
    ("avec charge additionnelle", "lesté"),
    ("avec charge", "chargé"),
    ("jambe tendue", "j. tendue"),
    ("jambes tendues", "j. tendues"),
    ("Soulevé de terre", "SDT"),
    ("Récupération", "Récup"),
)
FEMININE_HEAD_NOUNS = frozenset({
    "fente", "fentes", "montee", "montees", "flexion", "flexions", "extension",
    "extensions", "chaise", "planche", "pompe", "pompes", "traction", "tractions",
    "elevation", "elevations", "rotation", "rotations", "marche", "foulee", "foulees",
})

# Reason codes of a non-encodable item.
REASON_UNSUPPORTED_SPORT = "unsupported_sport"
REASON_NO_INTERVALS = "no_intervals"
REASON_LEGACY_SHAPE = "legacy_shape"
REASON_BAD_REPEAT = "bad_repeat"
REASON_BAD_SHAPE = "bad_shape"
REASON_TOO_MANY_STEPS = "too_many_steps"
REASON_TOO_LARGE = "too_large"
REASON_INTERNAL = "internal"

METRIC_OPEN_FALLBACK = "WorkoutStepOpenFallback"
METRIC_UNKNOWN_PACE_FAMILY = "WorkoutUnknownPaceFamily"
METRIC_PACE_OUT_OF_RANGE = "WorkoutPaceOutOfRange"

_SPORTS = {
    "road": (wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR),
    "ppg": (wf.ACTIVITY_TRADITIONAL_STRENGTH_TRAINING, wf.LOCATION_INDOOR),
}

_DURATION_RE = re.compile(r"^\s*(\d+)(?::(\d{2}))?\s*(sec|min|h|hour|hours)\s*$", re.I)
_PACE_RE = re.compile(r"\((\d{1,2}):(\d{2})\s*/\s*km\)")
_FAMILY_RE = re.compile(r"^\s*([^()]*?)\s*\(")
# Substring match, no word boundary, on purpose: the plan matcher
# (modules_processing._CAMPUS_MARKERS) also matches these markers as substrings, so a
# step name like "Hippocampus" would still look like a Campus declaration to it. Keep
# the two aligned: our own file must never feed the matcher.
_BANNED_WORDS_RE = re.compile(r"campus|ppg", re.I)
_WEEK_RE = re.compile(r"W(\d{2})$")
_INT_RE = re.compile(r"^\s*-?\d+\s*$")


@dataclass
class MapResult:
    """Outcome of mapping one session. ``bytes``/``summary`` are set only if encodable."""

    encodable: bool
    reason_code: Optional[str] = None
    bytes: Optional[bytes] = None
    summary: Optional[str] = None
    metrics: Dict[str, int] = field(default_factory=dict)


@dataclass
class _Step:
    purpose: int
    seconds: Optional[int]
    encoded: bytes
    label: Optional[str]  # short text for the summary, None when not shown


class _Refused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ----------------------------------------------------------------- text helpers

def normalize_family(text: str) -> str:
    """Lowercase, strip accents, drop digits and punctuation, collapse spaces."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    letters_only = re.sub(r"[^a-z]+", " ", no_accents)
    return " ".join(letters_only.split())


def strip_banned_words(text: str) -> str:
    """Remove ``campus`` / ``ppg`` so our own file never feeds the plan matcher."""
    cleaned = _BANNED_WORDS_RE.sub(" ", text or "")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip(" -·:,")


def parse_duration_seconds(text: Any) -> Optional[int]:
    """``N sec``, ``N min``, ``M:SS min``, ``N h``/``hour``/``hours`` -> seconds."""
    if not isinstance(text, str):
        return None
    match = _DURATION_RE.match(text)
    if not match:
        return None
    whole, secs, unit = int(match.group(1)), match.group(2), match.group(3).lower()
    if unit == "min":
        if secs is not None and int(secs) >= 60:
            return None
        total = whole * 60 + (int(secs) if secs else 0)
    elif secs is not None:
        return None  # "1:30 sec" or "1:30 h" is not a format the sync produces
    elif unit == "sec":
        total = whole
    else:
        total = whole * 3600
    return total or None


def _is_hours(text: Any) -> bool:
    """True when the source wrote the duration in hours (kept in HOURS on the Watch)."""
    match = _DURATION_RE.match(text) if isinstance(text, str) else None
    return bool(match) and match.group(3).lower().startswith("h")


def _target_sec_per_km(pace: str) -> Optional[int]:
    """Target pace in s/km parsed from ``Family (M:SS/km)``; range is checked by the caller."""
    match = _PACE_RE.search(pace or "")
    if not match or int(match.group(2)) >= 60:
        return None
    total = int(match.group(1)) * 60 + int(match.group(2))
    return total or None


def _family_text(pace: str) -> str:
    match = _FAMILY_RE.match(pace or "")
    return match.group(1).strip() if match else (pace or "").strip()


def _fmt_pace(sec_per_km: int) -> str:
    return f"{sec_per_km // 60}:{sec_per_km % 60:02d}"


def _fmt_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "libre"
    minutes, secs = divmod(seconds, 60)
    if not minutes:
        return f'{secs}"'
    return f"{minutes}'" if not secs else f"{minutes}'{secs:02d}\""


def _agree(short: str, base: str) -> str:
    """Feminine agreement of an abbreviated participle with the name's head noun."""
    words = base.split()
    head = normalize_family(words[0]) if words else ""
    if not short.endswith("é") or not words:
        return short
    plural = words[0].lower().endswith(("s", "x"))
    if head in FEMININE_HEAD_NOUNS:
        return short + ("es" if plural else "e")
    return short + ("s" if plural else "")


def _cap_name(base: str, suffix: str, limit: int) -> str:
    """Fit ``base + suffix`` in ``limit`` chars: abbreviate, then truncate the base."""
    for long, short in STEP_NAME_ABBREVIATIONS:
        if len(base) + len(suffix) <= limit:
            break
        replacement = _agree(short, base)
        base = re.sub(re.escape(long), lambda _m: replacement, base, flags=re.I)
    if len(base) + len(suffix) > limit:
        cut = base[: max(0, limit - len(suffix))]
        # Prefer a word boundary: "Soulevé de terre jambe" reads better than "... jambe t".
        if " " in cut and base[len(cut):len(cut) + 1] not in ("", " "):
            cut = cut.rsplit(" ", 1)[0]
        base = cut.rstrip()
    return (base + suffix).strip()


def _to_int(value: Any) -> Optional[int]:
    """An integer from int / Decimal / integral float / digit string, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (Decimal, float)):
        # NaN and infinities: int() would raise ValueError / OverflowError.
        if not math.isfinite(value):
            return None
        return int(value) if value == int(value) else None
    if isinstance(value, str) and _INT_RE.match(value):
        return int(value)
    return None


# ------------------------------------------------------------------- mapping

class _Mapper:
    def __init__(self, session: Dict[str, Any], run: bool) -> None:
        self.run = run
        self.race = session.get("training_type") in RACE_TRAINING_TYPES
        self.metrics: Dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.metrics[name] = self.metrics.get(name, 0) + 1

    def _goal(self, entry: Dict[str, Any]) -> Tuple[bytes, Optional[int]]:
        seconds = parse_duration_seconds(entry.get("duration"))
        if seconds is None:
            # A strength step counted in reps has no duration by design: OPEN is the
            # expected goal there, not a fallback worth a metric.
            if not (entry.get("reps") and not _text(entry, "duration").strip()):
                self._count(METRIC_OPEN_FALLBACK)
            return wf.open_goal(), None
        if _is_hours(entry.get("duration")):
            return wf.time_goal(float(seconds // 3600), wf.TIME_UNIT_HOURS), seconds
        if seconds % 60 == 0:
            return wf.time_goal(float(seconds // 60), wf.TIME_UNIT_MINUTES), seconds
        return wf.time_goal(float(seconds), wf.TIME_UNIT_SECONDS), seconds

    def _run_step(self, entry, purpose, seconds, is_edge) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """Alert, step name and summary label for a running step."""
        pace = _text(entry, "pace")
        family_text = _family_text(pace)
        family = normalize_family(family_text)
        target = _target_sec_per_km(pace)
        if target is not None and not MIN_TARGET_SEC_PER_KM <= target <= MAX_TARGET_SEC_PER_KM:
            self._count(METRIC_PACE_OUT_OF_RANGE)
            target = None
        quality = family in QUALITY_FAMILIES
        if family and not quality and family not in NO_ALERT_FAMILIES:
            self._count(METRIC_UNKNOWN_PACE_FAMILY)

        alert = None
        if (
            quality
            and target
            and purpose == wf.PURPOSE_WORK
            and not is_edge
            and seconds is not None
            and seconds >= MIN_PACE_ALERT_SECONDS
        ):
            mps = 1000.0 / target
            metric = wf.ALERT_METRIC_AVERAGE if self.race else wf.ALERT_METRIC_CURRENT
            alert = wf.pace_range_alert(mps * (1 - PACE_TOLERANCE), mps * (1 + PACE_TOLERANCE), metric)

        display = strip_banned_words(family_text)
        name = None
        if display:
            suffix = f" {_fmt_pace(target)}" if target else ""
            name = _cap_name(display, suffix, MAX_STEP_NAME_CHARS) or None
        label = None
        if purpose == wf.PURPOSE_WORK and not is_edge and display:
            short = display.split()[0]
            label = f"{short} {_fmt_pace(target)}" if target else short
        return alert, name, label

    def _strength_name(self, entry) -> Optional[str]:
        base = strip_banned_words(_text(entry, "name"))
        reps = _reps(entry)
        suffix = f" x{reps} rép." if reps else ""
        if not base:
            return suffix.strip() or None
        return _cap_name(base, suffix, MAX_STEP_NAME_CHARS) or None

    def step(self, entry: Any, is_edge: bool = False) -> _Step:
        if not isinstance(entry, dict) or entry.get("type") == "block":
            raise _Refused(REASON_BAD_SHAPE)
        for key in ("type", "duration", "pace", "name"):
            _text(entry, key)  # refuses a non-string value up front
        _reps(entry)
        purpose = wf.PURPOSE_RECOVERY if entry.get("type") == "recovery" else wf.PURPOSE_WORK
        goal, seconds = self._goal(entry)
        if self.run:
            alert, name, label = self._run_step(entry, purpose, seconds, is_edge)
        else:
            alert, name, label = None, self._strength_name(entry), None
        return _Step(purpose, seconds, wf.workout_step(goal, alert, name), label)


def _text(row: Dict[str, Any], key: str) -> str:
    """A string field, ``""`` when absent; any other type refuses the item."""
    value = row.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise _Refused(REASON_BAD_SHAPE)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:  # lone surrogate: not representable in the file
        raise _Refused(REASON_BAD_SHAPE) from None
    return value


def _reps(entry: Dict[str, Any]) -> Optional[int]:
    """Rep count of a strength step; a present but non-positive-integer value refuses."""
    raw = entry.get("reps")
    if raw is None or raw == "":
        return None
    reps = _to_int(raw)
    # The upper bound keeps the " x<n> rép." suffix short enough for the 32-char name cap.
    if reps is None or not 1 <= reps <= MAX_REPS:
        raise _Refused(REASON_BAD_SHAPE)
    return reps


def _repeat(raw: Any) -> int:
    repeat = _to_int(raw)
    if repeat is None or not MIN_REPEAT <= repeat <= MAX_REPEAT:
        raise _Refused(REASON_BAD_REPEAT)
    return repeat


def _summary_token(step: _Step) -> str:
    text = _fmt_duration(step.seconds)
    return f"{text} {step.label}" if step.label else text


def _block_summary(steps: List[_Step], repeat: int, run: bool) -> str:
    if not run:
        inner = f"{len(steps)} étape" + ("s" if len(steps) > 1 else "")
        return inner if repeat == 1 else f"{repeat}x({inner})"
    joined = " + ".join(_summary_token(s) for s in steps)
    return joined if repeat == 1 else f"{repeat}x({joined})"


def _workout_name(session: Dict[str, Any]) -> str:
    title = strip_banned_words(_text(session, "title")) or "Séance"
    week = _WEEK_RE.search(_text(session, "week_date_iso"))
    suffix = f" W{week.group(1)}" if week else ""
    if len(title) + len(suffix) > MAX_WORKOUT_NAME_CHARS:
        title = title[: MAX_WORKOUT_NAME_CHARS - len(suffix)].rstrip()
    return title + suffix


def _check_shape(intervals: List[Any]) -> None:
    for entry in intervals:
        if not isinstance(entry, dict):
            raise _Refused(REASON_BAD_SHAPE)
        if entry.get("type") == "block":
            continue
        raw = entry.get("repeat")
        if raw is None or raw == "":
            continue
        # Same 1..MAX_REPEAT rule as a block; then any factor above 1 is the legacy shape.
        if _repeat(raw) > 1:
            raise _Refused(REASON_LEGACY_SHAPE)


def map_session(session: Dict[str, Any], guid: Optional[str] = None) -> MapResult:
    """Encode one Campus session, or say why it cannot be. Never raises.

    ``guid``: a fresh UUIDv4 per export in production; tests pass a fixed one. A bad
    ``guid`` is a caller bug, not row data: it raises ValueError here, before any mapping.
    """
    if guid is not None:
        wf.validate_guid(guid)
    mapper: Optional[_Mapper] = None
    try:
        if not isinstance(session, dict):
            raise _Refused(REASON_BAD_SHAPE)
        sport = session.get("sport")
        if sport is not None and not isinstance(sport, str):
            raise _Refused(REASON_BAD_SHAPE)
        if sport not in _SPORTS:
            raise _Refused(REASON_UNSUPPORTED_SPORT)
        _text(session, "training_type")
        intervals = session.get("intervals")
        if not isinstance(intervals, list) or not intervals:
            raise _Refused(REASON_NO_INTERVALS)
        mapper = _Mapper(session, sport == "road")
        return _encode(session, sport, intervals, mapper, guid)
    except _Refused as refused:
        return MapResult(False, refused.reason, metrics=mapper.metrics if mapper else {})
    except (ValueError, TypeError, AttributeError, OverflowError, UnicodeError):
        # Last-resort boundary: one malformed row must be refused, not crash the batch.
        # Known bad shapes are refused above as bad_shape; reaching this line means a
        # case nobody anticipated, so it is reported as internal (plan section C).
        return MapResult(False, REASON_INTERNAL, metrics=mapper.metrics if mapper else {})


def _encode(
    session: Dict[str, Any], sport: str, intervals: List[Any], mapper: _Mapper, guid: Optional[str],
) -> MapResult:
    run = mapper.run
    _check_shape(intervals)
    entries = list(intervals)
    warmup = cooldown = None
    # Only index 0 is a warm-up and only the last index a cool-down; a warm-up
    # typed entry elsewhere becomes a plain WORK step.
    if entries[0].get("type") == "warm-up":
        warmup = mapper.step(entries.pop(0), is_edge=True)
    if entries and entries[-1].get("type") == "cool-down":
        cooldown = mapper.step(entries.pop(), is_edge=True)

    blocks: List[Tuple[List[_Step], int]] = []
    loose: List[_Step] = []
    for entry in entries:
        if entry.get("type") != "block":
            loose.append(mapper.step(entry))
            continue
        if loose:
            blocks.append((loose, 1))
            loose = []
        repeat = _repeat(entry.get("repeat"))
        exercises = entry.get("exercises")
        if not isinstance(exercises, list) or not exercises:
            raise _Refused(REASON_BAD_SHAPE)
        blocks.append(([mapper.step(e) for e in exercises], repeat))
    if loose:
        blocks.append((loose, 1))
    if not blocks:
        # Only a warm-up and/or a cool-down: no Watch export has zero interval blocks.
        raise _Refused(REASON_NO_INTERVALS)

    total = sum(len(s) for s, _ in blocks) + (warmup is not None) + (cooldown is not None)
    if any(len(s) > MAX_STEPS_PER_BLOCK for s, _ in blocks) or total > MAX_TOTAL_STEPS_PER_WORKOUT:
        raise _Refused(REASON_TOO_MANY_STEPS)

    activity, location = _SPORTS[sport]
    custom = wf.custom_workout(
        activity,
        location,
        _workout_name(session),
        warmup=warmup.encoded if warmup else None,
        blocks=[
            wf.interval_block([wf.interval_step(s.purpose, s.encoded) for s in steps], repeat)
            for steps, repeat in blocks
        ],
        cooldown=cooldown.encoded if cooldown else None,
    )
    data = wf.workout_file(custom, guid or wf.new_guid())
    if len(data) > MAX_WORKOUT_BYTES:
        raise _Refused(REASON_TOO_LARGE)

    parts = []
    if warmup:
        parts.append(f"WU {_fmt_duration(warmup.seconds)}")
    parts.extend(_block_summary(steps, repeat, run) for steps, repeat in blocks)
    if cooldown:
        parts.append(f"CD {_fmt_duration(cooldown.seconds)}")
    return MapResult(True, None, data, " · ".join(parts), mapper.metrics)


def workout_filename(session: Dict[str, Any]) -> str:
    """``<week>-<index>-<slug>.workout``: ASCII only, at most MAX_FILENAME_CHARS.

    ``index`` is clamped to 0..MAX_FILENAME_INDEX (anything non-integral is 0), so the
    prefix stays short and the ``.workout`` extension is always kept.
    """
    raw_week = session.get("week_date_iso")
    week = re.sub(r"[^A-Za-z0-9-]+", "", raw_week if isinstance(raw_week, str) else "")[:10]
    index = _to_int(session.get("training_index"))
    index = min(max(index if index is not None else 0, 0), MAX_FILENAME_INDEX)
    raw_title = session.get("title")
    title = strip_banned_words(raw_title if isinstance(raw_title, str) else "")
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-") or "seance"
    prefix = f"{week or 'week'}-{index}-"
    ext = ".workout"
    room = MAX_FILENAME_CHARS - len(prefix) - len(ext)
    slug = slug[: max(1, room)].rstrip("-") or "s"
    return prefix + slug + ext
