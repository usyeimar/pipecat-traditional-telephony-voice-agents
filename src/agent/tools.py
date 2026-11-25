"""Tools the LLM can call during a call.

A tool is an async function whose first parameter is ``params``. Pipecat builds its schema from
the signature and the docstring, which is the description the model reads. Add new tools to
``TOOLS``.
"""

from pipecat.frames.frames import EndWorkerFrame
from pipecat.services.llm_service import FunctionCallParams


async def end_call(params: FunctionCallParams):
    """Hang up the phone call.

    Use it once the caller has said goodbye or has nothing else to ask, in the same turn as
    your own goodbye.
    """
    await params.result_callback({"success": True})
    # Downstream, so the goodbye already on its way is spoken before the pipeline ends. The
    # telephony adapter hangs up when the pipeline does.
    await params.llm.push_frame(EndWorkerFrame(reason="end_call"))


TOOLS = [end_call]
