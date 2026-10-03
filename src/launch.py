"""Launch the Rewards Farmer terminal UI in this console."""

from __future__ import annotations

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(REPO_ROOT, "src", "launcher_tui.py")


def _venv_python() -> str | None:
	if sys.platform == "win32":
		candidates = [os.path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")]
	else:
		candidates = [
			os.path.join(REPO_ROOT, ".venv", "bin", "python"),
			os.path.join(REPO_ROOT, ".venv", "bin", "python3"),
		]
	for path in candidates:
		if os.path.isfile(path):
			return path
	return None


def _ensure_env() -> str:
	python = _venv_python()
	if python:
		return python

	print("First run: setting up Python environment...")
	code = subprocess.call(
		[sys.executable, os.path.join(REPO_ROOT, "src", "setup_env.py")],
		cwd=REPO_ROOT,
	)
	if code != 0:
		raise SystemExit(code)

	python = _venv_python()
	if not python:
		print("[ERROR] Missing .venv after setup.")
		print("Run Setup.bat or ./setup.sh first.")
		raise SystemExit(1)
	return python


def main() -> int:
	os.chdir(REPO_ROOT)
	os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
	os.environ.setdefault("OMP_NUM_THREADS", "1")
	os.makedirs(os.path.join(REPO_ROOT, "logs"), exist_ok=True)

	python = _ensure_env()
	# Replace this process so the TUI keeps the same terminal.
	os.execv(python, [python, LAUNCHER])
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
