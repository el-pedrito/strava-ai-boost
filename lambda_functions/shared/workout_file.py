"""Zero-dependency writer for Apple ``.workout`` files (WorkoutKit custom workouts).

What a ``.workout`` file is
---------------------------
It is the file the Watch or the iPhone produces with "Share workout", and what
``WorkoutKit.WorkoutPlan.dataRepresentation`` encodes (iOS 17 / watchOS 10). Apple does
not document it. It is plain protobuf with no header, decoded by three independent MIT
projects (DotnetWorkoutKit, dotworkout, @bibixx/workoutkit). See
``docs/design/apple-watch-workouts.md``.

Scope
-----
Only what the Campus mapper (``shared.campus_workout``) needs: a CustomWorkout with an
optional warm-up and cool-down, interval blocks of WORK / RECOVERY steps, TIME and OPEN
goals, and a RANGE pace alert (CURRENT or AVERAGE). The low-level field writers are
public so tests can rebuild Apple's own files byte for byte with the few extra shapes
those files carry (distance goals, heart-rate and single-value alerts).

There is deliberately NO decoder here: production only writes. The strict decoder lives
in the tests, where it fails on any unknown field.

Wire layout (proven byte-exact against 3 real Watch exports and 1 Swift WorkoutKit file):

    WorkoutFile   { 9: GUID string, 11: CustomWorkout, 1000: version=1, 1002: format=5 }
    CustomWorkout { 1: activity, 2: location, 3: name, 4: warm-up Step,
                    5: repeated IntervalBlock, 6: cool-down Step }
    IntervalBlock { 1: repeated IntervalStep, 2: iterations }
    IntervalStep  { 1: purpose (WORK 1 / RECOVERY 2), 2: Step }
    Step          { 1: Goal, 2: Alert, 3: name }
    Goal          { 1: type (TIME 1 / OPEN 4), 2: TimeGoal { 1: unit, 2: double } }
    Alert         { 1: metric (AVERAGE 1 / CURRENT 2), 2: style (RANGE 2),
                    4: SpeedAlert { 2: Range { 1: lower bound, 2: upper bound } } }
    SpeedBound    { 1: { 1: unit=1, 2: m/s double }, 2: { 1: SECONDS=1, 2: 1.0 } }

Every enum value and container field number is a named constant. They are pinned by a
no-silent-change test: a typo here produces a file the Watch silently misreads.
"""

from __future__ import annotations

import math
import struct
import uuid
from typing import Iterable, Optional, Sequence

# ---------------------------------------------------------------- container constants

FIELD_GUID = 9
FIELD_CUSTOM_WORKOUT = 11
FIELD_VERSION = 1000
FIELD_FORMAT = 1002
FILE_VERSION = 1
FILE_FORMAT = 5

# ------------------------------------------------- HKWorkoutActivityType (verbatim)

ACTIVITY_TRADITIONAL_STRENGTH_TRAINING = 50
ACTIVITY_RUNNING = 37
ACTIVITY_HIGH_INTENSITY_INTERVAL_TRAINING = 63

# ----------------------------------------------------------------------- locations

LOCATION_INDOOR = 2
LOCATION_OUTDOOR = 3

# ---------------------------------------------------------------- interval purpose

PURPOSE_WORK = 1
PURPOSE_RECOVERY = 2

# ---------------------------------------------------------------------------- goals

GOAL_TIME = 1
GOAL_OPEN = 4

TIME_UNIT_SECONDS = 1
TIME_UNIT_MINUTES = 2
TIME_UNIT_HOURS = 3

# --------------------------------------------------------------------------- alerts

ALERT_METRIC_AVERAGE = 1
ALERT_METRIC_CURRENT = 2

ALERT_STYLE_VALUE = 1
ALERT_STYLE_RANGE = 2

# Speed bounds carry a unit (1 = metres) and a time denominator (SECONDS, 1.0):
# the stored value is always metres per second, whatever the Watch displays.
SPEED_UNIT_METERS = 1

_TIME_UNITS = (TIME_UNIT_SECONDS, TIME_UNIT_MINUTES, TIME_UNIT_HOURS)
_PURPOSES = (PURPOSE_WORK, PURPOSE_RECOVERY)
_PACE_METRICS = (ALERT_METRIC_AVERAGE, ALERT_METRIC_CURRENT)

# Protobuf wire types.
WIRE_VARINT = 0
WIRE_FIXED64 = 1
WIRE_LENGTH_DELIMITED = 2


# ------------------------------------------------------------- low-level wire writer

def encode_varint(value: int) -> bytes:
    """Encode a non-negative integer as a protobuf base-128 varint."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"varint needs a non-negative int, got {value!r}")
    out = bytearray()
    while True:
        low = value & 0x7F
        value >>= 7
        if value:
            out.append(low | 0x80)
        else:
            out.append(low)
            return bytes(out)


def _key(field: int, wire: int) -> bytes:
    if field < 1:
        raise ValueError(f"field number must be >= 1, got {field}")
    return encode_varint((field << 3) | wire)


def field_varint(field: int, value: int) -> bytes:
    """A varint field (enums, counts)."""
    return _key(field, WIRE_VARINT) + encode_varint(value)


def field_double(field: int, value: float) -> bytes:
    """A 64-bit little-endian IEEE-754 double field."""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"double must be finite, got {value!r}")
    return _key(field, WIRE_FIXED64) + struct.pack("<d", value)


def field_bytes(field: int, payload: bytes) -> bytes:
    """A length-delimited field (nested message or raw bytes)."""
    return _key(field, WIRE_LENGTH_DELIMITED) + encode_varint(len(payload)) + payload


def field_string(field: int, text: str) -> bytes:
    """A UTF-8 string field. Names are written verbatim, accents included."""
    return field_bytes(field, text.encode("utf-8"))


# -------------------------------------------------------------------- typed builders

def time_goal(value: float, unit: int) -> bytes:
    """A TIME goal: ``value`` expressed in ``unit`` (SECONDS, MINUTES or HOURS)."""
    if unit not in _TIME_UNITS:
        raise ValueError(f"unknown time unit {unit!r}")
    if not float(value) > 0:
        raise ValueError(f"time goal must be > 0, got {value!r}")
    return field_varint(1, GOAL_TIME) + field_bytes(
        2, field_varint(1, unit) + field_double(2, value)
    )


def open_goal() -> bytes:
    """An OPEN goal: the athlete ends the step by hand. Carries no payload."""
    return field_varint(1, GOAL_OPEN)


def speed_bound(meters_per_second: float) -> bytes:
    """One speed bound, always in metres per second."""
    if not float(meters_per_second) > 0:
        raise ValueError(f"speed must be > 0 m/s, got {meters_per_second!r}")
    speed = field_varint(1, SPEED_UNIT_METERS) + field_double(2, meters_per_second)
    per_second = field_varint(1, TIME_UNIT_SECONDS) + field_double(2, 1.0)
    return field_bytes(1, speed) + field_bytes(2, per_second)


def pace_range_alert(lower_mps: float, upper_mps: float, metric: int) -> bytes:
    """A RANGE pace alert.

    ``lower_mps`` is the SLOWER bound (fewer m/s). For a pace this reads backwards
    relative to how the Watch displays it ("4:41 - 4:29 /km"), which is the classic
    inverted-range bug, so it is enforced here rather than trusted.
    ``metric`` is CURRENT (instant pace) or AVERAGE (pace averaged over the step).
    """
    if metric not in _PACE_METRICS:
        raise ValueError(f"pace alert metric must be CURRENT or AVERAGE, got {metric!r}")
    if not float(lower_mps) < float(upper_mps):
        raise ValueError(
            f"lower bound must be the slower speed: {lower_mps!r} >= {upper_mps!r}"
        )
    bounds = field_bytes(1, speed_bound(lower_mps)) + field_bytes(2, speed_bound(upper_mps))
    return (
        field_varint(1, metric)
        + field_varint(2, ALERT_STYLE_RANGE)
        + field_bytes(4, field_bytes(2, bounds))
    )


def pace_value_alert(target_mps: float, metric: int) -> bytes:
    """A VALUE pace alert: one target pace, the Watch applies its own margin.

    Same shape as Apple's real export ``Probe_Alerts_Zones.workout`` (rebuilt byte for
    byte in the tests): style VALUE, payload in ``SpeedAlert.speed_target`` (field 1).
    """
    if metric not in _PACE_METRICS:
        raise ValueError(f"pace alert metric must be CURRENT or AVERAGE, got {metric!r}")
    return (
        field_varint(1, metric)
        + field_varint(2, ALERT_STYLE_VALUE)
        + field_bytes(4, field_bytes(1, speed_bound(target_mps)))
    )


def workout_step(goal: bytes, alert: Optional[bytes] = None, name: Optional[str] = None) -> bytes:
    """A WorkoutStep: a goal, an optional alert, an optional display name."""
    out = field_bytes(1, goal)
    if alert is not None:
        out += field_bytes(2, alert)
    if name:
        out += field_string(3, name)
    return out


def interval_step(purpose: int, step: bytes) -> bytes:
    """An IntervalStep: WORK or RECOVERY around a WorkoutStep."""
    if purpose not in _PURPOSES:
        raise ValueError(f"purpose must be WORK or RECOVERY, got {purpose!r}")
    return field_varint(1, purpose) + field_bytes(2, step)


def interval_block(steps: Sequence[bytes], iterations: int) -> bytes:
    """An IntervalBlock: ordered interval steps repeated ``iterations`` times.

    ``iterations == 1`` is valid on the wire: the Watch itself writes it for a block
    holding unrepeated steps, even though its picker starts at 2.
    """
    if not steps:
        raise ValueError("an interval block needs at least one step")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
        raise ValueError(f"iterations must be an int >= 1, got {iterations!r}")
    return b"".join(field_bytes(1, s) for s in steps) + field_varint(2, iterations)


def custom_workout(
    activity: int,
    location: int,
    name: Optional[str] = None,
    warmup: Optional[bytes] = None,
    blocks: Iterable[bytes] = (),
    cooldown: Optional[bytes] = None,
) -> bytes:
    """A CustomWorkout. Warm-up and cool-down are omitted from the wire when absent."""
    if location not in (LOCATION_INDOOR, LOCATION_OUTDOOR):
        raise ValueError(f"unknown location {location!r}")
    out = field_varint(1, activity) + field_varint(2, location)
    if name:
        out += field_string(3, name)
    if warmup is not None:
        out += field_bytes(4, warmup)
    for block in blocks:
        out += field_bytes(5, block)
    if cooldown is not None:
        out += field_bytes(6, cooldown)
    return out


def new_guid() -> str:
    """A fresh workout identity: uppercase UUIDv4, as the Watch writes it.

    The GUID is a stable identity on the device, not a per-export nonce, so every
    export mints a new one. A fixed GUID is for tests only.
    """
    return str(uuid.uuid4()).upper()


def validate_guid(guid: str) -> None:
    """Raise ValueError unless ``guid`` is an uppercase canonical UUID v4 (RFC 4122 variant)."""
    try:
        parsed = uuid.UUID(guid)
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"GUID must be a UUID string, got {guid!r}") from None
    # Lowercase is rejected, not uppercased: the Watch writes uppercase, and silently
    # rewriting a caller's GUID would hide a caller bug.
    if str(parsed).upper() != guid:
        raise ValueError(f"GUID must be the uppercase canonical form, got {guid!r}")
    if parsed.version != 4 or parsed.variant != uuid.RFC_4122:
        raise ValueError(f"GUID must be a UUID version 4 with the RFC 4122 variant, got {guid!r}")


def workout_file(custom: bytes, guid: str) -> bytes:
    """Wrap a CustomWorkout in the file container: GUID, workout, version, format."""
    validate_guid(guid)
    return (
        field_string(FIELD_GUID, guid)
        + field_bytes(FIELD_CUSTOM_WORKOUT, custom)
        + field_varint(FIELD_VERSION, FILE_VERSION)
        + field_varint(FIELD_FORMAT, FILE_FORMAT)
    )
