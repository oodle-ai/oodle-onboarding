"""Run one order-support request using Amazon Bedrock."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from telemetry import setup_telemetry


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt")
    parser.add_argument("--session-id")
    args = parser.parse_args()
    provider = setup_telemetry("amazon-bedrock-demo")
    # Initialize telemetry before importing and constructing the agent.
    from support_agent import DEFAULT_PROMPT, run_agent

    try:
        print(json.dumps(run_agent(args.prompt or DEFAULT_PROMPT, args.session_id), indent=2))
    finally:
        provider.shutdown()


if __name__ == "__main__":
    main()
