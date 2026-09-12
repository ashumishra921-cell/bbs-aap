import type { ConfigContext, ExpoConfig } from "expo/config";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: config.name || "Broadband Solutions 24x7",
  slug: config.slug || "broadband-solutions-247",
  extra: { ...config.extra, backendUrl: process.env.EXPO_PUBLIC_BACKEND_URL },
});