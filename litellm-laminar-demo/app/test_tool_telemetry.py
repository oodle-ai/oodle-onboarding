"""Check tool span outcomes and model finish reasons with real Laminar spans."""

import json
import os
import unittest
from types import SimpleNamespace

from lmnr import Laminar
from lmnr.opentelemetry_lib.tracing import TracerWrapper
from lmnr.opentelemetry_lib.tracing.instruments import Instruments
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from finish_reason import FinishReasonTracker

EXPORTER = InMemorySpanExporter()


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
    global agent, route_audit
    import agent
    import route_audit


def _bash_call(command: str) -> dict:
    return {
        "id": "call_1",
        "function": {"name": "bash_execute", "arguments": json.dumps({"command": command})},
    }


class ToolSpanTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        EXPORTER.clear()

    def spans(self, prefix: str) -> list:
        return [span for span in EXPORTER.get_finished_spans() if span.name.startswith(prefix)]

    async def test_session_names_every_tool_span_and_records_finish_reasons(self) -> None:
        await agent.run_session("Describe the repository")

        tool_spans = self.spans("tool_call [")
        self.assertEqual(
            {span.name for span in tool_spans}, {"tool_call [bash_execute]", "tool_call [add_task]"}
        )
        for span in tool_spans:
            self.assertEqual(span.name, f"tool_call [{span.attributes['gen_ai.tool.name']}]")
            # With an operation name next to the tool name, Laminar renames the span.
            self.assertNotIn("gen_ai.operation.name", span.attributes)
            self.assertTrue(span.attributes["gen_ai.tool.call.id"])
        for span in self.spans("tool_call [bash_execute]"):
            self.assertEqual(span.attributes["process.exit.code"], 0)
            self.assertIsNot(span.status.status_code, StatusCode.ERROR)

        streams = self.spans("llm_call_stream")
        self.assertTrue(streams)
        for span in streams:
            self.assertEqual(len(span.attributes["gen_ai.response.finish_reasons"]), 1)

    async def test_failed_command_marks_the_tool_span_without_its_output(self) -> None:
        scope = route_audit.ExecutionScope("demo-account", "session-1", "explore-1")
        await agent._run_tool(scope, _bash_call("rm -rf secret-dir"))

        [span] = self.spans("tool_call [bash_execute]")
        self.assertEqual(span.attributes["process.exit.code"], 127)
        self.assertIs(span.status.status_code, StatusCode.ERROR)
        self.assertEqual(span.status.description, "exited with code 127")
        [event] = span.events
        self.assertEqual(event.name, "exception")
        self.assertNotIn("secret-dir", json.dumps(dict(event.attributes)))


class FinishReasonTrackerTests(unittest.TestCase):
    def test_keeps_the_last_reason_across_a_trailing_usage_chunk(self) -> None:
        tracker = FinishReasonTracker()
        for reason in ("length", None, ""):
            tracker.observe(SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason)]))
        tracker.observe(SimpleNamespace(choices=[], usage=object()))
        tracker.observe(None)

        recorded: dict = {}
        tracker.record_on(SimpleNamespace(set_attribute=recorded.__setitem__))
        self.assertEqual(recorded, {"gen_ai.response.finish_reasons": ["length"]})
