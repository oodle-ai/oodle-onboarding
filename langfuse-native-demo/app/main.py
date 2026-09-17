"""The Langfuse SDK's own exporter, pointed at Oodle.

No OpenTelemetry SDK in the app and no collector: the client reads
LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY from the
environment, and nothing in this file names Oodle. It is the code an
app already on Langfuse has today.
"""

import os

from langfuse import get_client, observe

# The Langfuse OpenAI drop-in traces every call it makes.
from langfuse.openai import openai

MODEL = os.environ.get("MODEL", "gpt-4o-mini")


# Group the LLM calls of one request under a single trace.
@observe()
def chat(message: str) -> str:
    response = openai.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": message}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    print(chat("What is OpenTelemetry in one sentence?"))

    # Short-lived processes must flush before they exit.
    get_client().flush()
