"""Tests for TUI Settings Modal and Upstream Hardening Improvements."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import launcher_tui
from fakes import FakeDriver, FakeElement
from llm_utils import sanitize_search_query
from sites.ms_rewards.browser import BrowserHelpers
from textual.widgets import Button, Checkbox, Input, Select


class QuerySanitizerTests(unittest.TestCase):
	def test_strips_search_query_prefix(self):
		self.assertEqual(sanitize_search_query("search query: james webb space telescope"), "james webb space telescope")
		self.assertEqual(sanitize_search_query("Search Query: mars rover discoveries"), "mars rover discoveries")
		self.assertEqual(sanitize_search_query("query: deep ocean trenches"), "deep ocean trenches")
		self.assertEqual(sanitize_search_query("search for: quantum computing"), "quantum computing")

	def test_strips_markdown_formatting_and_quotes(self):
		self.assertEqual(sanitize_search_query('**search query:** "aurora borealis Iceland"'), "aurora borealis Iceland")
		self.assertEqual(sanitize_search_query("`ancient roman architecture`"), "ancient roman architecture")
		self.assertEqual(sanitize_search_query("'artificial intelligence trends'"), "artificial intelligence trends")

	def test_handles_empty_or_clean_strings(self):
		self.assertEqual(sanitize_search_query(""), "")
		self.assertEqual(sanitize_search_query("national parks in utah"), "national parks in utah")


class BrowserScrollIntoCenterTests(unittest.TestCase):
	def test_move_to_and_click_executes_scroll_into_view(self):
		class ScriptTrackingDriver(FakeDriver):
			def __init__(self):
				super().__init__()
				self.scripts_executed = []

			def execute_script(self, script, *args):
				self.scripts_executed.append((script, args))
				return None

		driver = ScriptTrackingDriver()
		helpers = BrowserHelpers()
		helpers.driver = driver
		helpers.mouse = mock.Mock()

		element = FakeElement(text="target button")
		helpers.move_to_and_click(element)

		# Verify scrollIntoView was called with center alignment
		self.assertTrue(any("scrollIntoView" in call[0] and "center" in call[0] for call in driver.scripts_executed))
		helpers.mouse.move_to_element.assert_called_once_with(element)
		helpers.mouse.human_like_click.assert_called_once()


class SettingsPersistenceTests(unittest.TestCase):
	def setUp(self):
		self._orig_env = dict(os.environ)

	def tearDown(self):
		os.environ.clear()
		os.environ.update(self._orig_env)

	def test_save_env_settings_creates_file_and_updates_environ(self):
		with tempfile.TemporaryDirectory() as tmpdir:
			env_file = os.path.join(tmpdir, ".env")
			self.assertFalse(os.path.exists(env_file))

			settings = {
				"WEBHOOK_URL": "https://discord.com/api/webhooks/test",
				"WEBHOOK_NOTIFY_ON_FAILURE_ONLY": "true",
				"ENABLE_MOBILE_SEARCH": "true",
				"SEARCH_BURST_LIMIT": "4",
				"SEARCH_COOLDOWN_DELAY_SECONDS": "900",
				"QUERY_SOURCE": "trends",
			}

			launcher_tui.save_env_settings(settings, dotenv_path=env_file)

			self.assertTrue(os.path.exists(env_file))
			for key, val in settings.items():
				self.assertEqual(os.environ.get(key), val)

			with open(env_file, "r", encoding="utf-8") as f:
				content = f.read()
			self.assertIn("WEBHOOK_URL", content)
			self.assertIn("SEARCH_BURST_LIMIT", content)


class SettingsModalTuiTests(unittest.IsolatedAsyncioTestCase):
	def setUp(self):
		self._orig_env = dict(os.environ)

	def tearDown(self):
		os.environ.clear()
		os.environ.update(self._orig_env)

	def _app(self) -> launcher_tui.RewardsFarmerApp:
		self._patches = [
			mock.patch("launcher_runtime.preflight_issues", return_value=[]),
			mock.patch("launcher_runtime.preflight_warnings", return_value=[]),
			mock.patch("launcher_runtime.read_log_tail", return_value=""),
			mock.patch("launcher_runtime.readiness_summary", return_value="Ready"),
			mock.patch("launcher_runtime.detect_edge_profiles", return_value=[("Default", "Default profile")]),
		]
		for patcher in self._patches:
			patcher.start()
			self.addCleanup(patcher.stop)
		return launcher_tui.RewardsFarmerApp()

	async def test_open_settings_modal_and_cancel(self) -> None:
		app = self._app()
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			# Click Config button
			await pilot.click("#config")
			await pilot.pause()

			self.assertTrue(any(isinstance(screen, launcher_tui.SettingsModal) for screen in app.screen_stack))

			# Press escape or click Cancel to dismiss
			await pilot.click("#btn-cancel")
			await pilot.pause()

			self.assertFalse(any(isinstance(screen, launcher_tui.SettingsModal) for screen in app.screen_stack))

	async def test_settings_modal_save_persists_settings(self) -> None:
		app = self._app()
		with tempfile.TemporaryDirectory() as tmpdir:
			env_path = os.path.join(tmpdir, ".env")
			with mock.patch("launcher_tui.DOTENV_PATH", env_path):
				async with app.run_test(size=(100, 40)) as pilot:
					await pilot.pause()
					await pilot.press("s")
					await pilot.pause()

					modal = next(s for s in app.screen_stack if isinstance(s, launcher_tui.SettingsModal))
					modal.query_one("#cfg-webhook-url", Input).value = "https://example.com/webhook"
					modal.query_one("#cfg-enable-mobile-search", Checkbox).value = True
					modal.query_one("#cfg-burst-limit", Input).value = "3"

					await pilot.click("#btn-save")
					await pilot.pause()

					self.assertFalse(any(isinstance(screen, launcher_tui.SettingsModal) for screen in app.screen_stack))
					self.assertEqual(os.environ.get("WEBHOOK_URL"), "https://example.com/webhook")
					self.assertEqual(os.environ.get("ENABLE_MOBILE_SEARCH"), "true")
					self.assertEqual(os.environ.get("SEARCH_BURST_LIMIT"), "3")


if __name__ == "__main__":
	unittest.main()
