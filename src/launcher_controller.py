"""UI-agnostic orchestration for the desktop launcher."""

from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import launcher_progress as progress
import launcher_runtime as runtime
import site_registry

REPO_ROOT = runtime.REPO_ROOT
MAIN_SCRIPT = runtime.MAIN_SCRIPT
LOG_DIR = runtime.LOG_DIR
RUN_LOG_FILE = os.path.join(LOG_DIR, "launcher_runs.log")
GUI_ENV_FLAG = "REWARDS_LAUNCHED_FROM_GUI"

# Sent from background workers; drained only on the UI/main poll thread.
SPAWN_AFTER_PREP = object()

LogCallback = Callable[[str, str | None], None]
StateCallback = Callable[["LauncherSnapshot"], None]
QueueItem = str | None | object


@dataclass
class LauncherSnapshot:
	subtitle: str
	status_text: str
	status_tone: str
	run_count_label: str
	setup_strip: str
	progress_summary: str
	progress_rows: list[progress.StepRow] = field(default_factory=list)
	run_history: list[dict] = field(default_factory=list)
	run_enabled: bool = True
	stop_enabled: bool = False
	run_button_text: str = "Run"
	stopping: bool = False
	preparing_image: bool = False
	running: bool = False


class LauncherController:
	def __init__(
		self,
		*,
		on_log_line: LogCallback | None = None,
		on_state_changed: StateCallback | None = None,
	) -> None:
		self.on_log_line = on_log_line
		self.on_state_changed = on_state_changed

		self.process = None
		self.output_queue: queue.Queue[QueueItem] = queue.Queue()
		self.run_count = 0
		self._run_finished_pending = False
		self._user_stopped = False
		self._stopping = False
		self._edge_hint_shown = False
		self._preparing_image = False
		self._preflight_issues = runtime.preflight_issues()
		self._preflight_warnings = runtime.preflight_warnings()
		self.run_progress = progress.RunProgress()
		self.run_progress.active = False
		self._progress_running = False
		self._log_buffer: list[str] = []
		self._history_cache: list[dict] | None = None
		self.subtitle = "One-click MS Rewards runs with your saved Edge profile."
		self._prep_ready_subtitle: str | None = None

	def build_env(self) -> dict[str, str]:
		env = os.environ.copy()
		env[site_registry.ENV_VAR] = site_registry.DEFAULT_SITE
		env[GUI_ENV_FLAG] = "1"
		env["OPENBLAS_NUM_THREADS"] = "1"
		env["OMP_NUM_THREADS"] = "1"
		env.setdefault("QUERY_SOURCE", "trends")
		env.pop("REWARDS_ACCOUNTS", None)
		return env

	def setup_strip_text(self) -> str:
		site = self.run_progress.site_label or site_registry.site_label(site_registry.DEFAULT_SITE)
		query = self.run_progress.query_source or runtime.query_source_label()
		return f"{site}  ·  Edge profile  ·  {query}"

	def log_tag_for_line(self, line: str) -> str | None:
		if line.startswith("==="):
			return "banner"
		if "[OK]" in line:
			return "ok"
		if "[FAIL]" in line:
			return "fail"
		if "[SKIP]" in line:
			return "skip"
		if "WARNING" in line or "[WARN]" in line:
			return "warn"
		if "ERROR" in line:
			return "fail"
		if "INFO" in line:
			return "info"
		return None

	def initial_log_lines(self) -> list[tuple[str, str | None]]:
		lines: list[tuple[str, str | None]] = []
		for warning in self._preflight_warnings:
			lines.extend(self._process_log_text(f"[WARN] {warning}\n", to_file=False, emit=False))

		if not self._preflight_issues:
			self.subtitle = runtime.readiness_summary()
		else:
			self.subtitle = self._preflight_issues[0]
			for item in self._preflight_issues:
				lines.extend(self._process_log_text(f"[WARN] {item}\n", to_file=False, emit=False))

		previous = runtime.read_log_tail(RUN_LOG_FILE).strip()
		if previous:
			lines.extend(self._process_log_text(previous + "\n", to_file=False, emit=False))
			self.run_count = previous.count("=== Run #")

		self._history_cache = None
		return lines

	def initial_snapshot(self) -> LauncherSnapshot:
		if not self._preflight_issues:
			status_text = "Ready to run"
			status_tone = "idle"
		else:
			status_text = self._preflight_issues[0]
			status_tone = "warning"

		return self._make_snapshot(status_text=status_text, status_tone=status_tone)

	def poll_output(self) -> bool:
		"""Drain subprocess/worker queue on the UI thread. Returns True when a run finished."""
		run_finished = False

		while True:
			try:
				item = self.output_queue.get_nowait()
			except queue.Empty:
				break

			if item is SPAWN_AFTER_PREP:
				self._preparing_image = False
				if self._prep_ready_subtitle is not None:
					self.subtitle = self._prep_ready_subtitle
					self._prep_ready_subtitle = None
				error = self._spawn_bot()
				if error:
					self._process_log_text(f"[FAIL] Could not start: {error}\n", to_file=False)
				continue

			if item is None:
				if self._run_finished_pending:
					self._run_finished_pending = False
					self._finish_run()
					run_finished = True
				continue

			self._process_log_text(str(item))

		return run_finished

	def start_run(self) -> str | None:
		"""Begin a run. Returns an error message when blocked."""
		if self.process is not None and self.process.poll() is None:
			return None
		if self._preparing_image:
			return None
		if self._preflight_issues:
			return "\n".join(self._preflight_issues)

		self.run_count += 1
		self._user_stopped = False
		self._stopping = False
		self._edge_hint_shown = False
		stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		self._reset_progress_for_run()
		self._history_cache = None
		self._process_log_text(f"\n=== Run #{self.run_count} started {stamp} ===\n")

		if not os.path.isfile(runtime.VISUAL_SEARCH_IMAGE):
			self._preparing_image = True
			self._emit_state(status_text="Preparing visual search image…", status_tone="running")
			threading.Thread(target=self._prepare_image_worker, daemon=True).start()
			return None

		return self._spawn_bot()

	def stop_run(self) -> None:
		if self.process is None or self.process.poll() is not None:
			return
		if self._stopping:
			return

		self._stopping = True
		self._user_stopped = True
		self._process_log_text("\nStopping run…\n")
		self._emit_state(status_text="Stopping…", status_tone="warning")

		def _stop_worker() -> None:
			try:
				runtime.stop_run_process(self.process)
			except Exception as exc:
				self.output_queue.put(f"[WARN] Stop cleanup issue: {exc}\n")
			finally:
				self.output_queue.put(None)

		threading.Thread(target=_stop_worker, daemon=True).start()

	def clear_log(self) -> str | None:
		if self.process is not None and self.process.poll() is None:
			return "Stop the current run before clearing the log."

		self._log_buffer = []
		self.run_count = 0
		self._history_cache = None
		try:
			open(RUN_LOG_FILE, "w", encoding="utf-8").close()
		except OSError:
			pass

		self._emit_state()
		return None

	def open_logs_folder(self) -> None:
		runtime.open_path_in_file_manager(LOG_DIR)

	def open_profile_folder(self) -> None:
		runtime.open_path_in_file_manager(runtime.DATA_DIR)

	def is_run_active(self) -> bool:
		return self.process is not None and self.process.poll() is None

	def get_log_text(self) -> str:
		return "".join(self._log_buffer)

	def run_history(self) -> list[dict]:
		if self._history_cache is not None:
			return self._history_cache

		entries = runtime.parse_run_history(self.get_log_text())
		self._history_cache = [
			{
				"number": entry.number,
				"started": entry.started,
				"finished": entry.finished,
				"exit_code": entry.exit_code,
				"summary": entry.summary,
				"tone": entry.tone,
				"ok_count": entry.ok_count,
				"skip_count": entry.skip_count,
				"fail_count": entry.fail_count,
				"search_quota": entry.search_quota,
			}
			for entry in entries
		]
		return self._history_cache

	def get_run_log(self, run_number: int) -> str:
		return runtime.extract_run_log(self.get_log_text(), int(run_number))

	def _prepare_image_worker(self) -> None:
		"""Background work only — never touch UI callbacks from this thread."""
		ready = runtime.ensure_visual_search_image()
		if ready:
			self._prep_ready_subtitle = runtime.readiness_summary()
			self.output_queue.put("[INFO] visual_search.jpg ready.\n")
		else:
			self._prep_ready_subtitle = None
			self.output_queue.put(
				"[WARN] Could not download visual_search.jpg — bot will retry during the run.\n"
			)

		self.output_queue.put(SPAWN_AFTER_PREP)

	def _spawn_bot(self) -> str | None:
		command = runtime.build_run_command()
		env = self.build_env()

		try:
			self.process = runtime.spawn_run_process(command=command, env=env)
		except OSError as exc:
			self.run_count -= 1
			self._emit_state()
			return str(exc)

		self._run_finished_pending = True
		threading.Thread(target=self._reader_thread, args=(self.process,), daemon=True).start()
		self._emit_state(
			status_text=self.run_progress.current_label(),
			status_tone="running",
		)
		return None

	def _reader_thread(self, process) -> None:
		try:
			assert process.stdout is not None

			for line in process.stdout:
				self.output_queue.put(line)
		except Exception as exc:
			self.output_queue.put(f"[FAIL] Launcher lost output stream: {exc}\n")
		finally:
			try:
				process.wait()
			except Exception:
				pass
			self.output_queue.put(None)

	def _finish_run(self) -> None:
		exit_code = self.process.poll() if self.process is not None else None
		stopped_by_user = self._user_stopped
		finished_run = self.run_count
		self._user_stopped = False
		self._stopping = False
		self._progress_running = False
		self.process = None

		stamp = datetime.now().strftime("%H:%M:%S")
		self._process_log_text(f"=== Run finished {stamp} (exit {exit_code}) ===\n")

		status_text, status_tone = runtime.summarize_last_run(
			self.get_log_text(),
			finished_run,
			exit_code=exit_code,
			stopped_by_user=stopped_by_user,
		)
		self._history_cache = None
		self._emit_state(status_text=status_text, status_tone=status_tone)

	def _reset_progress_for_run(self) -> None:
		self.run_progress.reset()
		self._progress_running = True

	def _process_log_text(
		self,
		text: str,
		*,
		to_file: bool = True,
		emit: bool = True,
	) -> list[tuple[str, str | None]]:
		emitted: list[tuple[str, str | None]] = []
		hint_for_file = ""

		for line in text.splitlines(keepends=True):
			tag = self.log_tag_for_line(line)
			emitted.append((line, tag))
			self._log_buffer.append(line)
			if emit:
				self._emit_log_line(line, tag)

			line_for_progress = line.rstrip("\r\n")
			if line_for_progress and self._progress_running:
				self.run_progress.update_from_line(line_for_progress)

			if not self._edge_hint_shown:
				hint = runtime.edge_profile_hint_for_line(line)
				if hint is not None:
					self._edge_hint_shown = True
					emitted.append((hint, "warn"))
					self._log_buffer.append(hint)
					if emit:
						self._emit_log_line(hint, "warn")
					hint_for_file = hint

		if emit and self._progress_running:
			self._emit_state()

		if not to_file:
			return emitted

		try:
			os.makedirs(LOG_DIR, exist_ok=True)
			with open(RUN_LOG_FILE, "a", encoding="utf-8") as handle:
				handle.write(text)
				if hint_for_file:
					handle.write(hint_for_file)
		except OSError as exc:
			return self._process_log_text(f"[WARN] Could not write log file: {exc}\n", to_file=False)

		return emitted

	def _trim_log_buffer(self) -> None:
		line_count = len(self._log_buffer)
		if line_count <= runtime.MAX_LOG_LINES:
			return

		extra = line_count - runtime.MAX_LOG_LINES
		self._log_buffer = self._log_buffer[extra:]

	def _emit_log_line(self, line: str, tag: str | None) -> None:
		if self.on_log_line is not None:
			self.on_log_line(line, tag)

	def _make_snapshot(
		self,
		*,
		status_text: str | None = None,
		status_tone: str | None = None,
	) -> LauncherSnapshot:
		running = self.is_run_active() or self._preparing_image
		can_run = (running or not self._preflight_issues) and not self._preparing_image

		if status_text is None:
			if self._progress_running and self.run_progress.active:
				status_text = self.run_progress.current_label()
				status_tone = self.run_progress.status_tone()
			elif not self._preflight_issues:
				status_text = "Ready to run"
				status_tone = "idle"
			else:
				status_text = self._preflight_issues[0]
				status_tone = "warning"

		if status_tone is None:
			status_tone = "idle"

		run_label = "1 run" if self.run_count == 1 else f"{self.run_count} runs"
		run_text = "Run again" if not running and self.run_count > 0 else "Run"

		return LauncherSnapshot(
			subtitle=self.subtitle,
			status_text=status_text,
			status_tone=status_tone,
			run_count_label=run_label,
			setup_strip=self.setup_strip_text(),
			progress_summary=self.run_progress.progress_summary(),
			progress_rows=self.run_progress.step_rows(),
			run_history=self.run_history(),
			run_enabled=not running and can_run,
			stop_enabled=running and not self._stopping,
			run_button_text=run_text,
			stopping=self._stopping,
			preparing_image=self._preparing_image,
			running=running,
		)

	def _emit_state(
		self,
		*,
		status_text: str | None = None,
		status_tone: str | None = None,
	) -> None:
		self._trim_log_buffer()
		if self.on_state_changed is not None:
			self.on_state_changed(self._make_snapshot(status_text=status_text, status_tone=status_tone))
