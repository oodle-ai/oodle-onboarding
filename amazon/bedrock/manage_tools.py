"""Create independent demo tool resources, seed missing fixtures, or remove them."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from aws_tools import DEFAULT_STACK, ORDERS  # noqa: E402


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["deploy", "status", "destroy"])
    parser.add_argument("--runtime-role", default=os.environ.get("TOOL_RUNTIME_ROLE_NAME", ""))
    args = parser.parse_args()
    stack = os.environ.get("TOOLS_STACK_NAME", DEFAULT_STACK)
    region = os.environ.get("AWS_REGION", "us-west-2")
    base = ["aws", "--region", region, "cloudformation"]
    if args.action == "deploy":
        role = args.runtime_role
        config = ROOT / "app" / ".bedrock_agentcore.yaml"
        if not role and config.exists():
            import yaml  # Installed with the AgentCore deployment toolkit.
            cfg = yaml.safe_load(config.read_text())
            name = os.environ.get("AGENTCORE_AGENT_NAME") or cfg["default_agent"]
            role = cfg["agents"][name]["aws"].get("execution_role") or ""
        role = role.rsplit("/", 1)[-1]
        subprocess.run(base + ["deploy", "--stack-name", stack, "--template-file", str(ROOT / "tools.yaml"),
                       "--capabilities", "CAPABILITY_IAM", "--no-fail-on-empty-changeset",
                       "--parameter-overrides", f"RuntimeRoleName={role}"], check=True)
        client = boto3.client("dynamodb", region_name=region)
        for order_id, payload in ORDERS.items():
            try:
                client.put_item(TableName=stack + "-orders", Item={"order_id": {"S": order_id},
                                "payload": {"S": json.dumps(payload)}}, ConditionExpression="attribute_not_exists(order_id)")
            except ClientError as exc:
                if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
        print(f"Seeded missing fictional orders in {stack}-orders; existing items preserved.")
        if config.exists() and role:
            print(f"Granted {role} GetItem/GetParameter on this stack's resources only.")
    elif args.action == "status":
        subprocess.run(base + ["describe-stacks", "--stack-name", stack,
                              "--query", "Stacks[0].{Status:StackStatus,Outputs:Outputs}"], check=True)
    else:
        if input(f"Delete {stack}, its fictional orders, policy parameter, and tool IAM policy? [y/N] ").lower() != "y":
            return
        subprocess.run(base + ["delete-stack", "--stack-name", stack], check=True)
        subprocess.run(base + ["wait", "stack-delete-complete", "--stack-name", stack], check=True)


if __name__ == "__main__":
    main()
