"""The instructions sent to AI models, one file per prompt, each exporting one named variable.

``answer_judge/`` holds what the judge is told (grading, source check, run findings); ``testcase_generator/`` what the
question writer is told for each kind of question. Services import the variable; no prompt text lives anywhere else.
"""
