import json

import pytest

from telephony.asterisk import protocol

MEDIA_START = json.dumps(
    {
        "event": "MEDIA_START",
        "connection_id": "e226e283-c90a-4ea9-9e37-389000b9ef47",
        "channel": "WebSocket/voice_agent/0x1234",
        "channel_id": "1764069000.7",
        "format": "slin",
        "optimal_frame_size": 320,
        "ptime": 20,
        "channel_variables": {"CALLERID(num)": "1000"},
    }
)


def test_media_start_is_parsed():
    media = protocol.MediaStart.parse(MEDIA_START)

    assert media.channel_id == "1764069000.7"
    assert media.audio_format == "slin"
    assert media.sample_rate == 8000
    assert media.optimal_frame_size == 320
    assert media.variables == {"CALLERID(num)": "1000"}


@pytest.mark.parametrize(
    "text",
    [
        "MEDIA_START connection_id:abc format:slin optimal_frame_size:320",  # plain-text format
        json.dumps({"event": "DTMF_END", "digit": "5"}),  # another event
        json.dumps({"event": "MEDIA_START", "format": "slin"}),  # fields missing
        json.dumps(["MEDIA_START"]),  # not an object
    ],
)
def test_media_start_rejects_anything_else(text):
    with pytest.raises(protocol.ProtocolError):
        protocol.MediaStart.parse(text)


@pytest.mark.parametrize(
    ("audio_format", "rate"),
    [("slin", 8000), ("SLIN16", 16000), ("slin44", 44100), ("slin48", 48000)],
)
def test_slin_sample_rate(audio_format, rate):
    assert protocol.slin_sample_rate(audio_format) == rate


@pytest.mark.parametrize("audio_format", ["ulaw", "opus", "slin7", "slin16x", ""])
def test_slin_sample_rate_of_other_codecs_is_none(audio_format):
    assert protocol.slin_sample_rate(audio_format) is None


def test_command_is_a_json_object():
    assert json.loads(protocol.command(protocol.HANGUP)) == {"command": "HANGUP"}
    assert json.loads(protocol.command("MARK_MEDIA", correlation_id="a1")) == {
        "command": "MARK_MEDIA",
        "correlation_id": "a1",
    }
