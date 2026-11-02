"""LLM planner: turns a natural-language test goal into a list of GUI steps."""

from dataclasses import dataclass


@dataclass
class Step:
    action: str  # e.g. "click", "type", "check"
    target: str  # what the step acts on, described in plain words
    value: str = ""


class Planner:
    def __init__(self, model: str):
        self.model = model

    def plan(self, goal: str) -> list[Step]:
        """Ask the LLM to break the goal into steps."""
        # TODO: call the LLM provider set in .env and parse its answer into steps.
        raise NotImplementedError
