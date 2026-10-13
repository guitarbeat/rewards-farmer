"""Unit tests for src/notifications.py webhook dispatcher."""

import json
import os
import sys
import unittest
from unittest import mock
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import notifications


class NotificationsTests(unittest.TestCase):
	def setUp(self):
		self.orig_env = os.environ.copy()

	def tearDown(self):
		os.environ.clear()
		os.environ.update(self.orig_env)

	def test_get_webhook_url_none_when_empty(self):
		os.environ.pop("WEBHOOK_URL", None)
		self.assertIsNone(notifications.get_webhook_url())

		os.environ["WEBHOOK_URL"] = "   "
		self.assertIsNone(notifications.get_webhook_url())

	def test_get_webhook_url_trimmed(self):
		os.environ["WEBHOOK_URL"] = "  https://discord.com/api/webhooks/123/abc  "
		self.assertEqual(
			notifications.get_webhook_url(),
			"https://discord.com/api/webhooks/123/abc",
		)

	def test_is_discord_webhook(self):
		self.assertTrue(notifications.is_discord_webhook("https://discord.com/api/webhooks/123/abc"))
		self.assertTrue(notifications.is_discord_webhook("https://discordapp.com/api/webhooks/123/abc"))
		self.assertFalse(notifications.is_discord_webhook("https://hooks.slack.com/services/123/abc"))
		self.assertFalse(notifications.is_discord_webhook("https://example.com/api/webhook"))

	def test_build_discord_payload_formatting(self):
		payload = notifications.build_discord_payload(
			title="Run #1 Completed",
			description="Points earned successfully",
			status="SUCCESS",
			points_earned=150,
			duration_seconds=95.5,
			profile="Default",
			extra_fields=[("Extra", "Value")],
		)

		self.assertEqual(payload["username"], "Rewards Farmer")
		self.assertEqual(len(payload["embeds"]), 1)
		embed = payload["embeds"][0]
		self.assertEqual(embed["title"], "Run #1 Completed")
		self.assertEqual(embed["color"], 0x2ECC71)  # Green
		field_names = [f["name"] for f in embed["fields"]]
		self.assertIn("Profile", field_names)
		self.assertIn("Points Earned", field_names)
		self.assertIn("Duration", field_names)
		self.assertIn("Extra", field_names)

	def test_build_discord_payload_failure_color(self):
		payload = notifications.build_discord_payload(
			title="Run #2 Failed",
			description="Error occurred",
			status="FAILURE",
		)
		self.assertEqual(payload["embeds"][0]["color"], 0xE74C3C)  # Red

	def test_build_generic_payload(self):
		payload = notifications.build_generic_payload(
			title="Run Finished",
			description="All good",
			status="OK",
			points_earned=30,
			duration_seconds=12.0,
			profile="Spare",
		)
		self.assertEqual(payload["title"], "Run Finished")
		self.assertEqual(payload["status"], "OK")
		self.assertEqual(payload["points_earned"], 30)
		self.assertEqual(payload["profile"], "Spare")

	@mock.patch("urllib.request.urlopen")
	def test_send_webhook_notification_success(self, mock_urlopen):
		cm = mock.MagicMock()
		cm.status = 204
		cm.__enter__.return_value = cm
		mock_urlopen.return_value = cm

		success = notifications.send_webhook_notification(
			title="Test",
			description="Test run",
			status="SUCCESS",
			webhook_url="https://discord.com/api/webhooks/test",
		)
		self.assertTrue(success)
		mock_urlopen.assert_called_once()
		req = mock_urlopen.call_args[0][0]
		self.assertEqual(req.get_method(), "POST")
		self.assertEqual(req.full_url, "https://discord.com/api/webhooks/test")

	@mock.patch("urllib.request.urlopen")
	def test_notify_on_failure_only_filters_success(self, mock_urlopen):
		os.environ["WEBHOOK_NOTIFY_ON_FAILURE_ONLY"] = "true"
		success = notifications.send_webhook_notification(
			title="Success Run",
			description="All good",
			status="SUCCESS",
			webhook_url="https://discord.com/api/webhooks/test",
		)
		self.assertFalse(success)
		mock_urlopen.assert_not_called()

	@mock.patch("urllib.request.urlopen")
	def test_notify_on_failure_only_allows_failure(self, mock_urlopen):
		os.environ["WEBHOOK_NOTIFY_ON_FAILURE_ONLY"] = "true"
		cm = mock.MagicMock()
		cm.status = 200
		cm.__enter__.return_value = cm
		mock_urlopen.return_value = cm

		success = notifications.send_webhook_notification(
			title="Failed Run",
			description="Error occurred",
			status="FAIL",
			webhook_url="https://discord.com/api/webhooks/test",
		)
		self.assertTrue(success)
		mock_urlopen.assert_called_once()

	@mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused"))
	def test_network_failure_returns_false_without_raising(self, mock_urlopen):
		success = notifications.send_webhook_notification(
			title="Network test",
			description="Should handle gracefully",
			webhook_url="https://example.com/webhook",
		)
		self.assertFalse(success)


if __name__ == "__main__":
	unittest.main()
