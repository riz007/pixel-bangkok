"use client";

import type { RefObject } from "react";

import { ANALYTICS_ENABLED, openConsent } from "@/lib/consent";
import { FULL_NAME_ROMAN, FULL_NAME_TH, type Lang, STRINGS } from "@/lib/i18n";
import type { TileManifest } from "@/lib/manifest";
import { CONTACT_EMAIL, PRIVACY_ID } from "@/lib/site";

interface AboutDialogProps {
  dialogRef: RefObject<HTMLDialogElement | null>;
  manifest: TileManifest;
  lang: Lang;
}

const MAKER = process.env.NEXT_PUBLIC_MAKER_NAME;
const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL;

export function AboutDialog({ dialogRef, manifest, lang }: AboutDialogProps) {
  const text = STRINGS[lang];
  const retrieved = manifest.source.retrievedAt?.slice(0, 10);
  return (
    <dialog
      ref={dialogRef}
      className="about"
      aria-labelledby="about-title"
      {...({ closedby: "any" } as object)}
    >
      <form method="dialog" className="about__close">
        <button type="submit" aria-label={text.close}>
          <span aria-hidden="true">×</span>
        </button>
      </form>
      <h2 id="about-title">{text.aboutTitle}</h2>
      <p className="about__intro">{text.aboutIntro}</p>

      <figure className="about__name">
        <figcaption>{text.fullNameLabel}</figcaption>
        <p className="about__name-th" lang="th">
          {FULL_NAME_TH}
        </p>
        <p className="about__name-roman" lang="en">
          {FULL_NAME_ROMAN}
        </p>
        <p className="about__name-meaning">{text.fullNameMeaning}</p>
      </figure>

      <h3>{text.howMadeTitle}</h3>
      <p>{text.howMade}</p>

      <h3>{text.shortcutsTitle}</h3>
      <dl className="about__keys">
        {text.shortcuts.map(([key, action]) => (
          <div key={key}>
            <dt>
              <kbd>{key}</kbd>
            </dt>
            <dd>{action}</dd>
          </div>
        ))}
      </dl>

      <h3>{text.faqTitle}</h3>
      <div className="about__faq">
        {text.faq.map(([question, answer]) => (
          <details key={question}>
            <summary>{question}</summary>
            <p>{answer}</p>
          </details>
        ))}
      </div>

      <h3>{text.dataTitle}</h3>
      <ul className="about__credits">
        {manifest.attributions.map((attribution) => (
          <li key={attribution.url}>
            <a href={attribution.url} target="_blank" rel="noreferrer">
              {attribution.text}
            </a>{" "}
            <span className="about__licence">({attribution.licence})</span>
          </li>
        ))}
        {retrieved && (
          <li className="about__licence">OpenStreetMap {retrieved}</li>
        )}
      </ul>
      <p className="about__badge">
        <a
          href="https://isometriccities.com/"
          target="_blank"
          rel="noopener"
          title="Featured on Isometric Cities"
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- third-party badge, served as-is */}
          <img
            src="/isometric-cities-badge.svg"
            alt="Featured on Isometric Cities"
            width={200}
            height={48}
            loading="lazy"
          />
        </a>
      </p>
      <section className="about__privacy-notice" aria-labelledby={PRIVACY_ID}>
        <h3 id={PRIVACY_ID} tabIndex={-1}>
          {text.privacyTitle}
        </h3>
        <p>
          {text.privacyWho(MAKER ?? null, CONTACT_EMAIL !== null)}
          {CONTACT_EMAIL && (
            <>
              {" "}
              <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
            </>
          )}
        </p>
        {ANALYTICS_ENABLED && <p>{text.privacyAnalytics}</p>}
        <p>{text.privacyHosting}</p>
        <p>{text.privacyNone}</p>
        <p>{text.privacyTransfer}</p>
        <p>
          {text.privacyRights}
          {CONTACT_EMAIL && (
            <>
              {" "}
              <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
            </>
          )}
        </p>
        <p className="about__licence">{text.privacyUpdated}</p>
      </section>
      {ANALYTICS_ENABLED && (
        <p>
          <button
            type="button"
            className="about__privacy"
            onClick={() => {
              dialogRef.current?.close();
              openConsent();
            }}
          >
            {text.privacySettings}
          </button>
        </p>
      )}
      {(MAKER || REPO_URL) && (
        <p className="about__maker">
          {MAKER && text.madeBy(MAKER)}
          {MAKER && REPO_URL && " · "}
          {REPO_URL && (
            <a href={REPO_URL} target="_blank" rel="noreferrer">
              {text.sourceCode}
            </a>
          )}
        </p>
      )}
    </dialog>
  );
}
