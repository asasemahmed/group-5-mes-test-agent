"""Actuator: carries out planned steps in the browser with Playwright."""

from src.agent.planner import Step


class Actuator:
    def __init__(self, page):
        self.page = page

    def execute(self, step: Step) -> None:
        """Perform one step (click, type, ...) on the page."""
        # TODO: map step.action to Playwright calls.
        raise NotImplementedError
