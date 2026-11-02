"""What the product does, in two groups and four building blocks.

    evaluation/    run an evaluation, judge answers, record steps, summarise a run, recommend a version
    testcases/     manage and import test cases, generate them from documents, read documents and spreadsheets
    db_services/   the TinyDB store           llm_client/   calls any AI model
    text_metrics/  key words, BM25, meaning   app_info/     the guide page and which features are on

Services may use the layers below (core, schemas, utils, prompts), never routers. Among themselves the flow is one way:
evaluation may use testcases and the building blocks, testcases may use the building blocks, and a building block uses
none of the groups. db_services uses only core, schemas and utils. tests/architecture enforces all of this.
"""
