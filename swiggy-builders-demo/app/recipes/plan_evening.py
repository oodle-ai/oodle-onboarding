"""Recipe 4: Plan my evening (combined Dineout + Food).

Multi-server agent that fans out across Dineout and Food to book
a dinner reservation and arrange dessert delivery afterward.

Both servers share the same OAuth session (one token, two URLs).
Tool names don't collide: search_restaurants (Food) vs
search_restaurants_dineout (Dineout).

Constraints:
  - If one server returns 401, both are expired - re-auth once
  - Food delivery is immediate (no scheduling in v1)
  - Dineout uses lat/lng; Food uses addressId - don't mix
"""

import os

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp

from core import (
    create_dineout_server,
    create_food_server,
    get_swiggy_token,
    run_with_reauth,
)

SYSTEM_PROMPT = (
    "You are an evening planner that uses both Swiggy Dineout and Swiggy Food "
    "to plan the user's evening. Follow these rules:\n\n"
    "PHASE 1 - DINNER RESERVATION (Dineout tools):\n"
    "1. Call get_saved_locations for the user's lat/lng coordinates.\n"
    "2. Search restaurants with search_restaurants_dineout using the dinner query.\n"
    "3. Only show restaurants marked AVAILABLE.\n"
    "4. Check slots with get_available_slots for the requested date and guest count.\n"
    "5. Confirm the restaurant, time, and guest count with the user.\n"
    "6. Book with book_table and share the confirmation.\n\n"
    "PHASE 2 - DESSERT DELIVERY (Food tools):\n"
    "7. Call get_addresses to get the Food delivery addressId (different from Dineout lat/lng!).\n"
    "8. Search for dessert using search_restaurants with the dessert query.\n"
    "9. Browse the menu with get_restaurant_menu.\n"
    "10. Add items to cart with update_food_cart.\n"
    "11. Check total with get_food_cart (must be <= 1000 INR).\n"
    "12. Confirm with user, then place_food_order with COD.\n\n"
    "IMPORTANT NOTES:\n"
    "- Food orders are delivered IMMEDIATELY. There is no scheduling in v1. "
    "Tell the user that dessert will arrive ~30min after placing, so they should "
    "place the order when they're heading home from dinner.\n"
    "- Dineout uses lat/lng from get_saved_locations. "
    "Food uses addressId from get_addresses. Never mix these.\n"
    "- If any tool returns 401 or error code -32001, both servers have expired. "
    "Inform the user they need to re-authenticate."
)

MODEL = os.environ.get("MODEL", "gpt-4o-mini")


async def run_plan_evening(
    dinner_query: str,
    dessert_query: str,
    guests: int = 4,
) -> str:
    """Execute the combined evening planner agent.

    Args:
        dinner_query: Cuisine/restaurant query for dinner reservation.
        dessert_query: Food query for dessert delivery.
        guests: Number of guests for the dinner reservation.
    """
    token = get_swiggy_token()
    dineout_server = create_dineout_server(token)
    food_server = create_food_server(token)

    async with dineout_server, food_server:
        agent = Agent(
            name="EveningPlannerAgent",
            instructions=SYSTEM_PROMPT,
            mcp_servers=[dineout_server, food_server],
            model=MODEL,
            mcp_config={"include_server_in_tool_names": True},
        )

        prompt = (
            f"Plan my evening for {guests} people. "
            f"For dinner, I'm looking for: {dinner_query}. "
            f"After dinner, I'd like dessert delivered: {dessert_query}."
        )

        async def _run():
            result = await Runner.run(agent, prompt)
            return result.final_output

        return await run_with_reauth(_run)
