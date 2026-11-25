"""Builds and runs the voice pipeline for one call."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.dtmf_aggregator import DTMFAggregator
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner

from agent.services import build_llm, build_stt, build_tts
from agent.tools import TOOLS
from config import Settings

GREETING_INSTRUCTION = (
    "(The call has just been answered. Greet the caller briefly and ask how you can help.)"
)


@dataclass
class CallSession:
    """What a telephony adapter hands over for one call.

    Attributes:
        call_id: The PBX's identifier of the call, for logs.
        transport: The connected transport carrying the call's audio.
        sample_rate: Rate of the call's audio in both directions. The pipeline runs at it, so
            nothing is resampled.
        caller: The caller's number, when the PBX provides it.
        pre_output: Processors the adapter needs right before ``transport.output()``.
        on_disconnect: Called when the PBX closes the connection, to release what the adapter
            holds for the call.
    """

    call_id: str
    transport: BaseTransport
    sample_rate: int = 8000
    caller: str | None = None
    pre_output: Sequence[FrameProcessor] = ()
    on_disconnect: Callable[[], Awaitable[None]] | None = None


async def run_call(session: CallSession, settings: Settings) -> None:
    """Run the conversation until the call ends."""
    transport = session.transport

    context = LLMContext(tools=TOOLS)
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=settings.vad_confidence,
                    min_volume=settings.vad_min_volume,
                )
            )
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            build_stt(settings),
            DTMFAggregator(),  # keypad presses -> "DTMF: 123#" for the LLM
            aggregators.user(),
            build_llm(settings),
            build_tts(settings),
            *session.pre_output,
            transport.output(),
            aggregators.assistant(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=session.sample_rate,
            audio_out_sample_rate=session.sample_rate,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        context.add_message({"role": "user", "content": GREETING_INSTRUCTION})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info(f"Call {session.call_id} disconnected")
        await worker.cancel()
        if session.on_disconnect:
            await session.on_disconnect()

    logger.info(
        f"Call {session.call_id} started (caller {session.caller or 'unknown'}, "
        f"{session.sample_rate} Hz)"
    )
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
