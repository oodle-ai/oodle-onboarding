import os
import random
import time

import requests

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://frontend-api:8080")
REQUEST_INTERVAL = float(os.environ.get("REQUEST_INTERVAL", "3"))

ITEMS = ["widget", "gadget", "sprocket", "gizmo", "doohickey"]


def wait_for_frontend():
    """Poll the frontend-api health endpoint until it responds (up to 60 seconds)."""
    health_url = f"{FRONTEND_URL}/health"
    max_attempts = 30  # 30 attempts * 2 seconds = 60 seconds
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(health_url, timeout=5)
            if resp.status_code == 200:
                print(f"Frontend is healthy (attempt {attempt})")
                return
            print(f"Health check returned {resp.status_code}, retrying... (attempt {attempt}/{max_attempts})")
        except requests.exceptions.ConnectionError:
            print(f"Frontend not ready, retrying... (attempt {attempt}/{max_attempts})")
        except requests.exceptions.RequestException as exc:
            print(f"Health check error: {exc}, retrying... (attempt {attempt}/{max_attempts})")
        time.sleep(2)
    print("WARNING: Frontend did not become healthy within 60 seconds, proceeding anyway")


def send_order():
    """Send a POST /order request with a random item and quantity."""
    item = random.choice(ITEMS)
    quantity = random.randint(1, 20)
    payload = {"item": item, "quantity": quantity}
    url = f"{FRONTEND_URL}/order"
    try:
        resp = requests.post(url, json=payload, timeout=10)
        print(f"Sending order for {quantity}x {item}... OK {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"Sending order for {quantity}x {item}... Error: connection refused")
    except requests.exceptions.RequestException as exc:
        print(f"Sending order for {quantity}x {item}... Error: {exc}")


def send_trace_demo():
    """Send a GET /trace-demo request."""
    url = f"{FRONTEND_URL}/trace-demo"
    try:
        resp = requests.get(url, timeout=10)
        print(f"Sending GET /trace-demo... OK {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"Sending GET /trace-demo... Error: connection refused")
    except requests.exceptions.RequestException as exc:
        print(f"Sending GET /trace-demo... Error: {exc}")


def main():
    print(f"Load generator starting (frontend={FRONTEND_URL}, interval={REQUEST_INTERVAL}s)")
    wait_for_frontend()
    print("Starting load generation loop")

    request_count = 0
    while True:
        request_count += 1
        # Send a trace-demo request roughly every 5th iteration for variety
        if request_count % 5 == 0:
            send_trace_demo()
        else:
            send_order()
        time.sleep(REQUEST_INTERVAL)


if __name__ == "__main__":
    main()
