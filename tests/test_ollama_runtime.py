"""Tests for Ollama startup helpers and query-source fallback."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import ollama_runtime
import queries


class OllamaRuntimeTests(unittest.TestCase):
	def test_is_api_reachable_true_on_http_200(self) -> None:
		response = mock.Mock()
		response.__enter__ = mock.Mock(return_value=response)
		response.__exit__ = mock.Mock(return_value=False)
		response.status = 200

		with mock.patch("ollama_runtime.urllib.request.urlopen", return_value=response):
			self.assertTrue(ollama_runtime.is_api_reachable())

	def test_ensure_ready_returns_true_when_api_already_up(self) -> None:
		with mock.patch.object(ollama_runtime, "is_api_reachable", return_value=True):
			with mock.patch.object(ollama_runtime, "start_ollama_server") as start:
				self.assertTrue(ollama_runtime.ensure_ready())
		start.assert_not_called()

	def test_ensure_ready_starts_server_when_api_is_down(self) -> None:
		with mock.patch.object(
			ollama_runtime,
			"is_api_reachable",
			side_effect=[False, False, True],
		):
			with mock.patch.object(ollama_runtime, "start_ollama_server", return_value=True) as start:
				self.assertTrue(ollama_runtime.ensure_ready(timeout=1))
		start.assert_called_once()


class QuerySourceFallbackTests(unittest.TestCase):
	def setUp(self) -> None:
		queries.reset_resolved_source_for_tests()
		self._original = os.environ.get(queries.ENV_VAR)

	def tearDown(self) -> None:
		queries.reset_resolved_source_for_tests()
		if self._original is None:
			os.environ.pop(queries.ENV_VAR, None)
		else:
			os.environ[queries.ENV_VAR] = self._original

	def test_resolve_source_uses_trends_when_requested(self) -> None:
		os.environ[queries.ENV_VAR] = queries.TRENDS
		self.assertEqual(queries.resolve_source(), queries.TRENDS)

	def test_resolve_source_falls_back_to_trends_when_ollama_unavailable(self) -> None:
		os.environ[queries.ENV_VAR] = queries.LLM
		with mock.patch("ollama_runtime.ensure_ready", return_value=False):
			self.assertEqual(queries.resolve_source(), queries.TRENDS)

	def test_resolve_source_uses_llm_when_ollama_is_ready(self) -> None:
		os.environ[queries.ENV_VAR] = queries.LLM
		with mock.patch("ollama_runtime.ensure_ready", return_value=True):
			self.assertEqual(queries.resolve_source(), queries.LLM)


if __name__ == "__main__":
	unittest.main()
