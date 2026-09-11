import { useFocusEffect } from "expo-router";
import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api, loadAuth, User } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

type Form = {
  phone: string;
  name: string;
  address: string;
  router_model: string;
  router_mac: string;
  security_deposit: string;
  installation_date: string;
  notes: string;
  plan_id: string;
  payment_mode: "cash" | "upi" | "free";
};

const EMPTY: Form = {
  phone: "", name: "", address: "", router_model: "", router_mac: "",
  security_deposit: "", installation_date: "", notes: "", plan_id: "", payment_mode: "cash",
};

const PAY_MODES: Form["payment_mode"][] = ["cash", "upi", "free"];

export default function SubscribersList() {
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [plans, setPlans] = useState<any[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [saving, setSaving] = useState(false);

  const [detail, setDetail] = useState<any | null>(null);
  const [planOpen, setPlanOpen] = useState(false);
  const [planId, setPlanId] = useState("");
  const [payMode, setPayMode] = useState<Form["payment_mode"]>("cash");

  const [confirmDel, setConfirmDel] = useState<any | null>(null);

  const isSuper = me?.role === "super_admin";

  const load = useCallback(async () => {
    try {
      const { user } = await loadAuth();
      setMe(user);
      const [s, p] = await Promise.all([api.subscribers(), api.plans()]);
      setItems(s);
      setPlans(p);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((u) =>
      (u.name || "").toLowerCase().includes(q) || (u.phone || "").includes(q) || (u.address || "").toLowerCase().includes(q),
    );
  }, [items, query]);

  const set = (k: keyof Form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const openCreate = () => { setEditing(null); setForm(EMPTY); setFormOpen(true); };
  const openEdit = (u: any) => {
    setEditing(u);
    setForm({
      ...EMPTY,
      phone: u.phone, name: u.name || "", address: u.address || "", router_model: u.router_model || "",
      router_mac: u.router_mac || "", security_deposit: u.security_deposit != null ? String(u.security_deposit) : "",
      installation_date: u.installation_date || "", notes: u.notes || "",
    });
    setDetail(null);
    setFormOpen(true);
  };

  const save = async () => {
    if (!editing && form.phone.length < 10) { toast.show("10 अंकों का phone भरें", "error"); return; }
    if (!form.name.trim()) { toast.show("नाम आवश्यक है", "error"); return; }
    setSaving(true);
    const payload: Record<string, any> = {
      name: form.name.trim(),
      address: form.address.trim() || undefined,
      router_model: form.router_model.trim() || undefined,
      router_mac: form.router_mac.trim() || undefined,
      security_deposit: form.security_deposit ? Number(form.security_deposit) : undefined,
      installation_date: form.installation_date.trim() || undefined,
      notes: form.notes.trim() || undefined,
    };
    try {
      if (editing) {
        await api.updateSubscriber(editing.id, payload);
        toast.show("Subscriber updated ✓", "success");
      } else {
        await api.createSubscriber({ ...payload, phone: form.phone, plan_id: form.plan_id || undefined, payment_mode: form.payment_mode });
        toast.show(form.plan_id ? "Subscriber added & plan activated ✓" : "Subscriber added ✓", "success");
      }
      setFormOpen(false);
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setSaving(false); }
  };

  const openAssign = (u: any) => { setPlanId(""); setPayMode("cash"); setPlanOpen(true); setDetail(u); };
  const assign = async () => {
    if (!detail || !planId) { toast.show("Plan चुनें", "error"); return; }
    setSaving(true);
    try {
      await api.assignPlan(detail.id, planId, payMode);
      toast.show("Plan activated ✓", "success");
      setPlanOpen(false); setDetail(null);
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setSaving(false); }
  };

  const doDelete = async (u: any) => {
    try { await api.deleteSubscriber(u.id); toast.show("Subscriber removed", "success"); load(); }
    catch (e: any) { toast.show(e.message, "error"); }
    finally { setConfirmDel(null); setDetail(null); }
  };
  const askDelete = (u: any) => {
    if (Platform.OS === "web") { setConfirmDel(u); return; }
    Alert.alert("Delete subscriber?", `${u.name} (+91 ${u.phone}) को हटाया जाएगा।`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: () => doDelete(u) },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>Subscribers ({items.length})</Text>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={18} color={colors.muted} />
          <TextInput
            testID="subscriber-search"
            placeholder="नाम, phone या address खोजें"
            placeholderTextColor={colors.muted}
            value={query}
            onChangeText={setQuery}
            style={styles.searchInput}
            autoCorrect={false}
          />
          {query.length > 0 && (
            <Pressable onPress={() => setQuery("")} testID="clear-search" hitSlop={8}>
              <Ionicons name="close-circle" size={18} color={colors.muted} />
            </Pressable>
          )}
        </View>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : filtered.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="people-outline" size={60} color={colors.muted} />
          <Text style={{ color: colors.muted, marginTop: 8 }}>{query ? "कोई subscriber नहीं मिला" : "No subscribers yet"}</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 100 }} keyboardShouldPersistTaps="handled">
          {filtered.map((u) => (
            <Pressable key={u.id} onPress={() => setDetail(u)} style={({ pressed }) => [styles.card, { opacity: pressed ? 0.8 : 1 }]} testID={`sub-${u.phone}`}>
              <View style={styles.avatar}>
                <Ionicons name="person" size={22} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{u.name}</Text>
                <Text style={styles.phone}>+91 {u.phone}{u.address ? ` · ${u.address}` : ""}</Text>
                {u.active_plan ? (
                  <View style={styles.planBadge}>
                    <Ionicons name="wifi" size={11} color={colors.success} />
                    <Text style={styles.planTxt}>{u.active_plan} · till {dayjs(u.expires_at).format("DD MMM")}</Text>
                  </View>
                ) : (
                  <Text style={styles.noPlan}>No active plan</Text>
                )}
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          ))}
        </ScrollView>
      )}

      {isSuper && (
        <Pressable onPress={openCreate} style={[styles.fab, { backgroundColor: colors.brandPrimary, bottom: insets.bottom + 24 }]} testID="add-subscriber-fab">
          <Ionicons name="person-add" size={24} color="#FFFFFF" />
        </Pressable>
      )}

      {/* Detail sheet */}
      <Modal visible={!!detail && !planOpen && !formOpen} transparent animationType="slide" onRequestClose={() => setDetail(null)}>
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle} testID="detail-name">{detail?.name}</Text>
            <Text style={styles.modalSub}>+91 {detail?.phone}</Text>
            <View style={styles.detailGrid}>
              <DetailRow icon="wifi" label="Plan" value={detail?.active_plan ? `${detail.active_plan} · till ${dayjs(detail.expires_at).format("DD MMM YYYY")}` : "No active plan"} />
              <DetailRow icon="location" label="Address" value={detail?.address} />
              <DetailRow icon="hardware-chip" label="Router" value={[detail?.router_model, detail?.router_mac].filter(Boolean).join(" · ")} />
              <DetailRow icon="cash" label="Security Deposit" value={detail?.security_deposit != null ? `₹${detail.security_deposit}` : undefined} />
              <DetailRow icon="calendar" label="Installed" value={detail?.installation_date} />
              <DetailRow icon="document-text" label="Notes" value={detail?.notes} />
            </View>
            {isSuper && (
              <>
                <Pressable onPress={() => openAssign(detail)} style={[styles.primaryBtn, { backgroundColor: colors.brandPrimary }]} testID="assign-plan-btn">
                  <Ionicons name="flash" size={18} color="#FFFFFF" />
                  <Text style={styles.primaryTxt}>{detail?.active_plan ? "Renew / Change Plan" : "Assign Plan"}</Text>
                </Pressable>
                <View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}>
                  <Pressable onPress={() => openEdit(detail)} style={[styles.secBtn, { borderColor: colors.brandPrimary }]} testID="edit-subscriber-btn">
                    <Ionicons name="create-outline" size={18} color={colors.brandPrimary} />
                    <Text style={[styles.secTxt, { color: colors.brandPrimary }]}>Edit</Text>
                  </Pressable>
                  <Pressable onPress={() => askDelete(detail)} style={[styles.secBtn, { borderColor: colors.error }]} testID="delete-subscriber-btn">
                    <Ionicons name="trash-outline" size={18} color={colors.error} />
                    <Text style={[styles.secTxt, { color: colors.error }]}>Delete</Text>
                  </Pressable>
                </View>
              </>
            )}
            <Pressable onPress={() => setDetail(null)} style={styles.cancel} testID="close-detail-btn"><Text style={{ color: colors.muted, fontWeight: "600" }}>Close</Text></Pressable>
          </View>
        </View>
      </Modal>

      {/* Create / Edit form */}
      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <KeyboardAvoidingView style={styles.modalBg} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 16, maxHeight: "92%" }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>{editing ? "Edit Subscriber" : "Add Subscriber"}</Text>
            <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
              {!editing && (
                <>
                  <Text style={styles.label}>Phone *</Text>
                  <TextInput testID="sub-phone" placeholder="10-digit" placeholderTextColor={colors.muted} value={form.phone} onChangeText={(t) => set("phone")(t.replace(/[^0-9]/g, ""))} keyboardType="number-pad" maxLength={10} style={styles.input} />
                </>
              )}
              <Text style={styles.label}>Name *</Text>
              <TextInput testID="sub-name" placeholder="Full name" placeholderTextColor={colors.muted} value={form.name} onChangeText={set("name")} style={styles.input} />
              <Text style={styles.label}>Address</Text>
              <TextInput testID="sub-address" placeholder="House no, area, city" placeholderTextColor={colors.muted} value={form.address} onChangeText={set("address")} style={styles.input} />
              <View style={{ flexDirection: "row", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Router Model</Text>
                  <TextInput testID="sub-router-model" placeholder="TP-Link AC1200" placeholderTextColor={colors.muted} value={form.router_model} onChangeText={set("router_model")} style={styles.input} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Router MAC / Serial</Text>
                  <TextInput testID="sub-router-mac" placeholder="AA:BB:CC:.." placeholderTextColor={colors.muted} value={form.router_mac} onChangeText={set("router_mac")} autoCapitalize="characters" style={styles.input} />
                </View>
              </View>
              <View style={{ flexDirection: "row", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Security Deposit (₹)</Text>
                  <TextInput testID="sub-deposit" placeholder="1500" placeholderTextColor={colors.muted} value={form.security_deposit} onChangeText={(t) => set("security_deposit")(t.replace(/[^0-9.]/g, ""))} keyboardType="decimal-pad" style={styles.input} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Installation Date</Text>
                  <TextInput testID="sub-install-date" placeholder="DD-MM-YYYY" placeholderTextColor={colors.muted} value={form.installation_date} onChangeText={set("installation_date")} style={styles.input} />
                </View>
              </View>
              <Text style={styles.label}>Notes</Text>
              <TextInput testID="sub-notes" placeholder="Landmark, contact person, etc." placeholderTextColor={colors.muted} value={form.notes} onChangeText={set("notes")} style={styles.input} />

              {!editing && (
                <>
                  <Text style={styles.label}>Activate Plan (optional)</Text>
                  <View style={styles.chips}>
                    {plans.map((p) => (
                      <Pressable key={p.id} onPress={() => set("plan_id")(form.plan_id === p.id ? "" : p.id)} style={[styles.chip, form.plan_id === p.id && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]} testID={`form-plan-${p.id}`}>
                        <Text style={[styles.chipTxt, form.plan_id === p.id && { color: "#FFFFFF" }]}>{p.name} · ₹{p.price}</Text>
                      </Pressable>
                    ))}
                  </View>
                  {form.plan_id && (
                    <>
                      <Text style={styles.label}>Payment Mode</Text>
                      <View style={styles.chips}>
                        {PAY_MODES.map((m) => (
                          <Pressable key={m} onPress={() => setForm((f) => ({ ...f, payment_mode: m }))} style={[styles.chip, form.payment_mode === m && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]} testID={`form-pay-${m}`}>
                            <Text style={[styles.chipTxt, form.payment_mode === m && { color: "#FFFFFF" }]}>{m.toUpperCase()}</Text>
                          </Pressable>
                        ))}
                      </View>
                    </>
                  )}
                </>
              )}
            </ScrollView>
            <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, { backgroundColor: colors.brandPrimary, opacity: saving ? 0.8 : 1 }]} testID="save-subscriber-btn">
              {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryTxt}>{editing ? "Save" : "Add"}</Text>}
            </Pressable>
            <Pressable onPress={() => setFormOpen(false)} style={styles.cancel} testID="cancel-subscriber-btn"><Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text></Pressable>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Assign plan */}
      <Modal visible={planOpen} transparent animationType="slide" onRequestClose={() => setPlanOpen(false)}>
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>Assign Plan</Text>
            <Text style={styles.modalSub}>{detail?.name} · +91 {detail?.phone}</Text>
            <Text style={styles.label}>Select Plan</Text>
            <View style={{ gap: 8 }}>
              {plans.map((p) => (
                <Pressable key={p.id} onPress={() => setPlanId(p.id)} style={[styles.planRow, planId === p.id && { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary }]} testID={`assign-plan-${p.id}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.name}>{p.name}</Text>
                    <Text style={styles.phone}>{p.speed_mbps} Mbps · {p.data_gb ? `${p.data_gb} GB` : "Unlimited"} · {p.validity_days} days</Text>
                  </View>
                  <Text style={styles.price}>₹{p.price}</Text>
                  <Ionicons name={planId === p.id ? "radio-button-on" : "radio-button-off"} size={20} color={planId === p.id ? colors.brandPrimary : colors.muted} />
                </Pressable>
              ))}
            </View>
            <Text style={styles.label}>Payment Mode</Text>
            <View style={styles.chips}>
              {PAY_MODES.map((m) => (
                <Pressable key={m} onPress={() => setPayMode(m)} style={[styles.chip, payMode === m && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]} testID={`pay-${m}`}>
                  <Text style={[styles.chipTxt, payMode === m && { color: "#FFFFFF" }]}>{m.toUpperCase()}</Text>
                </Pressable>
              ))}
            </View>
            <Pressable onPress={assign} disabled={saving} style={[styles.primaryBtn, { backgroundColor: colors.brandPrimary, opacity: saving ? 0.8 : 1 }]} testID="confirm-assign-plan">
              {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryTxt}>Activate Plan</Text>}
            </Pressable>
            <Pressable onPress={() => setPlanOpen(false)} style={styles.cancel}><Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text></Pressable>
          </View>
        </View>
      </Modal>

      {/* Web delete confirm */}
      <Modal visible={!!confirmDel} transparent animationType="fade" onRequestClose={() => setConfirmDel(null)}>
        <View style={[styles.modalBg, { justifyContent: "center", padding: 24 }]}>
          <View style={styles.dialog}>
            <Text style={styles.modalTitle}>Delete subscriber?</Text>
            <Text style={{ color: colors.muted, marginTop: 8 }}>{confirmDel?.name} (+91 {confirmDel?.phone}) को हटाया जाएगा।</Text>
            <View style={{ flexDirection: "row", gap: 10, marginTop: 20 }}>
              <Pressable onPress={() => setConfirmDel(null)} style={[styles.dlgBtn, { backgroundColor: colors.surfaceTertiary }]} testID="cancel-delete-btn">
                <Text style={{ color: colors.onSurface, fontWeight: "700" }}>Cancel</Text>
              </Pressable>
              <Pressable onPress={() => doDelete(confirmDel)} style={[styles.dlgBtn, { backgroundColor: colors.error }]} testID="confirm-delete-btn">
                <Text style={{ color: colors.onError, fontWeight: "700" }}>Delete</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function DetailRow({ icon, label, value }: { icon: any; label: string; value?: string }) {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View style={styles.detailRow}>
      <Ionicons name={icon} size={16} color={colors.brandPrimary} />
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={[styles.detailValue, !value && { color: colors.muted, fontStyle: "italic" }]} numberOfLines={2}>{value || "—"}</Text>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 12, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 10 },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  searchBox: { flexDirection: "row", alignItems: "center", gap: 8, height: 44, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 12 },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 15, height: 44 },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  card: { flexDirection: "row", gap: 12, alignItems: "center", padding: 14, backgroundColor: colors.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: colors.border },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  name: { fontWeight: "700", color: colors.onSurface },
  phone: { fontSize: 12, color: colors.muted, marginTop: 2 },
  price: { fontWeight: "800", color: colors.brandPrimary, marginRight: 8 },
  planBadge: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 6, alignSelf: "flex-start", backgroundColor: "#D1FAE5", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  planTxt: { fontSize: 10, color: "#065F46", fontWeight: "700" },
  noPlan: { fontSize: 11, color: colors.muted, marginTop: 6, fontStyle: "italic" },
  fab: { position: "absolute", right: 20, width: 56, height: 56, borderRadius: 28, alignItems: "center", justifyContent: "center", shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 10, elevation: 6 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  dialog: { backgroundColor: colors.surfaceSecondary, borderRadius: 20, padding: 20 },
  dlgBtn: { flex: 1, height: 46, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  modalSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  label: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: 12, marginBottom: 6 },
  input: { height: 48, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, color: colors.onSurface, fontSize: 15 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  chipTxt: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  planRow: { flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  primaryBtn: { marginTop: 16, height: 50, borderRadius: 14, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center" },
  primaryTxt: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  secBtn: { flex: 1, height: 46, borderRadius: 12, borderWidth: 1, flexDirection: "row", gap: 6, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary },
  secTxt: { fontWeight: "700" },
  cancel: { marginTop: 8, height: 40, alignItems: "center", justifyContent: "center" },
  detailGrid: { marginTop: 14, gap: 10 },
  detailRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  detailLabel: { width: 110, fontSize: 12, color: colors.muted, fontWeight: "600" },
  detailValue: { flex: 1, fontSize: 13, color: colors.onSurface, fontWeight: "600" },
}));
