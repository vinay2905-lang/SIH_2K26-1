import { ChevronLeft, ChevronRight, Download, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiBlob, Doc, downloadFile } from "../api";
import { Spinner } from "./ui";

export interface Highlight {
  page: number;
  bbox: number[];
  label: string;
  tone: "bad" | "ok" | "dim";
  focus?: boolean;
}

const ZOOMS = [0.6, 0.8, 1, 1.25, 1.5];

export default function DocViewer({ doc, highlights = [], page, onPage, height }: {
  doc: Doc;
  highlights?: Highlight[];
  page: number;
  onPage: (p: number) => void;
  height?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const focusRef = useRef<HTMLDivElement>(null);
  const meta = doc.pages[page] || doc.pages[0];

  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    setSrc(null);
    setError(null);
    if (doc.status !== "PROCESSED" && doc.page_count === 0) return;
    apiBlob(`/api/documents/${doc.id}/pages/${page}?dpi=130`)
      .then((b) => {
        if (cancelled) return;
        url = URL.createObjectURL(b);
        setSrc(url);
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [doc.id, page, doc.status, doc.page_count]);

  useEffect(() => {
    focusRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlights, src]);

  const ratio = meta ? meta.h / meta.w : 1.414;
  const width = Math.round(560 * zoom);
  const boxes = highlights.filter((h) => h.page === page && h.bbox && meta);

  return (
    <>
      <div className="vbody" style={height ? { height } : undefined}>
        {doc.status === "PROCESSING" || doc.status === "UPLOADED" ? (
          <div className="empty"><Spinner label="Reading the document…" /></div>
        ) : error ? (
          <div className="empty">{error}</div>
        ) : (
          <div className="pagebox" style={{ width, height: src ? undefined : width * ratio }}>
            {src ? <img src={src} alt={`${doc.filename}, page ${page + 1}`} /> : <div className="empty"><Spinner /></div>}
            {src && boxes.map((h, i) => {
              const [x0, y0, x1, y1] = h.bbox;
              const pad = 2;
              return (
                <div key={i} ref={h.focus ? focusRef : undefined}
                  className={`hlbox${h.tone === "ok" ? " ok" : h.tone === "dim" ? " dim" : ""}`}
                  style={{
                    left: `calc(${(x0 / meta.w) * 100}% - ${pad}px)`, top: `calc(${(y0 / meta.h) * 100}% - ${pad}px)`,
                    width: `calc(${((x1 - x0) / meta.w) * 100}% + ${pad * 2}px)`, height: `calc(${((y1 - y0) / meta.h) * 100}% + ${pad * 2}px)`,
                  }}>
                  {h.tone !== "dim" && <span className="hltag">{h.label}</span>}
                </div>
              );
            })}
          </div>
        )}
      </div>
      <div className="vfoot">
        <button className="btn sm" onClick={() => setZoom(ZOOMS[Math.max(0, ZOOMS.indexOf(zoom) - 1)])} aria-label="Zoom out"><ZoomOut /></button>
        <span className="num">{Math.round(zoom * 100)}%</span>
        <button className="btn sm" onClick={() => setZoom(ZOOMS[Math.min(ZOOMS.length - 1, ZOOMS.indexOf(zoom) + 1)])} aria-label="Zoom in"><ZoomIn /></button>
        {doc.page_count > 1 && (
          <span className="row">
            <button className="btn sm" disabled={page === 0} onClick={() => onPage(page - 1)} aria-label="Previous page"><ChevronLeft /></button>
            <span className="num">{page + 1} / {doc.page_count}</span>
            <button className="btn sm" disabled={page >= doc.page_count - 1} onClick={() => onPage(page + 1)} aria-label="Next page"><ChevronRight /></button>
          </span>
        )}
        <span className="grow" />
        {doc.text_source && <span>{doc.text_source === "TEXT_LAYER" ? "Text layer" : doc.text_source === "NONE" ? "No text" : "OCR"}
          {doc.ocr_confidence != null && ` · ${(doc.ocr_confidence * 100).toFixed(0)}% confidence`}</span>}
        {doc.detected_label && <span>· read as <b>{doc.detected_label}</b> ({((doc.detected_confidence || 0) * 100).toFixed(0)}%)</span>}
        <button className="btn sm" onClick={() => downloadFile(`/api/documents/${doc.id}/file`, doc.filename)}><Download />Original</button>
      </div>
    </>
  );
}
