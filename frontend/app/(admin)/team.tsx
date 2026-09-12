import { useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Modal, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Ionicons from "@react-native-vector-icons/ionicons";
import dayjs from "dayjs";

import { api, loadAuth, User } from "@/src/api";
import { useToast } from "@/src/components/Toast";
import { makeStyles, useTheme } from "@/src/theme";
import { mapsUrl } from "@/src/utils/location";

export default function TeamManage() {
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
  const [role, setRole] = useState<"team" | "admin">("team");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const { user } = await loadAuth();
      setMe(user);
      const t = await api.team();
      setItems(t);
    } finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const add = async () => {
    if (phone.length < 10 || !name.trim()) { toast.show("Fill all fields", "error"); return; }
    setSaving(true);
    try {
      await api.createTeam({ phone, name, role });
      toast.show("Team member added ✓", "success");
      setPhone(""); setName(""); setRole("team"); setOpen(false);
      load();
    } catch (e: any) { toast.show(e.message, "error"); }
    finally { setSaving(false); }
  };

  const del = async (id: string) => {
    try { await api.deleteTeam(id); toast.show("Removed", "success"); load(); }
    catch (e: any) { toast.show(e.message, "error"); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>Team ({items.length})</Text>
      </View>
      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 100 }}>
          {items.map((u) => (
            <View key={u.id} style={styles.card} testID={`team-${u.phone}`}>
              <View style={styles.avatar}>
                <Ionicons name={u.role === "admin" ? "shield-checkmark" : "person"} size={22} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{u.name}</Text>
                <Text style={styles.phone}>+91 {u.phone}</Text>
                <Text style={styles.roleTxt}>{u.role.toUpperCase()}</Text>
                {u.role === "team" && (
                  u.location?.updated_at ? (
                    <Pressable onPress={() => Linking.openURL(mapsUrl(u.location.lat, u.location.lng))} style={styles.locRow} testID={`loc-${u.phone}`}>
                      <Ionicons name="navigate" size={12} color={u.location_fresh ? colors.success : colors.muted} />
                      <Text style={[styles.locTxt, { color: u.location_fresh ? colors.success : colors.muted }]}>
                        {u.location_fresh ? "Live" : "Last seen"} · {dayjs(u.location.updated_at).format("DD MMM hh:mm A")} · Maps
                      </Text>
                    </Pressable>
                  ) : (
                    <Text style={[styles.locTxt, { color: colors.muted }]}>Location not shared</Text>
                  )
                )}
              </View>
              {(me?.role === "super_admin" || (me?.role === "admin" && u.role === "team")) && (
                <Pressable onPress={() => del(u.id)} style={styles.delBtn} testID={`del-${u.phone}`}>
                  <Ionicons name="trash" size={18} color={colors.error} />
                </Pressable>
              )}
            </View>
          ))}
        </ScrollView>
      )}

      <Pressable
        onPress={() => setOpen(true)}
        style={[styles.fab, { backgroundColor: colors.brandPrimary, bottom: insets.bottom + 24 }]}
        testID="add-team-fab"
      >
        <Ionicons name="add" size={28} color="#FFFFFF" />
      </Pressable>

      <Modal visible={open} transparent animationType="slide">
        <View style={styles.modalBg}>
          <View style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]}>
            <View style={styles.grabber} />
            <Text style={styles.modalTitle}>Add Team Member</Text>
            <Text style={styles.label}>Phone</Text>
            <TextInput testID="team-phone" placeholder="10-digit" placeholderTextColor={colors.muted} value={phone} onChangeText={(t) => setPhone(t.replace(/[^0-9]/g, ""))} keyboardType="number-pad" maxLength={10} style={styles.input} />
            <Text style={styles.label}>Name</Text>
            <TextInput testID="team-name" placeholder="Full name" placeholderTextColor={colors.muted} value={name} onChangeText={setName} style={styles.input} />
            <Text style={styles.label}>Role</Text>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Pressable onPress={() => setRole("team")} style={[styles.chip, role === "team" && { backgroundColor: colors.brandPrimary }]}>
                <Text style={[styles.chipTxt, role === "team" && { color: "#FFFFFF" }]}>TEAM</Text>
              </Pressable>
              {me?.role === "super_admin" && (
                <Pressable onPress={() => setRole("admin")} style={[styles.chip, role === "admin" && { backgroundColor: colors.brandPrimary }]}>
                  <Text style={[styles.chipTxt, role === "admin" && { color: "#FFFFFF" }]}>ADMIN</Text>
                </Pressable>
              )}
            </View>
            <Pressable onPress={add} disabled={saving} style={[styles.saveBtn, { backgroundColor: colors.brandPrimary, opacity: saving ? 0.8 : 1 }]} testID="save-team-btn">
              {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.saveTxt}>Add</Text>}
            </Pressable>
            <Pressable onPress={() => setOpen(false)} style={styles.cancel}><Text style={{ color: colors.muted, fontWeight: "600" }}>Cancel</Text></Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  header: { paddingHorizontal: 20, paddingBottom: 12, backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  card: { flexDirection: "row", gap: 12, alignItems: "center", padding: 14, backgroundColor: colors.surfaceSecondary, borderRadius: 14, borderWidth: 1, borderColor: colors.border },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  name: { fontWeight: "700", color: colors.onSurface },
  phone: { fontSize: 12, color: colors.muted, marginTop: 2 },
  roleTxt: { fontSize: 10, color: colors.brandPrimary, fontWeight: "800", marginTop: 3, letterSpacing: 0.5 },
  locRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  locTxt: { fontSize: 11, fontWeight: "600", marginTop: 2 },

  delBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  fab: { position: "absolute", right: 20, width: 56, height: 56, borderRadius: 28, alignItems: "center", justifyContent: "center", shadowColor: "#000", shadowOpacity: 0.2, shadowRadius: 10, elevation: 6 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  sheet: { backgroundColor: colors.surfaceSecondary, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20 },
  grabber: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: 12 },
  modalTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  label: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: 12, marginBottom: 6 },
  input: { height: 48, borderRadius: 12, backgroundColor: colors.surfaceTertiary, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 14, color: colors.onSurface, fontSize: 15 },
  chip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceTertiary },
  chipTxt: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  saveBtn: { marginTop: 20, height: 50, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  saveTxt: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  cancel: { marginTop: 8, height: 40, alignItems: "center", justifyContent: "center" },
}));
