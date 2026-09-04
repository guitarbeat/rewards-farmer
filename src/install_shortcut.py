"""Install or refresh the desktop shortcut with icon."""

from __future__ import annotations

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCH_BAT = os.path.join(REPO_ROOT, "Launch.bat")
ICON_PATH = os.path.join(REPO_ROOT, "assets", "rewards-farmer.ico")
SHORTCUT_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "Rewards Farmer.lnk")


def main() -> int:
	ps = f"""
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut = Join-Path $desktop 'Rewards Farmer.lnk'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcut)
$link.TargetPath = '{LAUNCH_BAT.replace("'", "''")}'
$link.WorkingDirectory = '{REPO_ROOT.replace("'", "''")}'
$link.IconLocation = '{ICON_PATH.replace("'", "''")},0'
$link.Description = 'Launch Rewards Farmer'
$link.Save()
Write-Output $shortcut
""".strip()

	result = subprocess.run(
		["powershell", "-NoProfile", "-Command", ps],
		capture_output=True,
		text=True,
		check=False,
	)

	if result.returncode != 0:
		print(result.stderr or result.stdout, file=sys.stderr)
		return result.returncode

	print((result.stdout or SHORTCUT_PATH).strip())
	return 0


if __name__ == "__main__":
	sys.exit(main())
