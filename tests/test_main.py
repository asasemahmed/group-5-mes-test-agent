from src.main import Inventory, run_scenarios


def test_catalog_loads():
    inv = Inventory.from_csv()
    assert "BRG-6205" in inv.parts


def test_all_scenarios_pass():
    assert all(run_scenarios().values())
