#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["elevenlabs==2.72.0"]
# ///
# setup_webhook.py: run once (make webhook)
#
# This is the Python snippet of the ElevenLabs Agents tile in Oodle, step
# for step. The tile fills in the Oodle endpoint, API key and instance;
# here they come from .env, and `make webhook` sets ELEVENLABS_AGENT_ID
# to the demo agent.
import os

from elevenlabs import ElevenLabs

client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

webhook = client.webhooks.create(
    settings={
        "auth_type": "hmac",
        "name": "Oodle Agent Observability",
        "webhook_url": f"https://{os.environ['OODLE_INSTANCE']}-otlp.collector.oodle.ai/v1/otlp/traces/elevenlabs",
        # Sent with every delivery: Oodle authenticates with them.
        "request_headers": {
            "X-API-KEY": os.environ["OODLE_API_KEY"],
            "X-OODLE-INSTANCE": os.environ["OODLE_INSTANCE"],
        },
    }
)

# Retry a failed delivery, so that no call is lost.
client.webhooks.update(
    webhook.webhook_id,
    name="Oodle Agent Observability",
    is_disabled=False,
    retry_enabled=True,
)

# Send every conversation of the agent as an OpenTelemetry trace.
# For all agents, pass the same webhooks to
# client.conversational_ai.settings.update(webhooks=...).
client.conversational_ai.agents.update(
    os.environ["ELEVENLABS_AGENT_ID"],
    platform_settings={
        "workspace_overrides": {
            "webhooks": {
                "post_call_webhook_id": webhook.webhook_id,
                "events": ["transcript"],
                "transcript_format": "opentelemetry",
            }
        }
    },
)