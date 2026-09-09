import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api, clearAuth, loadAuth, User } from "@/src/api";
import HelplineCard from "@/src/components/HelplineCard";
import { makeStyles, useTheme } from "@/src/theme";

export default function ProfileScreen() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [user, setUser] = useState<User | null>(null);
  const [invoices, setInvoices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { user } = await loadAuth();
      setUser(user);
      const inv = await api.invoices();
      setInvoices(inv);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const logout = async () => {
    await clearAuth();
    router.replace("/");
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.surface }} contentContainerStyle={{ paddingBottom: 32 }}>
      <View style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <View style={styles.avatar}>
          <Ionicons name="person" size={36} color="#FFFFFF" />
        </View>
        <Text style={styles.name} testID="profile-name">{user?.name}</Text>
        <Text style={styles.phone}>+91 {user?.phone}</Text>
        <View style={styles.roleBadge}>
          <Text style={styles.roleText}>{user?.role?.replace("_", " ").toUpperCase()}</Text>
        </View>
      </View>

      <View style={{ padding: 16 }}>
        <Text style={styles.section}>Invoices</Text>
        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : invoices.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="receipt-outline" size={40} color={colors.muted} />
            <Text style={{ color: colors.muted, marginTop: 8 }}>No invoices yet</Text>
          </View>
        ) : (
          <View style={{ gap: 8 }}>
            {invoices.map((inv) => (
              <Pressable
                key={inv.id}
                onPress={() => router.push(`/invoice/${inv.id}`)}
                style={styles.invRow}
                testID={`invoice-${inv.invoice_no}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.invNo}>{inv.invoice_no}</Text>
                  <Text style={styles.invDate}>{dayjs(inv.created_at).format("DD MMM YYYY")} · {inv.plan_name}</Text>
                </View>
                <Text style={styles.invAmount}>₹{inv.amount}</Text>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
          </View>
        )}

        <HelplineCard />

        <Pressable onPress={logout} style={styles.logout} testID="logout-btn">
          <Ionicons name="log-out-outline" size={20} color={colors.error} />
          <Text style={styles.logoutText}>Logout</Text>
        </Pressable>
      </View>
    </ScrollView>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 24, alignItems: "center", backgroundColor: colors.brandPrimary, borderBottomLeftRadius: 24, borderBottomRightRadius: 24 },
  avatar: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.brandSecondary, alignItems: "center", justifyContent: "center" },
  name: { fontSize: 20, fontWeight: "800", color: "#FFFFFF", marginTop: 12 },
  phone: { fontSize: 13, color: "#CCFBF1", marginTop: 2 },
  roleBadge: { marginTop: 10, paddingHorizontal: 12, paddingVertical: 4, backgroundColor: "rgba(255,255,255,0.2)", borderRadius: 999 },
  roleText: { fontSize: 11, color: "#FFFFFF", fontWeight: "800", letterSpacing: 0.5 },
  section: { fontSize: 16, fontWeight: "800", color: colors.onSurface, marginBottom: 12 },
  empty: { alignItems: "center", padding: 24 },
  invRow: {
    backgroundColor: colors.surfaceSecondary, borderRadius: 12, padding: 14,
    borderWidth: 1, borderColor: colors.border,
    flexDirection: "row", alignItems: "center", gap: 8,
  },
  invNo: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  invDate: { fontSize: 11, color: colors.muted, marginTop: 2 },
  invAmount: { fontSize: 15, fontWeight: "800", color: colors.brandPrimary },
  logout: {
    marginTop: 24, flexDirection: "row", alignItems: "center", justifyContent: "center",
    gap: 8, height: 48, borderRadius: 12, borderWidth: 1, borderColor: colors.error,
    backgroundColor: colors.surfaceSecondary,
  },
  logoutText: { color: colors.error, fontWeight: "700" },
}));
