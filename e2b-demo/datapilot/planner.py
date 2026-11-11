"""The code that DataPilot runs in the sandbox for each user question.

In the product an LLM writes this code. The demo uses fixed code per
question and planner version so that each run behaves the same way. The
code is what a model typically writes for these questions.

Planner v2 is the release that causes the incident. Its prompt asks the
model to keep row-level detail so that the answer can cite example rows.
For the channel question the model then joins the raw orders to the raw
events on customer_id. That is a many-to-many join: each order row is
repeated once for each event of the same customer. On a small tenant the
result is a few million rows. On the largest tenant it is many times the
sandbox memory.
"""

LOAD = """
import pandas as pd
import datapilot_runtime as dp
orders = pd.read_parquet("/home/user/uploads/orders.parquet")
events = pd.read_parquet("/home/user/uploads/events.parquet")
dp.log.info("loaded uploads: orders=%d events=%d rss=%d MiB", len(orders), len(events), dp.rss_mib())
(len(orders), len(events))
"""

QUESTIONS = {
    "revenue_by_month": """
dp.log.info("step: revenue by month")
out = orders.groupby(orders.ordered_at.dt.to_period("M")).amount.sum().round(2)
out.tail(3).to_dict()
""",
    "top_customers": """
dp.log.info("step: top customers by spend")
out = orders.groupby("customer_id").amount.sum().nlargest(10)
out.to_dict()
""",
    "aov_by_channel": {
        "v1": """
dp.log.info("step: aggregate events per customer")
first_touch = events.sort_values("seen_at").groupby("customer_id").channel.first()
dp.log.info("step: join orders with first-touch channel")
df = orders.merge(first_touch, on="customer_id", how="left")
out = df.groupby("channel", observed=True).amount.mean().round(2)
dp.log.info("done: aov by channel rss=%d MiB", dp.rss_mib())
out.to_dict()
""",
        "v2": """
dp.log.info("step: join orders with events on customer_id (keep row detail)")
df = orders.merge(events, on="customer_id", how="inner")
dp.log.info("joined rows=%d rss=%d MiB", len(df), dp.rss_mib())
out = df.groupby("channel", observed=True).amount.mean().round(2)
examples = df.nlargest(5, "amount")[["order_id", "channel", "amount"]]
out.to_dict()
""",
    },
}


def code_for(question: str, planner_version: str) -> str:
    code = QUESTIONS[question]
    if isinstance(code, dict):
        code = code[planner_version]
    return code
