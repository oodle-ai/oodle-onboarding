import React, { useState } from "react";
import { Image, Linking, Platform, View } from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as Haptics from "expo-haptics";
import { NativeStackScreenProps } from "@react-navigation/native-stack";
import { StackParams, useNav } from "../navigation";
import { useApp } from "../state";
import {
  dumpSites,
  label,
  money,
  Order,
  PhotoKind,
  requiredPhotos,
  today,
} from "../shared/model";
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
  Page,
  Row,
  Status,
  Txt,
} from "../components/ui";
import { telemetry } from "../telemetry";
import { samplePhoto } from "../shared/sample-photo";

export function OrderScreen({
  route,
}: NativeStackScreenProps<StackParams, "Order">) {
  const { data, run, office, notify, queue } = useApp();
  const nav = useNav();
  const order = data?.orders.find((o) => o.id === route.params.id);
  const [asset, setAsset] = useState(order?.assetId || "");
  const [kind, setKind] = useState<PhotoKind>(
    order ? requiredPhotos(order.type)[0]! : "site",
  );
  const [weight, setWeight] = useState("");
  const [dumpSite, setDumpSite] = useState(dumpSites[0]!);
  const [note, setNote] = useState("");
  const [signature, setSignature] = useState("");
  const [issue, setIssue] = useState("");
  if (!order || !data)
    return (
      <Page>
        <Empty
          title="Order unavailable"
          detail="Refresh the workspace to load this order."
        />
      </Page>
    );
  const customer = data.customers.find((c) => c.id === order.customerId)!;
  const active = order.status === "in_progress";
  const needed = requiredPhotos(order.type);
  const invoice = data.invoices.find((i) => i.orderId === order.id);
  const upload = async (base64: string) => {
    telemetry.action("Photo upload size observed", {
      bytes: Math.floor(base64.length * 0.75),
      photo_kind: kind,
    });
    const result = await run({
      type: "order.photo",
      orderId: order.id,
      kind,
      base64,
    });
    if (!result.queued) {
      telemetry.action("Photo upload complete", { photo_kind: kind });
      notify("Evidence photo uploaded.", "success");
    }
  };
  const pick = async (camera: boolean) => {
    const permission = camera
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      notify(
        "Photo access is off. Use the sample evidence or enable access in device settings.",
      );
      return;
    }
    telemetry.action(camera ? "Take photo" : "Open photo library");
    const options: ImagePicker.ImagePickerOptions = {
      mediaTypes: ["images"],
      base64: true,
      quality: 0.45,
      allowsEditing: true,
      aspect: [4, 3],
    };
    const result = camera
      ? await ImagePicker.launchCameraAsync(options)
      : await ImagePicker.launchImageLibraryAsync(options);
    if (!result.canceled) {
      const picked = result.assets[0];
      if (!picked?.base64)
        throw new Error("The image has no data. Select another JPEG photo.");
      await upload(picked.base64);
    }
  };
  return (
    <Page>
      <Row style={{ justifyContent: "space-between" }}>
        <Txt muted style={{ fontWeight: "700", letterSpacing: 1 }}>
          {order.id}
        </Txt>
        <Status status={order.status} />
      </Row>
      <View>
        <Txt style={{ fontSize: 29, fontWeight: "700", letterSpacing: -0.8 }}>
          {customer.name}
        </Txt>
        <Txt muted style={{ marginTop: 8, lineHeight: 22 }}>
          {customer.address}
        </Txt>
      </View>
      <Row style={{ gap: 8, flexWrap: "wrap" }}>
        <Badge text={`${order.size} container`} />
        <Badge text={label(order.type)} tone="blue" />
        <Badge text={order.date} tone="gray" />
      </Row>
      <Card style={{ gap: 13 }}>
        <Row style={{ justifyContent: "space-between" }}>
          <Txt style={{ fontWeight: "700" }}>Site briefing</Txt>
          <Icon name="map-pin" />
        </Row>
        <Txt style={{ lineHeight: 22 }}>
          {order.notes ||
            customer.notes ||
            "No special instructions for this site."}
        </Txt>
        <Row style={{ gap: 10 }}>
          <Button
            title="Directions"
            icon="navigation"
            variant="secondary"
            small
            style={{ flex: 1 }}
            onPress={async () => {
              telemetry.action("Show site location in maps");
              await Linking.openURL(
                `https://www.google.com/maps/search/?api=1&query=${customer.lat},${customer.lng}`,
              );
            }}
          />
          <Button
            title="Site details"
            variant="ghost"
            small
            onPress={() => nav.navigate("Customer", { id: customer.id })}
          />
        </Row>
      </Card>
      {queue.some(
        (q) => "orderId" in q.command && q.command.orderId === order.id,
      ) && (
        <Card style={{ backgroundColor: "#fff4dd" }}>
          <Txt>
            Some actions are waiting to sync. This screen shows the last
            confirmed server state.
          </Txt>
          <Button
            title="Review pending actions"
            small
            variant="ghost"
            onPress={() => nav.navigate("Queue")}
          />
        </Card>
      )}
      {order.status === "scheduled" && (
        <Card style={{ gap: 14 }}>
          <Heading
            title="Ready for this stop?"
            subtitle="Complete your vehicle inspection and clock in before you start."
          />
          <Button
            title="Start job"
            icon="play"
            onPress={async () => {
              const result = await run({
                type: "order.start",
                orderId: order.id,
              });
              if (!result.queued)
                notify("Job started. Confirm the container next.", "success");
            }}
          />
          <Button
            title="Open my shift"
            variant="ghost"
            small
            onPress={() => nav.navigate("Shift")}
          />
        </Card>
      )}
      {order.status === "unassigned" && (
        <Button
          title="Assign in dispatch"
          icon="navigation"
          onPress={() => nav.popTo("Main", { screen: "Dispatch" })}
        />
      )}
      {(active || order.status === "completed") && (
        <>
          <Card style={{ gap: 15 }}>
            <Step
              title="Confirm the container"
              index={1}
              complete={order.containerConfirmed}
            />
            <Txt muted>Check the container ID and size at the site.</Txt>
            {active && (
              <>
                <Choices
                  values={data.assets
                    .filter(
                      (a) =>
                        a.size === order.size && a.status !== "maintenance",
                    )
                    .map((a) => a.id)}
                  value={asset}
                  onChange={setAsset}
                />
                <Button
                  title={
                    order.containerConfirmed
                      ? "Update container"
                      : "Confirm container"
                  }
                  variant="secondary"
                  disabled={!asset}
                  onPress={() =>
                    run({
                      type: "order.confirm_container",
                      orderId: order.id,
                      assetId: asset,
                    })
                  }
                />
              </>
            )}
            {order.containerConfirmed && (
              <Txt style={{ fontWeight: "600" }}>
                {order.assetId} · Confirmed
              </Txt>
            )}
          </Card>
          <Card style={{ gap: 15 }}>
            <Step
              title="Add proof of service"
              index={2}
              complete={needed.every((k) =>
                order.photos.some((p) => p.kind === k),
              )}
            />
            <Txt muted>
              Required: {needed.map(label).join(" + ")}. JPEG only, up to 2 MiB
              each.
            </Txt>
            {active && (
              <>
                <Choices
                  values={
                    Array.from(
                      new Set([...needed, "site", "ticket"]),
                    ) as PhotoKind[]
                  }
                  value={kind}
                  onChange={setKind}
                />
                <Row style={{ gap: 8 }}>
                  <Button
                    title="Take photo"
                    icon="camera"
                    variant="secondary"
                    small
                    style={{ flex: 1 }}
                    onPress={() => pick(true)}
                  />
                  <Button
                    title="Photo library"
                    icon="image"
                    variant="secondary"
                    small
                    style={{ flex: 1 }}
                    onPress={() => pick(false)}
                  />
                </Row>
                <Button
                  title={`Use sample ${label(kind).toLowerCase()} photo`}
                  variant="ghost"
                  small
                  onPress={() => upload(samplePhoto)}
                />
              </>
            )}
            {order.photos.map((photo) => (
              <View key={photo.id} style={{ gap: 10 }}>
                <Image
                  accessibilityLabel={`${label(photo.kind)} evidence`}
                  source={{ uri: photo.uri }}
                  style={{
                    height: 175,
                    width: "100%",
                    borderRadius: 12,
                    backgroundColor: colors.pale,
                  }}
                  resizeMode="cover"
                />
                <Row style={{ justifyContent: "space-between" }}>
                  <Badge text={label(photo.kind)} />
                  <Txt muted style={{ fontSize: 12 }}>
                    {photo.verified ? "Verified by office" : "Awaiting review"}
                  </Txt>
                </Row>
                {office && !photo.verified && (
                  <Button
                    title="Verify photo"
                    variant="secondary"
                    small
                    onPress={() =>
                      run({
                        type: "photo.verify",
                        orderId: order.id,
                        photoId: photo.id,
                      })
                    }
                  />
                )}
              </View>
            ))}
          </Card>
          {order.type !== "delivery" && (
            <Card style={{ gap: 15 }}>
              <Step
                title="Record disposal"
                index={3}
                complete={!!order.weightTons}
              />
              {order.weightTons && (
                <Txt>
                  {order.weightTons} tons · {order.dumpSite}
                </Txt>
              )}
              {active && (
                <>
                  <Field
                    title="Net weight in tons"
                    keyboardType="decimal-pad"
                    placeholder="e.g. 2.4"
                    value={weight}
                    onChangeText={setWeight}
                  />
                  <Choices
                    values={dumpSites}
                    value={dumpSite}
                    onChange={setDumpSite}
                  />
                  <Button
                    title="Save disposal ticket"
                    icon="archive"
                    variant="secondary"
                    onPress={() =>
                      run({
                        type: "order.dump",
                        orderId: order.id,
                        weightTons: Number(weight),
                        dumpSite,
                      })
                    }
                  />
                </>
              )}
            </Card>
          )}
          {active && (
            <Card style={{ gap: 15 }}>
              <Step
                title="Complete the job"
                index={order.type === "delivery" ? 3 : 4}
                complete={false}
              />
              <Field
                title="Completion note"
                placeholder="Access, placement, or site conditions"
                multiline
                value={note}
                onChangeText={setNote}
              />
              <Field
                title="Received by · optional"
                placeholder="Demo recipient name"
                value={signature}
                onChangeText={setSignature}
              />
              <Button
                title="Complete job"
                icon="check-circle"
                onPress={async () => {
                  const result = await run({
                    type: "order.complete",
                    orderId: order.id,
                    note,
                    signature,
                  });
                  if (!result.queued) {
                    if (Platform.OS !== "web")
                      void Haptics.notificationAsync(
                        Haptics.NotificationFeedbackType.Success,
                      ).catch(() => undefined);
                    notify(
                      "Job complete. The billing worker will prepare the invoice.",
                      "success",
                    );
                  }
                }}
              />
            </Card>
          )}
        </>
      )}
      {order.status === "completed" && (
        <Card style={{ backgroundColor: "#e7f0db", gap: 12 }}>
          <Icon name="check-circle" size={30} />
          <Heading
            title="A job well done."
            subtitle={`Completed ${new Date(order.completedAt!).toLocaleString()}`}
          />
          <Txt>
            {order.completionNote || "All required evidence has been saved."}
          </Txt>
          {office && (
            <Button
              title={
                invoice
                  ? `View invoice · ${money(invoice.amountCents)}`
                  : "Open billing queue"
              }
              variant="secondary"
              onPress={() => nav.navigate("Invoices")}
            />
          )}
          <Button
            title="Back to schedule"
            variant="ghost"
            onPress={() => nav.popTo("Main", { screen: "Schedule" })}
          />
        </Card>
      )}
      {["scheduled", "in_progress"].includes(order.status) && (
        <Card style={{ gap: 13 }}>
          <Heading
            title="Something in the way?"
            subtitle="Report a blocked site, access issue, or equipment problem."
          />
          <Field
            title="Issue details"
            value={issue}
            onChangeText={setIssue}
            placeholder="Tell dispatch what happened"
            multiline
          />
          <Button
            title="Report an issue"
            variant="danger"
            icon="alert-triangle"
            disabled={!issue.trim()}
            onPress={() =>
              run({ type: "order.block", orderId: order.id, reason: issue })
            }
          />
        </Card>
      )}
      {order.status === "blocked" && (
        <Card style={{ gap: 15 }}>
          <Heading
            title="Waiting for dispatch"
            subtitle={order.completionNote}
          />
          {office && (
            <Button
              title="Resolve and return to schedule"
              onPress={() => run({ type: "order.resume", orderId: order.id })}
            />
          )}
        </Card>
      )}
    </Page>
  );
}
function Step({
  index,
  title,
  complete,
}: {
  index: number;
  title: string;
  complete: boolean;
}) {
  return (
    <Row style={{ gap: 12 }}>
      <View
        style={{
          width: 30,
          height: 30,
          borderRadius: 15,
          backgroundColor: complete ? colors.lime : colors.pale,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {complete ? (
          <Icon name="check" size={17} />
        ) : (
          <Txt style={{ fontWeight: "700" }}>{index}</Txt>
        )}
      </View>
      <Txt style={{ fontSize: 17, fontWeight: "700" }}>{title}</Txt>
    </Row>
  );
}

export function NewOrderScreen({
  route,
}: NativeStackScreenProps<StackParams, "NewOrder">) {
  const { data, run, notify } = useApp();
  const nav = useNav();
  const [customerId, setCustomer] = useState(route.params?.customerId || "c1");
  const [type, setType] = useState<Order["type"]>("delivery");
  const [size, setSize] = useState<"10 yd" | "20 yd" | "30 yd" | "40 yd">(
    "20 yd",
  );
  const [date, setDate] = useState(today());
  const [priority, setPriority] = useState<"normal" | "urgent">("normal");
  const [notes, setNotes] = useState("");
  const [price, setPrice] = useState("425");
  if (!data) return null;
  return (
    <Page>
      <Heading
        title="Make room for the next job."
        subtitle="Create an order, then assign it to a route."
      />
      <Card style={{ gap: 19 }}>
        <Txt style={{ fontWeight: "700" }}>Customer & site</Txt>
        <Choices
          values={data.customers.map((c) => c.id)}
          labels={Object.fromEntries(data.customers.map((c) => [c.id, c.name]))}
          value={customerId}
          onChange={setCustomer}
        />
        <Txt muted>
          {data.customers.find((c) => c.id === customerId)?.address}
        </Txt>
      </Card>
      <Card style={{ gap: 18 }}>
        <Txt style={{ fontWeight: "700" }}>Service details</Txt>
        <Choices
          values={["delivery", "pickup", "swap", "live_load"] as const}
          value={type}
          onChange={setType}
        />
        <Choices
          values={["10 yd", "20 yd", "30 yd", "40 yd"] as const}
          value={size}
          onChange={setSize}
        />
        <Field
          title="Service date · YYYY-MM-DD"
          value={date}
          onChangeText={setDate}
        />
        <Field
          title="Service price · USD"
          keyboardType="decimal-pad"
          value={price}
          onChangeText={setPrice}
        />
        <Choices
          values={["normal", "urgent"] as const}
          value={priority}
          onChange={setPriority}
        />
        <Field
          title="Site instructions"
          multiline
          placeholder="Where should the driver place the container?"
          value={notes}
          onChangeText={setNotes}
        />
      </Card>
      <Button
        title="Create order"
        icon="plus"
        onPress={async () => {
          const result = await run({
            type: "order.create",
            customerId,
            orderType: type,
            size,
            date,
            priceCents: Math.round(Number(price) * 100),
            notes,
            priority,
          });
          if (result.entityId) {
            notify(`${result.entityId} is ready for dispatch.`, "success");
            nav.replace("Order", { id: result.entityId });
          } else nav.goBack();
        }}
      />
    </Page>
  );
}
