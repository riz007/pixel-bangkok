export const CONSENT_KEY = "pixel-bangkok-consent";
const CHANGE_EVENT = "pixel-bangkok:consent-change";
let reopened = false;

export type ConsentChoice = "granted" | "denied";

/** Google Analytics 4 Measurement ID (G-…): loaded directly, and only after consent. */
export const GA_ID = /^G-[A-Z0-9]+$/.test(process.env.NEXT_PUBLIC_GA_ID ?? "")
  ? (process.env.NEXT_PUBLIC_GA_ID as string)
  : null;
/** Optional Google Tag Manager container (GTM-…), for sites that manage tags there instead. */
export const GTM_ID = /^GTM-[A-Z0-9]+$/.test(process.env.NEXT_PUBLIC_GTM_ID ?? "")
  ? (process.env.NEXT_PUBLIC_GTM_ID as string)
  : null;
export const ANALYTICS_ENABLED = GA_ID !== null || GTM_ID !== null;

type Gtag = (...args: unknown[]) => void;
let analyticsLoaded = false;

/** Load gtag.js for GA4. Called only once the visitor has allowed analytics. */
export function loadGoogleAnalytics(): void {
  if (!GA_ID || analyticsLoaded) return;
  analyticsLoaded = true;
  const scope = window as unknown as { dataLayer?: unknown[]; gtag?: Gtag };
  scope.dataLayer = scope.dataLayer ?? [];
  scope.gtag =
    scope.gtag ??
    function gtag() {
      // gtag.js expects the arguments object itself, not an array.
      // eslint-disable-next-line prefer-rest-params
      scope.dataLayer?.push(arguments);
    };
  scope.gtag("js", new Date());
  scope.gtag("config", GA_ID);
  const script = document.createElement("script");
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
  document.head.appendChild(script);
}

export function readConsent(): ConsentChoice | null {
  try {
    const value = window.localStorage.getItem(CONSENT_KEY);
    return value === "granted" || value === "denied" ? value : null;
  } catch {
    return null;
  }
}

/** Store the visitor's choice and tell Google tags (Consent Mode v2). Ads stay denied: no ads. */
export function saveConsent(choice: ConsentChoice): void {
  try {
    window.localStorage.setItem(CONSENT_KEY, choice);
  } catch {
    // Storage can be blocked; the choice then lasts for this page view only.
  }
  const gtag = (window as unknown as { gtag?: Gtag }).gtag;
  gtag?.("consent", "update", { analytics_storage: choice });
  if (choice === "granted") loadGoogleAnalytics();
  reopened = false;
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** Show the banner again so the visitor can change their choice. */
export function openConsent(): void {
  reopened = true;
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function subscribeConsent(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => window.removeEventListener(CHANGE_EVENT, onChange);
}

export function bannerOpen(): boolean {
  return ANALYTICS_ENABLED && (reopened || readConsent() === null);
}
