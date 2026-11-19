import React, { useState } from "react";
import { View } from "react-native";
import { NativeStackScreenProps } from "@react-navigation/native-stack";
import { StackParams, useNav } from "../navigation";
import { useApp } from "../state";
import { label, money } from "../shared/model";
import {
  Badge,
  Button,
  Card,
  Choices,
  colors,
  Empty,
  Field,
  Heading,
  Icon,
  MenuItem,
  OrderCard,
  Page,
  Row,
  Txt,
} from "../components/ui";

export function CustomersScreen() {
  const { data } = useApp();
  const nav = useNav();
  const [query, setQuery] = useState("");
  const customers =
    data?.customers.filter((c) =>
      `${c.name} ${c.address} ${c.contact}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ) || [];
  return (
    <Page>
      <Heading
        title="People behind the places."
        subtitle="Customer details, site instructions, and service history."
      />
      <Field
        title="Find a customer"
        placeholder="Name, contact, or address"
        value={query}
        onChangeText={setQuery}
      />
      {customers.map((c) => (
        <Card key={c.id}>
          <MenuItem
            title={c.name}
            subtitle={c.address}
            icon="map-pin"
            onPress={() => nav.navigate("Customer", { id: c.id })}
          />
          <Row style={{ marginTop: 14, justifyContent: "space-between" }}>
            <Txt muted>{c.contact}</Txt>
            <Badge
              text={`${data?.orders.filter((o) => o.customerId === c.id).length} orders`}
            />
          </Row>
        </Card>
      ))}
      {!customers.length && (
        <Empty
          title="No customers found"
          detail="Try another name or address."
        />
      )}
    </Page>
  );
}
export function CustomerScreen({
  route,
}: NativeStackScreenProps<StackParams, "Customer">) {
  const { data, office, run, notify } = useApp();
  const nav = useNav();
  const customer = data?.customers.find((c) => c.id === route.params.id);
  const [note, setNote] = useState(customer?.notes || "");
  if (!data || !customer) return null;
  return (
    <Page>
      <Heading title={customer.name} subtitle={customer.address} />
      <Card style={{ gap: 14 }}>
        <Row style={{ gap: 9 }}>
          <Icon name="user" />
          <Txt style={{ fontWeight: "700" }}>{customer.contact}</Txt>
        </Row>
        <Txt muted>{customer.email}</Txt>
        <Txt muted>{customer.phone} · fictional contact</Txt>
        <Txt style={{ lineHeight: 22 }}>{customer.notes}</Txt>
      </Card>
      {office && (
        <>
          <Button
            title="Schedule service"
            icon="plus"
            onPress={() =>
              nav.navigate("NewOrder", { customerId: customer.id })
            }
          />
          <Card style={{ gap: 13 }}>
            <Field
              title="Site instructions"
              multiline
              value={note}
              onChangeText={setNote}
            />
            <Button
              title="Save site notes"
              variant="secondary"
              onPress={async () => {
                await run({
                  type: "customer.note",
                  customerId: customer.id,
                  note,
                });
                notify("Site notes saved.", "success");
              }}
            />
          </Card>
        </>
      )}
      <View>
        <Heading title="Service history" />
        <View style={{ gap: 12 }}>
          {data.orders
            .filter((o) => o.customerId === customer.id)
            .map((o) => (
              <OrderCard key={o.id} order={o} />
            ))}
        </View>
      </View>
      {office && (
        <Card>
          <Heading title="Account balance" />
          <Txt style={{ fontSize: 30, fontWeight: "700" }}>
            {money(
              data.invoices
                .filter((i) => i.customerId === customer.id)
                .reduce((n, i) => n + i.amountCents - i.paidCents, 0),
            )}
          </Txt>
          <Button
            title="Open invoices & payments"
            variant="ghost"
            onPress={() => nav.navigate("Invoices")}
          />
        </Card>
      )}
    </Page>
  );
}
export function InvoicesScreen() {
  const { data, run, notify } = useApp();
  const [filter, setFilter] = useState("open");
  const [selected, setSelected] = useState("");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"card_demo" | "cash_demo">("card_demo");
  if (!data) return null;
  const invoices = data.invoices.filter(
    (i) => filter === "all" || i.status === filter,
  );
  return (
    <Page>
      <Heading
        title="Good work. Clear accounts."
        subtitle="Invoices are created by the worker after a job is complete."
      />
      <Card style={{ backgroundColor: colors.ink, gap: 8 }}>
        <Txt style={{ color: "#becfb9" }}>Outstanding balance</Txt>
        <Txt
          style={{
            color: colors.white,
            fontSize: 36,
            fontWeight: "700",
            letterSpacing: -1,
          }}
        >
          {money(
            data.invoices.reduce((n, i) => n + i.amountCents - i.paidCents, 0),
          )}
        </Txt>
        <Txt style={{ color: colors.lime, fontSize: 12 }}>
          {data.pendingJobs} billing jobs pending
        </Txt>
      </Card>
      <Choices
        values={["open", "paid", "all"]}
        value={filter}
        onChange={setFilter}
      />
      {invoices.map((invoice) => (
        <Card key={invoice.id} style={{ gap: 15 }}>
          <Row style={{ justifyContent: "space-between" }}>
            <Txt style={{ fontWeight: "700" }}>{invoice.id}</Txt>
            <Badge
              text={label(invoice.status)}
              tone={invoice.status === "paid" ? "green" : "amber"}
            />
          </Row>
          <Txt style={{ fontSize: 18, fontWeight: "700" }}>
            {data.customers.find((c) => c.id === invoice.customerId)?.name}
          </Txt>
          <Row style={{ justifyContent: "space-between" }}>
            <Txt muted>{invoice.orderId}</Txt>
            <Txt style={{ fontWeight: "700", fontSize: 21 }}>
              {money(invoice.amountCents)}
            </Txt>
          </Row>
          <Txt muted>
            Paid {money(invoice.paidCents)} · Balance{" "}
            {money(invoice.amountCents - invoice.paidCents)}
          </Txt>
          {invoice.status === "open" &&
            (selected === invoice.id ? (
              <View style={{ gap: 14 }}>
                <Field
                  title="Payment amount · USD"
                  keyboardType="decimal-pad"
                  value={amount}
                  onChangeText={setAmount}
                />
                <Choices
                  values={["card_demo", "cash_demo"] as const}
                  value={method}
                  onChange={setMethod}
                  labels={{ card_demo: "Demo card", cash_demo: "Demo cash" }}
                />
                <Txt muted style={{ fontSize: 12, lineHeight: 18 }}>
                  This is a simulated payment. No card details are collected and
                  no money is transferred.
                </Txt>
                <Button
                  title="Record demo payment"
                  icon="check"
                  onPress={async () => {
                    const result = await run({
                      type: "payment.record",
                      invoiceId: invoice.id,
                      amountCents: Math.round(Number(amount) * 100),
                      method,
                    });
                    if (!result.queued)
                      notify("Demo payment recorded.", "success");
                    setSelected("");
                  }}
                />
                <Button
                  title="Cancel payment"
                  variant="ghost"
                  small
                  onPress={() => setSelected("")}
                />
              </View>
            ) : (
              <Button
                title={`Pay ${invoice.id}`}
                variant="secondary"
                icon="credit-card"
                onPress={() => {
                  setSelected(invoice.id);
                  setAmount(
                    ((invoice.amountCents - invoice.paidCents) / 100).toFixed(
                      2,
                    ),
                  );
                }}
              />
            ))}
        </Card>
      ))}
      {!invoices.length && (
        <Empty
          title="No invoices in this view"
          detail="Complete a job, then refresh after the billing worker runs."
          icon="file-text"
        />
      )}
      <View>
        <Heading title="Payment activity" />
        {data.payments.length ? (
          data.payments
            .slice()
            .reverse()
            .map((p) => (
              <Card key={p.id} style={{ marginBottom: 12 }}>
                <Row style={{ justifyContent: "space-between" }}>
                  <Txt style={{ fontWeight: "700" }}>{p.invoiceId}</Txt>
                  <Txt style={{ fontWeight: "700" }}>
                    {money(p.amountCents)}
                  </Txt>
                </Row>
                <Txt muted style={{ marginTop: 8, fontSize: 12 }}>
                  {label(p.method)} · {new Date(p.createdAt).toLocaleString()}
                </Txt>
              </Card>
            ))
        ) : (
          <Txt muted>Recorded demo payments will appear here.</Txt>
        )}
      </View>
    </Page>
  );
}
export function FleetScreen() {
  const { data, run, office, notify } = useApp();
  const nav = useNav();
  const [vehicle, setVehicle] = useState("truck-12");
  const [title, setTitle] = useState("");
  if (!data) return null;
  return (
    <Page>
      <Heading
        title="Ready for the road."
        subtitle="Trucks, containers, and the work that keeps them moving."
      />
      {data.vehicles.map((v) => (
        <Card key={v.id} style={{ gap: 13 }}>
          <Row style={{ justifyContent: "space-between" }}>
            <Row style={{ gap: 12 }}>
              <Icon name="truck" size={25} />
              <Txt style={{ fontSize: 20, fontWeight: "700" }}>{v.name}</Txt>
            </Row>
            <Badge
              text={label(v.status)}
              tone={v.status === "ready" ? "green" : "amber"}
            />
          </Row>
          <Txt muted>
            {v.plate} · {v.capacity}
          </Txt>
          <Button
            title={`Inspect ${v.name}`}
            small
            variant="secondary"
            onPress={() => nav.navigate("Inspection", { vehicleId: v.id })}
          />
        </Card>
      ))}
      <View>
        <Heading title="Shop board" />
        <View style={{ gap: 12 }}>
          {data.tasks
            .filter((t) => t.status === "open")
            .map((t) => (
              <Card key={t.id} style={{ gap: 12 }}>
                <Badge text={label(t.type)} tone="amber" />
                <Txt style={{ fontWeight: "700" }}>{t.title}</Txt>
                <Txt muted>
                  {data.vehicles.find((v) => v.id === t.vehicleId)?.name}
                </Txt>
                {office && (
                  <Button
                    title="Mark maintenance complete"
                    variant="secondary"
                    small
                    onPress={() => run({ type: "task.complete", taskId: t.id })}
                  />
                )}
              </Card>
            ))}
        </View>
      </View>
      {office && (
        <Card style={{ gap: 14 }}>
          <Heading title="New maintenance task" />
          <Choices
            values={data.vehicles.map((v) => v.id)}
            labels={Object.fromEntries(
              data.vehicles.map((v) => [v.id, v.name]),
            )}
            value={vehicle}
            onChange={setVehicle}
          />
          <Field
            title="Work required"
            value={title}
            onChangeText={setTitle}
            placeholder="Describe the work"
          />
          <Button
            title="Create shop task"
            disabled={!title.trim()}
            variant="secondary"
            onPress={async () => {
              await run({
                type: "maintenance.create",
                vehicleId: vehicle,
                title,
              });
              setTitle("");
              notify("Task created. The truck is in maintenance.", "success");
            }}
          />
        </Card>
      )}
      <Card>
        <Heading title="Container inventory" />
        {data.assets.map((a) => (
          <Row
            key={a.id}
            style={{
              paddingVertical: 13,
              justifyContent: "space-between",
              borderBottomWidth: 1,
              borderColor: colors.line,
            }}
          >
            <View>
              <Txt style={{ fontWeight: "700" }}>
                {a.id} · {a.size}
              </Txt>
              {a.customerId && (
                <Txt muted style={{ marginTop: 4, fontSize: 12 }}>
                  {data.customers.find((c) => c.id === a.customerId)?.name ||
                    "At customer site"}
                </Txt>
              )}
            </View>
            <Badge text={label(a.status)} tone="gray" />
          </Row>
        ))}
      </Card>
    </Page>
  );
}
export function SearchScreen() {
  const { data } = useApp();
  const nav = useNav();
  const [query, setQuery] = useState("");
  const match = (text: string) =>
    text.toLowerCase().includes(query.toLowerCase());
  return (
    <Page>
      <Heading title="Find your next detail." />
      <Field
        title="Search orders and customers"
        placeholder="Order ID, site, or address"
        value={query}
        onChangeText={setQuery}
        autoFocus
      />
      <View style={{ gap: 12 }}>
        {data?.customers
          .filter((c) => match(`${c.name} ${c.address}`))
          .map((c) => (
            <Card key={c.id}>
              <MenuItem
                title={c.name}
                subtitle={c.address}
                icon="users"
                onPress={() => nav.navigate("Customer", { id: c.id })}
              />
            </Card>
          ))}
        {data?.orders
          .filter((o) =>
            match(
              `${o.id} ${o.type} ${data.customers.find((c) => c.id === o.customerId)?.name}`,
            ),
          )
          .map((o) => (
            <OrderCard key={o.id} order={o} />
          ))}
      </View>
    </Page>
  );
}
