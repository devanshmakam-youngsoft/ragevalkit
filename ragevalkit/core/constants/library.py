"""The library's names. This is the only file that writes the name: everything else is derived from it.

Changing ``LIBRARY_NAME`` renames the data folder, the sign-in cookie, the loggers and the API docs title. The Python
package folder and ``pyproject.toml`` carry the name too, which ``scripts/rename_library.py`` updates together with this file.
"""

LIBRARY_NAME = "ragevalkit"

DISPLAY_NAME = "RAG Evaluator"                       # the heading people see in the dashboard and the browser tab

DATA_DIR_NAME = f"{LIBRARY_NAME}_data"               # default folder for the store, the logs and the uploads
STORE_FILE_NAME = "store.json"                       # inside the data folder
LOGS_DIR_NAME = "logs"                               # inside the data folder
UPLOADS_DIR_NAME = "uploads"                         # inside the data folder

SESSION_COOKIE_NAME = f"{LIBRARY_NAME}_session"
LOGGER_NAME = LIBRARY_NAME                           # root logger; per-run loggers hang below it
TEMP_FOLDER_PREFIX = f"{LIBRARY_NAME}_"              # prefix of temporary folders (uploaded documents being read)
API_TITLE = LIBRARY_NAME                             # title of the interactive API docs
