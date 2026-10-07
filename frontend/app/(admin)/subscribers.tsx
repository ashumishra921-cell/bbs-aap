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
import * as ImagePicker from "expo-image-picker";

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
  isp_user_id: string;
  isp_provider: string;
  expiry_date: string;
  plan_id: string;
  payment_mode: "cash" | "upi" | "free";
};

const EMPTY: Form = {
  phone: "", name: "", address: "", router_model: "", router_mac: "",
  security_deposit: "", installation_date: "", notes: "", isp_user_id: "", isp_provider: "", expiry_date: "", plan_id: "", payment_mode: "cash",
};

const CREATE_PAY_MODES: Form["payment_mode"][] = ["cash", "free"];

function parseBulkUsers(value: string) {
  const rows = value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const dataRows = rows[0]?.toLowerCase().includes("phone") ? rows.slice(1) : rows;
  const users: { phone: string; name: string; isp_user_id: string; isp_provider: string; address?: string }[] = [];
  const errors: string[] = [];
  dataRows.forEach((line, index) => {
    const [name = "", phone = "", isp_user_id = "", isp_provider = "", ...address] = line.split(",").map((v) => v.trim());
    if (!name || !/^\d{10}$/.test(phone) || !isp_user_id || !isp_provider) {
      errors.push(`Row ${index + 1}: Name, 10-digit phone, ISP ID और provider आवश्यक हैं`);
      return;
    }
    users.push({ name, phone, isp_user_id, isp_provider, address: address.join(", ") || undefined });
  });
  return { users, errors, total: dataRows.length };
}

export default function SubscribersList() {
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [plans, setPlans] = useState<any[]>([]);
  const [ispProviders, setIspProviders] = useState<any[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkResult, setBulkResult] = useState<{ created_count: number; error_count: number; errors: { row: number; message: string }[] } | null>(null);

  const [detail, setDetail] = useState<any | null>(null);
  const [planOpen, setPlanOpen] = useState(false);
  const [planId, setPlanId] = useState("");
  const [payMode, setPayMode] = useState<Form["payment_mode"]>("cash");
  const [paymentShot, setPaymentShot] = useState<{ uri: string; name: string; type: string } | null>(null);
  const [paymentUtr, setPaymentUtr] = useState("");
  const [paymentUploading, setPaymentUploading] = useState(false);
  const [paymentExpiryDate, setPaymentExpiryDate] = useState("");
  const [newIsp, setNewIsp] = useState("");

  const [confirmDel, setConfirmDel] = useState<any | null>(null);

  const isSuper = me?.role === "super_admin";
  const canManage = me?.role === "admin" || isSuper;

  const load = useCallback(async () => {
    try {
      const { user } = await loadAuth();
      setMe(user);
      const [s, p, providers] = await Promise.all([api.subscribers(), api.plans(), api.ispProviders()]);
      setItems(s);
      setPlans(p);
      setIspProviders(providers);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((u) =>
      (u.name || "").toLowerCase().includes(q) || (u.phone || "").includes(q) || (u.isp_user_id || "").toLowerCase().includes(q) || (u.isp_provider || "").toLowerCase().includes(q) || (u.address || "").toLowerCase().includes(q),
    );
  }, [items, query]);
  const bulkPreview = useMemo(() => parseBulkUsers(bulkText), [bulkText]);

  const set = (k: keyof Form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const openCreate = () => { setEditing(null); setNewIsp(""); setFormError(""); setForm(EMPTY); setFormOpen(true); };
  const openEdit = (u: any) => {
    setEditing(u);
    setFormError("");
    setForm({
      ...EMPTY,
      phone: u.phone, name: u.name || "", address: u.address || "", router_model: u.router_model || "",
      router_mac: u.router_mac || "", security_deposit: u.security_deposit != null ? String(u.security_deposit) : "",
      installation_date: u.installation_date || "", notes: u.notes || "", isp_user_id: u.isp_user_id || "", isp_provider: u.isp_provider || "",
    });
    setDetail(null);
    setFormOpen(true);
  };

  const save = async () => {
    setFormError("");
    if (!editing && form.phone.length < 10) { setFormError("10 अंकों का phone भरें"); return; }
    if (!form.name.trim()) { setFormError("नाम आवश्यक है"); return; }
    if (!form.isp_user_id.trim() || !form.isp_provider.trim()) { setFormError("ISP User ID और ISP Provider आवश्यक हैं"); return; }
    setSaving(true);
    const payload: Record<string, any> = {
      name: form.name.trim(),
      address: form.address.trim() || undefined,
      router_model: form.router_model.trim() || undefined,
      router_mac: form.router_mac.trim() || undefined,
      security_deposit: form.security_deposit ? Number(form.security_deposit) : undefined,
      installation_date: form.installation_date.trim() || undefined,
      notes: form.notes.trim() || undefined,
      isp_user_id: form.isp_user_id.trim(),
      isp_provider: form.isp_provider.trim(),
    };
    try {
      if (editing) {
        await api.updateSubscriber(editing.id, payload);
        toast.show("Subscriber updated ✓", "success");
      } else {
        await api.createSubscriber({ ...payload, phone: form.phone, plan_id: form.plan_id || undefined, payment_mode: form.payment_mode, expiry_date: form.expiry_date || undefined });
        toast.show(form.plan_id ? "Subscriber added & plan activated ✓" : "Subscriber added ✓", "success");
      }
      setFormOpen(false);
      load();
    } catch (e: any) { setFormError(e.message || "Customer add नहीं हुआ"); toast.show(e.message, "error"); }
    finally { setSaving(false); }
  };

  const openBulk = () => {
    setBulkText("");
    setBulkResult(null);
    setBulkOpen(true);
  };

  const importBulk = async () => {
    if (!bulkPreview.users.length) { toast.show("कम से कम एक सही customer row डालें", "error"); return; }
    if (bulkPreview.errors.length) { toast.show("पहले invalid rows ठीक करें", "error"); return; }
    setBulkSaving(true);
    try {
      const result = await api.createSubscribersBulk(bulkPreview.users);
      setBulkResult(result);
      if (result.created_count) await load();
      toast.show(`${result.created_count} customer add हुए${result.error_count ? ` · ${result.error_count} failed` : " ✓"}`, result.error_count ? "info" : "success");
    } catch (e: any) {
      toast.show(e.message || "Bulk import failed", "error");
    } finally {
      setBulkSaving(false);
    }
  };

  const openAssign = (u: any) => {
    setPlanId(""); setPayMode("cash"); setPaymentShot(null); setPaymentUtr(""); setPaymentExpiryDate(""); setPlanOpen(true); setDetail(u);
  };

  const addIspProvider = async () => {
    if (!newIsp.trim()) { toast.show("ISP provider नाम लिखें", "error"); return; }
    try {
      const provider = await api.createIspProvider(newIsp.trim());
      setIspProviders((list) => list.some((p) => p.id === provider.id) ? list : [...list, provider].sort((a, b) => a.name.localeCompare(b.name)));
      setForm((f) => ({ ...f, isp_provider: provider.name }));
      setNewIsp("");
      toast.show(`${provider.name} ISP added ✓`, "success");
    } catch (e: any) { toast.show(e.message || "ISP add नहीं हुआ", "error"); }
  };

  const pickPaymentScreenshot = async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) { toast.show("Screenshot चुनने के लिए Photos permission दें", "error"); return; }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.7, allowsEditing: false });
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    setPaymentShot({ uri: asset.uri, name: asset.fileName || `payment-${Date.now()}.jpg`, type: asset.mimeType || "image/jpeg" });
  };
  const assign = async () => {
    if (!detail || !planId) { toast.show("Plan चुनें", "error"); return; }
    if (payMode === "upi" && !paymentShot) { toast.show("UPI screenshot upload करें", "error"); return; }
    setSaving(true);
    try {
      let screenshot_path: string | undefined;
      if (payMode === "upi" && paymentShot) {
        setPaymentUploading(true);
        const upload = await api.uploadScreenshot(paymentShot.uri, paymentShot.name, paymentShot.type);
        screenshot_path = upload.path;
      }
      await api.createAdminPaymentEntry({ subscriber_id: detail.id, plan_id: planId, payment_mode: payMode as "cash" | "upi", screenshot_path, utr: paymentUtr.trim() || undefined, expiry_date: paymentExpiryDate.trim() || undefined });
      toast.show("Daily payment entry saved · plan active ✓", "success");
      setPlanOpen(false); setDetail(null);
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setSaving(false); setPaymentUploading(false); }
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
        <View style={styles.titleRow}>
          <Text style={styles.title}>Subscribers ({items.length})</Text>
          {isSuper && (
            <Pressable onPress={openBulk} style={styles.bulkHeaderBtn} testID="open-bulk-user-import-btn">
              <Ionicons name="people-circle-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.bulkHeaderText}>Bulk Add</Text>
            </Pressable>
          )}
        </View>
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

      {canManage && (
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
              <DetailRow icon="id-card" label="ISP User ID" value={detail?.isp_user_id} />
              <DetailRow icon="business" label="ISP Portal" value={detail?.isp_provider} />
              <DetailRow icon="location" label="Address" value={detail?.address} />
              <DetailRow icon="hardware-chip" label="Router" value={[detail?.router_model, detail?.router_mac].filter(Boolean).join(" · ")} />
              <DetailRow icon="cash" label="Security Deposit" value={detail?.security_deposit != null ? `₹${detail.security_deposit}` : undefined} />
              <DetailRow icon="calendar" label="Installed" value={detail?.installation_date} />
              <DetailRow icon="document-text" label="Notes" value={detail?.notes} />
            </View>
            {canManage && (
              <>
                <Pressable onPress={() => openAssign(detail)} style={[styles.primaryBtn, { backgroundColor: colors.brandPrimary }]} testID="assign-plan-btn">
                  <Ionicons name="cash-outline" size={18} color="#FFFFFF" />
                  <Text style={styles.primaryTxt}>Add Daily Payment</Text>
                </Pressable>
              </>
            )}
            {isSuper && (
              <>
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
            <Text style={styles.modalTitle} testID="customer-add-form-title">{editing ? "Edit Subscriber" : "Add Subscriber"}</Text>
            {!!formError && (
              <View style={styles.formError} testID="customer-add-error-msg">
                <Ionicons name="alert-circle" size={18} color={colors.error} />
                <Text style={styles.formErrorText}>{formError}</Text>
              </View>
            )}
            <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
              {!editing && canManage && (
                <>
                  <Text style={styles.label}>Phone *</Text>
                  <TextInput testID="sub-phone" placeholder="10-digit" placeholderTextColor={colors.muted} value={form.phone} onChangeText={(t) => set("phone")(t.replace(/[^0-9]/g, ""))} keyboardType="number-pad" maxLength={10} style={styles.input} />
                </>
              )}
              <Text style={styles.label}>Name *</Text>
              <TextInput testID="sub-name" placeholder="Full name" placeholderTextColor={colors.muted} value={form.name} onChangeText={set("name")} style={styles.input} />
              <Text style={styles.label}>ISP User ID *</Text>
              <TextInput testID="subscriber-isp-user-id" placeholder="Portal customer / user ID" placeholderTextColor={colors.muted} value={form.isp_user_id} onChangeText={set("isp_user_id")} style={styles.input} />
              <Text style={styles.label}>ISP Provider *</Text>
              <View style={styles.chips} testID="isp-provider-options">
                {ispProviders.map((provider) => (
                  <Pressable key={provider.id} onPress={() => set("isp_provider")(provider.name)} style={[styles.chip, form.isp_provider === provider.name && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]} testID={`isp-provider-${provider.id}`}>
                    <Text style={[styles.chipTxt, form.isp_provider === provider.name && { color: "#FFFFFF" }]}>{provider.name}</Text>
                  </Pressable>
                ))}
              </View>
              <View style={styles.addIspRow}>
                <TextInput testID="add-isp-provider-input" placeholder="Other ISP portal name" placeholderTextColor={colors.muted} value={newIsp} onChangeText={setNewIsp} style={[styles.input, { flex: 1, marginBottom: 0 }]} />
                <Pressable onPress={addIspProvider} style={styles.addIspBtn} testID="add-isp-provider-btn"><Text style={styles.addIspTxt}>Add ISP</Text></Pressable>
              </View>
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

              {!editing && isSuper && (
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
                        {CREATE_PAY_MODES.map((m) => (
                          <Pressable key={m} onPress={() => setForm((f) => ({ ...f, payment_mode: m }))} style={[styles.chip, form.payment_mode === m && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]} testID={`form-pay-${m}`}>
                            <Text style={[styles.chipTxt, form.payment_mode === m && { color: "#FFFFFF" }]}>{m.toUpperCase()}</Text>
                          </Pressable>
                        ))}
                      </View>
                      <Text style={styles.label}>Expiry Date Override (optional)</Text>
                      <TextInput testID="subscriber-expiry-date" placeholder="YYYY-MM-DD" placeholderTextColor={colors.muted} value={form.expiry_date} onChangeText={set("expiry_date")} style={styles.input} />
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

      {/* Super Admin bulk subscriber import */}
      <Modal visible={bulkOpen} transparent animationType="slide" onRequestClose={() => setBulkOpen(false)}>
        <KeyboardAvoidingView style={styles.modalBg} behavior={Platform.OS === "ios" ? "padding" : undefined} testID="bulk-user-import-modal">
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 16, maxHeight: "92%" }]}> 
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>Bulk Add Customers</Text>
            <Text style={styles.bulkHelp}>हर line: Name, Phone, ISP User ID, ISP Provider, Address (optional)</Text>
            <TextInput
              testID="bulk-user-csv-input"
              value={bulkText}
              onChangeText={(text) => { setBulkText(text); setBulkResult(null); }}
              placeholder={"Rahul,9876543210,ANO-101,Anonet,Delhi\nNeha,9876543211,GT-202,GTPL"}
              placeholderTextColor={colors.muted}
              multiline
              textAlignVertical="top"
              autoCorrect={false}
              style={styles.bulkInput}
            />
            <View style={styles.bulkSummary} testID="bulk-user-preview-table">
              <Text style={styles.bulkSummaryText}>Rows: {bulkPreview.total}</Text>
              <Text style={[styles.bulkSummaryText, { color: colors.success }]}>Ready: {bulkPreview.users.length}</Text>
              <Text style={[styles.bulkSummaryText, { color: bulkPreview.errors.length ? colors.error : colors.muted }]}>Errors: {bulkPreview.errors.length}</Text>
            </View>
            {bulkPreview.errors.slice(0, 3).map((error) => <Text key={error} style={styles.bulkError}>{error}</Text>)}
            {bulkResult && (
              <View style={styles.bulkResult} testID="bulk-user-import-result">
                <Text style={styles.bulkResultTitle}>{bulkResult.created_count} customer add हुए</Text>
                {bulkResult.errors.slice(0, 4).map((error) => <Text key={`${error.row}-${error.message}`} style={styles.bulkError}>Row {error.row}: {error.message}</Text>)}
              </View>
            )}
            <Pressable
              onPress={importBulk}
              disabled={bulkSaving || !bulkPreview.users.length || !!bulkPreview.errors.length}
              accessibilityState={{ disabled: bulkSaving || !bulkPreview.users.length || !!bulkPreview.errors.length }}
              style={[styles.primaryBtn, { backgroundColor: colors.brandPrimary, opacity: bulkSaving || !bulkPreview.users.length || !!bulkPreview.errors.length ? 0.55 : 1 }]}
              testID="submit-bulk-user-import-btn"
            >
              {bulkSaving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryTxt}>Import {bulkPreview.users.length || ""} Customers</Text>}
            </Pressable>
            <Pressable onPress={() => setBulkOpen(false)} style={styles.cancel} testID="close-bulk-user-import-btn"><Text style={{ color: colors.muted, fontWeight: "600" }}>Close</Text></Pressable>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Assign plan */}
      <Modal visible={planOpen} transparent animationType="slide" onRequestClose={() => setPlanOpen(false)}>
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>Add Daily Payment</Text>
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
              {(["cash", "upi"] as const).map((m) => (
                <Pressable key={m} onPress={() => setPayMode(m)} style={[styles.chip, payMode === m && { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }]} testID={`pay-${m}`}>
                  <Text style={[styles.chipTxt, payMode === m && { color: "#FFFFFF" }]}>{m.toUpperCase()}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={styles.label}>Expiry Date Override (optional)</Text>
            <TextInput testID="admin-payment-expiry-date" placeholder="YYYY-MM-DD · blank = plan validity" placeholderTextColor={colors.muted} value={paymentExpiryDate} onChangeText={setPaymentExpiryDate} style={styles.input} />
            {payMode === "upi" && (
              <>
                <Text style={styles.label}>UPI Screenshot *</Text>
                <Pressable onPress={pickPaymentScreenshot} style={[styles.uploadProof, { borderColor: paymentShot ? colors.success : colors.borderStrong }]} testID="admin-payment-screenshot">
                  <Ionicons name={paymentShot ? "checkmark-circle" : "image-outline"} size={22} color={paymentShot ? colors.success : colors.brandPrimary} />
                  <Text style={styles.uploadProofText}>{paymentShot ? "Screenshot selected ✓" : "Upload payment screenshot"}</Text>
                </Pressable>
                <Text style={styles.label}>UTR / Transaction ID (optional)</Text>
                <TextInput testID="admin-payment-utr" placeholder="UTR number" placeholderTextColor={colors.muted} value={paymentUtr} onChangeText={setPaymentUtr} style={styles.input} />
              </>
            )}
            <Pressable onPress={assign} disabled={saving || paymentUploading} style={[styles.primaryBtn, { backgroundColor: colors.brandPrimary, opacity: saving ? 0.8 : 1 }]} testID="confirm-assign-plan">
              {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryTxt}>{payMode === "upi" ? "Save UPI & Activate" : "Save Cash & Activate"}</Text>}
            </Pressable>
            <Pressable onPress={() => setPlanOpen(false)} style={styles.cancel} testID="cancel-admin-payment-btn"><Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text></Pressable>
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
  titleRow: { minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  bulkHeaderBtn: { minHeight: 44, paddingHorizontal: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  bulkHeaderText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "800" },
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
  formError: { marginTop: 12, minHeight: 44, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#FEE2E2" },
  formErrorText: { flex: 1, color: colors.error, fontSize: 12, fontWeight: "700" },
  bulkHelp: { marginTop: 8, color: colors.muted, fontSize: 12, lineHeight: 18 },
  bulkInput: { minHeight: 180, maxHeight: 260, marginTop: 12, borderRadius: 14, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, padding: 14, color: colors.onSurface, fontSize: 14, lineHeight: 21 },
  bulkSummary: { minHeight: 44, marginTop: 10, borderRadius: 12, backgroundColor: colors.surfaceTertiary, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8 },
  bulkSummaryText: { color: colors.onSurface, fontSize: 12, fontWeight: "800" },
  bulkError: { color: colors.error, fontSize: 11, marginTop: 5 },
  bulkResult: { marginTop: 10, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  bulkResultTitle: { color: colors.success, fontSize: 13, fontWeight: "800" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  addIspRow: { flexDirection: "row", gap: 8, alignItems: "center" },
  addIspBtn: { minWidth: 76, minHeight: 44, borderRadius: 12, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: 10 },
  addIspTxt: { color: "#FFFFFF", fontWeight: "800", fontSize: 12 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  chipTxt: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  planRow: { flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  uploadProof: { minHeight: 48, borderRadius: 12, borderWidth: 1, borderStyle: "dashed", backgroundColor: colors.surfaceTertiary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingHorizontal: 12 },
  uploadProofText: { color: colors.onSurface, fontWeight: "700", fontSize: 13 },
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
