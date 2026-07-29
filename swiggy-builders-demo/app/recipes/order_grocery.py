"""Recipe 2: Order groceries end-to-end (Instamart).

Quick-commerce grocery ordering via Swiggy Instamart MCP server.
Flow: get_addresses -> search_products / your_go_to_items
  -> update_cart -> get_cart -> checkout -> track_order

Constraints:
  - Minimum order 99 INR
  - Add variants by spinId, not parent products
  - COD only
  - Address change mid-cart requires clear_cart first
  - checkout is NOT idempotent
"""

import os

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp

from core import create_instamart_server, get_swiggy_token, run_with_reauth

SYSTEM_PROMPT = (
    "You are a grocery ordering assistant on Swiggy Instamart. Follow these rules:\n\n"
    "1. ALWAYS call get_addresses first to resolve the delivery location. "
    "Use the 'Home' address if available, otherwise the first saved address.\n"
    "2. For quick reorders, offer your_go_to_items (frequently ordered SKUs).\n"
    "3. For new searches, use search_products with the user's query and addressId.\n"
    "4. Each product has one or more variants with a spinId. "
    "You add VARIANTS (by spinId) to the cart, not the parent product.\n"
    "5. Build the cart with update_cart. Items are specified by spinId + quantity.\n"
    "6. Call get_cart before checkout to review. Check for errors:\n"
    "   - ADDRESS_NOT_SERVICEABLE: Instamart doesn't deliver here\n"
    "   - MIN_ORDER_NOT_MET: cart must be >= 99 INR\n"
    "7. Confirm the cart contents and total with the user before checkout.\n"
    "8. Payment is ALWAYS COD (Cash on Delivery).\n"
    "9. After checkout, track with track_order. ETA is typically 10-20 min.\n"
    "   Poll no faster than every 10 seconds.\n\n"
    "If checkout fails with 5xx, call get_orders to check if it went through "
    "before retrying. Never swap addresses mid-cart without calling clear_cart first."
)

MODEL = os.environ.get("MODEL", "gpt-4o-mini")


async def run_order_grocery(query: str) -> str:
    """Execute the grocery ordering agent with the given search query."""
    token = get_swiggy_token()
    im_server = create_instamart_server(token)

    async with im_server:
        agent = Agent(
            name="GroceryOrderAgent",
            instructions=SYSTEM_PROMPT,
            mcp_servers=[im_server],
            model=MODEL,
        )

        async def _run():
            result = await Runner.run(
                agent,
                f"I need to order: {query}",
            )
            return result.final_output

        return await run_with_reauth(_run)
