"""Authentication of the PBX on the WebSocket handshake.

Without it, anyone who can reach the bot's port could open calls on the paid speech services,
or, for FreeSWITCH, send another call's UUID and interrupt or hang up that call.
"""

import base64
import binascii
import secrets

from fastapi import WebSocket
from loguru import logger

POLICY_VIOLATION = 1008


def token_from_authorization(header: str) -> str | None:
    """The secret carried by an ``Authorization`` header.

    FreeSWITCH sends ``Bearer <token>``. Asterisk can only send HTTP Basic credentials, so for
    ``Basic`` the password is the token and the username is ignored.
    """
    scheme, _, value = header.strip().partition(" ")
    value = value.strip()
    if scheme.lower() == "bearer":
        return value or None
    if scheme.lower() == "basic":
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
        _, separator, password = decoded.partition(":")
        return password if separator and password else None
    return None


def is_authorized(websocket: WebSocket, expected_token: str) -> bool:
    """Whether the handshake carries the expected token, compared in constant time."""
    token = token_from_authorization(websocket.headers.get("authorization", ""))
    return token is not None and secrets.compare_digest(token.encode(), expected_token.encode())


async def reject_unauthorized(websocket: WebSocket, expected_token: str) -> bool:
    """Close an unauthorized handshake. Returns True if the connection was rejected.

    Call it before ``websocket.accept()``, so the handshake fails with HTTP 403.
    """
    if is_authorized(websocket, expected_token):
        return False
    logger.warning(f"Rejected WebSocket from {websocket.client}: missing or wrong token")
    await websocket.close(code=POLICY_VIOLATION)
    return True
