import pytest

from config import ConfigError, Settings


@pytest.fixture
def env(tmp_path):
    prompt = tmp_path / "agent.md"
    prompt.write_text("Eres un asistente.\n", encoding="utf-8")
    return {
        "BOT_TOKEN": "token",
        "DEEPGRAM_API_KEY": "dg",
        "ANTHROPIC_API_KEY": "ant",
        "CARTESIA_API_KEY": "car",
        "AGENT_PROMPT_FILE": str(prompt),
    }


def test_defaults(env):
    settings = Settings.from_env(env)

    assert settings.system_prompt == "Eres un asistente."
    assert settings.language == "es"
    assert settings.port == 8765
    assert settings.freeswitch is None


def test_freeswitch_is_enabled_by_its_password(env):
    settings = Settings.from_env(
        env | {"FREESWITCH_ESL_PASSWORD": "pw", "FREESWITCH_ESL_HOST": "fs"}
    )

    assert settings.freeswitch is not None
    assert (settings.freeswitch.esl_host, settings.freeswitch.esl_port) == ("fs", 8021)


def test_every_missing_variable_is_named(env):
    del env["BOT_TOKEN"]
    env["CARTESIA_API_KEY"] = ""

    with pytest.raises(ConfigError, match="BOT_TOKEN, CARTESIA_API_KEY"):
        Settings.from_env(env)


def test_invalid_number(env):
    with pytest.raises(ConfigError, match="Invalid number"):
        Settings.from_env(env | {"PORT": "abc"})


def test_missing_prompt_file(env, tmp_path):
    with pytest.raises(ConfigError, match="system prompt"):
        Settings.from_env(env | {"AGENT_PROMPT_FILE": str(tmp_path / "nope.md")})
