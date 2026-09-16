"""Thin HTTP client for the parts of Oodle this demo uses: the prompt registry
and the findings it reports. Both authenticate with the same Oodle API key."""

import os

import httpx

APP_URL = os.environ.get("OODLE_APP_URL", "https://app.oodle.ai").rstrip("/")
INSTANCE = os.environ["OODLE_INSTANCE"]
API_KEY = os.environ["OODLE_API_KEY"]

_INSTANCE_URL = f"{APP_URL}/v1/api/instance/{INSTANCE}"
_PROMPTS = f"{_INSTANCE_URL}/langfuse/api/public/v2"
_AUTH = ("default", API_KEY)


def get_prompt(name: str, label: str = "production") -> dict:
    """Resolve a label to a concrete version. Never call this from workflow code."""
    r = httpx.get(f"{_PROMPTS}/prompts/{name}", params={"label": label}, auth=_AUTH, timeout=30)
    r.raise_for_status()
    return r.json()


def create_prompt(name: str, prompt: str, tools: list, labels: list, commit_message: str) -> dict:
    """Add a version. Tool declarations ride along in the prompt's config."""
    r = httpx.post(
        f"{_PROMPTS}/prompts",
        auth=_AUTH,
        timeout=30,
        json={
            "name": name,
            "type": "text",
            "prompt": prompt,
            "config": {"tools": tools},
            "labels": labels,
            "commitMessage": commit_message,
        },
    )
    r.raise_for_status()
    return r.json()


def move_label(name: str, version: int, label: str = "production") -> dict:
    """Roll out by moving a label. This is the deploy."""
    r = httpx.patch(
        f"{_PROMPTS}/prompts/{name}/versions/{version}",
        auth=_AUTH,
        timeout=30,
        json={"newLabels": [label]},
    )
    r.raise_for_status()
    return r.json()


def recommendations() -> list:
    """What Oodle reported from the live traces, on its own."""
    r = httpx.get(
        f"{_INSTANCE_URL}/genai/recommendations",
        headers={"X-API-KEY": API_KEY},
        timeout=60,
    )
    r.raise_for_status()
    return r.json().get("recommendations") or []
