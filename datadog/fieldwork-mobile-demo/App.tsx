import React, { useEffect } from "react";
import { ActivityIndicator, Pressable, View } from "react-native";
import {
  NavigationContainer,
  DefaultTheme,
  createNavigationContainerRef,
} from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { AppProvider, useApp } from "./src/state";
import { StackParams, TabParams, useNav } from "./src/navigation";
import {
  Badge,
  Choices,
  colors,
  Icon,
  IconName,
  Row,
  Txt,
} from "./src/components/ui";
import { WelcomeScreen } from "./src/screens/Welcome";
import { HomeScreen } from "./src/screens/Home";
import { DispatchScreen, ScheduleScreen } from "./src/screens/Schedule";
import { NewOrderScreen, OrderScreen } from "./src/screens/Orders";
import { InspectionScreen, ShiftScreen } from "./src/screens/Shift";
import {
  CustomerScreen,
  CustomersScreen,
  FleetScreen,
  InvoicesScreen,
  SearchScreen,
} from "./src/screens/Office";
import { CommsScreen } from "./src/screens/Comms";
import {
  DiagnosticsScreen,
  MoreScreen,
  NotificationsScreen,
  QueueScreen,
} from "./src/screens/More";
import { telemetry } from "./src/telemetry";
import { TelemetryProvider } from "./src/telemetry/provider";

const Stack = createNativeStackNavigator<StackParams>();
const Tabs = createBottomTabNavigator<TabParams>();
const navRef = createNavigationContainerRef<StackParams>();
function trackView() {
  const route = navRef.getCurrentRoute();
  if (route) telemetry.view(route.key, route.name);
}
function Header() {
  const { office, workspace, setWorkspace, data, session, queue, sync } =
    useApp();
  const nav = useNav();
  const unread =
    data?.notifications.filter((n) => !n.readBy.includes(session!.user.id))
      .length || 0;
  return (
    <SafeAreaView edges={["top"]} style={{ backgroundColor: colors.bg }}>
      <View
        style={{
          paddingHorizontal: 22,
          paddingTop: 12,
          paddingBottom: 12,
          gap: 12,
          borderBottomWidth: 1,
          borderColor: colors.line,
        }}
      >
        <Row style={{ gap: 8 }}>
          <View
            style={{
              height: 28,
              width: 28,
              borderRadius: 9,
              backgroundColor: colors.ink,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Txt
              style={{ color: colors.lime, fontWeight: "800", fontSize: 20 }}
            >
              f.
            </Txt>
          </View>
          <Txt style={{ fontSize: 19, fontWeight: "700", letterSpacing: -0.5 }}>
            fieldwork
            <Txt style={{ color: colors.muted, fontSize: 19 }}> one</Txt>
          </Txt>
          <View style={{ flex: 1 }} />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Search"
            style={{ padding: 10 }}
            onPress={() => nav.navigate("Search")}
          >
            <Icon name="search" />
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Notifications, ${unread} unread`}
            style={{ padding: 10 }}
            onPress={() => nav.navigate("Notifications")}
          >
            <Icon name="bell" />
            {unread > 0 && (
              <View
                style={{
                  position: "absolute",
                  right: 6,
                  top: 7,
                  width: 7,
                  height: 7,
                  borderRadius: 4,
                  backgroundColor: "#cb9d45",
                  borderWidth: 1,
                  borderColor: colors.bg,
                }}
              />
            )}
          </Pressable>
        </Row>
        <Row style={{ justifyContent: "space-between" }}>
          <Txt
            muted
            style={{ fontSize: 11, fontWeight: "600", letterSpacing: 0.4 }}
          >
            HARBOR ENVIRONMENTAL
          </Txt>
          <Badge text="RUM DEMO" tone="gray" />
        </Row>
        {office && (
          <Choices
            values={["office", "field"] as const}
            value={workspace}
            onChange={(value) => {
              setWorkspace(value);
              telemetry.action("Workspace changed", { workspace: value });
            }}
            labels={{ office: "Office", field: "My field work" }}
          />
        )}
        {(queue.length > 0 || sync === "offline") && (
          <Pressable
            accessibilityRole="button"
            onPress={() => nav.navigate("Queue")}
          >
            <Txt style={{ color: colors.amber, fontSize: 12 }}>
              {queue.length
                ? `${queue.length} pending actions · Tap to review`
                : "Offline · Showing saved data"}
            </Txt>
          </Pressable>
        )}
      </View>
    </SafeAreaView>
  );
}
function MainTabs() {
  const { office } = useApp();
  const icons: Record<keyof TabParams, IconName> = {
    Home: "grid",
    Schedule: "calendar",
    Dispatch: "navigation",
    Comms: "message-circle",
    More: "menu",
  };
  return (
    <Tabs.Navigator
      screenOptions={({ route }) => ({
        header: () => <Header />,
        tabBarActiveTintColor: colors.green,
        tabBarAccessibilityLabel: route.name,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: "#fbfcf8",
          borderTopColor: colors.line,
          minHeight: 69,
          paddingTop: 8,
          paddingBottom: 8,
        },
        tabBarLabelStyle: { fontSize: 10, marginTop: 3, fontWeight: "600" },
        tabBarIcon: ({ color, focused }) => (
          <View
            style={{
              backgroundColor: focused ? "#e7eedc" : "transparent",
              width: 48,
              height: 29,
              borderRadius: 12,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Icon name={icons[route.name]} color={color} size={20} />
          </View>
        ),
      })}
    >
      <Tabs.Screen name="Home" component={HomeScreen} />
      <Tabs.Screen name="Schedule" component={ScheduleScreen} />
      {office && <Tabs.Screen name="Dispatch" component={DispatchScreen} />}
      <Tabs.Screen name="Comms" component={CommsScreen} />
      <Tabs.Screen name="More" component={MoreScreen} />
    </Tabs.Navigator>
  );
}
function Root() {
  const { booting, session, toast, office } = useApp();
  useEffect(() => {
    if (!booting && !session) telemetry.view("welcome", "Welcome");
  }, [booting, session]);
  if (booting)
    return (
      <View
        style={{
          flex: 1,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: colors.bg,
          gap: 14,
        }}
      >
        <ActivityIndicator color={colors.green} />
        <Txt muted>Opening your workspace…</Txt>
      </View>
    );
  return (
    <View style={{ flex: 1 }}>
      <StatusBar style="dark" />
      {session ? (
        <NavigationContainer
          ref={navRef}
          onReady={trackView}
          onStateChange={trackView}
          theme={{
            ...DefaultTheme,
            colors: {
              ...DefaultTheme.colors,
              primary: colors.green,
              background: colors.bg,
              card: colors.bg,
              text: colors.ink,
              border: colors.line,
            },
          }}
        >
          <Stack.Navigator
            screenOptions={{
              headerShadowVisible: false,
              headerBackTitle: "Back",
              headerTitleStyle: { fontSize: 16, fontWeight: "600" },
              contentStyle: { backgroundColor: colors.bg },
            }}
          >
            <Stack.Screen
              name="Main"
              component={MainTabs}
              options={{ headerShown: false }}
            />
            <Stack.Screen
              name="Order"
              component={OrderScreen}
              options={{ title: "Job details" }}
            />
            {office && (
              <Stack.Screen
                name="NewOrder"
                component={NewOrderScreen}
                options={{ title: "New order" }}
              />
            )}
            <Stack.Screen
              name="Customers"
              component={CustomersScreen}
              options={{ title: "Customers" }}
            />
            <Stack.Screen
              name="Customer"
              component={CustomerScreen}
              options={{ title: "Customer & site" }}
            />
            {office && (
              <Stack.Screen
                name="Invoices"
                component={InvoicesScreen}
                options={{ title: "Invoices & payments" }}
              />
            )}
            <Stack.Screen
              name="Inspection"
              component={InspectionScreen}
              options={{ title: "Vehicle inspection" }}
            />
            <Stack.Screen
              name="Shift"
              component={ShiftScreen}
              options={{ title: "My shift" }}
            />
            <Stack.Screen
              name="Fleet"
              component={FleetScreen}
              options={{ title: "Fleet & shop" }}
            />
            <Stack.Screen
              name="Notifications"
              component={NotificationsScreen}
              options={{ title: "Inbox" }}
            />
            <Stack.Screen
              name="Diagnostics"
              component={DiagnosticsScreen}
              options={{ title: "Demo & observability" }}
            />
            <Stack.Screen
              name="Queue"
              component={QueueScreen}
              options={{ title: "Pending actions" }}
            />
            <Stack.Screen
              name="Search"
              component={SearchScreen}
              options={{ title: "Search" }}
            />
          </Stack.Navigator>
        </NavigationContainer>
      ) : (
        <WelcomeScreen />
      )}
      {toast && (
        <View
          pointerEvents="box-none"
          style={{
            position: "absolute",
            bottom: session ? 86 : 25,
            left: 18,
            right: 18,
            alignItems: "center",
          }}
        >
          <View
            accessibilityRole="alert"
            accessibilityLiveRegion="polite"
            style={{
              backgroundColor: toast.tone === "error" ? "#893b34" : colors.ink,
              padding: 16,
              borderRadius: 15,
              maxWidth: 550,
              shadowColor: "#000",
              shadowOffset: { width: 0, height: 4 },
              shadowOpacity: 0.15,
              shadowRadius: 10,
              elevation: 5,
            }}
          >
            <Txt style={{ color: colors.white, lineHeight: 21 }}>
              {toast.message}
            </Txt>
          </View>
        </View>
      )}
    </View>
  );
}
export default function App() {
  return (
    <TelemetryProvider>
      <SafeAreaProvider>
        <AppProvider>
          <Root />
        </AppProvider>
      </SafeAreaProvider>
    </TelemetryProvider>
  );
}
