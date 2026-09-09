import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";

import { api, saveAuth } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

export default function OtpScreen() {
  const router = useRouter();
  const { phone, isNew, mode } = useLocalSearchParams<{ phone: string; isNew: string; mode: string }>();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [otp, setOtp] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(30);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const resend = async () => {
    setResending(true);
    try {
      const res = await api.requestOtp(phone as string);
      toast.show(res.mode === "sms" ? "OTP फिर से SMS किया गया" : `Demo OTP: ${res.otp}`, "success");
      setCooldown(30);
    } catch (e: any) {
      toast.show(e.message || "Resend failed", "error");
    } finally {
      setResending(false);
    }
  };

  const verify = async () => {
    if (otp.length !== 6) {
      toast.show("6 अंकों का OTP दर्ज करें", "error");
      return;
    }
    if (isNew === "1" && !name.trim()) {
      toast.show("नाम आवश्यक है", "error");
      return;
    }
    setLoading(true);
    try {
      const res = await api.verifyOtp(phone as string, otp, name || undefined);
      await saveAuth(res.token, res.user);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.show(`स्वागत है ${res.user.name}!`, "success");
      const r = res.user.role;
      if (r === "subscriber") router.replace("/(subscriber)/home");
      else if (r === "team") router.replace("/(team)/assigned");
      else router.replace("/(admin)/overview");
    } catch (e: any) {
      toast.show(e.message || "Verify failed", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="back-btn">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>OTP सत्यापन</Text>
      </View>

      <View style={styles.body}>
        <Text style={styles.title}>OTP दर्ज करें</Text>
        <Text style={styles.sub} testID="otp-sub">
          {mode === "sms" ? `+91 ${phone} पर SMS भेजा गया` : `+91 ${phone} · Demo OTP 123456 दर्ज करें`}
        </Text>

        <TextInput
          testID="otp-input"
          placeholder="6-digit OTP"
          placeholderTextColor={colors.muted}
          keyboardType="number-pad"
          maxLength={6}
          value={otp}
          onChangeText={(t) => setOtp(t.replace(/[^0-9]/g, ""))}
          style={styles.otpInput}
        />

        {isNew === "1" && (
          <>
            <Text style={styles.label}>आपका नाम</Text>
            <TextInput
              testID="name-input"
              placeholder="पूरा नाम"
              placeholderTextColor={colors.muted}
              value={name}
              onChangeText={setName}
              style={styles.textInput}
            />
          </>
        )}

        <Pressable
          testID="verify-otp-btn"
          onPress={verify}
          disabled={loading}
          style={({ pressed }) => [
            styles.primaryBtn,
            { backgroundColor: colors.brandPrimary, opacity: pressed || loading ? 0.85 : 1 },
          ]}
        >
          {loading ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryBtnText}>सत्यापित करें</Text>}
        </Pressable>

        <Pressable
          testID="resend-otp-btn"
          onPress={resend}
          disabled={cooldown > 0 || resending}
          style={styles.resendBtn}
        >
          {resending ? (
            <ActivityIndicator size="small" color={colors.brandPrimary} />
          ) : (
            <Text style={[styles.resendText, { color: cooldown > 0 ? colors.muted : colors.brandPrimary }]}>
              {cooldown > 0 ? `OTP फिर से भेजें (${cooldown}s)` : "OTP फिर से भेजें"}
            </Text>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles((colors) => ({
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingBottom: 12,
    gap: 8,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 20 },
  headerTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  body: { paddingHorizontal: 24, paddingTop: 24 },
  title: { fontSize: 24, fontWeight: "800", color: colors.onSurface },
  sub: { fontSize: 14, color: colors.muted, marginTop: 6, marginBottom: 24 },
  otpInput: {
    height: 60,
    borderRadius: 14,
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 20,
    fontSize: 22,
    letterSpacing: 6,
    fontWeight: "700",
    color: colors.onSurface,
    textAlign: "center",
  },
  label: { marginTop: 20, marginBottom: 8, color: colors.onSurface, fontWeight: "600" },
  textInput: {
    height: 52,
    borderRadius: 12,
    backgroundColor: colors.surfaceTertiary,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 16,
    fontSize: 16,
    color: colors.onSurface,
  },
  primaryBtn: {
    marginTop: 24,
    height: 52,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryBtnText: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  resendBtn: { marginTop: 16, height: 44, alignItems: "center", justifyContent: "center" },
  resendText: { fontWeight: "700", fontSize: 14 },
}));
