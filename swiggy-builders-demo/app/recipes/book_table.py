"""Recipe 3: Book a table (Dineout).

Table reservation via Swiggy Dineout MCP server.
Flow: get_saved_locations -> search_restaurants_dineout
  -> get_restaurant_details -> get_available_slots
  -> book_table -> get_booking_status

Constraints:
  - Uses lat/lng (not addressId) for location
  - Filter to restaurants with availability "AVAILABLE"
  - Slot times are in IST
  - book_table is NOT idempotent
"""

import os

from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp

from core import create_dineout_server, get_swiggy_token, run_with_reauth

SYSTEM_PROMPT = (
    "You are a restaurant reservation assistant on Swiggy Dineout. Follow these rules:\n\n"
    "1. ALWAYS call get_saved_locations first to get the user's lat/lng coordinates.\n"
    "2. Search restaurants using search_restaurants_dineout with lat, lng, and query.\n"
    "3. Only present restaurants where availability is 'AVAILABLE'. "
    "Include cuisine, price range, and any Dineout offers.\n"
    "4. Use get_restaurant_details to show ratings, amenities, and deals.\n"
    "5. Check available slots with get_available_slots. Provide date and guest count.\n"
    "   Slots span 7 days forward, broken into breakfast/lunch/dinner bands.\n"
    "6. Present slot times in IST (Indian Standard Time).\n"
    "7. Confirm guest count, date, time, and restaurant with the user before booking.\n"
    "8. Book with book_table using restaurantId, slotId, and guestCount.\n"
    "9. After booking, call get_booking_status and share the confirmation number "
    "and restaurant address with the user.\n\n"
    "Error handling:\n"
    "- SLOT_UNAVAILABLE: refetch availability and offer alternatives\n"
    "- RESTAURANT_NOT_BOOKABLE: suggest walk-in or a food delivery instead\n"
    "- BOOKING_WINDOW_CLOSED: present the next available day\n\n"
    "If book_table fails with 5xx, call get_booking_status to check before retrying."
)

MODEL = os.environ.get("MODEL", "gpt-4o-mini")


async def run_book_table(
    query: str,
    guests: int = 2,
    date: str | None = None,
) -> str:
    """Execute the table booking agent.

    Args:
        query: Cuisine or restaurant search query.
        guests: Number of guests.
        date: Target date (YYYY-MM-DD). If None, agent picks today/tomorrow.
    """
    token = get_swiggy_token()
    dineout_server = create_dineout_server(token)

    async with dineout_server:
        agent = Agent(
            name="BookTableAgent",
            instructions=SYSTEM_PROMPT,
            mcp_servers=[dineout_server],
            model=MODEL,
        )

        prompt = f"I want to book a table for {guests} guests"
        if date:
            prompt += f" on {date}"
        prompt += f". Looking for: {query}"

        async def _run():
            result = await Runner.run(agent, prompt)
            return result.final_output

        return await run_with_reauth(_run)
