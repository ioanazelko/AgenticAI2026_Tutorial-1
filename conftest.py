"""pytest configuration. Being at the rootdir, this file also puts book/code on sys.path."""

import pytest


@pytest.fixture(autouse=True)
def _snapshot_registry(monkeypatch):
    """Run every test against the bundled snapshot, even when REGISTRY_DIR points at
    a full clone: several tests check the snapshot's numbers."""
    from agentbook.registry import SNAPSHOT_DIR, _registry_for
    monkeypatch.setenv("REGISTRY_DIR", str(SNAPSHOT_DIR))
    _registry_for.cache_clear()
    yield
    _registry_for.cache_clear()
