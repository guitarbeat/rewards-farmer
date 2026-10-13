"""Adversarial stress-testing suite for Milestone 2 TUI redesign.

Empirically tests interactive controls, dynamic resizing geometry, profile selection,
task checkbox toggling, dashboard widgets, and control locking of src/launcher_tui.py.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import daily_schedule
import launcher_controller as ctl
import launcher_progress as progress
import launcher_tui
from textual.widgets import Button, Checkbox, ListView, ProgressBar, RichLog, Select, Static, TabbedContent


class Milestone2AdversarialTests(unittest.IsolatedAsyncioTestCase):
	"""Adversarial pilot tests for Milestone 2 TUI controls and layout."""

	def _app(
		self,
		*,
		issues: list[str] | None = None,
		profiles: list[tuple[str, str]] | None = None,
		log_tail: str = "",
	) -> launcher_tui.RewardsFarmerApp:
		detected_profiles = (
			profiles
			if profiles is not None
			else [("Default", "Default profile"), ("Profile 1", "Personal")]
		)
		self._patches = [
			mock.patch("launcher_runtime.preflight_issues", return_value=list(issues or [])),
			mock.patch("launcher_runtime.preflight_warnings", return_value=[]),
			mock.patch("launcher_runtime.read_log_tail", return_value=log_tail),
			mock.patch("launcher_runtime.readiness_summary", return_value="Ready to farm"),
			mock.patch("launcher_runtime.detect_edge_profiles", return_value=detected_profiles),
		]
		for patcher in self._patches:
			patcher.start()
			self.addCleanup(patcher.stop)
		return launcher_tui.RewardsFarmerApp()

	async def test_dynamic_resize_status_visibility_and_bounds(self) -> None:
		"""Mount app at (100, 40) and resize dynamically to (80, 24) and (120, 50).

		Asserts #status remains visible and within screen height without vertical overflow.
		"""
		app = self._app()
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			status = app.query_one("#status", Static)
			self.assertTrue(status.is_mounted)
			self.assertTrue(status.visible)
			self.assertIn("Ready to run", str(status.content))
			# Initial 100x40 geometry
			self.assertEqual(app.size.width, 100)
			self.assertEqual(app.size.height, 40)
			self.assertLess(status.region.y, 40)
			self.assertFalse(app.screen.has_class("compact-height"))

			# Dynamic resize down to compact (80, 24)
			await pilot.resize_terminal(80, 24)
			await pilot.pause()
			status = app.query_one("#status", Static)
			self.assertTrue(status.is_mounted)
			self.assertTrue(status.visible)
			self.assertEqual(app.size.width, 80)
			self.assertEqual(app.size.height, 24)
			# Exact status row must be within screen bounds (row 23 of 24)
			self.assertLess(status.region.y, 24)
			self.assertEqual(status.region.y, 23)
			self.assertTrue(app.screen.has_class("compact-height"))

			# Dynamic resize up to spacious (120, 50)
			await pilot.resize_terminal(120, 50)
			await pilot.pause()
			status = app.query_one("#status", Static)
			self.assertTrue(status.is_mounted)
			self.assertTrue(status.visible)
			self.assertEqual(app.size.width, 120)
			self.assertEqual(app.size.height, 50)
			self.assertLess(status.region.y, 50)
			self.assertFalse(app.screen.has_class("compact-height"))

			# Resize back to (80, 24) to ensure repeated transitions succeed
			await pilot.resize_terminal(80, 24)
			await pilot.pause()
			status = app.query_one("#status", Static)
			self.assertLess(status.region.y, 24)
			self.assertEqual(status.region.y, 23)
			self.assertTrue(app.screen.has_class("compact-height"))

	async def test_task_checkbox_toggle_and_run_button_lock(self) -> None:
		"""Toggle task checkboxes via pilot, asserting controller state and run button disabling."""
		app = self._app()
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			run_btn = app.query_one("#run", Button)
			self.assertFalse(run_btn.disabled)

			# All 7 canonical tasks should initially be enabled in controller
			self.assertEqual(len(app.controller.enabled_tasks), 7)

			# Toggle each checkbox off via pilot interaction
			checkbox_ids = [
				("task-daily-set", "Bing daily set"),
				("task-explore", "Explore on Bing"),
				("task-visual", "Visual search"),
				("task-misc", "Misc cards"),
				("task-quests", "Quests"),
				("task-searches", "Required searches"),
				("task-bonus", "Bonus points"),
			]

			for cb_id, task_name in checkbox_ids:
				cb = app.query_one(f"#{cb_id}", Checkbox)
				self.assertTrue(cb.value)
				self.assertTrue(app.controller.is_task_enabled(task_name))
				# Click to uncheck
				await pilot.click(f"#{cb_id}")
				await pilot.pause()
				self.assertFalse(cb.value)
				self.assertFalse(app.controller.is_task_enabled(task_name))

			# When all 6 tasks are disabled, run button MUST be disabled
			self.assertEqual(len(app.controller.enabled_tasks), 0)
			self.assertTrue(run_btn.disabled)

			# Attempting action_run when all tasks unchecked must not start a run
			with mock.patch.object(app.controller, "start_run") as mock_start:
				app.action_run()
				mock_start.assert_not_called()

			# Re-enable just one task (Searches) via pilot click
			await pilot.click("#task-searches")
			await pilot.pause()
			cb_searches = app.query_one("#task-searches", Checkbox)
			self.assertTrue(cb_searches.value)
			self.assertTrue(app.controller.is_task_enabled("Required searches"))
			self.assertEqual(app.controller.enabled_tasks, {"Required searches"})

			# Run button MUST be re-enabled now
			self.assertFalse(run_btn.disabled)

			# Re-enable the remaining tasks
			for cb_id, task_name in checkbox_ids:
				if cb_id != "task-searches":
					await pilot.click(f"#{cb_id}")
					await pilot.pause()
					self.assertTrue(app.controller.is_task_enabled(task_name))

			self.assertEqual(len(app.controller.enabled_tasks), 7)
			self.assertFalse(run_btn.disabled)

	async def test_profile_selection_via_pilot(self) -> None:
		"""Change profile selection via pilot, asserting controller selected_profile updates."""
		profiles = [
			("Default", "Default profile"),
			("Profile 1", "Personal account"),
			("Profile 2", "Work account"),
		]
		app = self._app(profiles=profiles)
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			select = app.query_one("#profile-select", Select)

			# Verify initial selection defaults to "Default"
			self.assertEqual(select.value, "Default")
			self.assertEqual(app.controller.selected_profile, "Default")

			# Select "Profile 1"
			select.value = "Profile 1"
			await pilot.pause()
			self.assertEqual(app.controller.selected_profile, "Profile 1")
			self.assertEqual(app.controller.build_env()["REWARDS_EDGE_PROFILES"], "Profile 1")

			# Select "all"
			select.value = "all"
			await pilot.pause()
			self.assertEqual(app.controller.selected_profile, "all")
			self.assertEqual(app.controller.build_env()["REWARDS_EDGE_PROFILES"], "all")

			# Select "Profile 2"
			select.value = "Profile 2"
			await pilot.pause()
			self.assertEqual(app.controller.selected_profile, "Profile 2")
			self.assertEqual(app.controller.build_env()["REWARDS_EDGE_PROFILES"], "Profile 2")

	async def test_dashboard_real_time_metrics_and_countdowns(self) -> None:
		"""Verify live dashboard widgets dynamically update from state snapshots."""
		app = self._app()
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			points_widget = app.query_one("#stat-points", Static)
			step_label = app.query_one("#active-step-label", Static)
			step_bar = app.query_one("#active-step-bar", ProgressBar)
			delay_widget = app.query_one("#timer-search-delay", Static)
			sched_widget = app.query_one("#timer-schedule-window", Static)

			# Create synthetic snapshot with active step and points
			fake_rows = [
				progress.StepRow("Bing daily set", "ok"),
				progress.StepRow("Explore on Bing", "ok"),
				progress.StepRow("Visual search", "running", "step 1/3"),
				progress.StepRow("Misc cards", "pending"),
			]
			snap = ctl.LauncherSnapshot(
				subtitle="Farming in progress",
				status_text="Running step 3",
				status_tone="running",
				run_count_label="1 of 1",
				setup_strip="Ready",
				progress_summary="2 of 4 complete",
				progress_rows=fake_rows,
				running=True,
				points_earned=120,
				session_points=350,
				active_step="Visual search",
				active_step_detail="step 1/3",
				search_delay_remaining=14.5,
				daily_schedule_countdown="03:45:12",
			)

			app._on_state_changed(snap)
			await pilot.pause()

			self.assertIn("+120", str(points_widget.content))
			self.assertIn("+350", str(points_widget.content))
			self.assertIn("Visual search", str(step_label.content))
			self.assertIn("step 1/3", str(step_label.content))
			self.assertEqual(step_bar.total, 4)
			self.assertEqual(step_bar.progress, 2)
			self.assertIn("14.5s", str(delay_widget.content))
			self.assertIn("03:45:12", str(sched_widget.content))

	async def test_controls_lock_during_running_session(self) -> None:
		"""Verify profile selector and task checkboxes are locked/disabled while running."""
		app = self._app()
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			select = app.query_one("#profile-select", Select)
			run_btn = app.query_one("#run", Button)
			stop_btn = app.query_one("#stop", Button)

			# Initial state: not running
			self.assertFalse(select.disabled)
			for cb_id in launcher_tui.TASK_TOGGLE_MAP:
				self.assertFalse(app.query_one(f"#{cb_id}", Checkbox).disabled)
			self.assertFalse(run_btn.disabled)
			self.assertTrue(stop_btn.disabled)

			# Transition to running
			running_snap = ctl.LauncherSnapshot(
				subtitle="Running",
				status_text="Active",
				status_tone="running",
				run_count_label="1",
				setup_strip="",
				progress_summary="",
				running=True,
				run_enabled=False,
				stop_enabled=True,
			)
			app._on_state_changed(running_snap)
			await pilot.pause()

			# Controls MUST be locked
			self.assertTrue(select.disabled)
			for cb_id in launcher_tui.TASK_TOGGLE_MAP:
				self.assertTrue(app.query_one(f"#{cb_id}", Checkbox).disabled)
			self.assertTrue(run_btn.disabled)
			self.assertFalse(stop_btn.disabled)

			# Transition back to finished / idle
			idle_snap = ctl.LauncherSnapshot(
				subtitle="Ready",
				status_text="Completed",
				status_tone="success",
				run_count_label="1",
				setup_strip="",
				progress_summary="",
				running=False,
				run_enabled=True,
				stop_enabled=False,
			)
			app._on_state_changed(idle_snap)
			await pilot.pause()

			# Controls MUST be unlocked
			self.assertFalse(select.disabled)
			for cb_id in launcher_tui.TASK_TOGGLE_MAP:
				self.assertFalse(app.query_one(f"#{cb_id}", Checkbox).disabled)
			self.assertFalse(run_btn.disabled)
			self.assertTrue(stop_btn.disabled)

	async def test_tabs_switching_and_log_visibility(self) -> None:
		"""Test switching between Console Log and Past Runs tabs and keyboard action."""
		past_run = (
			"=== Run #1 started 2026-01-01 10:00:00 ===\n"
			"[OK] Bing daily set\n"
			"=== Run finished 10:02:00 (exit 0) ===\n"
		)
		app = self._app(log_tail=past_run)
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			tabs = app.query_one("#panel-tabs", TabbedContent)
			# When history exists on startup, active tab defaults to past runs
			self.assertEqual(tabs.active, "tab-history")

			# Press 'l' key to toggle to log tab
			await pilot.press("l")
			await pilot.pause()
			self.assertEqual(tabs.active, "tab-log")

			# Press 'l' again to toggle back
			await pilot.press("l")
			await pilot.pause()
			self.assertEqual(tabs.active, "tab-history")

	async def test_single_profile_no_all_profiles_option(self) -> None:
		"""When only 1 profile exists, 'All Profiles' option must not be added."""
		app = self._app(profiles=[("Default", "Only Default")])
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			select = app.query_one("#profile-select", Select)
			# There should be only 1 option: ('Only Default', 'Default')
			self.assertEqual(len(select._options), 1)
			self.assertEqual(select.value, "Default")

	async def test_no_detected_profiles_falls_back_cleanly(self) -> None:
		"""When zero profiles are detected, fallback to Default with no crashes."""
		app = self._app(profiles=[])
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			select = app.query_one("#profile-select", Select)
			self.assertEqual(select.value, "Default")
			self.assertEqual(app.controller.selected_profile, "Default")

	async def test_narrow_screen_dynamic_resize_compact_width(self) -> None:
		"""Dynamic resize below width 90 applies .compact-width class."""
		app = self._app()
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			self.assertFalse(app.screen.has_class("compact-width"))

			# Dynamic resize to narrow width
			await pilot.resize_terminal(80, 35)
			await pilot.pause()
			self.assertTrue(app.screen.has_class("compact-width"))
			self.assertFalse(app.screen.has_class("compact-height"))

			# Resize back to wide width
			await pilot.resize_terminal(100, 35)
			await pilot.pause()
			self.assertFalse(app.screen.has_class("compact-width"))

	async def test_clear_log_button_clears_log_panel(self) -> None:
		"""Clicking Clear button invokes controller.clear_log and clears RichLog."""
		app = self._app(log_tail="Line 1\nLine 2\n")
		async with app.run_test(size=(100, 40)) as pilot:
			await pilot.pause()
			log_widget = app.query_one("#log", RichLog)
			self.assertGreater(len(log_widget.lines), 0)

			with mock.patch.object(app.controller, "clear_log", return_value=None) as mock_clear:
				await pilot.click("#clear-log")
				await pilot.pause()
				mock_clear.assert_called_once()
				self.assertEqual(len(log_widget.lines), 0)


if __name__ == "__main__":
	unittest.main()
