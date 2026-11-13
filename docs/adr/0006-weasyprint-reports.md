# ADR-0006 PDF reports: WeasyPrint in a dedicated worker

Status: accepted (2026-11-13, Phase 9)

**Decision:** PDF reports are built from HTML and CSS by WeasyPrint, in a separate `reports-worker` container (queue `reports`, concurrency 2, 1 GB memory limit, 120 s soft and 150 s hard task limit, worker recycled every 20 tasks). The page is a Django template (autoescaped) plus one print stylesheet (`apps/reports/assets/report.css`), with bundled Geist fonts (OFL) and charts drawn as inline SVG by our own code.

**Safety rules:**
- The engine gets a fetcher that serves only `data:` URIs and `.woff` files inside the bundled font folder. Local files and every network address are refused, so finding text cannot cause a server-side request or a file read.
- All user text goes through `apps.core.markdown.render_markdown` (no images, no raw HTML, no scripts). Evidence images are re-encoded by Pillow to bounded JPEG and passed as data URIs. Template logos are PNG or JPEG only, re-encoded to PNG; SVG is not accepted.
- The worker rebuilds the report from the requester's own scoped selectors and re-checks their rights, so a report never holds more than the requester could open. Drafts are never included. Technical details, proof of concept and technical notes appear only in internal reports for holders of `finding_notes.technical`.
- Every build writes `report.generated` (filters, counts, size, SHA-256) to the hash-chained audit log; downloads write `report.downloaded`.

**Why:** WeasyPrint gives real paged media (running headers, page counters, table of contents with page numbers, repeating table headers) without a headless browser, which would need a much larger image and a wider attack surface. A dedicated worker keeps its memory use away from imports.

**Consequences:** Backend image grows by Pango, HarfBuzz and a fallback font (about 150 MB). Files expire after `REPORT_RETENTION_DAYS` (90 by default); rows and audit stay. DOCX export is not built. WeasyPrint is pinned to `>=68,<70` because its fetcher interface changed in 68.
