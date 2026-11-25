"""Control messages of Asterisk's chan_websocket, in its JSON format.

Reference: https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/

Only the JSON format is supported (``f(json)`` in the dial string): the plain-text one is
deprecated and cannot carry channel variables.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

# Events Asterisk sends.
MEDIA_START = "MEDIA_START"
MEDIA_XOFF = "MEDIA_XOFF"
MEDIA_XON = "MEDIA_XON"
DTMF_END = "DTMF_END"

# Commands the bot sends.
HANGUP = "HANGUP"
FLUSH_MEDIA = "FLUSH_MEDIA"

# "slin" is 8 kHz; "slin16", "slin48"... carry the rate in kHz (and "slin44" means 44.1 kHz).
_SLIN_FORMAT = re.compile(r"slin(\d+)?")
_SLIN_RATES = {None: 8000, "12": 12000, "16": 16000, "24": 24000, "32": 32000, "44": 44100}
_SLIN_RATES |= {"48": 48000, "96": 96000, "192": 192000}


class ProtocolError(ValueError):
    """A control message that does not follow the protocol."""


def parse_event(text: str) -> dict[str, Any]:
    """Parse a text message from Asterisk into its event object.

    Raises:
        ProtocolError: If it is not a JSON object with an ``event`` name.
    """
    try:
        message = json.loads(text)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"not JSON (is f(json) set in the dial string?): {text[:120]!r}") from e
    if not isinstance(message, dict) or not isinstance(message.get("event"), str):
        raise ProtocolError(f"not an event object: {text[:120]!r}")
    return message


def command(name: str, **parameters: Any) -> str:
    """Build a command to send to Asterisk as a text message."""
    return json.dumps({"command": name, **parameters})


def slin_sample_rate(audio_format: str) -> int | None:
    """Sample rate of a signed linear format name, or None for any other codec."""
    match = _SLIN_FORMAT.fullmatch(audio_format.strip().lower())
    if not match:
        return None
    return _SLIN_RATES.get(match.group(1))


@dataclass(frozen=True)
class MediaStart:
    """The first message of a call: what Asterisk is going to send and expects back.

    Attributes:
        channel_id: Unique id of the WebSocket channel in Asterisk.
        channel: Name of that channel.
        audio_format: Codec of the audio in both directions, e.g. ``slin``.
        optimal_frame_size: Bytes of audio that make one frame. Asterisk only plays messages
            whose length is a multiple of it without dropping the remainder.
        ptime: Duration of one frame, in milliseconds.
        variables: The channel's variables at the time it was created.
    """

    channel_id: str
    channel: str
    audio_format: str
    optimal_frame_size: int
    ptime: int
    variables: dict[str, str] = field(default_factory=dict)

    @property
    def sample_rate(self) -> int | None:
        """Sample rate of the audio, or None if it is not signed linear."""
        return slin_sample_rate(self.audio_format)

    @classmethod
    def parse(cls, text: str) -> "MediaStart":
        """Parse the MEDIA_START event.

        Raises:
            ProtocolError: If the message is another event or lacks a field.
        """
        event = parse_event(text)
        if event["event"] != MEDIA_START:
            raise ProtocolError(f"expected {MEDIA_START}, got {event['event']}")
        try:
            return cls(
                channel_id=str(event["channel_id"]),
                channel=str(event.get("channel", "")),
                audio_format=str(event["format"]),
                optimal_frame_size=int(event["optimal_frame_size"]),
                ptime=int(event.get("ptime", 20)),
                variables=dict(event.get("channel_variables") or {}),
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ProtocolError(f"incomplete {MEDIA_START}: {text[:200]!r}") from e
