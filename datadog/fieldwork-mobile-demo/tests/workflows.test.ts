import { test, TestContext } from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createTRPCClient, httpLink, TRPCClientError } from "@trpc/client";
import { createApp } from "../server/app";
import { FileStore } from "../server/store";
import { AppRouter } from "../server/router";
import { runJobs } from "../server/jobs";
import { Command, inspectionChecks, today } from "../src/shared/model";
import { samplePhoto } from "../src/shared/sample-photo";

async function setup(t: TestContext) {
  const directory = await mkdtemp(join(tmpdir(), "fieldwork-test-"));
  const path = join(directory, "state.json");
  const store = new FileStore(path);
  const { app, close } = createApp(store);
  const server = app.listen(0, "127.0.0.1");
  await new Promise<void>((resolve, reject) => {
    server.once("listening", resolve);
    server.once("error", reject);
  });
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const url = `http://127.0.0.1:${address.port}`;
  t.after(async () => {
    await new Promise<void>((resolve, reject) =>
      server.close((e) => (e ? reject(e) : resolve())),
    );
    await close();
    await rm(directory, { recursive: true });
  });
  const post = (path: string, body: object) =>
    fetch(`${url}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  const connect = (token = "") =>
    createTRPCClient<AppRouter>({
      links: [
        httpLink({
          url: `${url}/api/trpc`,
          headers: { Authorization: `Bearer ${token}` },
        }),
      ],
    });
  async function login(profile: string) {
    const response = await post("/api/auth/login", { profile, code: "demo" });
    assert.equal(response.status, 200);
    const { token } = (await response.json()) as { token: string };
    const rpc = connect(token);
    return {
      rpc,
      token,
      act: (command: Command, requestId = randomUUID()) =>
        rpc.workflow.execute.mutate({ command, requestId }),
    };
  }
  return { store, path, url, post, connect, login };
}
async function rejectsCode(action: Promise<unknown>, code: string) {
  await assert.rejects(
    action,
    (e) => e instanceof TRPCClientError && e.data?.code === code,
  );
}
const inspection = (vehicleId = "truck-12"): Command => ({
  type: "inspection.submit",
  vehicleId,
  checks: inspectionChecks,
  defect: "",
});

test("A driver completes a delivery, and the office receives one invoice and one payment after retries", async (t) => {
  const { login, store } = await setup(t);
  const driver = await login("driver-ava");
  const admin = await login("admin-morgan");
  await rejectsCode(
    driver.act({ type: "order.start", orderId: "FW-1042" }),
    "BAD_REQUEST",
  );
  await rejectsCode(
    driver.act({ type: "shift.clock_in", vehicleId: "truck-12" }),
    "BAD_REQUEST",
  );
  await driver.act(inspection());
  await driver.act({ type: "shift.clock_in", vehicleId: "truck-12" });
  await driver.act({ type: "order.start", orderId: "FW-1042" });
  await rejectsCode(driver.act({ type: "shift.break_start" }), "BAD_REQUEST");
  await rejectsCode(
    driver.act({
      type: "order.complete",
      orderId: "FW-1042",
      note: "",
      signature: "",
    }),
    "BAD_REQUEST",
  );
  await driver.act({
    type: "order.confirm_container",
    orderId: "FW-1042",
    assetId: "BOX-201",
  });
  await rejectsCode(
    driver.act({
      type: "order.photo",
      orderId: "FW-1042",
      kind: "delivered",
      base64: "invalid-photo",
    }),
    "BAD_REQUEST",
  );
  await driver.act({
    type: "order.photo",
    orderId: "FW-1042",
    kind: "delivered",
    base64: samplePhoto,
  });
  const completion = {
    type: "order.complete",
    orderId: "FW-1042",
    note: "Placed at the marked site.",
    signature: "Demo recipient",
  } as const;
  const id = randomUUID();
  const results = await Promise.all([
    driver.act(completion, id),
    driver.act(completion, id),
  ]);
  assert.deepEqual(results.map((r) => r.duplicate).sort(), [false, true]);
  await runJobs(store);
  await runJobs(store);
  let snapshot = await admin.rpc.sync.snapshot.query();
  const invoices = snapshot.invoices.filter((i) => i.orderId === "FW-1042");
  assert.equal(invoices.length, 1);
  const invoice = invoices[0]!;
  const payment = {
    type: "payment.record",
    invoiceId: invoice.id,
    amountCents: invoice.amountCents,
    method: "card_demo",
  } as const;
  const paymentId = randomUUID();
  await Promise.all([
    admin.act(payment, paymentId),
    admin.act(payment, paymentId),
  ]);
  snapshot = await admin.rpc.sync.snapshot.query();
  assert.equal(
    snapshot.invoices.find((i) => i.id === invoice.id)?.status,
    "paid",
  );
  assert.equal(
    snapshot.payments.filter((p) => p.invoiceId === invoice.id).length,
    1,
  );
  assert.equal(
    snapshot.assets.find((a) => a.id === "BOX-201")?.customerId,
    "c1",
  );
  await rejectsCode(
    admin.act({ ...payment, amountCents: 1 }, paymentId),
    "CONFLICT",
  );
  await rejectsCode(admin.act(payment), "BAD_REQUEST");
  const photo = snapshot.orders.find((o) => o.id === "FW-1042")!.photos[0]!;
  await admin.act({
    type: "photo.verify",
    orderId: "FW-1042",
    photoId: photo.id,
  });
  assert.equal(
    (await driver.rpc.sync.snapshot.query()).orders.find(
      (o) => o.id === "FW-1042",
    )!.photos[0]!.verified,
    true,
  );
  await driver.act({ type: "shift.break_start" });
  await driver.act({ type: "shift.break_end" });
  await driver.act({ type: "shift.clock_out" });
  assert.ok((await driver.rpc.sync.snapshot.query()).shifts[0]?.endedAt);
});

test("A pickup requires removal evidence and a disposal ticket before completion", async (t) => {
  const { login } = await setup(t);
  const driver = await login("driver-ava");
  await driver.act(inspection());
  await driver.act({ type: "shift.clock_in", vehicleId: "truck-12" });
  await driver.act({ type: "order.start", orderId: "FW-1044" });
  await rejectsCode(
    driver.act({
      type: "order.confirm_container",
      orderId: "FW-1044",
      assetId: "BOX-201",
    }),
    "BAD_REQUEST",
  );
  await driver.act({
    type: "order.confirm_container",
    orderId: "FW-1044",
    assetId: "BOX-301",
  });
  await driver.act({
    type: "order.photo",
    orderId: "FW-1044",
    kind: "removed",
    base64: samplePhoto,
  });
  const complete = {
    type: "order.complete",
    orderId: "FW-1044",
    note: "",
    signature: "",
  } as const;
  await rejectsCode(driver.act(complete), "BAD_REQUEST");
  await driver.act({
    type: "order.dump",
    orderId: "FW-1044",
    weightTons: 2.4,
    dumpSite: "North transfer station",
  });
  await driver.act(complete);
  const result = await driver.rpc.sync.snapshot.query();
  assert.equal(result.orders.find((o) => o.id === "FW-1044")?.weightTons, 2.4);
  assert.equal(result.assets.find((a) => a.id === "BOX-301")?.status, "yard");
});

test("Profiles enforce route access, billing access, and authenticated reads", async (t) => {
  const { login, connect, url } = await setup(t);
  const driver = await login("driver-ava");
  await rejectsCode(connect().sync.snapshot.query(), "UNAUTHORIZED");
  await rejectsCode(
    connect(`${driver.token}tampered`).sync.snapshot.query(),
    "UNAUTHORIZED",
  );
  const snapshot = await driver.rpc.sync.snapshot.query();
  assert.ok(snapshot.orders.every((o) => o.driverId === "driver-ava"));
  assert.deepEqual(snapshot.invoices, []);
  assert.deepEqual(snapshot.payments, []);
  await rejectsCode(
    driver.act({ type: "order.start", orderId: "FW-1045" }),
    "FORBIDDEN",
  );
  await rejectsCode(
    driver.act({
      type: "order.assign",
      orderId: "FW-1042",
      routeId: "route-south",
    }),
    "FORBIDDEN",
  );
  await rejectsCode(
    driver.act({
      type: "payment.record",
      invoiceId: "INV-1001",
      amountCents: 10,
      method: "cash_demo",
    }),
    "FORBIDDEN",
  );
  assert.equal(
    (
      await fetch(`${url}/api/report`, {
        headers: { Authorization: `Bearer ${driver.token}` },
      })
    ).status,
    403,
  );
});

test("Dispatch creates, positions, resolves, and persists work across a store restart", async (t) => {
  const { login, path } = await setup(t);
  const office = await login("dispatcher-sam");
  const created = await office.act({
    type: "order.create",
    customerId: "c5",
    orderType: "delivery",
    size: "10 yd",
    date: today(),
    notes: "Use the marked gate.",
    priority: "urgent",
    priceCents: 35000,
  });
  await office.act({
    type: "order.assign",
    orderId: created.entityId,
    routeId: "route-north",
    position: 0,
  });
  await rejectsCode(
    office.act({
      type: "order.assign",
      orderId: created.entityId,
      routeId: "route-south",
      position: 999,
    }),
    "BAD_REQUEST",
  );
  let snapshot = await office.rpc.sync.snapshot.query();
  assert.equal(
    snapshot.routes.find((r) => r.id === "route-north")?.orderIds[0],
    created.entityId,
  );
  await office.act({
    type: "order.block",
    orderId: created.entityId,
    reason: "Gate closed.",
  });
  await office.act({ type: "order.resume", orderId: created.entityId });
  const restarted = new FileStore(path);
  t.after(() => restarted.close());
  assert.equal(
    (await restarted.read()).orders.find((o) => o.id === created.entityId)
      ?.status,
    "scheduled",
  );
  await office.act({
    type: "message.send",
    channel: "huddle",
    text: "The north route has a new stop.",
  });
  await office.act({
    type: "customer.note",
    customerId: "c5",
    note: "Access from the west gate.",
  });
  snapshot = await office.rpc.sync.snapshot.query();
  assert.equal(
    snapshot.messages.at(-1)?.text,
    "The north route has a new stop.",
  );
  assert.equal(
    snapshot.customers.find((c) => c.id === "c5")?.notes,
    "Access from the west gate.",
  );
});

test("A vehicle defect prevents clock-in until the office resolves maintenance and the driver inspects again", async (t) => {
  const { login } = await setup(t);
  const driver = await login("driver-ava");
  const office = await login("admin-morgan");
  await rejectsCode(
    driver.act({
      type: "inspection.submit",
      vehicleId: "truck-12",
      checks: ["Brakes"],
      defect: "",
    }),
    "BAD_REQUEST",
  );
  await driver.act({
    type: "inspection.submit",
    vehicleId: "truck-12",
    checks: inspectionChecks,
    defect: "Hydraulic leak.",
  });
  await rejectsCode(
    driver.act({ type: "shift.clock_in", vehicleId: "truck-12" }),
    "BAD_REQUEST",
  );
  const task = (await office.rpc.sync.snapshot.query()).tasks.find(
    (t) => t.vehicleId === "truck-12",
  )!;
  await office.act({ type: "task.complete", taskId: task.id });
  await rejectsCode(
    driver.act({ type: "shift.clock_in", vehicleId: "truck-12" }),
    "BAD_REQUEST",
  );
  await driver.act(inspection());
  await driver.act({ type: "shift.clock_in", vehicleId: "truck-12" });
  assert.equal(
    (await driver.rpc.sync.snapshot.query()).shifts[0]?.vehicleId,
    "truck-12",
  );
});

test("Demo phone verification rejects reused and exhausted challenges", async (t) => {
  const { post, connect } = await setup(t);
  const challenge = (await (
    await post("/api/auth/otp/phone", { profile: "driver-leo" })
  ).json()) as { challengeId: string };
  const verified = await post("/api/auth/otp/verify", {
    ...challenge,
    code: "123456",
  });
  assert.equal(verified.status, 200);
  const session = (await verified.json()) as { token: string };
  assert.equal(
    (await connect(session.token).sync.snapshot.query()).user.id,
    "driver-leo",
  );
  assert.equal(
    (await post("/api/auth/otp/verify", { ...challenge, code: "123456" }))
      .status,
    401,
  );
  const exhausted = (await (
    await post("/api/auth/otp/phone", { profile: "driver-ava" })
  ).json()) as { challengeId: string };
  for (let i = 0; i < 5; i++)
    assert.equal(
      (await post("/api/auth/otp/verify", { ...exhausted, code: "000000" }))
        .status,
      401,
    );
  assert.equal(
    (await post("/api/auth/otp/verify", { ...exhausted, code: "123456" }))
      .status,
    401,
  );
});

for (const scenario of [
  {
    name: "A swap requires both delivery and removal evidence",
    profile: "driver-ava",
    vehicle: "truck-12",
    order: "FW-1043",
    asset: "BOX-202",
    photos: ["delivered", "removed"] as const,
  },
  {
    name: "A live load requires site evidence and returns its container to the yard",
    profile: "driver-leo",
    vehicle: "truck-08",
    order: "FW-1045",
    asset: "BOX-302",
    photos: ["site"] as const,
  },
]) {
  test(scenario.name, async (t) => {
    const { login } = await setup(t);
    const driver = await login(scenario.profile);
    await driver.act(inspection(scenario.vehicle));
    await driver.act({ type: "shift.clock_in", vehicleId: scenario.vehicle });
    await driver.act({ type: "order.start", orderId: scenario.order });
    await driver.act({
      type: "order.confirm_container",
      orderId: scenario.order,
      assetId: scenario.asset,
    });
    await driver.act({
      type: "order.dump",
      orderId: scenario.order,
      weightTons: 1.5,
      dumpSite: "North transfer station",
    });
    const completion = {
      type: "order.complete",
      orderId: scenario.order,
      note: "",
      signature: "",
    } as const;
    for (const kind of scenario.photos) {
      await rejectsCode(driver.act(completion), "BAD_REQUEST");
      await driver.act({
        type: "order.photo",
        orderId: scenario.order,
        kind,
        base64: samplePhoto,
      });
    }
    await driver.act(completion);
    const snapshot = await driver.rpc.sync.snapshot.query();
    assert.equal(
      snapshot.orders.find((o) => o.id === scenario.order)?.status,
      "completed",
    );
    if (scenario.photos.length === 1)
      assert.equal(
        snapshot.assets.find((a) => a.id === scenario.asset)?.status,
        "yard",
      );
  });
}
