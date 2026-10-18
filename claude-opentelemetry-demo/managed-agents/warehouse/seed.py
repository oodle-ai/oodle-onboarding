"""Build the warehouse's SQLite file: a year of orders, fixed seed.

Runs at image build time, before any instrumentation is loaded, so seeding
adds no spans.

Usage: python seed.py <path>
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


def main(path: str) -> None:
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
    db.close()
    print(f"seeded {order_id} orders into {path}")


if __name__ == "__main__":
    main(sys.argv[1])
