import { createHash, randomUUID } from "node:crypto";
import {
  activeShift,
  Command,
  Envelope,
  inspectionChecks,
  isOnBreak,
  Order,
  requiredPhotos,
  Snapshot,
  State,
  User,
} from "../src/shared/model";

export class DomainError extends Error {
  constructor(
    public code: "BAD_REQUEST" | "FORBIDDEN" | "NOT_FOUND" | "CONFLICT",
    message: string,
  ) {
    super(message);
  }
}
const requireRule = (ok: unknown, message: string) => {
  if (!ok) throw new DomainError("BAD_REQUEST", message);
};
const find = <T extends { id: string }>(items: T[], id: string): T => {
  const item = items.find((value) => value.id === id);
  if (!item)
    throw new DomainError("NOT_FOUND", "The requested record does not exist.");
  return item;
};
const officeOnly = (user: User) => {
  if (user.role === "driver")
    throw new DomainError(
      "FORBIDDEN",
      "This action requires an Office profile.",
    );
};
const ownOrder = (state: State, user: User, id: string) => {
  const order = find(state.orders, id);
  if (user.role === "driver" && order.driverId !== user.id)
    throw new DomainError("FORBIDDEN", "This order belongs to another driver.");
  return order;
};
const notify = (
  state: State,
  title: string,
  body: string,
  now: string,
  userId?: string,
) =>
  state.notifications.unshift({
    id: randomUUID(),
    title,
    body,
    userId,
    readBy: [],
    createdAt: now,
  });
const workingShift = (state: State, user: User) => {
  const shift = activeShift(state.shifts, user.id);
  requireRule(shift, "Complete an inspection and clock in first.");
  requireRule(!isOnBreak(shift), "End your break before you start a job.");
  return shift!;
};

export function execute(
  state: State,
  user: User,
  envelope: Envelope,
  now = new Date().toISOString(),
  traceContext?: Record<string, string>,
) {
  const key = `${user.id}:${envelope.requestId}`;
  const fingerprint = createHash("sha256")
    .update(JSON.stringify(envelope.command))
    .digest("hex");
  const receipt = state.receipts[key];
  if (receipt) {
    if (receipt.fingerprint !== fingerprint)
      throw new DomainError(
        "CONFLICT",
        "The request ID belongs to a different action.",
      );
    return { entityId: receipt.entityId, duplicate: true };
  }
  const command = envelope.command;
  let entityId: string = user.id;
  if ("orderId" in command) entityId = command.orderId;
  switch (command.type) {
    case "order.create": {
      officeOnly(user);
      find(state.customers, command.customerId);
      entityId = `FW-${Math.max(1046, ...state.orders.map((o) => Number(o.id.split("-")[1]) || 0)) + 1}`;
      state.orders.push({
        id: entityId,
        customerId: command.customerId,
        type: command.orderType,
        size: command.size,
        date: command.date,
        notes: command.notes,
        priority: command.priority,
        priceCents: command.priceCents,
        window: "08:00–16:00",
        status: "unassigned",
        containerConfirmed: false,
        photos: [],
      });
      notify(state, "New order", `${entityId} is ready for dispatch.`, now);
      break;
    }
    case "order.assign": {
      officeOnly(user);
      const order = find(state.orders, command.orderId);
      const route = find(state.routes, command.routeId);
      requireRule(
        !["completed", "in_progress"].includes(order.status),
        "Only waiting orders can be assigned.",
      );
      requireRule(
        find(state.vehicles, route.vehicleId).status === "ready",
        "This route uses a vehicle under maintenance.",
      );
      state.routes.forEach((r) => {
        r.orderIds = r.orderIds.filter((id) => id !== order.id);
      });
      const position = command.position ?? route.orderIds.length;
      requireRule(
        position <= route.orderIds.length,
        "The route position is outside the stop list.",
      );
      route.orderIds.splice(position, 0, order.id);
      Object.assign(order, {
        routeId: route.id,
        driverId: route.driverId,
        status: "scheduled",
      });
      notify(
        state,
        "Route updated",
        `${order.id} was added to ${route.name}.`,
        now,
        route.driverId,
      );
      break;
    }
    case "order.start": {
      const order = ownOrder(state, user, command.orderId);
      const shift = workingShift(state, user);
      requireRule(
        order.status === "scheduled",
        "Only a scheduled job can start.",
      );
      requireRule(
        find(state.vehicles, shift.vehicleId).status === "ready",
        "This vehicle is under maintenance.",
      );
      requireRule(
        !state.orders.some(
          (o) => o.status === "in_progress" && o.driverId === order.driverId,
        ),
        "Complete or report the active job first.",
      );
      if (user.role === "driver")
        requireRule(
          find(state.routes, order.routeId!).vehicleId === shift.vehicleId,
          "Select the truck assigned to this route.",
        );
      order.status = "in_progress";
      order.startedAt = now;
      break;
    }
    case "order.confirm_container": {
      const order = ownOrder(state, user, command.orderId);
      requireRule(
        order.status === "in_progress",
        "Start this job before you confirm the container.",
      );
      const asset = find(state.assets, command.assetId);
      requireRule(
        asset.status !== "maintenance",
        "This container needs maintenance.",
      );
      requireRule(
        asset.size === order.size,
        "Select a container with the required size.",
      );
      requireRule(
        ["pickup", "swap"].includes(order.type)
          ? asset.status === "on_site" && asset.customerId === order.customerId
          : ["yard", "on_truck"].includes(asset.status),
        "Select an available container for this site and service type.",
      );
      requireRule(
        !state.orders.some(
          (o) =>
            o.id !== order.id &&
            ["in_progress", "blocked"].includes(o.status) &&
            o.assetId === asset.id,
        ),
        "Another active job uses this container.",
      );
      order.assetId = asset.id;
      order.containerConfirmed = true;
      break;
    }
    case "order.photo": {
      const order = ownOrder(state, user, command.orderId);
      requireRule(
        order.status === "in_progress",
        "Start this job before you add evidence.",
      );
      requireRule(
        order.photos.length < 12,
        "This job already has the maximum number of photos.",
      );
      const bytes = Buffer.from(command.base64, "base64");
      requireRule(
        bytes.length <= 2 * 1024 * 1024 &&
          bytes[0] === 0xff &&
          bytes[1] === 0xd8 &&
          bytes[2] === 0xff,
        "Use a JPEG photo smaller than 2 MiB.",
      );
      order.photos.push({
        id: randomUUID(),
        kind: command.kind,
        uri: `data:image/jpeg;base64,${bytes.toString("base64")}`,
        verified: false,
        createdAt: now,
      });
      break;
    }
    case "order.dump": {
      const order = ownOrder(state, user, command.orderId);
      requireRule(
        order.status === "in_progress",
        "Start this job before you record a disposal ticket.",
      );
      requireRule(
        order.type !== "delivery",
        "Delivery jobs do not need a disposal ticket.",
      );
      order.weightTons = command.weightTons;
      order.dumpSite = command.dumpSite;
      break;
    }
    case "order.complete": {
      const order = ownOrder(state, user, command.orderId);
      requireRule(
        order.status === "in_progress",
        "Only an active job can be completed.",
      );
      requireRule(
        order.containerConfirmed,
        "Confirm the container before you complete this job.",
      );
      requireRule(
        requiredPhotos(order.type).every((kind) =>
          order.photos.some((p) => p.kind === kind),
        ),
        "Add all required photos before you complete this job.",
      );
      if (order.type !== "delivery")
        requireRule(
          order.weightTons && order.dumpSite,
          "Record the disposal weight and site first.",
        );
      order.status = "completed";
      order.completedAt = now;
      order.completionNote = command.note;
      order.signature = command.signature;
      const asset = find(state.assets, order.assetId!);
      asset.status = ["pickup", "live_load"].includes(order.type)
        ? "yard"
        : "on_site";
      asset.customerId =
        asset.status === "on_site" ? order.customerId : undefined;
      state.events.push({
        id: randomUUID(),
        type: "order.completed",
        orderId: order.id,
        createdAt: now,
        traceContext,
      });
      notify(
        state,
        "Job completed",
        `${order.id} is complete. The invoice is in the processing queue.`,
        now,
      );
      break;
    }
    case "order.block": {
      const order = ownOrder(state, user, command.orderId);
      requireRule(
        ["scheduled", "in_progress"].includes(order.status),
        "Only an active or scheduled job can be blocked.",
      );
      order.status = "blocked";
      order.completionNote = command.reason;
      notify(
        state,
        "Dispatch needs to act",
        `${order.id}: ${command.reason}`,
        now,
      );
      break;
    }
    case "order.resume": {
      officeOnly(user);
      const order = find(state.orders, command.orderId);
      requireRule(order.status === "blocked", "This job is not blocked.");
      order.status = order.routeId ? "scheduled" : "unassigned";
      break;
    }
    case "photo.verify": {
      officeOnly(user);
      find(
        find(state.orders, command.orderId).photos,
        command.photoId,
      ).verified = true;
      break;
    }
    case "inspection.submit": {
      const vehicle = find(state.vehicles, command.vehicleId);
      requireRule(
        inspectionChecks.every((check) => command.checks.includes(check)),
        "Check every inspection item before you submit.",
      );
      entityId = randomUUID();
      state.inspections.unshift({
        id: entityId,
        userId: user.id,
        vehicleId: vehicle.id,
        checks: command.checks,
        defect: command.defect,
        safe: !command.defect,
        createdAt: now,
      });
      if (command.defect) {
        vehicle.status = "maintenance";
        state.tasks.unshift({
          id: randomUUID(),
          title: command.defect,
          type: "maintenance",
          vehicleId: vehicle.id,
          status: "open",
          createdAt: now,
        });
        notify(
          state,
          "Vehicle defect reported",
          `${vehicle.name} needs a maintenance review.`,
          now,
        );
      }
      break;
    }
    case "shift.clock_in": {
      requireRule(
        !activeShift(state.shifts, user.id),
        "You already have an active shift.",
      );
      const vehicle = find(state.vehicles, command.vehicleId);
      requireRule(
        vehicle.status === "ready",
        "This vehicle is under maintenance.",
      );
      requireRule(
        !state.shifts.some((s) => s.vehicleId === vehicle.id && !s.endedAt),
        "Another active shift uses this vehicle.",
      );
      const inspection = state.inspections.find(
        (i) => i.vehicleId === vehicle.id && i.userId === user.id,
      );
      requireRule(
        inspection?.safe &&
          inspection.createdAt.slice(0, 10) === now.slice(0, 10),
        "Complete a safe vehicle inspection today before you clock in.",
      );
      entityId = randomUUID();
      state.shifts.unshift({
        id: entityId,
        userId: user.id,
        vehicleId: vehicle.id,
        startedAt: now,
        breaks: [],
      });
      break;
    }
    case "shift.break_start": {
      const shift = workingShift(state, user);
      requireRule(
        !state.orders.some(
          (o) => o.status === "in_progress" && o.driverId === user.id,
        ),
        "Complete or report the active job before your break.",
      );
      shift.breaks.push({ startedAt: now });
      entityId = shift.id;
      break;
    }
    case "shift.break_end": {
      const shift = activeShift(state.shifts, user.id);
      const currentBreak = shift?.breaks.find((b) => !b.endedAt);
      requireRule(currentBreak, "There is no active break.");
      currentBreak!.endedAt = now;
      entityId = shift!.id;
      break;
    }
    case "shift.clock_out": {
      const shift = activeShift(state.shifts, user.id);
      requireRule(shift, "There is no active shift.");
      requireRule(
        !state.orders.some(
          (o) => o.status === "in_progress" && o.driverId === user.id,
        ),
        "Complete or report the active job before you end the day.",
      );
      shift!.breaks
        .filter((b) => !b.endedAt)
        .forEach((b) => {
          b.endedAt = now;
        });
      shift!.endedAt = now;
      entityId = shift!.id;
      break;
    }
    case "message.send": {
      if (command.channel.startsWith("customer:")) {
        const customerId = command.channel.split(":")[1]!;
        find(state.customers, customerId);
        if (user.role === "driver")
          requireRule(
            state.orders.some(
              (o) => o.driverId === user.id && o.customerId === customerId,
            ),
            "This customer is outside your route.",
          );
      }
      entityId = randomUUID();
      state.messages.push({
        id: entityId,
        channel: command.channel,
        authorId: user.id,
        text: command.text,
        kind: "message",
        createdAt: now,
      });
      notify(
        state,
        "New message",
        command.channel === "huddle"
          ? "Your team has a new huddle message."
          : "A new message is available in Comms.",
        now,
      );
      break;
    }
    case "call.record": {
      officeOnly(user);
      find(state.customers, command.customerId);
      entityId = randomUUID();
      state.messages.push({
        id: entityId,
        channel: `customer:${command.customerId}`,
        authorId: user.id,
        text: `Demo call: ${command.outcome.replaceAll("_", " ")}. No telephone call was placed.`,
        kind: "call",
        createdAt: now,
      });
      break;
    }
    case "notification.read": {
      const notification = find(state.notifications, command.notificationId);
      if (notification.userId && notification.userId !== user.id)
        throw new DomainError(
          "FORBIDDEN",
          "This notification belongs to another user.",
        );
      if (!notification.readBy.includes(user.id))
        notification.readBy.push(user.id);
      entityId = notification.id;
      break;
    }
    case "payment.record": {
      officeOnly(user);
      const invoice = find(state.invoices, command.invoiceId);
      requireRule(
        command.amountCents <= invoice.amountCents - invoice.paidCents,
        "The payment exceeds the invoice balance.",
      );
      invoice.paidCents += command.amountCents;
      invoice.status =
        invoice.paidCents === invoice.amountCents ? "paid" : "open";
      entityId = randomUUID();
      state.payments.push({
        id: entityId,
        invoiceId: invoice.id,
        amountCents: command.amountCents,
        method: command.method,
        createdAt: now,
      });
      notify(
        state,
        "Demo payment recorded",
        `${invoice.id} was updated. No money was transferred.`,
        now,
      );
      break;
    }
    case "maintenance.create": {
      officeOnly(user);
      const vehicle = find(state.vehicles, command.vehicleId);
      vehicle.status = "maintenance";
      entityId = randomUUID();
      state.tasks.unshift({
        id: entityId,
        title: command.title,
        type: "maintenance",
        vehicleId: vehicle.id,
        status: "open",
        createdAt: now,
      });
      break;
    }
    case "task.complete": {
      officeOnly(user);
      const task = find(state.tasks, command.taskId);
      task.status = "done";
      entityId = task.id;
      if (
        task.vehicleId &&
        !state.tasks.some(
          (t) => t.vehicleId === task.vehicleId && t.status === "open",
        )
      )
        find(state.vehicles, task.vehicleId).status = "ready";
      break;
    }
    case "customer.note":
      officeOnly(user);
      find(state.customers, command.customerId).notes = command.note;
      entityId = command.customerId;
      break;
    case "device.register": {
      state.devices = state.devices.filter((d) => d.token !== command.token);
      state.devices.push({
        userId: user.id,
        token: command.token,
        platform: command.platform,
      });
      break;
    }
    default: {
      const exhaustive: never = command;
      throw new Error(`Unknown command: ${exhaustive}`);
    }
  }
  state.revision += 1;
  state.receipts[key] = { fingerprint, entityId };
  state.audit.unshift({
    id: randomUUID(),
    actorId: user.id,
    action: command.type,
    entityId,
    createdAt: now,
  });
  state.audit = state.audit.slice(0, 200);
  return { entityId, duplicate: false };
}

export function processEvent(
  state: State,
  eventId: string,
  now = new Date().toISOString(),
) {
  const event = find(state.events, eventId);
  if (event.processedAt) return;
  const order = find(state.orders, event.orderId);
  if (!state.invoices.some((i) => i.orderId === order.id)) {
    state.invoices.push({
      id: `INV-${order.id.slice(3)}`,
      orderId: order.id,
      customerId: order.customerId,
      amountCents: order.priceCents,
      paidCents: 0,
      status: "open",
      createdAt: now,
    });
    notify(
      state,
      "Invoice ready",
      `The invoice for ${order.id} is ready for review.`,
      now,
    );
  }
  event.processedAt = now;
  state.revision += 1;
}

export function snapshot(state: State, user: User): Snapshot {
  const {
    events,
    receipts: _receipts,
    devices: _devices,
    ...data
  } = structuredClone(state);
  if (user.role === "driver") {
    data.orders = data.orders.filter((o) => o.driverId === user.id);
    const customerIds = new Set(data.orders.map((o) => o.customerId));
    data.customers = data.customers.filter((c) => customerIds.has(c.id));
    data.routes = data.routes.filter((r) => r.driverId === user.id);
    data.shifts = data.shifts.filter((s) => s.userId === user.id);
    data.inspections = data.inspections.filter((i) => i.userId === user.id);
    data.invoices = [];
    data.payments = [];
    data.messages = data.messages.filter(
      (m) =>
        !m.channel.startsWith("customer:") ||
        customerIds.has(m.channel.split(":")[1]!),
    );
    data.audit = data.audit.filter((a) => a.actorId === user.id);
    data.tasks = data.tasks.filter((t) => t.type === "maintenance");
  }
  data.notifications = data.notifications.filter(
    (n) => !n.userId || n.userId === user.id,
  );
  return {
    ...data,
    user,
    serverTime: new Date().toISOString(),
    pendingJobs:
      user.role === "driver" ? 0 : events.filter((e) => !e.processedAt).length,
  };
}
