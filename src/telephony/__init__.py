"""One adapter per PBX.

An adapter accepts the PBX's WebSocket, authenticates it, wraps it in a Pipecat transport with
the serializer for that PBX's protocol, and runs the agent on it. To support another PBX, add a
module with a ``create_router(settings)`` function and mount it in ``app``.
"""
