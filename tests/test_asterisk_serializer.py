import json
import struct
from types import SimpleNamespace

import pytest
from pipecat.audio.dtmf.types import KeypadEntry
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    InputAudioRawFrame,
    InputDTMFFrame,
    InterruptionFrame,
    OutputAudioRawFrame,
    TextFrame,
)

from telephony.asterisk import AsteriskFrameSerializer


async def make_serializer(rate: int = 8000, **params) -> AsteriskFrameSerializer:
    serializer = AsteriskFrameSerializer(
        AsteriskFrameSerializer.InputParams(
            audio_in_sample_rate=rate, audio_out_sample_rate=rate, **params
        )
    )
    # The transport sets the serializer up with the pipeline's rates.
    await serializer.setup(SimpleNamespace(audio_in_sample_rate=rate, audio_out_sample_rate=rate))
    return serializer


def pcm(*samples: int) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


def event(name: str, **fields) -> str:
    return json.dumps({"event": name, **fields})


async def test_caller_audio_becomes_an_input_frame():
    serializer = await make_serializer()
    audio = pcm(*range(160))

    frame = await serializer.deserialize(audio)

    assert isinstance(frame, InputAudioRawFrame)
    assert frame.audio == audio
    assert frame.sample_rate == 8000
    assert frame.num_channels == 1


async def test_bot_audio_is_sent_as_is_at_the_same_rate():
    serializer = await make_serializer()
    audio = pcm(*range(160))

    payload = await serializer.serialize(
        OutputAudioRawFrame(audio, sample_rate=8000, num_channels=1)
    )

    assert payload == audio


async def test_output_gain_attenuates_bot_audio():
    serializer = await make_serializer(output_gain_db=-6.0206)  # half the amplitude

    payload = await serializer.serialize(
        OutputAudioRawFrame(pcm(1000, -2000), sample_rate=8000, num_channels=1)
    )

    assert struct.unpack("<2h", payload) == pytest.approx((500, -1000), abs=1)


async def test_interruption_flushes_asterisk_queue():
    serializer = await make_serializer()

    payload = await serializer.serialize(InterruptionFrame())

    assert json.loads(payload) == {"command": "FLUSH_MEDIA"}


@pytest.mark.parametrize("frame_type", [EndFrame, CancelFrame])
async def test_end_of_pipeline_hangs_up_once(frame_type):
    serializer = await make_serializer()

    assert json.loads(await serializer.serialize(frame_type())) == {"command": "HANGUP"}
    assert await serializer.serialize(frame_type()) is None


async def test_end_waits_for_the_audio_already_sent_to_play(monkeypatch):
    serializer = await make_serializer()
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("telephony.asterisk.serializer.asyncio.sleep", fake_sleep)
    one_second = OutputAudioRawFrame(bytes(16000), sample_rate=8000, num_channels=1)
    await serializer.serialize(one_second)
    await serializer.serialize(one_second)

    await serializer.serialize(EndFrame())

    assert slept == [pytest.approx(2.1, abs=0.05)]


async def test_end_does_not_wait_for_flushed_audio(monkeypatch):
    serializer = await make_serializer()
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("telephony.asterisk.serializer.asyncio.sleep", fake_sleep)
    await serializer.serialize(OutputAudioRawFrame(bytes(16000), sample_rate=8000, num_channels=1))
    await serializer.serialize(InterruptionFrame())

    await serializer.serialize(EndFrame())

    assert slept == []


async def test_cancel_hangs_up_without_waiting(monkeypatch):
    serializer = await make_serializer()
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("telephony.asterisk.serializer.asyncio.sleep", fake_sleep)
    await serializer.serialize(OutputAudioRawFrame(bytes(16000), sample_rate=8000, num_channels=1))

    assert json.loads(await serializer.serialize(CancelFrame())) == {"command": "HANGUP"}
    assert slept == []


async def test_auto_hang_up_can_be_disabled():
    serializer = await make_serializer(auto_hang_up=False)

    assert await serializer.serialize(EndFrame()) is None


async def test_other_frames_are_not_sent():
    serializer = await make_serializer()

    assert await serializer.serialize(TextFrame("hola")) is None


async def test_dtmf_becomes_an_input_frame():
    serializer = await make_serializer()

    frame = await serializer.deserialize(event("DTMF_END", digit="5"))

    assert isinstance(frame, InputDTMFFrame)
    assert frame.button == KeypadEntry.FIVE


@pytest.mark.parametrize(
    "text",
    [
        event("DTMF_END", digit="A"),  # not on a phone keypad
        event("MEDIA_XOFF"),
        event("QUEUE_DRAINED"),
        "not json",
    ],
)
async def test_other_messages_produce_no_frame(text):
    serializer = await make_serializer()

    assert await serializer.deserialize(text) is None
