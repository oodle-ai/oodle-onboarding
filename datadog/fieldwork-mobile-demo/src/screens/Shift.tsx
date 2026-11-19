import React, { useState } from "react";
import { Pressable, View } from "react-native";
import { NativeStackScreenProps } from "@react-navigation/native-stack";
import { StackParams, useNav } from "../navigation";
import { useApp } from "../state";
import {
  activeShift,
  inspectionChecks,
  isOnBreak,
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
  Txt,
} from "../components/ui";

export function ShiftScreen() {
  const { data, session, run, notify } = useApp();
  const nav = useNav();
  const [vehicle, setVehicle] = useState("truck-12");
  if (!data || !session) return null;
  const shift = activeShift(data.shifts, session.user.id);
  const inspection = data.inspections.find(
    (i) =>
      i.userId === session.user.id &&
      i.vehicleId === vehicle &&
      i.createdAt.slice(0, 10) === today(),
  );
  return (
    <Page>
      <Heading
        title="Your day, in motion."
        subtitle="Inspect the truck. Clock in. Take a break when you need one."
      />
      {shift ? (
        <Card style={{ gap: 18 }}>
          <Badge text={isOnBreak(shift) ? "On break" : "On the clock"} />
          <Txt style={{ fontSize: 28, fontWeight: "700" }}>
            {data.vehicles.find((v) => v.id === shift.vehicleId)?.name}
          </Txt>
          <Txt muted>
            Started at{" "}
            {new Date(shift.startedAt).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}{" "}
            · {shift.breaks.length} breaks
          </Txt>
          <Button
            title={isOnBreak(shift) ? "End break" : "Start break"}
            icon="coffee"
            variant="secondary"
            onPress={() =>
              run({
                type: isOnBreak(shift)
                  ? "shift.break_end"
                  : "shift.break_start",
              })
            }
          />
          <Button
            title="End my day"
            icon="moon"
            onPress={async () => {
              await run({ type: "shift.clock_out" });
              notify("Shift saved. See you next time.", "success");
            }}
          />
          <Button
            title="Back to schedule"
            variant="ghost"
            onPress={() => nav.popTo("Main", { screen: "Schedule" })}
          />
        </Card>
      ) : (
        <Card style={{ gap: 18 }}>
          <Txt style={{ fontWeight: "700", fontSize: 17 }}>
            Select your truck
          </Txt>
          <Choices
            values={data.vehicles.map((v) => v.id)}
            value={vehicle}
            onChange={setVehicle}
            labels={Object.fromEntries(
              data.vehicles.map((v) => [
                v.id,
                `${v.name}${v.status === "maintenance" ? " · Shop" : ""}`,
              ]),
            )}
          />
          <Badge
            text={
              inspection?.safe
                ? "Inspection complete today"
                : "Inspection required"
            }
            tone={inspection?.safe ? "green" : "amber"}
          />
          <Button
            title="Start vehicle inspection"
            icon="clipboard"
            variant="secondary"
            onPress={() => nav.navigate("Inspection", { vehicleId: vehicle })}
          />
          <Button
            title="Confirm clock in"
            icon="sun"
            onPress={async () => {
              const result = await run({
                type: "shift.clock_in",
                vehicleId: vehicle,
              });
              if (!result.queued)
                notify("You are clocked in. Your route is ready.", "success");
            }}
          />
        </Card>
      )}
      <View>
        <Heading title="Shift history" />
        {data.shifts.filter((s) => s.userId === session.user.id && s.endedAt)
          .length === 0 ? (
          <Empty
            title="A fresh start"
            detail="Completed shifts will appear here."
            icon="clock"
          />
        ) : (
          data.shifts
            .filter((s) => s.userId === session.user.id && s.endedAt)
            .map((s) => (
              <Card key={s.id} style={{ marginBottom: 12 }}>
                <Txt style={{ fontWeight: "700" }}>
                  {new Date(s.startedAt).toLocaleDateString()}
                </Txt>
                <Txt muted style={{ marginTop: 8 }}>
                  {new Date(s.startedAt).toLocaleTimeString()} –{" "}
                  {new Date(s.endedAt!).toLocaleTimeString()} ·{" "}
                  {s.breaks.length} breaks
                </Txt>
              </Card>
            ))
        )}
      </View>
    </Page>
  );
}
export function InspectionScreen({
  route,
}: NativeStackScreenProps<StackParams, "Inspection">) {
  const { data, run, notify } = useApp();
  const nav = useNav();
  const [vehicle, setVehicle] = useState(route.params?.vehicleId || "truck-12");
  const [checks, setChecks] = useState<string[]>([]);
  const [defect, setDefect] = useState("");
  if (!data) return null;
  return (
    <Page>
      <Heading
        title="A safe start."
        subtitle="Check all six items. Report any defect before you drive."
      />
      <Choices
        values={data.vehicles.map((v) => v.id)}
        value={vehicle}
        onChange={(v) => {
          setVehicle(v);
          setChecks([]);
        }}
        labels={Object.fromEntries(data.vehicles.map((v) => [v.id, v.name]))}
      />
      <Card>
        {inspectionChecks.map((check) => (
          <Pressable
            key={check}
            accessibilityRole="checkbox"
            accessibilityLabel={check}
            accessibilityState={{ checked: checks.includes(check) }}
            onPress={() =>
              setChecks((current) =>
                current.includes(check)
                  ? current.filter((c) => c !== check)
                  : [...current, check],
              )
            }
            style={{
              flexDirection: "row",
              paddingVertical: 18,
              gap: 14,
              borderBottomWidth: 1,
              borderColor: colors.line,
            }}
          >
            <Icon
              name={checks.includes(check) ? "check-square" : "square"}
              color={checks.includes(check) ? colors.green : colors.muted}
            />
            <Txt style={{ fontSize: 16 }}>{check}</Txt>
          </Pressable>
        ))}
      </Card>
      <Field
        title="Defect report · leave blank if safe"
        placeholder="Describe any issue. A defect will place the truck in maintenance."
        value={defect}
        onChangeText={setDefect}
        multiline
      />
      <Button
        title={
          defect.trim() ? "Submit defect report" : "Submit safe inspection"
        }
        icon="check-circle"
        disabled={checks.length !== inspectionChecks.length}
        onPress={async () => {
          const result = await run({
            type: "inspection.submit",
            vehicleId: vehicle,
            checks,
            defect,
          });
          if (!result.queued)
            notify(
              defect.trim()
                ? "Defect reported. The truck needs a maintenance review."
                : "Inspection saved. You can clock in.",
              "success",
            );
          nav.popTo("Shift");
        }}
      />
      <Txt muted style={{ textAlign: "center", fontSize: 12 }}>
        {checks.length} of {inspectionChecks.length} checks complete
      </Txt>
    </Page>
  );
}
