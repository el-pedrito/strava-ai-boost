"""Output guard for the content agent: verify, regenerate once, strip as a last resort.

The content agent had no output check at all. Only the coach output was verified, which is
exactly why the coach's weekly figures were caught in production on 2026-08-14 while the
content agent published, on the same activity, "Bloc 1/2" and "Prochaine etape : le Bloc 2"
for a Campus session performed in full.

Order of recourse, same as the coach branch and for the same reason:

1. verify against the facts computed from the laps and the matched Campus plan,
2. regenerate ONCE, handing the model the problems found,
3. strip the contradicted sentences only if the regeneration is still wrong or fails.

Strip is last because the description is the athlete's main text, not an annex: a stripped
description is amputated, a regenerated one is whole. It is still better than publishing a
false figure, which is why it is not simply skipped.

Never blocking. An unchecked description beats no description.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from processing.coach_output_check import (
    CONTENT_CHECKED_FIELDS,
    find_internal_contradictions,
    strip_false_claims,
    verify_weekly_claims,
)
from shared.campus_structure import (
    compute_ppg_volume,
    extract_athlete_loads,
    is_fully_completed,
    summarize_structure,
)
from shared.lap_facts import build_lap_facts

# A callable taking the problems found and returning a fresh content dict, or None.
Regenerator = Callable[[List[str]], Optional[Dict[str, Any]]]


def build_content_facts(
    activity_data: Optional[Dict[str, Any]],
    laps_data: Optional[list],
    modules: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Collect the facts the content branch can compute on its own.

    Deliberately returns None for a family it cannot establish, rather than an empty
    default: a missing fact must produce no verdict, never a guess against zero.
    """
    matched = None
    for module in modules or []:
        if module.get("name") == "campus_coach" and module.get("matched_session"):
            matched = module["matched_session"]
            break

    duration_min = None
    raw_duration = (activity_data or {}).get("moving_time")
    if raw_duration is not None:
        try:
            duration_min = float(raw_duration) / 60.0
        except (TypeError, ValueError):
            duration_min = None

    campus = None
    if matched:
        # The volume carries the computed isometric times, which is what the seconds-total
        # guard compares against. Without it that guard is inert, exactly the shape of
        # defect this project keeps producing: a rule implemented and never reached.
        loads = extract_athlete_loads(
            (activity_data or {}).get("original_description")
            or (activity_data or {}).get("description")
        )
        campus = {
            "fully_completed": is_fully_completed(matched, duration_min),
            "structure": summarize_structure(matched),
            "computed_volume": compute_ppg_volume(matched, loads),
        }

    return {
        "lap_facts": build_lap_facts(laps_data) if laps_data else None,
        "campus": campus,
    }


def verify_content(
    content: Optional[Dict[str, Any]],
    facts: Optional[Dict[str, Any]],
    activity_date: str = "",
) -> List[str]:
    """Return the problems in one content dict, empty when it is consistent."""
    if not isinstance(content, dict):
        return []
    problems = verify_weekly_claims(content, None, None, facts, CONTENT_CHECKED_FIELDS)
    problems += find_internal_contradictions(content, activity_date, CONTENT_CHECKED_FIELDS)
    return problems


def _restore_emptied_fields(
    stripped: Dict[str, Any],
    original: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """Undo the strip on any field it emptied, and report which ones.

    Found by a test rather than by reasoning: on the real 2026-08-14 description all three
    sentences were contradicted, so the strip returned an EMPTY description. Publishing
    that would wipe the athlete's text from Strava, and an empty title is not a valid
    activity name at all. Where the strip removes everything it has no repair to offer, so
    the original is kept and the problem stays reported instead of being silently traded
    for a blank field.
    """
    restored = dict(stripped)
    kept: List[str] = []
    for field in CONTENT_CHECKED_FIELDS:
        had_text = str(original.get(field) or "").strip()
        has_text = str(restored.get(field) or "").strip()
        if had_text and not has_text:
            restored[field] = original[field]
            kept.append(field)
    return restored, kept


def apply_content_guard(
    content: Dict[str, Any],
    activity_data: Optional[Dict[str, Any]],
    laps_data: Optional[list],
    modules: Optional[List[Dict[str, Any]]],
    regenerate: Optional[Regenerator] = None,
) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Verify the generated content, regenerate once, strip only as a last resort.

    Returns ``(content, remaining_problems, removed_sentences)``. The returned content is
    always publishable: no field it received non-empty is handed back empty.
    """
    facts = build_content_facts(activity_data, laps_data, modules)
    activity_date = str(
        (activity_data or {}).get("start_date_local")
        or (activity_data or {}).get("start_date")
        or ""
    )

    problems = verify_content(content, facts, activity_date)
    if not problems:
        return content, [], []

    retried = None
    if regenerate is not None:
        try:
            retried = regenerate(list(problems))
        except Exception:
            # Swallowed on purpose: a regeneration failure must not cost the athlete the
            # publication. The caller logs; the fallback below still removes the false
            # sentences from the original.
            retried = None

    if isinstance(retried, dict):
        remaining = verify_content(retried, facts, activity_date)
        if not remaining:
            return retried, [], []
        stripped, removed = strip_false_claims(
            retried, None, None, facts, CONTENT_CHECKED_FIELDS
        )
        stripped, kept = _restore_emptied_fields(stripped, retried)
        if kept:
            removed = []
        return stripped, remaining, removed

    stripped, removed = strip_false_claims(
        content, None, None, facts, CONTENT_CHECKED_FIELDS
    )
    stripped, kept = _restore_emptied_fields(stripped, content)
    if kept:
        removed = []
    return stripped, problems, removed
