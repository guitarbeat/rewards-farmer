"""Usability-focused tests for the desktop launcher."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import launcher_controller as ctl
import launcher_progress as progress
import launcher_runtime as runtime
import site_registry
import task_steps


class LauncherControllerTests(unittest.TestCase):
	def test_build_env_uses_ms_rewards_and_default_profile(self) -> None:
		controller = ctl.LauncherController()
		env = controller.build_env()
		self.assertEqual(env[site_registry.ENV_VAR], "ms_rewards")
		self.assertEqual(env[ctl.GUI_ENV_FLAG], "1")
		self.assertEqual(env["QUERY_SOURCE"], "trends")
		self.assertNotIn("REWARDS_ACCOUNTS", env)

	def test_build_env_respects_existing_query_source(self) -> None:
		with mock.patch.dict(os.environ, {"QUERY_SOURCE": "llm"}):
			env = ctl.LauncherController().build_env()
		self.assertEqual(env["QUERY_SOURCE"], "llm")

	def test_process_log_updates_progress_during_run(self) -> None:
		controller = ctl.LauncherController()
		controller._reset_progress_for_run()
		controller._process_log_text("[STEP] Starting browser\n", to_file=False)
		controller._process_log_text("[STEP] Bing daily set\n", to_file=False)
		self.assertEqual(controller.run_progress.task_states["Bing daily set"].state, "running")

	def test_start_run_blocked_when_preflight_fails(self) -> None:
		with mock.patch.object(runtime, "preflight_issues", return_value=["Missing setup"]):
			controller = ctl.LauncherController()
		error = controller.start_run()
		self.assertEqual(error, "Missing setup")

	def test_clear_log_blocked_while_running(self) -> None:
		controller = ctl.LauncherController()
		controller.process = mock.Mock()
		controller.process.poll.return_value = None
		self.assertEqual(controller.clear_log(), "Stop the current run before clearing the log.")

	def test_finish_run_summarizes_failures(self) -> None:
		controller = ctl.LauncherController()
		controller.run_count = 1
		controller._progress_running = True
		controller._process_log_text("\n=== Run #1 started 2026-01-01 12:00:00 ===\n", to_file=False)
		controller._process_log_text("[FAIL] something broke\n", to_file=False)
		controller.process = mock.Mock()
		controller.process.poll.return_value = 1
		controller._finish_run()
		text, _tone = runtime.summarize_last_run(
			controller.get_log_text(),
			1,
			exit_code=1,
			stopped_by_user=False,
		)
		self.assertEqual(text, "Done with 1 error — check log")

	def test_prepare_image_worker_queues_spawn_without_ui_callbacks(self) -> None:
		logs: list[str] = []
		states: list[object] = []
		controller = ctl.LauncherController(
			on_log_line=lambda line, _tag: logs.append(line),
			on_state_changed=lambda snap: states.append(snap),
		)
		controller._preparing_image = True
		with mock.patch.object(runtime, "ensure_visual_search_image", return_value=True):
			with mock.patch.object(runtime, "readiness_summary", return_value="ready summary"):
				controller._prepare_image_worker()

		# Worker must not touch UI callbacks itself.
		self.assertEqual(logs, [])
		self.assertEqual(states, [])
		self.assertFalse(controller.output_queue.empty())

		with mock.patch.object(controller, "_spawn_bot", return_value=None) as spawn:
			controller.poll_output()
			spawn.assert_called_once()
		self.assertFalse(controller._preparing_image)
		self.assertEqual(controller.subtitle, "ready summary")
		self.assertTrue(any("visual_search.jpg ready" in line for line in logs))

	def test_write_crash_log_creates_file(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			path = os.path.join(temp_dir, "launcher_crash.log")
			with mock.patch.object(runtime, "CRASH_LOG_FILE", path):
				with mock.patch.object(runtime, "LOG_DIR", temp_dir):
					runtime.write_crash_log(text="forced test crash")
			self.assertTrue(os.path.isfile(path))
			with open(path, encoding="utf-8") as handle:
				content = handle.read()
			self.assertIn("forced test crash", content)


class LauncherRuntimeTests(unittest.TestCase):
	def test_main_script_path_exists(self) -> None:
		self.assertTrue(os.path.isfile(runtime.MAIN_SCRIPT))

	def test_read_log_tail_keeps_recent_bytes(self) -> None:
		with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
			handle.write(b"OLD\n" * 5000)
			handle.write(b"NEW\n")
			path = handle.name

		try:
			text = runtime.read_log_tail(path, max_bytes=64)
			self.assertIn("NEW", text)
			self.assertLess(len(text), 5000 * 4)
		finally:
			os.remove(path)

	def test_resolve_python_prefers_repo_venv(self) -> None:
		with mock.patch("launcher_runtime.os.path.isfile", return_value=True):
			self.assertEqual(runtime.resolve_python_executable(), runtime.VENV_PYTHON)

	def test_preflight_warnings_for_missing_visual_search_image(self) -> None:
		with mock.patch.object(runtime, "VISUAL_SEARCH_IMAGE", os.path.join(tempfile.gettempdir(), "missing-visual.jpg")):
			with mock.patch("launcher_runtime.os.path.isfile", side_effect=lambda path: path != runtime.VISUAL_SEARCH_IMAGE):
				warnings = runtime.preflight_warnings()
		self.assertTrue(any("visual_search.jpg missing" in warning for warning in warnings))

	def test_readiness_summary_mentions_trends_and_image_state(self) -> None:
		with mock.patch.object(runtime, "VISUAL_SEARCH_IMAGE", __file__):
			with mock.patch("launcher_runtime.os.path.isfile", return_value=True):
				summary = runtime.readiness_summary()
		self.assertIn("trends queries", summary)
		self.assertIn("visual search ready", summary)

	def test_summarize_last_run_includes_ok_skip_and_search_quota(self) -> None:
		log_text = (
			"\n=== Run #3 started 2026-01-01 12:00:00 ===\n"
			"[OK] Bing daily set\n"
			"[OK] Explore on Bing\n"
			"[SKIP] Visual search: not available\n"
			"Search quota complete: 30/30\n"
		)
		text, tone = runtime.summarize_last_run(
			log_text,
			3,
			exit_code=0,
			stopped_by_user=False,
		)
		self.assertEqual(text, "Done — 2 tasks OK, 1 skipped, searches 30/30")
		self.assertEqual(tone, "warning")

	def test_parse_run_history_newest_first(self) -> None:
		log_text = (
			"=== Run #1 started 2026-01-01 10:00:00 ===\n"
			"[OK] Bing daily set\n"
			"=== Run finished 10:01:00 (exit 0) ===\n"
			"\n"
			"=== Run #2 started 2026-01-02 11:00:00 ===\n"
			"[FAIL] Explore on Bing\n"
			"=== Run finished 11:05:00 (exit 1) ===\n"
		)
		entries = runtime.parse_run_history(log_text)
		self.assertEqual(len(entries), 2)
		self.assertEqual(entries[0].number, 2)
		self.assertEqual(entries[0].tone, "danger")
		self.assertEqual(entries[1].number, 1)
		self.assertEqual(entries[1].tone, "success")
		self.assertIn("Run #2 started", runtime.extract_run_log(log_text, 2))
		self.assertIn("exit 1", runtime.extract_run_log(log_text, 2))

	def test_ensure_visual_search_image_returns_true_when_file_exists(self) -> None:
		with mock.patch(
			"random_image_for_visual_search.ensure_visual_search_image",
			return_value=__file__,
		):
			self.assertTrue(runtime.ensure_visual_search_image())

	def test_build_run_command_uses_unbuffered_python(self) -> None:
		command = runtime.build_run_command()
		self.assertEqual(command[1], "-u")
		self.assertEqual(command[2], runtime.MAIN_SCRIPT)

	def test_preflight_warns_when_data_dir_is_not_edge_profile(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			with mock.patch.object(runtime, "DATA_DIR", temp_dir):
				with mock.patch.object(runtime, "VENV_PYTHON", __file__):
					with mock.patch("launcher_runtime.os.path.isfile", return_value=True):
						issues = runtime.preflight_issues()
		self.assertTrue(any("not a valid Edge profile" in issue for issue in issues))

	def test_clear_stale_lock_removes_dead_pid(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			lock_path = os.path.join(temp_dir, "launcher.lock")
			with open(lock_path, "w", encoding="utf-8") as handle:
				handle.write("999999")

			with mock.patch.object(runtime, "LOCK_FILE", lock_path):
				with mock.patch.object(runtime, "_is_process_alive", return_value=False):
					runtime.clear_stale_lock()

			self.assertFalse(os.path.exists(lock_path))

	def test_summarize_last_run_reports_clean_success(self) -> None:
		log_text = "\n=== Run #1 started 2026-01-01 12:00:00 ===\nINFO started\n"
		text, tone = runtime.summarize_last_run(
			log_text,
			1,
			exit_code=0,
			stopped_by_user=False,
		)
		self.assertEqual(text, "Done — last run finished cleanly")
		self.assertEqual(tone, "success")

	def test_summarize_last_run_reports_failures(self) -> None:
		log_text = (
			"\n=== Run #2 started 2026-01-01 12:00:00 ===\n"
			"[FAIL] task one\n"
			"[FAIL] task two\n"
		)
		text, tone = runtime.summarize_last_run(
			log_text,
			2,
			exit_code=0,
			stopped_by_user=False,
		)
		self.assertEqual(text, "Done with 2 errors — check log")
		self.assertEqual(tone, "danger")

	def test_summarize_last_run_reports_stopped(self) -> None:
		text, tone = runtime.summarize_last_run("", 1, exit_code=1, stopped_by_user=True)
		self.assertEqual(text, "Stopped")
		self.assertEqual(tone, "warning")

	def test_edge_profile_hint_for_known_failure_line(self) -> None:
		hint = runtime.edge_profile_hint_for_line("[FAIL] default: could not start Edge with this profile.")
		self.assertEqual(hint, runtime.EDGE_PROFILE_HINT)

	def test_run_finished_sets_error_status_from_log(self) -> None:
		seen: list[ctl.LauncherSnapshot] = []
		with tempfile.TemporaryDirectory() as temp_dir:
			log_file = os.path.join(temp_dir, "runs.log")
			self._assert_finish_status(seen, log_file)

	def _assert_finish_status(self, seen: list, log_file: str) -> None:
		with mock.patch.object(ctl, "RUN_LOG_FILE", log_file):
			self._finish_and_check_status(seen)

	def _finish_and_check_status(self, seen: list) -> None:
		controller = ctl.LauncherController(on_state_changed=seen.append)
		controller._log_buffer = []
		controller.run_count = 1
		controller._progress_running = True
		controller._process_log_text("\n=== Run #1 started 2026-01-01 12:00:00 ===\n", to_file=False)
		controller._process_log_text("[FAIL] something broke\n", to_file=False)
		controller.process = mock.Mock()
		controller.process.poll.return_value = 1
		controller._finish_run()
		self.assertTrue(seen)
		self.assertEqual(seen[-1].status_text, "Done with 1 error — check log")

	def test_edge_hint_appended_once_per_run(self) -> None:
		controller = ctl.LauncherController()
		controller._process_log_text(
			"[FAIL] default: could not start Edge with this profile.\n",
			to_file=False,
		)
		controller._process_log_text(
			"profile is already open in another Edge window\n",
			to_file=False,
		)
		joined = "".join(controller._log_buffer)
		self.assertEqual(joined.count("Close other Edge windows"), 1)

	def test_stop_run_marks_stopping_while_process_alive(self) -> None:
		controller = ctl.LauncherController()
		controller.process = mock.Mock()
		controller.process.poll.return_value = None
		controller._run_finished_pending = True

		with mock.patch.object(runtime, "stop_run_process"):
			controller.stop_run()

		self.assertTrue(controller._stopping)
		snapshot = controller.initial_snapshot()
		self.assertFalse(snapshot.stop_enabled)


class RunProgressTests(unittest.TestCase):
	def test_reset_marks_browser_pending(self) -> None:
		run = progress.RunProgress()
		run.reset()
		self.assertEqual(run.browser_state, "pending")
		self.assertEqual(len(run.step_rows()), len(task_steps.AUTOMATION_TASK_STEPS) + 1)

	def test_step_marker_sets_running_task(self) -> None:
		run = progress.RunProgress()
		run.reset()
		run.update_from_line("[STEP] Starting browser")
		run.update_from_line("[STEP] Bing daily set")
		self.assertEqual(run.browser_state, "ok")
		self.assertEqual(run.task_states["Bing daily set"].state, "running")
		self.assertEqual(run.current_label(), "Bing daily set")

	def test_logging_prefix_still_updates_the_running_step(self) -> None:
		run = progress.RunProgress()
		run.reset()
		run.update_from_line("09:23:01 INFO     rewards_tasks: [STEP] Starting browser")
		run.update_from_line("09:23:04 INFO     rewards_tasks: [STEP] Bing daily set")
		run.update_from_line("09:24:10 INFO     rewards_tasks: [OK] Bing daily set")
		run.update_from_line("09:24:11 INFO     rewards_tasks: Search points before: 18/30")
		self.assertEqual(run.browser_state, "ok")
		self.assertEqual(run.task_states["Bing daily set"].state, "ok")
		self.assertEqual(run.task_states["Explore on Bing"].state, "running")
		self.assertEqual(run.search_quota, "18/30")
		self.assertEqual(run.progress_summary(), "2 of 7 complete")

	def test_ok_advances_to_next_task(self) -> None:
		run = progress.RunProgress()
		run.reset()
		run.update_from_line("[STEP] Bing daily set")
		run.update_from_line("[OK] Bing daily set")
		self.assertEqual(run.task_states["Bing daily set"].state, "ok")
		self.assertEqual(run.task_states["Explore on Bing"].state, "running")

	def test_skip_sets_detail(self) -> None:
		run = progress.RunProgress()
		run.reset()
		run.update_from_line("[SKIP] Visual search: not available in this UI variant (TimeoutException)")
		row = run.task_states["Visual search"]
		self.assertEqual(row.state, "skip")
		self.assertIn("TimeoutException", row.detail)

	def test_search_quota_updates_required_searches(self) -> None:
		run = progress.RunProgress()
		run.reset()
		run.update_from_line("[STEP] Required searches")
		run.update_from_line("Search points before: 18/30")
		self.assertEqual(run.search_quota, "18/30")
		self.assertEqual(run.task_states["Required searches"].detail, "18/30")
		self.assertEqual(run.current_label(), "Required searches (18/30)")

	def test_progress_summary_before_and_during_run(self) -> None:
		run = progress.RunProgress()
		run.active = False
		self.assertIn("7 steps", run.progress_summary())
		run.reset()
		run.update_from_line("[STEP] Starting browser")
		run.update_from_line("[OK] Bing daily set")
		self.assertEqual(run.progress_summary(), "1 of 7 complete")


if __name__ == "__main__":
	unittest.main()
