"""SP-01 baseline: issuing 3 x BRG-6205 with 2 in stock is rejected."""

import pytest

pytest.importorskip("playwright")


@pytest.mark.skip(reason="Needs a running OpenMES instance")
def test_sp01_stock():
    # TODO: scripted Playwright steps against MES_BASE_URL.
    pass
