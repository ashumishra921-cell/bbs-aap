import { useRouter } from "expo-router";
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
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import Ionicons from "@react-native-vector-icons/ionicons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";

import { api, loadAuth } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

export default function LoginScreen() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    (async () => {
      const { token, user } = await loadAuth();
      if (token && user) {
        redirectByRole(user.role);
      } else {
        setBooting(false);
      }
    })();
  }, []);

  const redirectByRole = (role: string) => {
    if (role === "subscriber") router.replace("/(subscriber)/home");
    else if (role === "team") router.replace("/(team)/assigned");
    else router.replace("/(admin)/overview");
  };

  const onContinue = async () => {
    if (phone.length < 10) {
      toast.show("कृपया 10 अंकों का मोबाइल दर्ज करें", "error");
      return;
    }
    setLoading(true);
    try {
      const res = await api.requestOtp(phone);
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      router.push({ pathname: "/otp", params: { phone, isNew: res.is_new_user ? "1" : "0" } });
    } catch (e: any) {
      toast.show(e.message || "Something went wrong", "error");
    } finally {
      setLoading(false);
    }
  };

  if (booting) {
    return (
      <View style={[styles.center, { backgroundColor: colors.brandPrimary }]}>
        <ActivityIndicator color="#FFFFFF" />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surface }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={{ flex: 1 }}>
        <LinearGradient
          colors={[colors.brandPrimary, colors.brandSecondary]}
          style={[styles.hero, { paddingTop: insets.top + 32 }]}
        >
          <View style={styles.logoRow}>
            <View style={styles.logoBadge}>
              <Ionicons name="wifi" size={28} color={colors.brandPrimary} />
            </View>
            <Text style={styles.logoText}>Broadband Solutions 24×7</Text>
          </View>
          <Text style={styles.tagline}>तेज़ इंटरनेट. भरोसेमंद सेवा.</Text>
        </LinearGradient>

        <View style={styles.card}>
          <Text style={styles.title}>लॉगिन करें</Text>
          <Text style={styles.subtitle}>अपना मोबाइल नंबर दर्ज करें, हम OTP भेजेंगे</Text>

          <View style={styles.phoneBox}>
            <Text style={styles.cc}>+91</Text>
            <TextInput
              testID="phone-input"
              placeholder="10-digit mobile"
              placeholderTextColor={colors.muted}
              keyboardType="number-pad"
              maxLength={10}
              value={phone}
              onChangeText={(t) => setPhone(t.replace(/[^0-9]/g, ""))}
              style={styles.phoneInput}
            />
          </View>

          <Pressable
            testID="request-otp-btn"
            onPress={onContinue}
            disabled={loading}
            style={({ pressed }) => [
              styles.primaryBtn,
              { backgroundColor: colors.brandPrimary, opacity: pressed || loading ? 0.85 : 1 },
            ]}
          >
            {loading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.primaryBtnText}>OTP भेजें</Text>
            )}
          </Pressable>

          <View style={styles.hintBox}>
            <Ionicons name="information-circle" size={16} color={colors.info} />
            <Text style={styles.hintText}>Demo OTP: 123456</Text>
          </View>

          <View style={styles.demoNumbers}>
            <Text style={styles.demoTitle}>Demo Accounts</Text>
            <Text style={styles.demoLine}>Subscriber: 9999999996</Text>
            <Text style={styles.demoLine}>Team: 9999999997</Text>
            <Text style={styles.demoLine}>Admin: 9999999998</Text>
            <Text style={styles.demoLine}>Super Admin: 9999999999</Text>
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const useStyles = makeStyles((colors) => ({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  hero: {
    paddingHorizontal: 24,
    paddingBottom: 48,
    borderBottomLeftRadius: 32,
    borderBottomRightRadius: 32,
  },
  logoRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  logoBadge: {
    width: 48,
    height: 48,
    borderRadius: 16,
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
  },
  logoText: { color: "#FFFFFF", fontSize: 18, fontWeight: "800", flex: 1 },
  tagline: { color: "#CCFBF1", fontSize: 14, marginTop: 12 },
  card: {
    marginHorizontal: 20,
    marginTop: -28,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: 20,
    padding: 24,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 4,
  },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  subtitle: { fontSize: 13, color: colors.muted, marginTop: 6, marginBottom: 20 },
  phoneBox: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceTertiary,
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 56,
    gap: 10,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cc: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  phoneInput: { flex: 1, fontSize: 16, color: colors.onSurface },
  primaryBtn: {
    marginTop: 20,
    height: 52,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  primaryBtnText: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  hintBox: { marginTop: 16, flexDirection: "row", alignItems: "center", gap: 6, justifyContent: "center" },
  hintText: { color: colors.muted, fontSize: 12 },
  demoNumbers: {
    marginTop: 20,
    padding: 12,
    borderRadius: 12,
    backgroundColor: colors.brandTertiary,
  },
  demoTitle: { fontSize: 12, fontWeight: "700", color: colors.onBrandTertiary, marginBottom: 6 },
  demoLine: { fontSize: 12, color: colors.onBrandTertiary, lineHeight: 18 },
}));
