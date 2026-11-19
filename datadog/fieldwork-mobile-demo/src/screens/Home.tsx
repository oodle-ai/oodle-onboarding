import React, { useEffect, useState } from "react";
import { View } from "react-native";
import { useApp } from "../state";
import { useNav } from "../navigation";
import { activeShift, isOnBreak, money, today } from "../shared/model";
import {
  Badge,
  Button,
  Card,
  colors,
  Empty,
  Heading,
  Icon,
  MenuItem,
  OrderCard,
  Page,
  Row,
  Txt,
} from "../components/ui";
import { TruckArt } from "../components/illustrations";
import { timedFetch } from "../api";
import { apiUrl } from "../config";

export function HomeScreen() {
  const { data, session, office, workspace, offline } = useApp();
  const nav = useNav();
  const [report, setReport] = useState<{
    outstandingCents: number;
    revenueCents: number;
  } | null>(null);
  useEffect(() => {
    let active = true;
    if (office && session && !offline)
      void timedFetch(`${apiUrl}/api/report`, {
        headers: { Authorization: `Bearer ${session.token}` },
      })
        .then(async (response) => {
          if (response.ok && active) setReport(await response.json());
        })
        .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [office, session, offline, data?.revision]);
  if (!data || !session)
    return (
      <Page>
        <Empty
          title="Connecting to your workspace"
          detail="Start the demo API, then pull down to try again."
          icon="wifi"
        />
      </Page>
    );
  const field = workspace === "field";
  const shift = activeShift(data.shifts, session.user.id);
  const orders = data.orders.filter(
    (o) => o.date === today() && (!field || o.driverId === session.user.id),
  );
  const completed = orders.filter((o) => o.status === "completed").length;
  const next = orders
    .filter((o) => ["scheduled", "in_progress", "blocked"].includes(o.status))
    .slice(0, 2);
  return (
    <Page>
      <View>
        <Txt
          muted
          style={{ fontSize: 12, letterSpacing: 1, textTransform: "uppercase" }}
        >
          {new Date().toLocaleDateString("en-US", {
            weekday: "long",
            month: "short",
            day: "numeric",
          })}
        </Txt>
        <Txt
          style={{
            fontSize: 30,
            fontWeight: "700",
            letterSpacing: -1,
            marginTop: 8,
          }}
        >
          Hello, {session.user.name.split(" ")[0]}
          <Txt style={{ color: colors.muted, fontSize: 30 }}>.</Txt>
        </Txt>
        <Txt muted style={{ marginTop: 7 }}>
          {field
            ? "Try a driver journey with synthetic data."
            : "Try an office journey with synthetic data."}
        </Txt>
      </View>
      <Card
        style={{
          backgroundColor: colors.ink,
          borderColor: colors.ink,
          padding: 20,
          overflow: "hidden",
        }}
      >
        <Row>
          <View style={{ flex: 1 }}>
            <Badge
              text={
                field
                  ? shift
                    ? isOnBreak(shift)
                      ? "On break"
                      : "Shift active"
                    : "Ready when you are"
                  : "Operations overview"
              }
            />
            <Txt
              style={{
                color: colors.white,
                fontSize: 25,
                fontWeight: "600",
                letterSpacing: -0.8,
                marginTop: 16,
              }}
            >
              {field ? "Explore a\nsample route." : "Explore a\nsample order."}
            </Txt>
          </View>
          <TruckArt />
        </Row>
        <Button
          title={
            field
              ? shift
                ? "Manage my shift"
                : "Start my day"
              : "Create an order"
          }
          icon={field ? "sun" : "plus"}
          variant="secondary"
          style={{ marginTop: 18, backgroundColor: colors.lime }}
          onPress={() => nav.navigate(field ? "Shift" : "NewOrder")}
        />
      </Card>
      <Row style={{ gap: 12 }}>
        <Metric
          value={`${completed}/${orders.length}`}
          title="Stops complete"
          icon="check-circle"
        />
        <Metric
          value={String(
            field
              ? orders.filter((o) => o.status !== "completed").length
              : data.orders.filter((o) => o.status === "unassigned").length,
          )}
          title={field ? "Stops remaining" : "Need assignment"}
          icon="navigation"
        />
        <Metric
          value={
            field
              ? `${data.orders
                  .filter((o) => o.driverId === session.user.id)
                  .reduce((n, o) => n + (o.weightTons || 0), 0)
                  .toFixed(1)}t`
              : money(data.payments.reduce((n, p) => n + p.amountCents, 0))
          }
          title={field ? "Material moved" : "Collected"}
          icon={field ? "box" : "dollar-sign"}
        />
      </Row>
      <View>
        <Heading
          title={field ? "On your route" : "Keep things moving"}
          action={field ? "Schedule" : "Dispatch"}
          onPress={() =>
            nav.popTo("Main", { screen: field ? "Schedule" : "Dispatch" })
          }
        />
        <View style={{ gap: 12 }}>
          {next.length ? (
            next.map((o, i) => <OrderCard key={o.id} order={o} index={i} />)
          ) : (
            <Empty
              title={
                orders.length ? "All clear for today" : "No stops assigned"
              }
              detail={
                field
                  ? "Dispatch can add jobs to your route. Use the office workspace to assign them."
                  : "Create an order to plan the next stop."
              }
              icon="check-circle"
            />
          )}
        </View>
      </View>
      {office && report && (
        <Card style={{ gap: 10 }}>
          <Row style={{ justifyContent: "space-between" }}>
            <Txt muted>Open account balance</Txt>
            <Icon name="bar-chart-2" color={colors.muted} />
          </Row>
          <Txt style={{ fontSize: 28, fontWeight: "700" }}>
            {money(report.outstandingCents)}
          </Txt>
          <Txt muted style={{ fontSize: 12 }}>
            {money(report.revenueCents)} collected across the demo workspace
          </Txt>
        </Card>
      )}
      <Card>
        <Heading title="Your shortcuts" />
        <MenuItem
          title={office ? "Customers & sites" : "Truck & inspection"}
          subtitle={
            office
              ? "Contacts, site notes, and service history"
              : "A six-point check before every shift"
          }
          icon={office ? "users" : "truck"}
          onPress={() => nav.navigate(office ? "Customers" : "Inspection")}
        />
        <MenuItem
          title="Team huddle"
          subtitle="Keep the field and office connected"
          icon="message-circle"
          onPress={() => nav.popTo("Main", { screen: "Comms" })}
        />
        {office && (
          <MenuItem
            title="Invoices & payments"
            subtitle={`${data.invoices.filter((i) => i.status === "open").length} open · ${data.pendingJobs} jobs in the billing queue`}
            icon="file-text"
            onPress={() => nav.navigate("Invoices")}
          />
        )}
      </Card>
      <Row style={{ justifyContent: "center", gap: 6 }}>
        <Icon name="feather" size={13} color={colors.muted} />
        <Txt muted style={{ fontSize: 11 }}>
          Built for the people who keep the world moving.
        </Txt>
      </Row>
    </Page>
  );
}
function Metric({
  value,
  title,
  icon,
}: {
  value: string;
  title: string;
  icon: React.ComponentProps<typeof Icon>["name"];
}) {
  return (
    <Card style={{ flex: 1, padding: 12, gap: 9, minHeight: 116 }}>
      <Icon name={icon} color={colors.muted} size={17} />
      <Txt style={{ fontSize: 24, fontWeight: "700", letterSpacing: -0.8 }}>
        {value}
      </Txt>
      <Txt muted style={{ fontSize: 10 }}>
        {title}
      </Txt>
    </Card>
  );
}
