"""Check turn outcomes with real Laminar spans and a local exporter."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from lmnr import Laminar
from lmnr.opentelemetry_lib.tracing import TracerWrapper
from lmnr.opentelemetry_lib.tracing.instruments import Instruments
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from turn_attribution import trace_turn

EXPORTER = InMemorySpanExporter()
TURN_KEYS = {
    "agent.trigger", "agent.outcome", "agent.stop_reason",
    "agent.batch_count", "agent.mid_run_human_input",
}


def setUpModule() -> None:
    # Laminar keeps one provider per process. Initialize it before importing decorators.
    os.environ["MOCK_LLM"] = "true"
    TracerWrapper(
        disable_batch=True,
        exporter=EXPORTER,
        project_api_key="local",
        block_instruments={Instruments.LITELLM},
    )
    Laminar.initialize(project_api_key="local", disabled_instruments={Instruments.LITELLM})
    global agent
    import agent


class TurnSpanTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        EXPORTER.clear()

    def root_attributes(self) -> dict:
        roots = [span for span in EXPORTER.get_finished_spans() if span.name == "session_workflow"]
        self.assertEqual(len(roots), 1)
        self.assertIsNone(roots[0].parent)
        return dict(roots[0].attributes or {})

    async def test_each_followup_has_its_own_turn(self) -> None:
        result = await agent.run_session("Describe the repository", ["Which tests exist?"])

        roots = [span for span in EXPORTER.get_finished_spans() if span.name == "session_workflow"]
        self.assertEqual(len(roots), 2)
        self.assertEqual(len(set(result["trace_ids"])), 2)
        for root in roots:
            self.assertIsNone(root.parent)
            self.assertEqual(
                {key: value for key, value in root.attributes.items() if key in TURN_KEYS},
                {"agent.trigger": "human", "agent.outcome": "ended",
                 "agent.batch_count": 1, "agent.mid_run_human_input": False},
            )
        children = [span for span in EXPORTER.get_finished_spans() if span.name != "session_workflow"]
        self.assertTrue(any(span.name == "subagent [explore]" for span in children))
        self.assertFalse(any(TURN_KEYS.intersection(span.attributes or {}) for span in children))

    async def test_title_failure_preserves_the_exception(self) -> None:
        error = ValueError("title failed")
        with patch.object(agent, "_generate_title", AsyncMock(side_effect=error)):
            with self.assertRaises(ValueError) as raised:
                await agent.run_session("Describe the repository")

        self.assertIs(raised.exception, error)
        self.assertEqual(self.root_attributes()["agent.outcome"], "failed")

    async def test_tool_failure_preserves_the_exception(self) -> None:
        error = ValueError("tool failed")
        with patch.object(agent, "_run_tool", AsyncMock(side_effect=error)):
            with self.assertRaises(ValueError) as raised:
                await agent.run_session("Describe the repository")

        self.assertIs(raised.exception, error)
        self.assertEqual(self.root_attributes()["agent.outcome"], "failed")

    async def test_cancelled_task_records_cancelled(self) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def wait_for_tool(*args):
            entered.set()
            await release.wait()

        with patch.object(agent, "_run_tool", wait_for_tool):
            task = asyncio.create_task(agent.run_session("Describe the repository"))
            try:
                await asyncio.wait_for(entered.wait(), timeout=10)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

        self.assertEqual(self.root_attributes()["agent.outcome"], "cancelled")

    async def test_loop_limit_records_a_stop_reason(self) -> None:
        with patch.object(agent, "MAX_TURNS", 1):
            result = await agent.run_session("Describe the repository")

        self.assertIsNone(result["answer"])
        attributes = self.root_attributes()
        self.assertEqual(attributes["agent.outcome"], "ended")
        self.assertEqual(attributes["agent.stop_reason"], "max_turns")


class TelemetryFailureTests(unittest.TestCase):
    def test_attribute_failure_does_not_replace_the_run_error(self) -> None:
        span = Mock()
        span.is_recording.return_value = True
        span.set_attribute.side_effect = RuntimeError("telemetry failed")
        error = ValueError("run failed")

        with patch("turn_attribution.trace.get_current_span", return_value=span):
            with self.assertRaises(ValueError) as raised:
                with trace_turn():
                    raise error

        self.assertIs(raised.exception, error)

    def test_missing_span_does_not_prevent_completion(self) -> None:
        with patch("turn_attribution.trace.get_current_span", return_value=trace.INVALID_SPAN):
            with trace_turn() as turn:
                turn.stop_reason = "max_turns"

    def test_span_lookup_failure_does_not_prevent_completion(self) -> None:
        with patch("turn_attribution.trace.get_current_span", side_effect=RuntimeError("lookup failed")):
            with trace_turn():
                pass


if __name__ == "__main__":
    unittest.main()
