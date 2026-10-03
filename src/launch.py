"""Launch the desktop GUI (pywebview preferred, CustomTkinter fallback)."""

from __future__ import annotations

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def _venv_pythonw(python: str) -> str:
	if sys.platform != "win32":
		return python
	candidate = os.path.join(os.path.dirname(python), "pythonw.exe")
	return candidate if os.path.isfile(candidate) else python


def _ensure_env() -> str:
	python = _venv_python()
	if python:
		return python

	print("First run: setting up Python environment...")
	code = subprocess.call([sys.executable, os.path.join(REPO_ROOT, "src", "setup_env.py")], cwd=REPO_ROOT)
	if code != 0:
		raise SystemExit(code)

	python = _venv_python()
	if not python:
		print("[ERROR] Missing .venv after setup.")
		print("Run Setup.bat or ./setup.sh first.")
		raise SystemExit(1)
	return python


def _pick_launcher(python: str) -> str:
	webview = os.path.join(REPO_ROOT, "src", "launcher_webview.py")
	fallback = os.path.join(REPO_ROOT, "src", "launcher.py")

	if subprocess.run([python, "-c", "import webview"], cwd=REPO_ROOT, capture_output=True).returncode == 0:
		return webview
	if subprocess.run([python, "-c", "import customtkinter"], cwd=REPO_ROOT, capture_output=True).returncode == 0:
		return fallback

	print("[ERROR] Neither pywebview nor customtkinter is installed in .venv")
	print("Run Setup.bat or ./setup.sh to install dependencies.")
	raise SystemExit(1)


def _ensure_icon(python: str) -> None:
	ico = os.path.join(REPO_ROOT, "assets", "rewards-farmer.ico")
	png = os.path.join(REPO_ROOT, "assets", "rewards-farmer.png")
	if os.path.isfile(ico) and os.path.isfile(png):
		return
	subprocess.run(
		[python, os.path.join(REPO_ROOT, "assets", "generate_icon.py")],
		cwd=REPO_ROOT,
		capture_output=True,
		check=False,
	)


def main() -> int:
	os.chdir(REPO_ROOT)
	os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
	os.environ.setdefault("OMP_NUM_THREADS", "1")

	python = _ensure_env()
	launcher = _pick_launcher(python)
	_ensure_icon(python)
	os.makedirs(os.path.join(REPO_ROOT, "logs"), exist_ok=True)

	creationflags = 0
	if sys.platform == "win32":
		creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
			subprocess, "CREATE_NEW_PROCESS_GROUP", 0
		)

	subprocess.Popen(
		[_venv_pythonw(python), launcher],
		cwd=REPO_ROOT,
		creationflags=creationflags,
		close_fds=True,
		start_new_session=(sys.platform != "win32"),
	)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
