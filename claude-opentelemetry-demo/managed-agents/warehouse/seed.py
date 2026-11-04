"""Build the warehouse's SQLite file: a year of orders, fixed seed.

Runs at image build time, before any instrumentation is loaded, so seeding
adds no spans.

Usage: python seed.py <warehouse path> <apac path>
"""

import random
import sqlite3
import sys
from datetime import date, timedelta

PRODUCTS = [
    (1, "Trail Runner", "footwear", 120.0),
    (2, "City Sneaker", "footwear", 85.0),
    (3, "Rain Shell", "outerwear", 160.0),
    (4, "Down Parka", "outerwear", 290.0),
    (5, "Merino Tee", "apparel", 45.0),
    (6, "Fleece Hoodie", "apparel", 70.0),
    (7, "Daypack 22L", "gear", 95.0),
    (8, "Headlamp", "gear", 35.0),
]

# Monthly growth per region, so the data has a story to find.
REGIONS = {"North America": 0.01, "EMEA": 0.02, "APAC": 0.06, "LATAM": -0.01}
CHANNELS = ["web", "retail", "marketplace"]
EVENT_TYPES = ["placed", "paid", "packed", "shipped", "delivered"]
# Enough rows that a scan per order outlasts the warehouse's timeout with
# room to spare: a run that finishes in time would answer with APAC.
EVENTS_PER_ORDER = 120


def main(path: str, apac_path: str) -> None:
    rng = random.Random(7)
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            category   TEXT NOT NULL,
            list_price REAL NOT NULL
        );
        CREATE TABLE orders (
            order_id   INTEGER PRIMARY KEY,
            order_date TEXT NOT NULL,     -- YYYY-MM-DD
            region     TEXT NOT NULL,
            channel    TEXT NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(product_id),
            quantity   INTEGER NOT NULL,
            unit_price REAL NOT NULL      -- after discount
        );
        CREATE INDEX orders_date ON orders(order_date);
        """
    )
    db.executemany("INSERT INTO products VALUES (?, ?, ?, ?)", PRODUCTS)

    order_id = 0
    day = date(2025, 1, 1)
    while day.year == 2025:
        for region, growth in REGIONS.items():
            # Footwear sells more in summer, outerwear in winter.
            for _ in range(round(rng.randint(3, 6) * (1 + growth) ** (day.month - 1))):
                product_id, _, category, list_price = rng.choice(PRODUCTS)
                if category == "outerwear" and day.month in (5, 6, 7, 8) and rng.random() < 0.6:
                    continue
                order_id += 1
                discount = rng.choice([0, 0, 0, 0.1, 0.2])
                db.execute(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        order_id,
                        day.isoformat(),
                        region,
                        rng.choice(CHANNELS),
                        product_id,
                        rng.choice([1, 1, 1, 2, 3]),
                        round(list_price * (1 - discount), 2),
                    ),
                )
        day += timedelta(days=1)
    db.commit()
    move_apac(db, apac_path)
    db.close()
    print(f"seeded {order_id} orders into {path} and {apac_path}")


def move_apac(db: sqlite3.Connection, apac_path: str) -> None:
    """Move APAC's orders to their own file, with the order events its service filters on."""
    db.execute("ATTACH DATABASE ? AS apac", (apac_path,))
    db.executescript(
        """
        CREATE TABLE apac.orders AS SELECT * FROM main.orders WHERE region = 'APAC';
        DELETE FROM main.orders WHERE region = 'APAC';
        CREATE TABLE apac.order_events (
            event_id INTEGER PRIMARY KEY,
            order_id INTEGER NOT NULL,
            type     TEXT NOT NULL
        );
        """
    )
    # Its own generator, so the orders stay the same. No order is cancelled:
    # the filter costs time but never changes the revenue.
    rng = random.Random(11)
    order_ids = [row[0] for row in db.execute("SELECT order_id FROM apac.orders")]
    db.executemany(
        "INSERT INTO apac.order_events (order_id, type) VALUES (?, ?)",
        ((order_id, rng.choice(EVENT_TYPES)) for order_id in order_ids for _ in range(EVENTS_PER_ORDER)),
    )
    db.execute("CREATE INDEX apac.order_events_order ON order_events(order_id)")
    db.commit()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
