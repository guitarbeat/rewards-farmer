"""Create the local .venv, install deps, and set up the desktop launcher."""

from __future__ import annotations

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_PYTHON = (3, 12)


def _run(command: list[str], *, check: bool = True, env: dict[str, str] | None = None) -> int:
	result = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
	if check and result.returncode != 0:
		raise SystemExit(result.returncode)
	return result.returncode


def _venv_python() -> str:
	if sys.platform == "win32":
		return os.path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")
	return os.path.join(REPO_ROOT, ".venv", "bin", "python")


def _ensure_python_version() -> None:
	if sys.version_info[:2] < MIN_PYTHON:
		print(
			f"[ERROR] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required "
			f"(found {sys.version_info.major}.{sys.version_info.minor})."
		)
		raise SystemExit(1)

	print("Using:")
	print(f"Python {sys.version.split()[0]}")


def _ensure_poetry() -> list[str]:
	code = _run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "poetry"], check=False)
	if code != 0:
		print("[ERROR] Could not install Poetry.")
		raise SystemExit(1)
	return [sys.executable, "-m", "poetry"]


def _install_dependencies(poetry: list[str]) -> None:
	print()
	print("Creating local .venv in this folder...")
	_run([*poetry, "env", "remove", "--all"], check=False)
	code = _run([*poetry, "install", "--no-interaction"], check=False)
	if code != 0:
		print("[ERROR] poetry install failed.")
		raise SystemExit(1)

	python = _venv_python()
	if not os.path.isfile(python):
		print(f"[ERROR] Expected {python} was not created.")
		raise SystemExit(1)


def _ensure_icons(python: str) -> None:
	ico = os.path.join(REPO_ROOT, "assets", "rewards-farmer.ico")
	png = os.path.join(REPO_ROOT, "assets", "rewards-farmer.png")
	if not os.path.isfile(ico) or not os.path.isfile(png):
		print("Generating launcher icon...")
		_run([python, os.path.join(REPO_ROOT, "assets", "generate_icon.py")])


def _verify_imports(python: str) -> None:
	print()
	print("Verifying imports...")
	env = os.environ.copy()
	env["OPENBLAS_NUM_THREADS"] = "1"
	env["OMP_NUM_THREADS"] = "1"
	code = _run(
		[
			python,
			"-c",
			(
				"import sys; sys.path.insert(0, 'src'); "
				"import textual, selenium, numpy, requests, PIL, ollama, dotenv, "
				"mouse_trajectory, site_registry; "
				"from sites.ms_rewards.runner import RewardsTaskUtils; "
				"site_registry.resolve('ms_rewards'); "
				"print('launcher + bot imports ok')"
			),
		],
		check=False,
		env=env,
	)
	if code != 0:
		print("[ERROR] Import check failed.")
		raise SystemExit(1)


def _ensure_visual_search(python: str) -> None:
	image = os.path.join(REPO_ROOT, "visual_search.jpg")
	if os.path.isfile(image):
		return

	print()
	print("Downloading visual search image...")
	_run(
		[
			python,
			"-c",
			(
				"import sys; sys.path.insert(0, 'src'); "
				"import random_image_for_visual_search; "
				"random_image_for_visual_search.get_random_image()"
			),
		],
		check=False,
	)
	if os.path.isfile(image):
		print("visual_search.jpg ready.")
	else:
		print("[WARN] Could not download visual_search.jpg. The launcher can retry before each run.")


def _install_shortcut(python: str) -> None:
	print()
	print("Installing desktop shortcut...")
	_run([python, os.path.join(REPO_ROOT, "src", "install_shortcut.py")], check=False)


def main() -> int:
	os.chdir(REPO_ROOT)
	print()
	print("Rewards Farmer setup")
	print("====================")
	print()

	_ensure_python_version()
	poetry = _ensure_poetry()
	_install_dependencies(poetry)

	python = _venv_python()
	_ensure_icons(python)
	_verify_imports(python)
	_ensure_visual_search(python)
	_install_shortcut(python)

	launch = "Launch.bat" if sys.platform == "win32" else "./launch.sh"
	print()
	print("Setup complete.")
	print(f"Local Python: {python}")
	print(f"Launch with:  {launch}")
	print()
	return 0


if __name__ == "__main__":
	try:
		raise SystemExit(main())
	except KeyboardInterrupt:
		raise SystemExit(130)
