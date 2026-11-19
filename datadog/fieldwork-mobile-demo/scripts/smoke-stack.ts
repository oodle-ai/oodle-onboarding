import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import { createTRPCClient, httpLink } from "@trpc/client";
import type { AppRouter } from "../server/router";
import { Command, inspectionChecks, today } from "../src/shared/model";
import { samplePhoto } from "../src/shared/sample-photo";

async function main() {
  const base = process.env.SMOKE_API_URL || "http://127.0.0.1:4310";
  const health = (await (await fetch(`${base}/health`)).json()) as {
    storage: string;
    cache: string;
  };
  assert.equal(health.storage, "postgres");
  assert.equal(health.cache, "redis");
  async function profile(id: string) {
    const response = await fetch(`${base}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: id, code: "demo" }),
    });
    assert.equal(response.status, 200);
    const session = (await response.json()) as { token: string };
    const rpc = createTRPCClient<AppRouter>({
      links: [
        httpLink({
          url: `${base}/api/trpc`,
          headers: { Authorization: `Bearer ${session.token}` },
        }),
      ],
    });
    return {
      rpc,
      token: session.token,
      act: (command: Command, requestId = randomUUID()) =>
        rpc.workflow.execute.mutate({ command, requestId }),
    };
  }
  const office = await profile("admin-morgan");
  const driver = await profile("driver-leo");
  const before = await driver.rpc.sync.snapshot.query();
  assert.ok(
    !before.orders.some((o) => o.status === "in_progress"),
    "Use a demo dataset where Leo has no active job.",
  );
  if (!before.shifts.some((s) => !s.endedAt)) {
    await driver.act({
      type: "inspection.submit",
      vehicleId: "truck-08",
      checks: inspectionChecks,
      defect: "",
    });
    await driver.act({ type: "shift.clock_in", vehicleId: "truck-08" });
  }
  const create: Command = {
    type: "order.create",
    customerId: "c4",
    orderType: "live_load",
    size: "40 yd",
    date: today(),
    notes: "Synthetic stack verification.",
    priority: "normal",
    priceCents: 10000,
  };
  const requestId = randomUUID();
  const results = await Promise.all([
    office.act(create, requestId),
    office.act(create, requestId),
  ]);
  assert.deepEqual(results.map((r) => r.duplicate).sort(), [false, true]);
  const orderId = results[0]!.entityId;
  await office.act({ type: "order.assign", orderId, routeId: "route-south" });
  await driver.act({ type: "order.start", orderId });
  await driver.act({
    type: "order.confirm_container",
    orderId,
    assetId: "BOX-401",
  });
  await driver.act({
    type: "order.photo",
    orderId,
    kind: "site",
    base64: samplePhoto,
  });
  await driver.act({
    type: "order.dump",
    orderId,
    weightTons: 1.25,
    dumpSite: "Harbor recycling center",
  });
  await driver.act({
    type: "order.complete",
    orderId,
    note: "Stack verification complete.",
    signature: "",
  });
  let invoice;
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const snapshot = await office.rpc.sync.snapshot.query();
    invoice = snapshot.invoices.find((i) => i.orderId === orderId);
    if (invoice) break;
    await delay(250);
  }
  assert.ok(invoice, "The separate worker must create the invoice.");
  const paymentId = randomUUID();
  const payment = {
    type: "payment.record",
    invoiceId: invoice.id,
    amountCents: 10000,
    method: "cash_demo",
  } as const;
  await Promise.all([
    office.act(payment, paymentId),
    office.act(payment, paymentId),
  ]);
  const snapshot = await office.rpc.sync.snapshot.query();
  assert.equal(
    snapshot.payments.filter((p) => p.invoiceId === invoice.id).length,
    1,
  );
  assert.equal(
    snapshot.invoices.find((i) => i.id === invoice.id)?.status,
    "paid",
  );
  for (let i = 0; i < 2; i++) {
    const report = await fetch(`${base}/api/report`, {
      headers: { Authorization: `Bearer ${office.token}` },
    });
    assert.equal(report.status, 200);
    assert.ok(
      ((await report.json()) as { revenueCents: number }).revenueCents >= 10000,
    );
  }
  await driver.act({ type: "shift.clock_out" });
  console.log(
    "PostgreSQL retries, separate-worker billing, demo payments, and Redis reports passed.",
  );
}
void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
