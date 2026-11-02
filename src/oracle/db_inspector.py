"""Database oracle: reads the true stock balance straight from the MES database."""

import os


class DbInspector:
    def __init__(self, connection_url: str | None = None):
        self.connection_url = connection_url or os.getenv("MES_DB_CONNECTION")

    def stock_of(self, part_id: str) -> int:
        """Return the on-hand stock of a part from the database."""
        # TODO: SELECT stock_qty FROM inventory WHERE part_id = %s
        raise NotImplementedError
