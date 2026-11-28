"""Execution evidence: was the test actually carried out? (design sections 6.2 and 6.5)

The recorder watches the tester's browser page, independently of the mini MES:
  - every POST /issue the browser sends, with its form fields;
  - every time the tester *saw* the scenario's part.

What counts as seeing a part (settles review points 1 and 2 of design section 16):
only the part's inventory row or its detail section, both of which show the stock
and the warning state. The part's name in the issue form's dropdown, or on the
result page, does not count.
  - image mode: the row or detail section was fully inside the viewport of the
    screenshot that was sent to the model (`image_mode_saw`);
  - text mode: the row's or section's whole text, stock and status included, is
    inside the text that was sent (`text_mode_saw`);
  - a script: it read the row through the baseline's row helper.
The caller decides and calls `mark_seen`; loading a page alone never counts.

Required evidence (`check`):
  issue scenario    E1 exactly one POST /issue, with the scenario's part, quantity and
                       work order;
                    E2 for approaches whose judge reads the screen: after that
                       submission the tester saw the part again (so it saw the balance).
  inspect scenario  no POST /issue, and the tester saw the part at least once.
"""

import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import parse_qs, urlparse

SCREEN_JUDGE_APPROACHES = ("playwright_baseline", "pure_agent")

# Runs in the page: finds the part's row or detail section and reports what is visible.
_PART_VIEW_JS = """
(partId) => {
  const el = document.querySelector(`[data-testid="part-row-${partId}"]`)
          || document.querySelector(`[data-testid="part-detail-${partId}"]`);
  if (!el) return null;
  const kind = el.matches('[data-testid^="part-row-"]') ? 'row' : 'detail';
  const r = el.getBoundingClientRect();
  const inViewport = r.width > 0 && r.height > 0 && r.top >= 0 && r.left >= 0
                  && r.bottom <= window.innerHeight && r.right <= window.innerWidth;
  const rendered = typeof el.checkVisibility === 'function' ? el.checkVisibility() : true;
  const stock = el.querySelector(`[data-testid="stock-${partId}"]`);
  const status = el.querySelector('.badge');
  return {
    kind,
    visible: inViewport && rendered,
    stock_text: stock ? stock.innerText.trim() : '',
    status_text: status ? status.innerText.trim() : '',
    text: el.innerText,
  };
}
"""


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


@dataclass(frozen=True)
class PartView:
    part_id: str
    kind: str | None = None        # "row", "detail" or None when the page has neither
    visible: bool = False          # fully inside the viewport and rendered
    stock_text: str = ""
    status_text: str = ""
    text: str = ""

    @property
    def present(self) -> bool:
        return self.kind is not None


def part_view(page, part_id: str) -> PartView:
    """How the part's row or detail section appears on the current page."""
    data = page.evaluate(_PART_VIEW_JS, part_id)
    return PartView(part_id=part_id, **data) if data else PartView(part_id=part_id)


def image_mode_saw(view: PartView) -> bool:
    return view.present and view.visible and bool(view.stock_text) and bool(view.status_text)


def text_mode_saw(view: PartView, sent_text: str) -> bool:
    """The whole row or section, stock and status included, is inside the text sent to the model."""
    if not (view.present and view.stock_text and view.status_text):
        return False
    return _normalise(view.text) in _normalise(sent_text)


@dataclass(frozen=True)
class Submission:
    time: float
    fields: dict


@dataclass(frozen=True)
class Sighting:
    time: float
    part_id: str
    source: str        # "agent-image", "agent-text" or "script"
    kind: str
    stock_text: str
    status_text: str


class EvidenceRecorder:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self.submissions: list[Submission] = []
        self.sightings: list[Sighting] = []

    def attach(self, page) -> "EvidenceRecorder":
        page.on("request", self._on_request)
        return self

    def _on_request(self, request) -> None:
        if request.method == "POST" and urlparse(request.url).path == "/issue":
            form = parse_qs(request.post_data or "", keep_blank_values=True)
            self.submissions.append(Submission(self._clock(), {k: v[0] for k, v in form.items()}))

    def mark_seen(self, view: PartView, source: str) -> None:
        """Record that the tester saw the part. The caller has checked it (see module doc)."""
        if not view.present:
            raise ValueError(f"{view.part_id} is not on the page, so it cannot have been seen")
        self.sightings.append(Sighting(self._clock(), view.part_id, source, view.kind, view.stock_text, view.status_text))

    def to_dict(self) -> dict:
        return {"submissions": [asdict(s) for s in self.submissions], "sightings": [asdict(s) for s in self.sightings]}


@dataclass
class EvidenceResult:
    carried_out: bool
    reasons: list[str] = field(default_factory=list)
    submissions: int = 0
    saw_part: bool = False
    looked_after_submit: bool | None = None   # issue scenarios only
    required_look_after_submit: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _matches(fields: dict, action) -> bool:
    try:
        qty = int(str(fields.get("qty", "")).strip())
    except ValueError:
        return False
    return (fields.get("part_id", "").strip() == action.part_id
            and fields.get("work_order_id", "").strip() == action.work_order_id
            and qty == action.qty)


def check(scenario, approach: str, recorder: EvidenceRecorder) -> EvidenceResult:
    action = scenario.action
    sightings = [s for s in recorder.sightings if s.part_id == action.part_id]
    result = EvidenceResult(carried_out=False, submissions=len(recorder.submissions), saw_part=bool(sightings))

    if scenario.is_issue:
        result.required_look_after_submit = approach in SCREEN_JUDGE_APPROACHES
        if len(recorder.submissions) != 1:
            result.reasons.append(f"expected exactly one issue submission, saw {len(recorder.submissions)}")
        elif not _matches(recorder.submissions[0].fields, action):
            result.reasons.append(f"the submission {recorder.submissions[0].fields} is not the scenario's issue")
        if recorder.submissions:
            submitted_at = recorder.submissions[0].time
            result.looked_after_submit = any(s.time > submitted_at for s in sightings)
        else:
            result.looked_after_submit = False
        if result.required_look_after_submit and not result.looked_after_submit:
            result.reasons.append("the tester did not look at the part's balance after submitting")
    else:
        if recorder.submissions:
            result.reasons.append(f"an inspection must not issue anything, saw {len(recorder.submissions)} submission(s)")
        if not sightings:
            result.reasons.append(f"the tester never saw {action.part_id}'s row or detail page")

    result.carried_out = not result.reasons
    return result
