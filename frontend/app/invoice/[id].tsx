import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api } from "@/src/api";
import { makeStyles, useTheme } from "@/src/theme";

export default function InvoiceDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [inv, setInv] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const i = await api.invoice(id as string);
        setInv(i);
      } finally { setLoading(false); }
    })();
  }, [id]);

  if (loading) {
    return (
      <View style={[styles.center, { backgroundColor: colors.surface }]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }
  if (!inv) return null;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="inv-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Invoice</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 20 }}>
        <View style={styles.card}>
          <View style={styles.top}>
            <View>
              <Text style={styles.brand}>Broadband Solutions 24×7</Text>
              <Text style={styles.sub}>Local ISP · Delhi</Text>
            </View>
            <View style={[styles.statusPill, { backgroundColor: inv.status === "paid" ? "#D1FAE5" : "#FEF3C7" }]}>
              <Text style={{ color: inv.status === "paid" ? "#065F46" : "#B45309", fontWeight: "800", fontSize: 11 }}>
                {inv.status.toUpperCase()}
              </Text>
            </View>
          </View>

          <View style={styles.row}>
            <Text style={styles.k}>Invoice No</Text>
            <Text style={styles.v}>{inv.invoice_no}</Text>
          </View>
          <View style={styles.row}>
            <Text style={styles.k}>Date</Text>
            <Text style={styles.v}>{dayjs(inv.created_at).format("DD MMM YYYY, hh:mm A")}</Text>
          </View>
          <View style={styles.row}>
            <Text style={styles.k}>Customer</Text>
            <Text style={styles.v}>{inv.user_name}</Text>
          </View>
          <View style={styles.row}>
            <Text style={styles.k}>Phone</Text>
            <Text style={styles.v}>+91 {inv.user_phone}</Text>
          </View>

          <View style={styles.divider} />
          <Text style={styles.section}>Plan</Text>
          <View style={styles.planBox}>
            <Text style={styles.planName}>{inv.plan_name}</Text>
            <Text style={styles.planAmt}>₹{inv.amount}</Text>
          </View>

          {inv.upi_id && (
            <View style={styles.row}>
              <Text style={styles.k}>UPI ID</Text>
              <Text style={styles.v}>{inv.upi_id}</Text>
            </View>
          )}

          <View style={styles.divider} />
          <View style={styles.totalRow}>
            <Text style={styles.totalK}>Total Paid</Text>
            <Text style={styles.totalV}>₹{inv.amount}</Text>
          </View>

          <View style={styles.footer}>
            <Ionicons name="checkmark-circle" size={18} color={colors.success} />
            <Text style={{ color: colors.muted, fontSize: 12 }}>Thank you for your payment</Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingBottom: 12, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: 20 },
  title: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: 20, padding: 20, borderWidth: 1, borderColor: colors.border, gap: 12 },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 },
  brand: { fontSize: 16, fontWeight: "800", color: colors.brandPrimary },
  sub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  k: { color: colors.muted, fontSize: 12 },
  v: { color: colors.onSurface, fontSize: 13, fontWeight: "700" },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: 8 },
  section: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, fontWeight: "700" },
  planBox: { padding: 12, borderRadius: 12, backgroundColor: colors.brandTertiary, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  planName: { fontWeight: "800", color: colors.onBrandTertiary },
  planAmt: { fontWeight: "800", color: colors.onBrandTertiary, fontSize: 16 },
  totalRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  totalK: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  totalV: { fontSize: 22, fontWeight: "800", color: colors.brandPrimary },
  footer: { flexDirection: "row", alignItems: "center", gap: 6, justifyContent: "center", marginTop: 12 },
}));
