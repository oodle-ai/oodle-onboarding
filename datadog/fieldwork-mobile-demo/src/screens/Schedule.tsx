import React, { useState } from "react";
import { Linking, View } from "react-native";
import * as Location from "expo-location";
import { useApp } from "../state";
import { useNav } from "../navigation";
import { today } from "../shared/model";
import {
  Button,
  Card,
  Choices,
  colors,
  Empty,
  Field,
  Heading,
  OrderCard,
  Page,
  Row,
  Txt,
} from "../components/ui";
import { RouteArt } from "../components/illustrations";
import { telemetry } from "../telemetry";

export function ScheduleScreen() {
  const { data, session, workspace, notify } = useApp();
  const [date, setDate] = useState(today());
  const [filter, setFilter] = useState("all");
  const orders =
    data?.orders.filter(
      (o) =>
        o.date === date &&
        (workspace === "office" || o.driverId === session?.user.id) &&
        (filter === "all" ||
          (filter === "remaining"
            ? o.status !== "completed"
            : o.status === filter)),
    ) || [];
  return (
    <Page>
      <Heading
        title="Your schedule"
        subtitle="One stop at a time. Every detail in reach."
      />
      <Field
        title="Service date · YYYY-MM-DD"
        value={date}
        onChangeText={setDate}
      />
      <Card style={{ padding: 12 }}>
        <RouteArt />
        <Row style={{ padding: 8, justifyContent: "space-between" }}>
          <View>
            <Txt style={{ fontWeight: "700" }}>
              {orders.length} stops on the board
            </Txt>
            <Txt muted style={{ fontSize: 11, marginTop: 4 }}>
              Illustrated route · open a stop for directions
            </Txt>
          </View>
        </Row>
        <Button
          title="Center on my location"
          variant="ghost"
          small
          icon="crosshair"
          onPress={async () => {
            const p = await Location.requestForegroundPermissionsAsync();
            if (p.status !== "granted") {
              notify(
                "Location access is off. You can still open each site in maps.",
              );
              return;
            }
            const pos = await Location.getCurrentPositionAsync({
              accuracy: Location.Accuracy.Balanced,
            });
            telemetry.action("Center map");
            await Linking.openURL(
              `https://www.google.com/maps/search/?api=1&query=${pos.coords.latitude},${pos.coords.longitude}`,
            );
          }}
        />
      </Card>
      <Choices
        values={["all", "remaining", "completed"]}
        value={filter}
        onChange={setFilter}
      />
      <View style={{ gap: 12 }}>
        {orders.length ? (
          orders.map((o, i) => <OrderCard key={o.id} order={o} index={i} />)
        ) : (
          <Empty
            title="No stops in this view"
            detail="Try another date or filter."
          />
        )}
      </View>
    </Page>
  );
}

export function DispatchScreen() {
  const { data, run, notify } = useApp();
  const nav = useNav();
  const [selected, setSelected] = useState("");
  const [position, setPosition] = useState("end");
  if (!data) return null;
  return (
    <Page>
      <Heading
        title="Dispatch board"
        subtitle="The right job. The right truck. A clear plan."
      />
      <Button
        title="New order"
        icon="plus"
        onPress={() => nav.navigate("NewOrder")}
      />
      <View>
        <Heading
          title="Needs a route"
          subtitle="Choose an order, then place it on a route."
        />
        <Choices
          values={data.orders
            .filter(
              (o) => o.status === "unassigned" || o.status === "scheduled",
            )
            .map((o) => o.id)}
          value={selected}
          onChange={setSelected}
        />
        {!data.orders.some(
          (o) => o.status === "unassigned" || o.status === "scheduled",
        ) && (
          <Empty
            title="All jobs are moving"
            detail="New orders will appear here."
          />
        )}
        <View style={{ height: 12 }} />
        <Choices
          values={["end", "first"]}
          value={position}
          onChange={setPosition}
          labels={{ end: "At end of route", first: "First stop" }}
        />
      </View>
      {data.routes.map((route) => (
        <Card key={route.id} style={{ gap: 15 }}>
          <Row style={{ justifyContent: "space-between" }}>
            <View>
              <Txt style={{ fontWeight: "700", fontSize: 19 }}>
                {route.name}
              </Txt>
              <Txt muted style={{ marginTop: 5 }}>
                {data.users.find((u) => u.id === route.driverId)?.name} ·{" "}
                {data.vehicles.find((v) => v.id === route.vehicleId)?.name}
              </Txt>
            </View>
            <View
              style={{
                width: 12,
                height: 12,
                borderRadius: 6,
                backgroundColor: route.color,
              }}
            />
          </Row>
          {route.orderIds.map((id, i) => {
            const order = data.orders.find((o) => o.id === id);
            return order ? (
              <OrderCard key={id} order={order} index={i} />
            ) : null;
          })}
          <Button
            title={selected ? `Assign ${selected}` : "Select an order above"}
            disabled={!selected}
            variant="secondary"
            icon="corner-down-right"
            onPress={async () => {
              await run({
                type: "order.assign",
                orderId: selected,
                routeId: route.id,
                ...(position === "first" ? { position: 0 } : {}),
              });
              notify("Route assignment saved.", "success");
              setSelected("");
            }}
          />
        </Card>
      ))}
      <View>
        <Heading title="Needs attention" />
        {data.orders
          .filter((o) => o.status === "blocked")
          .map((o) => (
            <OrderCard key={o.id} order={o} />
          ))}
        {!data.orders.some((o) => o.status === "blocked") && (
          <Txt muted>No blocked jobs. The routes are clear.</Txt>
        )}
      </View>
    </Page>
  );
}
