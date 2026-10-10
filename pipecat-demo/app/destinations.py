"""Where the spans go: the Langfuse project and the Oodle instance.

Both tracing paths in this demo write to the same two destinations, and
each destination is addressed twice — once as a plain OpenTelemetry OTLP
endpoint and once as the Langfuse ingest API. The four URLs and their
credentials are built here so the two paths cannot drift apart.

| destination | OTLP/HTTP                                        | Langfuse ingest                                               |
| ----------- | ------------------------------------------------ | ------------------------------------------------------------- |
| Langfuse    | `<LANGFUSE_BASE_URL>/api/public/otel/v1/traces`  | `<LANGFUSE_BASE_URL>` (the SDK appends the path)              |
| Oodle       | `https://<instance>-otlp.collector.oodle.ai`     | `https://<domain>/v1/api/instance/<instance>/langfuse`        |

Oodle serves both: its OTLP collector takes OpenTelemetry directly, and
its Langfuse-compatible endpoint takes whatever the Langfuse SDK sends.
"""

import base64
import os

# The Langfuse OTLP path, as the Langfuse SDK itself builds it.
LANGFUSE_OTLP_TRACES_PATH = "api/public/otel/v1/traces"

# Oodle takes Langfuse ingest credentials as the public key `default` with
# the Oodle API key as the secret.
OODLE_LANGFUSE_PUBLIC_KEY = "default"


def required(name: str) -> str:
    """Read a variable that the demo cannot run without.

    An unset destination is an error rather than a silent no-op: a
    dual-write demo that quietly became a single write would look like it
    worked.
    """
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required to write to both destinations")

    return value


def _basic_auth(public_key: str, secret_key: str) -> str:
    return "Basic " + base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()


def langfuse_base_url() -> str:
    """The Langfuse project's base URL, without a trailing slash."""
    return os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")


def langfuse_otlp_endpoint() -> tuple[str, dict[str, str]]:
    """Langfuse as a plain OTLP/HTTP endpoint, for the OpenTelemetry path."""
    public_key = required("LANGFUSE_PUBLIC_KEY")
    secret_key = required("LANGFUSE_SECRET_KEY")

    return (
        f"{langfuse_base_url()}/{LANGFUSE_OTLP_TRACES_PATH}",
        {"Authorization": _basic_auth(public_key, secret_key)},
    )


def oodle_otlp_endpoint() -> tuple[str, dict[str, str]]:
    """Oodle as a plain OTLP/HTTP endpoint, for the OpenTelemetry path."""
    instance = required("OODLE_INSTANCE")
    endpoint = os.environ.get(
        "OODLE_TRACES_ENDPOINT", f"https://{instance}-otlp.collector.oodle.ai/v1/traces"
    )

    return (
        endpoint,
        {"X-API-KEY": required("OODLE_API_KEY"), "X-OODLE-INSTANCE": instance},
    )


def oodle_langfuse_ingest() -> tuple[str, dict[str, str]]:
    """Oodle's Langfuse-compatible ingest API, for the Langfuse SDK path.

    Returns the base URL the Langfuse SDK takes — it appends the OTLP path
    itself — and the headers that re-address a Langfuse span processor at
    Oodle. The processor builds an ``Authorization`` header from its own
    ``public_key``/``secret_key`` and merges ``additional_headers`` last,
    so these two replace what it built.
    """
    instance = required("OODLE_INSTANCE")
    api_domain = os.environ.get("OODLE_API_DOMAIN", "us1.oodle.ai")
    base_url = os.environ.get(
        "OODLE_LANGFUSE_BASE_URL",
        f"https://{api_domain}/v1/api/instance/{instance}/langfuse",
    ).rstrip("/")

    return (
        base_url,
        {
            "Authorization": _basic_auth(
                OODLE_LANGFUSE_PUBLIC_KEY, required("OODLE_API_KEY")
            ),
            "x-langfuse-public-key": OODLE_LANGFUSE_PUBLIC_KEY,
        },
    )
