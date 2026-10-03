"""Pilot tests for the Textual launcher."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import launcher_tui
import daily_schedule
from textual.widgets import Button, ListItem, RichLog, Static

_PAST_RUN = (
	"=== Run #4 started 2026-01-02 11:00:00 ===\n"
	"[OK] Bing daily set\n"
	"=== Run finished 11:05:00 (exit 0) ===\n"
)


class LauncherTuiTests(unittest.IsolatedAsyncioTestCase):
	def _app(self, *, issues: list[str] | None = None, log_tail: str = "") -> launcher_tui.RewardsFarmerApp:
		self._patches = [
			mock.patch("launcher_runtime.preflight_issues", return_value=list(issues or [])),
			mock.patch("launcher_runtime.preflight_warnings", return_value=[]),
			mock.patch("launcher_runtime.read_log_tail", return_value=log_tail),
			mock.patch("launcher_runtime.readiness_summary", return_value="Ready to farm"),
		]
		for patcher in self._patches:
			patcher.start()
			self.addCleanup(patcher.stop)
		return launcher_tui.RewardsFarmerApp()

	async def test_bootstrap_snapshot_enables_run(self) -> None:
		app = self._app()
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			self.assertEqual(app.sub_title, "Ready to farm")
			self.assertIn("Ready to run", str(app.query_one("#status", Static).content))
			self.assertFalse(app.query_one("#run", Button).disabled)
			self.assertTrue(app.query_one("#stop", Button).disabled)
			self.assertGreaterEqual(len(app.query("#progress Static")), 1)

	async def test_run_disabled_when_preflight_fails(self) -> None:
		app = self._app(issues=["Missing data-dir"])
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			self.assertTrue(app.query_one("#run", Button).disabled)
			self.assertEqual(app.sub_title, "Missing data-dir")

	async def test_history_row_opens_that_run_log(self) -> None:
		app = self._app(log_tail=_PAST_RUN)
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			items = list(app.query("#history ListItem"))
			self.assertTrue(any("4" in str(item.name) or "#4" in str(item) for item in items))
			await pilot.click("#history ListItem")
			await pilot.pause()
			log_text = app.query_one("#log", RichLog).lines
			joined = "\n".join(line.text for line in log_text)
			self.assertIn("Run #4 started", joined)
			self.assertTrue(app.query_one("#log-panel").display)

	async def test_prefixed_step_line_updates_progress_row(self) -> None:
		app = self._app()
		async with app.run_test(size=(100, 24)) as pilot:
			await pilot.pause()
			app.controller._reset_progress_for_run()
			app.controller._process_log_text(
				"09:23:01 INFO     rewards_tasks: [STEP] Starting browser\n",
				to_file=False,
			)
			await pilot.pause()
			running = list(app.query("#progress .step-running"))
			self.assertEqual(len(running), 1)
			self.assertIn("Starting browser", str(running[0].content))
			self.assertIn("0 of 7 complete", str(app.query_one("#progress-summary", Static).content))
			status = app.query_one("#status", Static)
			self.assertIn("Starting browser", str(status.content))
			self.assertLess(status.region.y, app.size.height)

	async def test_daily_key_shows_the_learned_window(self) -> None:
		app = self._app()
		plan = daily_schedule.DailyPlan(9 * 60 + 15, 75, 3, False)
		result = daily_schedule.InstallResult(daily_schedule.status_line(plan), plan)
		with mock.patch.object(daily_schedule, "install_daily_trigger", return_value=result):
			async with app.run_test(size=(80, 24)) as pilot:
				await pilot.pause()
				await pilot.press("d")
				await pilot.pause()
				text = str(app.query_one("#schedule", Static).content)
				self.assertIn("09:15", text)
				self.assertIn("from 3 runs", text)

	async def test_stop_while_idle_leaves_run_enabled(self) -> None:
		app = self._app()
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			await pilot.press("escape")
			await pilot.pause()
			self.assertFalse(app.query_one("#run", Button).disabled)
			self.assertTrue(app.query_one("#stop", Button).disabled)
			self.assertFalse(app.controller.is_run_active())


if __name__ == "__main__":
	unittest.main()
