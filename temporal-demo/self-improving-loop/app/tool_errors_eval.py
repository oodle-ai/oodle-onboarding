"""Oodle code evaluator: did the agent get every tool call right first time?

Uploaded to Oodle as the source of a code evaluator template (see oodle.py). On a
webhook experiment, Oodle hands it the agent's whole trace as ctx.trace.spans, so it
scores what the agent actually did, not what it said. Runs in Oodle's sandbox:
standard library only, no getattr/eval/open.
"""


def evaluate(ctx):
    spans = (ctx.trace.spans if ctx.trace else None) or []
    tools = [s for s in spans if s.get("kind") == "tool"]
    failed = [s for s in tools if s.get("error")]
    model_calls = sum(1 for s in spans if s.get("kind") == "llm")

    # Every ticket needs at least one tool call. No tool spans means the trace never
    # reached Oodle, and that must not read as a clean run.
    if not tools:
        return EvaluationResult(scores=[
            Score(name="no_tool_errors", value=False, data_type="BOOLEAN",
                  comment="no tool calls found in the trace"),
        ])

    detail = "; ".join(
        f"{s.get('tool_name') or s.get('name')}: "
        f"{str(s.get('error_message') or s.get('output') or 'failed')[:160]}"
        for s in failed)
    return EvaluationResult(scores=[
        Score(name="no_tool_errors", value=not failed, data_type="BOOLEAN",
              comment=detail or f"all {len(tools)} tool calls succeeded"),
        Score(name="tool_errors", value=float(len(failed)), higher_is_better=False,
              comment=f"{len(failed)} of {len(tools)} tool calls failed"),
        Score(name="model_calls", value=float(model_calls), higher_is_better=False),
    ])
