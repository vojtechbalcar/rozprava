/* Rozprava: small progressive enhancements. Every page works without this file.
   Section numbers (§) refer to DESIGN.md. */
(function () {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // Diacritics- and case-insensitive matching, one character at a time so indices stay aligned.
  const fold = (s) => Array.from(s, (c) => c.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase() || c).join("");
  const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  /* ---------- toast (§7.17) ---------- */
  const toastEl = $(".toast[role=status]");
  let toastTimer;
  function toast(message) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toastEl.hidden = true), 2500);
  }

  async function copy(text, message = "Odkaz zkopírován") {
    try {
      await navigator.clipboard.writeText(text);
      toast(message);
    } catch {
      toast("Kopírování se nepodařilo");
    }
  }

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-copy]");
    if (el) copy(new URL(el.dataset.copy, document.baseURI).href);
    const permalink = e.target.closest(".permalink");
    if (permalink) copy(new URL(permalink.getAttribute("href"), location.href).href);
  });

  /* ---------- theme (§3.2) ---------- */
  function setTheme(value) {
    document.cookie = `theme=${value}; path=/; max-age=31536000; samesite=lax`;
    if (value === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = value;
    $$("[data-theme-set]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.themeSet === value)));
  }
  const saved = (document.cookie.match(/(?:^|; )theme=(light|dark|system)/) || [])[1] || "system";
  $$("[data-theme-set]").forEach((b) => {
    b.setAttribute("aria-checked", String(b.dataset.themeSet === saved));
    b.addEventListener("click", () => setTheme(b.dataset.themeSet));
  });
  function toggleTheme() {
    const dark = document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && window.matchMedia("(prefers-color-scheme: dark)").matches);
    setTheme(dark ? "light" : "dark");
  }

  /* ---------- key hints ---------- */
  $$("[data-kbd]").forEach((k) => (k.textContent = isMac ? "⌘K" : "Ctrl K"));

  /* ---------- tooltips (§7.16) ---------- */
  const tip = $(".tip[hidden]");
  let tipTimer;
  function place(el, target, gap = 10) {
    const r = target.getBoundingClientRect();
    const w = el.offsetWidth, h = el.offsetHeight;
    let left = Math.min(Math.max(8, r.left), window.innerWidth - w - 16);
    let top = r.bottom + gap;
    if (top + h > window.innerHeight - 8) top = r.top - h - gap;
    el.style.left = `${left}px`;
    el.style.top = `${Math.max(8, top)}px`;
  }
  function showTip(target) {
    if (!tip) return;
    tip.textContent = target.dataset.tip;
    tip.hidden = false;
    place(tip, target);
  }
  document.addEventListener("pointerover", (e) => {
    const t = e.target.closest("[data-tip]");
    if (!t) return;
    clearTimeout(tipTimer);
    tipTimer = setTimeout(() => showTip(t), 300);
  });
  document.addEventListener("pointerout", (e) => {
    if (!e.target.closest("[data-tip]")) return;
    clearTimeout(tipTimer);
    if (tip) tip.hidden = true;
  });
  document.addEventListener("focusin", (e) => { const t = e.target.closest("[data-tip]"); if (t) showTip(t); });
  document.addEventListener("focusout", (e) => { if (e.target.closest("[data-tip]") && tip) tip.hidden = true; });

  /* ---------- citation popovers (§7.7) ---------- */
  let pop, popIn, popOut;
  function showCite(chip) {
    const source = document.getElementById(`cite-${chip.dataset.cite}`);
    if (!source) return;
    hideCite(true);
    pop = source.cloneNode(true);
    pop.removeAttribute("id");
    document.body.appendChild(pop);
    if (window.innerWidth >= 768) place(pop, chip, 8);
    pop.addEventListener("pointerenter", () => clearTimeout(popOut));
    pop.addEventListener("pointerleave", () => (popOut = setTimeout(hideCite, 100)));
  }
  function hideCite(now) { if (pop && (now || !pop.matches(":hover, :focus-within"))) { if (overlay === pop) closeOverlay(); pop.remove(); pop = null; } }
  $$(".cite[data-cite]").forEach((chip) => {
    chip.addEventListener("pointerenter", () => { if (innerWidth < 768) return; clearTimeout(popOut); popIn = setTimeout(() => showCite(chip), 150); });
    chip.addEventListener("pointerleave", () => { clearTimeout(popIn); popOut = setTimeout(hideCite, 100); });
    chip.addEventListener("focus", () => { if (innerWidth >= 768) showCite(chip); });
    chip.addEventListener("blur", () => (popOut = setTimeout(hideCite, 100)));
    chip.addEventListener("click", (e) => {
      const target = document.getElementById(`v${chip.dataset.cite}`);
      if (!target) return;
      e.preventDefault();
      if (innerWidth < 768) {
        showCite(chip);
        const close = document.createElement("button");
        close.className = "btn btn--secondary"; close.textContent = "Zavřít citaci";
        pop.append(close); close.addEventListener("click", () => hideCite(true));
        pop.setAttribute("aria-label", "Citovaný projev");
        openOverlay(pop, chip);
        return;
      }
      hideCite(true);
      target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      history.replaceState(null, "", `#v${chip.dataset.cite}`);
      target.classList.remove("is-flash");
      void target.offsetWidth;
      target.classList.add("is-flash");
    });
  });

  /* Modal focus, inert backgrounds and return-to-trigger behavior. */
  let overlay = null, overlayTrigger = null;
  function openOverlay(el, trigger) {
    closeOverlay();
    overlay = el; overlayTrigger = trigger;
    el.hidden = false;
    el.classList.add("is-open");
    if (!el.matches("[data-palette]")) { el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true"); }
    trigger?.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
    // Walk up so a nested filter drawer leaves its ancestors accessible.
    let branch = el;
    while (branch.parentElement && branch !== document.body) {
      [...branch.parentElement.children].forEach(sibling => {
        if (sibling !== branch && !sibling.inert) { sibling.inert = true; sibling.dataset.modalInert = ""; }
      });
      branch = branch.parentElement;
    }
    $("input, button, a[href]", el)?.focus();
  }
  function closeOverlay() {
    if (!overlay) return;
    overlay.classList.remove("is-open");
    if (!overlay.matches("[data-drawer]")) overlay.hidden = true;
    else { overlay.removeAttribute("role"); overlay.removeAttribute("aria-modal"); }
    $$('[data-modal-inert]').forEach(e => { e.inert = false; delete e.dataset.modalInert; });
    document.body.style.overflow = "";
    overlayTrigger?.setAttribute("aria-expanded", "false");
    overlayTrigger?.focus();
    overlay = null;
  }
  document.addEventListener("keydown", e => {
    if (e.key !== "Tab" || !overlay) return;
    const focusable = $$("a[href], button, input, select, [tabindex='0']", overlay).filter(e => !e.disabled && e.tabIndex >= 0 && e.getClientRects().length);
    if (!focusable.length) return;
    const first = focusable[0], last = focusable.at(-1);
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });
  const sheet = $("#menu-sheet");
  $$("[data-menu-open]").forEach(b => b.addEventListener("click", () => openOverlay(sheet, b)));
  $$("[data-menu-close]").forEach(b => b.addEventListener("click", closeOverlay));
  $$("[data-drawer-open]").forEach(b => b.addEventListener("click", () => openOverlay(document.getElementById(b.dataset.drawerOpen), b)));
  $$("[data-drawer-close]").forEach(b => b.addEventListener("click", closeOverlay));
  window.addEventListener("resize", () => { if (overlay?.matches("[data-drawer]") && innerWidth >= 1024) closeOverlay(); });

  /* ---------- ⌘K palette (§7.4) ---------- */
  const palette = $("[data-palette]");
  const data = JSON.parse(($("#palette-data") || { textContent: "{}" }).textContent || "{}");
  const input = palette && $("input", palette);
  const list = palette && $(".palette__list", palette);
  let items = [], selected = 0, lastFocus = null;

  function recent() {
    try {
      const value = JSON.parse(localStorage.getItem("rozprava.recent") || "[]");
      return Array.isArray(value) ? value.filter(r => typeof r?.title === "string" && typeof r?.url === "string" && new URL(r.url, location.href).origin === location.origin).slice(0, 5) : [];
    } catch { return []; }
  }
  function remember(item) {
    try {
      const next = [item, ...recent().filter((r) => r.url !== item.url)].slice(0, 5);
      localStorage.setItem("rozprava.recent", JSON.stringify(next));
    } catch { /* storage may be unavailable */ }
  }
  function mark(text, query) {
    if (!query) return escapeHtml(text);
    const i = fold(text).indexOf(fold(query));
    if (i < 0) return escapeHtml(text);
    return escapeHtml(text.slice(0, i)) + "<mark>" + escapeHtml(text.slice(i, i + query.length)) + "</mark>" + escapeHtml(text.slice(i + query.length));
  }
  const cz = (iso) => { const [y, m, d] = iso.split("-").map(Number); return `${d}. ${m}. ${y}`; };

  let paletteController = null, paletteTimer = null, paletteRequest = 0;
  function cancelPaletteRequest() {
    clearTimeout(paletteTimer);
    paletteController?.abort();
    paletteRequest++;
    list?.removeAttribute("aria-busy");
  }
  function renderPalette() {
    cancelPaletteRequest();
    const q = input.value.trim();
    if (!data.endpoint || !q) { drawPalette(data); return; }
    const empty = {...data, mps: [], bills: [], sittings: []};
    drawPalette(empty, "Hledám…");
    list.setAttribute("aria-busy", "true");
    const request = paletteRequest;
    paletteTimer = setTimeout(async () => {
      paletteController = new AbortController();
      try {
        const url = new URL(data.endpoint, location.href);
        url.searchParams.set("q", q);
        const response = await fetch(url, {signal: paletteController.signal});
        if (!response.ok) throw new Error("lookup failed");
        const result = await response.json();
        if (request !== paletteRequest || palette.hidden) return;
        drawPalette(result);
      } catch (error) {
        if (error.name === "AbortError" || request !== paletteRequest || palette.hidden) return;
        drawPalette(empty, "Rychlé hledání je teď nedostupné. Můžete přejít na hledání v projevech.");
      } finally {
        if (request === paletteRequest) list.removeAttribute("aria-busy");
      }
    }, 180);
  }
  function drawPalette(result, notice = "") {
    const q = input.value.trim();
    const f = fold(q);
    const groups = [];
    if (q) {
      const mps = data.endpoint ? result.mps : result.mps.filter((m) => fold(m.name).includes(f) || fold(`${m.sort} ${m.name}`).includes(f));
      groups.push(["Poslanci", mps, (m) => ({ url: m.url, title: m.name,
        html: `<span class="monogram monogram--24" aria-hidden="true">${escapeHtml(m.initials)}</span><span>${mark(m.name, q)}</span><span class="party-pill"><span class="swatch swatch--pending" aria-hidden="true"></span><span>${escapeHtml(m.party)}</span></span><span class="meta">${escapeHtml(m.region)}${m.term ? ` · ${m.term}. období` : ""}</span>` }), "poslanci.html"]);
      const bills = data.endpoint ? result.bills : result.bills.filter((b) => fold(`tisk ${b.tisk} ${b.title}`).includes(f));
      groups.push(["Body a tisky", bills, (b) => ({ url: b.url, title: `tisk ${b.tisk}${b.term ? ` (${b.term}. období)` : ""}`,
        html: `<span class="meta">tisk ${b.tisk}${b.term ? ` · ${b.term}. období` : ""}</span><span>${mark(b.title, q)}</span>` }), null]);
      const sittings = data.endpoint ? result.sittings : result.sittings.filter((s) => fold(`${s.number}. schuze ${s.number}`).includes(f));
      groups.push(["Schůze", sittings, (s) => ({ url: s.url, title: `${s.number}. schůze${s.term ? ` (${s.term}. období)` : ""}`,
        html: `<span>${mark(`${s.number}. schůze`, q)}</span><span class="meta">${s.term ? `${s.term}. období · ` : ""}${s.from ? (s.to && s.from !== s.to ? `${cz(s.from)} – ${cz(s.to)}` : cz(s.from)) : "Termín neuveden"}</span>` }), "schuze.html"]);
      groups.push(["Hledat v projevech", [q], () => ({ url: `${data.search}?q=${encodeURIComponent(q)}`, title: q,
        html: `<span>Hledat „${escapeHtml(q)}“ v&nbsp;projevech <span aria-hidden="true">→</span></span>` }), null]);
    } else {
      groups.push(["Akce", data.actions, (a) => ({ url: a.url, action: a.action, title: a.title, html: `<span>${escapeHtml(a.title)}</span>` }), null]);
      groups.push(["Nedávné", recent(), (r) => ({ url: r.url, title: r.title, html: `<span>${escapeHtml(r.title)}</span>` }), null]);
    }
    items = [];
    list.innerHTML = "";
    input.removeAttribute("aria-activedescendant");
    if (notice) {
      const message = document.createElement("p");
      message.className = "palette__empty"; message.setAttribute("role", "status");
      message.textContent = notice; list.append(message);
    }
    for (const [title, rows, toItem, more] of groups) {
      if (!rows.length) continue;
      const head = document.createElement("p");
      head.className = "palette__group label";
      head.textContent = title;
      list.appendChild(head);
      const shown = rows.slice(0, 6).map(toItem);
      if (rows.length > 6 && more) shown.push({ url: more, title, html: `<span>Zobrazit vše (${rows.length})</span>` });
      for (const item of shown) {
        const el = document.createElement("a");
        el.className = "palette__item";
        el.setAttribute("role", "option");
        el.id = `palette-item-${items.length}`;
        el.href = item.url || "#";
        el.tabIndex = -1;
        el.innerHTML = item.html;
        const index = items.length;
        el.addEventListener("pointermove", () => select(index));
        el.addEventListener("click", (e) => { e.preventDefault(); choose(index); });
        list.appendChild(el);
        items.push({ ...item, el });
      }
    }
    if (!items.length) list.innerHTML = '<p class="palette__empty">Nic nenalezeno.</p>';
    select(0);
  }
  function select(i) {
    if (!items.length) return;
    selected = (i + items.length) % items.length;
    items.forEach((it, j) => { it.el.classList.toggle("is-selected", j === selected); it.el.setAttribute("aria-selected", String(j === selected)); });
    input.setAttribute("aria-activedescendant", items[selected].el.id);
    items[selected].el.scrollIntoView({ block: "nearest" });
  }
  function choose(i) {
    const item = items[i];
    if (!item) return;
    if (item.action === "theme") { toggleTheme(); closePalette(); return; }
    remember({ url: item.url, title: item.title });
    location.href = new URL(item.url, document.baseURI).href;
  }
  function openPalette() {
    if (!palette) return;
    lastFocus = document.activeElement;
    openOverlay(palette, lastFocus);
    input.value = "";
    renderPalette();
    input.focus();
  }
  function closePalette() {
    cancelPaletteRequest();
    if (!palette || palette.hidden) return;
    closeOverlay();
  }
  if (palette) {
    input.addEventListener("input", renderPalette);
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); select(selected + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); select(selected - 1); }
      else if (e.key === "Enter") { e.preventDefault(); choose(selected); }
    });
    $$("[data-palette-open]").forEach((b) => b.addEventListener("click", openPalette));
    $$("[data-palette-close]").forEach((b) => b.addEventListener("click", closePalette));
  }

  /* ---------- keyboard shortcuts (§13: none hijack typing) ---------- */
  const reader = $("[data-reader]");
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.activeElement.isContentEditable;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); palette && (palette.hidden ? openPalette() : closePalette()); return; }
    if (e.key === "Escape") { hideCite(true); closePalette(); closeOverlay(); return; }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "/") { e.preventDefault(); openPalette(); }
    if (reader?.dataset.prev && e.key === "[") location.href = reader.dataset.prev;
    if (reader?.dataset.next && e.key === "]") location.href = reader.dataset.next;
  });

  /* ---------- full official title (§7.13) ---------- */
  $$("[data-clamp]").forEach((box) => {
    const button = $("button", box);
    button.addEventListener("click", () => {
      const open = box.classList.toggle("is-open");
      button.setAttribute("aria-expanded", String(open));
      button.textContent = open ? "Skrýt" : "Celý název";
    });
  });

  /* Only a selection inside one stored transcript paragraph can be quoted. */
  const bar = $("[data-selection-bar]");
  if (bar && reader) {
    let quoted = "";
    bar.addEventListener("pointerdown", e => e.preventDefault());
    document.addEventListener("selectionchange", () => {
      const sel = document.getSelection();
      if (!sel?.rangeCount || sel.isCollapsed) { bar.hidden = true; return; }
      const range = sel.getRangeAt(0);
      const node = range.commonAncestorContainer;
      const paragraph = (node.nodeType === 1 ? node : node.parentElement).closest(".speech__text");
      if (!paragraph || !reader.contains(paragraph)) { bar.hidden = true; return; }
      const text = sel.toString().trim().replace(/\u00a0/g, " ");
      if (!text) { bar.hidden = true; return; }
      const before = range.cloneRange(); before.selectNodeContents(paragraph); before.setEnd(range.startContainer, range.startOffset);
      const live = document.body.dataset.live === "true";
      const length = value => live ? Array.from(value).length : value.length;
      const start = length(before.toString()) + length(sel.toString()) - length(sel.toString().trimStart());
      const d = paragraph.closest(".speech").dataset;
      const r = range.getBoundingClientRect();
      quoted = `„${text}“\n${d.speaker}${d.party ? ` (${d.party})` : ""}, ${cz(d.date)}, ${d.sitting}. schůze, s. ${d.page}${d.status?.toLowerCase().includes("neautorizováno") ? ", neautorizováno" : ""}\n${paragraph.dataset.citationUrl ? new URL(paragraph.dataset.citationUrl, location.href).href : d.sourceUrl}`;
      const link = $("[data-card-selection]", bar);
      const key = paragraph.closest(".para").id.replace(/^p-/, "paragraph-");
      const params = new URLSearchParams({source: paragraph.dataset.quoteSource || key, start, end:start + length(text)});
      if (live) params.set("verze", d.revision);
      link.href = `${live ? "/karta" : "karta.html"}?${params}`;
      bar.hidden = false;
      bar.style.left = `${Math.max(8, Math.min(r.left, innerWidth - bar.offsetWidth - 8)) + scrollX}px`;
      bar.style.top = `${Math.max(scrollY + 8, r.top + scrollY - bar.offsetHeight - 10)}px`;
    });
    $("[data-cite-selection]", bar).addEventListener("click", () => copy(quoted, "Citace zkopírována"));
  }

  /* Four-line excerpts, with the omission mark inside the quotation. */
  const excerpts = $$(".obj:not(.obj--featured) .obj__excerpt").map(el => ({
    el, html: el.innerHTML, text: el.textContent,
    end: el.nextElementSibling?.classList.contains("cut") ? el.nextElementSibling : null,
  }));
  function fitExcerpts() {
    excerpts.forEach(({el, html, text, end}) => {
      if (!el.getClientRects().length) return;
      const p = el.closest("p");
      el.innerHTML = html;
      p.querySelector("[data-visual-cut]")?.remove();
      if (end) end.hidden = false;
      const maxHeight = parseFloat(getComputedStyle(p).lineHeight) * 4 + 1;
      if (p.getBoundingClientRect().height <= maxHeight) return;
      const cut = document.createElement("span");
      cut.className = "cut"; cut.dataset.visualCut = ""; cut.textContent = " …";
      cut.setAttribute("aria-hidden", "true"); el.after(cut);
      if (end) end.hidden = true;
      const words = [...text.matchAll(/\S+(?:\s+|$)/g)];
      function trim(count) {
        const length = count ? words[count-1].index + words[count-1][0].trimEnd().length : 0;
        el.innerHTML = html;
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let used = 0, node;
        while ((node = walker.nextNode())) {
          const value = node.textContent;
          node.textContent = value.slice(0, Math.max(0, length - used));
          used += value.length;
        }
        // A highlight emptied by the cut would still show its padding as a sliver.
        el.querySelectorAll("mark").forEach((mark) => { if (!mark.textContent.trim()) mark.replaceWith(mark.textContent); });
      }
      let low = 0, high = words.length;
      while (low < high) {
        const mid = Math.ceil((low + high) / 2); trim(mid);
        if (p.getBoundingClientRect().height <= maxHeight) low = mid; else high = mid - 1;
      }
      trim(low);
    });
  }
  document.fonts.ready.then(fitExcerpts);
  let excerptFrame;
  window.addEventListener("resize", () => { cancelAnimationFrame(excerptFrame); excerptFrame = requestAnimationFrame(fitExcerpts); });
  document.addEventListener("preview-results-change", fitExcerpts);

  /* ---------- dot-matrix reveal (§8.3) ---------- */
  const dots = $$(".dm-animate");
  if (dots.length && !reduced && "IntersectionObserver" in window) {
    dots.forEach((d) => d.classList.add("is-pending"));
    const io = new IntersectionObserver((entries) => entries.forEach((en) => {
      if (!en.isIntersecting) return;
      en.target.classList.replace("is-pending", "is-on");
      io.unobserve(en.target);
    }), { threshold: 0.4 });
    dots.forEach((d) => io.observe(d));
  }

  /* ---------- activity graph (§7.11) ---------- */
  const activity = $("[data-activity]");
  if (activity) {
    $$("[data-period]", activity).forEach((b) => b.addEventListener("click", () => {
      $$("[data-period]", activity).forEach((x) => x.setAttribute("aria-checked", String(x === b)));
      $$("[data-period-panel]", activity).forEach((p) => (p.hidden = p.dataset.periodPanel !== b.dataset.period));
      $$("[data-year]", activity).forEach(p => p.hidden = b.dataset.period !== "term" && p.dataset.year !== b.dataset.period);
    }));
    const toggle = $("[data-table-toggle]", activity);
    toggle.addEventListener("click", () => {
      const table = $("#activity-table");
      const hidden = table.classList.toggle("visually-hidden");
      toggle.setAttribute("aria-expanded", String(!hidden));
      toggle.lastChild.textContent = hidden ? " Zobrazit jako tabulku" : " Skrýt tabulku";
    });
    if (document.body.dataset.live !== "true") {
      const filter = $("[data-day-filter]");
      const objects = $$(".profile__main .obj");
      const search = $("#mp-q");
      const state = new URLSearchParams(location.search);
      let chosenDay = state.get("den") || "";
      search.value = state.get("q") || "";
      function applyProfile() {
        const query = fold(search.value.trim());
        let shown = 0;
        objects.forEach(o => {
          const hit = (!chosenDay || o.dataset.date === chosenDay) && (!query || fold(o.dataset.search).includes(query));
          o.closest("li").hidden = !hit; shown += hit;
        });
        $("[data-day-filter-label]", filter).textContent = `${chosenDay ? cz(chosenDay) + ": " : ""}${shown} z ukázkových projevů`;
        filter.hidden = !chosenDay && !query;
        state.delete("den"); state.delete("q");
        if (chosenDay) state.set("den", chosenDay);
        if (search.value) state.set("q", search.value);
        history.replaceState(null, "", `${location.pathname}${state.size ? `?${state}` : ""}${location.hash}`);
      }
      activity.addEventListener("click", e => {
        const day = e.target.closest("[data-day]");
        if (!day || !filter) return;
        chosenDay = day.dataset.day; applyProfile();
      });
      search.addEventListener("input", applyProfile);
      search.closest("form").addEventListener("submit", e => { e.preventDefault(); applyProfile(); });
      $("[data-day-filter-clear]", filter).addEventListener("click", () => {
        chosenDay = ""; search.value = ""; applyProfile();
      });
      applyProfile();
    }
  }

  /* ---------- MP directory (§11.5) ---------- */
  const directory = $("[data-directory]");
  if (directory) {
    const rows = $$("tbody tr", directory);
    const parties = new Set();
    const counter = $("[data-directory-count]", directory);
    function apply() {
      const region = $("[data-region-filter]", directory).value;
      const name = fold($("[data-name-filter]", directory).value.trim());
      let shown = 0;
      rows.forEach((r) => {
        const ok = (!parties.size || parties.has(r.dataset.party)) && (!region || r.dataset.region === region) && (!name || fold(r.dataset.search).includes(name));
        r.hidden = !ok;
        shown += ok;
      });
      counter.textContent = `${shown} z ${rows.length}`;
      $("[data-directory-empty]", directory).hidden = shown > 0;
    }
    $$("[data-party-filter]", directory).forEach((b) => b.addEventListener("click", () => {
      const p = b.dataset.partyFilter;
      parties.has(p) ? parties.delete(p) : parties.add(p);
      b.setAttribute("aria-pressed", String(parties.has(p)));
      apply();
    }));
    $("[data-region-filter]", directory).addEventListener("change", apply);
    $("[data-name-filter]", directory).addEventListener("input", apply);
    $("[data-name-filter]", directory).value = new URLSearchParams(location.search).get("q") || "";
    apply();
    const collator = new Intl.Collator("cs");
    $$("[data-sort]", directory).forEach((b) => b.addEventListener("click", () => {
      const th = b.closest("th");
      const dir = th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending";
      $$("thead th", directory).forEach((h) => h.removeAttribute("aria-sort"));
      th.setAttribute("aria-sort", dir);
      const key = b.dataset.sort;
      const numeric = key === "speeches" || key === "attendance";
      const value = (r) => (key === "name" ? r.dataset.name : r.dataset[key]);
      const sorted = rows.slice().sort((a, z) => {
        const c = numeric ? Number(value(a)) - Number(value(z)) : collator.compare(value(a), value(z)) || collator.compare(a.dataset.name, z.dataset.name);
        return dir === "ascending" ? c : -c;
      });
      const body = $("tbody", directory);
      sorted.forEach((r) => body.appendChild(r));
    }));
  }

  $$(".segmented[role=radiogroup]").forEach(group => {
    const buttons = $$("[role=radio]", group);
    const sync = () => buttons.forEach(b => b.tabIndex = b.getAttribute("aria-checked") === "true" ? 0 : -1);
    group.addEventListener("click", () => queueMicrotask(sync));
    group.addEventListener("keydown", e => {
      if (!["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "Home", "End"].includes(e.key)) return;
      e.preventDefault();
      const i = buttons.indexOf(document.activeElement);
      const next = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : (i + (["ArrowRight", "ArrowDown"].includes(e.key) ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next].click(); buttons[next].focus(); sync();
    });
    sync();
  });

  /* ---------- quote card composer (§7.14) ---------- */
  const frames = $$(".qcard-frame");
  function fit() {
    frames.forEach((f) => {
      const card = $(".qcard", f);
      if (!f.hidden && card) card.style.setProperty("--zoom", Math.min(1, f.clientWidth / Number(getComputedStyle(card).getPropertyValue("--w"))));
    });
  }
  $$("[data-card-size]").forEach((b) => b.addEventListener("click", () => {
    $$("[data-card-size]").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    frames.forEach((f) => (f.hidden = f.dataset.cardPanel !== b.dataset.cardSize));
    fit();
  }));
  if (frames.length) { fit(); window.addEventListener("resize", fit); }
})();
