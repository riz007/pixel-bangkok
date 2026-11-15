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
        <p>
          Map data{" "}
          <a href={manifest.attribution.url} target="_blank" rel="noreferrer">
            {manifest.attribution.text}
          </a>
          , available under the {manifest.attribution.licence} licence.
        </p>
        <dl>
          <dt>Dataset</dt>
          <dd>{manifest.source.dataset}</dd>
          {retrieved && (
            <>
              <dt>Retrieved</dt>
              <dd>{retrieved}</dd>
            </>
          )}
        </dl>
        <p>
          The picture is a stylised rendering of that data. Most building heights are not recorded
          in the source and are drawn at a default height, so the skyline is not to scale.
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
