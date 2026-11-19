import React, { PropsWithChildren, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleProp,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  TextStyle,
  View,
  ViewStyle,
} from "react-native";
import Feather from "@expo/vector-icons/Feather";
import { useApp } from "../state";
import { label, Order } from "../shared/model";
import { useNav } from "../navigation";

export const colors = {
  ink: "#183e34",
  muted: "#698077",
  green: "#205b46",
  lime: "#d4ef91",
  bg: "#f3f6ef",
  white: "#ffffff",
  line: "#dde5da",
  pale: "#e6eddf",
  amber: "#896021",
  red: "#a33c36",
  blue: "#3c6590",
};
export type IconName = React.ComponentProps<typeof Feather>["name"];
export function Icon({
  name,
  color = colors.ink,
  size = 20,
}: {
  name: IconName;
  color?: string;
  size?: number;
}) {
  return (
    <Feather
      name={name}
      size={size}
      color={color}
      accessible={false}
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    />
  );
}
export function Txt({
  children,
  style,
  muted,
}: PropsWithChildren<{ style?: StyleProp<TextStyle>; muted?: boolean }>) {
  return (
    <Text style={[s.text, muted && { color: colors.muted }, style]}>
      {children}
    </Text>
  );
}
export function Row({
  children,
  style,
}: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) {
  return <View style={[s.row, style]}>{children}</View>;
}
export function Card({
  children,
  style,
}: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) {
  return <View style={[s.card, style]}>{children}</View>;
}
export function Heading({
  title,
  subtitle,
  action,
  onPress,
}: {
  title: string;
  subtitle?: string;
  action?: string;
  onPress?: () => void;
}) {
  return (
    <Row
      style={{
        justifyContent: "space-between",
        marginBottom: 16,
        alignItems: "flex-start",
      }}
    >
      <View style={{ flex: 1 }}>
        <Txt style={s.heading}>{title}</Txt>
        {subtitle && (
          <Txt muted style={{ marginTop: 5, lineHeight: 20 }}>
            {subtitle}
          </Txt>
        )}
      </View>
      {action && (
        <Pressable accessibilityRole="button" onPress={onPress} style={s.link}>
          <Txt style={{ color: colors.green, fontWeight: "700" }}>
            {action} →
          </Txt>
        </Pressable>
      )}
    </Row>
  );
}
export function Button({
  title,
  onPress,
  icon,
  variant = "primary",
  disabled,
  small,
  style,
}: {
  title: string;
  onPress: () => void | Promise<unknown>;
  icon?: IconName;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  disabled?: boolean;
  small?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const [busy, setBusy] = useState(false);
  const { notify } = useApp();
  const foreground =
    variant === "primary"
      ? colors.white
      : variant === "danger"
        ? colors.red
        : colors.ink;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={async () => {
        setBusy(true);
        try {
          await onPress();
        } catch (e) {
          notify(
            e instanceof Error ? e.message : "The action failed. Try again.",
            "error",
          );
        } finally {
          setBusy(false);
        }
      }}
      style={({ pressed }) => [
        s.button,
        {
          backgroundColor:
            variant === "primary"
              ? colors.green
              : variant === "danger"
                ? "#f9e7e1"
                : variant === "secondary"
                  ? colors.pale
                  : "transparent",
          minHeight: small ? 44 : 50,
          paddingHorizontal: small ? 14 : 18,
          opacity: disabled || busy ? 0.5 : 1,
          transform: [{ scale: pressed ? 0.97 : 1 }],
        },
        style,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={foreground} size="small" />
      ) : icon ? (
        <Icon name={icon} size={small ? 17 : 19} color={foreground} />
      ) : null}
      <Txt
        style={{
          fontSize: small ? 13 : 15,
          fontWeight: "700",
          color: foreground,
        }}
      >
        {title}
      </Txt>
    </Pressable>
  );
}
export function Field({ title, ...props }: TextInputProps & { title: string }) {
  return (
    <View style={{ gap: 7 }}>
      <Txt style={s.label}>{title}</Txt>
      <TextInput
        accessibilityLabel={title}
        placeholderTextColor="#8d9b91"
        {...props}
        style={[
          s.input,
          props.multiline && { height: 90, textAlignVertical: "top" },
          props.style,
        ]}
      />
    </View>
  );
}
export function Choices<T extends string>({
  values,
  value,
  onChange,
  labels,
}: {
  values: readonly T[];
  value: T;
  onChange: (v: T) => void;
  labels?: Partial<Record<T, string>>;
}) {
  return (
    <Row style={{ flexWrap: "wrap", gap: 8 }}>
      {values.map((v) => (
        <Pressable
          key={v}
          accessibilityRole="button"
          accessibilityState={{ selected: value === v }}
          onPress={() => onChange(v)}
          style={[
            s.chip,
            value === v && {
              backgroundColor: colors.ink,
              borderColor: colors.ink,
            },
          ]}
        >
          <Txt
            style={{
              fontSize: 13,
              color: value === v ? colors.white : colors.ink,
              fontWeight: "600",
            }}
          >
            {labels?.[v] || label(v)}
          </Txt>
        </Pressable>
      ))}
    </Row>
  );
}
export function Badge({
  text,
  tone = "green",
}: {
  text: string;
  tone?: "green" | "amber" | "red" | "gray" | "blue";
}) {
  const tones = {
    green: ["#e5efd7", "#426137"],
    amber: ["#f7edd5", "#896021"],
    red: ["#f8e3df", "#a33c36"],
    gray: ["#eaf0e7", "#698077"],
    blue: ["#e6eef9", "#3c6590"],
  };
  return (
    <View style={[s.badge, { backgroundColor: tones[tone][0] }]}>
      <Txt
        style={{
          color: tones[tone][1],
          fontWeight: "700",
          fontSize: 11,
          letterSpacing: 0.3,
        }}
      >
        {text}
      </Txt>
    </View>
  );
}
export function Status({ status }: { status: Order["status"] }) {
  return (
    <Badge
      text={label(status)}
      tone={
        status === "blocked"
          ? "red"
          : status === "in_progress"
            ? "blue"
            : status === "unassigned"
              ? "amber"
              : status === "completed"
                ? "green"
                : "gray"
      }
    />
  );
}
export function Empty({
  title,
  detail,
  icon = "inbox",
}: {
  title: string;
  detail: string;
  icon?: IconName;
}) {
  return (
    <Card style={{ alignItems: "center", paddingVertical: 35, gap: 12 }}>
      <Icon name={icon} size={28} color={colors.muted} />
      <Txt style={{ fontWeight: "700", fontSize: 17 }}>{title}</Txt>
      <Txt muted style={{ textAlign: "center", lineHeight: 22 }}>
        {detail}
      </Txt>
    </Card>
  );
}
export function Page({
  children,
  refresh = true,
}: PropsWithChildren<{ refresh?: boolean }>) {
  const app = useApp();
  const [loading, setLoading] = useState(false);
  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={s.page}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        refresh ? (
          <RefreshControl
            tintColor={colors.green}
            refreshing={loading}
            onRefresh={async () => {
              setLoading(true);
              await app.flush();
              setLoading(false);
            }}
          />
        ) : undefined
      }
    >
      <View
        style={{ width: "100%", maxWidth: 850, alignSelf: "center", gap: 22 }}
      >
        {children}
      </View>
    </ScrollView>
  );
}
export function OrderCard({ order, index }: { order: Order; index?: number }) {
  const { data } = useApp();
  const nav = useNav();
  const customer = data?.customers.find((c) => c.id === order.customerId);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Open ${order.id}, ${customer?.name}, ${label(order.type)}`}
      onPress={() => nav.navigate("Order", { id: order.id })}
      style={({ pressed }) => [s.card, { gap: 14, opacity: pressed ? 0.8 : 1 }]}
    >
      <Row style={{ justifyContent: "space-between" }}>
        <Row style={{ gap: 8 }}>
          <View style={s.number}>
            <Txt style={{ fontWeight: "700", fontSize: 13 }}>
              {index !== undefined ? (
                String(index + 1).padStart(2, "0")
              ) : (
                <Icon
                  name={
                    order.type === "delivery" ? "arrow-down-left" : "repeat"
                  }
                  size={17}
                />
              )}
            </Txt>
          </View>
          <Txt muted style={{ fontSize: 12 }}>
            {order.id} · {order.window}
          </Txt>
        </Row>
        <Status status={order.status} />
      </Row>
      <View>
        <Txt style={{ fontSize: 18, fontWeight: "700", letterSpacing: -0.3 }}>
          {customer?.name || "Customer"}
        </Txt>
        <Txt muted style={{ marginTop: 6, fontSize: 13 }}>
          {customer?.address}
        </Txt>
      </View>
      <Row
        style={{
          borderTopWidth: 1,
          borderColor: colors.line,
          paddingTop: 12,
          justifyContent: "space-between",
        }}
      >
        <Row style={{ gap: 8 }}>
          <Icon name="box" size={16} color={colors.muted} />
          <Txt style={{ fontSize: 13 }}>
            {order.size} · {label(order.type)}
          </Txt>
          {order.priority === "urgent" && <Badge text="Urgent" tone="amber" />}
        </Row>
        <Icon name="arrow-up-right" size={18} />
      </Row>
    </Pressable>
  );
}
export function MenuItem({
  title,
  subtitle,
  icon,
  onPress,
  trailing,
}: {
  title: string;
  subtitle?: string;
  icon: IconName;
  onPress: () => void;
  trailing?: React.ReactNode;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      accessibilityLabel={title}
      accessibilityHint={subtitle}
      style={({ pressed }) => [s.menu, { opacity: pressed ? 0.6 : 1 }]}
    >
      <View style={s.menuIcon}>
        <Icon name={icon} />
      </View>
      <View style={{ flex: 1, gap: 5 }}>
        <Txt style={{ fontWeight: "600" }}>{title}</Txt>
        {subtitle && (
          <Txt muted style={{ fontSize: 12 }}>
            {subtitle}
          </Txt>
        )}
      </View>
      {trailing || <Icon name="chevron-right" color={colors.muted} size={18} />}
    </Pressable>
  );
}
export const s = StyleSheet.create({
  text: {
    fontSize: 14,
    color: colors.ink,
    fontFamily: Platform.OS === "ios" ? "System" : undefined,
  },
  row: { flexDirection: "row", alignItems: "center" },
  page: { padding: 22, paddingBottom: 32 },
  card: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 20,
    padding: 18,
  },
  heading: { fontSize: 22, fontWeight: "700", letterSpacing: -0.6 },
  label: {
    fontSize: 12,
    fontWeight: "700",
    color: colors.muted,
    letterSpacing: 0.4,
  },
  input: {
    minHeight: 50,
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 12,
    backgroundColor: colors.white,
    padding: 14,
    color: colors.ink,
    fontSize: 15,
  },
  button: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 9,
    borderRadius: 13,
  },
  chip: {
    minHeight: 42,
    paddingHorizontal: 15,
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.line,
    borderRadius: 30,
    backgroundColor: colors.white,
  },
  badge: { paddingHorizontal: 9, paddingVertical: 5, borderRadius: 7 },
  link: { paddingLeft: 12, minHeight: 36, justifyContent: "center" },
  number: {
    width: 28,
    height: 28,
    borderRadius: 9,
    backgroundColor: colors.bg,
    alignItems: "center",
    justifyContent: "center",
  },
  menu: {
    flexDirection: "row",
    gap: 14,
    alignItems: "center",
    paddingVertical: 15,
    borderBottomWidth: 1,
    borderColor: colors.line,
  },
  menuIcon: {
    width: 43,
    height: 43,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.pale,
  },
});
