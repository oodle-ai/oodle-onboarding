import React, { useState } from "react";
import { View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { authPost } from "../api";
import { useApp } from "../state";
import {
  Badge,
  Button,
  Card,
  Choices,
  colors,
  Field,
  Page,
  Row,
  Txt,
} from "../components/ui";
import { TruckArt } from "../components/illustrations";

export function WelcomeScreen() {
  const { login, loginOtp } = useApp();
  const [profile, setProfile] = useState("driver-ava");
  const [challenge, setChallenge] = useState("");
  const [code, setCode] = useState("");
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.bg }}>
      <Page refresh={false}>
        <Row style={{ gap: 8, paddingTop: 12 }}>
          <View
            style={{
              height: 30,
              width: 30,
              borderRadius: 10,
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
          <Txt style={{ fontWeight: "700", fontSize: 19, letterSpacing: -0.5 }}>
            fieldwork
            <Txt style={{ fontSize: 19, color: colors.muted }}> one</Txt>
          </Txt>
          <View style={{ flex: 1 }} />
          <Badge text="RUM DEMO" tone="gray" />
        </Row>
        <View
          style={{
            alignItems: "center",
            backgroundColor: colors.ink,
            borderRadius: 28,
            padding: 27,
            marginTop: 5,
          }}
        >
          <TruckArt />
          <Txt
            style={{
              color: colors.white,
              fontSize: 30,
              fontWeight: "700",
              letterSpacing: -1,
              textAlign: "center",
              marginTop: 15,
            }}
          >
            Mobile RUM demo
          </Txt>
          <Txt
            style={{
              color: "#c6d9c1",
              textAlign: "center",
              lineHeight: 23,
              marginTop: 14,
            }}
          >
            Try sample jobs to explore RUM,{"\n"}session replay, and traces.
          </Txt>
        </View>
        <Card style={{ gap: 18 }}>
          <View>
            <Txt
              style={{ fontSize: 21, fontWeight: "700", letterSpacing: -0.5 }}
            >
              Choose a demo role
            </Txt>
            <Txt muted style={{ marginTop: 7, lineHeight: 21 }}>
              Sign in with a demo profile. Each profile has its own role and
              work queue.
            </Txt>
          </View>
          <Choices
            values={[
              "driver-ava",
              "driver-leo",
              "dispatcher-sam",
              "admin-morgan",
            ]}
            value={profile}
            onChange={(p) => {
              setProfile(p);
              setChallenge("");
            }}
            labels={{
              "driver-ava": "Ava · Driver",
              "driver-leo": "Leo · Driver",
              "dispatcher-sam": "Sam · Dispatch",
              "admin-morgan": "Morgan · Admin",
            }}
          />
          {challenge ? (
            <>
              <Txt muted>
                Demo verification code: 123456. No text message is sent.
              </Txt>
              <Field
                title="Verification code"
                keyboardType="number-pad"
                value={code}
                onChangeText={setCode}
                maxLength={6}
              />
              <Button
                title="Verify and sign in"
                onPress={() => loginOtp(challenge, code)}
              />
              <Button
                title="Back to profiles"
                variant="ghost"
                onPress={() => setChallenge("")}
              />
            </>
          ) : (
            <>
              <Button
                title="Continue with demo email"
                icon="arrow-right"
                onPress={() => login(profile)}
              />
              <Button
                title="Try demo phone sign-in"
                variant="secondary"
                icon="smartphone"
                onPress={async () => {
                  const result = await authPost<{ challengeId: string }>(
                    "/api/auth/otp/phone",
                    { profile },
                  );
                  setChallenge(result.challengeId);
                  setCode("");
                }}
              />
            </>
          )}
        </Card>
        <Txt
          muted
          style={{ textAlign: "center", fontSize: 12, lineHeight: 20 }}
        >
          Synthetic data. Demo use only.{"\n"}Not for live business operations.
        </Txt>
      </Page>
    </SafeAreaView>
  );
}
