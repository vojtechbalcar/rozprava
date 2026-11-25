/* URL-backed search controls. In the design preview they filter the six sample
   objects in place; on live pages (data-live) every change is a normal navigation
   to the server-rendered results, and links and forms work without this script. */
(() => {
  "use strict";
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const fold = s => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  const options = JSON.parse($("#filter-data").textContent);
  const page = $("[data-search-page]");
  const live = document.body.dataset.live === "true";
  const objects = page ? $$(".results .obj", page) : [];
  let params = new URLSearchParams(location.search), pop = null, opener = null;
  if (page && !params.has("q")) params.set("q", page.dataset.query);
  const values = key => params.getAll(key);
  const updateURL = () => {
    if (live) {
      params.delete("stranka");
      location.assign(`${page ? location.pathname : "/hledat"}${params.size ? `?${params}` : ""}`);
      return;
    }
    history.pushState(null, "", `${location.pathname}${params.size ? `?${params}` : ""}${location.hash}`);
    refresh();
  };
  let billController = null, billTimer = null;
  function close() {
    clearTimeout(billTimer); billController?.abort();
    if (pop) pop.remove();
    if (opener) opener.setAttribute("aria-expanded", "false");
    pop = null;
  }
  function clear(key) {
    if (key === "datum") { params.delete("od"); params.delete("do"); }
    else params.delete(key);
    updateURL();
  }
  function toggle(key, value) {
    const selected = values(key);
    params.delete(key);
    (selected.includes(value) ? selected.filter(v => v !== value) : [...selected, value]).forEach(v => params.append(key, v));
    updateURL();
  }
  function refresh() {
    $$("[data-filter]").forEach(b => {
      const key = b.dataset.filter;
      const chosen = key === "datum" ? [params.get("od"), params.get("do")].filter(Boolean) : values(key);
      const label = chosen.map(v => {
        const option = (options[key] || []).find(o => (o.value || o) === v);
        return option?.label || v;
      }).join(key === "datum" ? " – " : ", ");
      b.firstChild.textContent = `${b.dataset.label}${label ? `: ${label}` : ""}`;
      b.classList.toggle("chip--active", !!chosen.length);
      b.parentElement.querySelector("[data-filter-clear]").hidden = !chosen.length;
    });
    if (!page || live) return;
    const q = params.get("q") || "";
    $("#search-q").value = q;
    document.title = `${q || "Hledání"} · Rozprava`;
    const sameQuery = fold(q) === fold(page.dataset.query);
    const words = sameQuery ? [] : fold(q).split(/\s+/).filter(Boolean);
    const hits = objects.filter(o => {
      const d = o.dataset;
      const match = (!values("obdobi").length || values("obdobi").includes(d.term)) &&
        (!values("klub").length || values("klub").includes(d.party)) &&
        (!values("poslanec").length || values("poslanec").includes(d.speaker)) &&
        (!values("tisk").length || values("tisk").includes(d.bill)) &&
        (!params.get("od") || d.date >= params.get("od")) &&
        (!params.get("do") || d.date <= params.get("do")) && words.every(w => fold(d.search).includes(w));
      o.closest("li").hidden = !match;
      return match;
    });
    const newest = params.get("razeni") === "nejnovejsi";
    const ordered = newest ? objects.slice().sort((a,b) => b.dataset.date.localeCompare(a.dataset.date)) : objects;
    ordered.forEach(o => $(".results", page).append(o.closest("li")));
    const noun = hits.length === 1 ? "projev" : hits.length >= 2 && hits.length <= 4 ? "projevy" : "projevů";
    $("[data-result-count]").textContent = `${hits.length} ${noun} · seřazeno podle ${newest ? "data" : "relevance"}`;
    $("[data-search-empty]").hidden = !!hits.length;
    $(".results__end", page).hidden = !hits.length;
    const summary = $(".summary", page);
    if (summary) summary.hidden = !sameQuery || hits.length !== objects.length;
    $$("[data-facet]").forEach(a => {
      const selected = values(a.dataset.facet).includes(a.dataset.value);
      if (selected) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
    });
    $$("[data-month]").forEach(bar => {
      const month = bar.dataset.month;
      bar.classList.toggle("is-selected", !!(params.get("od") || params.get("do")) && (!params.get("od") || month >= params.get("od").slice(0,7)) && (!params.get("do") || month <= params.get("do").slice(0,7)));
    });
    document.dispatchEvent(new Event("preview-results-change"));
    $$("[data-result-sort]").forEach(a => {
      if (a.dataset.resultSort === (newest ? "nejnovejsi" : "relevance")) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
  }
  $$("[data-filter]").forEach(b => b.addEventListener("click", () => {
    const wasOpen = opener === b && pop;
    close();
    if (wasOpen) return;
    opener = b;
    b.setAttribute("aria-expanded", "true");
    pop = document.createElement("div");
    pop.className = "filter-pop";
    pop.setAttribute("role", "dialog");
    pop.setAttribute("aria-label", b.dataset.label);
    const key = b.dataset.filter;
    if (live && key === "tisk") {
      const container = pop;
      const input = document.createElement("input");
      input.type = "search"; input.maxLength = 200; input.placeholder = "Číslo nebo název tisku";
      input.setAttribute("aria-label", "Hledat tisk");
      const list = document.createElement("div"); list.className = "filter-pop__list";
      list.textContent = "Zadejte číslo nebo část názvu tisku.";
      pop.append(input, list);
      input.addEventListener("input", () => {
        clearTimeout(billTimer); billController?.abort();
        const q = input.value.trim();
        list.textContent = q ? "Hledám…" : "Zadejte číslo nebo část názvu tisku.";
        if (!q) return;
        billTimer = setTimeout(async () => {
          const controller = new AbortController(); billController = controller;
          try {
            const response = await fetch(`/api/palette?q=${encodeURIComponent(q)}`, {signal: controller.signal});
            if (!response.ok) throw new Error("lookup failed");
            const data = await response.json();
            if (controller.signal.aborted || pop !== container || input.value.trim() !== q) return;
            list.replaceChildren();
            for (const bill of data.bills) {
              const label = document.createElement("label"), check = document.createElement("input");
              const value = `${bill.term}-${bill.tisk}`;
              check.type = "checkbox"; check.checked = values("tisk").includes(value);
              check.addEventListener("change", () => toggle("tisk", value));
              label.append(check, document.createTextNode(`${bill.term}. období · tisk ${bill.tisk}: ${bill.title}`));
              list.append(label);
            }
            if (!data.bills.length) list.textContent = "Žádný tisk neodpovídá dotazu.";
          } catch (error) {
            if (!controller.signal.aborted && pop === container) list.textContent = "Tisky se nepodařilo načíst. Zkuste to znovu.";
          }
        }, 180);
      });
    } else if (key === "datum") {
      const form = document.createElement("form");
      form.className = "filter-pop__dates";
      for (const [name, label] of [["od", "Od"], ["do", "Do"]]) {
        const field = document.createElement("label");
        field.textContent = label;
        const input = document.createElement("input");
        input.type = "date"; input.name = name; input.value = params.get(name) || "";
        field.append(input); form.append(field);
      }
      const submit = document.createElement("button");
      submit.className = "btn btn--primary"; submit.textContent = "Použít období";
      form.append(submit);
      form.addEventListener("submit", e => {
        e.preventDefault();
        const from = form.elements.od, to = form.elements.do;
        to.setCustomValidity(from.value && to.value && from.value > to.value ? "Konec období musí být po začátku." : "");
        if (!form.reportValidity()) return;
        for (const name of ["od", "do"]) {
          const value = form.elements[name].value;
          value ? params.set(name, value) : params.delete(name);
        }
        updateURL(); close(); b.focus();
      });
      form.addEventListener("input", () => form.elements.do.setCustomValidity(""));
      pop.append(form);
    } else {
      if (["poslanec", "klub"].includes(key)) {
        const input = document.createElement("input");
        input.type = "search"; input.placeholder = "Hledat v seznamu"; input.setAttribute("aria-label", "Hledat v seznamu");
        input.addEventListener("input", () => $$("label", pop).forEach(l => l.hidden = !fold(l.textContent).includes(fold(input.value))));
        pop.append(input);
      }
      const list = document.createElement("div"); list.className = "filter-pop__list";
      (options[key] || []).forEach(option => {
        const value = option.value || option;
        const label = document.createElement("label");
        const check = document.createElement("input");
        check.type = "checkbox"; check.checked = values(key).includes(value);
        check.addEventListener("change", () => toggle(key, value));
        label.append(check, document.createTextNode(option.label || option)); list.append(label);
      });
      pop.append(list);
    }
    document.body.append(pop);
    const rect = b.getBoundingClientRect();
    pop.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - pop.offsetWidth - 16))}px`;
    pop.style.top = `${Math.max(12, Math.min(rect.bottom + 8, innerHeight - pop.offsetHeight - 16))}px`;
    $("input", pop)?.focus();
  }));
  $$("[data-filter-clear]").forEach(b => b.addEventListener("click", () => { close(); clear(b.dataset.filterClear); }));
  if (!live) {
    $$("[data-facet]").forEach(a => a.addEventListener("click", e => { e.preventDefault(); toggle(a.dataset.facet, a.dataset.value); }));
    $$("[data-result-sort]").forEach(a => a.addEventListener("click", e => { e.preventDefault(); params.set("razeni", a.dataset.resultSort); updateURL(); }));
  }
  document.addEventListener("pointerdown", e => { if (pop && !pop.contains(e.target) && !opener.contains(e.target)) close(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && pop) { close(); opener.focus(); } });
  window.addEventListener("resize", close);
  if (!live) window.addEventListener("popstate", () => { params = new URLSearchParams(location.search); refresh(); });
  if (!live) $$(".hero .search-bar, [data-search-page] .search-bar").forEach(form => form.addEventListener("submit", e => {
    params.set("q", $("input[name=q]", form).value.trim());
    e.preventDefault();
    if (page) updateURL(); else location.href = `${form.getAttribute("action")}?${params}`;
  }));
  $("[data-search-reset]")?.addEventListener("click", () => { params = new URLSearchParams({q:page.dataset.query}); updateURL(); });
  const histogram = $("[data-date-histogram]");
  if (histogram) {
    let first = null;
    const bars = $$("[data-month]", histogram);
    const indexAt = event => {
      const bounds = histogram.getBoundingClientRect();
      return Math.max(0, Math.min(bars.length - 1, Math.floor((event.clientX - bounds.left) / bounds.width * bars.length)));
    };
    histogram.addEventListener("pointerdown", e => {
      first = indexAt(e); histogram.setPointerCapture(e.pointerId);
    });
    histogram.addEventListener("pointermove", e => {
      if (first === null) return;
      const last = indexAt(e);
      bars.forEach((bar,i) => bar.classList.toggle("is-selected", i >= Math.min(first,last) && i <= Math.max(first,last)));
    });
    histogram.addEventListener("pointerup", e => {
      if (first === null) return;
      const last = indexAt(e), lo = Math.min(first,last), hi = Math.max(first,last);
      params.set("od", `${bars[lo].dataset.month}-01`);
      const [y,m] = bars[hi].dataset.month.split("-").map(Number);
      const end = new Date(Date.UTC(y,m,0));
      params.set("do", end.toISOString().slice(0,10));
      first = null; updateURL();
    });
    histogram.addEventListener("pointercancel", () => { first = null; });
    $("[data-date-picker]").addEventListener("click", () => {
      document.querySelector("[data-drawer-close]")?.click();
      $("[data-filter=datum]").click();
    });
  }
  refresh();
  // The chips now name every active filter; the server's plain list is the no-script fallback.
  if ($("[data-search-filters]")) $$(".active-filters").forEach(list => (list.hidden = true));
})();
