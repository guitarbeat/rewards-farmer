"""Textual terminal UI for the Rewards Farmer launcher."""

from __future__ import annotations

import launcher_controller as controller
import launcher_runtime as runtime
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Footer, Header, Label, ListItem, ListView, RichLog, Static

_ICONS = {
	"pending": "○",
	"running": "●",
	"ok": "✓",
	"skip": "–",
	"fail": "✕",
}


class RewardsFarmerApp(App):
	"""Launcher screens: run, progress, past runs, and the log."""

	TITLE = "Rewards Farmer"
	CSS = """
	Screen {
		layout: vertical;
	}

	#subtitle, #setup, #status, #progress-summary, #history-count {
		height: auto;
		padding: 0 1;
	}

	#subtitle {
		color: $text-muted;
	}

	#setup {
		color: $text-muted;
		margin-bottom: 1;
	}

	#actions {
		height: auto;
		padding: 0 1;
	}

	#actions Button {
		margin-right: 1;
	}

	#progress {
		height: auto;
		max-height: 12;
		padding: 0 1;
		margin-bottom: 1;
	}

	.step {
		height: auto;
	}

	.step-running {
		color: $accent;
	}

	.step-ok {
		color: $success;
	}

	.step-skip {
		color: $warning;
	}

	.step-fail {
		color: $error;
	}

	#history {
		height: 8;
		margin: 0 1 1 1;
		border: solid $primary;
	}

	#log-panel {
		height: 1fr;
		margin: 0 1 1 1;
		border: solid $surface;
	}

	#log {
		height: 1fr;
	}

	#status {
		dock: bottom;
		height: 1;
		padding: 0 1;
	}

	#status.tone-success {
		color: $success;
	}

	#status.tone-warning {
		color: $warning;
	}

	#status.tone-danger {
		color: $error;
	}

	#status.tone-running {
		color: $accent;
	}
	"""

	BINDINGS = [
		Binding("r", "run", "Run"),
		Binding("ctrl+enter", "run", "Run", show=False),
		Binding("escape", "stop", "Stop"),
		Binding("l", "toggle_log", "Log"),
		Binding("q", "quit_app", "Quit"),
	]

	def __init__(self) -> None:
		super().__init__()
		self.controller = controller.LauncherController(
			on_log_line=self._on_log_line,
			on_state_changed=self._on_state_changed,
		)
		self._pending_logs: list[tuple[str, str | None]] = []
		self._snapshot: controller.LauncherSnapshot | None = None
		self._progress_key: tuple = ()
		self._history_key = ""
		self._viewing_run: int | None = None
		self._log_visible = False
		self._quit_after_stop = False

	def compose(self) -> ComposeResult:
		yield Header()
		yield Static("", id="subtitle")
		yield Static("", id="setup")
		with Horizontal(id="actions"):
			yield Button("Run", id="run", variant="success")
			yield Button("Stop", id="stop", variant="error", disabled=True)
			yield Button("Open logs", id="open-logs")
			yield Button("Open profile", id="open-profile")
			yield Button("Clear log", id="clear-log")
		yield Static("Run progress", id="progress-summary")
		yield Vertical(id="progress")
		yield Static("Past runs", id="history-count")
		yield ListView(id="history")
		with VerticalScroll(id="log-panel"):
			yield RichLog(id="log", markup=False, wrap=True, highlight=False)
		yield Static("Ready to run", id="status")
		yield Footer()

	def on_mount(self) -> None:
		self.query_one("#log-panel").display = False
		for line, tag in self.controller.initial_log_lines():
			self._pending_logs.append((line, tag))
		self._snapshot = self.controller.initial_snapshot()
		self._flush_logs()
		self._paint()
		self.set_interval(0.1, self._poll)

	def _on_log_line(self, line: str, tag: str | None) -> None:
		self._pending_logs.append((line, tag))

	def _on_state_changed(self, snapshot: controller.LauncherSnapshot) -> None:
		self._snapshot = snapshot

	def _poll(self) -> None:
		if not self.is_running or not self.query("#subtitle"):
			return
		self.controller.poll_output()
		self._flush_logs()
		self._paint()
		if self._quit_after_stop and not self.controller.is_run_active():
			self.exit()

	def _flush_logs(self) -> None:
		if self._viewing_run is not None or not self._pending_logs:
			if self._viewing_run is not None:
				self._pending_logs.clear()
			return
		log = self.query_one("#log", RichLog)
		for line, _tag in self._pending_logs:
			log.write(line.rstrip("\r\n"))
		self._pending_logs.clear()

	def _paint(self) -> None:
		snapshot = self._snapshot
		if snapshot is None:
			return

		self.query_one("#subtitle", Static).update(snapshot.subtitle)
		self.query_one("#setup", Static).update(snapshot.setup_strip)
		self.query_one("#progress-summary", Static).update(
			f"Run progress  {snapshot.progress_summary}"
		)
		status = self.query_one("#status", Static)
		status.update(f"{snapshot.status_text}   {snapshot.run_count_label}")
		status.set_classes(f"tone-{snapshot.status_tone}")

		run = self.query_one("#run", Button)
		run.disabled = not snapshot.run_enabled
		run.label = snapshot.run_button_text
		self.query_one("#stop", Button).disabled = not snapshot.stop_enabled

		self._paint_progress(snapshot.progress_rows)
		self._paint_history(snapshot.run_history)

	def _paint_progress(self, rows) -> None:
		key = tuple((row.name, row.state, row.detail) for row in rows)
		if key == self._progress_key:
			return
		self._progress_key = key
		box = self.query_one("#progress", Vertical)
		box.remove_children()
		for row in rows:
			icon = _ICONS.get(row.state, _ICONS["pending"])
			detail = f"  {row.detail}" if row.detail else ""
			box.mount(Static(f"{icon} {row.name}{detail}", classes=f"step step-{row.state}"))

	def _paint_history(self, entries: list[dict]) -> None:
		count = self.query_one("#history-count", Static)
		count.update(f"Past runs  {len(entries)}")
		key = "|".join(
			f"{entry.get('number')}:{entry.get('finished')}:{entry.get('summary')}"
			for entry in entries
		)
		if key == self._history_key:
			return
		self._history_key = key
		history = self.query_one("#history", ListView)
		history.clear()
		if not entries:
			history.append(ListItem(Label("No past runs yet."), name="empty"))
			return
		for entry in entries:
			number = entry.get("number")
			label = f"#{number}  {entry.get('started') or ''}  —  {entry.get('summary') or ''}"
			history.append(ListItem(Label(label), name=str(number)))

	def _show_run_log(self, run_number: int) -> None:
		self._viewing_run = run_number
		text = self.controller.get_run_log(run_number)
		log = self.query_one("#log", RichLog)
		log.clear()
		for line in text.splitlines():
			log.write(line)
		self._set_log_visible(True)

	def _set_log_visible(self, visible: bool) -> None:
		self._log_visible = visible
		self.query_one("#log-panel").display = visible

	def action_toggle_log(self) -> None:
		if self._viewing_run is not None:
			self._viewing_run = None
			log = self.query_one("#log", RichLog)
			log.clear()
			for line in self.controller.get_log_text().splitlines()[-200:]:
				log.write(line)
			self._set_log_visible(True)
			return
		self._set_log_visible(not self._log_visible)

	def action_run(self) -> None:
		self._viewing_run = None
		error = self.controller.start_run()
		if error:
			title = "Setup required" if any(word in error for word in ("Setup", "Missing", "data-dir")) else "Could not start"
			self.notify(f"{title}\n{error}", severity="error", timeout=8)
		self._paint()

	def action_stop(self) -> None:
		self.controller.stop_run()
		self._paint()

	def action_quit_app(self) -> None:
		if self.controller.is_run_active():
			self.controller.stop_run()
			self._quit_after_stop = True
			self.notify("Stopping the run…", timeout=3)
			return
		self.exit()

	def on_button_pressed(self, event: Button.Pressed) -> None:
		button_id = event.button.id
		if button_id == "run":
			self.action_run()
		elif button_id == "stop":
			self.action_stop()
		elif button_id == "open-logs":
			self.controller.open_logs_folder()
		elif button_id == "open-profile":
			self.controller.open_profile_folder()
		elif button_id == "clear-log":
			error = self.controller.clear_log()
			if error:
				self.notify(error, severity="warning")
				return
			self._viewing_run = None
			self._history_key = ""
			self.query_one("#log", RichLog).clear()
			self._paint()

	def on_list_view_selected(self, event: ListView.Selected) -> None:
		name = event.item.name or ""
		if not name.isdigit():
			return
		self._show_run_log(int(name))


def main() -> int:
	runtime.install_crash_hooks()
	try:
		RewardsFarmerApp().run()
	except Exception as exc:
		runtime.write_crash_log(exc)
		raise
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
