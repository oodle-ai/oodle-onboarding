# Swiggy Builders Club Demo

AI agents powered by [Swiggy MCP](https://mcp.swiggy.com/builders/) — food ordering, grocery delivery, table reservations, and combined evening planning. Built with the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) (Python) and traced to [Oodle](https://oodle.ai) via OpenTelemetry.

## Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────────────┐
│   Client     │────▶│  FastAPI App     │────▶│  Swiggy MCP Servers      │
│  (curl/UI)   │     │  (4 agents)     │     │  /food  /im  /dineout    │
└──────────────┘     └────────┬────────┘     └──────────────────────────┘
                              │ OTel spans
                              ▼
                     ┌─────────────────┐     ┌──────────────────────────┐
                     │  OTel Collector  │────▶│  Oodle (traces)          │
                     └─────────────────┘     └──────────────────────────┘
```

No approval needed to start — prototype on localhost against real tool schemas for free.

## Recipes

| # | Recipe | Endpoint | Swiggy Server | Description |
|---|--------|----------|---------------|-------------|
| 1 | Order Food | `POST /order-food` | `/food` | Full food ordering: address → search → menu → cart → coupon → place → track |
| 2 | Order Grocery | `POST /order-grocery` | `/im` | Instamart quick-commerce: address → search → cart → checkout → track |
| 3 | Book a Table | `POST /book-table` | `/dineout` | Dineout reservation: location → search → slots → book → confirm |
| 4 | Plan Evening | `POST /plan-evening` | `/dineout` + `/food` | Combined: book dinner table + arrange dessert delivery |

## Prerequisites

- Python 3.12+
- Docker & Docker Compose
- A Swiggy account (phone number for OTP login)
- An OpenAI API key (for GPT-4o-mini agent LLM)
- Oodle credentials (for trace export)

## Quick Start

```bash
# 1. Sign up on Oodle at https://ap1.oodle.ai/signup

# 2. Clone and enter the demo
cd swiggy-builders-demo

# 3. Set up environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY, OODLE_INSTANCE, OODLE_API_KEY

# 4. Authenticate with Swiggy (opens browser for phone+OTP)
make auth

# 5. Start services
make up

# 6. Try it out
make test-food       # Order biryani
make test-grocery    # Order milk
make test-dineout    # Book an Italian restaurant for 4
make test-combined   # Plan evening: dinner + dessert
```

## Authentication

Swiggy MCP uses OAuth 2.1 + PKCE. The `make auth` command:

1. Discovers Swiggy's OAuth endpoints via `.well-known` URLs
2. Registers a client dynamically (no pre-applied credentials needed)
3. Opens your browser for Swiggy login (phone + OTP)
4. Catches the callback on `http://localhost:8765/callback`
5. Exchanges the code for an access token (5-day TTL)
6. Writes `SWIGGY_ACCESS_TOKEN` to your `.env`

Tokens last 5 days. When expired, re-run `make auth`.

## API Reference

### POST /order-food

Order food delivery via Swiggy Food.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | `biryani` | What to search for |

### POST /order-grocery

Order groceries via Swiggy Instamart.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | `bananas` | What to search for |

### POST /book-table

Book a restaurant table via Swiggy Dineout.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | `italian` | Cuisine or restaurant query |
| `guests` | int | `2` | Number of guests |
| `date` | string | (today) | Target date (YYYY-MM-DD) |

### POST /plan-evening

Plan an evening with dinner reservation + dessert delivery.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dinner_query` | string | `italian` | Dinner cuisine query |
| `dessert_query` | string | `gelato` | Dessert delivery query |
| `guests` | int | `4` | Number of dinner guests |

### GET /health

Health check endpoint.

## Constraints (Swiggy v1)

- **Payment**: COD (Cash on Delivery) only
- **Food cart cap**: ₹1000 maximum
- **Grocery minimum**: ₹99 minimum order
- **Scheduling**: Food orders are immediate delivery only (no future scheduling)
- **Idempotency**: `place_food_order`, `checkout`, and `book_table` are NOT idempotent — agents verify state before retrying on failure
- **Token expiry**: 5-day access tokens; re-run `make auth` on 401

## Observability

All agent interactions (LLM calls, MCP tool invocations, handoffs) are traced via OpenTelemetry using the `opentelemetry-instrumentation-openai-agents-v2` package and exported to Oodle through the OTel Collector.

## Project Structure

```
swiggy-builders-demo/
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── core.py              # MCP server factory + OTel setup
│   ├── auth.py              # OAuth 2.1 PKCE helper
│   └── recipes/
│       ├── order_food.py    # Recipe 1: Food ordering
│       ├── order_grocery.py # Recipe 2: Grocery (Instamart)
│       ├── book_table.py    # Recipe 3: Table reservation (Dineout)
│       └── plan_evening.py  # Recipe 4: Combined evening planner
├── docker-compose.yml
├── otel-collector-config.yaml
├── .env.example
├── Makefile
└── README.md
```

## References

- [Swiggy Builders Club Docs](https://mcp.swiggy.com/builders/docs/start/developer/)
- [Build an Agent](https://mcp.swiggy.com/builders/docs/start/developer/build-an-agent/)
- [Order Food Recipe](https://mcp.swiggy.com/builders/docs/build/recipes/order-food/)
- [Order Groceries Recipe](https://mcp.swiggy.com/builders/docs/build/recipes/order-groceries/)
- [Book a Table Recipe](https://mcp.swiggy.com/builders/docs/build/recipes/book-a-table/)
- [Combined Recipe](https://mcp.swiggy.com/builders/docs/build/recipes/combined/)
- [Food Server Reference](https://mcp.swiggy.com/builders/docs/reference/food/)
