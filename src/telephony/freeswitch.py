"""FreeSWITCH adapter, over mod_audio_stream.

    caller --SIP/RTP--> FreeSWITCH --mod_audio_stream (WebSocket)--> bot
                            ^                                         |
                            +--------- event socket (ESL) ------------+

The open source mod_audio_stream streams the caller's audio but cannot play audio back: it writes
what the bot sends to files. pipecat-freeswitch therefore drives the call over the event socket:
it plays those files, stops them when the caller barges in, hangs up, and forwards keypad presses
(DTMF). Dialplan: freeswitch/conf/dialplan/default.xml.
"""

from fastapi import APIRouter, WebSocket
from loguru import logger
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat_freeswitch import FreeSWITCHFrameSerializer
from pipecat_freeswitch.control import is_valid_uuid

from agent import CallSession, run_call
from config import FreeSwitchSettings, Settings
from telephony.auth import POLICY_VIOLATION, reject_unauthorized

# G.711 calls: 8 kHz in both directions, matching "mono 8k" in the dialplan and the channel's
# codec, so neither the bot nor FreeSWITCH resamples anything.
SAMPLE_RATE = 8000
# First block of each utterance sent to FreeSWITCH. Later blocks grow by themselves (lookahead).
FIRST_BLOCK_MS = 200


def create_router(settings: Settings, freeswitch: FreeSwitchSettings) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/freeswitch")
    async def freeswitch_call(websocket: WebSocket):
        """Handle one call."""
        if await reject_unauthorized(websocket, settings.bot_token):
            return
        await websocket.accept()

        # mod_audio_stream sends its metadata (the channel UUID, per the dialplan) before any
        # audio. The UUID goes into event socket commands, so only a canonical one is accepted.
        call_uuid = (await websocket.receive_text()).strip()
        if not is_valid_uuid(call_uuid):
            logger.error(f"Expected the channel UUID as the first message, got {call_uuid[:80]!r}")
            await websocket.close(code=POLICY_VIOLATION)
            return

        serializer = FreeSWITCHFrameSerializer(
            call_uuid=call_uuid,
            esl_host=freeswitch.esl_host,
            esl_port=freeswitch.esl_port,
            esl_password=freeswitch.esl_password,
            params=FreeSWITCHFrameSerializer.InputParams(
                freeswitch_sample_rate=SAMPLE_RATE,
                output_gain_db=settings.output_gain_db,
            ),
        )
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                audio_out_10ms_chunks=FIRST_BLOCK_MS // 10,
                # No trailing silence: the serializer waits for playback before hanging up.
                audio_out_end_silence_secs=0,
                serializer=serializer,
            ),
        )

        await run_call(
            CallSession(
                call_id=call_uuid,
                transport=transport,
                sample_rate=SAMPLE_RATE,
                caller=websocket.query_params.get("caller"),
                # Right before the output: speech reaches FreeSWITCH ahead of real time, in a
                # few large blocks. Each playback that starts costs ~35 ms of caller audio, so
                # many small blocks would leave the bot deaf to barge-in.
                pre_output=[serializer.lookahead()],
                # A closed WebSocket keeps the pipeline's CancelFrame from reaching the
                # serializer, so the hang-up and the event socket are settled here.
                on_disconnect=serializer.cleanup,
            ),
            settings,
        )

    return router
