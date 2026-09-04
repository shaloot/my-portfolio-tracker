/* Portfolio - static frontend. Reads the three precomputed JSON files and
   renders; no business logic beyond formatting and drawing. All the math was
   done at build time by scripts/fetch.py, so this stays dumb and static.

   The pipeline precomputes every figure in each view currency (NATIVE + each
   display currency), so switching the currency view is just re-picking which
   precomputed numbers to show - no FX math happens in the browser. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const VIEW_KEY = "pf_view";
  const clone = (o) => JSON.parse(JSON.stringify(o));

  let DATA = { p: null, hist: null, news: null };
  let VIEW = "NATIVE"; // "NATIVE" or a display currency code (e.g. "INR")

  // Session working copy of the ledger: starts as the backend config and
  // accumulates every transaction staged in the UI (not yet saved/rebuilt).
  // Export, the row popup, and the "pending" badges all read from this.
  let stagedHoldings = [];
  let pendingSymbols = new Set();

  /* ---- formatting -------------------------------------------------- */
  const localeFor = (ccy) => (ccy === "INR" ? "en-IN" : "en-US");
  const money = (v, ccy, dp) =>
    new Intl.NumberFormat(localeFor(ccy), {
      style: "currency", currency: ccy, maximumFractionDigits: dp == null ? 0 : dp,
    }).format(v);
  const moneyPrecise = (v, ccy) => money(v, ccy, 2);
  const pct = (v) => (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
  const signClass = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "muted");
  const arrow = (v) => (v > 0 ? "▲" : v < 0 ? "▼" : "·");

  const svgNS = "http://www.w3.org/2000/svg";
  const el = (name, attrs) => {
    const n = document.createElementNS(svgNS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  };
  const escapeHtml = (s) =>
    String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const debounce = (fn, ms) => {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  };

  /* ---- load -------------------------------------------------------- */
  async function load() {
    try {
      const [p, h, n] = await Promise.all([
        fetch("data/portfolio.json").then((r) => { if (!r.ok) throw new Error("no portfolio"); return r.json(); }),
        fetch("data/history.json").then((r) => (r.ok ? r.json() : { series: [] })),
        fetch("data/news.json").then((r) => (r.ok ? r.json() : { market: [], by_symbol: {} })),
      ]);
      DATA = { p, hist: h, news: n };
      init();
    } catch (e) {
      $("app").hidden = true;
      $("error").hidden = false;
    }
  }

  function displaysOf() { return DATA.p.display_currencies || [DATA.p.base_currency]; }

  /* ---- one-time setup ---------------------------------------------- */
  function init() {
    const p = DATA.p;
    const displays = displaysOf();

    let saved = null;
    try { saved = localStorage.getItem(VIEW_KEY); } catch (e) { /* ignore */ }
    VIEW = saved === "NATIVE" || displays.includes(saved) ? saved : p.base_currency;

    stagedHoldings = (p.config_holdings || []).map(clone);
    pendingSymbols = new Set();
    refreshDatalist();

    buildToggle(displays);

    document.title = p.title || "Portfolio";
    $("owner").textContent = "End-of-day snapshot";
    const dt = new Date(p.generated_at);
    $("updated").textContent = "Updated " + (isNaN(dt) ? "—" :
      dt.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }));
    $("basecc").textContent = p.base_currency + " base";
    if (p.holdings.some((r) => r.stale)) $("freshdot").classList.add("stale");

    setupCsvIo();
    setupAddTxn();
    setupRowDetails();
    setupNewspaper();
    renderView();
    // The chart is drawn in pixel space, so redraw it when the window resizes.
    window.addEventListener("resize", debounce(() => { if (DATA.p) drawChartArea(DATA.hist, DATA.p); }, 160));
    $("app").setAttribute("aria-busy", "false");
  }

  function buildToggle(displays) {
    const host = $("viewtoggle");
    host.innerHTML = "";
    const label = (v) => (v === "NATIVE" ? "Native" : v);
    ["NATIVE", ...displays].forEach((v) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label(v);
      b.title = v === "NATIVE" ? "Each holding in its own currency" : "Show everything in " + v;
      b.setAttribute("aria-pressed", String(v === VIEW));
      b.addEventListener("click", () => {
        if (VIEW === v) return;
        VIEW = v;
        try { localStorage.setItem(VIEW_KEY, v); } catch (e) { /* ignore */ }
        [...host.children].forEach((c) => c.setAttribute("aria-pressed", String(c.textContent === label(v))));
        renderView();
      });
      host.appendChild(b);
    });
  }

  /* ---- render everything for the current view ---------------------- */
  function renderView() {
    const p = DATA.p;
    renderHero(p);
    drawChartArea(DATA.hist, p);
    marketSplit(p.holdings, p.base_currency);
    rows(p.holdings);
    renderNews(DATA.news, p.holdings);
  }

  // In NATIVE view the total has no single currency, so show every display
  // currency (dual INR + USD); otherwise show just the selected one.
  function heroCurrencies() { return VIEW === "NATIVE" ? displaysOf() : [VIEW]; }

  function renderHero(p) {
    const ccys = heroCurrencies();
    const dual = ccys.length > 1;
    $("viewnote").textContent = dual ? "· " + ccys.join(" & ") : "";

    // Big total value.
    $("total-value").innerHTML = ccys.map((c, i) => {
      const s = money(p.totals[c].value, c);
      return i === 0 ? s : `<span class="dual">${s}</span>`;
    }).join("");

    const signed = (t, k, pk, c) =>
      `<span class="${signClass(t[k])}">${arrow(t[k])} ${money(Math.abs(t[k]), c)} (${pct(t[pk])})</span>`;

    fillNode($("day-change"), ccys, (c) => signed(p.totals[c], "day", "day_pct", c));
    fillNode($("total-pnl"), ccys, (c) => signed(p.totals[c], "pnl", "pnl_pct", c));
    fillNode($("total-cost"), ccys, (c) => `<span class="muted">${money(p.totals[c].cost, c)}</span>`, "muted");

    // Realized P&L only appears once you've sold something.
    const anyReal = ccys.some((c) => Math.abs(p.totals[c].realized || 0) >= 0.005);
    $("realized-block").hidden = !anyReal;
    if (anyReal) {
      fillNode($("total-realized"), ccys, (c) => {
        const rz = p.totals[c].realized || 0;
        return `<span class="${signClass(rz)}">${arrow(rz)} ${money(Math.abs(rz), c)}</span>`;
      });
    }
  }

  function fillNode(node, ccys, fn, extra) {
    node.className = "fig-md mono" + (extra ? " " + extra : "");
    node.innerHTML = ccys.map((c, i) => (i === 0 ? fn(c) : `<span class="dual">${fn(c)}</span>`)).join("");
  }

  // The figures block for a holding under the current view.
  const figOf = (r) => r.figures[VIEW] || r.figures.NATIVE;

  /* ---- Signature: cost-basis waterline chart(s) -------------------- */
  function drawChartArea(hist, p) {
    const host = $("chart");
    host.innerHTML = "";
    host.classList.remove("multi");
    const ccys = heroCurrencies();
    if (ccys.length > 1) {
      host.classList.add("multi");
      // Append every cell first so flex layout settles, THEN measure + draw
      // (drawing per-cell inline would measure the next cell before it has width).
      const pending = ccys.map((c) => {
        const cell = document.createElement("div");
        cell.className = "cell";
        const lab = document.createElement("div");
        lab.className = "chart-mini-label";
        lab.textContent = c;
        const svgHost = document.createElement("div");
        svgHost.className = "svg-host";
        cell.appendChild(lab); cell.appendChild(svgHost); host.appendChild(cell);
        return [svgHost, c];
      });
      pending.forEach(([svgHost, c]) => drawWaterline(svgHost, hist, c, p.base_currency));
    } else {
      drawWaterline(host, hist, ccys[0], p.base_currency);
    }
  }

  function drawWaterline(hostEl, hist, ccy, baseCcy) {
    const raw = (hist && hist.series) || [];
    const series = raw.map((d) => ({
      date: d.date,
      value: d.value && typeof d.value === "object" ? (d.value[ccy] ?? d.value[baseCcy]) : d.value_base,
      cost: d.cost && typeof d.cost === "object" ? (d.cost[ccy] ?? d.cost[baseCcy]) : d.cost_base,
    })).filter((d) => d.value != null && d.cost != null);

    if (series.length < 2) {
      hostEl.innerHTML = '<p class="muted mono" style="font-size:12px">Chart appears after the first daily build.</p>';
      return;
    }

    // Draw in the host's own pixel space so nothing is stretched (crisp text +
    // natural line/stroke proportions). Falls back to sane defaults pre-layout.
    const W = Math.max(Math.round(hostEl.clientWidth) || 0, 160);
    const H = Math.max(Math.round(hostEl.clientHeight) || 0, 160);
    const padL = 10, padR = 10, padT = 16, padB = 26;
    const vals = series.map((d) => d.value);
    const cost = series[series.length - 1].cost;
    const lo = Math.min(...vals, cost), hi = Math.max(...vals, cost);
    const span = (hi - lo) || 1;
    const pad = span * 0.12;
    const yMin = lo - pad, yMax = hi + pad;

    const x = (i) => padL + (i / (series.length - 1)) * (W - padL - padR);
    const y = (v) => padT + (1 - (v - yMin) / (yMax - yMin)) * (H - padT - padB);
    const costY = y(cost);

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: "100%" });

    const defs = el("defs", {});
    const uid = "c" + Math.abs(hashCode(ccy));
    const cTop = el("clipPath", { id: uid + "t" });
    cTop.appendChild(el("rect", { x: 0, y: 0, width: W, height: Math.max(0, costY) }));
    const cBot = el("clipPath", { id: uid + "b" });
    cBot.appendChild(el("rect", { x: 0, y: costY, width: W, height: Math.max(0, H - costY) }));
    defs.appendChild(cTop); defs.appendChild(cBot);
    svg.appendChild(defs);

    let d = `M ${x(0).toFixed(1)} ${y(vals[0]).toFixed(1)}`;
    for (let i = 1; i < series.length; i++) d += ` L ${x(i).toFixed(1)} ${y(vals[i]).toFixed(1)}`;
    d += ` L ${x(series.length - 1).toFixed(1)} ${costY.toFixed(1)} L ${x(0).toFixed(1)} ${costY.toFixed(1)} Z`;
    svg.appendChild(el("path", { d, fill: "var(--up)", opacity: 0.14, "clip-path": `url(#${uid}t)` }));
    svg.appendChild(el("path", { d, fill: "var(--down)", opacity: 0.14, "clip-path": `url(#${uid}b)` }));

    svg.appendChild(el("line", {
      x1: padL, y1: costY, x2: W - padR, y2: costY,
      stroke: "var(--muted)", "stroke-width": 1, "stroke-dasharray": "4 4", opacity: 0.7,
    }));

    let ld = `M ${x(0).toFixed(1)} ${y(vals[0]).toFixed(1)}`;
    for (let i = 1; i < series.length; i++) ld += ` L ${x(i).toFixed(1)} ${y(vals[i]).toFixed(1)}`;
    const endUp = vals[vals.length - 1] >= cost;
    const endColor = endUp ? "var(--up)" : "var(--down)";
    svg.appendChild(el("path", {
      class: "val-line", d: ld, fill: "none", stroke: endColor, pathLength: 1,
      "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round",
    }));
    svg.appendChild(el("circle", {
      cx: x(series.length - 1), cy: y(vals[vals.length - 1]), r: 3.5, fill: endColor,
    }));

    const lbl = (i, anchor) => {
      const txt = el("text", {
        x: x(i), y: H - 6, "text-anchor": anchor,
        fill: "var(--muted)", "font-size": 10, "font-family": "var(--mono)",
      });
      const dt = new Date(series[i].date);
      txt.textContent = isNaN(dt) ? series[i].date
        : dt.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      svg.appendChild(txt);
    };
    lbl(0, "start"); lbl(series.length - 1, "end");

    // --- Hover interaction: guide line, focus dot, and a tooltip ----------
    const guide = el("line", {
      x1: 0, y1: padT, x2: 0, y2: H - padB, stroke: "var(--muted)",
      "stroke-width": 1, "stroke-dasharray": "3 3", opacity: 0,
    });
    const focus = el("circle", { r: 4, fill: "var(--ink)", stroke: "var(--surface)", "stroke-width": 1.5, opacity: 0 });
    const overlay = el("rect", { x: 0, y: 0, width: W, height: H, fill: "transparent", style: "cursor:crosshair" });
    svg.appendChild(guide); svg.appendChild(focus); svg.appendChild(overlay);

    hostEl.innerHTML = "";
    hostEl.appendChild(svg);

    const tip = document.createElement("div");
    tip.className = "chart-tip"; tip.style.display = "none";
    hostEl.appendChild(tip);

    const fmtD = (s) => { const d = new Date(s); return isNaN(d) ? s : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }); };
    const moveTip = (ev) => {
      const r = svg.getBoundingClientRect();
      const px = ((ev.clientX - r.left) / r.width) * W;   // svg-space x
      const frac = (px - padL) / ((W - padL - padR) || 1);
      const i = Math.max(0, Math.min(series.length - 1, Math.round(frac * (series.length - 1))));
      const d = series[i], cx = x(i), cy = y(d.value);
      const prev = i > 0 ? series[i - 1].value : d.value;
      const day = d.value - prev, dayPct = prev ? (day / prev) * 100 : 0;
      const pnl = d.value - d.cost, pnlPct = d.cost ? (pnl / d.cost) * 100 : 0;
      const up = d.value >= d.cost;
      guide.setAttribute("x1", cx); guide.setAttribute("x2", cx); guide.setAttribute("opacity", 0.55);
      focus.setAttribute("cx", cx); focus.setAttribute("cy", cy); focus.setAttribute("opacity", 1);
      focus.setAttribute("fill", up ? "var(--up)" : "var(--down)");
      tip.innerHTML =
        `<div class="tt-date">${fmtD(d.date)}</div>
         <div class="tt-row"><span>Value</span><b>${money(d.value, ccy)}</b></div>
         <div class="tt-row"><span>Day</span><b class="${signClass(day)}">${arrow(day)} ${money(Math.abs(day), ccy)} (${pct(dayPct)})</b></div>
         <div class="tt-row"><span>P&amp;L</span><b class="${signClass(pnl)}">${money(pnl, ccy)} (${pct(pnlPct)})</b></div>`;
      tip.style.display = "block";
      const scale = r.width / W;                          // px per svg-unit
      let left = cx * scale + 14;
      if (left + tip.offsetWidth > r.width) left = cx * scale - tip.offsetWidth - 14;
      let top = Math.max(2, cy * scale - tip.offsetHeight - 10);
      tip.style.left = Math.max(2, left) + "px"; tip.style.top = top + "px";
    };
    overlay.addEventListener("mousemove", moveTip);
    overlay.addEventListener("mouseleave", () => {
      tip.style.display = "none"; guide.setAttribute("opacity", 0); focus.setAttribute("opacity", 0);
    });
  }

  function hashCode(s) {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i) | 0;
    return h;
  }

  /* ---- Allocation by market (mini-bar) ----------------------------- */
  function marketSplit(holdings, baseCcy) {
    let inV = 0, usV = 0;
    holdings.forEach((r) => {
      const v = r.figures[baseCcy].value;
      r.market === "IN" ? (inV += v) : (usV += v);
    });
    const tot = inV + usV || 1;
    const inPct = (inV / tot) * 100;
    $("market-split").innerHTML =
      `<span class="key"><span class="swatch" style="background:var(--accent)"></span>IN ${inPct.toFixed(0)}%</span>` +
      `<span class="bar"><span class="seg-in" style="width:${inPct}%"></span><span class="seg-us" style="width:${100 - inPct}%"></span></span>` +
      `<span class="key"><span class="swatch" style="background:var(--accent-2)"></span>US ${(100 - inPct).toFixed(0)}%</span>`;
  }

  /* ---- Holdings rows ----------------------------------------------- */
  function rows(holdings) {
    const tb = $("rows");
    tb.innerHTML = "";
    const maxW = Math.max(...holdings.map((r) => r.weight_pct), 1);
    holdings.forEach((r) => {
      const f = figOf(r);
      const tr = document.createElement("tr");
      const dayCls = signClass(f.day_pct), pnlCls = signClass(f.pnl);
      const spark = sparkline(r.spark, r.figures.NATIVE.pnl >= 0);
      const stale = r.stale
        ? ` <span class="stale-flag" title="${escapeHtml(r.error || "price unavailable")}">stale</span>`
        : "";
      // Show the stale reason inline so a delisting/rename is easy to spot.
      const staleReason = r.stale
        ? `<div class="stale-reason" title="${escapeHtml(r.error || "")}">last price unavailable${r.error ? ": " + escapeHtml(r.error) : ""}</div>`
        : "";
      // Flag rows with an unsaved transaction staged this session.
      const pend = pendingSymbols.has(r.symbol.toUpperCase())
        ? ` <span class="pending-flag" title="Unsaved transaction(s) staged - open the row (⋮) to see them, then rebuild to apply">pending</span>`
        : "";
      // Avg cost / Last / Value / P&L all follow the selected view currency (f.ccy).
      tr.innerHTML =
        `<td class="l">
           <span class="sym">${escapeHtml(r.symbol)}</span><span class="mkt-tag">${r.market}</span>${stale}${pend}
           <div class="name">${escapeHtml(r.name)}</div>${staleReason}
         </td>
         <td class="r">${r.quantity}</td>
         <td class="r">${moneyPrecise(f.avg, f.ccy)}</td>
         <td class="r">${moneyPrecise(f.last, f.ccy)}</td>
         <td class="r ${dayCls}">${pct(f.day_pct)}</td>
         <td class="c">${spark}</td>
         <td class="r">${money(f.value, f.ccy)}</td>
         <td class="r ${pnlCls}">${money(f.pnl, f.ccy)}<div class="name ${pnlCls}">${pct(f.pnl_pct)}</div></td>
         <td class="r wgt">${r.weight_pct.toFixed(1)}%<span class="wgt-bar" style="width:${(r.weight_pct / maxW) * 46 + 4}px"></span></td>
         <td class="c"><button type="button" class="rowbtn" data-sym="${escapeHtml(r.symbol)}" title="Transaction history" aria-label="Transactions for ${escapeHtml(r.symbol)}">&#8942;</button></td>`;
      tb.appendChild(tr);
    });
  }

  function sparkline(points, positive) {
    if (!points || points.length < 2) return "";
    const w = 68, h = 22, lo = Math.min(...points), hi = Math.max(...points), s = (hi - lo) || 1;
    const step = w / (points.length - 1);
    const d = points
      .map((v, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(1)} ${(h - ((v - lo) / s) * (h - 4) - 2).toFixed(1)}`)
      .join(" ");
    const col = positive ? "var(--up)" : "var(--down)";
    return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="${d}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round"/></svg>`;
  }

  /* ---- News -------------------------------------------------------- */
  function newsLi(item, withTicker) {
    const li = document.createElement("li");
    const when = item.published ? new Date(item.published) : null;
    const whenStr = when && !isNaN(when)
      ? " · " + when.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
    const tkr = withTicker && item.symbol ? `<span class="tkr">${escapeHtml(item.symbol)}</span> · ` : "";
    li.innerHTML =
      `<a href="${encodeURI(item.url || "#")}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a>
       <span class="src">${tkr}${escapeHtml(item.source || "")}${whenStr}</span>`;
    return li;
  }

  function renderNews(news, holdings) {
    const mkt = $("market-news"); mkt.innerHTML = "";
    (news.market || []).forEach((it) => mkt.appendChild(newsLi(it, false)));
    if (!(news.market || []).length) mkt.innerHTML = '<li class="muted">No market headlines in this build.</li>';

    const hn = $("holding-news"); hn.innerHTML = "";
    const flat = [];
    holdings.forEach((r) => (news.by_symbol[r.symbol] || []).forEach((it) => flat.push(it)));
    flat.slice(0, 8).forEach((it) => hn.appendChild(newsLi(it, true)));
    if (!flat.length) hn.innerHTML = '<li class="muted">No holding-specific news in this build.</li>';
  }

  /* ---- Per-holding transaction history popup ----------------------- */
  function setupRowDetails() {
    const modal = $("row-modal");
    const close = () => { modal.hidden = true; };
    $("row-close").addEventListener("click", close);
    $("row-done").addEventListener("click", close);
    modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) close(); });
    // Delegated: rows are re-rendered on every view change.
    $("rows").addEventListener("click", (e) => {
      const btn = e.target.closest(".rowbtn");
      if (btn) openRowModal(btn.getAttribute("data-sym"));
    });
  }

  function openRowModal(sym) {
    const row = (DATA.p.holdings || []).find((r) => r.symbol === sym);
    const cfg = stagedFor(sym) || row;          // working copy = config + staged txns
    if (!cfg) return;
    const ccy = row ? row.currency : (cfg.market === "IN" ? "INR" : "USD");
    const last = row ? row.last : null;          // native current price (if known)

    const lots = lotsOf(cfg).slice().sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
    const staged = lots.filter((l) => l._staged).length;

    $("row-title").textContent = `${sym} · ${row ? row.name : cfg.name || sym}`;
    const tb = $("row-txn-body");
    tb.innerHTML = "";
    let bal = 0;
    lots.forEach((l) => {
      const q = Number(l.quantity) || 0, price = Number(l.price) || 0;
      const sell = l.action === "sell";
      bal += sell ? -q : q;
      const tag = l._staged ? ' <span class="txn-staged" title="staged this session, not yet saved">pending</span>' : "";
      const tr = document.createElement("tr");
      if (l._staged) tr.className = "staged";
      tr.innerHTML =
        `<td class="l">${l.date ? escapeHtml(l.date) : '<span class="muted">opening</span>'}${tag}</td>
         <td class="l"><span class="act ${sell ? "sell" : "buy"}">${sell ? "SELL" : "BUY"}</span></td>
         <td class="r">${q}</td>
         <td class="r">${moneyPrecise(price, ccy)}</td>
         <td class="r">${money(q * price, ccy)}</td>
         <td class="r">${+bal.toFixed(4)}</td>`;
      tb.appendChild(tr);
    });

    // Recompute the net balance from the (possibly staged) lots. Native currency
    // is FX-free, so this is exact in the browser even for staged transactions.
    const pos = nativePosition(lots, last);
    const line = (k, v, cls, net) =>
      `<div class="rs-row${net ? " net" : ""}"><span class="rs-k">${k}</span><span class="rs-v ${cls || ""}">${v}</span></div>`;
    let html = "";
    if (staged) {
      html += `<div class="rs-pending">Includes ${staged} unsaved transaction${staged !== 1 ? "s" : ""}. `
        + `Figures below are estimates; save the CSV and rebuild to apply.</div>`;
    }
    html += line("Net quantity", String(+pos.qty.toFixed(4)), "", true)
      + line("Average cost", moneyPrecise(pos.avg, ccy))
      + line("Invested (cost basis)", money(pos.cost, ccy));
    if (pos.value != null) {
      const pnl = pos.value - pos.cost;
      html += line("Market value", money(pos.value, ccy))
        + line("Unrealized P&L", `${money(pnl, ccy)} (${pct(pos.cost ? pnl / pos.cost * 100 : 0)})`, signClass(pnl));
    } else {
      html += line("Market value", '<span class="muted">priced after rebuild</span>');
    }
    if (Math.abs(pos.realized || 0) >= 0.005) {
      html += line("Realized P&L (from sells)", money(pos.realized, ccy), signClass(pos.realized));
    }
    $("row-summary").innerHTML = html;
    $("row-modal").hidden = false;
    try { $("row-close").focus(); } catch (e) { /* ignore */ }
  }

  /* ---- Add-transaction builder ------------------------------------- */
  // The site is static and must not fetch prices/FX in the browser, so this
  // records the buy/sell into an updated config/holdings.csv (the friendly,
  // spreadsheet-editable ledger) for the user to save + rebuild; the pipeline
  // then does the forex-accurate recompute.
  const CSV_HEADER = ["symbol", "name", "market", "date", "action", "quantity", "price"];

  const csvCell = (v) => {
    const s = String(v == null ? "" : v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const numCell = (x) => {
    const f = Number(x);
    return Number.isFinite(f) ? String(f) : "";
  };
  function holdingsToCsv(holdings) {
    const lines = [CSV_HEADER.join(",")];
    holdings.forEach((h) => {
      let lots = h.lots;
      if (!lots || !lots.length) lots = [{ date: null, action: "buy", quantity: h.quantity, price: h.avg_cost }];
      lots.forEach((l) => {
        lines.push([h.symbol || "", h.name || "", h.market || "", l.date || "",
          l.action || "buy", numCell(l.quantity), numCell(l.price)].map(csvCell).join(","));
      });
    });
    return lines.join("\n") + "\n";
  }

  function downloadFile(fn, text) {
    const blob = new Blob([text], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = fn; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // Staged-ledger helpers ------------------------------------------------
  const stagedFor = (sym) =>
    stagedHoldings.find((h) => (h.symbol || "").toUpperCase() === String(sym).toUpperCase());

  function lotsOf(h) {
    return (h && h.lots && h.lots.length)
      ? h.lots
      : [{ date: null, action: "buy", quantity: h ? h.quantity : 0, price: h ? h.avg_cost : 0 }];
  }

  // Append a buy/sell to the working copy; tags it `_staged` so it can be marked
  // and the affected symbol flagged pending. Migrates a legacy holding to lots.
  function stageLot(sym, name, market, lot) {
    sym = sym.toUpperCase();
    const tagged = Object.assign({ _staged: true }, lot);
    const h = stagedFor(sym);
    if (h) {
      if (!Array.isArray(h.lots)) {
        h.lots = [{ date: null, action: "buy", quantity: h.quantity, price: h.avg_cost }];
        delete h.quantity; delete h.avg_cost;
      }
      h.lots.push(tagged);
      h.lots.sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
    } else {
      stagedHoldings.push({ symbol: sym, name, market, lots: [tagged] });
    }
    pendingSymbols.add(sym);
  }

  // Average-cost accounting in native currency (FX-free, so exact in-browser):
  // mirrors core/compute.process_lots for one holding.
  function nativePosition(lots, lastPrice) {
    const sorted = lots.slice().sort((a, b) => String(a.date || "").localeCompare(String(b.date || "")));
    let qty = 0, cost = 0, realized = 0;
    sorted.forEach((l) => {
      const q = Math.abs(Number(l.quantity) || 0), price = Number(l.price) || 0;
      if (l.action === "sell") {
        if (qty <= 0) return;
        const s = Math.min(q, qty), avg = qty ? cost / qty : 0;
        realized += s * (price - avg); cost -= s * avg; qty -= s;
      } else { cost += q * price; qty += q; }
    });
    return { qty, avg: qty ? cost / qty : 0, cost, realized, value: lastPrice != null ? qty * lastPrice : null };
  }

  function refreshDatalist() {
    const dl = $("sym-list");
    if (!dl) return;
    dl.innerHTML = "";
    stagedHoldings.forEach((h) => { const o = document.createElement("option"); o.value = h.symbol; dl.appendChild(o); });
  }

  // Changes are staged in this session only - the static page can't recompute or
  // write your repo. Show a persistent reminder until the user rebuilds/dismisses.
  let pendingCount = 0;
  function markPending(desc) {
    pendingCount++;
    $("pending-text").textContent = pendingCount === 1
      ? `Change staged: ${desc}. `
      : `${pendingCount} changes staged this session. `;
    $("pending-banner").hidden = false;
    try { $("pending-banner").scrollIntoView({ block: "nearest", behavior: "smooth" }); } catch (e) { /* ignore */ }
  }

  // Same header aliases as scripts/core/holdings_io.py, for browser-side import.
  const CSV_ALIASES = {
    symbol: "symbol", ticker: "symbol", name: "name", company: "name",
    market: "market", exchange: "market", date: "date", txn_date: "date",
    trade_date: "date", action: "action", type: "action", side: "action",
    txn: "action", quantity: "quantity", qty: "quantity", shares: "quantity",
    units: "quantity", price: "price", cost: "price", avg_cost: "price",
    amount: "price", rate: "price",
  };

  // Minimal RFC-4180-ish CSV tokenizer (handles quotes, commas, newlines).
  function parseCsvRows(text) {
    const rows = []; let field = "", row = [], inq = false;
    const pushF = () => { row.push(field); field = ""; };
    const pushR = () => { rows.push(row); row = []; };
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inq) {
        if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inq = false; }
        else field += c;
      } else if (c === '"') inq = true;
      else if (c === ",") pushF();
      else if (c === "\n") { pushF(); pushR(); }
      else if (c !== "\r") field += c;
    }
    if (field.length || row.length) { pushF(); pushR(); }
    return rows.filter((r) => !(r.length === 1 && r[0].trim() === ""));
  }

  function parseCsvToHoldings(text) {
    const rows = parseCsvRows(text);
    if (!rows.length) return { holdings: [], errors: ["The file is empty."], txnCount: 0 };
    const cols = rows[0].map((h) => CSV_ALIASES[String(h).trim().toLowerCase().replace(/ /g, "_")] || null);
    const idx = (n) => cols.indexOf(n);
    if (idx("symbol") < 0 || idx("quantity") < 0 || idx("price") < 0) {
      return { holdings: [], errors: ["Header must include symbol, quantity and price columns."], txnCount: 0 };
    }
    const order = [], bySym = {}, errors = []; let txn = 0;
    for (let r = 1; r < rows.length; r++) {
      const cells = rows[r];
      const get = (n) => { const j = idx(n); return j >= 0 && j < cells.length ? String(cells[j]).trim() : ""; };
      const sym = get("symbol").toUpperCase();
      if (!sym || sym.startsWith("_") || sym.startsWith("#")) continue;
      const qs = get("quantity").replace(/,/g, ""), ps = get("price").replace(/,/g, "");
      const qty = parseFloat(qs), price = parseFloat(ps);
      const market = get("market").toUpperCase();
      const action = (get("action") || "buy").toLowerCase();
      if (!(qty > 0)) { errors.push(`Row ${r + 1} (${sym}): quantity "${qs}" is not a positive number - skipped.`); continue; }
      if (!(price >= 0)) { errors.push(`Row ${r + 1} (${sym}): price "${ps}" is not a number - skipped.`); continue; }
      if (market && market !== "IN" && market !== "US") errors.push(`Row ${r + 1} (${sym}): market "${market}" should be IN or US.`);
      if (action !== "buy" && action !== "sell") errors.push(`Row ${r + 1} (${sym}): action "${action}" should be buy or sell.`);
      if (!bySym[sym]) { bySym[sym] = { symbol: sym, name: sym, market: market || "US", lots: [] }; order.push(sym); }
      const h = bySym[sym];
      if (get("name")) h.name = get("name");
      if (market === "IN" || market === "US") h.market = market;
      h.lots.push({ date: get("date") || null, action: action === "sell" ? "sell" : "buy", quantity: Math.abs(qty), price });
      txn++;
    }
    return { holdings: order.map((s) => bySym[s]), errors, txnCount: txn };
  }

  function setupCsvIo() {
    const p = DATA.p;
    $("pending-dismiss").addEventListener("click", () => { $("pending-banner").hidden = true; pendingCount = 0; });
    // Export the working copy, so any transactions staged this session are included.
    $("exportbtn").addEventListener("click", () => downloadFile("holdings.csv", holdingsToCsv(stagedHoldings)));

    const file = $("imp-file");
    $("importbtn").addEventListener("click", () => file.click());
    file.addEventListener("change", () => {
      const f = file.files && file.files[0];
      if (!f) return;
      const reader = new FileReader();
      reader.onload = () => { showImport(String(reader.result || "")); file.value = ""; };
      reader.onerror = () => { file.value = ""; };
      reader.readAsText(f);
    });

    const modal = $("import-modal");
    const close = () => { modal.hidden = true; };
    $("imp-close").addEventListener("click", close);
    $("imp-done").addEventListener("click", close);
    modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) close(); });

    function showImport(text) {
      const res = parseCsvToHoldings(text);
      const cleaned = holdingsToCsv(res.holdings);
      const nH = res.holdings.length, nT = res.txnCount;
      $("imp-summary").textContent = nH
        ? `Parsed ${nT} transaction${nT !== 1 ? "s" : ""} across ${nH} holding${nH !== 1 ? "s" : ""}.`
        : "No valid holdings found.";
      const errBox = $("imp-errors");
      if (res.errors.length) {
        errBox.innerHTML = `<strong style="font-size:12.5px">${res.errors.length} issue${res.errors.length !== 1 ? "s" : ""}:</strong><ul>`
          + res.errors.slice(0, 12).map((e) => `<li>${escapeHtml(e)}</li>`).join("")
          + (res.errors.length > 12 ? `<li>and ${res.errors.length - 12} more</li>` : "") + "</ul>";
      } else {
        errBox.innerHTML = nH ? '<span class="ok">All rows valid.</span>' : "";
      }
      $("imp-preview").textContent = res.holdings.map((h) => `${h.symbol} (${h.market}) - ${h.lots.length} lot(s)`).join("\n");
      $("imp-cmd").textContent =
        "# save this over config/holdings.csv, then:\n" +
        "python scripts/fetch.py && bash scripts/build_site.sh";
      const dl = $("imp-download"); dl.disabled = !nH;
      dl.onclick = () => {
        downloadFile("holdings.csv", cleaned);
        // Adopt the imported ledger as the working copy so Export + rows reflect it.
        stagedHoldings = res.holdings.map(clone);
        pendingSymbols = new Set(res.holdings.map((h) => (h.symbol || "").toUpperCase()));
        refreshDatalist(); renderView();
        markPending(`imported ${nH} holding${nH !== 1 ? "s" : ""}`);
      };
      $("imp-copy").onclick = () => {
        if (!navigator.clipboard) return;
        navigator.clipboard.writeText(cleaned).then(() => {
          $("imp-copy").textContent = "Copied!";
          setTimeout(() => ($("imp-copy").textContent = "Copy CSV"), 1500);
        });
      };
      modal.hidden = false;
    }
  }

  function setupAddTxn() {
    const p = DATA.p;
    const modal = $("txn-modal");

    const findCfg = (sym) => stagedFor(sym);   // includes staged additions
    const findRow = (sym) => (p.holdings || []).find((r) => r.symbol.toUpperCase() === sym.toUpperCase());
    // Current net quantity for a symbol, including transactions staged this session.
    const stagedQty = (sym) => {
      const h = stagedFor(sym);
      return h ? nativePosition(lotsOf(h), null).qty : 0;
    };

    const priceLabel = () => {
      $("f-price-label").textContent = "Price per share (" + ($("f-market").value === "IN" ? "INR" : "USD") + ")";
    };

    function resetForm() {
      $("txn-form").hidden = false; $("txn-result").hidden = true;
      $("txn-form").reset();
      $("f-name").disabled = false; $("f-market").disabled = false;
      $("txn-hint").textContent = ""; $("txn-hint").classList.remove("warn");
      priceLabel();
    }
    const open = () => { resetForm(); modal.hidden = false; $("f-symbol").focus(); };
    const close = () => { modal.hidden = true; };

    $("addbtn").addEventListener("click", open);
    $("txn-close").addEventListener("click", close);
    $("txn-cancel").addEventListener("click", close);
    $("txn-done").addEventListener("click", close);
    modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) close(); });
    $("f-market").addEventListener("change", priceLabel);

    $("f-symbol").addEventListener("input", () => {
      const h = findCfg($("f-symbol").value.trim());
      const hint = $("txn-hint"); hint.classList.remove("warn");
      if (h) {
        $("f-name").value = h.name || ""; $("f-name").disabled = true;
        $("f-market").value = h.market; $("f-market").disabled = true;
        priceLabel();
        const ccy = h.market === "IN" ? "INR" : "USD";
        const pos = nativePosition(lotsOf(h), null);
        const pend = pendingSymbols.has((h.symbol || "").toUpperCase()) ? " (incl. staged)" : "";
        hint.textContent = `Existing: ${+pos.qty.toFixed(4)} sh @ avg ${moneyPrecise(pos.avg, ccy)}${pend}.`;
      } else {
        $("f-name").disabled = false; $("f-market").disabled = false;
        hint.textContent = $("f-symbol").value.trim() ? "New holding." : "";
      }
    });

    function sellCheck() {
      const hint = $("txn-hint");
      if ($("f-action").value !== "sell") { hint.classList.remove("warn"); return; }
      const held = stagedQty($("f-symbol").value.trim());
      const q = parseFloat($("f-qty").value || "0");
      if (held && q > held) {
        hint.textContent = `Selling ${q} but only ${+held.toFixed(4)} held - the pipeline will cap it.`;
        hint.classList.add("warn");
      } else { hint.classList.remove("warn"); }
    }
    $("f-action").addEventListener("change", sellCheck);
    $("f-qty").addEventListener("input", sellCheck);

    $("txn-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const sym = $("f-symbol").value.trim().toUpperCase();
      const action = $("f-action").value;
      const date = $("f-date").value;
      const qty = parseFloat($("f-qty").value);
      const price = parseFloat($("f-price").value);
      if (!sym || !date || !(qty > 0) || !(price >= 0)) return;
      const market = $("f-market").value;
      const name = $("f-name").value.trim() || sym;

      // Accumulate into the session working copy so multiple staged transactions
      // compound and Export/the popup/badges all reflect them.
      stageLot(sym, name, market, { date, action, quantity: qty, price });
      refreshDatalist();
      renderView();   // repaint rows so the affected holding shows a "pending" flag

      showResult(holdingsToCsv(stagedHoldings), { sym, action, qty, price, date });
    });

    function showResult(csv, m) {
      $("txn-form").hidden = true;
      $("txn-result").hidden = false;
      $("txn-ok-msg").textContent =
        `Staged (not applied yet): ${m.action} ${m.qty} ${m.sym} @ ${m.price} on ${m.date}.`;
      $("txn-json").textContent = csv;
      markPending(`${m.action} ${m.qty} ${m.sym}`);
      $("txn-cmd").textContent =
        "python scripts/fetch.py         # recompute (purchase-date FX, avg cost, realized P&L)\n" +
        "bash scripts/build_site.sh      # rebuild the site\n" +
        `git commit -am "txn: ${m.action} ${m.qty} ${m.sym}" && git push   # CI redeploys`;
      $("txn-download").onclick = () => downloadFile("holdings.csv", csv);
      $("txn-copy").onclick = () => {
        if (!navigator.clipboard) return;
        navigator.clipboard.writeText(csv).then(() => {
          $("txn-copy").textContent = "Copied!";
          setTimeout(() => ($("txn-copy").textContent = "Copy CSV"), 1500);
        });
      };
    }

    function downloadFile(fn, text) {
      const blob = new Blob([text], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = fn; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  }

  /* ---- Newspaper report ------------------------------------------- */
  // Figures use a system UI font stack (reliable rupee/₹ glyph) while prose stays
  // serif; monetary symbols are missing from some webfonts, which renders wrong.
  const NEWSPAPER_CSS = `
  :root{--ink:#20201c;--paper:#fbf8f0;--rule:#cabfa4;--muted:#6b6558;
    --up:#0a6b3f;--down:#b0301f;--serif:'PT Serif',Georgia,'Times New Roman',serif;
    --disp:'Playfair Display',Georgia,serif;
    --fig:'Helvetica Neue',-apple-system,'Segoe UI',system-ui,Roboto,Arial,sans-serif;}
  *{box-sizing:border-box;}
  body{margin:0;background:#dedad0;color:var(--ink);padding:26px 20px;
    font-family:var(--serif);-webkit-font-smoothing:antialiased;font-size:15px;}
  .paper{max-width:920px;margin:0 auto;background:var(--paper);padding:40px 46px 30px;
    box-shadow:0 8px 40px rgba(0,0,0,.2);}
  .num,.fig{font-family:var(--fig);font-variant-numeric:tabular-nums;font-feature-settings:"tnum";}
  /* Masthead */
  .masthead{text-align:center;margin-bottom:18px;}
  .mh-line{font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:var(--muted);
    border-bottom:1px solid var(--ink);padding-bottom:8px;margin-bottom:8px;}
  .paper-name{font-family:var(--disp);font-weight:900;font-size:60px;line-height:.98;
    margin:4px 0 6px;letter-spacing:-.01em;}
  .mh-meta{display:flex;justify-content:space-between;align-items:center;font-size:10.5px;
    letter-spacing:.14em;text-transform:uppercase;color:#3a362d;
    border-top:3px double var(--ink);border-bottom:3px double var(--ink);padding:6px 2px;}
  /* Lead */
  .headline{font-family:var(--disp);font-weight:900;font-size:40px;line-height:1.08;
    margin:20px 0 6px;text-align:center;letter-spacing:-.01em;}
  .deck{text-align:center;font-style:italic;color:#4a4438;font-size:14.5px;margin:0 auto 16px;
    max-width:640px;border-bottom:1px solid var(--rule);padding-bottom:14px;}
  .lead-grid{display:grid;grid-template-columns:1fr 340px;gap:30px;align-items:start;}
  .lead-text{font-size:15px;line-height:1.66;text-align:justify;margin:0;}
  .lead-text::first-letter{font-family:var(--disp);font-weight:900;font-size:58px;
    float:left;line-height:.72;padding:8px 9px 0 0;color:var(--ink);}
  .box{border:1.5px solid var(--ink);padding:0;}
  .box-h{font-family:var(--disp);font-weight:700;font-size:11px;text-transform:uppercase;
    letter-spacing:.14em;text-align:center;background:var(--ink);color:var(--paper);padding:6px 0;}
  .box-b{padding:6px 13px 9px;}
  .up{color:var(--up);} .down{color:var(--down);}
  /* By-the-numbers dual-currency table */
  .numtable{width:100%;border-collapse:collapse;}
  .numtable th{font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
    padding:3px 4px 6px;border-bottom:1.5px solid var(--ink);text-align:right;}
  .numtable th:first-child{text-align:left;}
  .numtable td{padding:6px 3px;border-bottom:1px dotted var(--rule);}
  .numtable td.ml{color:var(--muted);text-transform:uppercase;font-size:8.5px;letter-spacing:.05em;
    line-height:1.2;padding-right:8px;}
  .numtable td.num{text-align:right;font-size:11.5px;font-weight:600;white-space:nowrap;}
  .numtable tr:first-child td{padding-top:8px;} .numtable tr.hi td{font-size:13px;}
  .numtable tr:last-child td{border-bottom:0;}
  /* Dual mini charts */
  .charts-row{display:grid;gap:22px;margin-top:20px;border-top:1px solid var(--rule);padding-top:14px;}
  .np-fig{margin:0;}
  .np-lab{font-family:var(--fig);font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;
    color:var(--muted);margin-bottom:4px;}
  .np-chart{width:100%;height:118px;display:block;border-bottom:1px solid var(--rule);}
  .charts-cap{font-size:10.5px;font-style:italic;color:var(--muted);text-align:center;
    grid-column:1/-1;margin-top:2px;}
  /* Section headers */
  .section{margin-top:24px;border-top:3px double var(--ink);padding-top:16px;}
  .sec{font-family:var(--disp);font-weight:700;font-size:16px;text-transform:uppercase;
    letter-spacing:.04em;border-bottom:2px solid var(--ink);padding-bottom:5px;margin:0 0 14px;}
  /* Company briefs (stock + its news together) */
  .briefs{column-count:3;column-gap:24px;}
  .brief{break-inside:avoid;-webkit-column-break-inside:avoid;border-top:2px solid var(--ink);
    padding:9px 0 12px;margin-bottom:4px;}
  .brief.stale{opacity:.72;}
  .brief-h{display:flex;align-items:baseline;gap:6px;}
  .bk{font-family:var(--disp);font-weight:900;font-size:21px;letter-spacing:-.01em;}
  .brief-h .mk{font-family:var(--fig);font-size:8px;background:#eae3d0;padding:1px 4px;border-radius:2px;
    color:var(--muted);}
  .brief-day{margin-left:auto;font-size:12px;font-weight:700;}
  .brief-nm{color:var(--muted);font-size:10.5px;margin:1px 0 8px;font-style:italic;}
  .brief-stats>div{display:flex;justify-content:space-between;gap:8px;padding:3px 0;
    border-bottom:1px dotted var(--rule);font-size:11.5px;}
  .brief-stats span{color:var(--muted);text-transform:uppercase;font-size:8.5px;letter-spacing:.06em;align-self:center;}
  .brief-stats b{font-weight:600;} .brief-stats .sep{color:var(--rule);}
  .brief-news{list-style:none;margin:9px 0 0;padding:0;}
  .brief-news li{font-size:11px;line-height:1.36;padding:5px 0;border-bottom:1px solid #ece5d3;}
  .brief-news li:last-child{border-bottom:0;}
  .brief-news a{color:var(--ink);text-decoration:none;} .brief-news a:hover{text-decoration:underline;}
  .brief-news .src{display:block;font-size:8px;text-transform:uppercase;letter-spacing:.04em;color:#8a8272;margin-top:2px;}
  .brief-news .muted{color:#a49b88;font-style:italic;}
  .alloc-note{font-size:11.5px;color:var(--muted);margin-top:14px;font-style:italic;text-align:center;}
  /* Market wire (general news, multi-column) */
  .wire{column-count:3;column-gap:26px;}
  .wire li{break-inside:avoid;list-style:none;padding:8px 0;border-bottom:1px solid #e6dfcc;
    font-size:12px;line-height:1.4;}
  .wire a{color:var(--ink);text-decoration:none;} .wire a:hover{text-decoration:underline;}
  .wire .src{display:block;font-size:8.5px;text-transform:uppercase;color:#8a8272;margin-top:2px;}
  .wire .muted{color:#a49b88;}
  .colophon{margin-top:26px;border-top:1px solid var(--ink);padding-top:9px;font-size:10px;
    color:var(--muted);text-align:center;letter-spacing:.02em;}
  .print-btn{position:fixed;top:18px;right:18px;z-index:10;background:var(--ink);color:var(--paper);border:0;
    padding:11px 20px;font-family:var(--fig);font-size:13px;font-weight:600;letter-spacing:.03em;
    border-radius:7px;cursor:pointer;box-shadow:0 6px 18px rgba(0,0,0,.3);}
  .print-btn:hover{background:#000;}
  @media print{ body{background:#fff;padding:0;} .paper{box-shadow:none;max-width:100%;padding:0;}
    .no-print{display:none!important;} a{color:#000;text-decoration:none;} @page{margin:13mm;}
    .section{break-before:auto;} .brief,.wire li{break-inside:avoid;} }
  @media (max-width:760px){ .paper{padding:26px 22px;} .lead-grid{grid-template-columns:1fr;}
    .charts-row{grid-template-columns:1fr!important;} .briefs{column-count:1;} .wire{column-count:1;}
    .paper-name{font-size:42px;} .headline{font-size:30px;} }
  @media (min-width:761px) and (max-width:1040px){ .briefs{column-count:2;} .wire{column-count:2;} }`;

  function reportChartSvg(hist, ccy, baseCcy) {
    const raw = (hist && hist.series) || [];
    const s = raw.map((d) => ({
      value: d.value && typeof d.value === "object" ? (d.value[ccy] ?? d.value[baseCcy]) : d.value_base,
      cost: d.cost && typeof d.cost === "object" ? (d.cost[ccy] ?? d.cost[baseCcy]) : d.cost_base,
    })).filter((d) => d.value != null && d.cost != null);
    if (s.length < 2) return "";
    const W = 820, H = 200, pl = 6, pr = 6, pt = 10, pb = 14;
    const vals = s.map((d) => d.value), cost = s[s.length - 1].cost;
    const lo = Math.min(...vals, cost), hi = Math.max(...vals, cost), span = (hi - lo) || 1;
    const yMin = lo - span * 0.12, yMax = hi + span * 0.12;
    const x = (i) => pl + (i / (s.length - 1)) * (W - pl - pr);
    const y = (v) => pt + (1 - (v - yMin) / (yMax - yMin)) * (H - pt - pb);
    const costY = y(cost).toFixed(1);
    let d = `M ${x(0).toFixed(1)} ${y(vals[0]).toFixed(1)}`;
    for (let i = 1; i < s.length; i++) d += ` L ${x(i).toFixed(1)} ${y(vals[i]).toFixed(1)}`;
    const up = vals[vals.length - 1] >= cost, col = up ? "#0a6b3f" : "#b03325";
    const area = `${d} L ${x(s.length - 1).toFixed(1)} ${costY} L ${x(0).toFixed(1)} ${costY} Z`;
    return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="np-chart">
      <path d="${area}" fill="${col}" opacity="0.1"/>
      <line x1="${pl}" y1="${costY}" x2="${W - pr}" y2="${costY}" stroke="#555" stroke-dasharray="4 4" stroke-width="1" opacity="0.6"/>
      <path d="${d}" fill="none" stroke="${col}" stroke-width="1.8"/></svg>`;
  }

  function buildNewspaperHtml() {
    const p = DATA.p, news = DATA.news || { market: [], by_symbol: {} }, base = p.base_currency;
    const displays = p.display_currencies || [base];
    const T = p.totals[base], gain = T.pnl >= 0;
    const usdT = p.totals.USD;   // secondary currency, if any US holdings
    const ed = new Date(p.generated_at);
    const edStr = isNaN(ed) ? "" : ed.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    const holdings = p.holdings.slice();
    const byNat = holdings.slice().sort((a, b) => b.figures.NATIVE.pnl_pct - a.figures.NATIVE.pnl_pct);
    const topG = byNat[0], topL = byNat[byNat.length - 1];
    let inV = 0, usV = 0;
    holdings.forEach((r) => { r.market === "IN" ? (inV += r.figures[base].value) : (usV += r.figures[base].value); });
    const inPct = Math.round((inV / (inV + usV || 1)) * 100);
    const M = (v, c) => `<span class="num">${money(v, c || base)}</span>`;   // clean ₹ glyph

    // "By the Numbers" - every metric across each display currency (INR + USD).
    const metrics = [["Total Value", "value", null, true], ["Total P&L", "pnl", "pnl_pct"],
      ["Today", "day", "day_pct"], ["Invested", "cost", null]];
    if (Math.abs((p.totals[base].realized) || 0) >= 0.005) metrics.push(["Realized", "realized", null]);
    const numHead = `<tr><th></th>${displays.map((c) => `<th class="num">${c}</th>`).join("")}</tr>`;
    const numBody = metrics.map(([label, key, pk, hi]) => {
      const cells = displays.map((c) => {
        const t = p.totals[c], v = t[key];
        const cls = (key === "pnl" || key === "day" || key === "realized") ? (v >= 0 ? "up" : "down") : "";
        return `<td class="num ${cls}">${money(v, c)}${pk ? ` (${pct(t[pk])})` : ""}</td>`;
      }).join("");
      return `<tr class="${hi ? "hi" : ""}"><td class="ml">${label}</td>${cells}</tr>`;
    }).join("");

    // Dual mini charts (one per display currency).
    const chartsHtml = displays.map((c) =>
      `<figure class="np-fig"><div class="np-lab">${c} value vs. cost</div>${reportChartSvg(DATA.hist, c, base)}</figure>`).join("");

    // Company briefs: each holding's figures + its own headlines, together.
    const briefs = holdings.map((r) => {
      const nat = r.figures.NATIVE, ncy = r.currency;
      const dayCls = nat.day_pct >= 0 ? "up" : "down", pnlCls = nat.pnl >= 0 ? "up" : "down";
      const valDual = displays.map((c) => M(r.figures[c].value, c)).join('<span class="sep"> / </span>');
      const items = (news.by_symbol[r.symbol] || []).slice(0, 2).map((it) =>
        `<li><a href="${encodeURI(it.url || "#")}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a><span class="src">${escapeHtml(it.source || "")}</span></li>`).join("")
        || '<li class="muted">No recent company news.</li>';
      return `<article class="brief${r.stale ? " stale" : ""}">
        <div class="brief-h"><span class="bk">${escapeHtml(r.symbol)}</span><span class="mk">${r.market}</span>
          <span class="brief-day num ${dayCls}">${pct(nat.day_pct)}</span></div>
        <div class="brief-nm">${escapeHtml(r.name)}${r.stale ? " (price stale)" : ""}</div>
        <div class="brief-stats">
          <div><span>Last</span><b class="num">${moneyPrecise(r.last, ncy)}</b></div>
          <div><span>Value</span><b>${valDual}</b></div>
          <div><span>P&L</span><b class="num ${pnlCls}">${money(nat.pnl, ncy)} (${pct(nat.pnl_pct)})</b></div>
        </div>
        <ul class="brief-news">${items}</ul></article>`;
    }).join("");

    const wire = (news.market || []).slice(0, 12).map((it) =>
      `<li><a href="${encodeURI(it.url || "#")}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a><span class="src">${escapeHtml(it.source || "")}</span></li>`).join("")
      || '<li class="muted">No market headlines in this build.</li>';

    const headline = `Portfolio ${gain ? "Rallies" : "Retreats"} ${Math.abs(T.pnl_pct).toFixed(1)}%`;
    const lead =
      `The book closed the latest end-of-day session valued at <b>${M(T.value)}</b>` +
      `${usdT ? ` (about <b>${M(usdT.value, "USD")}</b>)` : ""}, a ` +
      `${gain ? "gain" : "loss"} of <b>${M(Math.abs(T.pnl))}</b> (${pct(T.pnl_pct)}) on invested ` +
      `capital of ${M(T.cost)}. On the day it ${T.day >= 0 ? "added" : "shed"} ` +
      `${M(Math.abs(T.day))} (${pct(T.day_pct)}). ` +
      `${topG ? `<b>${escapeHtml(topG.symbol)}</b> led the gainers at ${pct(topG.figures.NATIVE.pnl_pct)}` : ""}` +
      `${topL && topL !== topG ? `, while <b>${escapeHtml(topL.symbol)}</b> trailed at ${pct(topL.figures.NATIVE.pnl_pct)}` : ""}. ` +
      `Holdings are split ${inPct}% India and ${100 - inPct}% United States by value. ` +
      `Figures are shown in each holding's own currency and totalled in both ${displays.join(" and ")}.`;

    return `<!doctype html><html lang="en"><head><meta charset="utf-8">
      <title>The Portfolio Ledger</title><meta name="viewport" content="width=device-width, initial-scale=1">
      <link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
      <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=PT+Serif:ital,wght@0,400;0,700;1,400&display=swap" rel="stylesheet">
      <style>${NEWSPAPER_CSS}</style></head><body>
      <div class="paper">
        <header class="masthead">
          <div class="mh-line">Personal Edition &middot; Free &amp; Open &middot; Not Investment Advice</div>
          <h1 class="paper-name">The Portfolio Ledger</h1>
          <div class="mh-meta"><span>${edStr}</span><span>End-of-Day Report</span><span>${displays.join(" &amp; ")} Editions</span></div>
        </header>
        <section class="lead">
          <h2 class="headline">${headline}</h2>
          <div class="deck">Day ${pct(T.day_pct)} &middot; ${holdings.length} holdings &middot; ${gain ? "in profit" : "underwater"}</div>
          <div class="lead-grid">
            <p class="lead-text">${lead}</p>
            <div class="box">
              <div class="box-h">By the Numbers</div>
              <div class="box-b"><table class="numtable"><thead>${numHead}</thead><tbody>${numBody}</tbody></table></div>
            </div>
          </div>
          <div class="charts-row" style="grid-template-columns:repeat(${displays.length},1fr)">
            ${chartsHtml}
            <div class="charts-cap">Portfolio value against the dashed cost-basis line, trailing history.</div>
          </div>
        </section>
        <section class="section">
          <h3 class="sec">Company Briefs</h3>
          <div class="briefs">${briefs}</div>
          <div class="alloc-note">Allocation by market: India ${inPct}% and United States ${100 - inPct}% by value.</div>
        </section>
        <section class="section">
          <h3 class="sec">Market Wire</h3>
          <ul class="wire">${wire}</ul>
        </section>
        <footer class="colophon">Compiled ${new Date().toLocaleString()} from end-of-day data.
          Prices are delayed and for personal tracking only, not investment advice.</footer>
      </div></body></html>`;
  }

  function setupNewspaper() {
    const overlay = $("report-overlay"), frame = $("report-frame");
    const close = () => { overlay.hidden = true; frame.srcdoc = ""; };
    $("newsbtn").addEventListener("click", () => {
      frame.srcdoc = buildNewspaperHtml();   // isolated document, no popup
      overlay.hidden = false;
    });
    $("report-close").addEventListener("click", close);
    $("report-print").addEventListener("click", () => {
      try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch (e) { window.print(); }
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !overlay.hidden) close(); });
  }

  load();
})();
