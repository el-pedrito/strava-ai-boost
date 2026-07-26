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
    """Resolve local, legacy, matched, and provider state in precedence order."""
    local = normalize_status(session.get('local_status'))
    if local is not None:
        return local

    legacy = normalize_status(session.get('status'))
    if legacy in (STATUS_DONE, STATUS_SKIP):
        return legacy

    if session.get('matched_activity_id') or session.get('completed_at'):
        return STATUS_DONE

    provider = normalize_status(session.get('provider_status'))
    if provider is not None:
        return provider
    return STATUS_TODO
