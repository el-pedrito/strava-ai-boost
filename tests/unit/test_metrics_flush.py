"""Anti-drift guard: a Lambda that records a metric must also flush it.

WHY this exists: ``metrics.add_metric()`` only appends to an in-memory metric set.
Powertools serialises the EMF blob that CloudWatch turns into a metric ONLY when the
handler is decorated with ``@metrics.log_metrics`` (or ``flush_metrics()`` is called
explicitly). Neither existed anywhere in this repo, so all eight call sites were
inert: ``aws cloudwatch list-metrics --namespace StravaAIBoost`` returned nothing,
and no ``_aws`` EMF blob was ever present in any log group.

That silence was invisible because monitoring_stack.py was removed and the surviving
alarms all watch AWS-native namespaces, so an empty custom namespace looked exactly
like a healthy one. It hid a coach output that stated a figure the code had already
rejected, and it also hid ``WebhookRejectedForeignOrigin`` and
``CoachSummaryMissingUserClaim`` -- both signals you would want to see spike.

The entry points are read from the CDK stacks rather than listed here, so a Lambda
added tomorrow is covered the day it is declared instead of the day somebody notices
its dashboard is empty.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAMBDA_ROOT = REPO_ROOT / "lambda_functions"
STACKS_ROOT = REPO_ROOT / "stacks"

# handler="processing.coach_generator.handler" -> ("processing/coach_generator.py", "handler")
_CDK_HANDLER_RE = re.compile(r'handler="([a-z_]+(?:\.[a-z_]+)+)"')


def _cdk_entry_points() -> dict:
    """Map every CDK-declared Lambda handler to its module path and function name.

    Derived from the stacks so this guard cannot drift from the deployed topology.
    ``index.handler`` is skipped: it belongs to CDK-provided inline/bundled functions
    that have no module in lambda_functions/.
    """
    found = {}
    for stack in sorted(STACKS_ROOT.glob("*.py")):
        for dotted in _CDK_HANDLER_RE.findall(stack.read_text()):
            *module_parts, func = dotted.split(".")
            rel = Path(*module_parts).with_suffix(".py")
            if not (LAMBDA_ROOT / rel).exists():
                continue
            found[str(rel)] = func
    return found


def _iter_module_sources():
    """Every module under lambda_functions/, shared helpers included."""
    for path in sorted(LAMBDA_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _calls_add_metric(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_metric"
        ):
            return True
    return False


def _decorator_names(func: ast.FunctionDef) -> list:
    """Flatten each decorator to a dotted string, ignoring call parentheses."""
    names = []
    for dec in func.decorator_list:
        node = dec.func if isinstance(dec, ast.Call) else dec
        parts = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        names.append(".".join(reversed(parts)))
    return names


def _handler_of(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _is_flushed(rel: str, handler_name: str) -> bool:
    tree = ast.parse((LAMBDA_ROOT / rel).read_text())
    func = _handler_of(tree, handler_name)
    assert func is not None, f"{rel}: no top-level {handler_name}() declared by the CDK stacks"
    return "metrics.log_metrics" in _decorator_names(func)


def _modules_recording_metrics() -> set:
    return {
        str(p.relative_to(LAMBDA_ROOT))
        for p in _iter_module_sources()
        if _calls_add_metric(ast.parse(p.read_text()))
    }


def test_cdk_entry_points_are_discoverable():
    """Guard the guard: a parsing regression here would silently pass everything."""
    entry_points = _cdk_entry_points()
    assert len(entry_points) >= 15, (
        f"only {len(entry_points)} CDK handlers parsed from stacks/ -- the regex or the "
        "stack syntax changed, so the flush checks below are no longer meaningful"
    )
    assert entry_points.get("processing/coach_generator.py") == "handler"
    assert entry_points.get("support/feedback_analyzer.py") == "lambda_handler"


def test_entry_points_recording_metrics_flush_them():
    """A handler that records a metric directly must be decorated to flush it."""
    entry_points = _cdk_entry_points()
    missing = [
        f"{rel}::{handler}"
        for rel, handler in sorted(entry_points.items())
        if rel in _modules_recording_metrics() and not _is_flushed(rel, handler)
    ]
    assert not missing, (
        "these handlers call add_metric but never flush it, so the metric never reaches "
        f"CloudWatch: {missing}. Decorate with @metrics.log_metrics."
    )


def test_metrics_recorded_outside_an_entry_point_force_every_handler_to_flush():
    """A metric recorded in a helper is flushed by whichever handler is running.

    ``metrics`` is a module-level singleton, so ``add_metric`` in a shared helper (or in
    any non-entry-point module) buffers onto the same set -- and is dropped unless the
    handler that happens to call it is decorated. Statically we cannot tell which
    handlers reach that helper, so the only safe invariant is that ALL of them flush.

    No such module exists today, which is why this test is currently vacuous. It is here
    so that adding ``add_metric`` to a helper cannot silently reintroduce the original
    defect: reviewing the six decorated handlers would look sufficient, and would not be.
    """
    entry_points = _cdk_entry_points()
    helpers = sorted(_modules_recording_metrics() - set(entry_points))
    if not helpers:
        return

    undecorated = [
        f"{rel}::{handler}"
        for rel, handler in sorted(entry_points.items())
        if not _is_flushed(rel, handler)
    ]
    assert not undecorated, (
        f"{helpers} record metrics outside a Lambda entry point, so every handler must "
        f"flush or the metric is dropped depending on the caller. Undecorated: {undecorated}"
    )
