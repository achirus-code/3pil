/*
 * Säulenwächter – Lovelace-Karte und Seitenleisten-Panel.
 *
 *   type: custom:saeulenwaechter-card            → Übersicht aller drei Säulen
 *   type: custom:saeulenwaechter-card
 *   pillar: welt                                  → Detailansicht einer Säule (Signale, Monatsstreifen, Säulen)
 */

const STATE_COLORS = {
  on: "var(--sw-green)", off: "var(--sw-red)", ok: "var(--sw-green)",
  warn: "var(--sw-orange)", neutral: "var(--secondary-text-color)", unknown: "var(--secondary-text-color)",
};
const STATE_ICONS = {
  on: "mdi:check-circle", off: "mdi:close-circle", ok: "mdi:check-circle-outline",
  warn: "mdi:alert", neutral: "mdi:circle-outline", unknown: "mdi:help-circle-outline",
};
const MONTH_COLORS = { in: "var(--sw-green)", hedged: "var(--sw-blue)", parked: "var(--sw-teal)", cash: "var(--sw-grey)" };
const MONTH_LABELS = { in: "Investiert", hedged: "Gesichert", parked: "Ausgewichen", cash: "Cash" };
const MONTHS = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."];
const ACTION_COLORS = { buy: "var(--sw-green)", sell: "var(--sw-red)", switch: "var(--sw-orange)" };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const eur = (v, d = 2) => (v == null ? "–" : v.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d }) + " €");
const pct = (v, d = 1, sign = true) => {
  if (v == null) return "–";
  const r = Math.round(v * 100 * 10 ** d) / 10 ** d || 0; // kein „−0,0 %“
  return (sign && r > 0 ? "+" : r < 0 ? "−" : "") + Math.abs(r).toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d }) + " %";
};
const monthLabel = (k) => { if (!k) return "–"; const [y, m] = k.split("-"); return `${MONTHS[+m - 1]} ${y}`; };

const STYLE = `
  :host { --sw-green:#34c759; --sw-red:#ff3b30; --sw-orange:#ff9500; --sw-blue:#0a84ff; --sw-teal:#30b0c7;
          --sw-grey:rgba(142,142,147,.4); display:block; }
  .num { font-variant-numeric: tabular-nums; }
  ha-card { overflow:hidden; }
  .section { padding: 12px 16px; }
  .section + .section { border-top: 1px solid var(--divider-color); }
  .label { font-size: 11px; font-weight: 600; letter-spacing: .06em; color: var(--secondary-text-color);
           text-transform: uppercase; margin: 0 0 8px; }
  .hero { display:flex; gap:12px; align-items:flex-start; padding:16px; color:#fff;
          background: linear-gradient(135deg, var(--sw-green), var(--sw-blue)); }
  .hero .icon { width:40px; height:40px; border-radius:10px; background:rgba(255,255,255,.2);
                display:flex; align-items:center; justify-content:center; flex:none; }
  .hero h2 { margin:0; font-size:17px; font-weight:600; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .hero .sub { font-size:12px; opacity:.85; margin-top:2px; }
  .hero .price { font-size:22px; font-weight:600; margin-top:8px; }
  .hero .status { font-size:12.5px; margin-top:6px; display:flex; gap:6px; align-items:flex-start; }
  .hero .prices { margin:6px 0 2px; font-size:14px; line-height:1.5; }
  .hero .prices b { font-size:17px; }
  .hero .prices > div { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 8px; }
  .hero .prices > div > span:first-child { flex:1; min-width:0; }
  .badge { font-size:10px; font-weight:700; padding:2px 6px; border-radius:6px; background:rgba(255,255,255,.25); letter-spacing:.04em; }
  .dot { width:8px; height:8px; border-radius:50%; flex:none; margin-top:5px; }
  .row { display:flex; gap:8px; align-items:flex-start; padding:5px 0; }
  .row ha-icon { --mdc-icon-size:14px; width:14px; flex:none; margin-top:1px; }
  .row .t { font-size:11px; font-weight:500; }
  .row .v { font-size:10.5px; color:var(--secondary-text-color); }
  .row .h { font-size:10.5px; font-weight:500; }
  .row .grow { flex:1; min-width:0; }
  .row .right { font-size:11px; color:var(--secondary-text-color); white-space:nowrap; }
  .strip { display:flex; flex-wrap:wrap; gap:3px; margin-top:8px; }
  .strip span { width:12px; height:12px; border-radius:3px; }
  .legend { font-size:10.5px; color:var(--secondary-text-color); margin-top:4px; display:flex; gap:10px; flex-wrap:wrap; }
  .legend i { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:4px; }
  .pillar { margin: 6px 0 10px; }
  .pillar .head { display:flex; justify-content:space-between; font-size:13px; }
  .pillar .head b { font-weight:700; }
  .bar { position:relative; height:8px; overflow:hidden; border-radius:3px; background:var(--divider-color); margin:5px 0 3px; }
  .bar .fill { position:absolute; left:0; top:0; bottom:0; border-radius:3px; }
  .bar .mark { position:absolute; top:-2px; bottom:-2px; width:1.5px; background:var(--primary-text-color); }
  table.stats { width:100%; border-collapse:collapse; font-size:12px; margin:2px 0 10px; }
  table.stats th { text-align:right; font-weight:500; color:var(--secondary-text-color); padding:2px 4px; }
  table.stats th:first-child, table.stats td:first-child { text-align:left; padding-left:0; }
  table.stats td { text-align:right; padding:3px 4px; border-top:1px solid var(--divider-color); white-space:nowrap; }
  .alarm { margin:12px; padding:14px 16px; border-radius:12px; color:#fff;
           background:linear-gradient(135deg, #d70015, #ff3b30); border:3px solid #ff3b30;
           box-shadow:0 0 0 0 rgba(255,59,48,.7); animation:sw-pulse 1.6s infinite; }
  .alarm-head { display:flex; align-items:center; gap:8px; font-size:16px; font-weight:800; letter-spacing:.2px;
                text-transform:uppercase; }
  .alarm-head ha-icon { --mdc-icon-size:28px; }
  .alarm-row { margin-top:10px; padding:10px 12px; border-radius:8px; background:rgba(0,0,0,.22); }
  .alarm-tag { display:inline-block; font-size:11px; font-weight:800; text-transform:uppercase; background:#fff;
               color:#d70015; padding:2px 8px; border-radius:10px; }
  .alarm-text { margin-top:6px; font-size:15px; font-weight:700; line-height:1.35; }
  .interest { margin-top:10px; padding:8px 10px; border-radius:8px; background:var(--secondary-background-color, rgba(127,127,127,.12)); font-size:13px; }
  .interest .muted { opacity:.7; }
  .muted { color:var(--secondary-text-color); font-weight:normal; }
  details.trades { font-size:12px; }
  details.trades summary { cursor:pointer; color:var(--primary-color); }
  details.trades table { width:100%; border-collapse:collapse; margin-top:4px; }
  details.trades td { padding:3px 4px; border-top:1px solid var(--divider-color); white-space:nowrap; }
  details.trades td.num { text-align:right; }
  .since-edit { font-size:11px; color:var(--primary-color); }
  .alarm-table { width:100%; margin-top:8px; border-collapse:collapse; font-size:14px; }
  .alarm-table th { text-align:left; font-size:11px; text-transform:uppercase; opacity:.85; padding:4px 6px; }
  .alarm-row { overflow-x:auto; }
  .alarm-table td { padding:6px 4px; border-top:1px solid rgba(255,255,255,.25); white-space:nowrap; }
  .alarm-table .mv { white-space:normal; }
  .alarm-table .num { text-align:right; }
  .alarm-table .mv { font-weight:800; }
  .alarm-foot { margin-top:10px; font-size:12px; opacity:.9; }
  @keyframes sw-pulse { 0% { box-shadow:0 0 0 0 rgba(255,59,48,.7); } 70% { box-shadow:0 0 0 14px rgba(255,59,48,0); }
                        100% { box-shadow:0 0 0 0 rgba(255,59,48,0); } }
  @media (prefers-reduced-motion: reduce) { .alarm { animation:none; } }
  svg.hist { width:100%; height:110px; display:block; margin-top:4px; }
  .periods { display:flex; gap:6px; margin:6px 0; overflow-x:auto; padding-bottom:2px; }
  .period { flex:0 0 auto; min-width:84px; }
  .period[disabled] { opacity:.35; cursor:default; }
  .chart-wrap { position:relative; margin-top:6px; touch-action:pan-y; }
  svg.perf-chart { width:100%; height:180px; display:block; cursor:crosshair; }
  .perf-chart .grid { stroke:var(--divider-color); stroke-width:1; vector-effect:non-scaling-stroke; stroke-dasharray:3 3; }
  .perf-chart .cross { stroke:var(--secondary-text-color); stroke-width:1; vector-effect:non-scaling-stroke; }
  .chart-wrap .dot { position:absolute; width:9px; height:9px; border-radius:50%; background:var(--card-background-color, #1c1c1e);
                     border:2px solid; transform:translate(-50%,-50%); pointer-events:none; }
  .chart-wrap .ylabels span { position:absolute; right:4px; transform:translateY(-110%); font-size:10px; color:var(--secondary-text-color); pointer-events:none; }
  .chart-wrap .xlabels { position:relative; height:14px; }
  .chart-wrap .xlabels span { position:absolute; transform:translateX(-50%); font-size:10px; color:var(--secondary-text-color); white-space:nowrap; top:-16px; }
  .chart-wrap .xlabels span:first-child { transform:none; }
  .chart-wrap .xlabels span:last-child { transform:translateX(-100%); }
  .chart-wrap .tip { position:absolute; top:4px; min-width:210px; padding:8px 10px; border-radius:8px; font-size:12px;
                     background:var(--card-background-color, #1c1c1e); border:1px solid var(--divider-color); box-shadow:0 4px 16px rgba(0,0,0,.35); pointer-events:none; z-index:2; }
  .chart-wrap .tip .row { display:flex; justify-content:space-between; gap:12px; margin-top:3px; }
  .chart-wrap .mark { position:absolute; bottom:18px; transform:translateX(-50%); font-size:9px; pointer-events:none; line-height:1; }
  .chart-wrap .mark.buy { color:var(--sw-green); }
  .chart-wrap .mark.sell { color:var(--sw-red); }
  .chart-wrap .tip .ev { color:var(--secondary-text-color); border-top:1px solid var(--divider-color); padding-top:3px; }
  .chart-wrap .tip i { display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:5px; }
  .period { display:flex; flex-direction:column; align-items:flex-start; gap:1px; padding:6px 10px; border-radius:8px; cursor:pointer;
            border:1px solid var(--divider-color); background:transparent; color:var(--primary-text-color); font:inherit; text-align:left; }
  .period.on { border-color:var(--primary-color); background:rgba(127,127,127,.1); }
  .period .k { font-size:11px; color:var(--secondary-text-color); }
  .period .num { font-size:15px; font-weight:600; }
  .period .small { font-size:11px; font-weight:500; }
  .hist-legend { display:flex; justify-content:space-between; font-size:11px; color:var(--secondary-text-color); margin-top:2px; }
  .stat-top { display:flex; gap:18px; flex-wrap:wrap; align-items:flex-end; margin:2px 0 8px; }
  .stat-top .k { font-size:11px; color:var(--secondary-text-color); }
  .stat-top .big { font-size:24px; font-weight:700; }
  .stat-top .mid { font-size:15px; font-weight:600; }
  .parts { font-size:11px; color:var(--secondary-text-color); display:flex; flex-wrap:wrap; gap:2px 10px; }
  .parts i { display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:4px; vertical-align:0; }
  .bar .fill.cash { background:repeating-linear-gradient(45deg, var(--secondary-text-color) 0 3px, transparent 3px 6px) !important; opacity:.45; }
  .log.info { border-left-color:var(--sw-orange); }
  .pillar .val { font-size:12px; color:var(--secondary-text-color); }
  .note { font-size:12px; color:var(--secondary-text-color); margin-top:4px; }
  .note.warn { color: var(--sw-orange); font-weight:500; }
  .overview { display:grid; gap:10px; }
  .ov { display:flex; gap:10px; align-items:center; padding:8px 0; cursor:pointer; }
  .ov .chip { width:6px; align-self:stretch; border-radius:3px; }
  .ov .n { font-weight:600; font-size:14px; }
  .ov .s { font-size:12px; color:var(--secondary-text-color); }
  .ov .a { font-size:11px; font-weight:700; padding:2px 8px; border-radius:10px; color:#fff; white-space:nowrap; }
  .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:8px 16px; }
  .kv .k { font-size:10.5px; color:var(--secondary-text-color); }
  .kv .v { font-size:13px; font-weight:500; }
  .buttons { display:flex; gap:8px; flex-wrap:wrap; }
  button.sw { font: inherit; font-size:12px; padding:6px 12px; border-radius:8px; cursor:pointer;
              border:1px solid var(--divider-color); background:var(--secondary-background-color, transparent);
              color:var(--primary-text-color); }
  button.sw:hover { border-color: var(--primary-color); }
  .err { color: var(--sw-red); font-size:12px; }
  .log-box { max-height:220px; overflow-y:auto; border:1px solid var(--divider-color); border-radius:8px; padding:6px 8px; }
  .log { font-size:11.5px; white-space:pre-wrap; color:var(--secondary-text-color); border-left:3px solid var(--divider-color);
         padding-left:8px; margin:6px 0; }
`;

// Haltedauer: „seit 3 Tagen / 2 Wochen / 5 Monaten / 1 Jahr 2 M.“ – ohne „seit“: „3 Tage / 2 Wochen …“
function heldFor(iso, withSeit = true) {
  if (!iso) return "–";
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  const n = (v, one, many, manyDat) => `${v} ${v === 1 ? one : withSeit ? manyDat : many}`;
  let txt;
  if (days < 1) return withSeit ? "seit heute" : "heute";
  if (days < 7) txt = n(days, "Tag", "Tage", "Tagen");
  else if (days < 31) txt = n(Math.floor(days / 7), "Woche", "Wochen", "Wochen");
  else {
    const months = Math.floor(days / 30.44);
    if (months < 12) txt = n(months, "Monat", "Monate", "Monaten");
    else txt = n(Math.floor(months / 12), "Jahr", "Jahre", "Jahren") + (months % 12 ? ` ${months % 12} M.` : "");
  }
  return withSeit ? `seit ${txt}` : txt;
}

class SaeulenBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._stamp = null;
  }

  set hass(hass) {
    this._hass = hass;
    const st = hass.states["sensor.saeulenwaechter_depotwert"];
    const stamp = st ? st.last_updated + JSON.stringify(st.attributes?.saeulen ?? "") : null;
    if (stamp !== this._stamp || !this._data) {
      this._stamp = stamp;
      this._load();
    }
  }

  connectedCallback() {
    this._timer = setInterval(() => this._load(), 60000);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      this._data = await this._hass.callWS({ type: "saeulenwaechter/data" });
      this._error = null;
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._loading = false;
    this._render();
  }

  async _action(action, extra = {}) {
    try {
      await this._hass.callWS({ type: "saeulenwaechter/action", action, ...extra });
      setTimeout(() => this._load(), 1500);
    } catch (e) {
      alert(e.message || e);
    }
  }

  /* ---------- Bausteine ---------- */

  hero(p, d) {
    const live = p.state && p.live_state && p.live_state !== p.state;
    // Gekaufte Produkte statt des Referenz-Instruments; bei mehreren (z. B. zwei IMI-ETFs) alle
    const held = d.mode === "depot" ? (p.held || []).filter((h) => !h.physical) : [];
    const title = held.length ? held.map((h) => esc(h.name)).join(" + ") : esc(p.instrument);
    const sub = held.length
      ? `${esc(p.name)} · ${held.length === 1 ? esc(held[0].isin) : `${held.length} Produkte`} · Signal aus ${esc(p.instrument)}`
      : `${esc(p.name)} · Monatlicher Trendfolger · ${esc(p.isin)}`;
    const change = (c) => c != null ? `<span style="font-size:13px;font-weight:400;opacity:.85">${pct(c)} heute</span>` : "";
    const price = held.length === 1
      ? `<div class="price num">${eur(held[0].bid)} ${change(held[0].change_24h)}</div>`
      : held.length > 1
        ? `<div class="prices num">${held.map((h) => `<div><span>${esc(h.name)}</span> <b>${eur(h.bid)}</b> ${change(h.change_24h)}</div>`).join("")}</div>`
        : `<div class="price num">${eur(p.price)} ${change(p.change_24h)}</div>`;
    return `
      <div class="hero" style="background:linear-gradient(135deg, ${esc(p.color)}, var(--sw-blue))">
        <div class="icon"><ha-icon icon="mdi:calendar-clock"></ha-icon></div>
        <div style="flex:1;min-width:0">
          <h2>${title} ${d.mode === "paper" ? '<span class="badge">PAPER</span>' : '<span class="badge">DEPOT</span>'}</h2>
          <div class="sub">${sub}</div>
          ${price}
          <div class="status"><span class="dot" style="background:#fff"></span><span>${esc(p.status)}</span></div>
          ${live ? `<div class="status" style="opacity:.85">Aktuelle Daten würden „${esc(MONTH_LABELS[p.live_state])}“ ergeben – entschieden wird am Monatsersten.</div>` : ""}
        </div>
      </div>`;
  }

  position(p, d) {
    if (!p.held || !p.held.length) return "";
    const trades = (d && d.trades) || [];
    const tradeList = (isin) => {
      const ts = trades.filter((t) => t.isin === isin).slice().reverse();
      if (!ts.length) return "";
      return `<details class="trades"><summary>${ts.length} Käufe/Verkäufe laut Trade Republic</summary><table>
        ${ts.map((t) => `<tr><td>${new Date(t.date).toLocaleDateString("de-DE")}</td><td>${t.shares >= 0 ? "Kauf" : "Verkauf"}${t.subtitle ? ` <span class="muted">${esc(t.subtitle)}</span>` : ""}</td>
          <td class="num">${(t.shares >= 0 ? "+" : "−") + Math.abs(t.shares).toLocaleString("de-DE", { maximumFractionDigits: 4 })}</td>
          <td class="num">${t.amount != null ? eur(Math.abs(t.amount), 2) : "–"}</td></tr>`).join("")}</table></details>`;
    };
    return `<div class="section"><div class="label">Offene Position</div>${p.held.map((h) => {
      const res = h.value != null && h.cost ? h.value / h.cost - 1 : null;
      return `<div class="grid num">
        <div class="kv"><div class="k">Instrument</div><div class="v">${esc(h.name)}${h.counts_as_name ? `<div class="s" style="font-size:11px;color:var(--secondary-text-color)">zählt als ${esc(h.counts_as_name)}</div>` : ""}</div></div>
        <div class="kv"><div class="k">Menge</div><div class="v">${(h.size ?? 0).toLocaleString("de-DE", { maximumFractionDigits: 4 })}</div></div>
        <div class="kv"><div class="k">Einstieg</div><div class="v">${eur(h.avg_buy)}</div></div>
        <div class="kv"><div class="k">Investiert</div><div class="v">${eur(h.cost, 0)}</div></div>
        <div class="kv"><div class="k">Wert (Geldkurs)</div><div class="v">${eur(h.value, 0)}</div></div>
        <div class="kv"><div class="k">Ergebnis</div><div class="v" style="color:${res == null || Math.abs(res) < 0.0005 ? "inherit" : res > 0 ? "var(--sw-green)" : "var(--sw-red)"}">${pct(res)}</div></div>
        <div class="kv"><div class="k">Gehalten</div><div class="v">${heldFor(h.since)}${h.since ? `<div class="s" style="font-size:11px;color:var(--secondary-text-color)">${h.since_manual || h.physical || !h.isin || h.isin === "PHYSISCH" ? "gekauft" : "erster Abgleich"} ${new Date(h.since).toLocaleDateString("de-DE")}</div>` : ""}${!h.physical && h.isin && h.isin !== "PHYSISCH" && h.since !== undefined && h.counts_as !== undefined ? `<a href="#" class="since-edit" data-since="${esc(h.isin)}" data-date="${esc(h.since || "")}">ändern</a>` : ""}</div></div>
        ${tradeList(h.isin) ? `<div class="kv" style="grid-column:1/-1">${tradeList(h.isin)}</div>` : ""}
        ${h.share && h.share < 1 ? `<div class="kv"><div class="k">Anteil am Bestand</div><div class="v">${pct(h.share, 0, false)}</div></div>` : ""}
      </div>`;
    }).join("")}</div>`;
  }

  signals(p) {
    if (!p.ready) {
      return `<div class="section"><div class="label">Signale</div><div class="note">${esc(p.status)}</div></div>`;
    }
    const rows = (p.signals || []).map((r) => `
      <div class="row">
        <ha-icon icon="${STATE_ICONS[r.state] || STATE_ICONS.unknown}" style="color:${STATE_COLORS[r.state] || STATE_COLORS.unknown}"></ha-icon>
        <div class="grow">
          <div class="t">${esc(r.title)}</div>
          ${r.key !== "decision" ? `<div class="v num">${esc(r.value)}</div>` : ""}
          ${r.hint ? `<div class="h num" style="color:${STATE_COLORS[r.state] || "inherit"}">${esc(r.hint)}</div>` : ""}
        </div>
        ${r.key === "decision" ? `<div class="right">${esc(r.value)}</div>` : ""}
      </div>`).join("");
    return `<div class="section"><div class="label">Signale</div>${rows}${this.strip(p)}</div>`;
  }

  strip(p) {
    const h = p.history || [];
    if (!h.length) return "";
    const seen = [...new Set(h.map((x) => x.state))];
    return `
      <div class="strip">${h.map((x) => `<span title="${esc(monthLabel(x.month))}: ${esc(MONTH_LABELS[x.state])}${x.name ? " (" + esc(x.name) + ")" : ""}" style="background:${MONTH_COLORS[x.state]}"></span>`).join("")}</div>
      <div class="legend"><span>${esc(monthLabel(h[0].month))} – ${esc(monthLabel(h[h.length - 1].month))}</span>
        ${seen.map((s) => `<span><i style="background:${MONTH_COLORS[s]}"></i>${MONTH_LABELS[s]}</span>`).join("")}</div>`;
  }

  alert(d, only) {
    const todo = (d.todo || []).filter((t) => !only || t.key === only || t.key === "rebalance");
    if (!todo.length) return "";
    return `<div class="alarm" role="alert">
      <div class="alarm-head"><ha-icon icon="mdi:alert-octagon"></ha-icon>
        <span>${todo.length === 1 ? "Handlung nötig" : `${todo.length} Handlungen nötig`} – Depot weicht von der Strategie ab</span></div>
      ${todo.map((t) => `<div class="alarm-row"><span class="alarm-tag">${esc(t.name)} · ${esc(t.action_label)}</span>
        ${t.rows ? this.rebalanceTable(t.rows) : `<div class="alarm-text">${esc(t.text)}</div>`}</div>`).join("")}
      <div class="alarm-foot">Bitte bei Trade Republic umsetzen – die Meldung verschwindet, sobald das Depot zum Ziel passt.</div>
    </div>`;
  }

  reconcileLine(r) {
    if (!r) return "";
    const parts = [`in den Säulen ${eur(r.counted, 0)}`, `Cash ${eur(r.cash || 0, 0)}`];
    if (r.unassigned) parts.push(`<b>nicht zugeordnet ${eur(r.unassigned, 0)}</b> (zählt nicht mit)`);
    const tr = r.tr_positions != null
      ? `Trade Republic: Wertpapiere ${eur(r.tr_positions, 0)} + Cash ${eur(r.cash || 0, 0)} = <b>${eur(r.tr_positions + (r.cash || 0), 0)}</b> · ` : "";
    const miss = r.missing_price && r.missing_price.length ? ` · ohne Kurs: ${r.missing_price.map(esc).join(", ")}` : "";
    return `<div class="note">${tr}App: ${parts.join(" · ")}${miss}</div>`;
  }

  interestLine(z) {
    if (!z) return "";
    if (z.rate == null) return `<div class="note">Zinsen auf Cash: Satz noch unbekannt – kommt beim nächsten Abgleich mit Trade Republic.</div>`;
    const rate = `${(z.rate * 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} % p. a.`;
    const src = { option: "eigener Wert", trade_republic: "laut Trade Republic" }[z.source] || "";
    const earned = z.earned ? ` · bisher gutgeschrieben ${eur(z.earned, 2)}` : "";
    return `<div class="interest"><span>💶 Zinsen auf Cash</span>
      <b>${rate}</b>${src ? ` <span class="muted">(${src})</span>` : ""} auf ${eur(z.cash, 0)} ≈ <b>${eur(z.per_year, 0)} im Jahr</b>${earned}</div>`;
  }

  rebalanceTable(rows) {
    const pc = (v) => `${(v * 100).toLocaleString("de-DE", { maximumFractionDigits: 1 })} %`;
    // Eine Säule in Cash hält ihr Geld als Guthaben: da wird nichts ge- oder verkauft, nur Cash umgeschichtet
    const move = (r) => Math.abs(r.delta) < 1 ? "passt"
      : r.cash ? `${r.delta > 0 ? "als Cash halten +" : "aus Cash nehmen "}${eur(Math.abs(r.delta), 0)}`
      : `${r.delta > 0 ? "kaufen " : "verkaufen "}${eur(Math.abs(r.delta), 0)}`;
    return `<table class="alarm-table">
      <tr><th>Säule</th><th class="num">Ist</th><th class="num">Ziel</th><th class="num">Anteil</th><th>Umsetzen</th></tr>
      ${rows.map((r) => `<tr><td>${esc(r.name)}${r.cash ? `<br><small>in Cash</small>` : ""}</td><td class="num">${eur(r.value, 0)}</td>
        <td class="num">${eur(r.target_value, 0)}</td><td class="num">${pc(r.ist)} → ${pc(r.soll)}</td>
        <td class="mv">${move(r)}</td></tr>`).join("")}
    </table>`;
  }

  stats(d) {
    const st = d.stats;
    if (!st) return "";
    const color = (v) => v == null || Math.abs(v) < 0.5 ? "inherit" : v > 0 ? "var(--sw-green)" : "var(--sw-red)";
    const signed = (v) => v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${eur(Math.abs(v), 0)}`;
    const t = st.total;
    // Gewinn heute: Tagesänderung je Position (physisches Gold mit der Änderung des Goldpreises)
    const today = {};
    let todayTotal = null;
    for (const p of Object.values(d.pillars || {})) {
      for (const h of p.held || []) {
        const c = h.physical ? p.change_24h : h.change_24h;
        if (c == null || h.value == null) continue;
        const v = h.value - h.value / (1 + c);
        today[p.key] = (today[p.key] || 0) + v;
        todayTotal = (todayTotal || 0) + v;
      }
    }
    // Seit wann: die älteste gehaltene Position der Säule
    const since = {};
    for (const p of Object.values(d.pillars || {})) {
      const ds = (p.held || []).map((h) => h.since).filter(Boolean).sort();
      if (ds.length) since[p.key] = ds[0];
    }
    const todayPct = todayTotal != null && t.value ? todayTotal / (t.value - todayTotal) : null;
    const row = (r) => `<tr>
        <td>${esc(r.name)}${r.invested === false && r.value ? ` <span class="muted">· in Cash</span>` : ""}</td>
        <td class="num">${eur(r.value, 0)}</td>
        <td class="num">${r.cost != null ? eur(r.cost, 0) : (r.invested === false ? "Cash" : "–")}</td>
        <td class="num" style="color:${color(r.pnl)}">${signed(r.pnl)}</td>
        <td class="num" style="color:${color(r.pnl)}">${r.pnl_pct != null ? pct(r.pnl_pct) : ""}</td>
        <td class="num" style="color:${color(today[r.key])}">${today[r.key] != null ? signed(today[r.key]) : "–"}</td>
        <td class="num muted">${since[r.key] ? heldFor(since[r.key], false) : "–"}</td></tr>`;
    return `<div class="section">
      <div class="label">Säulenstatistik · ${d.mode === "paper" ? "Papierdepot" : "Depot"}</div>
      <div class="stat-top num">
        <div><div class="k">Gesamtwert</div><div class="big">${eur(t.value, 0)}</div></div>
        <div><div class="k">Einstand</div><div class="mid">${t.cost != null ? eur(t.cost, 0) : "–"}</div></div>
        <div><div class="k">Gewinn / Verlust</div><div class="mid" style="color:${color(t.pnl)}">${signed(t.pnl)}${t.pnl_pct != null ? ` · ${pct(t.pnl_pct)}` : ""}</div></div>
        <div><div class="k">Heute</div><div class="mid" style="color:${color(todayTotal)}">${signed(todayTotal)}${todayPct != null ? ` · ${pct(todayPct)}` : ""}</div></div>
      </div>
      <table class="stats"><tr><th>Säule</th><th>Wert</th><th>Einstand</th><th colspan="2">Ergebnis</th><th>Heute</th><th>Gehalten</th></tr>
        ${st.rows.map(row).join("")}</table>
      ${this.interestLine(st.interest)}
      ${this.reconcileLine(d.reconcile)}
      <div class="note">Gewinn/Verlust der offenen Positionen zum Geldkurs; Säulen in Cash ohne Gewinn/Verlust.</div>
      ${this.performance(d)}
    </div>`;
  }

  performance(d) {
    const perf = d.performance;
    if (!perf || !perf.series || perf.series.length < 2) return this.history(d);
    const LABELS = { "1W": "1 Woche", "1M": "1 Monat", "3M": "3 Monate", "6M": "6 Monate", YTD: "Seit 1.1.",
                     "1J": "1 Jahr", "3J": "3 Jahre", "5J": "5 Jahre", MAX: "Max." };
    const avail = Object.keys(LABELS).filter((k) => perf.periods[k]);
    let sel = this._period && perf.periods[this._period] ? this._period : (perf.periods["1M"] ? "1M" : avail[0]);
    this._period = sel;
    const signed = (v) => v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${eur(Math.abs(v), 0)}`;
    const col = (v) => v == null || Math.abs(v) < 0.5 ? "inherit" : v > 0 ? "var(--sw-green)" : "var(--sw-red)";
    const chips = Object.keys(LABELS).map((k) => {
      const p = perf.periods[k];
      return `<button class="period${k === sel ? " on" : ""}" data-period="${k}" ${p ? "" : "disabled"}>
        <span class="k">${LABELS[k]}</span>
        <span class="num" style="color:${col(p && p.gain)}">${p ? signed(p.gain) : "–"}</span>
        <span class="num small" style="color:${col(p && p.gain)}">${p && p.pct != null ? pct(p.pct) : ""}</span></button>`;
    }).join("");
    const cur = perf.periods[sel];
    const i0 = Math.max(0, perf.series.findIndex((r) => r[0] >= cur.from));
    const rows = perf.series.slice(i0);
    const flows = (perf.flows || []).slice(i0);
    const names = Object.fromEntries(Object.values(d.pillars).map((p) => [p.key, p]));
    this._chart = { rows, flows, cur, keys: perf.keys, events: (perf.events || []).filter((e) => e.date >= cur.from), names: Object.fromEntries(perf.keys.map((k) => [k, (names[k] || {}).name || k])),
                    colors: Object.fromEntries(perf.keys.map((k) => [k, (names[k] || {}).color || "#888"])) };
    const split = perf.keys.map((k) => {
      const v = cur.pillars[k];
      return `<span><i style="background:${esc(this._chart.colors[k])}"></i>${esc(this._chart.names[k])} <b class="num" style="color:${col(v)}">${signed(v)}</b></span>`;
    }).join("");
    const inv = cur.invested ? ` · im Zeitraum investiert <b class="num">${signed(cur.invested)}</b> (zählt nicht als Gewinn)` : "";
    const src = perf.history
      ? "Stückzahlen je Tag aus deinen Käufen und Verkäufen bei Trade Republic"
      : d.mode === "depot"
        ? "<b>Ohne Kaufhistorie</b> – mit den heutigen Stückzahlen gerechnet. Einmal „Neu synchronisieren“, dann liest die App deine Käufe und Verkäufe"
        : "Papierdepot ab Einstieg";
    return `<div class="label" style="margin-top:12px">Wertentwicklung der Wertpapiere</div>
      <div class="periods">${chips}</div>
      <div class="parts" style="margin:2px 0 4px">${split}${inv ? `<span>${inv}</span>` : ""}</div>
      ${this.chart(rows)}
      <div class="note">${src}. Gewinn = Wertänderung ohne neu investiertes Geld; Cash ist nicht enthalten. ▲ Kauf, ▼ Verkauf – mit der Maus oder dem Finger über die Grafik fahren für Einzelwerte.</div>`;
  }

  chart(rows) {
    const W = 600, H = 170, L = 4, R = 4, T = 8, B = 18;
    const vals = rows.map((r) => r[1]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    const x = (i) => L + (rows.length > 1 ? i / (rows.length - 1) : 0) * (W - L - R);
    const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const line = rows.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r[1]).toFixed(1)}`).join("");
    const area = `${line}L${x(rows.length - 1).toFixed(1)},${H - B}L${x(0).toFixed(1)},${H - B}Z`;
    const gainNow = this._chart && this._chart.cur ? this._chart.cur.gain : rows[rows.length - 1][1] - rows[0][1];
    const c = gainNow >= 0 ? "var(--sw-green)" : "var(--sw-red)";
    const fmtD = (iso, long) => new Date(iso).toLocaleDateString("de-DE", long ? { day: "numeric", month: "short", year: "numeric" } : { month: "short", year: "2-digit" });
    // drei Hilfslinien mit Werten und vier Datumsmarken
    const grid = [0, 0.5, 1].map((f) => { const v = lo + pad + f * (hi - lo - 2 * pad); return `<line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" class="grid"/>`; }).join("");
    const gridLabels = [0, 0.5, 1].map((f) => { const v = lo + pad + f * (hi - lo - 2 * pad); return `<span style="top:${(y(v) / H * 100).toFixed(1)}%">${eur(v, 0)}</span>`; }).join("");
    const ticks = [0, 1 / 3, 2 / 3, 1].map((f) => { const i = Math.round(f * (rows.length - 1)); return `<span style="left:${(x(i) / W * 100).toFixed(1)}%">${fmtD(rows[i][0], rows.length < 120)}</span>`; }).join("");
    return `<div class="chart-wrap">
      <svg class="perf-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
           aria-label="Wert von ${eur(rows[0][1], 0)} auf ${eur(rows[rows.length - 1][1], 0)}">
        ${grid}
        <path d="${area}" fill="${c}" opacity=".12"/>
        <path d="${line}" fill="none" stroke="${c}" stroke-width="1.8" vector-effect="non-scaling-stroke"/>
        <line class="cross" x1="0" x2="0" y1="${T}" y2="${H - B}" style="display:none"/>
      </svg>
      ${(() => {
        const ev = (this._chart && this._chart.events) || [];
        const byDay = {};
        for (const e of ev) byDay[e.date] = (byDay[e.date] || 0) + e.amount;
        return Object.entries(byDay).map(([day, amt]) => {
          let i = rows.findIndex((r) => r[0] >= day);
          if (i < 0) i = rows.length - 1;
          return `<span class="mark ${amt >= 0 ? "buy" : "sell"}" style="left:${(x(i) / W * 100).toFixed(2)}%">${amt >= 0 ? "▲" : "▼"}</span>`;
        }).join("");
      })()}
      <div class="dot" style="display:none;border-color:${c}"></div>
      <div class="ylabels num">${gridLabels}</div>
      <div class="xlabels num">${ticks}</div>
      <div class="tip" style="display:none"></div>
    </div>
    <div class="hist-legend num"><span>${fmtD(rows[0][0], true)} – ${fmtD(rows[rows.length - 1][0], true)} · Tief ${eur(Math.min(...vals), 0)} · Hoch ${eur(Math.max(...vals), 0)}</span>
      ${(() => { const cur = this._chart && this._chart.cur; if (!cur) return ""; const g = cur.gain;
        return `<span style="color:${g >= 0 ? "var(--sw-green)" : "var(--sw-red)"}">Gewinn ${g >= 0 ? "+" : "−"}${eur(Math.abs(g), 0)}${cur.pct != null ? ` (${pct(cur.pct)})` : ""}</span>`; })()}</div>`;
  }

  _bindChart() {
    const wrap = this.shadowRoot.querySelector(".chart-wrap");
    if (!wrap || !this._chart) return;
    const { rows, flows, keys, names, colors, events } = this._chart;
    const svg = wrap.querySelector("svg"), tip = wrap.querySelector(".tip"), cross = wrap.querySelector(".cross"),
          dot = wrap.querySelector(".dot");
    const [, , W, H] = svg.getAttribute("viewBox").split(" ").map(Number);
    const L = 4, R = 4, T = 8, B = 18;
    const vals = rows.map((r) => r[1]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    const show = (clientX) => {
      const box = svg.getBoundingClientRect();
      const fx = Math.min(1, Math.max(0, ((clientX - box.left) / box.width * W - L) / (W - L - R)));
      const i = Math.round(fx * (rows.length - 1));
      const r = rows[i], first = rows[0];
      const px = L + (rows.length > 1 ? i / (rows.length - 1) : 0) * (W - L - R);
      const py = T + (1 - (r[1] - lo) / (hi - lo)) * (H - T - B);
      cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.style.display = "";
      dot.style.display = ""; dot.style.left = `${px / W * 100}%`; dot.style.top = `${py / H * 100}%`;
      const ch = r[1] - first[1];
      const sign = (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${eur(Math.abs(v), 0)}`;
      const colr = (v) => Math.abs(v) < 0.5 ? "inherit" : v > 0 ? "var(--sw-green)" : "var(--sw-red)";
      tip.innerHTML = `<b>${new Date(r[0]).toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "long", year: "numeric" })}</b>
        <div class="row"><span>Gesamt</span><b class="num">${eur(r[1], 0)}</b></div>
        ${(() => { const inv = (flows || []).slice(1, i + 1).reduce((a, f) => a + f[0], 0); const g = ch - inv;
          return `<div class="row"><span>Gewinn seit ${new Date(first[0]).toLocaleDateString("de-DE")}</span><b class="num" style="color:${colr(g)}">${sign(g)}</b></div>`
            + (Math.abs(inv) >= 1 ? `<div class="row"><span>investiert seitdem</span><span class="num">${sign(inv)}</span></div>` : ""); })()}
        ${keys.map((k, j) => `<div class="row"><span><i style="background:${esc(colors[k])}"></i>${esc(names[k])}</span><span class="num">${eur(r[2 + j], 0)}</span></div>`).join("")}
        ${(events || []).filter((e) => e.date === r[0] || (i > 0 && e.date > rows[i - 1][0] && e.date <= r[0])).map((e) =>
          `<div class="row ev"><span>${e.amount >= 0 ? "▲ Kauf" : "▼ Verkauf"} ${esc(e.name)}</span><span class="num">${eur(Math.abs(e.amount), 0)}${e.shares ? ` · ${Math.abs(e.shares).toLocaleString("de-DE", { maximumFractionDigits: 3 })} St.` : ""}</span></div>`).join("")}`;
      tip.style.display = "";
      // neben den Cursor, auf der Seite mit mehr Platz
      const left = px / W * box.width;
      tip.style.left = `${left > box.width / 2 ? Math.max(left - tip.offsetWidth - 14, 0) : Math.min(left + 14, box.width - tip.offsetWidth)}px`;
    };
    const hide = () => { tip.style.display = "none"; cross.style.display = "none"; dot.style.display = "none"; };
    svg.addEventListener("pointermove", (e) => show(e.clientX));
    svg.addEventListener("pointerdown", (e) => show(e.clientX));
    svg.addEventListener("pointerleave", hide);
  }

  history(d) {
    const h = (d.value_history || []).filter((x) => x.value != null);
    if (h.length < 2) {
      return `<div class="label" style="margin-top:12px">Verlauf</div>
        <div class="note">Der Verlauf wird ab heute einmal täglich aufgezeichnet${h.length ? " – erster Punkt " + new Date(h[0].date).toLocaleDateString("de-DE") : ""}.</div>`;
    }
    const W = 400, H = 110, P = 4;
    const vals = h.map((x) => x.value);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (hi - lo < 1) { lo -= 1; hi += 1; }
    const x = (i) => P + (i / (h.length - 1)) * (W - 2 * P);
    const y = (v) => P + (1 - (v - lo) / (hi - lo)) * (H - 2 * P);
    const line = h.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
    const area = `${line}L${x(h.length - 1).toFixed(1)},${H - P}L${x(0).toFixed(1)},${H - P}Z`;
    const first = h[0], last = h[h.length - 1];
    const change = last.value - first.value;
    const col = change >= 0 ? "var(--sw-green)" : "var(--sw-red)";
    const dates = (p) => new Date(p.date).toLocaleDateString("de-DE");
    return `<div class="label" style="margin-top:12px">Verlauf · ${dates(first)} – ${dates(last)}</div>
      <svg class="hist" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
           aria-label="Verlauf des Gesamtwerts von ${eur(first.value, 0)} auf ${eur(last.value, 0)}">
        <path d="${area}" fill="${col}" opacity=".12"/>
        <path d="${line}" fill="none" stroke="${col}" stroke-width="1.8" vector-effect="non-scaling-stroke"/>
        ${h.map((p, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p.value).toFixed(1)}" r="5" fill="transparent"><title>${dates(p)}: ${eur(p.value, 0)}${p.pnl != null ? " · G/V " + eur(p.pnl, 0) : ""}</title></circle>`).join("")}
      </svg>
      <div class="hist-legend num"><span>Tief ${eur(Math.min(...vals), 0)} · Hoch ${eur(Math.max(...vals), 0)}</span>
        <span style="color:${col}">${change >= 0 ? "+" : "−"}${eur(Math.abs(change), 0)} (${pct(change / first.value)})</span></div>`;
  }

  pillars(d, active) {
    const ov = d.overview;
    const tol = ov.tolerance_pp || 5;
    const split = d.tr_split || {};
    const shade = [1, 0.6, 0.38, 0.25];
    const rows = ov.rows.map((r) => {
      const warn = Math.abs(r.diff_pp) > tol;
      // ein Balken je Säule: die Produkte als Abschnitte in der Säulenfarbe, ohne Position als Cash schraffiert
      const parts = (((split.rows || []).find((x) => x.key === r.key) || {}).parts || []).filter((x) => x.value > 0);
      let left = 0;
      const segs = parts.length && ov.total
        ? parts.map((x, i) => {
            const w = x.value / ov.total * 100;
            const seg = `<div class="fill" title="${esc(x.name)}: ${eur(x.value, 0)}" style="left:${left}%;width:${w}%;background:${esc(r.color)};opacity:${shade[i % shade.length]};border-radius:0"></div>`;
            left += w;
            return seg;
          }).join("")
        : `<div class="fill${r.value ? " cash" : ""}" style="width:${Math.min(100, r.ist * 100)}%;background:${esc(r.color)}"></div>`;
      const legend = parts.length
        ? parts.map((x, i) => `<span><i style="background:${esc(r.color)};opacity:${shade[i % shade.length]}"></i>${esc(x.name)} ${eur(x.value, 0)}</span>`).join("")
        : `<span>${r.value ? "als Cash" : "leer"}</span>`;
      return `<div class="pillar">
        <div class="head"><span>${r.key === active ? `<b>${esc(r.name)}</b>` : esc(r.name)}</span>
          <span class="num"><span style="color:${warn ? "var(--sw-orange)" : "inherit"}">${Math.round(r.ist * 100)} %</span>
            <span class="muted">/ ${Math.round(r.soll * 100)} % · ${eur(r.value, 0)}</span></span></div>
        <div class="bar">${segs}<div class="mark" style="left:${r.soll * 100}%"></div></div>
        <div class="parts">${legend}</div>
      </div>`;
    }).join("");
    const pp = (v) => v.toLocaleString("de-DE", { maximumFractionDigits: 1 });
    const note = ov.due
      ? `<div class="note warn">Um ${pp(ov.drift_pp)} Pp von den Soll-Anteilen abgewichen – siehe Tabelle oben${d.mode === "paper" ? "" : "; bei Trade Republic umsetzen"}.</div>
         ${d.mode === "paper" ? `<div class="buttons" style="margin-top:8px"><button class="sw" data-action="rebalance">Angleichung übernehmen</button></div>` : ""}`
      : ov.drift_pp >= 0.5
        ? `<div class="note">Kleine Abweichung (höchstens ${pp(ov.drift_pp)} Pp) – im Rahmen von ±${tol} Pp, kein Handlungsbedarf.</div>`
        : `<div class="note">Nahe an den Soll-Anteilen – einmal im Jahr angleichen.</div>`;
    return `<div class="section"><div class="label">Säulen · ${eur(ov.total, 0)} <span class="muted">· Strich = Soll</span></div>${rows}${note}</div>`;
  }

  unassignedLog(d) {
    const un = (d.depot && d.depot.unassigned) || [];
    if (!un.length) return "";
    const sum = un.reduce((a, u) => a + (u.value || 0), 0);
    return `<div class="log info"><b>Nicht zugeordnet · ${eur(sum, 0)} (zählt nicht mit)</b>\n${un.map((u) =>
      `${esc(u.name)} (${esc(u.isin)}) ${eur(u.value, 0)}${u.suggestion_name ? " – vermutlich " + esc(u.suggestion_name) : ""}`).join("\n")}
Soll eine Position mitzählen: ISIN in den Optionen unter „Weitere ISINs …“ eintragen.</div>`;
  }

  overviewRows(d, clickable) {
    return Object.values(d.pillars).map((p) => {
      const color = { in: "var(--sw-green)", hedged: "var(--sw-blue)", parked: "var(--sw-teal)", cash: "var(--sw-grey)" }[p.state] || "var(--sw-grey)";
      const act = p.action && p.action !== "hold" && p.action !== "cash"
        ? `<span class="a" style="background:${ACTION_COLORS[p.action] || "var(--sw-grey)"}">${esc(p.action_label)}</span>` : "";
      const flip = p.would_flip ? `<ha-icon icon="mdi:swap-vertical-bold" title="Würde zum Monatsende kippen" style="color:var(--sw-orange);--mdc-icon-size:18px"></ha-icon>` : "";
      return `<div class="ov" ${clickable ? `data-pillar="${esc(p.key)}"` : ""}>
        <div class="chip" style="background:${color}"></div>
        <div style="flex:1;min-width:0">
          <div class="n">${esc(p.name)} <span class="s">· ${esc(p.state_label)}${p.target_name && p.state !== "in" ? " · " + esc(p.target_name) : ""}</span></div>
          <div class="s">${esc(p.status)}</div>
        </div>${flip}${act}
      </div>`;
    }).join("");
  }

  bind() {
    this.shadowRoot.querySelectorAll("[data-action]").forEach((b) =>
      b.addEventListener("click", (e) => { e.stopPropagation(); this._action(b.dataset.action); }));
    this.shadowRoot.querySelectorAll("[data-period]").forEach((b) =>
      b.addEventListener("click", (e) => { e.stopPropagation(); this._period = b.dataset.period; this._render(); }));
    this._bindChart();
    this.shadowRoot.querySelectorAll("[data-since]").forEach((b) =>
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        const v = prompt(`Gekauft am (TT.MM.JJJJ) – leer lassen setzt auf den ersten Abgleich zurück:`, b.dataset.date ? new Date(b.dataset.date).toLocaleDateString("de-DE") : "");
        if (v === null) return;
        const m = v.trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
        if (v.trim() && !m) { alert("Bitte als TT.MM.JJJJ eingeben."); return; }
        const iso = m ? `${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}` : null;
        this._action("since", { isin: b.dataset.since, date: iso });
      }));
  }
}

/* ======================= Karte ======================= */

class SaeulenwaechterCard extends SaeulenBase {
  setConfig(config) {
    this._config = config || {};
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return this._config?.pillar ? 10 : 5;
  }

  _render() {
    const d = this._data;
    const cfg = this._config || {};
    let body;
    if (this._error) {
      body = `<div class="section err">${esc(this._error)}</div>`;
    } else if (!d) {
      body = `<div class="section note">Lade …</div>`;
    } else if (cfg.pillar && d.pillars[cfg.pillar]) {
      const p = d.pillars[cfg.pillar];
      body = this.alert(d, p.key) + this.hero(p, d) + this.position(p, d) + this.signals(p) + this.pillars(d, p.key);
    } else {
      body = this.alert(d) + this.stats(d) + `<div class="section"><div class="label">${esc(cfg.title || "Säulenwächter")} · ${d.mode === "paper" ? "Papierdepot" : "Depot"}</div>
        ${this.overviewRows(d, false)}</div>` + this.pillars(d, null);
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${body}</ha-card>`;
    this.bind();
  }
}

/* ======================= Panel ======================= */

class SaeulenwaechterPanel extends SaeulenBase {
  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }

  _render() {
    const d = this._data;
    let body;
    if (this._error) {
      body = `<ha-card><div class="section err">${esc(this._error)}</div></ha-card>`;
    } else if (!d) {
      body = `<ha-card><div class="section note">Lade …</div></ha-card>`;
    } else {
      const sel = this._selected && d.pillars[this._selected] ? this._selected : Object.keys(d.pillars)[0];
      this._selected = sel;
      const p = d.pillars[sel];
      const depot = d.depot || {};
      const tabs = Object.values(d.pillars).map((x) =>
        `<button class="sw" data-pillar="${esc(x.key)}" style="${x.key === sel ? "border-color:var(--primary-color);font-weight:600" : ""}">${esc(x.name)}</button>`).join("");
      const log = this.unassignedLog(d) + ((d.log || []).slice().reverse().map((l) =>
        `<div class="log"><b>${new Date(l.time).toLocaleString("de-DE")}</b>\n${esc(l.text)}</div>`).join("") || `<div class="note">Noch keine Meldungen.</div>`);
      body = `
        <div class="cols">
          <div>
            <ha-card>
              ${this.alert(d)}
              ${this.stats(d)}
              <div class="section">
                <div class="label">Übersicht</div>
                <div class="grid num">
                  <div class="kv"><div class="k">Modus</div><div class="v">${d.mode === "paper" ? "Papierdepot" : "Echtes Depot"}</div></div>
                  <div class="kv"><div class="k">Depotwert (Säulen)</div><div class="v">${eur(d.overview.total, 0)}</div></div>
                  <div class="kv"><div class="k">Trade Republic</div><div class="v" style="color:${depot.connected ? "var(--sw-green)" : "var(--secondary-text-color)"}">${depot.connected ? `Stand ${depot.synced_at ? new Date(depot.synced_at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }) : "–"}` : esc(depot.error || "–")}</div></div>
                  <div class="kv"><div class="k">Nächste Prüfung</div><div class="v">${new Date(d.next_check).toLocaleDateString("de-DE")}</div></div>
                </div>
                ${d.market_error ? `<div class="err" style="margin-top:6px">Kursdaten: ${esc(d.market_error)}</div>` : ""}
              </div>
              <div class="section">${this.overviewRows(d, true)}</div>
              ${this.pillars(d, sel)}
              <div class="section buttons">
                <button class="sw" data-action="refresh">Jetzt aktualisieren</button>
                <button class="sw" data-action="test">WhatsApp-Test</button>
              </div>
            </ha-card>
            <ha-card style="margin-top:16px"><div class="section"><div class="label">Letzte Meldungen</div><div class="log-box">${log}</div></div></ha-card>
          </div>
          <div>
            <div class="buttons" style="margin-bottom:12px">${tabs}</div>
            <ha-card>${this.hero(p, d)}${this.position(p, d)}${this.signals(p)}</ha-card>
          </div>
        </div>`;
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}
      :host { padding: 16px; box-sizing: border-box; min-height: 100vh; background: var(--primary-background-color); }
      .top { display:flex; align-items:center; gap:10px; margin-bottom:16px; }
      .top h1 { font-size:22px; margin:0; font-weight:600; color: var(--primary-text-color); }
      .cols { display:grid; grid-template-columns: minmax(0,1.5fr) minmax(0,1fr); gap:16px; align-items:start; }
      @media (max-width: 900px) { .cols { grid-template-columns: minmax(0,1fr); } }
    </style>
    <div class="top">
      ${this._narrow ? `<ha-menu-button></ha-menu-button>` : ""}
      <ha-icon icon="mdi:pillar" style="color:var(--primary-color)"></ha-icon><h1>Säulenwächter</h1>
    </div>${body}`;
    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) { menu.hass = this._hass; menu.narrow = this._narrow; }
    this.shadowRoot.querySelectorAll("[data-pillar]").forEach((el) =>
      el.addEventListener("click", () => { this._selected = el.dataset.pillar; this._render(); }));
    this.bind();
  }
}

if (!customElements.get("saeulenwaechter-card")) customElements.define("saeulenwaechter-card", SaeulenwaechterCard);
if (!customElements.get("saeulenwaechter-panel")) customElements.define("saeulenwaechter-panel", SaeulenwaechterPanel);

window.customCards = window.customCards || [];
if (!window.customCards.find((c) => c.type === "saeulenwaechter-card")) {
  window.customCards.push({
    type: "saeulenwaechter-card",
    name: "Säulenwächter",
    description: "Die 3-Säulen-Strategie: Signale, Monatsentscheidung und Säulen (Ist / Soll).",
    preview: false,
  });
}
