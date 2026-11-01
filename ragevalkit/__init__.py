"""ragevalkit — evaluate any RAG pipeline, chatbot, or multi-agent system.

Quickstart::

    import ragevalkit

    def my_rag(question):
        return pipeline.run(question)

    ragevalkit.serve(my_rag)

With step recording::

    @ragevalkit.step("retriever")
    def retrieve(query):
        return vector_db.search(query)

    with ragevalkit.step("llm") as s:
        answer = llm.generate(query)
        s.material = retrieved_context
"""
from ragevalkit.core.exceptions import (
    ConfigError,
    DatasetError,
    JudgeError,
    RagevalError,
    RunBusy,
    RunError,
    StoreError,
    VersionNotFound,
)
from ragevalkit.launcher import serve
from ragevalkit.services.step_recorder.notes import note
from ragevalkit.services.step_recorder.steps import step

__version__ = "0.1.3"
__all__ = [
    "serve", "step", "note", "__version__",
    # exceptions
    "RagevalError",
    "ConfigError",
    "DatasetError",
    "StoreError", "VersionNotFound",
    "RunError", "RunBusy",
    "JudgeError",
]
