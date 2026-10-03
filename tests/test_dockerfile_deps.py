"""Guardrails for the Docker runtime image."""

from __future__ import annotations

import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCKERFILE = os.path.join(REPO_ROOT, "Dockerfile")


class DockerfileRuntimeDepsTests(unittest.TestCase):
	def test_installs_dotenv_requests_and_pillow(self) -> None:
		with open(DOCKERFILE, encoding="utf-8") as handle:
			text = handle.read()

		self.assertIn("python-dotenv", text)
		self.assertIn("requests", text)
		self.assertIn("pillow", text)
		self.assertIn("selenium", text)


if __name__ == "__main__":
	unittest.main()
