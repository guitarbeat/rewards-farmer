"""Live run progress parsed from bot log output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from task_steps import AUTOMATION_TASK_STEPS, BROWSER_STEP, REQUIRED_SEARCHES

StepState = Literal["pending", "running", "ok", "skip", "fail"]

_RUN_START_RE = re.compile(r"=== Run #\d+ started")
_RUN_FINISH_PREFIX = "=== Run finished"
_STEP_PREFIX = "[STEP] "
_OUTCOME_PREFIXES = ("[OK] ", "[SKIP] ", "[FAIL] ")


@dataclass
class StepRow:
	name: str
	state: StepState = "pending"
	detail: str = ""


@dataclass
class RunProgress:
	browser_state: StepState = "pending"
	task_states: dict[str, StepRow] = field(default_factory=dict)
	query_source: str | None = None
	site_label: str | None = None
	search_quota: str | None = None
	active: bool = False
	_current_running: str | None = None
	other_failures: int = 0

	def __post_init__(self) -> None:
		if not self.task_states:
			self.reset()

	def reset(self) -> None:
		self.browser_state = "pending"
		self.task_states = {
			name: StepRow(name=name) for name in AUTOMATION_TASK_STEPS
		}
		self.query_source = None
		self.site_label = None
		self.search_quota = None
		self.active = True
		self._current_running = None
		self.other_failures = 0

	def finish(self) -> None:
		self.active = False
		self._current_running = None
		if self.browser_state == "running":
			self.browser_state = "pending"

		for row in self.task_states.values():
			if row.state == "running":
				row.state = "pending"

	def update_from_line(self, line: str) -> None:
		stripped = line.strip()
		if not stripped:
			return

		if _RUN_START_RE.search(stripped):
			self.reset()
			return

		if stripped.startswith(_RUN_FINISH_PREFIX) or stripped == "Stopping run…":
			self.finish()
			return

		if stripped.startswith("Automation site:"):
			# "Automation site: MS Rewards (ms_rewards)"
			label_part = stripped.removeprefix("Automation site:").strip()
			if label_part:
				self.site_label = label_part.split(" (", 1)[0]
			return

		if stripped.startswith("Search queries:"):
			self.query_source = stripped.removeprefix("Search queries:").strip()
			return

		quota = _parse_search_quota_from_line(stripped)
		if quota is not None:
			self.search_quota = quota
			if REQUIRED_SEARCHES in self.task_states:
				self.task_states[REQUIRED_SEARCHES].detail = quota
			return

		if stripped.startswith(_STEP_PREFIX):
			step_name = stripped[len(_STEP_PREFIX) :].strip()
			if step_name == BROWSER_STEP:
				self._set_browser_running()
				return

			if step_name in self.task_states:
				if self.browser_state in ("pending", "running"):
					self.browser_state = "ok"
				self._set_task_running(step_name)
			return

		for prefix, outcome in (("[OK] ", "ok"), ("[SKIP] ", "skip"), ("[FAIL] ", "fail")):
			if not stripped.startswith(prefix):
				continue

			remainder = stripped[len(prefix) :].strip()
			task_name = _match_task_name(remainder)
			if task_name is None:
				if prefix == "[FAIL] ":
					self.other_failures += 1
				return

			detail = remainder[len(task_name) :].strip()
			if detail.startswith(":"):
				detail = detail[1:].strip()
			if len(detail) > 72:
				detail = detail[:69] + "..."

			self._set_task_outcome(task_name, outcome, detail)
			return

	def _set_browser_running(self) -> None:
		self.browser_state = "running"
		self._current_running = BROWSER_STEP

	def _set_task_running(self, name: str) -> None:
		if self._current_running and self._current_running != BROWSER_STEP:
			previous = self.task_states.get(self._current_running)
			if previous is not None and previous.state == "running":
				previous.state = "pending"

		row = self.task_states[name]
		row.state = "running"
		self._current_running = name

	def _set_task_outcome(self, name: str, outcome: StepState, detail: str) -> None:
		row = self.task_states[name]
		row.state = outcome
		row.detail = detail
		if name == REQUIRED_SEARCHES and self.search_quota:
			row.detail = self.search_quota if not detail else f"{self.search_quota} · {detail}"

		if self._current_running == name:
			self._current_running = None

		if outcome in ("ok", "skip", "fail"):
			next_pending = _next_pending_task(self.task_states, after=name)
			if next_pending is not None:
				self.task_states[next_pending].state = "running"
				self._current_running = next_pending

	def step_rows(self) -> list[StepRow]:
		rows = [StepRow(name=BROWSER_STEP, state=self.browser_state)]
		rows.extend(self.task_states[name] for name in AUTOMATION_TASK_STEPS)
		return rows

	def ok_count(self) -> int:
		return sum(1 for row in self.task_states.values() if row.state == "ok")

	def skip_count(self) -> int:
		return sum(1 for row in self.task_states.values() if row.state == "skip")

	def fail_count(self) -> int:
		return sum(1 for row in self.task_states.values() if row.state == "fail") + self.other_failures

	def total_steps(self) -> int:
		return len(AUTOMATION_TASK_STEPS) + 1

	def completed_count(self) -> int:
		completed = 0
		if self.browser_state in ("ok", "skip", "fail"):
			completed += 1

		completed += sum(
			1 for row in self.task_states.values() if row.state in ("ok", "skip", "fail")
		)
		return completed

	def progress_summary(self) -> str:
		completed = self.completed_count()
		total = self.total_steps()
		if not self.active:
			return f"{total} steps when you run"

		if completed == total:
			return f"All {total} steps complete"

		return f"{completed} of {total} complete"

	def current_label(self) -> str:
		if not self.active:
			return "Ready to run"

		if self._current_running == BROWSER_STEP:
			return BROWSER_STEP

		if self._current_running and self._current_running in self.task_states:
			label = self._current_running
			row = self.task_states[self._current_running]
			if row.detail:
				return f"{label} ({row.detail})"
			return label

		for row in self.step_rows():
			if row.state == "running":
				if row.detail:
					return f"{row.name} ({row.detail})"
				return row.name

		return "Running…"

	def status_tone(self) -> str:
		if not self.active:
			return "idle"

		if self.fail_count() > 0:
			return "danger"

		if self._current_running or any(row.state == "running" for row in self.step_rows()):
			return "running"

		return "running"

	@classmethod
	def from_log_lines(cls, lines: list[str]) -> RunProgress:
		progress = cls()
		progress.active = False
		progress.browser_state = "pending"
		progress.task_states = {
			name: StepRow(name=name) for name in AUTOMATION_TASK_STEPS
		}

		for line in lines:
			progress.update_from_line(line)

		progress.active = False
		return progress


def _match_task_name(remainder: str) -> str | None:
	for name in AUTOMATION_TASK_STEPS:
		if remainder == name or remainder.startswith(f"{name}:"):
			return name

	return None


def _next_pending_task(task_states: dict[str, StepRow], *, after: str) -> str | None:
	try:
		start = AUTOMATION_TASK_STEPS.index(after) + 1
	except ValueError:
		start = 0

	for name in AUTOMATION_TASK_STEPS[start:]:
		if task_states[name].state == "pending":
			return name

	return None


def _parse_search_quota_from_line(line: str) -> str | None:
	if "Search quota complete:" not in line and "Search quota not filled:" not in line:
		if "Search points before:" not in line:
			return None

	for token in line.split():
		if "/" in token and token[0].isdigit():
			return token.rstrip(".")

	return None


def summarize_progress(
	progress: RunProgress,
	*,
	exit_code: int | None,
	stopped_by_user: bool,
) -> tuple[str, str]:
	"""Return status-bar text and tone for a finished run."""
	if stopped_by_user or exit_code in (None, -15, -9):
		return "Stopped", "warning"

	fail_count = progress.fail_count()
	ok_count = progress.ok_count()
	skip_count = progress.skip_count()
	search_quota = progress.search_quota

	if fail_count == 1:
		return "Done with 1 error — check log", "danger"
	if fail_count > 1:
		return f"Done with {fail_count} errors — check log", "danger"

	summary_parts: list[str] = []
	if ok_count == 1:
		summary_parts.append("1 task OK")
	elif ok_count > 1:
		summary_parts.append(f"{ok_count} tasks OK")

	if skip_count == 1:
		summary_parts.append("1 skipped")
	elif skip_count > 1:
		summary_parts.append(f"{skip_count} skipped")

	if search_quota is not None:
		summary_parts.append(f"searches {search_quota}")

	if summary_parts and exit_code == 0:
		tone = "success" if skip_count == 0 else "warning"
		return f"Done — {', '.join(summary_parts)}", tone

	if exit_code == 0:
		return "Done — last run finished cleanly", "success"

	return f"Finished with errors (exit {exit_code})", "danger"
