"""Write a tenant's uploaded files: orders.parquet and events.parquet.

In the real product the user uploads these files. The demo makes them
inside the sandbox, so no large upload is necessary. The sizes per tenant
are fixed, so each run has the same memory profile.
"""

import argparse
import os
import zlib

import numpy as np
import pandas as pd

# customers, orders per customer, events per customer
TENANTS = {
    "acme-retail": (5_000, 8, 10),
    "initech": (15_000, 10, 15),
    "globex": (40_000, 15, 25),
}
CHANNELS = np.array(["search", "email", "social", "direct", "partner"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True, choices=TENANTS)
    p.add_argument("--out", default="/home/user/uploads")
    a = p.parse_args()

    customers, n_orders, n_events = TENANTS[a.tenant]
    rng = np.random.default_rng(zlib.crc32(a.tenant.encode()))
    os.makedirs(a.out, exist_ok=True)

    n = customers * n_orders
    pd.DataFrame(
        {
            "order_id": np.arange(n, dtype=np.int64),
            "customer_id": np.repeat(np.arange(customers, dtype=np.int64), n_orders),
            "amount": rng.gamma(2.0, 40.0, n).round(2),
            "ordered_at": pd.Timestamp("2026-01-01")
            + pd.to_timedelta(rng.integers(0, 300 * 86400, n), unit="s"),
        }
    ).to_parquet(f"{a.out}/orders.parquet")

    n = customers * n_events
    pd.DataFrame(
        {
            "event_id": np.arange(n, dtype=np.int64),
            "customer_id": np.repeat(np.arange(customers, dtype=np.int64), n_events),
            "channel": pd.Categorical(CHANNELS[rng.integers(0, len(CHANNELS), n)]),
            "session_secs": rng.integers(5, 1800, n),
            "seen_at": pd.Timestamp("2026-01-01")
            + pd.to_timedelta(rng.integers(0, 300 * 86400, n), unit="s"),
        }
    ).to_parquet(f"{a.out}/events.parquet")
    print(f"{a.tenant}: {customers} customers, {customers * n_orders} orders, {customers * n_events} events")


if __name__ == "__main__":
    main()
