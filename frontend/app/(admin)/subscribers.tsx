import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Alert, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api, loadAuth, User } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";

export default function SubscribersList() {
  const styles = useStyles();
  const { colors } = useTheme();
  const toast = useToast();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<any[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [address, setAddress] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmDel, setConfirmDel] = useState<any | null>(null);

  const isSuper = me?.role === "super_admin";

  const load = useCallback(async () => {
    try {
      const { user } = await loadAuth();
      setMe(user);
      const s = await api.subscribers();
      setItems(s);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const add = async () => {
    if (phone.length < 10 || !name.trim()) { toast.show("Phone और नाम भरें", "error"); return; }
    setSaving(true);
    try {
      await api.createSubscriber({ phone, name: name.trim(), address: address.trim() || undefined });
      toast.show("Subscriber added ✓", "success");
      setPhone(""); setName(""); setAddress(""); setOpen(false);
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setSaving(false); }
  };

  const doDelete = async (u: any) => {
    try { await api.deleteSubscriber(u.id); toast.show("Subscriber removed", "success"); load(); }
    catch (e: any) { toast.show(e.message, "error"); }
    finally { setConfirmDel(null); }
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
      </View>
      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : items.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="people-outline" size={60} color={colors.muted} />
          <Text style={{ color: colors.muted, marginTop: 8 }}>No subscribers yet</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 100 }}>
          {items.map((u) => (
            <View key={u.id} style={styles.card} testID={`sub-${u.phone}`}>
              <View style={styles.avatar}>
                <Ionicons name="person" size={22} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{u.name}</Text>
                <Text style={styles.phone}>+91 {u.phone}</Text>
                {u.active_plan ? (
                  <View style={styles.planBadge}>
                    <Ionicons name="wifi" size={11} color={colors.success} />
                    <Text style={styles.planTxt}>{u.active_plan} · till {dayjs(u.expires_at).format("DD MMM")}</Text>
                  </View>
                ) : (
                  <Text style={styles.noPlan}>No active plan</Text>
                )}
              </View>
              {isSuper && (
                <Pressable onPress={() => askDelete(u)} style={styles.delBtn} testID={`del-sub-${u.phone}`}>
                  <Ionicons name="trash" size={18} color={colors.error} />
                </Pressable>
              )}
            </View>
          ))}
        </ScrollView>
      )}

      {isSuper && (
        <Pressable
          onPress={() => setOpen(true)}
          style={[styles.fab, { backgroundColor: colors.brandPrimary, bottom: insets.bottom + 24 }]}
          testID="add-subscriber-fab"
        >
          <Ionicons name="person-add" size={24} color="#FFFFFF" />
        </Pressable>
      )}

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>Add Subscriber</Text>
            <Text style={styles.label}>Phone</Text>
            <TextInput testID="sub-phone" placeholder="10-digit" placeholderTextColor={colors.muted} value={phone} onChangeText={(t) => setPhone(t.replace(/[^0-9]/g, ""))} keyboardType="number-pad" maxLength={10} style={styles.input} />
            <Text style={styles.label}>Name</Text>
            <TextInput testID="sub-name" placeholder="Full name" placeholderTextColor={colors.muted} value={name} onChangeText={setName} style={styles.input} />
            <Text style={styles.label}>Address (optional)</Text>
            <TextInput testID="sub-address" placeholder="House no, area, city" placeholderTextColor={colors.muted} value={address} onChangeText={setAddress} style={styles.input} />
            <Pressable onPress={add} disabled={saving} style={[styles.saveBtn, { backgroundColor: colors.brandPrimary, opacity: saving ? 0.8 : 1 }]} testID="save-subscriber-btn">
              {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.saveTxt}>Add</Text>}
            </Pressable>
            <Pressable onPress={() => setOpen(false)} style={styles.cancel} testID="cancel-subscriber-btn"><Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text></Pressable>
          </View>
        </View>
      </Modal>

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

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 12, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  empty: { flex: 1, alignItems: "center", justifyContent: "center" },
  card: { flexDirection: "row", gap: 12, alignItems: "center", padding: 14, backgroundColor: colors.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: colors.border },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  name: { fontWeight: "700", color: colors.onSurface },
  phone: { fontSize: 12, color: colors.muted, marginTop: 2 },
  planBadge: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 6, alignSelf: "flex-start", backgroundColor: "#D1FAE5", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999 },
  planTxt: { fontSize: 10, color: "#065F46", fontWeight: "700" },
  noPlan: { fontSize: 11, color: colors.muted, marginTop: 6, fontStyle: "italic" },
  delBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  fab: { position: "absolute", right: 20, width: 56, height: 56, borderRadius: 28, alignItems: "center", justifyContent: "center", shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 10, elevation: 6 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  dialog: { backgroundColor: colors.surfaceSecondary, borderRadius: 20, padding: 20 },
  dlgBtn: { flex: 1, height: 46, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  label: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: 12, marginBottom: 6 },
  input: { height: 48, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, color: colors.onSurface, fontSize: 15 },
  saveBtn: { marginTop: 20, height: 50, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  saveTxt: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  cancel: { marginTop: 8, height: 40, alignItems: "center", justifyContent: "center" },
}));
