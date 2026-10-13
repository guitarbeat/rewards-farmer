"""Dispatch webhook notifications on run completion or failure.

Supports Discord webhooks and generic JSON POST webhooks without external dependencies.
Configured via WEBHOOK_URL and WEBHOOK_NOTIFY_ON_FAILURE_ONLY in .env.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("notifications")


def get_webhook_url() -> str | None:
	"""Return trimmed webhook URL from environment if configured."""
	url = os.environ.get("WEBHOOK_URL", "").strip()
	return url or None


def notify_on_failure_only() -> bool:
	"""Whether to only send notifications on failed runs."""
	return os.environ.get("WEBHOOK_NOTIFY_ON_FAILURE_ONLY", "").strip().lower() in (
		"1",
		"true",
		"yes",
	)


def is_discord_webhook(url: str) -> bool:
	"""Whether the URL points to the Discord Webhook API."""
	return "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url


def build_discord_payload(
	*,
	title: str,
	description: str,
	status: str,
	points_earned: int | None = None,
	duration_seconds: float | None = None,
	profile: str | None = None,
	extra_fields: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
	"""Build a rich Discord embed payload."""
	# 0x2ECC71: Green (Success), 0xE67E22: Orange (Warning), 0xE74C3C: Red (Failure)
	if status.upper() in ("SUCCESS", "OK"):
		color = 0x2ECC71
	elif status.upper() in ("PARTIAL", "WARNING", "WARN"):
		color = 0xE67E22
	else:
		color = 0xE74C3C

	fields = []
	if profile:
		fields.append({"name": "Profile", "value": profile, "inline": True})
	if points_earned is not None:
		fields.append({"name": "Points Earned", "value": f"+{points_earned}", "inline": True})
	if duration_seconds is not None:
		mins = int(duration_seconds // 60)
		secs = int(duration_seconds % 60)
		time_str = f"{mins}m {secs}s" if mins else f"{secs}s"
		fields.append({"name": "Duration", "value": time_str, "inline": True})

	if extra_fields:
		for name, val in extra_fields:
			fields.append({"name": name, "value": str(val), "inline": True})

	embed = {
		"title": title,
		"description": description,
		"color": color,
		"fields": fields,
		"footer": {"text": "Rewards Farmer Bot"},
	}

	return {
		"username": "Rewards Farmer",
		"embeds": [embed],
	}


def build_generic_payload(
	*,
	title: str,
	description: str,
	status: str,
	points_earned: int | None = None,
	duration_seconds: float | None = None,
	profile: str | None = None,
	extra_fields: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
	"""Build generic JSON payload for standard webhooks."""
	payload: dict[str, Any] = {
		"title": title,
		"description": description,
		"status": status,
		"timestamp": os.environ.get("RUN_TIMESTAMP", ""),
	}
	if profile:
		payload["profile"] = profile
	if points_earned is not None:
		payload["points_earned"] = points_earned
	if duration_seconds is not None:
		payload["duration_seconds"] = duration_seconds
	if extra_fields:
		payload["details"] = dict(extra_fields)
	return payload


def send_webhook_notification(
	*,
	title: str,
	description: str,
	status: str = "SUCCESS",
	points_earned: int | None = None,
	duration_seconds: float | None = None,
	profile: str | None = None,
	extra_fields: list[tuple[str, str]] | None = None,
	webhook_url: str | None = None,
	timeout_seconds: float = 10.0,
) -> bool:
	"""Send webhook notification via HTTP POST. Returns True if successfully delivered."""
	url = webhook_url or get_webhook_url()
	if not url:
		return False

	is_fail = status.upper() not in ("SUCCESS", "OK")
	if notify_on_failure_only() and not is_fail:
		logger.debug("Skipping webhook notification: WEBHOOK_NOTIFY_ON_FAILURE_ONLY is enabled.")
		return False

	if is_discord_webhook(url):
		payload = build_discord_payload(
			title=title,
			description=description,
			status=status,
			points_earned=points_earned,
			duration_seconds=duration_seconds,
			profile=profile,
			extra_fields=extra_fields,
		)
	else:
		payload = build_generic_payload(
			title=title,
			description=description,
			status=status,
			points_earned=points_earned,
			duration_seconds=duration_seconds,
			profile=profile,
			extra_fields=extra_fields,
		)

	try:
		raw_data = json.dumps(payload).encode("utf-8")
		req = urllib.request.Request(
			url,
			data=raw_data,
			headers={
				"Content-Type": "application/json",
				"User-Agent": "Rewards-Farmer/1.0",
			},
			method="POST",
		)
		with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
			if resp.status in (200, 204):
				logger.info("Webhook notification delivered successfully (%s).", resp.status)
				return True
			logger.warning("Webhook returned unexpected HTTP %s.", resp.status)
			return False
	except Exception as exc:
		logger.warning("Failed to deliver webhook notification: %s", exc)
		return False
