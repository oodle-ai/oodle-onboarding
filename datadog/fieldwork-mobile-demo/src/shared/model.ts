import { z } from "zod";

export type Role = "driver" | "dispatcher" | "admin";
export type User = {
  id: string;
  name: string;
  role: Role;
  initials: string;
  email: string;
};
export type Customer = {
  id: string;
  name: string;
  contact: string;
  email: string;
  phone: string;
  address: string;
  lat: number;
  lng: number;
  notes: string;
};
export type Vehicle = {
  id: string;
  name: string;
  plate: string;
  capacity: string;
  status: "ready" | "maintenance";
};
export type Asset = {
  id: string;
  size: string;
  status: "yard" | "on_site" | "on_truck" | "maintenance";
  customerId?: string;
};
export type Route = {
  id: string;
  name: string;
  driverId: string;
  vehicleId: string;
  orderIds: string[];
  color: string;
};
export type PhotoKind = "delivered" | "removed" | "ticket" | "site";
export type Photo = {
  id: string;
  kind: PhotoKind;
  uri: string;
  verified: boolean;
  createdAt: string;
};
export type Order = {
  id: string;
  customerId: string;
  type: "delivery" | "pickup" | "swap" | "live_load";
  size: string;
  date: string;
  window: string;
  priority: "normal" | "urgent";
  status: "unassigned" | "scheduled" | "in_progress" | "completed" | "blocked";
  routeId?: string;
  driverId?: string;
  assetId?: string;
  notes: string;
  containerConfirmed: boolean;
  photos: Photo[];
  weightTons?: number;
  dumpSite?: string;
  completionNote?: string;
  completedAt?: string;
  startedAt?: string;
  signature?: string;
  priceCents: number;
};
export type Shift = {
  id: string;
  userId: string;
  vehicleId: string;
  startedAt: string;
  endedAt?: string;
  breaks: { startedAt: string; endedAt?: string }[];
};
export type Inspection = {
  id: string;
  userId: string;
  vehicleId: string;
  createdAt: string;
  checks: string[];
  defect: string;
  safe: boolean;
};
export type Invoice = {
  id: string;
  orderId: string;
  customerId: string;
  amountCents: number;
  paidCents: number;
  status: "open" | "paid";
  createdAt: string;
};
export type Payment = {
  id: string;
  invoiceId: string;
  amountCents: number;
  method: "card_demo" | "cash_demo";
  createdAt: string;
};
export type Message = {
  id: string;
  channel: string;
  authorId: string;
  text: string;
  createdAt: string;
  kind: "message" | "call" | "system";
};
export type Notification = {
  id: string;
  title: string;
  body: string;
  userId?: string;
  readBy: string[];
  createdAt: string;
};
export type Task = {
  id: string;
  title: string;
  type: "maintenance" | "follow_up";
  vehicleId?: string;
  status: "open" | "done";
  createdAt: string;
};
export type OutboxEvent = {
  id: string;
  type: "order.completed";
  orderId: string;
  createdAt: string;
  processedAt?: string;
  traceContext?: Record<string, string>;
};
export type Audit = {
  id: string;
  actorId: string;
  action: string;
  entityId: string;
  createdAt: string;
};
export type State = {
  revision: number;
  users: User[];
  customers: Customer[];
  vehicles: Vehicle[];
  assets: Asset[];
  routes: Route[];
  orders: Order[];
  shifts: Shift[];
  inspections: Inspection[];
  invoices: Invoice[];
  payments: Payment[];
  messages: Message[];
  notifications: Notification[];
  tasks: Task[];
  events: OutboxEvent[];
  audit: Audit[];
  receipts: Record<string, { fingerprint: string; entityId: string }>;
  devices: { userId: string; token: string; platform: string }[];
};
export type Snapshot = Omit<State, "events" | "receipts" | "devices"> & {
  user: User;
  serverTime: string;
  pendingJobs: number;
};

const id = z.string().min(1).max(100);
const note = z.string().trim().max(2000);
const text = z.string().trim().min(1).max(2000);
const cents = z.number().int().min(1).max(10000000);
export const inspectionChecks = [
  "Brakes",
  "Tires",
  "Lights",
  "Hydraulics",
  "Mirrors",
  "Safety equipment",
];
export const dumpSites = [
  "North transfer station",
  "Harbor recycling center",
  "South recovery facility",
];
export const commandSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("order.create"),
    customerId: id,
    orderType: z.enum(["delivery", "pickup", "swap", "live_load"]),
    size: z.enum(["10 yd", "20 yd", "30 yd", "40 yd"]),
    date: z.iso.date(),
    notes: note,
    priority: z.enum(["normal", "urgent"]),
    priceCents: cents,
  }),
  z.object({
    type: z.literal("order.assign"),
    orderId: id,
    routeId: id,
    position: z.number().int().min(0).optional(),
  }),
  z.object({ type: z.literal("order.start"), orderId: id }),
  z.object({
    type: z.literal("order.confirm_container"),
    orderId: id,
    assetId: id,
  }),
  z.object({
    type: z.literal("order.photo"),
    orderId: id,
    kind: z.enum(["delivered", "removed", "ticket", "site"]),
    base64: z.string().min(4).max(2800000),
  }),
  z.object({
    type: z.literal("order.dump"),
    orderId: id,
    weightTons: z.number().min(0.01).max(40),
    dumpSite: z.enum(dumpSites as [string, ...string[]]),
  }),
  z.object({
    type: z.literal("order.complete"),
    orderId: id,
    note,
    signature: z.string().trim().max(100),
  }),
  z.object({ type: z.literal("order.block"), orderId: id, reason: text }),
  z.object({ type: z.literal("order.resume"), orderId: id }),
  z.object({ type: z.literal("photo.verify"), orderId: id, photoId: id }),
  z.object({
    type: z.literal("inspection.submit"),
    vehicleId: id,
    checks: z.array(z.enum(inspectionChecks as [string, ...string[]])).max(6),
    defect: note,
  }),
  z.object({ type: z.literal("shift.clock_in"), vehicleId: id }),
  z.object({ type: z.literal("shift.break_start") }),
  z.object({ type: z.literal("shift.break_end") }),
  z.object({ type: z.literal("shift.clock_out") }),
  z.object({
    type: z.literal("message.send"),
    channel: z.string().regex(/^(dispatch|huddle|customer:c[0-9]+)$/),
    text,
  }),
  z.object({
    type: z.literal("call.record"),
    customerId: id,
    outcome: z.enum(["connected", "voicemail", "no_answer"]),
  }),
  z.object({ type: z.literal("notification.read"), notificationId: id }),
  z.object({
    type: z.literal("payment.record"),
    invoiceId: id,
    amountCents: cents,
    method: z.enum(["card_demo", "cash_demo"]),
  }),
  z.object({
    type: z.literal("maintenance.create"),
    vehicleId: id,
    title: text,
  }),
  z.object({ type: z.literal("task.complete"), taskId: id }),
  z.object({ type: z.literal("customer.note"), customerId: id, note }),
  z.object({
    type: z.literal("device.register"),
    token: z.string().min(1).max(300),
    platform: z.enum(["ios", "android", "web"]),
  }),
]);
export type Command = z.infer<typeof commandSchema>;
export type Envelope = { requestId: string; command: Command };
export const envelopeSchema = z.object({
  requestId: z.string().uuid(),
  command: commandSchema,
});
export const money = (cents: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: cents % 100 ? 2 : 0,
  }).format(cents / 100);
export const label = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
export const today = () => new Date().toISOString().slice(0, 10);
export const activeShift = (shifts: Shift[], userId: string) =>
  shifts.find((s) => s.userId === userId && !s.endedAt);
export const isOnBreak = (shift?: Shift) =>
  !!shift?.breaks.some((b) => !b.endedAt);
export const requiredPhotos = (type: Order["type"]): PhotoKind[] =>
  type === "swap"
    ? ["delivered", "removed"]
    : type === "delivery"
      ? ["delivered"]
      : type === "pickup"
        ? ["removed"]
        : ["site"];
