"use client";

import { useRef } from "react";

import type { TileManifest } from "@/lib/manifest";

export function CreditsDialog({ manifest }: { manifest: TileManifest }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const retrieved = manifest.source.retrievedAt?.slice(0, 10);

  return (
    <>
      <button type="button" className="text-button" onClick={() => dialogRef.current?.showModal()}>
        Credits
      </button>
      <dialog
        ref={dialogRef}
        className="credits"
        aria-labelledby="credits-title"
        {...({ closedby: "any" } as object)}
      >
        <h2 id="credits-title">Credits &amp; data</h2>
        <ul className="credits__sources">
          {manifest.attributions.map((attribution) => (
            <li key={attribution.url}>
              <a href={attribution.url} target="_blank" rel="noreferrer">
                {attribution.text}
              </a>{" "}
              <span className="credits__licence">({attribution.licence})</span>
            </li>
          ))}
        </ul>
        {retrieved && (
          <dl>
            <dt>Map data retrieved</dt>
            <dd>{retrieved}</dd>
          </dl>
        )}
        <p>
          The picture is a stylised drawing of that data. Building heights are mostly estimates
          from a satellite-derived model, trees are placed where a canopy-height model shows tree
          cover, and roof shapes and windows are drawn for illustration, so heights and details
          are approximate.
        </p>
        <form method="dialog">
          <button type="submit" autoFocus>
            Close
          </button>
        </form>
      </dialog>
    </>
  );
}
