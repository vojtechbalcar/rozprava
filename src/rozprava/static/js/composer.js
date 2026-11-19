/* A quote is a contiguous span of one stored paragraph, pinned to its revision. */
(() => {
  "use strict";
  const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
  if (!$("#card-sources")) return;
  const live = document.body.dataset.live === "true";
  const sources = JSON.parse($("#card-sources").textContent);
  const initial = JSON.parse($("#card-default").textContent);
  const query = new URLSearchParams(location.search);
  const source = live ? initial.source : sources[query.get("source")] || initial.source;
  const text = source.text, chars = Array.from(text);
  const characterCount = value => Array.from(value).length;
  const index = text.indexOf(initial.span);
  let start = live ? initial.start : index < 0 ? 0 : characterCount(text.slice(0, index));
  let end = live ? initial.end : index < 0 ? Math.min(chars.length, 280) : start + characterCount(initial.span);
  if (!live && sources[query.get("source")]) {
    const a = Number(query.get("start")), b = Number(query.get("end"));
    if (Number.isInteger(a) && Number.isInteger(b) && a >= 0 && b > a && b <= text.length) {
      start = characterCount(text.slice(0, a)); end = characterCount(text.slice(0, b));
    }
  }
  const sourceEl = $("[data-card-source]");
  sourceEl.textContent = text; sourceEl.tabIndex = 0;
  const download = $("[data-card-download]"), share = $("[data-card-link]");
  const error = $("[data-card-error]"), highlight = $("[data-card-highlight]");
  const serif = '"Source Serif 4"', sans = '"Cooper Hewitt"', mono = '"IBM Plex Mono"';
  const pad = (v, n) => String(v).padStart(n, "0");
  const c = source.catalog;
  const catalog = `${c.term}/${pad(c.sitting,3)}/${pad(c.page,4)}/${c.order}`;
  const date = source.date ? source.date.split("-").reverse().map(Number).join(". ") : "Datum neuvedeno";
  const provenance = `${date} · ${source.sitting}. schůze · s. ${source.page}${(source.status || "").toLowerCase().includes("neautorizováno") ? " · neautorizováno" : ""}`;
  const activeSize = () => ($('[data-card-size][aria-checked="true"]')?.dataset.cardSize || "1200x630");
  const selected = () => chars.slice(start, end).join("");
  const quotation = () => {
    const value = selected();
    const lead = live ? source.lead || start > 0 : start > 0 && !/[.!?…]\s*$/.test(chars.slice(0, start).join(""));
    const trail = live ? source.trail || end < chars.length : end < chars.length && !/[.!?…]$/.test(value);
    return `„${lead ? "… " : ""}${value}${trail ? " …" : ""}“`;
  };
  const canvas = document.createElement("canvas"), ctx = canvas.getContext("2d");
  let fontsReady = false, fontError = "", busy = false;
  function normalize() {
    while (start < end && /\s/u.test(chars[start])) start++;
    while (end > start && /\s/u.test(chars[end - 1])) end--;
  }
  function shareURL() {
    const url = new URL(initial.url, location.href);
    url.searchParams.set("start", start); url.searchParams.set("end", end);
    url.searchParams.set("format", activeSize());
    if (highlight.checked && initial.highlight && selected().includes(initial.highlight)) url.searchParams.set("highlight", initial.highlight);
    else url.searchParams.delete("highlight");
    return url;
  }
  function linesFor(value, width, font) {
    if (!ctx) return [];
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
    const match = highlight.checked && initial.highlight ? value.indexOf(initial.highlight) : -1;
    if (match < 0) { node.textContent = value; return; }
    const mark = document.createElement("mark"); mark.textContent = initial.highlight;
    node.append(value.slice(0, match), mark, value.slice(match + initial.highlight.length));
  }
  function update() {
    normalize();
    const value = quotation(), [w] = activeSize().split("x").map(Number);
    const fontSize = w === 1200 ? 44 : 60, maxLines = w === 1200 ? 4 : 9;
    const lines = linesFor(value, w - 128, `400 ${fontSize}px ${serif}`);
    const invalid = !selected() ? "Vyberte neprázdný úsek citace." : end - start > 280 ? "Vyberte kratší úsek, nejvýše 280 znaků." : "";
    const tooWide = ctx && lines.some(line => ctx.measureText(line).width > w - 128);
    const fitError = lines.length > maxLines || tooWide ? "Citace se do tohoto formátu nevejde. Vyberte kratší úsek nebo vyšší formát." : "";
    error.textContent = invalid || (!ctx ? "Prohlížeč nepodporuje export obrázku." : fontError || (!fontsReady ? "Načítám písma…" : fitError));
    download.disabled = busy || !!error.textContent;
    share.disabled = busy || !!invalid;
    $("[data-card-count]").textContent = `Vybraný úsek: ${end - start} z nejvýše 280 znaků.`;
    $$(".qcard__quote p").forEach(p => paintText(p, value));
    $$(".qcard__catalog").forEach(p => p.textContent = catalog);
    $$(".qcard__who > span:first-child").forEach(p => p.textContent = source.speaker.name);
    $$(".qcard__party").forEach(p => {
      p.replaceChildren();
      if (!source.speaker.party) return;
      const swatch = document.createElement("span"); swatch.className = "swatch swatch--pending";
      p.append(swatch, document.createTextNode(source.speaker.party));
    });
    $$(".qcard__prov").forEach(p => p.textContent = provenance);
    $$(".qcard__url").forEach(p => p.textContent = `psp.cz · ${catalog}`);
    highlight.closest("label").hidden = !initial.highlight || !selected().includes(initial.highlight);
    if (live && !invalid) {
      const url = shareURL();
      history.replaceState(null, "", url.pathname + url.search);
    }
  }
  async function validate() {
    if (!live) return;
    const expected = shareURL(), url = new URL(initial.validation_url, location.href);
    url.search = expected.search;
    let response;
    try { response = await fetch(url); }
    catch { throw new Error("Citaci se nepodařilo ověřit. Zkuste to znovu."); }
    if (!response.ok) throw new Error("Citaci se nepodařilo ověřit. Zkuste to znovu.");
    const verified = await response.json();
    if (expected.href !== shareURL().href) throw new Error("Výběr se mezitím změnil. Zkuste to znovu.");
    if (verified.span !== selected() || verified.revision !== initial.revision || verified.source_key !== initial.source_key) {
      throw new Error("Citace neodpovídá uloženému zdroji. Obnovte stránku.");
    }
  }
  document.addEventListener("selectionchange", () => {
    const selection = getSelection();
    if (!selection?.rangeCount || selection.isCollapsed) return;
    const range = selection.getRangeAt(0);
    if (!sourceEl.contains(range.startContainer) || !sourceEl.contains(range.endContainer)) return;
    const before = range.cloneRange(); before.selectNodeContents(sourceEl); before.setEnd(range.startContainer, range.startOffset);
    start = characterCount(before.toString()); end = start + characterCount(range.toString());
    update();
  });
  highlight.addEventListener("change", update);
  $$("[data-card-size]").forEach(b => b.addEventListener("click", update));
  share.addEventListener("click", async () => {
    update(); if (share.disabled) return;
    busy = true; update();
    try {
      await validate();
      await navigator.clipboard.writeText(live ? shareURL().href : source.psp_url);
      error.textContent = "Odkaz zkopírován.";
    } catch (e) { error.textContent = e.name === "NotAllowedError" ? "Prohlížeč nepovolil kopírování. Zkopírujte odkaz z adresního řádku." : e.message || "Odkaz se nepodařilo zkopírovat."; }
    finally { const message = error.textContent; busy = false; update(); error.textContent = message; }
  });
  download.addEventListener("click", async () => {
    update(); if (download.disabled) return;
    busy = true; update();
    try {
      await validate();
      const [w,h] = activeSize().split("x").map(Number), fontSize = w === 1200 ? 44 : 60, leading = fontSize * 1.3;
      canvas.width = w; canvas.height = h;
      ctx.fillStyle = "#F6F5F0"; ctx.fillRect(0,0,w,h);
      ctx.textBaseline = "alphabetic";
      ctx.fillStyle = "#6B6A64"; ctx.font = `400 22px ${mono}`; ctx.fillText(catalog,64,86);
      ctx.fillStyle = "#111111"; ctx.font = `600 28px ${sans}`;
      ctx.fillText("Rozprava", w - 64 - ctx.measureText("Rozprava").width - 12,86);
      ctx.fillStyle = "#FFE45E"; ctx.fillRect(w-72,78,8,8);
      const lines = linesFor(quotation(), w-128, `400 ${fontSize}px ${serif}`);
      let y = 128 + Math.max(0, (h - 340 - lines.length * leading) / 2) + fontSize;
      const matchStart = highlight.checked && initial.highlight ? quotation().indexOf(initial.highlight) : -1;
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
      ctx.font = `600 28px ${sans}`; ctx.fillText(source.speaker.name,64,h-130,w-128);
      if (source.speaker.party) {
        const partyX = Math.min(64 + ctx.measureText(source.speaker.name).width + 20, w - 220);
        ctx.fillStyle = "#A3A198"; ctx.fillRect(partyX,h-145,14,14);
        ctx.fillStyle = "#3D3C38"; ctx.font = `500 20px ${mono}`;
        ctx.fillText(source.speaker.party.toUpperCase(),partyX+24,h-131);
      }
      ctx.font = `400 20px ${mono}`; ctx.fillText(provenance,64,h-96,w-128);
      ctx.fillStyle = "#6B6A64"; ctx.font = `400 18px ${mono}`;
      const urlText = `psp.cz · ${catalog}`; ctx.fillText(urlText,w-64-ctx.measureText(urlText).width,h-64);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("Obrázek se nepodařilo vytvořit. Zkuste to znovu.");
      const link = document.createElement("a"), url = URL.createObjectURL(blob);
      link.href = url; link.download = `rozprava-${catalog.replaceAll("/", "-")}-${w}x${h}.png`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url),1000);
      error.textContent = "Obrázek je připravený ke stažení.";
    } catch (e) { error.textContent = e.message || "Obrázek se nepodařilo vytvořit."; }
    finally { const message = error.textContent; busy = false; update(); error.textContent = message; }
  });
  async function loadFonts() {
    const sample = text + source.speaker.name + provenance;
    let timer;
    try {
      const faces = await Promise.race([
        Promise.all([`400 44px ${serif}`, `600 28px ${sans}`, `400 22px ${mono}`, `500 20px ${mono}`].map(font => document.fonts.load(font, sample))),
        new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("font timeout")), 10000); }),
      ]);
      fontsReady = faces.every(group => group.length && group.every(face => face.status === "loaded"));
      if (!fontsReady) throw new Error("font missing");
    } catch {
      fontError = "Písma se nepodařilo načíst. Pro export obrázku obnovte stránku.";
    } finally { clearTimeout(timer); update(); }
  }
  update(); loadFonts();
})();
