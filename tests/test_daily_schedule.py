"""Tests for the smart daily trigger."""

from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import daily_schedule as schedule


def _ok_run(hour: int, *, exit_code: int = 0) -> str:
	return (
		f"=== Run #1 started 2026-01-01 {hour:02d}:05:00 ===\n"
		"[OK] Bing daily set\n"
		f"=== Run finished {hour:02d}:10:00 (exit {exit_code}) ===\n"
	)


class PlanTests(unittest.TestCase):
	def test_empty_history_uses_morning_window(self) -> None:
		plan = schedule.plan_from_history("")
		self.assertEqual(plan.start_minute, 9 * 60 + 15)
		self.assertEqual(plan.learned_from, 0)
		self.assertFalse(plan.clamped)
		self.assertIn("09:15", schedule.status_line(plan))

	def test_successful_evening_runs_set_the_window(self) -> None:
		log = _ok_run(18) + _ok_run(19) + _ok_run(3, exit_code=1)
		plan = schedule.plan_from_history(log)
		self.assertEqual(plan.start_minute, 18 * 60 + 15)
		self.assertEqual(plan.learned_from, 2)
		self.assertFalse(plan.clamped)

	def test_overnight_success_is_kept_in_daytime(self) -> None:
		plan = schedule.plan_from_history(_ok_run(3) + _ok_run(4))
		self.assertEqual(plan.start_minute, 8 * 60 + 15)
		self.assertTrue(plan.clamped)
		self.assertIn("daytime only", schedule.status_line(plan))


class TimingTests(unittest.TestCase):
	def test_wait_is_stable_for_the_day_and_zero_after_the_instant(self) -> None:
		plan = schedule.DailyPlan(9 * 60 + 15, 75, 0, False)
		start = datetime(2026, 10, 3, 9, 15, 0)
		rng = random.Random(start.date().isoformat())
		offset = rng.randrange(0, 75 * 60)
		self.assertEqual(schedule.wait_seconds(start, plan, random.Random(start.date().isoformat())), offset)

		later = start + timedelta(seconds=offset + 5)
		self.assertEqual(schedule.wait_seconds(later, plan, random.Random(start.date().isoformat())), 0)

	def test_early_login_waits_longer_than_the_window(self) -> None:
		plan = schedule.DailyPlan(9 * 60 + 15, 75, 0, False)
		early = datetime(2026, 10, 3, 7, 0, 0)
		wait = schedule.wait_seconds(early, plan, random.Random(early.date().isoformat()))
		self.assertGreater(wait, plan.window_minutes * 60)

	def test_autostart_covers_the_window_and_a_short_grace(self) -> None:
		plan = schedule.DailyPlan(9 * 60 + 15, 75, 0, False)
		start = datetime(2026, 10, 3, 9, 15, 0)
		offset = random.Random(start.date().isoformat()).randrange(0, 75 * 60)
		target = start + timedelta(seconds=offset)
		self.assertTrue(schedule.autostart_due(target, plan, claimed=False, unfinished=True))
		self.assertFalse(schedule.autostart_due(target - timedelta(seconds=1), plan, claimed=False, unfinished=True))
		self.assertFalse(schedule.autostart_due(target, plan, claimed=True, unfinished=True))
		too_late = start + timedelta(minutes=75, hours=3, seconds=offset + 1)
		self.assertFalse(schedule.autostart_due(too_late, plan, claimed=False, unfinished=True))


class ClaimTests(unittest.TestCase):
	def test_claim_is_once_per_day_and_can_be_released(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			path = os.path.join(temp_dir, "claim.txt")
			self.assertTrue(schedule.claim_today(path, "2026-10-03"))
			self.assertFalse(schedule.claim_today(path, "2026-10-03"))
			self.assertTrue(schedule.claimed_today(path, "2026-10-03"))
			schedule.release_claim(path, "2026-10-03")
			self.assertTrue(schedule.claim_today(path, "2026-10-03"))


class InstallTests(unittest.TestCase):
	def test_linux_timer_persists_across_sleep(self) -> None:
		calls: list[list[str]] = []

		def runner(command, **_kwargs):
			calls.append(list(command))
			return subprocess.CompletedProcess(command, 0, "", "")

		with tempfile.TemporaryDirectory() as temp_dir:
			plan_path = os.path.join(temp_dir, "plan.json")
			with mock.patch.object(schedule, "PLAN_FILE", plan_path):
				result = schedule.install_daily_trigger(
					platform="linux",
					home=temp_dir,
					log_text="",
					runner=runner,
				)
			timer = os.path.join(temp_dir, ".config", "systemd", "user", "rewards-farmer.timer")
			with open(timer, encoding="utf-8") as handle:
				body = handle.read()
			self.assertIn("Persistent=true", body)
			self.assertIn("OnCalendar=*-*-* 09:15:00", body)
			self.assertIn("09:15", result.status_line)
			self.assertTrue(any(command[:3] == ["systemctl", "--user", "enable"] for command in calls))

	def test_windows_xml_catches_up_after_sleep(self) -> None:
		plan = schedule.DailyPlan(9 * 60 + 15, 75, 0, False)
		xml = schedule.windows_task_xml(
			plan,
			python=r"C:\venv\python.exe",
			script=r"C:\repo\src\daily_schedule.py",
			workdir=r"C:\repo",
			day=datetime(2026, 10, 3, 12, 0, 0),
		)
		self.assertIn("<StartWhenAvailable>true</StartWhenAvailable>", xml)
		self.assertIn("2026-10-03T09:15:00", xml)
		self.assertIn("--run", xml)

	def test_scheduled_run_skips_when_the_ui_is_open(self) -> None:
		spawned: list[str] = []
		with mock.patch.object(schedule.runtime, "launcher_ui_is_open", return_value=True):
			code = schedule.run_scheduled(spawn=lambda: spawned.append("ran") or 0)
		self.assertEqual(code, 0)
		self.assertEqual(spawned, [])

	def test_scheduled_run_after_the_window_starts_the_bot_once(self) -> None:
		plan = schedule.DailyPlan(9 * 60 + 15, 75, 0, False)
		with tempfile.TemporaryDirectory() as temp_dir:
			claim = os.path.join(temp_dir, "claim.txt")
			spawned: list[int] = []
			with mock.patch.object(schedule, "CLAIM_FILE", claim):
				with mock.patch.object(schedule.runtime, "launcher_ui_is_open", return_value=False):
					with mock.patch.object(schedule, "unfinished_accounts", return_value=True):
						code = schedule.run_scheduled(
							now=datetime(2026, 10, 3, 18, 0, 0),
							plan=plan,
							sleep=lambda _seconds: self.fail("catch-up should not sleep"),
							spawn=lambda: spawned.append(1) or 0,
						)
			self.assertEqual(code, 0)
			self.assertEqual(spawned, [1])
			self.assertTrue(schedule.claimed_today(claim, "2026-10-03"))


if __name__ == "__main__":
	unittest.main()
