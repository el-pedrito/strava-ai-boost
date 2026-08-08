"""Canonical Campus Coach session execution status helpers."""

from typing import Any, Dict, Optional

STATUS_DONE = 'done'
STATUS_SKIP = 'skip'
STATUS_TODO = 'todo'

_DONE_VALUES = {
    'done', 'fait', 'faite', 'complete', 'completed', 'complétée',
    'completée', 'validée',
}
_SKIP_VALUES = {
    'skip', 'skipped', 'sauté', 'saute', 'sautée', 'ignoré', 'ignorée',
}
_TODO_VALUES = {'todo', 'to do', 'à faire', 'a faire', 'planned', 'pending', ''}


def normalize_status(raw: Optional[str]) -> Optional[str]:
    """Normalize a legacy or provider status to a canonical execution state."""
    if raw is None:
        return None
    value = str(raw).strip().lower()
    if value in _DONE_VALUES:
        return STATUS_DONE
    if value in _SKIP_VALUES:
        return STATUS_SKIP
    if value in _TODO_VALUES:
        return STATUS_TODO
    return None


def effective_status(session: Dict[str, Any]) -> str:
    """Resolve local, matched, and provider execution state in precedence order.

    Precedence: ``local_status`` -> ``matched_activity_id``/``completed_at`` ->
    ``provider_status`` -> ``todo``.

    The raw ``status`` attribute is deliberately NOT consulted. It is a legacy
    field the provider sync never rewrites, so it held mixed, stale values from
    several eras ('todo', 'done', 'skip', 'Fait') and reading it made the coach
    recommend already-done sessions. Its completion information has been migrated
    into ``local_status`` (see ``scripts/migrate_campus_legacy_status.py``); the
    field is dropped so it can no longer mislead a reader. ``normalize_status``
    still recognises the legacy 'Fait'/'done'/'skip' spellings because the
    migration relies on it to read those rows one last time.
    """
    local = normalize_status(session.get('local_status'))
    if local is not None:
        return local

    if session.get('matched_activity_id') or session.get('completed_at'):
        return STATUS_DONE

    provider = normalize_status(session.get('provider_status'))
    if provider is not None:
        return provider
    return STATUS_TODO
