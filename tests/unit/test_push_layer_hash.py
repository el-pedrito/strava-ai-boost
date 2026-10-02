"""The Web Push layer asset hash tracks the layer definition content.

compute_layer_asset_hash() derives the hash from requirements.txt + build_layer.sh
(not a frozen constant, not the filesystem), so:
  * a dependency change (editing requirements.txt or the build script) DOES change the
    hash -> the push layer is republished;
  * identical content yields an identical hash -> no spurious layer replacement from
    metadata churn.
"""

import os
import sys

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, REPO_ROOT)

from stacks.layer_hash import compute_layer_asset_hash  # noqa: E402

LAYER_DIR = os.path.join(REPO_ROOT, "lambda_layer_push")
SHARED_LAYER_DIR = os.path.join(REPO_ROOT, "lambda_layer")


def _write_layer(tmp_path, requirements: str, build: str):
    (tmp_path / "requirements.txt").write_text(requirements)
    (tmp_path / "build_layer.sh").write_text(build)
    return str(tmp_path)


def test_hash_is_deterministic_for_same_content(tmp_path):
    d = _write_layer(tmp_path, "requests>=2.31.0\npywebpush>=1.14.0\n", "#!/bin/bash\npip install\n")
    assert compute_layer_asset_hash(d) == compute_layer_asset_hash(d)


def test_requirements_change_changes_hash(tmp_path):
    build = "#!/bin/bash\npip install\n"
    da = tmp_path / "a"
    db = tmp_path / "b"
    da.mkdir()
    db.mkdir()
    _write_layer(da, "requests>=2.31.0\n", build)
    _write_layer(db, "requests>=2.31.0\npywebpush>=1.14.0\n", build)
    assert compute_layer_asset_hash(str(da)) != compute_layer_asset_hash(str(db))


def test_build_script_change_changes_hash(tmp_path):
    reqs = "requests>=2.31.0\n"
    da = tmp_path / "a"
    db = tmp_path / "b"
    da.mkdir()
    db.mkdir()
    _write_layer(da, reqs, "#!/bin/bash\npip install\n")
    _write_layer(db, reqs, "#!/bin/bash\npip install --platform manylinux2014_x86_64\n")
    assert compute_layer_asset_hash(str(da)) != compute_layer_asset_hash(str(db))


def test_real_requirements_includes_pywebpush():
    with open(os.path.join(LAYER_DIR, "requirements.txt")) as fh:
        assert "pywebpush" in fh.read()


def test_real_layer_hash_computes():
    # The actual repo layer definition must hash without error.
    assert len(compute_layer_asset_hash(LAYER_DIR)) == 64


def test_shared_layer_does_not_carry_pywebpush():
    """pywebpush lives in the push-only layer: the shared layer exported by Core is
    never replaced by this feature (cross-stack export constraint)."""
    with open(os.path.join(SHARED_LAYER_DIR, "requirements.txt")) as fh:
        assert "pywebpush" not in fh.read()
