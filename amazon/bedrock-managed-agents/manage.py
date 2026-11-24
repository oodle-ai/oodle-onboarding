"""Manage only this demo's CloudFormation stack; credentials stay in .env."""

import argparse
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["deploy", "status", "destroy"])
    args = parser.parse_args()
    stack = os.environ.get("STACK_NAME", "oodle-bedrock-managed-agents-demo")
    region = os.environ.get("AWS_REGION", "us-west-2")
    base = ["aws", "--region", region, "cloudformation"]
    if args.action == "deploy":
        command = base + [
            "deploy", "--stack-name", stack, "--template-file", str(ROOT / "template.yaml"),
            "--capabilities", "CAPABILITY_IAM", "--no-fail-on-empty-changeset",
            "--parameter-overrides", f"ModelId={os.environ.get('BEDROCK_MODEL_ID', 'us.amazon.nova-lite-v1:0')}",
        ]
    elif args.action == "status":
        command = base + ["describe-stacks", "--stack-name", stack, "--query", "Stacks[0].{Status:StackStatus,Outputs:Outputs}"]
    else:
        if input(f"Delete stack {stack} in {region}, including its agent and IAM role? [y/N] ").lower() != "y":
            return
        subprocess.run(base + ["delete-stack", "--stack-name", stack], check=True)
        command = base + ["wait", "stack-delete-complete", "--stack-name", stack]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
