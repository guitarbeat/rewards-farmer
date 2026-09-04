"""Process and environment helpers for the desktop launcher."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import TextIO

import accounts
import launcher_progress

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PYTHON = os.path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")
MAIN_SCRIPT = os.path.join(REPO_ROOT, "src", "main.py")
DATA_DIR = os.path.join(REPO_ROOT, "data-dir")
LOG_DIR = os.path.join(REPO_ROOT, "logs")
VISUAL_SEARCH_IMAGE = os.path.join(REPO_ROOT, "visual_search.jpg")
LOCK_FILE = os.path.join(LOG_DIR, "launcher.lock")

LOG_TAIL_BYTES = 200_000
MAX_LOG_LINES = 3_000
STOP_GRACE_SECONDS = 8.0

EDGE_LOCK_MARKERS = (
	"could not start edge",
	"profile is already open",
)
EDGE_PROFILE_HINT = "Close other Edge windows using this profile, then Run again.\n"

CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def resolve_python_executable() -> str:
	"""Prefer the repo-local venv over whatever interpreter opened the GUI."""
	if os.path.isfile(VENV_PYTHON):
		return VENV_PYTHON

	return sys.executable


def build_run_command() -> list[str]:
	"""Build an unbuffered command line for the automation subprocess."""
	return [resolve_python_executable(), "-u", MAIN_SCRIPT]


def preflight_issues() -> list[str]:
	issues: list[str] = []

	if not os.path.isfile(VENV_PYTHON):
		issues.append("Missing .venv\\Scripts\\python.exe — run Setup.bat first.")

	if not os.path.isfile(MAIN_SCRIPT):
		issues.append("Missing src\\main.py.")

	if not os.path.isdir(DATA_DIR):
		issues.append("Missing data-dir\\ — copy your Edge profile folder here before running.")
	elif not accounts.is_edge_user_data_dir(DATA_DIR):
		issues.append(
			"data-dir\\ is not a valid Edge profile — copy your Edge User Data folder here."
		)

	return issues


def preflight_warnings() -> list[str]:
	warnings: list[str] = []

	if not os.path.isfile(VISUAL_SEARCH_IMAGE):
		warnings.append("visual_search.jpg missing — will download before the run")

	return warnings


def query_source_label() -> str:
	source = os.environ.get("QUERY_SOURCE", "trends").strip().lower()
	if source == "llm":
		return "Ollama queries"

	return "trends queries"


def readiness_summary() -> str:
	parts = ["Edge profile OK", query_source_label()]

	if os.path.isfile(VISUAL_SEARCH_IMAGE):
		parts.append("visual search ready")
	else:
		parts.append("visual search will download on run")

	return " · ".join(parts)


def ensure_visual_search_image() -> bool:
	if os.path.isfile(VISUAL_SEARCH_IMAGE):
		return True

	original_cwd = os.getcwd()
	try:
		os.chdir(REPO_ROOT)
		import random_image_for_visual_search

		random_image_for_visual_search.get_random_image()
	except Exception:
		return False
	finally:
		os.chdir(original_cwd)

	return os.path.isfile(VISUAL_SEARCH_IMAGE)


def open_path_in_file_manager(path: str) -> None:
	os.makedirs(path, exist_ok=True)

	if sys.platform == "win32":
		os.startfile(path)
		return

	if sys.platform == "darwin":
		subprocess.run(["open", path], check=False)
		return

	subprocess.run(["xdg-open", path], check=False)


def _read_lock_pid() -> int | None:
	if not os.path.isfile(LOCK_FILE):
		return None

	try:
		with open(LOCK_FILE, encoding="utf-8") as handle:
			content = handle.read().strip()
	except OSError:
		return None

	if not content.isdigit():
		return None

	return int(content)


def _is_process_alive(pid: int) -> bool:
	if pid <= 0:
		return False

	if sys.platform == "win32":
		import ctypes

		process_query = 0x1000
		handle = ctypes.windll.kernel32.OpenProcess(process_query, False, pid)
		if not handle:
			return False
		ctypes.windll.kernel32.CloseHandle(handle)
		return True

	try:
		os.kill(pid, 0)
	except OSError:
		return False

	return True


def clear_stale_lock() -> None:
	"""Remove a lock file left behind when a previous launcher crashed."""
	pid = _read_lock_pid()
	if pid is None:
		return

	if _is_process_alive(pid):
		return

	try:
		os.remove(LOCK_FILE)
	except OSError:
		pass


def acquire_single_instance() -> TextIO | None:
	"""Return an open lock handle, or None if another launcher is already open."""
	os.makedirs(LOG_DIR, exist_ok=True)
	clear_stale_lock()
	lock_handle = open(LOCK_FILE, "a+", encoding="utf-8")

	if sys.platform == "win32":
		import msvcrt

		try:
			lock_handle.seek(0)
			msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
		except OSError:
			lock_handle.close()
			return None
	else:
		import fcntl

		try:
			fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
		except BlockingIOError:
			lock_handle.close()
			return None

	lock_handle.seek(0)
	lock_handle.truncate()
	lock_handle.write(str(os.getpid()))
	lock_handle.flush()
	return lock_handle


def read_log_tail(path: str, *, max_bytes: int = LOG_TAIL_BYTES) -> str:
	if not os.path.isfile(path):
		return ""

	size = os.path.getsize(path)
	with open(path, "rb") as handle:
		if size > max_bytes:
			handle.seek(size - max_bytes)
			data = handle.read()
			newline = data.find(b"\n")
			if newline != -1:
				trimmed = data[newline + 1 :]
				if trimmed:
					data = trimmed
		else:
			data = handle.read()

	return data.decode("utf-8", errors="replace")


def edge_profile_hint_for_line(line: str) -> str | None:
	lowered = line.lower()
	if any(marker in lowered for marker in EDGE_LOCK_MARKERS):
		return EDGE_PROFILE_HINT

	return None


def _extract_run_lines(log_text: str, run_number: int) -> list[str]:
	start_marker = f"=== Run #{run_number} started"
	run_lines: list[str] = []
	collecting = False

	for line in log_text.splitlines():
		if start_marker in line:
			collecting = True
			run_lines = []
			continue
		if collecting and line.startswith("=== Run finished"):
			break
		if collecting:
			run_lines.append(line)

	return run_lines


def summarize_last_run(
	log_text: str,
	run_number: int,
	*,
	exit_code: int | None,
	stopped_by_user: bool,
) -> tuple[str, str]:
	"""Return status-bar text and tone for a finished run."""
	run_lines = _extract_run_lines(log_text, run_number)
	progress = launcher_progress.RunProgress.from_log_lines(run_lines)
	return launcher_progress.summarize_progress(
		progress,
		exit_code=exit_code,
		stopped_by_user=stopped_by_user,
	)


def spawn_run_process(*, command: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
	kwargs: dict = {
		"cwd": REPO_ROOT,
		"env": env,
		"stdout": subprocess.PIPE,
		"stderr": subprocess.STDOUT,
		"text": True,
		"bufsize": 1,
	}

	if sys.platform == "win32":
		kwargs["creationflags"] = CREATE_NEW_PROCESS_GROUP

	return subprocess.Popen(command, **kwargs)


def stop_run_process(process: subprocess.Popen[str], *, grace_seconds: float = STOP_GRACE_SECONDS) -> None:
	if process.poll() is not None:
		return

	process.terminate()

	deadline = time.monotonic() + grace_seconds
	while time.monotonic() < deadline:
		if process.poll() is not None:
			return
		time.sleep(0.2)

	if process.poll() is not None:
		return

	if sys.platform == "win32":
		subprocess.run(
			["taskkill", "/PID", str(process.pid), "/T", "/F"],
			capture_output=True,
			text=True,
			check=False,
		)
	else:
		process.kill()

	process.wait(timeout=5)
