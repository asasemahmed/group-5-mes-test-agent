"""Project settings, read from the environment and the repository's .env file.

Values already set in the environment win over the .env file. The API key is
never part of repr() or public_dict(), so settings can be logged and stored.
"""

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

OBSERVATION_MODES = ("image", "text")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str | None = field(default=None, repr=False)
    llm_model: str = "z-ai/glm-5.3-flash"
    llm_price_input_per_mtok: float | None = 0.15
    llm_price_output_per_mtok: float | None = 0.50
    llm_temperature: float = 0.0
    observation_mode: str = "image"
    max_agent_retries: int = 3
    agent_max_steps: int = 20
    run_timeout_s: int = 180
    headless_mode: bool = True
    benchmark_concurrency: int = 3
    benchmark_repeats: int = 5
    benchmark_max_cost_usd: float = 5.0

    def public_dict(self) -> dict:
        """All settings except the key, plus whether a key is set."""
        data = {f.name: getattr(self, f.name) for f in fields(self) if f.name != "openrouter_api_key"}
        data["openrouter_api_key_set"] = bool(self.openrouter_api_key)
        return data


def _parse_bool(name: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


def _parse_number(name: str, raw: str, kind, minimum):
    try:
        value = kind(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a {kind.__name__}, got {raw!r}") from None
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {value}")
    return value


# setting name -> (environment variable, parser); a parser gets (name, raw text)
_PARSERS = {
    "openrouter_api_key": ("OPENROUTER_API_KEY", lambda n, r: r.strip() or None),
    "llm_model": ("LLM_MODEL", lambda n, r: r.strip()),
    "llm_price_input_per_mtok": ("LLM_PRICE_INPUT_PER_MTOK", lambda n, r: _parse_number(n, r, float, 0) if r.strip() else None),
    "llm_price_output_per_mtok": ("LLM_PRICE_OUTPUT_PER_MTOK", lambda n, r: _parse_number(n, r, float, 0) if r.strip() else None),
    "llm_temperature": ("LLM_TEMPERATURE", lambda n, r: _parse_number(n, r, float, 0)),
    "observation_mode": ("OBSERVATION_MODE", lambda n, r: r.strip().lower()),
    "max_agent_retries": ("MAX_AGENT_RETRIES", lambda n, r: _parse_number(n, r, int, 0)),
    "agent_max_steps": ("AGENT_MAX_STEPS", lambda n, r: _parse_number(n, r, int, 1)),
    "run_timeout_s": ("RUN_TIMEOUT_S", lambda n, r: _parse_number(n, r, int, 1)),
    "headless_mode": ("HEADLESS_MODE", _parse_bool),
    "benchmark_concurrency": ("BENCHMARK_CONCURRENCY", lambda n, r: _parse_number(n, r, int, 1)),
    "benchmark_repeats": ("BENCHMARK_REPEATS", lambda n, r: _parse_number(n, r, int, 1)),
    "benchmark_max_cost_usd": ("BENCHMARK_MAX_COST_USD", lambda n, r: _parse_number(n, r, float, 0)),
}


def load_settings(env_file: Path | None = ENV_FILE, environ: dict | None = None) -> Settings:
    """Read settings from `env_file` (if it exists) and `environ` (default: os.environ).

    Pass env_file=None to ignore any .env file.
    """
    values: dict[str, str] = {}
    if env_file is not None and Path(env_file).is_file():
        values.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    values.update(os.environ if environ is None else environ)

    kwargs = {}
    for name, (env_name, parse) in _PARSERS.items():
        if env_name in values:
            kwargs[name] = parse(env_name, values[env_name])

    settings = Settings(**kwargs)
    if settings.observation_mode not in OBSERVATION_MODES:
        raise ConfigError(f"OBSERVATION_MODE must be one of {OBSERVATION_MODES}, got {settings.observation_mode!r}")
    if not settings.llm_model:
        raise ConfigError("LLM_MODEL must not be empty")
    return settings
