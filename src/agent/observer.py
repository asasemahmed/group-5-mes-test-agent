"""Observer: captures what the agent sees on screen (screenshot and page text)."""

from dataclasses import dataclass


@dataclass
class Observation:
    screenshot_path: str
    page_text: str


class Observer:
    def observe(self, page) -> Observation:
        """Take a screenshot of the Playwright page and read its visible text."""
        # TODO: page.screenshot(...) and page.inner_text("body").
        raise NotImplementedError
