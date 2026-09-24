#!/usr/bin/env python3
import json
import os
import re
import sys
import tempfile
from copy import deepcopy
from urllib.parse import urlparse

MCP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(MCP_ROOT, "config", "backlog.json")
PROJECTS_CONFIG_DIR = os.path.join(MCP_ROOT, "config", "projects")
WORKFLOWS_CONFIG_DIR = os.path.join(MCP_ROOT, "config", "workflows")
ENV_PATH = os.path.join(MCP_ROOT, ".env")
LOG_DIR = os.environ.get("BACKLOG_MCP_LOG_DIR") or os.path.join(MCP_ROOT, "logs")
REQUEST_TIMEOUT_SECONDS = 20
MAX_LOG_VALUE_LENGTH = 500


def load_env_file():
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config():
    load_env_file()
    with open(CONFIG_PATH, "r", encoding="utf-8") as config_file:
        config = json.load(config_file)
    env_base_url = os.environ.get("BACKLOG_BASE_URL")
    if env_base_url:
        config["base_url"] = env_base_url
    validate_config(config)
    return config


def save_config(config):
    validate_config(config)
    config_dir = os.path.dirname(CONFIG_PATH)
    os.makedirs(config_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="backlog.", suffix=".json", dir=config_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(config, tmp_file, indent=2, ensure_ascii=False)
            tmp_file.write("\n")
        os.replace(tmp_path, CONFIG_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def validate_config(config):
    if not config.get("base_url"):
        raise ValueError("Missing config.base_url")
    if not isinstance(config.get("projects"), list) or not config["projects"]:
        raise ValueError("Missing config.projects list")
    if "default_project_key" in config:
        raise ValueError("default_project_key is no longer supported in global configuration. Please use workspace settings or specify explicitly.")


def api_base_url(config):
    return config["base_url"].rstrip("/") + "/api/v2"


def view_base_url(config):
    return config["base_url"].rstrip("/")


def catalog_path(project_key):
    return os.path.join(PROJECTS_CONFIG_DIR, f"{project_key}.json")


def load_project_catalog(project_key):
    path = catalog_path(project_key)
    if not os.path.exists(path):
        raise ValueError(
            f"Missing project catalog {path}. Run: backlog-cli project inspect {project_key}"
        )
    with open(path, "r", encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def workflow_config_path(name):
    return os.path.join(WORKFLOWS_CONFIG_DIR, f"{name}.json")


def load_workflow_config(name):
    path = workflow_config_path(name)
    if not os.path.exists(path):
        raise ValueError(f"Missing workflow config {path}")
    with open(path, "r", encoding="utf-8") as workflow_file:
        return json.load(workflow_file)


def project_keys(config):
    return list(config["projects"])


ISSUE_KEY_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)-\d+$")


def project_key_from_issue_id(issue_id):
    match = ISSUE_KEY_PATTERN.match(str(issue_id or ""))
    return match.group(1) if match else None


def find_workspace_project_key(start_path=None):
    curr = os.path.abspath(start_path or os.getcwd())
    while True:
        # Check .backlog-project.json
        local_config = os.path.join(curr, ".backlog-project.json")
        if os.path.exists(local_config):
            try:
                with open(local_config, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError(
                    f"Invalid workspace config {local_config}: {error}"
                ) from error
            if not isinstance(data, dict) or not data.get("project_key"):
                raise ValueError(
                    f"Invalid workspace config {local_config}: missing project_key"
                )
            return str(data["project_key"])

        # Stop traversing if we hit .git directory
        if os.path.exists(os.path.join(curr, ".git")):
            break

        # Move to parent directory
        parent = os.path.dirname(curr)
        if parent == curr:  # Root reached
            break
        curr = parent
    return None


def resolve_project_key(config, project_key=None, start_path=None):
    # 1. Explicit argument
    if project_key:
        key = project_key
        if key not in project_keys(config):
            keys = ", ".join(sorted(project_keys(config)))
            raise ValueError(f"Unknown Backlog project '{key}'. Available projects: {keys}")
        return key

    # 2. Local workspace config (.backlog-project.json walk-up to .git)
    workspace_key = find_workspace_project_key(start_path)
    if workspace_key:
        if workspace_key not in project_keys(config):
            keys = ", ".join(sorted(project_keys(config)))
            raise ValueError(
                f"Workspace project_key '{workspace_key}' was found, but it is not configured in global backlog.json. "
                f"Please add it to the 'projects' list in config/backlog.json."
            )
        return workspace_key

    # 3. Workspace path convention (segment match)
    curr_path = os.path.abspath(start_path or os.getcwd())
    p_keys = project_keys(config)
    segments = curr_path.split(os.sep)
    for segment in reversed(segments):
        if not segment:
            continue
        # Exact match first
        for pk in p_keys:
            if segment == pk:
                return pk
        # Case-insensitive match next
        for pk in p_keys:
            if segment.upper() == pk.upper():
                return pk

    # 5. Fail Fast
    p_keys_list = sorted(p_keys)
    projects_str = "\n".join(f"- {pk}" for pk in p_keys_list)
    raise ValueError(
        f"Cannot determine Backlog project.\n\n"
        f"Available projects:\n"
        f"{projects_str}\n\n"
        f"Please specify project_key explicitly\n"
        f"(for a bug such as OOP-123, the project_key is its prefix 'OOP')\n"
        f"or run inside a valid workspace."
    )


def resolve_project_key_for_issue(config, issue_id, project_key=None, start_path=None):
    issue_project_key = project_key_from_issue_id(issue_id)
    if issue_project_key and project_key and issue_project_key != project_key:
        raise ValueError(
            f"Issue key project '{issue_project_key}' does not match --project '{project_key}'."
        )
    return resolve_project_key(config, issue_project_key or project_key, start_path=start_path)


def resolve_project(config, project_key=None, start_path=None):
    key = resolve_project_key(config, project_key, start_path=start_path)
    return deepcopy(load_project_catalog(key))


def resolve_project_for_issue(config, issue_id, project_key=None, start_path=None):
    key = resolve_project_key_for_issue(config, issue_id, project_key, start_path=start_path)
    return deepcopy(load_project_catalog(key))


def resolve_user_id(config, user_ref):
    if isinstance(user_ref, int):
        return user_ref
    user = config.get("users", {}).get(str(user_ref))
    if not user or "id" not in user:
        raise ValueError(f"Unknown Backlog user reference '{user_ref}'")
    return int(user["id"])


def require_api_key():
    api_key = os.environ.get("BACKLOG_API_KEY", "")
    if not api_key:
        raise Exception("Missing BACKLOG_API_KEY. Set it in the environment or create .env from .env.example.")
    return api_key


def rotate_file_if_needed(path, max_bytes=5 * 1024 * 1024, backup_count=3):
    """Rotate a file if it exceeds max_bytes."""
    if not os.path.exists(path):
        return
    try:
        if os.path.getsize(path) < max_bytes:
            return
        
        # Rotate existing backups
        for i in range(backup_count - 1, 0, -1):
            s = f"{path}.{i}"
            d = f"{path}.{i+1}"
            if os.path.exists(s):
                os.replace(s, d)
        
        # Rename current to .1
        os.replace(path, f"{path}.1")
    except Exception:
        pass


_reported_log_failures: set[str] = set()


def report_log_failure(path, error):
    """Warn once per log file on stderr; logging must never break a tool call.

    stderr is safe for the stdio MCP transport (only stdout carries protocol).
    """
    if path in _reported_log_failures:
        return
    _reported_log_failures.add(path)
    try:
        print(f"backlog-mcp: failed to write {path}: {error}", file=sys.stderr)
    except Exception:
        pass


def response_error_body(response):
    text = response.text or ""
    return text[:MAX_LOG_VALUE_LENGTH]


EVAL_MARKER = ".backlog-eval.json"
_LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def find_eval_marker(workspace):
    """Eval mode is enabled only by a marker file in the workspace root itself (never a parent)."""
    if not workspace:
        return None
    path = os.path.join(workspace, EVAL_MARKER)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def apply_eval_marker(marker):
    from . import telemetry

    parsed = urlparse(marker.get("baseUrl", ""))
    host = parsed.hostname
    scheme = parsed.scheme
    if host not in _LOCAL_HOSTS or scheme != "http":
        raise ValueError(f"Eval backend must be localhost with http scheme, got {marker.get('baseUrl')!r}")
    global LOG_DIR
    os.environ["BACKLOG_BASE_URL"] = marker["baseUrl"]
    os.environ["BACKLOG_API_KEY"] = "eval-fake-key"
    LOG_DIR = marker["logDir"]
    telemetry.set_eval_tags(marker.get("runId"), marker.get("scenario"))
