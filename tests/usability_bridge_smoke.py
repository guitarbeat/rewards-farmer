"""Scripted usability path for the launcher controller (no window)."""

from __future__ import annotations

import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import launcher_controller as ctl


class FakeProc:
	def __init__(self) -> None:
		self.stdout = iter([])
		self._code = None

	def poll(self):
		return self._code

	def wait(self):
		self._code = 0
		return 0


def main() -> int:
	tmp = tempfile.TemporaryDirectory()
	log_file = os.path.join(tmp.name, "runs.log")
	image = os.path.join(tmp.name, "visual_search.jpg")
	open(image, "wb").write(b"x")

	patches = [
		mock.patch.object(ctl, "RUN_LOG_FILE", log_file),
		mock.patch.object(ctl.runtime, "preflight_issues", return_value=[]),
		mock.patch.object(ctl.runtime, "preflight_warnings", return_value=[]),
		mock.patch.object(ctl.runtime, "read_log_tail", return_value=""),
		mock.patch.object(ctl.runtime, "readiness_summary", return_value="Ready for usability check"),
		mock.patch.object(ctl.runtime, "ensure_visual_search_image", return_value=True),
		mock.patch.object(ctl.runtime, "VISUAL_SEARCH_IMAGE", image),
	]
	for patcher in patches:
		patcher.start()

	controller = ctl.LauncherController()
	boot = controller.initial_snapshot()
	assert boot.run_enabled, boot
	assert boot.run_button_text == "Run"

	fake = FakeProc()
	with mock.patch.object(ctl.runtime, "spawn_run_process", return_value=fake), mock.patch.object(
		ctl.LauncherController, "_reader_thread", lambda self, process: None
	):
		err = controller.start_run()
		assert err is None, err

		controller._process_log_text("[STEP] Starting browser\n", to_file=False)
		controller._process_log_text("[OK] Starting browser\n", to_file=False)
		controller._process_log_text("[STEP] Bing daily set\n", to_file=False)
		controller.poll_output()
		rows = controller.initial_snapshot().progress_rows
		assert any(row.state == "running" for row in rows), rows
		assert controller.initial_snapshot().stop_enabled

		controller.stop_run()
		fake._code = 0
		controller.output_queue.put(None)
		controller.poll_output()
		finished = controller.initial_snapshot()
		assert finished.run_enabled
		assert finished.run_button_text == "Run again"

		cleared = controller.clear_log()
		assert cleared is None

		print("USABILITY_BRIDGE_OK")
		print("status:", finished.status_text)
		print("rows:", len(finished.progress_rows))
	tmp.cleanup()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
