"""Visual theme helpers for the CustomTkinter desktop launcher."""

from __future__ import annotations

import os
import sys

import customtkinter as ctk

try:
	from PIL import Image, ImageTk
except ImportError:
	Image = None  # type: ignore
	ImageTk = None  # type: ignore

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_PATH = os.path.join(REPO_ROOT, "assets", "rewards-farmer.ico")
ICON_PNG_PATH = os.path.join(REPO_ROOT, "assets", "rewards-farmer.png")

# Soft slate + teal — reads as a product app, not a default CTk green theme.
COLORS = {
	"accent": "#0D9488",
	"accent_hover": "#14B8A6",
	"accent_pressed": "#0F766E",
	"accent_soft": ("#CCFBF1", "#134E4A"),
	"accent_deep": ("#115E59", "#5EEAD4"),
	"stop": "#E11D48",
	"stop_hover": ("#FFE4E6", "#4C0519"),
	"success": "#059669",
	"warning": "#D97706",
	"danger": "#E11D48",
	"idle": "#94A3B8",
	"muted": ("#64748B", "#94A3B8"),
	"text": ("#0F172A", "#F1F5F9"),
	"text_secondary": ("#475569", "#CBD5E1"),
	"window_bg": ("#E8EEF5", "#0A1018"),
	"card": ("#FFFFFF", "#121A26"),
	"card_border": ("#D8E0EA", "#1E2A3A"),
	"hero_tint": ("#F0FDFA", "#0F1C1A"),
	"chip_bg": ("#F1F5F9", "#1A2433"),
	"chip_border": ("#E2E8F0", "#2A3A4E"),
	"section_label": ("#64748B", "#64748B"),
	"log_bg": ("#0B1220", "#020617"),
	"log_fg": "#CBD5E1",
	"log_ok": "#34D399",
	"log_skip": "#FBBF24",
	"log_fail": "#FB7185",
	"log_warn": "#FB923C",
	"log_info": "#38BDF8",
	"log_banner": "#67E8F9",
	"progress_pending": "#94A3B8",
	"progress_running": "#0D9488",
	"progress_ok": "#059669",
	"progress_skip": "#D97706",
	"progress_fail": "#E11D48",
	"progress_running_bg": ("#CCFBF1", "#134E4A"),
	"progress_ok_bg": ("#ECFDF5", "#064E3B"),
	"progress_skip_bg": ("#FFFBEB", "#451A03"),
	"progress_fail_bg": ("#FFF1F2", "#4C0519"),
	"progress_row": ("#F8FAFC", "#182232"),
	"ghost_hover": ("#E8EEF5", "#1A2433"),
	"summary_pill": ("#EEF2F7", "#1A2433"),
}


def _ui_font_family() -> str:
	if sys.platform == "win32":
		return "Segoe UI"
	if sys.platform == "darwin":
		return "SF Pro Text"
	return "Sans"


def apply_theme() -> None:
	ctk.set_appearance_mode("system")
	ctk.set_default_color_theme("green")
	ctk.set_widget_scaling(1.0)
	ctk.set_window_scaling(1.0)


def apply_window_icon(window: ctk.CTk) -> None:
	if os.path.isfile(ICON_PATH):
		try:
			window.iconbitmap(default=ICON_PATH)
		except Exception:
			pass


def load_header_icon(size: int = 52):
	if Image is None or ImageTk is None or not os.path.isfile(ICON_PNG_PATH):
		return None

	image = Image.open(ICON_PNG_PATH).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
	return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


def font(size: int = 13, *, weight: str = "normal", family: str | None = None) -> ctk.CTkFont:
	kwargs = {"family": family or _ui_font_family(), "size": size, "weight": weight}
	return ctk.CTkFont(**kwargs)


def mono_font(size: int = 12) -> ctk.CTkFont:
	family = "Consolas" if sys.platform == "win32" else "Menlo"
	return font(size, family=family)


def make_card(
	parent,
	*,
	radius: int = 18,
	padx: int = 0,
	pady: int = 0,
	fg_color=None,
) -> ctk.CTkFrame:
	card = ctk.CTkFrame(
		parent,
		corner_radius=radius,
		fg_color=fg_color if fg_color is not None else COLORS["card"],
		border_width=1,
		border_color=COLORS["card_border"],
	)
	if padx or pady:
		inner = ctk.CTkFrame(card, fg_color="transparent")
		inner.pack(fill="both", expand=True, padx=padx, pady=pady)
		return inner
	return card


def make_section_label(parent, text: str) -> ctk.CTkLabel:
	return ctk.CTkLabel(
		parent,
		text=text.upper(),
		font=font(11, weight="bold"),
		text_color=COLORS["section_label"],
		anchor="w",
	)


def make_ghost_button(
	parent,
	*,
	text: str,
	command,
	width: int = 100,
	height: int = 36,
) -> ctk.CTkButton:
	return ctk.CTkButton(
		parent,
		text=text,
		command=command,
		width=width,
		height=height,
		corner_radius=11,
		fg_color="transparent",
		border_width=1,
		border_color=COLORS["card_border"],
		text_color=COLORS["text_secondary"],
		hover_color=COLORS["ghost_hover"],
		font=font(12),
	)


def make_primary_button(
	parent,
	*,
	text: str,
	command,
	width: int = 132,
	height: int = 44,
) -> ctk.CTkButton:
	return ctk.CTkButton(
		parent,
		text=text,
		command=command,
		width=width,
		height=height,
		corner_radius=12,
		fg_color=COLORS["accent"],
		hover_color=COLORS["accent_hover"],
		text_color="#FFFFFF",
		font=font(15, weight="bold"),
	)


def progress_icon_for_state(state: str) -> tuple[str, str]:
	return {
		"pending": ("○", COLORS["progress_pending"]),
		"running": ("●", COLORS["progress_running"]),
		"ok": ("✓", COLORS["progress_ok"]),
		"skip": ("–", COLORS["progress_skip"]),
		"fail": ("✕", COLORS["progress_fail"]),
	}.get(state, ("○", COLORS["progress_pending"]))


def progress_row_colors(state: str) -> tuple[object, str]:
	"""Return (row_bg, accent_strip_color) for a progress state."""
	mapping = {
		"pending": (COLORS["progress_row"], COLORS["progress_pending"]),
		"running": (COLORS["progress_running_bg"], COLORS["progress_running"]),
		"ok": (COLORS["progress_ok_bg"], COLORS["progress_ok"]),
		"skip": (COLORS["progress_skip_bg"], COLORS["progress_skip"]),
		"fail": (COLORS["progress_fail_bg"], COLORS["progress_fail"]),
	}
	return mapping.get(state, (COLORS["progress_row"], COLORS["progress_pending"]))


def status_color(tone: str) -> str:
	return {
		"idle": COLORS["idle"],
		"running": COLORS["accent"],
		"success": COLORS["success"],
		"warning": COLORS["warning"],
		"danger": COLORS["danger"],
	}.get(tone, COLORS["idle"])
