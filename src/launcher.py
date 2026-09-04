"""Desktop launcher for site automation runs.

CustomTkinter UI backed by LauncherController.
Double-click Launch.bat at the repo root.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime

import customtkinter as ctk
from tkinter import messagebox

import launcher_controller as controller
import launcher_progress as progress
import launcher_runtime as runtime
import launcher_theme as theme

REPO_ROOT = runtime.REPO_ROOT
MAIN_SCRIPT = runtime.MAIN_SCRIPT
LOG_DIR = runtime.LOG_DIR
RUN_LOG_FILE = controller.RUN_LOG_FILE
GUI_ENV_FLAG = controller.GUI_ENV_FLAG
CRASH_LOG_FILE = os.path.join(LOG_DIR, "launcher_crash.log")


def write_crash_log(exc: BaseException | None = None, *, text: str | None = None) -> None:
	"""Persist a traceback so pythonw launches still leave evidence."""
	try:
		os.makedirs(LOG_DIR, exist_ok=True)
		stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		with open(CRASH_LOG_FILE, "a", encoding="utf-8") as handle:
			handle.write(f"\n=== Launcher crash {stamp} ===\n")
			if text:
				handle.write(text.rstrip() + "\n")
			if exc is not None:
				handle.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
			elif text is None:
				handle.write("".join(traceback.format_exception(*sys.exc_info())))
	except OSError:
		pass


def install_crash_hooks() -> None:
	def _hook(exc_type, exc, tb) -> None:
		try:
			os.makedirs(LOG_DIR, exist_ok=True)
			stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
			with open(CRASH_LOG_FILE, "a", encoding="utf-8") as handle:
				handle.write(f"\n=== Launcher crash {stamp} ===\n")
				handle.write("".join(traceback.format_exception(exc_type, exc, tb)))
		except OSError:
			pass
		sys.__excepthook__(exc_type, exc, tb)

	sys.excepthook = _hook


class LauncherApp(ctk.CTk):
	def __init__(self) -> None:
		super().__init__()
		theme.apply_theme()
		self.title("Rewards Farmer")
		self.minsize(720, 560)
		theme.apply_window_icon(self)
		self._center_window()

		self._progress_row_widgets: dict[str, dict] = {}
		self._log_visible = False
		self._header_icon = None
		self._status_tone = "idle"
		self._pulse_on = False
		self._poll_after_id = None
		self._pulse_after_id = None

		self.controller = controller.LauncherController(
			on_log_line=self._on_log_line,
			on_state_changed=self._on_state_changed,
		)

		self.configure(fg_color=theme.COLORS["window_bg"])
		self._build_ui()
		self._bind_shortcuts()
		self._load_initial_state()
		self.protocol("WM_DELETE_WINDOW", self._on_close)
		self.after(100, self._poll_output)
		self.after(700, self._pulse_status)

	def _center_window(self) -> None:
		width = 860
		height = 720
		x = (self.winfo_screenwidth() - width) // 2
		y = (self.winfo_screenheight() - height) // 2
		self.geometry(f"{width}x{height}+{x}+{y}")

	def _build_ui(self) -> None:
		self.grid_columnconfigure(0, weight=1)
		self.grid_rowconfigure(1, weight=1)

		# Soft top accent strip
		ctk.CTkFrame(self, height=3, fg_color=theme.COLORS["accent"], corner_radius=0).grid(
			row=0, column=0, sticky="ew"
		)

		outer = ctk.CTkFrame(self, fg_color="transparent")
		outer.grid(row=1, column=0, sticky="nsew", padx=24, pady=(16, 20))
		outer.grid_columnconfigure(0, weight=1)
		outer.grid_rowconfigure(2, weight=1)

		# --- Hero ---
		hero = theme.make_card(outer, radius=20, fg_color=theme.COLORS["hero_tint"])
		hero.grid(row=0, column=0, sticky="ew", pady=(0, 16))
		hero.grid_columnconfigure(1, weight=1)

		accent_bar = ctk.CTkFrame(hero, width=5, corner_radius=0, fg_color=theme.COLORS["accent"])
		accent_bar.grid(row=0, column=0, rowspan=3, sticky="ns")

		title_row = ctk.CTkFrame(hero, fg_color="transparent")
		title_row.grid(row=0, column=1, sticky="ew", padx=22, pady=(20, 0))
		title_row.grid_columnconfigure(1, weight=1)

		self._header_icon = theme.load_header_icon()
		if self._header_icon is not None:
			icon_label = ctk.CTkLabel(title_row, image=self._header_icon, text="")
			icon_label.grid(row=0, column=0, padx=(0, 14), sticky="nw")
			self._header_icon_label = icon_label

		text_col = ctk.CTkFrame(title_row, fg_color="transparent")
		text_col.grid(row=0, column=1, sticky="ew")
		ctk.CTkLabel(
			text_col,
			text="Rewards Farmer",
			font=theme.font(26, weight="bold"),
			text_color=theme.COLORS["text"],
			anchor="w",
		).pack(anchor="w")
		self.subtitle_label = ctk.CTkLabel(
			text_col,
			text=self.controller.subtitle,
			font=theme.font(13),
			text_color=theme.COLORS["text_secondary"],
			anchor="w",
			wraplength=620,
			justify="left",
		)
		self.subtitle_label.pack(anchor="w", pady=(4, 0))

		self.setup_chip_label = ctk.CTkLabel(
			text_col,
			text=self.controller.setup_strip_text(),
			font=theme.font(12),
			fg_color=theme.COLORS["chip_bg"],
			text_color=theme.COLORS["text_secondary"],
			corner_radius=10,
			anchor="w",
			wraplength=620,
			justify="left",
		)
		self.setup_chip_label.pack(anchor="w", pady=(12, 0), ipadx=12, ipady=7)

		actions = ctk.CTkFrame(hero, fg_color="transparent")
		actions.grid(row=1, column=1, sticky="ew", padx=22, pady=(18, 20))
		actions.grid_columnconfigure(2, weight=1)

		self.run_button = theme.make_primary_button(actions, text="Run", command=self.start_run)
		self.run_button.grid(row=0, column=0, padx=(0, 10))
		self.stop_button = ctk.CTkButton(
			actions,
			text="Stop",
			command=self.stop_run,
			width=100,
			height=44,
			corner_radius=12,
			fg_color="transparent",
			border_width=1,
			border_color=theme.COLORS["card_border"],
			text_color=theme.COLORS["stop"],
			hover_color=theme.COLORS["stop_hover"],
			font=theme.font(13, weight="bold"),
			state="disabled",
		)
		self.stop_button.grid(row=0, column=1, sticky="w")

		folder_actions = ctk.CTkFrame(actions, fg_color="transparent")
		folder_actions.grid(row=0, column=2, sticky="e")
		theme.make_ghost_button(folder_actions, text="Clear log", command=self.clear_log, width=96).pack(
			side="right", padx=(8, 0)
		)
		theme.make_ghost_button(
			folder_actions, text="Open profile", command=self.open_profile_folder, width=112
		).pack(side="right", padx=(8, 0))
		theme.make_ghost_button(folder_actions, text="Open logs", command=self.open_logs_folder, width=96).pack(
			side="right"
		)

		# --- Progress (primary) ---
		progress_header = ctk.CTkFrame(outer, fg_color="transparent")
		progress_header.grid(row=1, column=0, sticky="ew", pady=(0, 8))
		progress_header.grid_columnconfigure(0, weight=1)
		theme.make_section_label(progress_header, "Run progress").grid(row=0, column=0, sticky="w")
		self.progress_summary_label = ctk.CTkLabel(
			progress_header,
			text=self.controller.run_progress.progress_summary(),
			font=theme.font(12),
			fg_color=theme.COLORS["summary_pill"],
			text_color=theme.COLORS["muted"],
			corner_radius=10,
			padx=10,
			pady=4,
		)
		self.progress_summary_label.grid(row=0, column=1, sticky="e")

		self.progress_section = theme.make_card(outer, radius=18)
		self.progress_section.grid(row=2, column=0, sticky="nsew", pady=(0, 14))
		self.progress_frame = ctk.CTkFrame(self.progress_section, fg_color="transparent")
		self.progress_frame.pack(fill="both", expand=True, padx=16, pady=16)
		self._build_progress_rows([])

		# --- Log (secondary, collapsed by default) ---
		log_header = ctk.CTkFrame(outer, fg_color="transparent")
		log_header.grid(row=3, column=0, sticky="ew", pady=(0, 8))
		log_header.grid_columnconfigure(0, weight=1)
		theme.make_section_label(log_header, "Detailed log").grid(row=0, column=0, sticky="w")
		self.log_toggle_button = theme.make_ghost_button(
			log_header, text="Show", command=self._toggle_log_visibility, width=78, height=32
		)
		self.log_toggle_button.grid(row=0, column=1, sticky="e")

		self.log_section = theme.make_card(outer, radius=16)
		# Hidden until user expands — progress stays the focus.
		self.log_text = ctk.CTkTextbox(
			self.log_section,
			font=theme.mono_font(12),
			fg_color=theme.COLORS["log_bg"],
			text_color=theme.COLORS["log_fg"],
			wrap="word",
			activate_scrollbars=True,
			corner_radius=12,
			border_width=0,
			height=180,
		)
		self.log_text.pack(fill="both", expand=True, padx=12, pady=12)
		self.log_text.configure(state="disabled")
		self._configure_log_tags()

		# --- Status bar ---
		self.status_bar = theme.make_card(outer, radius=16)
		self.status_bar.grid(row=4, column=0, sticky="ew")
		status_inner = ctk.CTkFrame(self.status_bar, fg_color="transparent")
		status_inner.pack(fill="x", padx=18, pady=14)
		self.status_dot = ctk.CTkLabel(
			status_inner,
			text="●",
			width=18,
			font=theme.font(15),
			text_color=theme.COLORS["idle"],
		)
		self.status_dot.pack(side="left", padx=(0, 10))
		self.status_label = ctk.CTkLabel(
			status_inner,
			text="Ready to run",
			font=theme.font(13),
			text_color=theme.COLORS["text"],
		)
		self.status_label.pack(side="left")
		self.run_count_label = ctk.CTkLabel(
			status_inner,
			text="0 runs",
			font=theme.font(12),
			fg_color=theme.COLORS["summary_pill"],
			text_color=theme.COLORS["muted"],
			corner_radius=10,
			padx=10,
			pady=3,
		)
		self.run_count_label.pack(side="right")

	def _configure_log_tags(self) -> None:
		textbox = self.log_text._textbox
		textbox.tag_configure("ok", foreground=theme.COLORS["log_ok"])
		textbox.tag_configure("fail", foreground=theme.COLORS["log_fail"])
		textbox.tag_configure("skip", foreground=theme.COLORS["log_skip"])
		textbox.tag_configure("warn", foreground=theme.COLORS["log_warn"])
		textbox.tag_configure("info", foreground=theme.COLORS["log_info"])
		textbox.tag_configure("banner", foreground=theme.COLORS["log_banner"])

	def _bind_shortcuts(self) -> None:
		self.bind("<Control-Return>", lambda _event: self.start_run())
		self.bind("<Control-r>", lambda _event: self.start_run())
		self.bind("<Escape>", lambda _event: self.stop_run())

	def _load_initial_state(self) -> None:
		for line, tag in self.controller.initial_log_lines():
			self._insert_log_line(line, tag)
		self._apply_snapshot(self.controller.initial_snapshot())

	def _on_log_line(self, line: str, tag: str | None) -> None:
		# Marshal onto the Tk main thread — never touch widgets from workers.
		self.after(0, lambda: self._insert_log_line(line, tag))

	def _on_state_changed(self, snapshot: controller.LauncherSnapshot) -> None:
		self.after(0, lambda s=snapshot: self._apply_snapshot(s))

	def _insert_log_line(self, line: str, tag: str | None) -> None:
		self.log_text.configure(state="normal")
		if tag:
			self.log_text._textbox.insert("end", line, tag)
		else:
			self.log_text.insert("end", line)
		self._trim_log_widget()
		self.log_text.see("end")
		self.log_text.configure(state="disabled")

	def _trim_log_widget(self) -> None:
		line_count = int(self.log_text._textbox.index("end-1c").split(".")[0])
		if line_count <= runtime.MAX_LOG_LINES:
			return

		extra = line_count - runtime.MAX_LOG_LINES
		self.log_text.configure(state="normal")
		self.log_text._textbox.delete("1.0", f"{extra + 1}.0")
		self.log_text.configure(state="disabled")

	def _build_progress_rows(self, rows: list[progress.StepRow]) -> None:
		for child in self.progress_frame.winfo_children():
			child.destroy()

		self._progress_row_widgets = {}
		if not rows:
			rows = self.controller.run_progress.step_rows()

		left_column = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
		left_column.pack(side="left", fill="both", expand=True, padx=(0, 8))
		right_column = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
		right_column.pack(side="left", fill="both", expand=True, padx=(8, 0))

		split_at = (len(rows) + 1) // 2
		for index, row in enumerate(rows):
			parent = left_column if index < split_at else right_column
			self._create_progress_row(parent, row.name)

	def _create_progress_row(self, parent: ctk.CTkFrame, name: str) -> None:
		row_frame = ctk.CTkFrame(
			parent,
			fg_color=theme.COLORS["progress_row"],
			corner_radius=14,
			border_width=0,
		)
		row_frame.pack(fill="x", pady=5, padx=2)
		row_frame.grid_columnconfigure(1, weight=1)

		accent = ctk.CTkFrame(
			row_frame,
			width=4,
			corner_radius=0,
			fg_color=theme.COLORS["progress_pending"],
		)
		accent.pack(side="left", fill="y", padx=(0, 0))

		inner = ctk.CTkFrame(row_frame, fg_color="transparent")
		inner.pack(side="left", fill="both", expand=True, padx=12, pady=10)

		icon_label = ctk.CTkLabel(inner, text="○", width=26, font=theme.font(15))
		icon_label.pack(side="left")

		text_col = ctk.CTkFrame(inner, fg_color="transparent")
		text_col.pack(side="left", fill="x", expand=True, padx=(8, 0))

		name_label = ctk.CTkLabel(
			text_col,
			text=name,
			font=theme.font(13),
			text_color=theme.COLORS["text"],
			anchor="w",
		)
		name_label.pack(anchor="w")
		detail_label = ctk.CTkLabel(
			text_col,
			text="",
			font=theme.font(11),
			text_color=theme.COLORS["muted"],
			anchor="w",
		)
		detail_label.pack(anchor="w")

		self._progress_row_widgets[name] = {
			"row_frame": row_frame,
			"accent": accent,
			"inner": inner,
			"text_col": text_col,
			"icon_label": icon_label,
			"name_label": name_label,
			"detail_label": detail_label,
		}

	def _apply_snapshot(self, snapshot: controller.LauncherSnapshot) -> None:
		if len(snapshot.progress_rows) != len(self._progress_row_widgets):
			self._build_progress_rows(snapshot.progress_rows)

		self.subtitle_label.configure(text=snapshot.subtitle)
		self.setup_chip_label.configure(text=f"  {snapshot.setup_strip}  ")
		self.progress_summary_label.configure(text=snapshot.progress_summary)
		self.status_label.configure(text=snapshot.status_text)
		self._status_tone = snapshot.status_tone
		self.status_dot.configure(text_color=theme.status_color(snapshot.status_tone))
		self.run_count_label.configure(text=snapshot.run_count_label)
		self.run_button.configure(
			text=snapshot.run_button_text,
			state="normal" if snapshot.run_enabled else "disabled",
		)
		self.stop_button.configure(state="normal" if snapshot.stop_enabled else "disabled")

		for row in snapshot.progress_rows:
			widgets = self._progress_row_widgets.get(row.name)
			if widgets is None:
				continue

			icon, color = theme.progress_icon_for_state(row.state)
			row_bg, accent_color = theme.progress_row_colors(row.state)
			widgets["icon_label"].configure(text=icon, text_color=color)
			name_font = theme.font(13, weight="bold" if row.state == "running" else "normal")
			name_kwargs: dict = {"text": row.name, "font": name_font}
			if row.state == "running":
				name_kwargs["text_color"] = theme.COLORS["progress_running"]
			else:
				name_kwargs["text_color"] = theme.COLORS["text"]
			widgets["name_label"].configure(**name_kwargs)
			widgets["detail_label"].configure(text=row.detail or "")
			widgets["row_frame"].configure(fg_color=row_bg)
			widgets["accent"].configure(fg_color=accent_color)

	def _toggle_log_visibility(self) -> None:
		self._log_visible = not self._log_visible
		if self._log_visible:
			self.log_section.grid(row=4, column=0, sticky="nsew", pady=(0, 14))
			self.status_bar.grid(row=5, column=0, sticky="ew")
			self.log_toggle_button.configure(text="Hide")
		else:
			self.log_section.grid_remove()
			self.status_bar.grid(row=4, column=0, sticky="ew")
			self.log_toggle_button.configure(text="Show")

	def _pulse_status(self) -> None:
		if not self.winfo_exists():
			return
		if self._status_tone == "running":
			self._pulse_on = not self._pulse_on
			color = theme.COLORS["accent"] if self._pulse_on else theme.COLORS["accent_hover"]
			self.status_dot.configure(text_color=color)
		else:
			self._pulse_on = False
			self.status_dot.configure(text_color=theme.status_color(self._status_tone))
		self._pulse_after_id = self.after(700, self._pulse_status)

	def _poll_output(self) -> None:
		if not self.winfo_exists():
			return
		self.controller.poll_output()
		self._poll_after_id = self.after(100, self._poll_output)

	def _cancel_scheduled(self) -> None:
		for attr in ("_poll_after_id", "_pulse_after_id"):
			job = getattr(self, attr, None)
			if job is not None:
				try:
					self.after_cancel(job)
				except Exception:
					pass
				setattr(self, attr, None)

	def start_run(self) -> None:
		error = self.controller.start_run()
		if error:
			if "Setup" in error or "Missing" in error or "data-dir" in error:
				messagebox.showerror("Setup required", error)
			else:
				messagebox.showerror("Could not start", error)

	def stop_run(self) -> None:
		self.controller.stop_run()

	def clear_log(self) -> None:
		error = self.controller.clear_log()
		if error:
			messagebox.showinfo("Run in progress", error)
			return

		self.log_text.configure(state="normal")
		self.log_text.delete("1.0", "end")
		self.log_text.configure(state="disabled")

	def open_logs_folder(self) -> None:
		try:
			self.controller.open_logs_folder()
		except OSError as exc:
			messagebox.showerror("Could not open folder", str(exc))

	def open_profile_folder(self) -> None:
		try:
			self.controller.open_profile_folder()
		except OSError as exc:
			messagebox.showerror("Could not open folder", str(exc))

	def _on_close(self) -> None:
		if self.controller.is_run_active():
			if not messagebox.askyesno(
				"Run in progress",
				"A run is still going. Stop it and close?",
			):
				return

			self.stop_run()
			self.after(200, self._wait_for_shutdown_then_close)
			return

		self._cancel_scheduled()
		self.destroy()

	def _wait_for_shutdown_then_close(self) -> None:
		if self.controller.is_run_active():
			self.after(200, self._wait_for_shutdown_then_close)
			return

		self._cancel_scheduled()
		self.destroy()


def main() -> None:
	install_crash_hooks()
	lock_handle = None
	app = None
	try:
		lock_handle = runtime.acquire_single_instance()
		if lock_handle is None:
			root = ctk.CTk()
			root.withdraw()
			messagebox.showwarning(
				"Already open",
				"Rewards Farmer is already running.\n\nCheck your taskbar for an existing window.",
			)
			root.destroy()
			return

		app = LauncherApp()
		app._lock_handle = lock_handle
		app.mainloop()
	except Exception as exc:
		write_crash_log(exc)
		raise
	finally:
		handle = None
		if app is not None:
			handle = getattr(app, "_lock_handle", None)
		elif lock_handle is not None:
			handle = lock_handle
		if handle is not None:
			try:
				handle.close()
			except OSError:
				pass


if __name__ == "__main__":
	main()
