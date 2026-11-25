"""Asterisk adapter, over chan_websocket (Asterisk 22.6+).

    caller --SIP/RTP--> Asterisk --chan_websocket (WebSocket)--> bot

Dialing ``WebSocket/voice_agent/...`` makes Asterisk open a WebSocket to the bot and bridge the
call's audio to it. Audio travels in binary messages in both directions and control messages
(interrupt, hang up, DTMF) as JSON text on the same connection, so nothing else is needed to
drive the call. Dialplan: asterisk/conf/extensions.conf.
"""

from telephony.asterisk.router import create_router
from telephony.asterisk.serializer import AsteriskFrameSerializer

__all__ = ["AsteriskFrameSerializer", "create_router"]
