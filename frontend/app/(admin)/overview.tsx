import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";

import { api, clearAuth, loadAuth, User } from "@/src/api";
import { makeStyles, useTheme } from "@/src/theme";
import PaymentDashboardCard from "@/src/components/PaymentDashboardCard";
import { AlertSoundControl } from "@/src/components/ActivityAlerts";

export default function AdminOverview() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [metrics, setMetrics] = useState<any | null>(null);
  const [expiring, setExpiring] = useState<any[]>([]);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const { user } = await loadAuth();
      setUser(user);
      const [m, ex] = await Promise.all([api.adminMetrics(), api.adminExpiring(3)]);
      setMetrics(m);
      setExpiring(ex);
    } catch (e: any) {
      setError(e.message || "Failed to load");
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
      ) : error || !metrics ? (
        <View style={styles.errorBox} testID="overview-error">
          <Ionicons name="cloud-offline-outline" size={40} color={colors.muted} />
          <Text style={{ color: colors.muted, marginTop: 8, textAlign: "center" }}>{error || "डेटा लोड नहीं हुआ"}</Text>
          <Pressable onPress={() => { setLoading(true); load(); }} style={[styles.retryBtn, { backgroundColor: colors.brandPrimary }]} testID="overview-retry">
            <Text style={{ color: "#FFFFFF", fontWeight: "700" }}>Retry</Text>
          </Pressable>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 16, gap: 12 }}
          refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
        >
          <View style={styles.grid}>
            <MetricCard label="Subscribers" value={metrics.subscribers} icon="people" tint={colors.info} onPress={() => router.push("/(admin)/subscribers")} testID="metric-subscribers" />
            <MetricCard label="Team" value={metrics.team_members} icon="briefcase" tint={colors.warning} onPress={() => router.push("/(admin)/team")} testID="metric-team" />
            <MetricCard label="Active Plans" value={metrics.active_subscriptions} icon="wifi" tint={colors.brandPrimary} onPress={() => router.push("/(admin)/subscribers")} testID="metric-plans" />
            <MetricCard label="Open Tickets" value={metrics.open_complaints} icon="alert-circle" tint={colors.error} onPress={() => router.push("/(admin)/complaints")} testID="metric-tickets" />
          </View>

          <PaymentDashboardCard admin />
          <AlertSoundControl />

          <View style={styles.revenueCard}>
            <Text style={styles.revLabel}>Total Revenue</Text>
            <Text style={styles.revValue}>₹{metrics.total_revenue?.toLocaleString?.() || 0}</Text>
            <Text style={styles.revSub}>{metrics.resolved_complaints} tickets resolved</Text>
          </View>

          {user?.role === "super_admin" && (
            <View style={styles.toolsRow}>
              <Pressable onPress={() => router.push("/(admin)/report")} style={styles.tool} testID="open-report">
                <Ionicons name="bar-chart" size={22} color={colors.brandPrimary} />
                <Text style={styles.toolTxt}>Collection Report</Text>
                <Text style={styles.toolSub}>UPI · Cash · Dues · SMS</Text>
              </Pressable>
              <Pressable onPress={() => router.push("/(admin)/plans")} style={styles.tool} testID="open-plans">
                <Ionicons name="pricetags" size={22} color={colors.brandPrimary} />
                <Text style={styles.toolTxt}>Plan Editor</Text>
                <Text style={styles.toolSub}>Add · Edit · Hide plans</Text>
              </Pressable>
            </View>
          )}

          <View style={styles.expCard} testID="expiring-card">
            <View style={styles.expHeader}>
              <Ionicons name="alarm" size={18} color={colors.warning} />
              <Text style={styles.expTitle}>Expiring in 3 days</Text>
              <View style={[styles.expCount, { backgroundColor: expiring.length ? colors.warning : colors.border }]}>
                <Text style={styles.expCountTxt}>{expiring.length}</Text>
              </View>
            </View>
            {expiring.length === 0 ? (
              <Text style={styles.expEmpty}>कोई प्लान समाप्त नहीं हो रहा 🎉</Text>
            ) : (
              expiring.map((e) => (
                <Pressable
                  key={e.user_id}
                  onPress={() => Linking.openURL(`tel:${e.phone}`)}
                  style={styles.expRow}
                  testID={`expiring-${e.phone}`}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.expName}>{e.name}</Text>
                    <Text style={styles.expSub}>+91 {e.phone} · {e.plan_name}</Text>
                  </View>
                  <View style={[styles.expBadge, { backgroundColor: e.expired || e.days_left === 0 ? "#FEE2E2" : "#FEF3C7" }]}>
                    <Text style={[styles.expBadgeTxt, { color: e.expired || e.days_left === 0 ? "#B91C1C" : "#B45309" }]}>
                      {e.expired ? "Expired" : e.days_left === 0 ? "Today" : `${e.days_left}d left`}
                    </Text>
                  </View>
                  <Ionicons name="call" size={18} color={colors.success} />
                </Pressable>
              ))
            )}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

function MetricCard({ label, value, icon, tint, onPress, testID }: any) {
  const styles = useStyles();
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.metricCard, { opacity: pressed ? 0.7 : 1 }]} testID={testID}>
      <View style={[styles.metricIcon, { backgroundColor: tint + "20" }]}>
        <Ionicons name={icon} size={20} color={tint} />
      </View>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 20, borderBottomLeftRadius: 24, borderBottomRightRadius: 24 },
  hello: { color: "#CCFBF1", fontSize: 12, letterSpacing: 0.5, textTransform: "uppercase" },
  name: { color: "#FFFFFF", fontSize: 22, fontWeight: "800", marginTop: 2 },
  logoutBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: "rgba(255,255,255,0.2)", alignItems: "center", justifyContent: "center" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  errorBox: { alignItems: "center", padding: 32, marginTop: 40 },
  retryBtn: { marginTop: 16, paddingHorizontal: 24, height: 44, borderRadius: 12, alignItems: "center", justifyContent: "center" },
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
  toolsRow: { flexDirection: "row", gap: 12 },
  tool: { flex: 1, padding: 14, backgroundColor: colors.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: colors.border, gap: 4 },
  toolTxt: { fontWeight: "800", color: colors.onSurface, marginTop: 6 },
  toolSub: { fontSize: 11, color: colors.muted },
  expCard: { padding: 16, backgroundColor: colors.surfaceSecondary, borderRadius: 16, borderWidth: 1, borderColor: colors.border, gap: 10 },
  expHeader: { flexDirection: "row", alignItems: "center", gap: 8 },
  expTitle: { flex: 1, fontSize: 15, fontWeight: "800", color: colors.onSurface },
  expCount: { minWidth: 26, height: 26, borderRadius: 13, paddingHorizontal: 8, alignItems: "center", justifyContent: "center" },
  expCountTxt: { color: "#FFFFFF", fontWeight: "800", fontSize: 12 },
  expEmpty: { color: colors.muted, fontSize: 13 },
  expRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.border },
  expName: { fontWeight: "700", color: colors.onSurface },
  expSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  expBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999 },
  expBadgeTxt: { fontSize: 11, fontWeight: "700" },
}));
