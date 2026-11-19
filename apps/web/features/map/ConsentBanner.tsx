"use client";

import { useId, useSyncExternalStore } from "react";

import { bannerOpen, type ConsentChoice, saveConsent, subscribeConsent } from "@/lib/consent";
import { type Lang, STRINGS } from "@/lib/i18n";

export function ConsentBanner({ lang, onPrivacy }: { lang: Lang; onPrivacy: () => void }) {
  const text = STRINGS[lang];
  const titleId = useId();
  const open = useSyncExternalStore(subscribeConsent, bannerOpen, () => false);

  if (!open) return null;

  const choose = (choice: ConsentChoice) => saveConsent(choice);

  return (
    <section className="consent" aria-labelledby={titleId}>
      <h2 id={titleId} className="consent__title">
        {text.consentTitle}
      </h2>
      <p className="consent__text">
        {text.consentText}{" "}
        <button type="button" className="consent__link" onClick={onPrivacy}>
          {text.privacyLink}
        </button>
      </p>
      <div className="consent__actions">
        <button type="button" className="consent__decline" onClick={() => choose("denied")}>
          {text.consentDecline}
        </button>
        <button type="button" className="consent__allow" onClick={() => choose("granted")}>
          {text.consentAllow}
        </button>
      </div>
    </section>
  );
}
