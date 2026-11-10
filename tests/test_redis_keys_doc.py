"""The "Redis keys" table in DATA_MODEL.md is generated from the registry in code; this fails if they differ.

Runs on the host (no Django, no Redis, no database): python -m pytest --noconftest tests/test_redis_keys_doc.py
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "redis_keys_doc.py"
needs_repository = pytest.mark.skipif(
    not (SCRIPT.exists() and (ROOT / "docs" / "DATA_MODEL.md").exists()), reason="the container does not mount docs/"
)


def generator():
    spec = importlib.util.spec_from_file_location("redis_keys_doc", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@needs_repository
def test_the_data_model_table_is_the_one_generated_from_the_registry():
    assert generator().main(["--check"]) == 0, "run python scripts/redis_keys_doc.py"


@needs_repository
def test_every_registry_key_has_a_documented_lifetime_and_invalidation():
    module = generator()
    for key in module.redis_keys.KEYS:
        assert key.ttl and key.invalidated_by and key.purpose and key.pattern
    names = [key.name for key in module.redis_keys.KEYS]
    assert len(names) == len(set(names))
    without_expiry = [key.name for key in module.redis_keys.KEYS if key.ttl.startswith("none")]
    assert without_expiry == ["dashboard_version"]  # the one key that never expires
