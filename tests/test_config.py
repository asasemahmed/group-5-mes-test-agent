import pytest

from src.config import ConfigError, Settings, load_settings


def test_defaults_load_without_env_file():
    settings = load_settings(env_file=None, environ={})
    assert settings == Settings()
    assert settings.openrouter_api_key is None
    assert settings.llm_model == "z-ai/glm-5.3-flash"
    assert settings.max_agent_retries == 3


def test_env_file_is_read_and_environment_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_TEMPERATURE=0.5\nMAX_AGENT_RETRIES=1\nHEADLESS_MODE=false\n")
    settings = load_settings(env_file=env_file, environ={"MAX_AGENT_RETRIES": "2"})
    assert settings.llm_temperature == 0.5
    assert settings.max_agent_retries == 2
    assert settings.headless_mode is False


def test_public_dict_and_repr_never_contain_the_key():
    key = "sk-or-v1-canary-0000"
    settings = load_settings(env_file=None, environ={"OPENROUTER_API_KEY": key})
    public = settings.public_dict()
    assert "openrouter_api_key" not in public
    assert public["openrouter_api_key_set"] is True
    assert key not in str(public)
    assert key not in repr(settings)


def test_empty_price_means_unknown():
    settings = load_settings(env_file=None, environ={"LLM_PRICE_INPUT_PER_MTOK": ""})
    assert settings.llm_price_input_per_mtok is None


@pytest.mark.parametrize(
    "name, value",
    [
        ("OBSERVATION_MODE", "video"),
        ("MAX_AGENT_RETRIES", "-1"),
        ("AGENT_MAX_STEPS", "0"),
        ("RUN_TIMEOUT_S", "soon"),
        ("HEADLESS_MODE", "maybe"),
        ("LLM_MODEL", " "),
    ],
)
def test_invalid_values_are_refused(name, value):
    with pytest.raises(ConfigError):
        load_settings(env_file=None, environ={name: value})
