"use client";

import { useEffect } from "react";

import { loadGoogleAnalytics, readConsent } from "@/lib/consent";

/** Loads GA4 on page load for visitors who allowed analytics on an earlier visit. */
export function AnalyticsLoader() {
  useEffect(() => {
    if (readConsent() === "granted") loadGoogleAnalytics();
  }, []);
  return null;
}
