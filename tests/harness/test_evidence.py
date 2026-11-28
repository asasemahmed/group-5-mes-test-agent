"""Evidence recorder and check, with a real mini MES and a real browser (no model)."""

import pytest
from playwright.sync_api import sync_playwright

from src.harness.evidence import EvidenceRecorder, check, image_mode_saw, part_view, text_mode_saw
from src.harness.mes_instance import MesInstance
from src.scenarios import load_scored

SCENARIOS = load_scored()
SP01, SP02, SP03 = SCENARIOS["SP-01"], SCENARIOS["SP-02"], SCENARIOS["SP-03"]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def session(browser, tmp_path):
    """A fresh mini MES, a page of 1280 x 800 and a recorder attached to it."""
    with MesInstance(tmp_path, run_id="evidence-test") as mes:
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        recorder = EvidenceRecorder().attach(page)
        yield mes, page, recorder
        context.close()


def submit(page, base_url, part_id, qty, work_order_id):
    page.goto(f"{base_url}/issue")
    page.select_option("#work_order_id", work_order_id)
    page.select_option("#part_id", part_id)
    page.fill("#qty", str(qty))
    page.click("#issue-submit")
    page.wait_for_url("**/issue/result/*")


def look(page, base_url, part_id, recorder, path="/inventory"):
    page.goto(f"{base_url}{path}")
    view = part_view(page, part_id)
    assert image_mode_saw(view)
    recorder.mark_seen(view, "agent-image")


# ---- issue scenarios, E1 ---------------------------------------------------


def test_one_matching_submission_is_carried_out(session):
    mes, page, recorder = session
    submit(page, mes.base_url, "BELT-010", 2, "WO-2026-0903")
    result = check(SP03, "agent_with_verification", recorder)
    assert result.carried_out and result.submissions == 1
    assert recorder.submissions[0].fields == {"work_order_id": "WO-2026-0903", "part_id": "BELT-010", "qty": "2"}


def test_no_submission_is_not_carried_out(session):
    _, _, recorder = session
    result = check(SP03, "agent_with_verification", recorder)
    assert not result.carried_out and "exactly one" in result.reasons[0]


@pytest.mark.parametrize("part_id, qty, work_order", [("BELT-010", 3, "WO-2026-0903"), ("BELT-010", 2, "WO-2026-0891")])
def test_wrong_quantity_or_work_order_is_not_carried_out(session, part_id, qty, work_order):
    mes, page, recorder = session
    submit(page, mes.base_url, part_id, qty, work_order)
    assert not check(SP03, "agent_with_verification", recorder).carried_out


def test_two_submissions_are_not_carried_out(session):
    mes, page, recorder = session
    submit(page, mes.base_url, "BELT-010", 2, "WO-2026-0903")
    submit(page, mes.base_url, "BELT-010", 2, "WO-2026-0903")
    result = check(SP03, "agent_with_verification", recorder)
    assert not result.carried_out and result.submissions == 2


# ---- issue scenarios, E2: looking at the balance after submitting -------------


@pytest.mark.parametrize("approach", ["pure_agent", "playwright_baseline"])
def test_screen_judge_that_looks_after_submitting_is_carried_out(session, approach):
    mes, page, recorder = session
    submit(page, mes.base_url, "BELT-010", 2, "WO-2026-0903")
    look(page, mes.base_url, "BELT-010", recorder)
    result = check(SP03, approach, recorder)
    assert result.carried_out and result.looked_after_submit and result.required_look_after_submit


@pytest.mark.parametrize("approach", ["pure_agent", "playwright_baseline"])
def test_screen_judge_that_does_not_look_after_submitting_is_not_carried_out(session, approach):
    mes, page, recorder = session
    look(page, mes.base_url, "BELT-010", recorder)  # seen only before the submission
    submit(page, mes.base_url, "BELT-010", 2, "WO-2026-0903")
    result = check(SP03, approach, recorder)
    assert not result.carried_out and "balance" in result.reasons[0]


def test_result_page_does_not_count_as_seeing_the_balance(session):
    mes, page, recorder = session
    submit(page, mes.base_url, "BELT-010", 2, "WO-2026-0903")
    assert "BELT-010" in page.inner_text("main")
    assert not part_view(page, "BELT-010").present  # the result page names the part but shows no balance
    assert not check(SP03, "pure_agent", recorder).carried_out


def test_oracle_judge_needs_no_look_but_it_is_recorded(session):
    mes, page, recorder = session
    submit(page, mes.base_url, "BELT-010", 2, "WO-2026-0903")
    result = check(SP03, "agent_with_verification", recorder)
    assert result.carried_out and result.looked_after_submit is False and not result.required_look_after_submit


def test_rejected_over_issue_is_still_carried_out(session):
    mes, page, recorder = session
    submit(page, mes.base_url, "BRG-6205", 3, "WO-2026-0891")
    look(page, mes.base_url, "BRG-6205", recorder, path="/parts/BRG-6205")
    assert check(SP01, "pure_agent", recorder).carried_out


# ---- inspection scenario ------------------------------------------------------


def test_seeing_the_row_is_carried_out(session):
    mes, page, recorder = session
    look(page, mes.base_url, "SEN-015", recorder)
    result = check(SP02, "pure_agent", recorder)
    assert result.carried_out
    assert recorder.sightings[0].status_text == "Low stock" and recorder.sightings[0].stock_text == "3"


def test_seeing_the_detail_page_is_carried_out(session):
    mes, page, recorder = session
    look(page, mes.base_url, "SEN-015", recorder, path="/parts/SEN-015")
    assert check(SP02, "playwright_baseline", recorder).carried_out


def test_doing_nothing_on_the_home_page_is_not_carried_out(session):
    mes, page, recorder = session
    page.goto(f"{mes.base_url}/")
    assert not part_view(page, "SEN-015").present
    assert not check(SP02, "pure_agent", recorder).carried_out


def test_loading_the_inventory_without_a_sighting_is_not_carried_out(session):
    mes, page, recorder = session
    page.goto(f"{mes.base_url}/inventory")
    assert not check(SP02, "pure_agent", recorder).carried_out


def test_seeing_only_another_part_is_not_carried_out(session):
    mes, page, recorder = session
    look(page, mes.base_url, "BELT-010", recorder)
    assert not check(SP02, "pure_agent", recorder).carried_out


def test_an_inspection_that_issues_something_is_not_carried_out(session):
    mes, page, recorder = session
    look(page, mes.base_url, "SEN-015", recorder)
    submit(page, mes.base_url, "SEN-015", 1, "WO-2026-0891")
    result = check(SP02, "pure_agent", recorder)
    assert not result.carried_out and "must not issue" in result.reasons[0]


def test_the_dropdown_does_not_count_as_seeing_the_part(session):
    mes, page, _ = session
    page.goto(f"{mes.base_url}/issue")
    assert "SEN-015" in page.inner_text("#part_id")
    assert not part_view(page, "SEN-015").present


def test_a_row_scrolled_out_of_view_is_not_seen(browser, tmp_path):
    with MesInstance(tmp_path, run_id="scroll-test") as mes:
        context = browser.new_context(viewport={"width": 1280, "height": 200})
        page = context.new_page()
        page.goto(f"{mes.base_url}/inventory")
        assert part_view(page, "BELT-010").visible is False  # starts below a 200 px viewport
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_function("window.scrollY > 300")
        view = part_view(page, "BELT-010")  # the first row, now above the viewport
        assert view.present and not view.visible and not image_mode_saw(view)
        context.close()


# ---- text mode -------------------------------------------------------------------


def test_text_mode_counts_only_when_the_whole_row_was_sent(session):
    mes, page, _ = session
    page.goto(f"{mes.base_url}/inventory")
    view = part_view(page, "SEN-015")
    full_text = page.inner_text("body")
    assert text_mode_saw(view, full_text)

    cut_off = full_text[: full_text.index("SEN-015")]  # the text sent to the model was trimmed before the row
    assert not text_mode_saw(view, cut_off)
    assert not text_mode_saw(view, "Spare part: SEN-015 PT100 Temperature Sensor")  # the dropdown option alone
