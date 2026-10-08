"""Content-derived asset hash for a Lambda layer directory."""

import hashlib
import os

LAYER_DEFINITION_FILES = ("requirements.txt", "build_layer.sh")
BUILT_DIR = "python"


def _built_files(layer_dir: str) -> list[str]:
    """Relative paths of the built layer content, sorted, bytecode excluded."""
    root = os.path.join(layer_dir, BUILT_DIR)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in filenames:
            if name.endswith((".pyc", ".pyo")) or name == ".DS_Store":
                continue
            out.append(os.path.relpath(os.path.join(dirpath, name), layer_dir))
    return sorted(out)


def compute_layer_asset_hash(layer_dir: str) -> str:
    """Hash the layer definition AND its built content, from file bytes only.

    Covers requirements.txt, build_layer.sh and every file under ``python/``, so a
    dependency change or a rebuild (including an empty or partial one) changes the
    hash and republishes the layer, while filesystem metadata (macOS xattrs, mtimes)
    never does.
    """
    hasher = hashlib.sha256()
    rel_paths = list(LAYER_DEFINITION_FILES) + _built_files(layer_dir)
    for rel in rel_paths:
        with open(os.path.join(layer_dir, rel), "rb") as fh:
            hasher.update(rel.replace(os.sep, "/").encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(fh.read())
            hasher.update(b"\0")
    return hasher.hexdigest()
