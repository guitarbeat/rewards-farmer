"""Install or refresh the desktop shortcut (Windows / macOS / Linux)."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_ICO = os.path.join(REPO_ROOT, "assets", "rewards-farmer.ico")
ICON_PNG = os.path.join(REPO_ROOT, "assets", "rewards-farmer.png")
LAUNCH_BAT = os.path.join(REPO_ROOT, "Launch.bat")
LAUNCH_SH = os.path.join(REPO_ROOT, "launch.sh")
LAUNCH_PY = os.path.join(REPO_ROOT, "src", "launch.py")


def _desktop_dir() -> str:
	xdg = os.environ.get("XDG_DESKTOP_DIR")
	if xdg:
		return os.path.expanduser(xdg)

	desktop = os.path.join(os.path.expanduser("~"), "Desktop")
	if os.path.isdir(desktop):
		return desktop
	return os.path.expanduser("~")


def _ensure_icons() -> None:
	if os.path.isfile(ICON_ICO) and os.path.isfile(ICON_PNG):
		return
	generate = os.path.join(REPO_ROOT, "assets", "generate_icon.py")
	if os.path.isfile(generate):
		subprocess.run([sys.executable, generate], cwd=REPO_ROOT, check=False)


def _icon_for_platform() -> str:
	if sys.platform == "win32" and os.path.isfile(ICON_ICO):
		return ICON_ICO
	if os.path.isfile(ICON_PNG):
		return ICON_PNG
	if os.path.isfile(ICON_ICO):
		return ICON_ICO
	return ""


def _install_windows() -> str:
	_ensure_icons()
	target = LAUNCH_BAT if os.path.isfile(LAUNCH_BAT) else LAUNCH_PY
	icon = _icon_for_platform()
	icon_location = f"{icon},0" if icon else ""

	ps = textwrap.dedent(
		f"""
		$desktop = [Environment]::GetFolderPath('Desktop')
		$shortcut = Join-Path $desktop 'Rewards Farmer.lnk'
		$shell = New-Object -ComObject WScript.Shell
		$link = $shell.CreateShortcut($shortcut)
		$link.TargetPath = '{target.replace("'", "''")}'
		$link.WorkingDirectory = '{REPO_ROOT.replace("'", "''")}'
		$link.IconLocation = '{icon_location.replace("'", "''")}'
		$link.Description = 'Launch Rewards Farmer'
		$link.Save()
		Write-Output $shortcut
		"""
	).strip()

	result = subprocess.run(
		["powershell", "-NoProfile", "-Command", ps],
		capture_output=True,
		text=True,
		check=False,
	)
	if result.returncode != 0:
		raise RuntimeError(result.stderr or result.stdout or "shortcut failed")
	return (result.stdout or "").strip()


def _install_macos() -> str:
	_ensure_icons()
	desktop = _desktop_dir()
	os.makedirs(desktop, exist_ok=True)
	path = os.path.join(desktop, "Rewards Farmer.command")
	if os.path.isfile(LAUNCH_SH):
		cmd = f'exec "{LAUNCH_SH}"'
	else:
		cmd = f'exec "{sys.executable}" "{LAUNCH_PY}"'
	with open(path, "w", encoding="utf-8", newline="\n") as handle:
		handle.write(f'#!/bin/bash\ncd "{REPO_ROOT}"\n{cmd}\n')
	os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
	return path


def _install_linux() -> str:
	_ensure_icons()
	desktop = _desktop_dir()
	os.makedirs(desktop, exist_ok=True)

	icon = _icon_for_platform()
	exec_line = f'"{LAUNCH_SH}"' if os.path.isfile(LAUNCH_SH) else f'"{sys.executable}" "{LAUNCH_PY}"'

	applications = os.path.join(os.path.expanduser("~"), ".local", "share", "applications")
	os.makedirs(applications, exist_ok=True)
	app_path = os.path.join(applications, "rewards-farmer.desktop")
	desktop_path = os.path.join(desktop, "Rewards Farmer.desktop")

	content = textwrap.dedent(
		f"""\
		[Desktop Entry]
		Type=Application
		Version=1.0
		Name=Rewards Farmer
		Comment=Launch Rewards Farmer
		Exec={exec_line}
		Icon={icon}
		Terminal=true
		Categories=Utility;
		Path={REPO_ROOT}
		"""
	)
	for path in (app_path, desktop_path):
		with open(path, "w", encoding="utf-8", newline="\n") as handle:
			handle.write(content)
		os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

	return desktop_path


def main() -> int:
	try:
		if sys.platform == "win32":
			path = _install_windows()
		elif sys.platform == "darwin":
			path = _install_macos()
		else:
			path = _install_linux()
	except Exception as exc:
		print(exc, file=sys.stderr)
		return 1

	print(path)
	return 0


if __name__ == "__main__":
	sys.exit(main())
