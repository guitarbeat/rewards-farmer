"""Tests for cross-platform desktop shortcut installation."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import install_shortcut as shortcut


class InstallShortcutTests(unittest.TestCase):
	def test_macos_writes_executable_command(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			with mock.patch.object(shortcut, "_desktop_dir", return_value=temp_dir):
				with mock.patch.object(shortcut.sys, "platform", "darwin"):
					with mock.patch.object(shortcut, "_ensure_icons"):
						path = shortcut._install_macos()

			self.assertTrue(path.endswith("Rewards Farmer.command"))
			self.assertTrue(os.path.isfile(path))
			self.assertTrue(os.access(path, os.X_OK))
			with open(path, encoding="utf-8") as handle:
				body = handle.read()
			self.assertIn("#!/bin/bash", body)
			self.assertIn(shortcut.REPO_ROOT, body)

	def test_linux_writes_desktop_entry(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			desktop = os.path.join(temp_dir, "Desktop")
			apps = os.path.join(temp_dir, ".local", "share", "applications")
			os.makedirs(desktop)
			os.makedirs(apps)

			def fake_expanduser(path: str) -> str:
				if path in ("~", "~/"):
					return temp_dir
				if path.startswith("~/"):
					return os.path.join(temp_dir, path[2:].replace("/", os.sep))
				return path

			with mock.patch.object(shortcut, "_desktop_dir", return_value=desktop):
				with mock.patch.object(shortcut, "_ensure_icons"):
					with mock.patch.object(shortcut.os.path, "expanduser", side_effect=fake_expanduser):
						path = shortcut._install_linux()

			self.assertTrue(path.endswith("Rewards Farmer.desktop"))
			self.assertTrue(os.path.isfile(path))
			self.assertTrue(os.path.isfile(os.path.join(apps, "rewards-farmer.desktop")))
			with open(path, encoding="utf-8") as handle:
				body = handle.read()
			self.assertIn("[Desktop Entry]", body)
			self.assertIn("Name=Rewards Farmer", body)
			self.assertIn("Exec=", body)

	def test_icon_prefers_png_off_windows(self) -> None:
		with mock.patch.object(shortcut.sys, "platform", "linux"):
			with mock.patch.object(shortcut.os.path, "isfile", side_effect=lambda p: p == shortcut.ICON_PNG):
				self.assertEqual(shortcut._icon_for_platform(), shortcut.ICON_PNG)


class VenvPathTests(unittest.TestCase):
	def test_default_venv_python_is_platform_specific(self) -> None:
		import launcher_runtime as runtime

		with mock.patch.object(runtime.sys, "platform", "win32"):
			path = runtime.default_venv_python("/repo")
		self.assertTrue(path.replace("\\", "/").endswith(".venv/Scripts/python.exe"))

		with mock.patch.object(runtime.sys, "platform", "darwin"):
			path = runtime.default_venv_python("/repo")
		self.assertTrue(path.replace("\\", "/").endswith(".venv/bin/python"))


if __name__ == "__main__":
	unittest.main()
