import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, Switch, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";

import { api } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

type Form = { name: string; speed_mbps: string; data_gb: string; validity_days: string; price: string; description: string };
const EMPTY: Form = { name: "", speed_mbps: "", data_gb: "0", validity_days: "30", price: "", description: "" };

export default function PlanEditor() {
  const router = useRouter();
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { setPlans(await api.plansAll()); } finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const set = (k: keyof Form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  const openCreate = () => { setEditing(null); setForm(EMPTY); setOpen(true); };
  const openEdit = (p: any) => {
    setEditing(p);
    setForm({ name: p.name, speed_mbps: String(p.speed_mbps), data_gb: String(p.data_gb), validity_days: String(p.validity_days), price: String(p.price), description: p.description || "" });
    setOpen(true);
  };

  const save = async () => {
    const payload = {
      name: form.name.trim(),
      speed_mbps: Number(form.speed_mbps),
      data_gb: Number(form.data_gb || 0),
      validity_days: Number(form.validity_days),
      price: Number(form.price),
      description: form.description.trim(),
    };
    if (!payload.name || !payload.speed_mbps || !payload.validity_days || !(payload.price >= 0) || Number.isNaN(payload.price)) {
      toast.show("Name, speed, validity और price भरें", "error");
      return;
    }
    setSaving(true);
    try {
      if (editing) await api.updatePlan(editing.id, payload);
      else await api.createPlan(payload);
      toast.show(editing ? "Plan updated ✓" : "Plan added ✓", "success");
      setOpen(false);
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setSaving(false); }
  };

  const toggleActive = async (p: any, v: boolean) => {
    setPlans((ps) => ps.map((x) => (x.id === p.id ? { ...x, active: v } : x)));
    try {
      await api.updatePlan(p.id, { active: v });
      toast.show(v ? `${p.name} अब customers को दिखेगा` : `${p.name} hide कर दिया`, "success");
    } catch (e: any) { toast.show(e.message, "error"); load(); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Pressable onPress={() => router.back()} style={styles.back} testID="plans-back">
          <Ionicons name="arrow-back" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Plan Editor</Text>
          <Text style={styles.sub}>Hidden plans customers को नहीं दिखते</Text>
        </View>
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 100 }}>
          {plans.map((p) => (
            <View key={p.id} style={[styles.card, p.active === false && { opacity: 0.6 }]} testID={`plan-row-${p.id}`}>
              <Pressable onPress={() => openEdit(p)} style={{ flex: 1 }} testID={`edit-plan-${p.id}`}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={styles.name}>{p.name}</Text>
                  {p.active === false && <View style={styles.hiddenBadge}><Text style={styles.hiddenTxt}>HIDDEN</Text></View>}
                </View>
                <Text style={styles.meta}>{p.speed_mbps} Mbps · {p.data_gb ? `${p.data_gb} GB` : "Unlimited"} · {p.validity_days} days</Text>
                {p.description ? <Text style={styles.desc} numberOfLines={1}>{p.description}</Text> : null}
              </Pressable>
              <View style={{ alignItems: "flex-end", gap: 6 }}>
                <Text style={styles.price}>₹{p.price}</Text>
                <Switch
                  testID={`plan-active-${p.id}`}
                  value={p.active !== false}
                  onValueChange={(v) => toggleActive(p, v)}
                  trackColor={{ true: colors.brandPrimary, false: colors.borderStrong }}
                  thumbColor="#FFFFFF"
                />
              </View>
            </View>
          ))}
        </ScrollView>
      )}

      <Pressable onPress={openCreate} style={[styles.fab, { backgroundColor: colors.brandPrimary, bottom: insets.bottom + 24 }]} testID="add-plan-fab">
        <Ionicons name="add" size={28} color="#FFFFFF" />
      </Pressable>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <KeyboardAvoidingView style={styles.modalBg} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 16, maxHeight: "90%" }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>{editing ? "Edit Plan" : "New Plan"}</Text>
            <ScrollView keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
              <Text style={styles.label}>Plan Name *</Text>
              <TextInput testID="plan-name" placeholder="e.g. Turbo 200" placeholderTextColor={colors.muted} value={form.name} onChangeText={set("name")} style={styles.input} />
              <View style={{ flexDirection: "row", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Speed (Mbps) *</Text>
                  <TextInput testID="plan-speed" placeholder="100" placeholderTextColor={colors.muted} value={form.speed_mbps} onChangeText={(t) => set("speed_mbps")(t.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Data (GB, 0 = Unlimited)</Text>
                  <TextInput testID="plan-data" placeholder="0" placeholderTextColor={colors.muted} value={form.data_gb} onChangeText={(t) => set("data_gb")(t.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} />
                </View>
              </View>
              <View style={{ flexDirection: "row", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Validity (days) *</Text>
                  <TextInput testID="plan-validity" placeholder="30" placeholderTextColor={colors.muted} value={form.validity_days} onChangeText={(t) => set("validity_days")(t.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.label}>Price (₹) *</Text>
                  <TextInput testID="plan-price" placeholder="799" placeholderTextColor={colors.muted} value={form.price} onChangeText={(t) => set("price")(t.replace(/[^0-9.]/g, ""))} keyboardType="decimal-pad" style={styles.input} />
                </View>
              </View>
              <Text style={styles.label}>Description</Text>
              <TextInput testID="plan-desc" placeholder="Best for families & streaming" placeholderTextColor={colors.muted} value={form.description} onChangeText={set("description")} style={styles.input} />
            </ScrollView>
            <Pressable onPress={save} disabled={saving} style={[styles.saveBtn, { backgroundColor: colors.brandPrimary, opacity: saving ? 0.8 : 1 }]} testID="save-plan-btn">
              {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.saveTxt}>{editing ? "Save Changes" : "Add Plan"}</Text>}
            </Pressable>
            <Pressable onPress={() => setOpen(false)} style={styles.cancel}><Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text></Pressable>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border },
  back: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  sub: { fontSize: 12, color: colors.muted },
  card: { flexDirection: "row", gap: 12, alignItems: "center", padding: 14, backgroundColor: colors.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: colors.border },
  name: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  meta: { fontSize: 12, color: colors.muted, marginTop: 2 },
  desc: { fontSize: 12, color: colors.onSurfaceSecondary, marginTop: 2 },
  price: { fontSize: 18, fontWeight: "800", color: colors.brandPrimary },
  hiddenBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border },
  hiddenTxt: { fontSize: 9, fontWeight: "800", color: colors.muted },
  fab: { position: "absolute", right: 20, width: 56, height: 56, borderRadius: 28, alignItems: "center", justifyContent: "center", elevation: 6 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  label: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: 12, marginBottom: 6 },
  input: { height: 48, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, color: colors.onSurface, fontSize: 15 },
  saveBtn: { marginTop: 16, height: 50, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  saveTxt: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  cancel: { marginTop: 8, height: 40, alignItems: "center", justifyContent: "center" },
}));
