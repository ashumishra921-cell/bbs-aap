import { Linking, Pressable, Text, View } from "react-native";
import Ionicons from "@react-native-vector-icons/ionicons";

import { makeStyles, useTheme } from "@/src/theme";

export const HELPLINE_NUMBER = "8826004211";

export function callHelpline() {
  Linking.openURL(`tel:${HELPLINE_NUMBER}`);
}

export default function HelplineCard() {
  const styles = useStyles();
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={callHelpline}
      style={({ pressed }) => [styles.card, { opacity: pressed ? 0.8 : 1 }]}
      testID="helpline-card"
    >
      <View style={[styles.icon, { backgroundColor: colors.success }]}>
        <Ionicons name="call" size={22} color={colors.onSuccess} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.title}>Customer Helpline</Text>
        <Text style={styles.sub}>24×7 सहायता के लिए कॉल करें</Text>
      </View>
      <Text style={styles.number}>{HELPLINE_NUMBER}</Text>
    </Pressable>
  );
}

const useStyles = makeStyles((colors) => ({
  card: {
    marginTop: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 16,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
  },
  icon: { width: 44, height: 44, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  title: { color: colors.onSurface, fontWeight: "700" },
  sub: { color: colors.muted, fontSize: 12, marginTop: 2 },
  number: { color: colors.success, fontWeight: "800", fontSize: 14 },
}));
