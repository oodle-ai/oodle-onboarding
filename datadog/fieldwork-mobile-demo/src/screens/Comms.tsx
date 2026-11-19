import React, { useState } from "react";
import { View } from "react-native";
import { useApp } from "../state";
import {
  Badge,
  Button,
  Card,
  Choices,
  colors,
  Empty,
  Field,
  Heading,
  Page,
  Row,
  Txt,
} from "../components/ui";

export function CommsScreen() {
  const { data, session, run, office, notify } = useApp();
  const [channel, setChannel] = useState("dispatch");
  const [text, setText] = useState("");
  if (!data || !session) return null;
  const channels = [
    "dispatch",
    "huddle",
    ...data.customers.map((c) => `customer:${c.id}`),
  ];
  const labels = {
    dispatch: "Dispatch",
    huddle: "Team huddle",
    ...Object.fromEntries(
      data.customers.map((c) => [`customer:${c.id}`, c.name]),
    ),
  };
  const messages = data.messages.filter((m) => m.channel === channel);
  return (
    <Page>
      <Heading
        title="A connected crew."
        subtitle="From the office to the last stop of the day."
      />
      <Choices
        values={channels}
        value={channel}
        labels={labels}
        onChange={setChannel}
      />
      {channel.startsWith("customer:") && office && (
        <Card style={{ gap: 12 }}>
          <Badge text="Call simulator" tone="blue" />
          <Txt muted>
            Record a call outcome for this demo contact. No telephone call will
            be placed.
          </Txt>
          <Row style={{ gap: 8, flexWrap: "wrap" }}>
            {(["connected", "voicemail", "no_answer"] as const).map(
              (outcome) => (
                <Button
                  key={outcome}
                  title={
                    outcome === "no_answer"
                      ? "No answer"
                      : outcome === "connected"
                        ? "Connected"
                        : "Voicemail"
                  }
                  icon="phone"
                  variant="secondary"
                  small
                  onPress={() =>
                    run({
                      type: "call.record",
                      customerId: channel.split(":")[1]!,
                      outcome,
                    })
                  }
                />
              ),
            )}
          </Row>
        </Card>
      )}
      <View style={{ gap: 14 }}>
        {messages.map((m) => {
          const own = m.authorId === session.user.id;
          return (
            <View
              key={m.id}
              style={{
                alignSelf: own ? "flex-end" : "flex-start",
                maxWidth: "92%",
                gap: 6,
              }}
            >
              <Txt muted style={{ fontSize: 11 }}>
                {data.users.find((u) => u.id === m.authorId)?.name || "System"}{" "}
                ·{" "}
                {new Date(m.createdAt).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </Txt>
              <Card
                style={{
                  backgroundColor: own ? colors.ink : colors.white,
                  borderColor: own ? colors.ink : colors.line,
                  borderBottomRightRadius: own ? 4 : 20,
                  borderBottomLeftRadius: own ? 20 : 4,
                }}
              >
                <Txt
                  style={{
                    color: own ? colors.white : colors.ink,
                    lineHeight: 22,
                  }}
                >
                  {m.text}
                </Txt>
              </Card>
            </View>
          );
        })}
        {!messages.length && (
          <Empty
            title="Start a conversation"
            detail="Messages stay in this demo workspace."
            icon="message-circle"
          />
        )}
      </View>
      <Card style={{ gap: 12 }}>
        <Field
          title="Message"
          multiline
          placeholder={
            channel === "huddle"
              ? "Share an update with your crew…"
              : "Write a message…"
          }
          value={text}
          onChangeText={setText}
        />
        <Button
          title="Send message"
          icon="send"
          disabled={!text.trim()}
          onPress={async () => {
            const result = await run({ type: "message.send", channel, text });
            setText("");
            if (!result.queued) notify("Message sent.", "success");
          }}
        />
      </Card>
    </Page>
  );
}
