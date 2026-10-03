"""Process and environment helpers for the desktop launcher."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import TextIO

import accounts
import launcher_progress

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_venv_python(repo_root: str | None = None) -> str:
	root = repo_root or REPO_ROOT
	if sys.platform == "win32":
		return os.path.join(root, ".venv", "Scripts", "python.exe")
	return os.path.join(root, ".venv", "bin", "python")


VENV_PYTHON = default_venv_python()
MAIN_SCRIPT = os.path.join(REPO_ROOT, "src", "main.py")
DATA_DIR = os.path.join(REPO_ROOT, "data-dir")
LOG_DIR = os.path.join(REPO_ROOT, "logs")
VISUAL_SEARCH_IMAGE = os.path.join(REPO_ROOT, "visual_search.jpg")
LOCK_FILE = os.path.join(LOG_DIR, "launcher.lock")
SETUP_HINT = "Setup.bat" if sys.platform == "win32" else "./setup.sh"


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

	alt = os.path.join(REPO_ROOT, ".venv", "bin", "python3")
	if sys.platform != "win32" and os.path.isfile(alt):
		return alt

	return sys.executable


def build_run_command() -> list[str]:
	"""Build an unbuffered command line for the automation subprocess."""
	return [resolve_python_executable(), "-u", MAIN_SCRIPT]


def preflight_issues() -> list[str]:
	issues: list[str] = []

	if not os.path.isfile(VENV_PYTHON) and not (
		sys.platform != "win32" and os.path.isfile(os.path.join(REPO_ROOT, ".venv", "bin", "python3"))
	):
		issues.append(f"Missing .venv — run {SETUP_HINT} first.")

	if not os.path.isfile(MAIN_SCRIPT):
		issues.append("Missing src/main.py.")

	if not os.path.isdir(DATA_DIR):
		issues.append("Missing data-dir — copy your Edge profile folder here before running.")
	elif not accounts.is_edge_user_data_dir(DATA_DIR):
		issues.append(
			"data-dir is not a valid Edge profile — copy your Edge User Data folder here."
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


_RUN_START_RE = re.compile(r"^=== Run #(\d+) started (.+?) ===\s*$")
_RUN_FINISH_RE = re.compile(r"^=== Run finished (.+?) \(exit (.+?)\) ===\s*$")


@dataclass(frozen=True)
class RunHistoryEntry:
	number: int
	started: str
	finished: str | None
	exit_code: int | None
	summary: str
	tone: str
	ok_count: int
	skip_count: int
	fail_count: int
	search_quota: str | None


def parse_run_history(log_text: str, *, limit: int = 30) -> list[RunHistoryEntry]:
	"""Parse finished/incomplete runs from launcher_runs.log text (newest first)."""
	entries: list[RunHistoryEntry] = []
	current_number: int | None = None
	current_started: str | None = None
	current_lines: list[str] = []

	def flush(*, finished: str | None, exit_raw: str | None) -> None:
		nonlocal current_number, current_started, current_lines
		if current_number is None or current_started is None:
			current_lines = []
			return

		exit_code: int | None = None
		if exit_raw is not None and exit_raw not in {"None", "none"}:
			try:
				exit_code = int(exit_raw)
			except ValueError:
				exit_code = None

		stopped = any("Stopping run" in line for line in current_lines)
		progress = launcher_progress.RunProgress.from_log_lines(current_lines)
		summary, tone = launcher_progress.summarize_progress(
			progress,
			exit_code=exit_code,
			stopped_by_user=stopped,
		)
		if finished is None and exit_code is None and not stopped:
			summary = "Incomplete — no finish marker in log"
			tone = "warning"

		entries.append(
			RunHistoryEntry(
				number=current_number,
				started=current_started.strip(),
				finished=finished,
				exit_code=exit_code,
				summary=summary,
				tone=tone,
				ok_count=progress.ok_count(),
				skip_count=progress.skip_count(),
				fail_count=progress.fail_count(),
				search_quota=progress.search_quota,
			)
		)
		current_number = None
		current_started = None
		current_lines = []

	for line in log_text.splitlines():
		start = _RUN_START_RE.match(line.strip())
		if start:
			flush(finished=None, exit_raw=None)
			current_number = int(start.group(1))
			current_started = start.group(2)
			current_lines = []
			continue

		finish = _RUN_FINISH_RE.match(line.strip())
		if finish and current_number is not None:
			flush(finished=finish.group(1).strip(), exit_raw=finish.group(2).strip())
			continue

		if current_number is not None:
			current_lines.append(line)

	flush(finished=None, exit_raw=None)
	entries.reverse()
	return entries[:limit]


def extract_run_log(log_text: str, run_number: int) -> str:
	"""Return the raw log text for one run, including start/finish banners."""
	start_marker = f"=== Run #{run_number} started"
	lines: list[str] = []
	collecting = False

	for line in log_text.splitlines(keepends=True):
		stripped = line.strip()
		if start_marker in stripped:
			collecting = True
			lines = [line]
			continue
		if collecting:
			lines.append(line)
			if stripped.startswith("=== Run finished"):
				break

	return "".join(lines)


def summarize_last_run(
	log_text: str,
	run_number: int,
	*,
	exit_code: int | None,
	stopped_by_user: bool,
) -> tuple[str, str]:
	"""Return status-bar text and tone for a finished run."""
	run_chunk = extract_run_log(log_text, run_number)
	run_lines = [line.rstrip("\r\n") for line in run_chunk.splitlines()]
	# Drop start/finish banners so progress parsing stays task-focused.
	run_lines = [
		line
		for line in run_lines
		if not line.startswith("=== Run #") and not line.startswith("=== Run finished")
	]
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
