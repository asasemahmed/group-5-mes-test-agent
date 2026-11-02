"""SP-03 baseline: issuing 2 x BELT-010 leaves 8 in stock."""

import pytest

pytest.importorskip("playwright")


@pytest.mark.skip(reason="Needs a running OpenMES instance")
def test_sp03_update():
    # TODO: scripted Playwright steps against MES_BASE_URL.
    pass
