"""Self-correction: retries a failed step a bounded number of times."""

import os

MAX_RETRIES = int(os.getenv("MAX_AGENT_RETRIES", "3"))


def with_retries(func, *args, retries: int = MAX_RETRIES):
    """Call func, retrying on error up to `retries` times."""
    last_error = None
    for _ in range(retries):
        try:
            return func(*args)
        except Exception as error:  # any step failure is retried
            last_error = error
    raise last_error
