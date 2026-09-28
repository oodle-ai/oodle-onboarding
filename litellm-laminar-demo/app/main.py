"""FastAPI entry point: one POST runs one traced agent session."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

import tracing

SERVICE_NAME = os.environ.get("SERVICE_NAME", "litellm-laminar-demo")

tracing.init_laminar()
tracing.init_oodle(SERVICE_NAME)

import agent  # noqa: E402  (Laminar's @observe must see an initialized SDK)



@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    tracing.flush()
    tracing.shutdown_oodle()


app = FastAPI(title="Laminar + Oodle dual-write demo", lifespan=lifespan)


class SessionRequest(BaseModel):
    message: str = "What is in this repository?"


@app.post("/session")
async def session(request: SessionRequest) -> dict:
    result = await agent.run_session(request.message)
    tracing.flush()
    return result


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8102")))
