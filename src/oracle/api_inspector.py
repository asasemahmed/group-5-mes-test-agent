"""API oracle: checks MES state through its read-only REST API."""

import os


class ApiInspector:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv("MES_BASE_URL", "http://localhost:8080")

    def part(self, part_id: str) -> dict:
        """Return the part record (stock, reorder flag, ...) from the API."""
        # TODO: GET {base_url}/api/parts/{part_id}
        raise NotImplementedError
