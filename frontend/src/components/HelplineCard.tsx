import { Linking, Pressable, Text, View } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";

import { makeStyles, useTheme } from "@/src/theme";

export const HELPLINE_NUMBER = "8826004211";
const WHATSAPP_BRAND = "#25D366";

export function callHelpline() {
  Linking.openURL(`tel:${HELPLINE_NUMBER}`);
}

export function openWhatsApp() {
  const text = encodeURIComponent("नमस्ते, मुझे Broadband Solutions 24×7 से सहायता चाहिए।");
  Linking.openURL(`https://wa.me/91${HELPLINE_NUMBER}?text=${text}`);
}

export default function HelplineCard() {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <View style={styles.card} testID="helpline-card">
      <View style={styles.row}>
        <View style={[styles.icon, { backgroundColor: colors.brandTertiary }]}>
          <Ionicons name="headset" size={22} color={colors.brandPrimary} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Customer Helpline</Text>
          <Text style={styles.sub}>24×7 सहायता · {HELPLINE_NUMBER}</Text>
        </View>
      </View>
      <View style={styles.actions}>
        <Pressable
          onPress={callHelpline}
          style={({ pressed }) => [styles.btn, { backgroundColor: colors.success, opacity: pressed ? 0.8 : 1 }]}
          testID="helpline-call-btn"
        >
          <Ionicons name="call" size={18} color={colors.onSuccess} />
          <Text style={[styles.btnText, { color: colors.onSuccess }]}>Call</Text>
        </Pressable>
        <Pressable
          onPress={openWhatsApp}
          style={({ pressed }) => [styles.btn, { backgroundColor: WHATSAPP_BRAND, opacity: pressed ? 0.8 : 1 }]}
          testID="helpline-whatsapp-btn"
        >
          <Ionicons name="logo-whatsapp" size={18} color="#FFFFFF" />
          <Text style={[styles.btnText, { color: "#FFFFFF" }]}>WhatsApp</Text>
        </Pressable>
      </View>
    </View>
  );
}

const useStyles = makeStyles((colors) => ({
  card: {
    marginTop: 16,
    padding: 16,
    gap: 14,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  icon: { width: 44, height: 44, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  title: { color: colors.onSurface, fontWeight: "700" },
  sub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  actions: { flexDirection: "row", gap: 10 },
  btn: {
    flex: 1,
    height: 44,
    borderRadius: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  btnText: { fontWeight: "700", fontSize: 14 },
}));
