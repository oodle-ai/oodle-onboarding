"""Swiggy Builders Club Demo - FastAPI entrypoint.

Wires all 4 recipe agents to HTTP endpoints with OTel tracing to Oodle.
"""

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from core import setup_opentelemetry
from recipes.book_table import run_book_table
from recipes.order_food import run_order_food
from recipes.order_grocery import run_order_grocery
from recipes.plan_evening import run_plan_evening

setup_opentelemetry()

app = FastAPI(
    title="Swiggy Builders Club Demo",
    description=(
        "AI agents powered by Swiggy MCP — food ordering, grocery delivery, "
        "table reservations, and combined evening planning."
    ),
)


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request, exc):
    return JSONResponse(
        status_code=503,
        content={"error": str(exc)},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "swiggy-builders-demo"}


@app.post("/order-food")
async def order_food(query: str = "biryani"):
    """Order food via Swiggy Food MCP (Recipe 1).

    The agent handles the full flow: address -> search -> menu -> cart
    -> coupon -> place order -> track.
    """
    result = await run_order_food(query)
    return {"recipe": "order-food", "query": query, "result": result}


@app.post("/order-grocery")
async def order_grocery(query: str = "bananas"):
    """Order groceries via Swiggy Instamart MCP (Recipe 2).

    The agent handles: address -> search/reorder -> cart -> checkout -> track.
    """
    result = await run_order_grocery(query)
    return {"recipe": "order-grocery", "query": query, "result": result}


@app.post("/book-table")
async def book_table(
    query: str = "italian",
    guests: int = 2,
    date: str | None = None,
):
    """Book a restaurant table via Swiggy Dineout MCP (Recipe 3).

    The agent handles: location -> search -> details -> slots -> book -> confirm.
    """
    result = await run_book_table(query, guests=guests, date=date)
    return {
        "recipe": "book-table",
        "query": query,
        "guests": guests,
        "date": date,
        "result": result,
    }


@app.post("/plan-evening")
async def plan_evening(
    dinner_query: str = "italian",
    dessert_query: str = "gelato",
    guests: int = 4,
):
    """Plan an evening with dinner + dessert delivery (Recipe 4).

    Combined agent fans out across Dineout (reservation) and Food (delivery).
    """
    result = await run_plan_evening(
        dinner_query, dessert_query, guests=guests
    )
    return {
        "recipe": "plan-evening",
        "dinner_query": dinner_query,
        "dessert_query": dessert_query,
        "guests": guests,
        "result": result,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8093"))
    uvicorn.run(app, host="0.0.0.0", port=port)
