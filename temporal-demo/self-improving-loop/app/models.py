"""Which Gemini models can this key actually call right now?

Free-tier quota is per model and has two independent caps, a per-minute one and a
per-day one, so "the demo stopped working" usually means one model is spent while
several others are fine. This spends one trivial call per model to find out.

    python models.py
"""

import os

from google import genai
from google.genai import errors

SKIP = ("image", "tts", "transcribe", "robotics", "lyria", "deep-research",
        "computer-use", "omni", "antigravity", "nano-banana", "embedding")


def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    names = [
        m.name.split("/")[-1]
        for m in client.models.list()
        if "generateContent" in (m.supported_actions or [])
        and not any(s in m.name for s in SKIP)
    ]

    available = []
    for name in sorted(names):
        try:
            client.models.generate_content(model=name, contents="ok")
            available.append(name)
            print(f"  {name:<34} available")
        except errors.APIError as exc:
            quotas = [
                v.get("quotaId", "")
                for d in ((exc.details or {}).get("error") or {}).get("details", [])
                for v in d.get("violations", [])
            ]
            if any("PerDay" in q for q in quotas):
                reason = "daily quota spent"
            elif quotas:
                reason = "per-minute limit, retry shortly"
            else:
                reason = "unavailable / overloaded"
            print(f"  {name:<34} {exc.code} {reason}")

    print()
    if available:
        print(f"Set GEMINI_MODEL in .env to one of: {', '.join(available)}")
        print("Prefer a *-flash-lite: the lite tiers get the largest free-tier caps.")
    else:
        print("Nothing available. Caps reset at midnight Pacific.")


if __name__ == "__main__":
    main()
