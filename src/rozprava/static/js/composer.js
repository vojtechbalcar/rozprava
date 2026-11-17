/* A quote is selected from a stored source, never typed or rewritten. */
(() => {
  "use strict";
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  if (!$("#card-sources")) return;
  const sources = JSON.parse($("#card-sources").textContent);
  const initial = JSON.parse($("#card-default").textContent);
  const query = new URLSearchParams(location.search);
  const source = sources[query.get("source")] || initial.source;
  const text = source.text;
  const defaultStart = text.indexOf(initial.span);
  let start = defaultStart < 0 ? 0 : defaultStart;
  let end = defaultStart < 0 ? Math.min(text.length, 280) : start + initial.span.length;
  if (sources[query.get("source")]) {
    const a = Number(query.get("start")), b = Number(query.get("end"));
    if (Number.isInteger(a) && Number.isInteger(b) && a >= 0 && b > a && b <= text.length) { start = a; end = b; }
  }
  const sourceEl = $("[data-card-source]");
  sourceEl.textContent = text;
  sourceEl.tabIndex = 0;
  const download = $("[data-card-download]");
  const error = $("[data-card-error]");
  const highlight = $("[data-card-highlight]");
  const serif = '"Source Serif 4"', sans = '"Cooper Hewitt"', mono = '"IBM Plex Mono"';
  const pad = (v, n) => String(v).padStart(n, "0");
  const c = source.catalog;
  const catalog = `${c.term}/${pad(c.sitting,3)}/${pad(c.page,4)}/${c.order}`;
  const date = source.date.split("-").reverse().map(Number).join(". ");
  const provenance = `${date} · ${source.sitting}. schůze · s. ${source.page}${(source.status || "").toLowerCase().includes("neautorizováno") ? " · neautorizováno" : ""}`;
  $("[data-card-link]").dataset.copy = source.psp_url;
  const activeSize = () => ($('[data-card-size][aria-checked="true"]')?.dataset.cardSize || "1200x630").split("x").map(Number);
  const selected = () => text.slice(start, end).trim();
  const quotation = () => {
    const value = selected();
    const lead = start > 0 && !/[.!?…]\s*$/.test(text.slice(0, start));
    const trail = end < text.length && !/[.!?…]$/.test(value);
    return `„${lead ? "… " : ""}${value}${trail ? " …" : ""}“`;
  };
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  function linesFor(value, width, font) {
    ctx.font = font;
    const lines = []; let line = "";
    for (const word of value.split(/\s+/)) {
      const next = line ? `${line} ${word}` : word;
      if (line && ctx.measureText(next).width > width) { lines.push(line); line = word; }
      else line = next;
    }
    if (line) lines.push(line);
    return lines;
  }
  function paintText(node, value) {
    node.replaceChildren();
    const match = highlight.checked ? value.indexOf(initial.highlight) : -1;
    if (match < 0) { node.textContent = value; return; }
    const mark = document.createElement("mark"); mark.textContent = initial.highlight;
    node.append(value.slice(0, match), mark, value.slice(match + initial.highlight.length));
  }
  function update() {
    const value = quotation();
    const [w] = activeSize();
    const size = w === 1200 ? 44 : 60, maxLines = w === 1200 ? 4 : 9;
    const lines = linesFor(value, w - 128, `400 ${size}px ${serif}`);
    const tooWide = lines.some(line => ctx.measureText(line).width > w - 128);
    error.textContent = selected().length > 280 ? "Vyberte kratší úsek, nejvýše 280 znaků." :
      lines.length > maxLines || tooWide ? "Citace se do tohoto formátu nevejde. Vyberte kratší úsek nebo vyšší formát." : "";
    download.disabled = !!error.textContent || !selected();
    $("[data-card-count]").textContent = `Vybraný úsek: ${selected().length} z nejvýše 280 znaků.`;
    $$(".qcard__quote p").forEach(p => paintText(p, value));
    $$(".qcard__catalog").forEach(p => p.textContent = catalog);
    $$(".qcard__who > span:first-child").forEach(p => p.textContent = source.speaker.name);
    $$(".qcard__party").forEach(p => {
      const swatch = document.createElement("span"); swatch.className = "swatch swatch--pending";
      p.replaceChildren(swatch, document.createTextNode(source.speaker.party || ""));
    });
    $$(".qcard__prov").forEach(p => p.textContent = provenance);
    $$(".qcard__url").forEach(p => p.textContent = `psp.cz · ${catalog}`);
    highlight.closest("label").hidden = !selected().includes(initial.highlight);
  }
  document.addEventListener("selectionchange", () => {
    const selection = getSelection();
    if (!selection?.rangeCount || selection.isCollapsed) return;
    const range = selection.getRangeAt(0);
    if (!sourceEl.contains(range.startContainer) || !sourceEl.contains(range.endContainer)) return;
    const before = range.cloneRange(); before.selectNodeContents(sourceEl); before.setEnd(range.startContainer, range.startOffset);
    start = before.toString().length; end = start + range.toString().length;
    update();
  });
  highlight.addEventListener("change", update);
  $$("[data-card-size]").forEach(b => b.addEventListener("click", update));
  download.addEventListener("click", async () => {
    await document.fonts.ready;
    update(); if (download.disabled) return;
    const [w,h] = activeSize(), fontSize = w === 1200 ? 44 : 60, leading = fontSize * 1.3;
    canvas.width = w; canvas.height = h;
    ctx.fillStyle = "#F6F5F0"; ctx.fillRect(0,0,w,h);
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "#6B6A64"; ctx.font = `400 22px ${mono}`; ctx.fillText(catalog,64,86);
    ctx.fillStyle = "#111111"; ctx.font = `600 28px ${sans}`;
    ctx.fillText("Rozprava", w - 64 - ctx.measureText("Rozprava").width - 12,86);
    ctx.fillStyle = "#FFE45E"; ctx.fillRect(w-72,78,8,8);
    const lines = linesFor(quotation(), w-128, `400 ${fontSize}px ${serif}`);
    let y = 128 + Math.max(0, (h - 340 - lines.length * leading) / 2) + fontSize;
    const matchStart = highlight.checked ? quotation().indexOf(initial.highlight) : -1;
    const matchEnd = matchStart + initial.highlight.length;
    let lineStart = 0;
    for (const line of lines) {
      ctx.font = `400 ${fontSize}px ${serif}`;
      const a = Math.max(0, matchStart - lineStart), b = Math.min(line.length, matchEnd - lineStart);
      if (matchStart >= 0 && b > a) {
        const x = 64 + ctx.measureText(line.slice(0,a)).width;
        ctx.fillStyle = "#FFE45E"; ctx.fillRect(x, y-fontSize*0.85, ctx.measureText(line.slice(a,b)).width, fontSize*1.15);
      }
      ctx.fillStyle = "#111111"; ctx.fillText(line,64,y); y += leading;
      lineStart += line.length + 1;
    }
    ctx.fillStyle = "#111111"; ctx.fillRect(64,h-174,w-128,1);
    ctx.font = `600 28px ${sans}`; ctx.fillText(source.speaker.name,64,h-130);
    const partyX = 64 + ctx.measureText(source.speaker.name).width + 20;
    ctx.fillStyle = "#A3A198"; ctx.fillRect(partyX,h-145,14,14);
    ctx.fillStyle = "#3D3C38"; ctx.font = `500 20px ${mono}`; ctx.fillText((source.speaker.party || "").toUpperCase(),partyX+24,h-131);
    ctx.font = `400 20px ${mono}`; ctx.fillText(provenance,64,h-96);
    ctx.fillStyle = "#6B6A64"; ctx.font = `400 18px ${mono}`;
    const url = `psp.cz · ${catalog}`; ctx.fillText(url,w-64-ctx.measureText(url).width,h-64);
    canvas.toBlob(blob => {
      if (!blob) { error.textContent = "Obrázek se nepodařilo vytvořit. Zkuste to znovu."; return; }
      const link = document.createElement("a"), url = URL.createObjectURL(blob);
      link.href = url; link.download = `rozprava-${catalog.replaceAll("/", "-")}-${w}x${h}.png`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url),1000);
    }, "image/png");
  });
  document.fonts.ready.then(update);
  update();
})();
