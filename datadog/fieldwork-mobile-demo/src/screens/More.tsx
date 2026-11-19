import React, { useState } from "react";
import { Platform, Switch, View } from "react-native";
import { useApp } from "../state";
import { useNav } from "../navigation";
import { apiUrl } from "../config";
import { client } from "../api";
import { telemetry } from "../telemetry";
import { label } from "../shared/model";
import {
  Badge,
  Button,
  Card,
  colors,
  Empty,
  Heading,
  Icon,
  MenuItem,
  Page,
  Row,
  Txt,
} from "../components/ui";

export function MoreScreen() {
  const { session, office, queue, logout } = useApp();
  const nav = useNav();
  return (
    <Page>
      <Heading title="Everything in its place." />
      <Card>
        <Row style={{ gap: 15, marginBottom: 14 }}>
          <View
            style={{
              backgroundColor: colors.lime,
              width: 52,
              height: 52,
              borderRadius: 18,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Txt style={{ fontWeight: "800", fontSize: 20 }}>
              {session?.user.initials}
            </Txt>
          </View>
          <View>
            <Txt style={{ fontWeight: "700", fontSize: 18 }}>
              {session?.user.name}
            </Txt>
            <Txt muted style={{ marginTop: 5 }}>
              {label(session?.user.role || "")} · Demo profile
            </Txt>
          </View>
        </Row>
        <MenuItem
          title="Search"
          subtitle="Find orders, customers, and sites"
          icon="search"
          onPress={() => nav.navigate("Search")}
        />
        <MenuItem
          title="Customers & sites"
          subtitle="Contact details and service history"
          icon="users"
          onPress={() => nav.navigate("Customers")}
        />
        {office && (
          <MenuItem
            title="Invoices & payments"
            subtitle="Billing and simulated payment records"
            icon="credit-card"
            onPress={() => nav.navigate("Invoices")}
          />
        )}
        <MenuItem
          title="Fleet & shop"
          subtitle="Trucks, containers, and maintenance"
          icon="truck"
          onPress={() => nav.navigate("Fleet")}
        />
        <MenuItem
          title="Time & shifts"
          subtitle="Inspection, clock-in, breaks, and end of day"
          icon="clock"
          onPress={() => nav.navigate("Shift")}
        />
        <MenuItem
          title="Notification inbox"
          subtitle="Updates from the field and office"
          icon="bell"
          onPress={() => nav.navigate("Notifications")}
        />
      </Card>
      <Card>
        <MenuItem
          title="Pending actions"
          subtitle={`${queue.length} actions stored on this device`}
          icon="refresh-cw"
          onPress={() => nav.navigate("Queue")}
        />
        <MenuItem
          title="Demo & observability"
          subtitle="Connection, consent, RUM, and Session Replay"
          icon="activity"
          onPress={() => nav.navigate("Diagnostics")}
        />
      </Card>
      <Button
        title="Switch profile / sign out"
        variant="ghost"
        icon="log-out"
        onPress={logout}
      />
      <Txt muted style={{ textAlign: "center", fontSize: 11 }}>
        Fieldwork One · Sample application · v1.0.0{"\n"}All customers, orders,
        and payments are fictional.
      </Txt>
    </Page>
  );
}
export function QueueScreen() {
  const { queue, flush, discard, offline, setOffline } = useApp();
  const [confirm, setConfirm] = useState("");
  return (
    <Page>
      <Heading
        title="Work that waits for signal."
        subtitle="Actions are saved in order. The server validates each action when the connection returns."
      />
      <Card>
        <Toggle
          title="Simulate offline mode"
          value={offline}
          onChange={setOffline}
        />
        <Txt muted style={{ lineHeight: 21, marginTop: 10 }}>
          The app shows the last server state until actions sync. A rejected
          action pauses the queue so you can review it.
        </Txt>
      </Card>
      <Button
        title="Sync pending actions"
        disabled={offline || !queue.length}
        icon="refresh-cw"
        onPress={flush}
      />
      {queue.map((q) => (
        <Card key={q.requestId} style={{ gap: 12 }}>
          <Row style={{ justifyContent: "space-between" }}>
            <Txt style={{ fontWeight: "700" }}>
              {label(q.command.type.replaceAll(".", " "))}
            </Txt>
            <Badge
              text={q.error ? "Needs review" : "Pending"}
              tone={q.error ? "red" : "amber"}
            />
          </Row>
          <Txt muted>{new Date(q.createdAt).toLocaleString()}</Txt>
          {"orderId" in q.command && <Txt>{q.command.orderId}</Txt>}
          {q.error && <Txt style={{ color: colors.red }}>{q.error}</Txt>}
          <Button
            title={
              confirm === q.requestId
                ? "Confirm discard action"
                : "Discard this action"
            }
            variant="danger"
            small
            onPress={async () => {
              if (confirm === q.requestId) {
                await discard(q.requestId);
                setConfirm("");
              } else setConfirm(q.requestId);
            }}
          />
        </Card>
      ))}
      {!queue.length && (
        <Empty
          title="Everything is up to date"
          detail="Actions saved while offline will appear here."
          icon="check-circle"
        />
      )}
    </Page>
  );
}
function Toggle({
  title,
  value,
  onChange,
}: {
  title: string;
  value: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <Row style={{ justifyContent: "space-between", gap: 15, minHeight: 48 }}>
      <Txt style={{ flex: 1, fontWeight: "600" }}>{title}</Txt>
      <Switch
        accessibilityLabel={title}
        value={value}
        onValueChange={onChange}
        trackColor={{ false: "#c4cfc0", true: colors.green }}
        thumbColor={colors.white}
      />
    </Row>
  );
}
export function DiagnosticsScreen() {
  const {
    session,
    telemetryStatus,
    consent,
    setConsent,
    offline,
    setOffline,
    notify,
    sync,
    replay,
    setReplay,
  } = useApp();
  const [sessionId, setSessionId] = useState("");
  const [probe, setProbe] = useState("");
  return (
    <Page>
      <Heading
        title="See the whole journey."
        subtitle="Use these controls to create a small, repeatable observability demo."
      />
      <Card style={{ gap: 13 }}>
        <Row style={{ gap: 10 }}>
          <Icon name="activity" />
          <Txt style={{ fontWeight: "700" }}>Datadog RUM + Session Replay</Txt>
        </Row>
        <Badge text={telemetryStatus} tone="blue" />
        <Txt muted style={{ lineHeight: 21 }}>
          Screen views, interactions, requests, errors, and workflow operations
          are instrumented. Native replay requires a development or installed
          build with credentials.
        </Txt>
        <Toggle
          title="Allow telemetry collection"
          value={consent}
          onChange={(v) => {
            void setConsent(v).catch((e) => notify(String(e), "error"));
          }}
        />
        <Toggle
          title="Record session replay"
          value={replay && consent}
          onChange={(v) => {
            if (!consent && v) {
              notify("Enable telemetry consent first.");
              return;
            }
            void setReplay(v).catch((e) => notify(String(e), "error"));
          }}
        />
        <Txt muted style={{ fontSize: 12, lineHeight: 19 }}>
          Inputs and evidence images are masked in native replay. Collection
          stays disabled until the environment contains Datadog credentials.
        </Txt>
        <Button
          title="Get current RUM session ID"
          variant="secondary"
          small
          onPress={async () =>
            setSessionId(
              (await telemetry.sessionId()) ||
                "No RUM session. Configure credentials and allow collection.",
            )
          }
        />
        {sessionId && <Txt style={{ fontSize: 12 }}>{sessionId}</Txt>}
      </Card>
      <Card style={{ gap: 14 }}>
        <Heading
          title="Request scenarios"
          subtitle="Slow and failed requests require ENABLE_DEMO_SCENARIOS=true on the API."
        />
        {(["healthy", "slow", "error"] as const).map((scenario) => (
          <Button
            key={scenario}
            title={`${label(scenario)} API request`}
            icon={scenario === "error" ? "alert-circle" : "zap"}
            variant="secondary"
            onPress={async () => {
              if (!session) return;
              const start = Date.now();
              try {
                await client(session.token).diagnostics.probe.query({
                  scenario,
                });
                setProbe(
                  `${label(scenario)} request completed in ${Date.now() - start} ms.`,
                );
              } catch (e) {
                telemetry.error(e, { "demo.scenario": scenario });
                setProbe(e instanceof Error ? e.message : "Request failed.");
              }
            }}
          />
        ))}
        <Button
          title="Capture a handled JavaScript error"
          variant="ghost"
          small
          onPress={() => {
            telemetry.error(new Error("Demo: photo processing failed"), {
              "demo.scenario": "handled_error",
            });
            notify("Handled error submitted when telemetry is enabled.");
          }}
        />
        {probe && <Txt style={{ lineHeight: 21 }}>{probe}</Txt>}
      </Card>
      <Card style={{ gap: 12 }}>
        <Heading title="Connection" />
        <Badge
          text={label(sync)}
          tone={sync === "online" ? "green" : "amber"}
        />
        <Txt muted style={{ fontSize: 12 }}>
          {apiUrl}
        </Txt>
        <Toggle
          title="Simulate offline mode"
          value={offline}
          onChange={setOffline}
        />
        <Txt muted style={{ fontSize: 12 }}>
          This switch stops workspace synchronization. It does not disable your
          device network or the Datadog SDK.
        </Txt>
      </Card>
    </Page>
  );
}
export function NotificationsScreen() {
  const { data, session, run, notify } = useApp();
  const localNotification = async () => {
    if (Platform.OS === "web") {
      notify(
        "Local device notifications are available in the iOS and Android builds.",
      );
      return;
    }
    const Notifications = await import("expo-notifications");
    if (Platform.OS === "android")
      await Notifications.setNotificationChannelAsync("demo", {
        name: "Demo updates",
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    const permission = await Notifications.requestPermissionsAsync();
    if (permission.status !== "granted") {
      notify("Notification access is off. The in-app inbox still works.");
      return;
    }
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: false,
        shouldSetBadge: false,
      }),
    });
    await Notifications.scheduleNotificationAsync({
      content: {
        title: "Your route is ready",
        body: "A demo notification from Fieldwork One.",
        data: { screen: "Schedule" },
      },
      trigger: null,
    });
    notify("Local demo notification scheduled.", "success");
  };
  return (
    <Page>
      <Heading
        title="Stay in the loop."
        subtitle="Route changes, messages, and updates from your crew."
      />
      <Button
        title="Test a device notification"
        icon="bell"
        variant="secondary"
        onPress={localNotification}
      />
      <Button
        title="Register device for demo push"
        variant="ghost"
        small
        onPress={async () => {
          if (Platform.OS === "web") {
            notify(
              "Use an iOS or Android development build on a physical device.",
            );
            return;
          }
          if (process.env.EXPO_PUBLIC_NATIVE_PUSH_ENABLED !== "true") {
            notify(
              "Native push is optional. Configure APNs or FCM, enable native push in .env, and rebuild first.",
            );
            return;
          }
          const Notifications = await import("expo-notifications");
          if (Platform.OS === "android")
            await Notifications.setNotificationChannelAsync("demo", {
              name: "Demo updates",
              importance: Notifications.AndroidImportance.DEFAULT,
            });
          const permission = await Notifications.requestPermissionsAsync();
          if (permission.status !== "granted") {
            notify("Allow notifications before you register this device.");
            return;
          }
          const token = await Notifications.getDevicePushTokenAsync();
          await run({
            type: "device.register",
            token: token.data,
            platform: Platform.OS as "ios" | "android",
          });
          notify(
            "Device registered in the demo API. The sample does not send remote push messages.",
            "success",
          );
        }}
      />
      {data?.notifications.map((n) => (
        <Card
          key={n.id}
          style={{
            gap: 10,
            borderLeftWidth: 3,
            borderLeftColor: n.readBy.includes(session!.user.id)
              ? colors.line
              : colors.green,
          }}
        >
          <Txt style={{ fontWeight: "700", fontSize: 17 }}>{n.title}</Txt>
          <Txt muted style={{ lineHeight: 21 }}>
            {n.body}
          </Txt>
          <Txt muted style={{ fontSize: 11 }}>
            {new Date(n.createdAt).toLocaleString()}
          </Txt>
          {!n.readBy.includes(session!.user.id) && (
            <Button
              title="Mark as read"
              variant="ghost"
              small
              onPress={() =>
                run({ type: "notification.read", notificationId: n.id })
              }
            />
          )}
        </Card>
      ))}
    </Page>
  );
}
