"""What the product does, one folder per functionality: run an evaluation, judge answers, write test cases from documents,
read documents, manage and import test cases, recommend a version, summarise a run, score text, record steps, call models,
and read and write the TinyDB store (db_services).

Services use each other and the layers below (core, schemas, utils, prompts), never routers. db_services is the exception
in the other direction: it uses only core, schemas and utils, so storage code never depends on what the product does.
"""
