"""Writing test cases from documents.

FLOW
----
1. ``docs.read_document`` turns each upload into passages (and the upload is deleted).
2. ``planning.plan_tasks`` decides which passages each question is written from: passages are taken in a spread
   order so they sample the whole document, and questions are shared out across the uploaded files.
3. ``writer.generate_item`` asks the model for ONE item of a category (a question, or a whole conversation).
   ``checks.validate`` rejects anything that breaks the rules — most importantly, the evidence (sentence numbers
   such as A3, or a quoted sentence) must point at real sentences of the passages — and the item is retried with the
   reason spelled out.
4. ``manager.GenerationManager`` runs this in the background, saving every finished item to a *review batch*
   so closing the browser or losing the network loses nothing. Items become test cases only when approved;
   batches never approved are deleted after ``batch_ttl_hours``.

CATEGORIES (see ``categories``; each becomes a group)
    direct     answered by one plainly stated fact
    indirect   answered from the document, but phrased in everyday words or as a situation
    multipart  one question with two or more parts, answered from different passages
    multiturn  a conversation whose follow-ups only make sense with the earlier turns

Every generated test case has the type ``rag``: its answer has to come from the documents.

Modules: ``prompts/`` (what the model is told, one file each) · ``evidence`` (quotes are really in the document) ·
``checks`` (the rules) · ``llm`` (the model client; the call itself is ``llm.complete``) · ``writer`` · ``planning`` · ``manager``.
"""
from ragevalkit.generation.categories import CASE_TYPE, CATEGORIES, CATEGORY_LABELS
from ragevalkit.generation.checks import validate
from ragevalkit.generation.exceptions import GenerationBusy, GenerationError
from ragevalkit.generation.manager import GenerationManager
from ragevalkit.generation.model_client import GenerationModelClient
from ragevalkit.generation.planning import Task, plan_tasks
from ragevalkit.generation.reply_parser import parse_reply
from ragevalkit.generation.writer import generate_item

__all__ = [
    "CASE_TYPE", "CATEGORIES", "CATEGORY_LABELS", "GenerationBusy", "GenerationError", "GenerationManager",
    "GenerationModelClient", "Task", "generate_item", "parse_reply", "plan_tasks", "validate",
]
