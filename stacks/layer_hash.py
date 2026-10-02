"""Content-derived asset hash for a Lambda layer directory."""

import hashlib
import os

LAYER_DEFINITION_FILES = ("requirements.txt", "build_layer.sh")


def compute_layer_asset_hash(layer_dir: str) -> str:
    """Hash the layer DEFINITION (requirements + build script), not the filesystem.

    Identical content gives an identical hash, so macOS xattr/metadata churn never
    republishes the layer. Editing requirements.txt or build_layer.sh changes the
    hash, so a dependency change is actually shipped.
    """
    hasher = hashlib.sha256()
    for name in LAYER_DEFINITION_FILES:
        with open(os.path.join(layer_dir, name), "rb") as fh:
            hasher.update(name.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(fh.read())
            hasher.update(b"\0")
    return hasher.hexdigest()
