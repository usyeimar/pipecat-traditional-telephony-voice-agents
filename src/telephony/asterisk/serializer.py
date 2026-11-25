"""Pipecat frame serializer for Asterisk's chan_websocket."""

import asyncio
import time

from loguru import logger
from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.audio.utils import scale_audio
from pipecat.frames.frames import (
    AudioRawFrame,
    CancelFrame,
    EndFrame,
    Frame,
    InputAudioRawFrame,
    InputDTMFFrame,
    InterruptionFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer

from telephony.asterisk import protocol

BYTES_PER_SAMPLE = 2  # 16-bit mono
# Added to the estimated end of playback before hanging up, for the trip to Asterisk.
HANG_UP_MARGIN_SECS = 0.1
# Longest wait for playback before hanging up, whatever the estimate says.
MAX_HANG_UP_WAIT_SECS = 5.0


class AsteriskFrameSerializer(FrameSerializer):
    """Converts between Pipecat frames and the chan_websocket protocol.

    Meant for ``FastAPIWebsocketTransport``, which sends the bot's audio at real time. Asterisk
    queues what it receives and plays one frame per packet interval, so at that pace its queue
    stays nearly empty and an interruption has almost nothing to flush.

    Asterisk to Pipecat:

    - binary message: caller audio, as ``InputAudioRawFrame``
    - ``DTMF_END``: a keypad press, as ``InputDTMFFrame``

    Pipecat to Asterisk:

    - audio frame: binary message with the samples
    - ``InterruptionFrame``: ``FLUSH_MEDIA``, dropping audio queued in Asterisk
    - ``EndFrame``: ``HANGUP``, once the audio already sent has had time to play, so the
      goodbye is not cut short
    - ``CancelFrame``: ``HANGUP``, right away

    Asterisk drops the end of any audio message whose length is not a multiple of its frame
    size. Set the transport's ``fixed_audio_packet_size`` to ``MediaStart.optimal_frame_size``
    so every message is exactly one frame.
    """

    class InputParams(FrameSerializer.InputParams):
        """Configuration of AsteriskFrameSerializer.

        Parameters:
            audio_in_sample_rate: Rate of the audio Asterisk sends, per the codec in the dial
                string: 8000 for ``c(slin)``, 16000 for ``c(slin16)``.
            audio_out_sample_rate: Rate of the audio sent to Asterisk; the same codec.
            output_gain_db: Gain applied to the bot's audio, in dB (negative to attenuate).
                TTS services deliver speech far louder than telephone level.
            auto_hang_up: Whether to hang up the call on ``EndFrame`` or ``CancelFrame``.
        """

        audio_in_sample_rate: int = 8000
        audio_out_sample_rate: int = 8000
        output_gain_db: float = 0.0
        auto_hang_up: bool = True

    def __init__(self, params: InputParams | None = None):
        params = params or AsteriskFrameSerializer.InputParams()
        super().__init__(params)
        self._params: AsteriskFrameSerializer.InputParams = params
        self._output_gain = 10 ** (params.output_gain_db / 20)
        self._hangup_sent = False
        # When Asterisk will have played all the audio sent so far (time.monotonic()).
        self._playout_end = 0.0

    async def serialize(self, frame: Frame) -> str | bytes | None:
        """Convert a Pipecat frame to a message for Asterisk, or None if it has none."""
        if isinstance(frame, (EndFrame, CancelFrame)):
            if not self._params.auto_hang_up or self._hangup_sent:
                return None
            self._hangup_sent = True
            if isinstance(frame, EndFrame):
                await self._wait_for_playout()
            return protocol.command(protocol.HANGUP)

        if isinstance(frame, InterruptionFrame):
            await self._reset_audio_out()
            self._playout_end = 0.0
            return protocol.command(protocol.FLUSH_MEDIA)

        if isinstance(frame, AudioRawFrame):
            audio = await self._resample_audio_out(frame)
            if not audio:
                return None
            if self._output_gain != 1.0:
                audio = scale_audio(audio, self._output_gain)
            self._track_playout(len(audio))
            return audio

        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        """Convert a message from Asterisk to a Pipecat frame, or None if it maps to none."""
        if isinstance(data, bytes):
            audio = await self._resample_audio_in(data)
            if not audio:
                return None
            return InputAudioRawFrame(audio=audio, num_channels=1, sample_rate=self._sample_rate)

        try:
            event = protocol.parse_event(data)
        except protocol.ProtocolError as e:
            logger.warning(f"{self}: ignoring text message, {e}")
            return None

        name = event["event"]
        if name == protocol.DTMF_END:
            return self._dtmf_frame(event.get("digit"))
        if name == protocol.MEDIA_XOFF:
            # Unexpected at real-time pace: it means ~18 s of audio are queued in Asterisk.
            logger.warning(f"{self}: Asterisk's audio queue is full, bot audio is being dropped")
        else:
            logger.debug(f"{self}: {name} event")
        return None

    def _track_playout(self, num_bytes: int) -> None:
        """Account for audio about to be sent: Asterisk plays it after what it already holds."""
        duration = num_bytes / (BYTES_PER_SAMPLE * self._params.audio_out_sample_rate)
        self._playout_end = max(self._playout_end, time.monotonic()) + duration

    async def _wait_for_playout(self) -> None:
        """Sleep until Asterisk has played the audio sent so far.

        HANGUP takes effect at once and drops what Asterisk still has queued. The transport
        sends audio at real time, so this is normally the last chunk plus the margin.
        """
        remaining = self._playout_end - time.monotonic()
        if remaining > -HANG_UP_MARGIN_SECS:
            await asyncio.sleep(min(remaining + HANG_UP_MARGIN_SECS, MAX_HANG_UP_WAIT_SECS))

    def _dtmf_frame(self, digit: object) -> InputDTMFFrame | None:
        try:
            return InputDTMFFrame(KeypadEntry(digit))
        except ValueError:
            # A-D exist in RFC 4733 but not on phone keypads, nor in KeypadEntry.
            logger.debug(f"{self}: ignoring DTMF digit {digit!r}")
            return None
