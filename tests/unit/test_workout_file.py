"""Tests for shared/workout_file.py: the protobuf writer behind Apple ``.workout`` files.

The strongest proof is byte equality with files Apple produced itself
(tests/fixtures/workout/apple/, provenance and SHA-256 in its README): a writer that
rebuilds them exactly cannot be silently misordering fields or mis-encoding doubles.
"""

import hashlib
import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda_functions"))

from shared import workout_file as wf  # noqa: E402

APPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "workout", "apple")

# Shapes Apple's files carry that the Campus mapper never writes. Built here from the
# public low-level writers so the production module stays limited to what it needs.
GOAL_DISTANCE = 3
DISTANCE_UNIT_METERS = 1
ALERT_METRIC_HEART_RATE = 5


def _apple(name):
    with open(os.path.join(APPLE_DIR, name), "rb") as fh:
        return fh.read()


def _distance_goal(meters):
    return wf.field_varint(1, GOAL_DISTANCE) + wf.field_bytes(
        4, wf.field_varint(1, DISTANCE_UNIT_METERS) + wf.field_double(2, meters)
    )


def _hr_range_alert(low, high):
    rng = wf.field_bytes(1, wf.field_double(1, low)) + wf.field_bytes(2, wf.field_double(1, high))
    return (
        wf.field_varint(1, ALERT_METRIC_HEART_RATE)
        + wf.field_varint(2, wf.ALERT_STYLE_RANGE)
        + wf.field_bytes(7, wf.field_bytes(2, rng))
    )


def _speed_value_alert(mps):
    # The production builder: Probe_Alerts_Zones.workout (a real Watch export) is
    # rebuilt with it byte for byte, which pins pace_value_alert to Apple's format.
    return wf.pace_value_alert(mps, wf.ALERT_METRIC_CURRENT)


def _recovery_60s():
    return wf.interval_step(wf.PURPOSE_RECOVERY, wf.workout_step(wf.time_goal(60.0, wf.TIME_UNIT_SECONDS)))


class TestAppleFilesRebuiltByteForByte:
    def test_fixture_hashes_match_readme(self):
        expected = {
            "Run_Average.workout": "462cfe698ddc4e7c3c2102672fcb2654423668924b2288a045995a6987767c8e",  # pragma: allowlist secret
            "ProbeAlertsRange.workout": "d587f78eb4623b117f5b38af3bc0bf191214b874a08fef17b686ef9e931f0dfc",  # pragma: allowlist secret
            "Probe_Alerts_Zones.workout": "2728d6a51f9f3a5feb359f6d191a04e3da34a7b79e666bdb83bf47d612db6979",  # pragma: allowlist secret
            "custom-hiit-mixed.workout": "5ad2274b2a18e9ff67d088b9aab6f70505a8a28704351e1e7ee27f9473080cb8",  # pragma: allowlist secret
        }
        with open(os.path.join(APPLE_DIR, "README.md"), encoding="utf-8") as fh:
            readme = fh.read()
        for name, digest in expected.items():
            assert hashlib.sha256(_apple(name)).hexdigest() == digest, name
            assert digest in readme, name

    def test_run_average_watch_export_range_average(self):
        # The Watch stored these exact doubles; rebuilding them from 1000/s rounds differently.
        slow = struct.unpack("<d", b">\xf8\xe0\x83\x0f>\x08@")[0]
        fast = struct.unpack("<d", b"\xab\xaa\xaa\xaa\xaa\xaa\n@")[0]
        work = wf.interval_step(
            wf.PURPOSE_WORK,
            wf.workout_step(_distance_goal(400.0), wf.pace_range_alert(slow, fast, wf.ALERT_METRIC_AVERAGE)),
        )
        custom = wf.custom_workout(
            wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR, "Run_Average",
            blocks=[wf.interval_block([work, _recovery_60s()], 2)],
        )
        built = wf.workout_file(custom, "AF5BAD10-228E-433F-A0A8-D296F2FCD874")
        assert built == _apple("Run_Average.workout")

    def test_probe_alerts_range_current_with_warmup_and_cooldown(self):
        work = wf.interval_step(
            wf.PURPOSE_WORK,
            wf.workout_step(
                _distance_goal(400.0),
                wf.pace_range_alert(1000 / 330, 1000 / 300, wf.ALERT_METRIC_CURRENT),
            ),
        )
        custom = wf.custom_workout(
            wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR, "Probe Alerts",
            warmup=wf.workout_step(wf.time_goal(10.0, wf.TIME_UNIT_MINUTES), _hr_range_alert(120.0, 140.0)),
            blocks=[wf.interval_block([work, _recovery_60s()], 3)],
            cooldown=wf.workout_step(wf.time_goal(300.0, wf.TIME_UNIT_SECONDS)),
        )
        built = wf.workout_file(custom, "4004C7EB-8906-4861-B689-C99F93A3A33F")
        assert built == _apple("ProbeAlertsRange.workout")

    def test_probe_alerts_zones_single_value_pace(self):
        work = wf.interval_step(wf.PURPOSE_WORK, wf.workout_step(_distance_goal(400.0), _speed_value_alert(1000 / 300)))
        custom = wf.custom_workout(
            wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR, "Probe Alerts",
            blocks=[wf.interval_block([work, _recovery_60s()], 3)],
        )
        built = wf.workout_file(custom, "4004C7EB-8906-4861-B689-C99F93A3A33F")
        assert built == _apple("Probe_Alerts_Zones.workout")

    def test_swift_workoutkit_hiit_named_steps(self):
        def block(work_s, rec_s, name):
            return wf.interval_block([
                wf.interval_step(wf.PURPOSE_WORK, wf.workout_step(wf.time_goal(work_s, wf.TIME_UNIT_SECONDS), name=name)),
                wf.interval_step(wf.PURPOSE_RECOVERY, wf.workout_step(wf.time_goal(rec_s, wf.TIME_UNIT_SECONDS))),
            ], 2)

        custom = wf.custom_workout(
            wf.ACTIVITY_HIGH_INTENSITY_INTERVAL_TRAINING, wf.LOCATION_INDOOR, "Pyramid HIIT",
            warmup=wf.workout_step(wf.time_goal(5.0, wf.TIME_UNIT_MINUTES)),
            blocks=[block(30.0, 15.0, "Hard"), block(45.0, 30.0, "Harder")],
            cooldown=wf.workout_step(wf.time_goal(3.0, wf.TIME_UNIT_MINUTES)),
        )
        built = wf.workout_file(custom, "00000000-0000-4000-8000-000000000004")
        assert built == _apple("custom-hiit-mixed.workout")


class TestConstantsNoSilentChange:
    def test_container_and_enum_values_are_pinned(self):
        # Changing any of these makes a file the Watch silently misreads. If Apple
        # changes the format, update here deliberately and redo Gate 0.
        assert (wf.FIELD_GUID, wf.FIELD_CUSTOM_WORKOUT, wf.FIELD_VERSION, wf.FIELD_FORMAT) == (9, 11, 1000, 1002)
        assert (wf.FILE_VERSION, wf.FILE_FORMAT) == (1, 5)
        assert wf.ACTIVITY_RUNNING == 37
        assert wf.ACTIVITY_TRADITIONAL_STRENGTH_TRAINING == 50
        assert wf.ACTIVITY_HIGH_INTENSITY_INTERVAL_TRAINING == 63
        assert (wf.LOCATION_INDOOR, wf.LOCATION_OUTDOOR) == (2, 3)
        assert (wf.PURPOSE_WORK, wf.PURPOSE_RECOVERY) == (1, 2)
        assert (wf.GOAL_TIME, wf.GOAL_OPEN) == (1, 4)
        assert (wf.TIME_UNIT_SECONDS, wf.TIME_UNIT_MINUTES, wf.TIME_UNIT_HOURS) == (1, 2, 3)
        assert (wf.ALERT_METRIC_AVERAGE, wf.ALERT_METRIC_CURRENT) == (1, 2)
        assert (wf.ALERT_STYLE_VALUE, wf.ALERT_STYLE_RANGE) == (1, 2)
        assert wf.SPEED_UNIT_METERS == 1

    def test_container_trailer_bytes(self):
        tail = wf.field_varint(wf.FIELD_VERSION, 1) + wf.field_varint(wf.FIELD_FORMAT, 5)
        assert tail == bytes.fromhex("c03e01d03e05")


class TestWriterGuards:
    def test_varint_multibyte(self):
        assert wf.encode_varint(0) == b"\x00"
        assert wf.encode_varint(300) == b"\xac\x02"

    def test_varint_rejects_negative_and_bool(self):
        with pytest.raises(ValueError):
            wf.encode_varint(-1)
        with pytest.raises(ValueError):
            wf.encode_varint(True)

    def test_double_rejects_nan(self):
        with pytest.raises(ValueError):
            wf.field_double(2, float("nan"))

    def test_pace_range_rejects_inverted_bounds(self):
        with pytest.raises(ValueError):
            wf.pace_range_alert(4.0, 3.5, wf.ALERT_METRIC_CURRENT)
        with pytest.raises(ValueError):
            wf.pace_range_alert(3.5, 3.5, wf.ALERT_METRIC_CURRENT)

    def test_pace_range_rejects_non_pace_metric(self):
        with pytest.raises(ValueError):
            wf.pace_range_alert(3.0, 3.5, 5)

    def test_time_goal_rejects_zero_and_unknown_unit(self):
        with pytest.raises(ValueError):
            wf.time_goal(0, wf.TIME_UNIT_SECONDS)
        with pytest.raises(ValueError):
            wf.time_goal(10, 9)

    def test_interval_block_guards(self):
        step = _recovery_60s()
        with pytest.raises(ValueError):
            wf.interval_block([], 1)
        with pytest.raises(ValueError):
            wf.interval_block([step], 0)
        assert wf.interval_block([step], 1).endswith(b"\x10\x01")

    def test_interval_step_rejects_unknown_purpose(self):
        with pytest.raises(ValueError):
            wf.interval_step(3, wf.workout_step(wf.open_goal()))

    def test_guid_must_be_uppercase_uuid(self):
        custom = wf.custom_workout(wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR)
        with pytest.raises(ValueError):
            wf.workout_file(custom, "not-a-guid")
        with pytest.raises(ValueError):
            wf.workout_file(custom, "af5bad10-228e-433f-a0a8-d296f2fcd874")

    def test_new_guid_is_fresh_uppercase_v4(self):
        first, second = wf.new_guid(), wf.new_guid()
        assert first != second
        assert first == first.upper() and first[14] == "4"
        assert first[19] in "89AB"  # RFC 4122 variant nibble

    def test_guid_lowercase_v4_is_rejected_not_uppercased(self):
        custom = wf.custom_workout(wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR)
        with pytest.raises(ValueError, match="uppercase"):
            wf.workout_file(custom, "af5bad10-228e-433f-a0a8-d296f2fcd874")

    def test_guid_uppercase_v4_is_accepted_verbatim(self):
        custom = wf.custom_workout(wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR)
        guid = "AF5BAD10-228E-433F-A0A8-D296F2FCD874"
        assert wf.workout_file(custom, guid).startswith(wf.field_string(wf.FIELD_GUID, guid))

    def test_guid_version_1_is_rejected(self):
        custom = wf.custom_workout(wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR)
        with pytest.raises(ValueError, match="version 4"):
            wf.workout_file(custom, "AF5BAD10-228E-133F-A0A8-D296F2FCD874")

    def test_guid_non_rfc_variant_is_rejected(self):
        custom = wf.custom_workout(wf.ACTIVITY_RUNNING, wf.LOCATION_OUTDOOR)
        # Variant nibble C = Microsoft reserved, not RFC 4122.
        with pytest.raises(ValueError, match="RFC 4122"):
            wf.workout_file(custom, "AF5BAD10-228E-433F-C0A8-D296F2FCD874")

    def test_open_goal_has_no_payload(self):
        assert wf.open_goal() == b"\x08\x04"

    def test_names_are_utf8(self):
        assert wf.workout_step(wf.open_goal(), name="Récup").endswith("Récup".encode("utf-8"))
