import { Tabs } from "expo-router";
import Ionicons from "@react-native-vector-icons/ionicons";
import { Platform } from "react-native";
import { useTheme } from "@/src/theme";
import { useBadges } from "@/src/hooks/useBadges";

export default function TeamLayout() {
  const { colors } = useTheme();
  const { badges } = useBadges();
  const newTickets = badges.new_tickets || 0;
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surfaceSecondary, borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="assigned"
        options={{
          title: "Tickets",
          tabBarIcon: ({ color, size }) => <Ionicons name="briefcase" color={color} size={size} />,
          tabBarBadge: newTickets > 0 ? newTickets : undefined,
          tabBarBadgeStyle: { backgroundColor: colors.error, color: colors.onError, fontSize: 10, fontWeight: "700" },
        }}
      />
      <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: ({ color, size }) => <Ionicons name="person-circle" color={color} size={size} /> }} />
    </Tabs>
  );
}
