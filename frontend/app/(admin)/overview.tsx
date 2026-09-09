import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";

import { api, clearAuth, loadAuth, User } from "@/src/api";
import { makeStyles, useTheme } from "@/src/theme";

export default function AdminOverview() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [metrics, setMetrics] = useState<any | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const { user } = await loadAuth();
      setUser(user);
      const m = await api.adminMetrics();
      setMetrics(m);
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
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <LinearGradient colors={[colors.brandPrimary, colors.brandSecondary]} style={[styles.header, { paddingTop: insets.top + 16 }]}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <View>
            <Text style={styles.hello}>{user?.role === "super_admin" ? "Super Admin" : "Admin"}</Text>
            <Text style={styles.name}>{user?.name}</Text>
          </View>
          <Pressable onPress={logout} style={styles.logoutBtn} testID="admin-logout">
            <Ionicons name="log-out-outline" size={22} color="#FFFFFF" />
          </Pressable>
        </View>
      </LinearGradient>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
          <View style={styles.grid}>
            <MetricCard label="Subscribers" value={metrics.subscribers} icon="people" tint={colors.info} />
            <MetricCard label="Team" value={metrics.team_members} icon="briefcase" tint={colors.warning} />
            <MetricCard label="Active Plans" value={metrics.active_subscriptions} icon="wifi" tint={colors.brandPrimary} />
            <MetricCard label="Open Tickets" value={metrics.open_complaints} icon="alert-circle" tint={colors.error} />
          </View>

          <View style={styles.revenueCard}>
            <Text style={styles.revLabel}>Total Revenue</Text>
            <Text style={styles.revValue}>₹{metrics.total_revenue?.toLocaleString?.() || 0}</Text>
            <Text style={styles.revSub}>{metrics.resolved_complaints} tickets resolved</Text>
          </View>
        </ScrollView>
      )}
    </View>
  );
}

function MetricCard({ label, value, icon, tint }: any) {
  const styles = useStyles();
  return (
    <View style={styles.metricCard}>
      <View style={[styles.metricIcon, { backgroundColor: tint + "20" }]}>
        <Ionicons name={icon} size={20} color={tint} />
      </View>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 20, borderBottomLeftRadius: 24, borderBottomRightRadius: 24 },
  hello: { color: "#CCFBF1", fontSize: 12, letterSpacing: 0.5, textTransform: "uppercase" },
  name: { color: "#FFFFFF", fontSize: 22, fontWeight: "800", marginTop: 2 },
  logoutBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: "rgba(255,255,255,0.2)", alignItems: "center", justifyContent: "center" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  metricCard: {
    width: "47%", padding: 16, backgroundColor: colors.surfaceSecondary,
    borderRadius: 14, borderWidth: 1, borderColor: colors.border,
  },
  metricIcon: { width: 36, height: 36, borderRadius: 10, alignItems: "center", justifyContent: "center", marginBottom: 12 },
  metricValue: { fontSize: 24, fontWeight: "800", color: colors.onSurface },
  metricLabel: { fontSize: 12, color: colors.muted, marginTop: 2 },
  revenueCard: { padding: 20, backgroundColor: colors.brandTertiary, borderRadius: 16 },
  revLabel: { fontSize: 12, color: colors.onBrandTertiary, letterSpacing: 0.5, textTransform: "uppercase" },
  revValue: { fontSize: 28, fontWeight: "800", color: colors.onBrandTertiary, marginTop: 4 },
  revSub: { fontSize: 12, color: colors.onBrandTertiary, marginTop: 4 },
}));
