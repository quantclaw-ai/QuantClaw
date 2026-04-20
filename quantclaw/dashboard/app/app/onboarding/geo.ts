export interface GeoInfo {
  country: string;
  isChina: boolean;
}

export async function detectRegion(): Promise<GeoInfo> {
  try {
    // Try multiple free geo APIs with short timeouts
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);

    const res = await fetch("https://ipapi.co/json/", { signal: controller.signal });
    clearTimeout(timeout);

    if (res.ok) {
      const data = await res.json();
      const country = data.country_code || "";
      return { country, isChina: country === "CN" };
    }
  } catch {
    // Fallback: try alternative
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 3000);

      const res = await fetch("https://api.country.is/", { signal: controller.signal });
      clearTimeout(timeout);

      if (res.ok) {
        const data = await res.json();
        const country = data.country || "";
        return { country, isChina: country === "CN" };
      }
    } catch {
      // If all geo APIs fail (likely blocked by GFW), assume China
      return { country: "CN", isChina: true };
    }
  }

  return { country: "US", isChina: false };
}
