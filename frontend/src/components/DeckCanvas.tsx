import { useEffect, useRef } from "react";
import { api } from "../api";
import type { SelectedElement } from "../types";

export type DeckCanvasProps = {
  deckId: string;
  reloadKey: number;
  onSelect: (sel: SelectedElement) => void;
  /** When set, the iframe scrolls to the slide with this id. */
  gotoSlideId?: string | null;
};

export function isValidOsdSelectMessage(data: unknown): data is { type: "osd:select" } & SelectedElement {
  if (data === null || typeof data !== "object") return false;
  const d = data as Record<string, unknown>;
  if (d.type !== "osd:select") return false;
  if (typeof d.target_id !== "string") return false;
  const r = d.rect;
  if (r === null || typeof r !== "object") return false;
  const rect = r as Record<string, unknown>;
  return (
    typeof rect.x === "number" &&
    typeof rect.y === "number" &&
    typeof rect.w === "number" &&
    typeof rect.h === "number"
  );
}

export function DeckCanvas({ deckId, reloadKey, onSelect, gotoSlideId }: DeckCanvasProps) {
  const ref = useRef<HTMLIFrameElement | null>(null);
  // Track the latest gotoSlideId so the osd:ready handler can scroll to
  // the user's active slide after an iframe remount (e.g. post-edit reload).
  const gotoSlideIdRef = useRef<string | null>(gotoSlideId ?? null);
  useEffect(() => {
    gotoSlideIdRef.current = gotoSlideId ?? null;
  }, [gotoSlideId]);

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      if (!ref.current || e.source !== ref.current.contentWindow) return;
      // Sandboxed iframe (no allow-same-origin) posts as origin "null".
      // Reject anything else to prevent bubbled messages from other windows.
      if (e.origin !== "null") return;
      if (e.data && (e.data as { type?: string }).type === "osd:ready") {
        // Always restore the active slide on iframe (re)ready — without
        // this, applying a comment / re-rendering the deck jumps the
        // preview back to slide 1, which is jarring mid-edit.
        const target = gotoSlideIdRef.current;
        if (target && ref.current?.contentWindow) {
          ref.current.contentWindow.postMessage(
            { type: "osd:goto", slide_id: target },
            "*",
          );
        }
        return;
      }
      if (!isValidOsdSelectMessage(e.data)) return;
      onSelect({ target_id: e.data.target_id, rect: e.data.rect });
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [onSelect]);

  useEffect(() => {
    const iframe = ref.current;
    if (!iframe) return;
    const onLoad = () => {
      try {
        const doc = iframe.contentDocument;
        if (doc && !doc.getElementById("genie-hover-affordance")) {
          const style = doc.createElement("style");
          style.id = "genie-hover-affordance";
          style.textContent = `
        [data-osd-id]:hover {
          outline: 2px solid rgba(255, 54, 33, 0.4);
          outline-offset: -2px;
          cursor: pointer;
        }
      `;
          doc.head.appendChild(style);
        }
      } catch {
        // cross-origin or unloaded
      }
      // Restore active slide unconditionally on load. The osd:ready
      // handshake races the iframe remount on reloadKey++.
      const slideId = gotoSlideIdRef.current;
      if (slideId) {
        iframe.contentWindow?.postMessage(
          { type: "osd:goto", slide_id: slideId },
          "*",
        );
      }
    };
    iframe.addEventListener("load", onLoad);
    onLoad();
    return () => {
      iframe.removeEventListener("load", onLoad);
    };
  }, [reloadKey]);

  // Send goto whenever active slide changes. postMessage to an unloaded iframe
  // is harmless; osd:ready and load handlers also re-send for remount recovery.
  useEffect(() => {
    if (!gotoSlideId) return;
    ref.current?.contentWindow?.postMessage(
      { type: "osd:goto", slide_id: gotoSlideId },
      "*",
    );
  }, [gotoSlideId]);

  const src = `${api.deckEditUrl(deckId)}?r=${reloadKey}`;

  return (
    <iframe
      ref={ref}
      key={src}
      title="deck"
      sandbox="allow-scripts"
      src={src}
      style={{ width: "100%", height: "100%", border: 0, background: "#fff" }}
    />
  );
}
