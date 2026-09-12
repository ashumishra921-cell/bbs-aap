import { useCallback, useEffect, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import * as Clipboard from "expo-clipboard";
import Ionicons from "@react-native-vector-icons/ionicons";
import { api } from "@/src/api";
import { makeStyles, useTheme } from "@/src/theme";
import { useToast } from "./Toast";

export default function PaymentDashboardCard({ admin = false }: { admin?: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [upi, setUpi] = useState("");
  const [error, setError] = useState(false);
  const load = useCallback(async () => {
    try { setUpi((await api.paymentConfig()).upi_id); setError(false); }
    catch { setError(true); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const copy = async () => {
    try { await Clipboard.setStringAsync(upi); show("UPI ID copied", "success"); }
    catch { show("UPI ID copy नहीं हुई", "error"); }
  };
  return <View style={styles.card} testID="dashboard-payments-card">
    <Text style={styles.title} testID="dashboard-payments-title">Payments</Text>
    <Text style={styles.sub} testID="dashboard-payments-description">{admin ? "Customer-wise UPI & Cash records" : "आपके UPI & Cash payment records"}</Text>
    <View style={styles.actions}>
      <Pressable testID="dashboard-upi-shortcut" onPress={() => router.push(admin ? "/(admin)/payments" : "/(subscriber)/recharge")} style={({ pressed }) => [styles.action, styles.primary, { opacity: pressed ? 0.7 : 1 }]}>
        <Ionicons name="qr-code" size={20} color={colors.onBrandPrimary} />
        <Text style={styles.primaryText}>{admin ? "UPI Requests" : "Pay via UPI"}</Text>
      </Pressable>
      <Pressable testID="dashboard-payment-history" onPress={() => router.push("/payment-history")} style={({ pressed }) => [styles.action, { opacity: pressed ? 0.7 : 1 }]}>
        <Ionicons name="receipt-outline" size={20} color={colors.brandPrimary} />
        <Text style={styles.actionText}>Payment history</Text>
      </Pressable>
    </View>
    {error ? <Pressable testID="dashboard-upi-retry" onPress={load} style={styles.copy}><Text style={styles.sub}>UPI ID load नहीं हुई · Retry</Text></Pressable>
      : <Pressable testID="dashboard-copy-upi" accessibilityLabel="Copy UPI ID" disabled={!upi} onPress={copy} style={styles.copy}>
        <Text style={styles.upi} testID="dashboard-upi-id">{upi || "UPI ID loading…"}</Text><Ionicons name="copy-outline" size={16} color={colors.brandPrimary} />
      </Pressable>}
  </View>;
}

const useStyles = makeStyles(colors => ({
  card: { marginTop: 16, padding: 16, borderWidth: 1, borderColor: colors.border, borderRadius: 18, backgroundColor: colors.surfaceSecondary },
  title: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  sub: { color: colors.muted, fontSize: 12, lineHeight: 18, marginTop: 4 },
  actions: { flexDirection: "row", gap: 10, marginTop: 16 },
  action: { flex: 1, minHeight: 72, justifyContent: "center", alignItems: "center", gap: 6, padding: 8, borderRadius: 12, backgroundColor: colors.brandTertiary },
  primary: { backgroundColor: colors.brandPrimary },
  primaryText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 13, textAlign: "center" },
  actionText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 13, textAlign: "center" },
  copy: { minHeight: 44, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", marginTop: 6 },
  upi: { color: colors.muted, fontSize: 12, flexShrink: 1 },
}));