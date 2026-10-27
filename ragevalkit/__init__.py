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
from ragevalkit.datasets.exceptions import DatasetError
from ragevalkit.evaluation.exceptions import RunBusy, RunError
from ragevalkit.exceptions import ConfigError, RagevalError
from ragevalkit.judging.exceptions import JudgeError
from ragevalkit.launcher import serve
from ragevalkit.recording.notes import note
from ragevalkit.recording.steps import step
from ragevalkit.storage.exceptions import StoreError, VersionNotFound

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
