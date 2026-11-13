"""The user manual build (docs/manual/build_manual.py): role tables come from the live catalogue."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path("/docs/manual/build_manual.py")

pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="docs are not mounted")


@pytest.fixture(scope="module")
def manual():
    spec = importlib.util.spec_from_file_location("build_manual", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manual_covers_every_system_role(manual):
    from apps.rbac.catalogue import SYSTEM_ROLES

    assert set(manual.ROLE_KEYS) == set(SYSTEM_ROLES)
    table = manual.capability_table()
    for name in manual.ROLE_NAMES.values():
        assert name in table


def test_generated_tables_follow_the_catalogue(manual):
    from apps.rbac.catalogue import PERMISSIONS

    permissions = manual.permission_table()
    assert all(code in permissions for code in PERMISSIONS)
    assert "Verified" in manual.transitions_table()


def test_manual_builds_a_pdf(manual, tmp_path):
    if not manual.BRAND.exists():
        pytest.skip("brand files are not mounted (set BRAND_DIR)")
    manual.OUT = tmp_path / "manual.pdf"
    manual.build()
    data = manual.OUT.read_bytes()
    assert data.startswith(b"%PDF") and len(data) > 500_000
