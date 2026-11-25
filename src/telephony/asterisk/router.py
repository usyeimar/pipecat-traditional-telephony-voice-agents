"""WebSocket endpoint Asterisk connects to, one connection per call."""

import asyncio

from fastapi import APIRouter, WebSocket
from loguru import logger
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from starlette.websockets import WebSocketDisconnect

from agent import CallSession, run_call
from config import Settings
from telephony.asterisk import protocol
from telephony.asterisk.serializer import AsteriskFrameSerializer
from telephony.auth import POLICY_VIOLATION, reject_unauthorized

# The WebSocket subprotocol chan_websocket asks for (protocols = media in websocket_client.conf).
SUBPROTOCOL = "media"
# The rates Silero VAD accepts: c(slin) and c(slin16) in the dial string.
SUPPORTED_SAMPLE_RATES = (8000, 16000)
# Asterisk sends MEDIA_START right after the handshake.
MEDIA_START_TIMEOUT_SECS = 5


def create_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/asterisk")
    async def asterisk_call(websocket: WebSocket):
        """Handle one call."""
        if await reject_unauthorized(websocket, settings.bot_token):
            return
        offered = websocket.scope.get("subprotocols", [])
        await websocket.accept(subprotocol=SUBPROTOCOL if SUBPROTOCOL in offered else None)

        media = await _receive_media_start(websocket)
        if media is None:
            return

        serializer = AsteriskFrameSerializer(
            AsteriskFrameSerializer.InputParams(
                audio_in_sample_rate=media.sample_rate,
                audio_out_sample_rate=media.sample_rate,
                output_gain_db=settings.output_gain_db,
            )
        )
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                # Exactly one Asterisk frame per message: it drops what does not fill a frame.
                fixed_audio_packet_size=media.optimal_frame_size,
                # No trailing silence: the serializer waits for playback before hanging up.
                audio_out_end_silence_secs=0,
                serializer=serializer,
            ),
        )

        await run_call(
            CallSession(
                call_id=media.channel_id,
                transport=transport,
                sample_rate=media.sample_rate,
                # Set by v(caller=...) in the dial string.
                caller=websocket.query_params.get("caller"),
            ),
            settings,
        )

    return router


async def _receive_media_start(websocket: WebSocket) -> protocol.MediaStart | None:
    """Read and check the MEDIA_START event. On failure, hang up and return None."""
    try:
        text = await asyncio.wait_for(websocket.receive_text(), MEDIA_START_TIMEOUT_SECS)
        media = protocol.MediaStart.parse(text)
        if media.sample_rate not in SUPPORTED_SAMPLE_RATES:
            raise protocol.ProtocolError(
                f"unsupported audio format {media.audio_format!r}: use c(slin) or c(slin16) "
                "in the dial string"
            )
        return media
    except WebSocketDisconnect:
        logger.info("Asterisk closed the connection before the call started")
        return None
    except (TimeoutError, KeyError, protocol.ProtocolError) as e:
        # KeyError: the first message was audio, not text.
        logger.error(f"Rejected Asterisk call: {e or type(e).__name__}")
        await websocket.send_text(protocol.command(protocol.HANGUP))
        await websocket.close(code=POLICY_VIOLATION)
        return None
