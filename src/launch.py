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
	same_interpreter = os.path.normcase(os.path.abspath(python)) == os.path.normcase(os.path.abspath(sys.executable))
	if same_interpreter:
		# Imported only after we know this process is the venv interpreter.
		# A system Python used to bootstrap setup does not have Textual installed.
		sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
		import launcher_tui

		return launcher_tui.main()

	if sys.platform == "win32":
		# os.execv on Windows does not keep a usable console for a full-screen TUI.
		return subprocess.call([python, LAUNCHER], cwd=REPO_ROOT)

	os.execv(python, [python, LAUNCHER])
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
