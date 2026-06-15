import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { api } from "../api";

export function ExportMenu({ deckId }: { deckId: string }) {
  const [open, setOpen] = useState(false);
  const [gsErr, setGsErr] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const menu = menuRef.current;
    const items = menu?.querySelectorAll<HTMLElement>('[role="menuitem"]');
    items?.[0]?.focus();
  }, [open]);

  const openGoogleSlides = async () => {
    setGsErr(null);
    setOpen(false);
    try {
      const { url } = await api.exportGoogleSlides(deckId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setGsErr(e instanceof Error ? e.message : "Google Slides export failed");
    }
  };

  const handleMenuKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const menu = menuRef.current;
    if (!menu) return;
    const itemList = [...menu.querySelectorAll<HTMLElement>('[role="menuitem"]')];
    if (!itemList.length) return;

    const idx = itemList.indexOf(document.activeElement as HTMLElement);

    switch (e.key) {
      case "Escape":
        e.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
        break;
      case "ArrowDown": {
        e.preventDefault();
        const next = idx < 0 ? 0 : (idx + 1) % itemList.length;
        itemList[next]?.focus();
        break;
      }
      case "ArrowUp": {
        e.preventDefault();
        const next = idx < 0 ? itemList.length - 1 : (idx - 1 + itemList.length) % itemList.length;
        itemList[next]?.focus();
        break;
      }
      case "Home":
        e.preventDefault();
        itemList[0]?.focus();
        break;
      case "End":
        e.preventDefault();
        itemList[itemList.length - 1]?.focus();
        break;
      default:
        break;
    }
  };

  return (
    <div className="export-menu" ref={ref}>
      {gsErr && (
        <p className="dim export-menu__err" role="alert">
          {gsErr}
        </p>
      )}
      <button
        ref={triggerRef}
        type="button"
        className="btn btn--primary btn--sm"
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            e.preventDefault();
            setOpen(false);
          }
        }}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls="export-menu-list"
      >
        Export <span aria-hidden>▼</span>
      </button>
      {open && (
        <div
          ref={menuRef}
          id="export-menu-list"
          className="export-menu__list"
          role="menu"
          tabIndex={-1}
          onKeyDown={handleMenuKeyDown}
        >
          <button
            type="button"
            className="export-menu__link"
            role="menuitem"
            onClick={() => void openGoogleSlides()}
          >
            Google Slides (experimental)
          </button>
          <a
            href={api.deckExportUrl(deckId, "pptx")}
            download="presentation.pptx"
            role="menuitem"
          >
            PPTX (experimental)
          </a>
          <a
            href={`/api/decks/${encodeURIComponent(deckId)}/export/pdf`}
            download="presentation.pdf"
            role="menuitem"
          >
            PDF
          </a>
          <a
            href={api.deckExportUrl(deckId, "html")}
            download="presentation.html"
            role="menuitem"
          >
            HTML
          </a>
        </div>
      )}
    </div>
  );
}
