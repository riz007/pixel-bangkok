export const CONSENT_KEY = "pixel-bangkok-consent";
const CHANGE_EVENT = "pixel-bangkok:consent-change";
let reopened = false;

export type ConsentChoice = "granted" | "denied";

export const ANALYTICS_ENABLED = /^GTM-[A-Z0-9]+$/.test(process.env.NEXT_PUBLIC_GTM_ID ?? "");

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
  const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
  gtag?.("consent", "update", { analytics_storage: choice });
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
