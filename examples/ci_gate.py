"""Run an evaluation from a script (for example in CI) against a ragevalkit server that is already running,
and fail the build when quality drops below a bar.

    python ci_gate.py            # exit code 0: passed, 1: below the bar, 2: no result
"""
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE_URL = os.environ.get("EVAL_URL", "http://localhost:8002")
USERNAME, PASSWORD = os.environ.get("EVAL_USER", ""), os.environ.get("EVAL_PASSWORD", "")
GROUP = os.environ.get("EVAL_GROUP", "Billing")          # the group of test cases to run
VERSION = os.environ.get("EVAL_VERSION", "ci-" + time.strftime("%m%d-%H%M"))
MINIMUM_ANSWER_QUALITY = float(os.environ.get("EVAL_MINIMUM", "7"))
WAIT_SECONDS = 1800
POLL_SECONDS = 5

opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path: str, *, json_body: dict | None = None, form: dict | None = None):
    """One request to the dashboard's API. Returns the decoded JSON answer."""
    data, headers = None, {}
    if json_body is not None:
        data, headers = json.dumps(json_body).encode(), {"Content-Type": "application/json"}
    if form is not None:
        boundary = uuid.uuid4().hex
        data = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in form.items())
        data += f"--{boundary}--\r\n".encode()
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    with opener.open(urllib.request.Request(BASE_URL + "/api/" + path, data=data, headers=headers), timeout=60) as response:
        return json.loads(response.read())


def run_gate() -> int:
    if USERNAME:                                             # only needed when the server asks for a sign-in
        call("auth/login", json_body={"username": USERNAME, "password": PASSWORD})
    group = next(g for g in call("groups") if g["name"] == GROUP)
    call("runs", form={"version": VERSION, "group_ids": json.dumps([group["group_id"]]), "notes": "CI run"})

    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:                            # a version appears when its run has finished
        try:
            summary = call(f"versions/{VERSION}")["summary"]
            break
        except urllib.error.HTTPError:
            time.sleep(POLL_SECONDS)
    else:
        print(f"No result after {WAIT_SECONDS} seconds: look at the dashboard or at eval_logs/.")
        return 2

    quality, failed = summary["avg_answer_marks"], summary["failed_rows"]
    print(f"Version {VERSION}: answer quality {quality}, {failed} failed questions, {summary['total_rows']} questions")
    return 0 if quality is not None and quality >= MINIMUM_ANSWER_QUALITY and failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_gate())
