"""Start Ollama when needed and verify its HTTP API is reachable."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11434
STARTUP_TIMEOUT = 45.0
POLL_INTERVAL = 0.5


def _base_url() -> str:
	host = os.environ.get("OLLAMA_HOST", f"{DEFAULT_HOST}:{DEFAULT_PORT}").strip()
	if not host:
		host = f"{DEFAULT_HOST}:{DEFAULT_PORT}"

	if host.startswith("http://") or host.startswith("https://"):
		return host.rstrip("/")

	return f"http://{host.rstrip('/')}"


def is_api_reachable(*, timeout: float = 3.0) -> bool:
	request = urllib.request.Request(f"{_base_url()}/api/tags", method="GET")

	try:
		with urllib.request.urlopen(request, timeout=timeout) as response:
			return response.status == 200
	except (urllib.error.URLError, OSError, ValueError):
		return False


def find_ollama_executable() -> str | None:
	path = shutil.which("ollama")
	if path:
		return path

	local_app_data = os.environ.get("LOCALAPPDATA", "")
	candidate = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
	if os.path.isfile(candidate):
		return candidate

	return None


def _popen_hidden(command: list[str]) -> None:
	kwargs: dict = {
		"stdout": subprocess.DEVNULL,
		"stderr": subprocess.DEVNULL,
	}

	if sys.platform == "win32":
		kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

	subprocess.Popen(command, **kwargs)


def start_ollama_server() -> bool:
	"""Best-effort start of the local Ollama API on Windows and other platforms."""
	executable = find_ollama_executable()
	if executable is None:
		logger.warning("Ollama executable not found on PATH.")
		return False

	if sys.platform == "win32":
		app_path = os.path.join(os.path.dirname(executable), "ollama app.exe")
		if os.path.isfile(app_path):
			_popen_hidden([app_path])

	_popen_hidden([executable, "serve"])
	return True


def ensure_ready(*, timeout: float = STARTUP_TIMEOUT) -> bool:
	"""Return True when the Ollama HTTP API responds."""
	if is_api_reachable():
		return True

	logger.info("Ollama API not reachable; attempting to start it…")
	if not start_ollama_server():
		return False

	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		if is_api_reachable():
			logger.info("Ollama is ready.")
			return True
		time.sleep(POLL_INTERVAL)

	return False
