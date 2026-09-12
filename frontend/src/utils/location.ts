import * as Location from "expo-location";
import { Linking, Platform } from "react-native";

export type LocationResult =
  | { ok: true; lat: number; lng: number }
  | { ok: false; reason: "denied" | "blocked" | "unavailable" };

/**
 * Permission-aware one-shot location fetch.
 * Checks first, asks at most once, and reports "blocked" so callers can show an Open Settings button.
 */
export async function getCurrentLocation(): Promise<LocationResult> {
  try {
    let perm = await Location.getForegroundPermissionsAsync();
    if (!perm.granted) {
      if (!perm.canAskAgain) return { ok: false, reason: "blocked" };
      perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) return { ok: false, reason: perm.canAskAgain ? "denied" : "blocked" };
    }
    const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    return { ok: true, lat: pos.coords.latitude, lng: pos.coords.longitude };
  } catch {
    return { ok: false, reason: "unavailable" };
  }
}

export function openAppSettings() {
  if (Platform.OS !== "web") Linking.openSettings();
}

export function mapsUrl(lat: number, lng: number) {
  return `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
}
