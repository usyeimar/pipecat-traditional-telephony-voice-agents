"""The speech and language services of the pipeline.

To use another provider, change the builder here; nothing else depends on which one it is.
"""

from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService

from config import Settings


def build_stt(settings: Settings) -> DeepgramSTTService:
    """Speech-to-text: Deepgram, streaming."""
    return DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        settings=DeepgramSTTService.Settings(language=settings.language),
    )


def build_llm(settings: Settings) -> AnthropicLLMService:
    """The LLM: Claude."""
    return AnthropicLLMService(
        api_key=settings.anthropic_api_key,
        settings=AnthropicLLMService.Settings(
            model=settings.llm_model,
            system_instruction=settings.system_prompt,
            effort=settings.llm_effort,
            max_tokens=settings.llm_max_tokens,
            # The system prompt and tools are the same on every turn of every call.
            enable_prompt_caching=True,
        ),
    )


def build_tts(settings: Settings) -> CartesiaTTSService:
    """Text-to-speech: Cartesia, at the pipeline's output rate."""
    return CartesiaTTSService(
        api_key=settings.cartesia_api_key,
        settings=CartesiaTTSService.Settings(
            voice=settings.cartesia_voice_id,
            language=settings.language,
        ),
    )
