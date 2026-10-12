"""Adversarial stress-testing suite for Milestone 1 changes.

Empirically tests LauncherController, RunProgress, launcher_runtime,
and runner task filtering against edge cases, rapid toggles, malformed logs,
and boundary conditions.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import accounts
import launcher_controller as ctl
import launcher_progress as progress
import launcher_runtime as runtime
from sites.ms_rewards.steps import AUTOMATION_TASK_STEPS, REQUIRED_SEARCHES
import task_steps


class TaskTogglingStressTests(unittest.TestCase):
	"""Stress test task toggling combinations, concurrency, and validation."""

	def test_all_tasks_enabled_by_default(self) -> None:
		controller = ctl.LauncherController()
		self.assertEqual(controller.enabled_tasks, set(AUTOMATION_TASK_STEPS))
		snap = controller.initial_snapshot()
		self.assertEqual(len(snap.enabled_tasks), len(AUTOMATION_TASK_STEPS))
		for step in AUTOMATION_TASK_STEPS:
			self.assertTrue(snap.enabled_tasks[step])

	def test_toggle_all_tasks_off_and_on(self) -> None:
		controller = ctl.LauncherController()

		# Toggle every task off
		for step in AUTOMATION_TASK_STEPS:
			state = controller.toggle_task(step)
			self.assertFalse(state)
			self.assertFalse(controller.is_task_enabled(step))

		self.assertEqual(controller.enabled_tasks, set())
		snap = controller._make_snapshot()
		self.assertEqual(snap.enabled_tasks, {s: False for s in AUTOMATION_TASK_STEPS})
		env = controller.build_env()
		self.assertEqual(env["REWARDS_ENABLED_TASKS"], "")

		# Toggle every task back on
		for step in AUTOMATION_TASK_STEPS:
			state = controller.toggle_task(step)
			self.assertTrue(state)
			self.assertTrue(controller.is_task_enabled(step))

		self.assertEqual(controller.enabled_tasks, set(AUTOMATION_TASK_STEPS))
		snap2 = controller._make_snapshot()
		self.assertEqual(snap2.enabled_tasks, {s: True for s in AUTOMATION_TASK_STEPS})

	def test_explicit_boolean_toggle_idempotency(self) -> None:
		controller = ctl.LauncherController()
		task = "Visual search"

		# Setting already True to True
		self.assertTrue(controller.toggle_task(task, enabled=True))
		self.assertTrue(controller.is_task_enabled(task))
		self.assertTrue(controller.toggle_task(task, enabled=True))
		self.assertTrue(controller.is_task_enabled(task))

		# Setting to False multiple times
		self.assertFalse(controller.toggle_task(task, enabled=False))
		self.assertFalse(controller.is_task_enabled(task))
		self.assertFalse(controller.toggle_task(task, enabled=False))
		self.assertFalse(controller.is_task_enabled(task))

	def test_set_enabled_tasks_various_subsets(self) -> None:
		controller = ctl.LauncherController()

		# Single task subsets
		for step in AUTOMATION_TASK_STEPS:
			controller.set_enabled_tasks([step])
			self.assertEqual(controller.enabled_tasks, {step})
			env = controller.build_env()
			self.assertEqual(env["REWARDS_ENABLED_TASKS"], step)
			snap = controller._make_snapshot()
			for s in AUTOMATION_TASK_STEPS:
				self.assertEqual(snap.enabled_tasks[s], (s == step))

		# Empty subset
		controller.set_enabled_tasks([])
		self.assertEqual(controller.enabled_tasks, set())
		self.assertEqual(controller.build_env()["REWARDS_ENABLED_TASKS"], "")

		# Multi-task arbitrary subset
		subset = ["Bing daily set", "Bonus points"]
		controller.set_enabled_tasks(subset)
		self.assertEqual(controller.enabled_tasks, set(subset))
		env = controller.build_env()
		self.assertEqual(env["REWARDS_ENABLED_TASKS"], "Bing daily set,Bonus points")

	def test_invalid_task_names_raise_value_error_without_corrupting_state(self) -> None:
		controller = ctl.LauncherController()
		initial_set = set(controller.enabled_tasks)

		with self.assertRaises(ValueError):
			controller.toggle_task("Nonexistent Task")
		self.assertEqual(controller.enabled_tasks, initial_set)

		with self.assertRaises(ValueError):
			controller.set_task_enabled("Another Invalid", True)
		self.assertEqual(controller.enabled_tasks, initial_set)

		with self.assertRaises(ValueError):
			controller.set_enabled_tasks(["Bing daily set", "Invalid Task"])
		# State should remain untouched
		self.assertEqual(controller.enabled_tasks, initial_set)

	def test_concurrent_task_toggling(self) -> None:
		"""Stress test toggling from multiple threads rapidly."""
		controller = ctl.LauncherController()

		def worker(thread_id: int) -> None:
			for i in range(100):
				task = AUTOMATION_TASK_STEPS[i % len(AUTOMATION_TASK_STEPS)]
				controller.toggle_task(task)

		with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
			futures = [executor.submit(worker, tid) for tid in range(4)]
			for f in futures:
				f.result()

		# Every task in enabled_tasks should still be a valid canonical task
		for t in controller.enabled_tasks:
			self.assertIn(t, AUTOMATION_TASK_STEPS)
		snap = controller._make_snapshot()
		self.assertIsInstance(snap.enabled_tasks, dict)

	def test_visual_search_image_prep_gating(self) -> None:
		"""Verify image preparation is triggered only when Visual search is enabled and image is missing."""
		controller = ctl.LauncherController()

		# Visual search disabled -> no thread spawned, no prep
		controller.set_task_enabled("Visual search", False)
		with mock.patch("launcher_runtime.os.path.isfile", return_value=False):
			with mock.patch.object(controller, "_spawn_bot"):
				with mock.patch("threading.Thread") as mock_thread:
					controller.start_run()
					mock_thread.assert_not_called()
					self.assertFalse(controller._preparing_image)

		# Visual search enabled + image exists -> no prep
		controller.set_task_enabled("Visual search", True)
		with mock.patch("launcher_runtime.os.path.isfile", return_value=True):
			with mock.patch.object(controller, "_spawn_bot"):
				with mock.patch("threading.Thread") as mock_thread:
					controller.start_run()
					mock_thread.assert_not_called()
					self.assertFalse(controller._preparing_image)

		# Visual search enabled + image missing -> prep thread spawned
		with mock.patch("launcher_runtime.os.path.isfile", return_value=False):
			with mock.patch("threading.Thread") as mock_thread:
				mock_inst = mock.Mock()
				mock_thread.return_value = mock_inst
				controller.start_run()
				self.assertTrue(controller._preparing_image)
				mock_thread.assert_called_once()
				mock_inst.start.assert_called_once()


class ProfileSelectionEdgeCaseTests(unittest.TestCase):
	"""Edge cases in profile selection, detection, and env propagation."""

	def test_profile_none(self) -> None:
		controller = ctl.LauncherController()
		controller.set_selected_profile(None)
		self.assertIsNone(controller.selected_profile)
		self.assertIsNone(controller._make_snapshot().selected_profile)
		self.assertIn("Edge profile", controller.setup_strip_text())
		env = controller.build_env()
		self.assertNotIn(accounts.EDGE_PROFILES_ENV_VAR, env)

	def test_profile_empty_string(self) -> None:
		controller = ctl.LauncherController()
		controller.set_selected_profile("")
		self.assertEqual(controller.selected_profile, "")
		self.assertEqual(controller._make_snapshot().selected_profile, "")
		# Empty string treated as falsy in setup_strip_text fallback
		self.assertIn("Edge profile", controller.setup_strip_text())
		env = controller.build_env()
		# Empty string should not be exported as edge profiles
		self.assertNotIn(accounts.EDGE_PROFILES_ENV_VAR, env)

	def test_profile_default(self) -> None:
		controller = ctl.LauncherController()
		controller.set_selected_profile("Default")
		self.assertEqual(controller.selected_profile, "Default")
		self.assertEqual(controller._make_snapshot().selected_profile, "Default")
		self.assertIn("Default", controller.setup_strip_text())
		env = controller.build_env()
		self.assertEqual(env[accounts.EDGE_PROFILES_ENV_VAR], "Default")

	def test_profile_with_spaces_and_special_characters(self) -> None:
		special_profiles = [
			"Profile 99",
			"Work & Personal",
			"User_123-Test.Account",
			"Profile (Home)",
			"Special #$%!@*",
		]
		for prof in special_profiles:
			controller = ctl.LauncherController()
			controller.set_selected_profile(prof)
			self.assertEqual(controller.selected_profile, prof)
			self.assertEqual(controller._make_snapshot().selected_profile, prof)
			self.assertIn(prof, controller.setup_strip_text())
			env = controller.build_env()
			self.assertEqual(env[accounts.EDGE_PROFILES_ENV_VAR], prof)

	def test_detect_edge_profiles_handles_missing_and_corrupt_directories(self) -> None:
		# Non-existent directory
		profiles = runtime.detect_edge_profiles("C:\\nonexistent_dir_123456")
		self.assertEqual(profiles, [("Default", "Default profile")])

		# Directory without Local State
		with tempfile.TemporaryDirectory() as tmpdir:
			profiles = runtime.detect_edge_profiles(tmpdir)
			self.assertEqual(profiles, [("Default", "Default profile")])

			# Corrupt Local State file
			local_state_path = os.path.join(tmpdir, "Local State")
			with open(local_state_path, "w", encoding="utf-8") as f:
				f.write("{invalid json content!!!")
			profiles = runtime.detect_edge_profiles(tmpdir)
			self.assertEqual(profiles, [("Default", "Default profile")])

	def test_detect_edge_profiles_with_valid_local_state(self) -> None:
		with tempfile.TemporaryDirectory() as tmpdir:
			local_state = {
				"profile": {
					"info_cache": {
						"Default": {
							"name": "Personal",
							"user_name": "personal@example.com",
						},
						"Profile 1": {
							"name": "Work",
							"user_name": "work@example.com",
						},
					}
				}
			}
			with open(os.path.join(tmpdir, "Local State"), "w", encoding="utf-8") as f:
				json.dump(local_state, f)
			os.makedirs(os.path.join(tmpdir, "Default"), exist_ok=True)
			os.makedirs(os.path.join(tmpdir, "Profile 1"), exist_ok=True)

			profiles = runtime.detect_edge_profiles(tmpdir)
			self.assertEqual(len(profiles), 2)
			self.assertEqual(profiles[0][0], "Default")
			self.assertIn("Personal", profiles[0][1])
			self.assertEqual(profiles[1][0], "Profile 1")
			self.assertIn("Work", profiles[1][1])


class LogIngestionAndPointsTrackingStressTests(unittest.TestCase):
	"""Stress test log ingestion, points calculations, and edge cases."""

	def test_full_normal_search_progression(self) -> None:
		p = progress.RunProgress()
		p.reset()

		p.update_from_line("Search points before: 0/30")
		self.assertEqual(p.points_earned, 0)
		self.assertEqual(p.session_points, 0)

		p.update_from_line("Round 1: 5 searches -> 15/30")
		self.assertEqual(p.points_earned, 15)
		self.assertEqual(p.session_points, 15)

		p.update_from_line("Round 2: 5 searches -> 30/30")
		self.assertEqual(p.points_earned, 30)
		self.assertEqual(p.session_points, 30)

		p.update_from_line("Search quota complete: 30/30")
		self.assertEqual(p.points_earned, 30)
		self.assertEqual(p.session_points, 30)

		# [OK] Required searches should NOT double-count since search points were tracked
		p.update_from_line("[OK] Required searches")
		self.assertEqual(p.points_earned, 30)
		self.assertEqual(p.session_points, 30)

	def test_baseline_nonzero_points_before(self) -> None:
		p = progress.RunProgress()
		p.reset()

		p.update_from_line("Search points before: 20/60")
		self.assertEqual(p.points_earned, 0)

		p.update_from_line("Search quota complete: 60/60")
		self.assertEqual(p.points_earned, 40)
		self.assertEqual(p.session_points, 40)

	def test_duplicate_quota_lines_do_not_re_accumulate_points(self) -> None:
		p = progress.RunProgress()
		p.reset()

		p.update_from_line("Search points before: 10/50")
		p.update_from_line("Search points before: 10/50")
		p.update_from_line("Search points before: 10/50")
		self.assertEqual(p.points_earned, 0)

		p.update_from_line("Round 1: 5 searches -> 25/50")
		p.update_from_line("Round 1: 5 searches -> 25/50")
		self.assertEqual(p.points_earned, 15)
		self.assertEqual(p.session_points, 15)

		p.update_from_line("Search quota complete: 50/50")
		p.update_from_line("Search quota complete: 50/50")
		p.update_from_line("Search quota complete: 50/50")
		self.assertEqual(p.points_earned, 40)
		self.assertEqual(p.session_points, 40)

	def test_duplicate_ok_marker_is_idempotent(self) -> None:
		"""BUG 1: Ingesting duplicate [OK] lines for a task double-counts points."""
		p = progress.RunProgress()
		p.reset()

		p.update_from_line("[OK] Bing daily set")
		self.assertEqual(p.points_earned, 30)

		# Duplicate [OK] for same task should not re-add 30 points
		p.update_from_line("[OK] Bing daily set")
		self.assertEqual(p.points_earned, 30)

	def test_out_of_order_quota_after_ok_replaces_fallback(self) -> None:
		"""BUG 2: Ingesting [OK] Required searches before quota complete double-counts points."""
		p = progress.RunProgress()
		p.reset()

		# Fallback points (30) awarded when no quota has been parsed yet
		p.update_from_line("[OK] Required searches")
		self.assertEqual(p.points_earned, 30)

		# When quota arrives later, it cleanly replaces the fallback
		p.update_from_line("Search quota complete: 30/30")
		self.assertEqual(p.points_earned, 30)

	def test_session_points_immune_to_non_monotonic_fluctuation(self) -> None:
		"""BUG 3: Non-monotonic quota drops and rises inflate session_points."""
		p = progress.RunProgress()
		p.reset()

		p.update_from_line("Search points before: 20/100")
		p.update_from_line("Search quota complete: 30/100")
		self.assertEqual(p.session_points, 10)

		# Quota drops temporarily (delta < 0, session_points remains 10)
		p.update_from_line("Search quota complete: 20/100")
		self.assertEqual(p.session_points, 10)

		# Quota returns to 30/100 (session_points does not re-add 10)
		p.update_from_line("Search quota complete: 30/100")
		self.assertEqual(p.session_points, 10)

	def test_negative_deltas_clamped_to_zero(self) -> None:
		p = progress.RunProgress()
		p.reset()

		# Case 1: End points reported as less than start points
		p.update_from_line("Search points before: 50/100")
		p.update_from_line("Search quota complete: 20/100")
		self.assertEqual(p.points_earned, 0)
		self.assertEqual(p.session_points, 0)

	def test_malformed_and_adversarial_log_lines(self) -> None:
		p = progress.RunProgress()
		p.reset()

		malformed_lines = [
			"",
			"   ",
			"Search points before:",
			"Search points before: ",
			"Search points before: invalid/data",
			"Search points before: /50",
			"Search points before: 50/",
			"Search points before: -10/50",
			"Search points before: 10/-50",
			"Search points before: 10 50",
			"Search points before: None/None",
			"Search points before: 10/20/30",
			"Search quota complete:",
			"Search quota complete: corrupted_token",
			"Search quota complete: 0/0",
			"searches ->",
			"searches -> None",
			"searches -> /",
			"searches -> " + "x" * 500,
			"[OK] " + "y" * 1000,
			"[STEP] Unknown step name not in tasks",
			"[FAIL] Unknown step failure",
			"random noise line with no structure 12345 67890",
			"A" * 10000,  # very long string
		]

		for line in malformed_lines:
			try:
				p.update_from_line(line)
			except Exception as exc:
				self.fail(f"update_from_line crashed on malformed line: {line!r} with {exc}")

		# Progress state should remain valid
		self.assertIsInstance(p.points_earned, int)
		self.assertIsInstance(p.session_points, int)
		self.assertGreaterEqual(p.points_earned, 0)
		self.assertGreaterEqual(p.session_points, 0)

	def test_all_standard_task_completion_points(self) -> None:
		p = progress.RunProgress()
		p.reset()

		# Bing daily set (30)
		p.update_from_line("[OK] Bing daily set")
		self.assertEqual(p.points_earned, 30)

		# Explore on Bing (15)
		p.update_from_line("[OK] Explore on Bing")
		self.assertEqual(p.points_earned, 45)

		# Visual search (5)
		p.update_from_line("[OK] Visual search")
		self.assertEqual(p.points_earned, 50)

		# Misc cards (10)
		p.update_from_line("[OK] Misc cards")
		self.assertEqual(p.points_earned, 60)

		# Bonus points (5)
		p.update_from_line("[OK] Bonus points")
		self.assertEqual(p.points_earned, 65)

		# Required searches without quota logs (fallback: 30)
		p.update_from_line("[OK] Required searches")
		self.assertEqual(p.points_earned, 95)
		self.assertEqual(p.session_points, 95)

	def test_skipped_and_failed_tasks_earn_zero_points(self) -> None:
		p = progress.RunProgress()
		p.reset()

		p.update_from_line("[SKIP] Bing daily set: disabled in configuration")
		p.update_from_line("[FAIL] Visual search: image error")
		p.update_from_line("[SKIP] Misc cards: skipped")
		self.assertEqual(p.points_earned, 0)
		self.assertEqual(p.session_points, 0)
		self.assertEqual(p.skip_count(), 2)
		self.assertEqual(p.fail_count(), 1)

	def test_session_points_persists_across_runs_and_resets_on_clear(self) -> None:
		controller = ctl.LauncherController()

		# Run 1
		controller._reset_progress_for_run()
		controller._process_log_text("[OK] Bing daily set\n", to_file=False)
		self.assertEqual(controller.run_progress.points_earned, 30)
		self.assertEqual(controller.session_points, 30)

		# Run 2
		controller._reset_progress_for_run()
		self.assertEqual(controller.run_progress.points_earned, 0)
		self.assertEqual(controller.session_points, 30)
		controller._process_log_text("[OK] Explore on Bing\n", to_file=False)
		self.assertEqual(controller.run_progress.points_earned, 15)
		self.assertEqual(controller.session_points, 45)

		# Clear log resets session points
		controller.clear_log()
		self.assertEqual(controller.session_points, 0)

	def test_active_step_and_active_step_detail_lifecycle(self) -> None:
		p = progress.RunProgress()
		p.reset()

		# Starting browser
		p.update_from_line("[STEP] Starting browser")
		self.assertEqual(p.active_step(), "Starting browser")

		# First task starts
		p.update_from_line("[STEP] Bing daily set")
		self.assertEqual(p.active_step(), "Bing daily set")
		self.assertEqual(p.active_step_detail(), "")

		# First task completes
		p.update_from_line("[OK] Bing daily set")
		# Next pending task auto-transitions to running
		self.assertEqual(p.active_step(), "Explore on Bing")

		# Finished run
		p.finish()
		self.assertIsNone(p.active_step())
		self.assertEqual(p.active_step_detail(), "")

	def test_search_delay_countdown_in_controller(self) -> None:
		controller = ctl.LauncherController()
		self.assertIsNone(controller.get_search_delay_remaining())

		# Historical or idle replay does not activate delay when not running
		controller._process_log_text("[DELAY] 10\n", to_file=False)
		self.assertIsNone(controller.get_search_delay_remaining())

		# Process log line with delay tag during active run
		controller._running = True
		controller._process_log_text("[DELAY] 10\n", to_file=False)
		remaining = controller.get_search_delay_remaining()
		self.assertIsNotNone(remaining)
		self.assertGreater(remaining, 8.0)
		self.assertLessEqual(remaining, 10.0)

		# Explicit negative delay clears/expires immediately
		controller.set_search_delay(-5)
		self.assertIsNone(controller.get_search_delay_remaining())

		# Stop run clears delay when running
		controller.set_search_delay(20)
		self.assertIsNotNone(controller.get_search_delay_remaining())
		mock_proc = mock.Mock()
		mock_proc.poll.return_value = None
		controller.process = mock_proc
		controller.stop_run()
		self.assertIsNone(controller.get_search_delay_remaining())

	def test_daily_window_countdown_calculation(self) -> None:
		mock_plan = mock.Mock(start_minute=600, window_minutes=60)

		# 1 hour before window (start at 10:00, current at 09:00)
		dt_before = datetime(2026, 10, 11, 9, 0, 0)
		with mock.patch("daily_schedule.load_plan", return_value=mock_plan):
			with mock.patch("daily_schedule.claimed_today", return_value=False):
				cd = runtime.get_daily_window_countdown(now=dt_before)
				self.assertEqual(cd, "in 01h 00m")

		# Inside active window (10:15)
		dt_active = datetime(2026, 10, 11, 10, 15, 0)
		with mock.patch("daily_schedule.load_plan", return_value=mock_plan):
			with mock.patch("daily_schedule.claimed_today", return_value=False):
				cd = runtime.get_daily_window_countdown(now=dt_active)
				self.assertEqual(cd, "active (45m left)")

		# Past window (11:05) -> returns None
		dt_past = datetime(2026, 10, 11, 11, 5, 0)
		with mock.patch("daily_schedule.load_plan", return_value=mock_plan):
			with mock.patch("daily_schedule.claimed_today", return_value=False):
				cd = runtime.get_daily_window_countdown(now=dt_past)
				self.assertIsNone(cd)


class RunnerTaskFilterIntegrationTests(unittest.TestCase):
	"""Test runner.py complete_all_tasks() honoring REWARDS_ENABLED_TASKS."""

	def test_runner_filters_disabled_tasks(self) -> None:
		from sites.ms_rewards.runner import RewardsTaskUtils

		class DummyRunner(RewardsTaskUtils):
			def __init__(self) -> None:
				self.executed: list[str] = []
				self.driver = mock.Mock()
				self.elements = mock.Mock()
				self.progress = None

			def complete_bing_daily_set(self) -> bool:
				self.executed.append("Bing daily set")
				return True

			def complete_explore_on_bing_tasks(self) -> bool:
				self.executed.append("Explore on Bing")
				return True

			def complete_visual_search(self) -> bool:
				self.executed.append("Visual search")
				return True

			def complete_misc_cards(self) -> bool:
				self.executed.append("Misc cards")
				return True

			def complete_required_searches(self) -> bool:
				self.executed.append("Required searches")
				return True

			def claim_bonus_points(self) -> bool:
				self.executed.append("Bonus points")
				return True

			def restore_main_tab(self) -> None:
				pass

			def return_to_rewards_home(self) -> None:
				pass

		# Case 1: Subset enabled
		with mock.patch.dict(os.environ, {"REWARDS_ENABLED_TASKS": "Bing daily set,Misc cards"}):
			runner = DummyRunner()
			runner.complete_all_tasks()
			self.assertEqual(runner.executed, ["Bing daily set", "Misc cards"])

		# Case 2: All disabled
		with mock.patch.dict(os.environ, {"REWARDS_ENABLED_TASKS": ""}):
			runner = DummyRunner()
			runner.complete_all_tasks()
			self.assertEqual(runner.executed, [])

		# Case 3: Env var unset (default all enabled)
		env_copy = os.environ.copy()
		env_copy.pop("REWARDS_ENABLED_TASKS", None)
		with mock.patch.dict(os.environ, env_copy, clear=True):
			runner = DummyRunner()
			runner.complete_all_tasks()
			self.assertEqual(len(runner.executed), len(AUTOMATION_TASK_STEPS))


if __name__ == "__main__":
	unittest.main()
