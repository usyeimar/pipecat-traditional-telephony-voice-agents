"""Settings read from the environment (see .env.example)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PROMPT_FILE = "prompts/agent.md"
# A multilingual Cartesia voice. Pick one that speaks AGENT_LANGUAGE natively.
DEFAULT_CARTESIA_VOICE_ID = "71a7ad14-091c-4e8e-a314-022ece01c121"


class ConfigError(RuntimeError):
    """The environment is missing a setting or holds an invalid one."""


@dataclass(frozen=True)
class FreeSwitchSettings:
    """How to reach the FreeSWITCH event socket, which plays the bot's audio and hangs up."""

    esl_host: str
    esl_port: int
    esl_password: str


@dataclass(frozen=True)
class Settings:
    # Shared secret each PBX presents on the WebSocket handshake.
    bot_token: str

    deepgram_api_key: str
    anthropic_api_key: str
    cartesia_api_key: str

    system_prompt: str
    language: str
    llm_model: str
    llm_effort: str
    llm_max_tokens: int
    cartesia_voice_id: str

    # Telephony tuning, with the values pipecat-freeswitch measured on real phones.
    # TTS speech is ~12 dB louder than telephone level: that loud it distorts, and phones' echo
    # suppression mutes the caller while the bot speaks, which defeats barge-in.
    output_gain_db: float
    # Phone audio is much quieter than a desktop microphone; Pipecat's default (0.6) misses
    # barge-ins.
    vad_min_volume: float
    vad_confidence: float

    host: str
    port: int

    # None when FREESWITCH_ESL_PASSWORD is not set: the FreeSWITCH endpoint is then not served.
    freeswitch: FreeSwitchSettings | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Build the settings, failing with every missing variable named at once."""
        env = os.environ if env is None else env

        required = ["BOT_TOKEN", "DEEPGRAM_API_KEY", "ANTHROPIC_API_KEY", "CARTESIA_API_KEY"]
        missing = [name for name in required if not env.get(name)]
        if missing:
            raise ConfigError(f"Set {', '.join(missing)} (see .env.example)")

        prompt_file = Path(env.get("AGENT_PROMPT_FILE") or DEFAULT_PROMPT_FILE)
        try:
            system_prompt = prompt_file.read_text(encoding="utf-8").strip()
        except OSError as e:
            raise ConfigError(f"Cannot read the system prompt {prompt_file}: {e}") from e
        if not system_prompt:
            raise ConfigError(f"The system prompt {prompt_file} is empty")

        try:
            esl_password = env.get("FREESWITCH_ESL_PASSWORD")
            freeswitch = (
                FreeSwitchSettings(
                    esl_host=env.get("FREESWITCH_ESL_HOST") or "127.0.0.1",
                    esl_port=int(env.get("FREESWITCH_ESL_PORT") or 8021),
                    esl_password=esl_password,
                )
                if esl_password
                else None
            )
            return cls(
                bot_token=env["BOT_TOKEN"],
                deepgram_api_key=env["DEEPGRAM_API_KEY"],
                anthropic_api_key=env["ANTHROPIC_API_KEY"],
                cartesia_api_key=env["CARTESIA_API_KEY"],
                system_prompt=system_prompt,
                language=env.get("AGENT_LANGUAGE") or "es",
                llm_model=env.get("LLM_MODEL") or "claude-opus-5-5",
                # Low effort keeps the pause before each answer short, which matters more on a
                # call than depth.
                llm_effort=env.get("LLM_EFFORT") or "low",
                # Room for the model's thinking plus a spoken answer; the prompt is what keeps
                # answers short.
                llm_max_tokens=int(env.get("LLM_MAX_TOKENS") or 2048),
                cartesia_voice_id=env.get("CARTESIA_VOICE_ID") or DEFAULT_CARTESIA_VOICE_ID,
                output_gain_db=float(env.get("OUTPUT_GAIN_DB") or -12),
                vad_min_volume=float(env.get("VAD_MIN_VOLUME") or 0.4),
                vad_confidence=float(env.get("VAD_CONFIDENCE") or 0.7),
                host=env.get("HOST") or "127.0.0.1",
                port=int(env.get("PORT") or 8765),
                freeswitch=freeswitch,
            )
        except ValueError as e:
            raise ConfigError(f"Invalid number in the environment: {e}") from e
