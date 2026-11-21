"""Invoke the deployed managed agent and export service traces to Oodle."""

import argparse
import json
import os
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv

from managed_agent import DEFAULT_PROMPT, run_agent
from telemetry import setup_telemetry


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--session-id")
    args = parser.parse_args()
    session = boto3.Session(region_name=os.environ.get("AWS_REGION", "us-west-2"))
    agent_id = os.environ.get("BEDROCK_AGENT_ID")
    alias_id = os.environ.get("BEDROCK_AGENT_ALIAS_ID", "TSTALIASID")
    if not agent_id:
        stack = session.client("cloudformation").describe_stacks(
            StackName=os.environ.get("STACK_NAME", "oodle-bedrock-managed-agents-demo"),
        )["Stacks"][0]
        outputs = {x["OutputKey"]: x["OutputValue"] for x in stack.get("Outputs", [])}
        agent_id = outputs.get("AgentId")
        if not agent_id:
            raise RuntimeError("Stack has no agent output; complete make deploy first")
    provider = setup_telemetry("amazon-bedrock-managed-agents-demo")
    try:
        client = session.client("bedrock-agent-runtime", config=Config(
            connect_timeout=10, read_timeout=120, retries={"max_attempts": 2},
        ))
        print(json.dumps(run_agent(client, agent_id, alias_id, args.prompt, args.session_id), indent=2))
    finally:
        provider.shutdown()


if __name__ == "__main__":
    main()
