import requests
import time
import random
import os

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend:3000")
INTERVAL = int(os.getenv("REQUEST_INTERVAL", "3"))

ITEMS = ["widget", "gadget", "doohickey", "thingamajig", "whatchamacallit"]

print(f"Load generator targeting {FRONTEND_URL} every {INTERVAL}s")

while True:
    item = random.choice(ITEMS)
    quantity = random.randint(1, 10)
    try:
        resp = requests.post(
            f"{FRONTEND_URL}/order",
            json={"item": item, "quantity": quantity},
            timeout=10,
        )
        print(f"Order {item} x{quantity}: {resp.status_code}")
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(INTERVAL)
