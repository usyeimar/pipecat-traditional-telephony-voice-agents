"""The conversation itself, independent of the PBX the call comes from."""

from agent.pipeline import CallSession, run_call

__all__ = ["CallSession", "run_call"]
