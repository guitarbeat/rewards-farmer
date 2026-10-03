"""Visual search image fallbacks and cookie-banner helper."""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from fakes import FakeDriver, FakeElement
from selenium.webdriver.common.by import By

import random_image_for_visual_search
from sites.ms_rewards.tasks.visual_search import dismiss_cookie_banners


class EnsureVisualSearchImage(unittest.TestCase):
	def test_reuses_existing_file_when_not_forced(self) -> None:
		with mock.patch.object(random_image_for_visual_search, "_usable_image_path", return_value="/tmp/visual_search.jpg"):
			with mock.patch.object(random_image_for_visual_search, "get_random_image") as download:
				path = random_image_for_visual_search.ensure_visual_search_image(force_refresh=False)
		self.assertEqual(path, "/tmp/visual_search.jpg")
		download.assert_not_called()

	def test_force_refresh_tries_wikipedia_first(self) -> None:
		with mock.patch.object(random_image_for_visual_search, "get_random_image"):
			with mock.patch.object(
				random_image_for_visual_search,
				"_usable_image_path",
				return_value="/tmp/fresh.jpg",
			):
				path = random_image_for_visual_search.ensure_visual_search_image(force_refresh=True)
		self.assertEqual(path, "/tmp/fresh.jpg")

	def test_falls_back_to_synthetic_image(self) -> None:
		with mock.patch.object(random_image_for_visual_search, "get_random_image"):
			with mock.patch.object(random_image_for_visual_search, "generate_fallback_image") as synth:
				with mock.patch.object(
					random_image_for_visual_search,
					"_usable_image_path",
					side_effect=[None, "/tmp/synth.jpg"],
				):
					path = random_image_for_visual_search.ensure_visual_search_image(force_refresh=True)
		self.assertEqual(path, "/tmp/synth.jpg")
		synth.assert_called_once()


class CookieBanner(unittest.TestCase):
	def test_clicks_visible_accept_button(self) -> None:
		btn = FakeElement(displayed=True)
		clicked = []
		driver = FakeDriver(children={(By.CSS_SELECTOR, "#bnp_btn_accept"): [btn]})
		driver.execute_script = lambda script, *args: clicked.append(args[0] if args else script)

		self.assertTrue(dismiss_cookie_banners(driver))
		self.assertEqual(clicked, [btn])


if __name__ == "__main__":
	unittest.main()
