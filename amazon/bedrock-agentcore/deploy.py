"""Deploy the app directory to AgentCore using the AWS starter toolkit."""

import os
from pathlib import Path

from dotenv import load_dotenv


def main():
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    instance = os.environ.get("OODLE_INSTANCE", "").strip()
    api_key = os.environ.get("OODLE_API_KEY", "").strip()
    if not instance or not api_key or instance == "your-instance-id" or api_key == "your-api-key":
        raise SystemExit("Set OODLE_INSTANCE and OODLE_API_KEY in .env before deploying")

    from bedrock_agentcore_starter_toolkit.operations.runtime import (
        configure_bedrock_agentcore,
        launch_bedrock_agentcore,
    )

    # Package only app/. In particular, .env and the deployment script stay local.
    os.chdir(root / "app")
    configuration = configure_bedrock_agentcore(
        entrypoint_path=root / "app" / "main.py",
        # An explicit source path keeps dependency caches under .bedrock_agentcore/,
        # which the packager excludes, rather than embedding dependencies.zip twice.
        source_path=str(root / "app"),
        agent_name=os.environ.get("AGENTCORE_AGENT_NAME", "oodle_order_support_demo"),
        region=os.environ.get("AWS_REGION", "us-west-2"),
        auto_create_execution_role=True,
        requirements_file="requirements.txt",
        deployment_type="direct_code_deploy",
        runtime_type="PYTHON_3_12",
        auto_create_s3=True,
        auto_create_ecr=False,
        enable_observability=False,  # Our provider owns export; avoid a second ADOT provider.
        non_interactive=True,
        memory_mode="NO_MEMORY",
        idle_timeout=60,
        max_lifetime=600,
    )
    result = launch_bedrock_agentcore(configuration.config_path, auto_update_on_conflict=True, env_vars={
        "AWS_REGION": os.environ.get("AWS_REGION", "us-west-2"),
        "BEDROCK_MODEL_ID": os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0"),
        "OODLE_INSTANCE": instance,
        "OODLE_API_KEY": api_key,
        "OODLE_OTLP_ENDPOINT": os.environ.get("OODLE_OTLP_ENDPOINT") or f"https://{instance}-otlp.collector.oodle.ai",
        "CAPTURE_CONTENT": os.environ.get("CAPTURE_CONTENT", "true"),
        "TOOL_DATA_SOURCE": os.environ.get("TOOL_DATA_SOURCE", "aws"),
        "TOOLS_STACK_NAME": os.environ.get("TOOLS_STACK_NAME", "oodle-bedrock-agentcore-tools"),
        "ORDERS_TABLE_NAME": os.environ.get("ORDERS_TABLE_NAME", ""),
        "RETURN_POLICY_PARAMETER": os.environ.get("RETURN_POLICY_PARAMETER", ""),
    })
    print(f"AgentCore runtime: {result.agent_arn}")
    print("Run make invoke to send a request, or make status to check readiness.")


if __name__ == "__main__":
    main()
