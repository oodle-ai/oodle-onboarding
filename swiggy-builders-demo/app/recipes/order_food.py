"""Recipe 1: Order food end-to-end.

Full food-ordering journey via Swiggy Food MCP server.
Flow: get_addresses -> search_restaurants -> get_restaurant_menu
  -> update_food_cart -> fetch_food_coupons -> apply_food_coupon
  -> get_food_cart -> place_food_order -> track_food_order

Constraints:
  - COD payment only (v1)
  - Cart capped at 1000 INR
  - Cart is single-restaurant; changing restaurant flushes it
  - place_food_order is NOT idempotent
"""

import os

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp

from core import create_food_server, get_swiggy_token, run_with_reauth

SYSTEM_PROMPT = (
    "You are a food ordering assistant on Swiggy. Follow these rules strictly:\n\n"
    "1. ALWAYS call get_addresses first to resolve the delivery location. "
    "Use the 'Home' address if available, otherwise the first saved address.\n"
    "2. Search restaurants using the user's query and the resolved addressId.\n"
    "3. Only recommend restaurants marked OPEN in availabilityStatus. "
    "Surface distance for far restaurants so the user isn't surprised.\n"
    "4. Browse the menu and help the user pick items. Handle variants and add-ons.\n"
    "5. Build the cart with update_food_cart. Remember: cart is tied to ONE restaurant.\n"
    "6. Check for coupons with fetch_food_coupons. Only apply COD-compatible coupons "
    "(filter out those requiring online payment).\n"
    "7. Before placing: call get_food_cart and verify total <= 1000 INR. "
    "If over, ask user to remove items.\n"
    "8. Confirm the full order summary with the user before calling place_food_order.\n"
    "9. Payment is ALWAYS COD (Cash on Delivery).\n"
    "10. After placing, track with track_food_order. Poll no faster than every 10s.\n\n"
    "If place_food_order fails with 5xx, call get_food_orders to check if it "
    "actually went through before retrying."
)

MODEL = os.environ.get("MODEL", "gpt-4o-mini")


async def run_order_food(query: str) -> str:
    """Execute the food ordering agent with the given search query."""
    token = get_swiggy_token()
    food_server = create_food_server(token)

    async with food_server:
        agent = Agent(
            name="FoodOrderAgent",
            instructions=SYSTEM_PROMPT,
            mcp_servers=[food_server],
            model=MODEL,
        )

        async def _run():
            result = await Runner.run(
                agent,
                f"I want to order: {query}",
            )
            return result.final_output

        return await run_with_reauth(_run)
