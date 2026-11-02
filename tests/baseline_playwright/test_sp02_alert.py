"""SP-02 baseline: SEN-015 shows a low-stock warning."""

import pytest

pytest.importorskip("playwright")


@pytest.mark.skip(reason="Needs a running OpenMES instance")
def test_sp02_alert():
    # TODO: scripted Playwright steps against MES_BASE_URL.
    pass
