"use client";

import type { RefObject } from "react";

import { ANALYTICS_ENABLED, openConsent } from "@/lib/consent";
import { FULL_NAME_ROMAN, FULL_NAME_TH, type Lang, STRINGS } from "@/lib/i18n";
import type { TileManifest } from "@/lib/manifest";

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
      {manifest.ai && (
        <p>{text.aiNote(manifest.ai.model, Math.max(1, Math.round(manifest.ai.coverage * 100)))}</p>
      )}

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
        {manifest.ai && (
          <li>
            {manifest.ai.model} <span className="about__licence">({manifest.ai.licence})</span>
          </li>
        )}
        {retrieved && <li className="about__licence">OpenStreetMap {retrieved}</li>}
      </ul>
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
