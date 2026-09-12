import { useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, Pressable, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";
import { api, loadAuth, PaymentHistoryItem } from "@/src/api";
import { useLiveRefresh } from "@/src/hooks/useLiveRefresh";
import { makeStyles, useTheme } from "@/src/theme";

export default function PaymentHistoryScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [admin, setAdmin] = useState(false);
  const [mode, setMode] = useState("all");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<PaymentHistoryItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const visibleCount = useRef(40);
  const load = useCallback(async (more = false) => {
    const request = ++generation.current;
    if (more) setLoadingMore(true);
    try {
      const { user } = await loadAuth();
      const targetCount = more ? 40 : Math.max(40, visibleCount.current);
      let rows: PaymentHistoryItem[] = [];
      let moreAvailable = true;
      while (rows.length < targetCount && moreAvailable) {
        const page = await api.paymentHistory(mode, search, (more ? visibleCount.current : 0) + rows.length, Math.min(100, targetCount - rows.length));
        if (request !== generation.current) return;
        rows = [...rows, ...page.items];
        moreAvailable = page.has_more && page.items.length > 0;
      }
      const result = { items: rows, has_more: moreAvailable };
      if (request !== generation.current) return;
      setAdmin(user?.role === "admin" || user?.role === "super_admin");
      setItems(old => more ? [...old, ...result.items.filter(row => !old.some(i => i.id === row.id))] : result.items);
      visibleCount.current = (more ? visibleCount.current : 0) + result.items.length;
      setHasMore(result.has_more);
      setError("");
    } catch (e: any) { if (request === generation.current) setError(e.message || "Payments load नहीं हुए"); }
    finally { if (request === generation.current) { setLoading(false); setRefreshing(false); setLoadingMore(false); } }
  }, [mode, search]);
  useEffect(() => { const timer = setTimeout(() => setSearch(query.trim()), 300); return () => clearTimeout(timer); }, [query]);
  useEffect(() => { visibleCount.current = 40; setLoading(true); setItems([]); void load(); }, [load]);
  useLiveRefresh(useCallback(async () => { if (!loadingMore) await load(); }, [load, loadingMore]));

  return <KeyboardAvoidingView style={[styles.page, { paddingTop: insets.top }]} behavior={Platform.OS === "ios" ? "padding" : undefined}>
    <View style={styles.header}>
      <Pressable testID="payment-history-back" onPress={() => router.canGoBack() ? router.back() : router.replace(admin ? "/(admin)/overview" : "/(subscriber)/home")} style={styles.back}><Ionicons name="chevron-back" size={24} color={colors.onSurface} /></Pressable>
      <View style={{ flex: 1 }}><Text style={styles.title} testID="payment-history-title">Payment history</Text><Text style={styles.sub} testID="payment-history-subtitle">{admin ? "All customers · UPI & Cash" : "Your payments · UPI & Cash"}</Text></View>
    </View>
    <View style={styles.filters}>
      <View style={styles.search}><Ionicons name="search-outline" size={20} color={colors.muted} /><TextInput testID="payment-history-search" value={query} onChangeText={setQuery} placeholder={admin ? "Customer name, phone or plan" : "Search plan"} placeholderTextColor={colors.muted} style={styles.input} /></View>
      <View style={styles.modes}>{["all", "upi", "cash", "free"].map(value => <Pressable key={value} testID={`history-filter-${value}`} accessibilityRole="button" accessibilityState={{ selected: mode === value }} onPress={() => setMode(value)} style={[styles.chip, mode === value && { backgroundColor: colors.brandPrimary }]}><Text style={[styles.chipText, mode === value && { color: colors.onBrandPrimary }]}>{value.toUpperCase()}</Text></Pressable>)}</View>
    </View>
    {!!error && <View style={styles.error} testID="payment-history-error"><Text style={{ color: colors.error }}>{error}</Text><Pressable testID="payment-history-retry" onPress={() => load()} style={styles.back}><Text style={styles.link}>Retry</Text></Pressable></View>}
    {loading ? <ActivityIndicator testID="payment-history-loading" style={{ marginTop: 32 }} color={colors.brandPrimary} /> : <FlatList
      testID="payment-history-list" data={items} keyExtractor={item => item.id} keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 32, gap: 12 }}
      refreshing={refreshing} onRefresh={() => { setRefreshing(true); void load(); }}
      ListEmptyComponent={!error ? <Text style={styles.empty} testID="payment-history-empty">कोई payment record नहीं मिला</Text> : null}
      renderItem={({ item }) => <PaymentRow item={item} admin={admin} onPress={() => router.push(`/invoice/${item.invoice_id}`)} />}
      ListFooterComponent={hasMore ? <Pressable testID="payment-history-more" disabled={loadingMore} onPress={() => load(true)} style={styles.more}>{loadingMore ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.link}>Load more</Text>}</Pressable> : null}
    />}
  </KeyboardAvoidingView>;
}

function PaymentRow({ item, admin, onPress }: { item: PaymentHistoryItem; admin: boolean; onPress: () => void }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const tint = item.status === "paid" || item.status === "approved" ? colors.success : item.status === "rejected" || item.status === "failed" ? colors.error : colors.warning;
  return <Pressable testID={`history-row-${item.id}`} onPress={onPress} disabled={!item.invoice_id} style={({ pressed }) => [styles.card, { opacity: pressed ? 0.75 : 1 }]}>
    <View style={styles.row}>
      <View style={styles.icon}><Ionicons name={item.payment_mode === "cash" ? "cash-outline" : item.payment_mode === "free" ? "gift-outline" : "qr-code-outline"} size={22} color={colors.brandPrimary} /></View>
      <View style={{ flex: 1 }}><Text style={styles.plan} testID={`history-plan-${item.id}`}>{item.plan_name}</Text><Text style={styles.sub} testID={`history-date-${item.id}`}>{dayjs(item.created_at).format("DD MMM YYYY, hh:mm A")}</Text></View>
      <Text style={styles.amount} testID={`history-amount-${item.id}`}>₹{item.amount.toLocaleString("en-IN")}</Text>
    </View>
    {admin && <Text style={styles.customer} testID={`history-customer-${item.id}`}>{item.user_name} · {item.user_phone}</Text>}
    <View style={styles.row}><Text style={styles.mode} testID={`history-mode-${item.id}`}>{item.payment_mode.toUpperCase()}</Text><Text style={[styles.status, { color: tint }]} testID={`history-status-${item.id}`}>{item.status === "pending" ? "Verification pending" : item.status.toUpperCase()}</Text>{!!item.invoice_id && <Ionicons name="chevron-forward" size={18} color={colors.muted} />}</View>
    {!!item.reject_reason && <Text style={styles.sub} testID={`history-reason-${item.id}`}>{item.reject_reason}</Text>}
  </Pressable>;
}

const useStyles = makeStyles(colors => ({
  page: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", padding: 12, gap: 6, backgroundColor: colors.surfaceSecondary },
  back: { minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  sub: { fontSize: 12, lineHeight: 18, color: colors.muted, marginTop: 3 },
  filters: { padding: 16, gap: 12, backgroundColor: colors.surfaceSecondary },
  search: { flexDirection: "row", alignItems: "center", gap: 10, borderRadius: 12, backgroundColor: colors.surfaceTertiary, paddingHorizontal: 12 },
  input: { flex: 1, minWidth: 0, minHeight: 46, color: colors.onSurface, fontSize: 14 },
  modes: { flexDirection: "row", gap: 8 },
  chip: { flex: 1, minHeight: 44, alignItems: "center", justifyContent: "center", borderRadius: 12, backgroundColor: colors.surfaceTertiary },
  chipText: { color: colors.muted, fontWeight: "700", fontSize: 12 },
  error: { paddingHorizontal: 16, flexDirection: "row", alignItems: "center", flexWrap: "wrap" },
  empty: { textAlign: "center", color: colors.muted, paddingVertical: 40 },
  card: { padding: 16, gap: 12, borderRadius: 16, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  icon: { width: 42, height: 42, borderRadius: 12, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  plan: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  amount: { fontSize: 17, fontWeight: "800", color: colors.brandPrimary, flexShrink: 1 },
  customer: { color: colors.onSurfaceSecondary, fontSize: 13, lineHeight: 20 },
  mode: { color: colors.brandPrimary, fontSize: 12, fontWeight: "800" },
  status: { flex: 1, textAlign: "right", fontSize: 12, fontWeight: "700" },
  more: { minHeight: 48, alignItems: "center", justifyContent: "center", marginTop: 12 },
  link: { color: colors.brandPrimary, fontWeight: "700" },
}));