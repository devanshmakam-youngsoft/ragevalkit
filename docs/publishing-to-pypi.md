# Publishing the library to PyPI

Everything you need to publish this library so that anyone can run `pip install <name>`, and to publish every later
release. It is written for this repository as it is today and for Windows with Git Bash. Commands are meant to be run
from the repository root.

Contents: [1. Decide the name first](#1-decide-the-name-first) · [2. One-time setup](#2-one-time-setup) ·
[3. Get the repository ready](#3-get-the-repository-ready) · [4. Build and check](#4-build-and-check) ·
[5. Rehearse on TestPyPI](#5-rehearse-on-testpypi) · [6. Publish for real](#6-publish-for-real) ·
[7. After publishing](#7-after-publishing) · [8. Every later release](#8-every-later-release) ·
[9. Automatic publishing from GitHub](#9-automatic-publishing-from-github) · [10. Rules to know](#10-rules-to-know) ·
[11. When something goes wrong](#11-when-something-goes-wrong)

---

## 1. Decide the name first

The name on PyPI is the name people type in `pip install`, and it cannot be changed afterwards. A published name stays
with the project; moving to a new name later means publishing a new project and asking users to switch.

`ragevalkit` is a temporary name. If you are going to rename the library, do it **before** the first upload:

```bash
python scripts/rename_library.py NEW_NAME            # a dry run: lists what would change
python scripts/rename_library.py NEW_NAME --apply    # does it
python scripts/build_guide.py
cd frontend && npm run build && cd ..
python -m pytest
```

The script renames the package folder, every import, `pyproject.toml`, the docs and the name constant in
`ragevalkit/core/constants/library.py` (after the rename that file lives under the new name). It leaves the GitHub links and the
repository folder name alone: rename the repository on GitHub yourself, then update `[project.urls]` in `pyproject.toml`.

**Check the name is free** (a `404` means nobody has it):

```bash
python - <<'EOF'
import urllib.error
import urllib.request

name = "NAME"
try:
    urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json")
    print(name, "is TAKEN")
except urllib.error.HTTPError as error:
    print(name, "is free" if error.code == 404 else f"unclear (HTTP {error.code})")
EOF
```

Or open `https://pypi.org/project/NAME/` in a browser: a "404 Not Found" page means it is free. PyPI treats `-`, `_` and `.`
as the same character and ignores case, so `Rag-Eval`, `rag_eval` and `rag.eval` are one name. "Free on PyPI" is not trademark
clearance: also look at GitHub, a web search and the domain if you care about those.

## 2. One-time setup

1. **Create two accounts**, because the two sites are completely separate:
   - <https://pypi.org/account/register/> (the real index)
   - <https://test.pypi.org/account/register/> (a practice index; uploads there are disposable)
2. **Turn on two-factor sign-in** on both. PyPI requires it for uploads.
3. **Create an API token** on each site: *Account settings → API tokens → Add API token*.
   - For the first upload the only choice is *Entire account*, because the project does not exist yet.
   - After the first upload, delete that token and make a new one scoped to this one project.
   - A token is shown once. Store it in your password manager.
4. **Install the build tools** (in any Python environment):
   ```bash
   python -m pip install --upgrade build twine
   ```
5. **Tell twine your tokens.** Either set environment variables for the session:
   ```bash
   export TWINE_USERNAME=__token__
   export TWINE_PASSWORD=pypi-AgEIcHlwaS5vcmc...      # the token, starting with pypi-
   ```
   or create `%USERPROFILE%\.pypirc` (never commit this file):
   ```ini
   [distutils]
   index-servers =
       pypi
       testpypi

   [pypi]
   username = __token__
   password = pypi-...your real token...

   [testpypi]
   repository = https://test.pypi.org/legacy/
   username = __token__
   password = pypi-...your TestPyPI token...
   ```
   If you set up [automatic publishing](#9-automatic-publishing-from-github) you never need a token on your machine.

## 3. Get the repository ready

Work through this list once, and again (items 3 to 7) before each release.

1. **A `LICENSE` file.** `pyproject.toml` declares MIT, but the repository has no `LICENSE` file, so the license text does not
   ship with the package. Create `LICENSE` in the repository root:
   ```text
   MIT License

   Copyright (c) <year> <copyright holder, for example Youngsoft>

   Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
   documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
   rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
   persons to whom the Software is furnished to do so, subject to the following conditions:

   The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
   Software.

   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
   WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
   COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
   OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
   ```
   Check with the company that MIT is the license it wants, and who the copyright holder is. If the library must stay
   internal, do not publish to PyPI at all: use a private index (see [10](#10-rules-to-know)).
   Newer setuptools prefer `license = "MIT"` plus `license-files = ["LICENSE"]` in `[project]` over the older
   `license = { text = "MIT" }`. Both build today; modernise when convenient.
2. **Metadata in `pyproject.toml`.** Read `[project]` once: `name`, `description`, `authors` (add an email if you want
   people to reach you), `requires-python`, the classifiers and `[project.urls]`. Add `Homepage`, `Issues` and
   `Documentation` links if you have them; PyPI shows them in the sidebar.
3. **Choose the version.** One number, written in two places that must agree: `version` in `pyproject.toml` and `__version__`
   in `ragevalkit/__init__.py`. Use `MAJOR.MINOR.PATCH`:
   - PATCH (0.1.5 → 0.1.6): fixes only.
   - MINOR (0.1.x → 0.2.0): new features, or in a `0.` project, a change that breaks callers.
   - The git tag `v0.1.4` already exists publicly with the older layout. Do not reuse a version number that is already
     tagged for different code.
4. **Build the dashboard** and commit the result. People who `pip install` have no Node, so the built files must be inside the
   package:
   ```bash
   cd frontend && npm ci && npm run build && cd ..      # writes ragevalkit/web/dashboard/
   python scripts/build_guide.py                        # writes ragevalkit/web/guide/
   git status                                           # these two folders must have no uncommitted changes
   ```
5. **Run the checks:**
   ```bash
   python -m ruff check ragevalkit tests scripts examples
   python -m pytest
   ```
6. **README renders on PyPI.** PyPI shows `README.md` as the project page. Links inside it must be full `https://` URLs
   (relative links such as `docs/guide` break on PyPI). Update the install line to `pip install <name>` once the first
   release is out.
7. **Everything committed, on the branch you release from** (normally `main`), and pushed.

## 4. Build and check

```bash
rm -rf dist build *.egg-info          # start clean so old files cannot slip in
python -m build                       # writes dist/<name>-<version>.tar.gz and dist/<name>-<version>-py3-none-any.whl
python -m twine check dist/*          # both lines must say PASSED
```

What you get: a **wheel** (`.whl`, a ready-to-unpack archive pip prefers) and a **source distribution** (`.tar.gz`, the fallback).
Look inside the wheel before you upload it:

```bash
python -m zipfile -l dist/*.whl | head -60
```

For this repository the wheel should contain only the package folder (about 200 files): `core/`, `routers/`, `schemas/`,
`services/`, `prompts/`, `utils/`, `web/dashboard/`, `web/guide/`, `py.typed`, plus the `.dist-info` folder. It must **not**
contain `tests/`, `frontend/`, `docs/`, `examples/` or `scripts/`. The source distribution also contains the dashboard files.

Optional extras are declared in `pyproject.toml`: `semantic` (the meaning score, which brings PyTorch) and `dev`. The wheel
metadata lists `sentence-transformers` only under the `semantic` extra, so a plain install stays small.

## 5. Rehearse on TestPyPI

TestPyPI is a separate copy of PyPI for practice. Nothing there affects the real name.

```bash
python -m twine upload --repository testpypi dist/*
```

(With environment variables instead of `.pypirc`:
`python -m twine upload --repository-url https://test.pypi.org/legacy/ dist/*`.)

Then install it into a **fresh** virtual environment, as a stranger would:

```bash
python -m venv /tmp/trial && source /tmp/trial/Scripts/activate        # Git Bash on Windows
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ NAME
```

The `--extra-index-url` is required, because TestPyPI does not have FastAPI, pandas and the other dependencies.

Test what a user would do:

```bash
python -c "import NAME; print(NAME.__version__)"
cat > try.py <<'EOF'
import NAME
def bot(question: str) -> str:
    return "Refunds are allowed within 30 days."
NAME.serve(bot, port=8031, require_login=False, judge_fn=lambda q, e, g, m: {"answer_marks": 9, "material_marks": 8})
EOF
python try.py
```

Open `http://localhost:8031`: the dashboard must load (a blank page means the dashboard files were not built or committed), the
Help page must open, and a run on a test case must finish. Repeat once with `pip install "NAME[semantic]"` to try the meaning
score. Note a TestPyPI version, like a PyPI one, can never be uploaded twice. If the rehearsal shows a problem, fix it and
bump the version (for example `0.2.0.dev1`, `0.2.0.dev2`) before the next rehearsal.

## 6. Publish for real

Only when the rehearsal was clean:

```bash
python -m twine upload dist/*
```

Within a minute `https://pypi.org/project/NAME/` shows the project. Anyone can now run `pip install NAME`.

**This is permanent.** A file name can be uploaded once, ever. You can later *yank* a release (pip then skips it unless pinned) but
you cannot delete it and reuse the version number. Triple-check the version and the contents before this command.

## 7. After publishing

1. **Verify from a clean environment**, using the real index:
   ```bash
   python -m venv /tmp/real && source /tmp/real/Scripts/activate
   pip install NAME
   python -c "import NAME; print(NAME.__version__)"
   ```
2. **Tag the release** on the commit you built from, and push the tag (a plain `git push` does not push tags):
   ```bash
   git tag -a v0.2.0 -m "0.2.0: first PyPI release"
   git push origin v0.2.0
   ```
3. **Replace the project-scoped token.** On PyPI: *Account settings → API tokens*, delete the "entire account" token, create one
   limited to this project.
4. **Update the docs:** the README and `docs/guide/pages/02-first-run.html` currently say
   `pip install git+https://github.com/...`. Change them to `pip install NAME`, add the `NAME[semantic]` line, run
   `python scripts/build_guide.py`, commit and push.
5. **Create a GitHub release** from the tag (optional but useful): *Releases → Draft a new release → choose the tag →
   write the changes in plain words*.

## 8. Every later release

```text
1. Change code, merge to main, tests green.
2. Bump the version in pyproject.toml and ragevalkit/__init__.py (the same number).
3. Rebuild the dashboard and guide if they changed; commit the built folders.
4. rm -rf dist build *.egg-info && python -m build && python -m twine check dist/*
5. (Optional but safe for big changes) upload to TestPyPI and try it.
6. python -m twine upload dist/*
7. git tag -a vX.Y.Z -m "..." && git push origin main && git push origin vX.Y.Z
```

Keep a short `CHANGELOG.md` (what changed, in plain words, newest first) from the first release on: users read it before they upgrade.
When a change breaks existing callers, say so at the top of that release's entry. The `data_dir` option replacing
`store_path` and `log_dir` is an example.

## 9. Automatic publishing from GitHub

PyPI's **trusted publishing** lets GitHub upload for you when you push a tag. There is no token to store, copy or leak: PyPI trusts
one named workflow in one named repository.

1. On PyPI: *Your account → Publishing → Add a new pending publisher* (works before the project exists). Fill in:
   project name `NAME`, the GitHub owner and repository, workflow file name `publish.yml`, environment name `pypi`.
2. In the GitHub repository: *Settings → Environments → New environment* named `pypi`. Add yourself as a required reviewer if you
   want an approval click before each publish.
3. Add `.github/workflows/publish.yml`:
   ```yaml
   name: Publish to PyPI
   on:
     push:
       tags: ["v*"]

   jobs:
     build:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with: { python-version: "3.12" }
         - run: python -m pip install build twine
         - run: python -m build
         - run: python -m twine check dist/*
         - uses: actions/upload-artifact@v4
           with: { name: dist, path: dist/ }

     publish:
       needs: build
       runs-on: ubuntu-latest
       environment: pypi
       permissions:
         id-token: write            # lets PyPI verify this run is really your workflow
       steps:
         - uses: actions/download-artifact@v4
           with: { name: dist, path: dist/ }
         - uses: pypa/gh-action-pypi-publish@release/v1
   ```
4. From then on a release is: bump the version, commit, `git tag -a vX.Y.Z -m "..."`, `git push origin main vX.Y.Z`. The workflow builds,
   checks and uploads.

Because the dashboard is committed, the workflow does not need Node. If you ever stop committing `web/dashboard/`, add a Node build step
before `python -m build`.

## 10. Rules to know

- **Permanent releases.** One upload per file name, ever. Fix forward with a new version; use *yank* to hide a bad release.
- **Public.** Everything in the package is public, including the prompts, the built dashboard and the docstrings. No secrets, no
  company data, no internal URLs. The package contains no `.env` file; keep it that way.
- **Dependencies are your users' dependencies.** This project pins `litellm` to `>=1.104,<1.107` because later releases carried malware.
  Review the bounds of every dependency before each release, and raise the `litellm` cap only after checking a newer version is clean.
- **Python versions.** `requires-python = ">=3.10"` and the classifiers say 3.10 to 3.12. Test on the oldest and newest you claim.
- **Supported platforms.** The package is pure Python (`py3-none-any`), so one wheel serves Windows, macOS and Linux.
- **Keeping it internal instead.** If the library should not be public, publish to a private index (a company PyPI server, Azure
  Artifacts, GitHub Packages or an S3-backed index) with the same `build` step and `twine upload --repository-url <your index> dist/*`.
  Users then install with `pip install --index-url <your index> NAME`.
- **Name squatting rules.** PyPI can remove projects that are only placeholders. Publish a real release, not an empty one.

## 11. When something goes wrong

| Message or symptom | Cause and fix |
|---|---|
| `403 Invalid or non-existent authentication information` | Wrong token, or the username is not `__token__`, or the token belongs to the other site (TestPyPI vs PyPI). |
| `400 File already exists` | That version was already uploaded (even to TestPyPI). Bump the version and rebuild; delete the old files from `dist/` first. |
| `403 The user ... isn't allowed to upload to project` | Someone else owns the name, or your token is scoped to another project. |
| `400 The name '...' is too similar to an existing project` | PyPI blocks names that are confusingly close to another one. Pick another name. |
| `twine check` says the long description failed to render | Fix the README markdown (unclosed code fence, raw HTML PyPI strips) and rebuild. |
| The project page shows no README | `readme = "README.md"` is missing in `[project]`, or the file was not in the built distribution. |
| Installed package opens a blank dashboard | `ragevalkit/web/dashboard/` was not built or not committed before `python -m build`; check the wheel listing and rebuild. |
| `ModuleNotFoundError` for your package after install | The package list in `[tool.setuptools.packages.find]` does not include it (`include = ["ragevalkit*"]` must match the package folder name; after a rename it changes). |
| Wheel contains `tests/` or `frontend/` | A stale `build/` folder or `*.egg-info` from an earlier build. Delete them and rebuild. |
| `pip install NAME` gives an older version | PyPI's cache and your pip cache: wait a minute, or `pip install --no-cache-dir NAME==X.Y.Z`. |
| A release has a serious bug | Publish a fixed version first, then yank the bad one (*Manage → Releases → Options → Yank*) so new installs skip it. |
| Trusted publishing says `invalid-publisher` | The workflow file name, environment name, owner or repository in PyPI's publisher form does not exactly match the GitHub run. |

---

*Checked against this repository on 2 Nov 2026: `python -m build` produces a wheel and a source distribution, `twine check` passes on both, the
wheel contains `web/dashboard/` and `web/guide/` and no tests, and `sentence-transformers` appears only under the `semantic` extra.
The repository has no `LICENSE` file yet (item 3.1).*
