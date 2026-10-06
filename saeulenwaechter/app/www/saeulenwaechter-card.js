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
const TR_SHADES = ["#af52de", "#ff2d92", "#5e5ce6", "#bf5af2", "#ff6482"];
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
  :host { --sw-green:#34c759; --sw-red:#ff3b30; --sw-orange:#ff9500; --sw-blue:#0a84ff; --sw-teal:#30b0c7; --sw-tr:#af52de;
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
  .bar { position:relative; height:5px; border-radius:3px; background:var(--divider-color); margin:5px 0 3px; }
  .bar .fill { position:absolute; left:0; top:0; bottom:0; border-radius:3px; }
  .bar .mark { position:absolute; top:-2px; bottom:-2px; width:1.5px; background:var(--primary-text-color); }
  .bar.tr { height:4px; margin:3px 0 2px; }
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
  .hist-legend { display:flex; justify-content:space-between; font-size:11px; color:var(--secondary-text-color); margin-top:2px; }
  .stat-top { display:flex; gap:18px; flex-wrap:wrap; align-items:flex-end; margin:2px 0 8px; }
  .stat-top .k { font-size:11px; color:var(--secondary-text-color); }
  .stat-top .big { font-size:24px; font-weight:700; }
  .stat-top .mid { font-size:15px; font-weight:600; }
  .trv { font-size:11px; color:var(--sw-tr); }
  .trv.warn { color:var(--sw-orange); }
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
  .log { font-size:11.5px; white-space:pre-wrap; color:var(--secondary-text-color); border-left:3px solid var(--divider-color);
         padding-left:8px; margin:6px 0; }
`;

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

  async _action(action) {
    try {
      await this._hass.callWS({ type: "saeulenwaechter/action", action });
      setTimeout(() => this._load(), 1500);
    } catch (e) {
      alert(e.message || e);
    }
  }

  /* ---------- Bausteine ---------- */

  hero(p, d) {
    const live = p.state && p.live_state && p.live_state !== p.state;
    return `
      <div class="hero" style="background:linear-gradient(135deg, ${esc(p.color)}, var(--sw-blue))">
        <div class="icon"><ha-icon icon="mdi:calendar-clock"></ha-icon></div>
        <div style="flex:1;min-width:0">
          <h2>${esc(p.instrument)} ${d.mode === "paper" ? '<span class="badge">PAPER</span>' : '<span class="badge">DEPOT</span>'}</h2>
          <div class="sub">${esc(p.name)} · Monatlicher Trendfolger · ${esc(p.isin)}</div>
          <div class="price num">${eur(p.price)} <span style="font-size:13px;font-weight:400;opacity:.85">${p.change_24h != null ? pct(p.change_24h) + " heute" : ""}</span></div>
          <div class="status"><span class="dot" style="background:#fff"></span><span>${esc(p.status)}</span></div>
          ${live ? `<div class="status" style="opacity:.85">Aktuelle Daten würden „${esc(MONTH_LABELS[p.live_state])}“ ergeben – entschieden wird am Monatsersten.</div>` : ""}
        </div>
      </div>`;
  }

  position(p) {
    if (!p.held || !p.held.length) return "";
    return `<div class="section"><div class="label">Offene Position</div>${p.held.map((h) => {
      const res = h.value != null && h.cost ? h.value / h.cost - 1 : null;
      return `<div class="grid num">
        <div class="kv"><div class="k">Instrument</div><div class="v">${esc(h.name)}${h.counts_as_name ? `<div class="s" style="font-size:11px;color:var(--secondary-text-color)">zählt als ${esc(h.counts_as_name)}</div>` : ""}</div></div>
        <div class="kv"><div class="k">Menge</div><div class="v">${(h.size ?? 0).toLocaleString("de-DE", { maximumFractionDigits: 4 })}</div></div>
        <div class="kv"><div class="k">Einstieg</div><div class="v">${eur(h.avg_buy)}</div></div>
        <div class="kv"><div class="k">Investiert</div><div class="v">${eur(h.cost, 0)}</div></div>
        <div class="kv"><div class="k">Wert (Geldkurs)</div><div class="v">${eur(h.value, 0)}</div></div>
        <div class="kv"><div class="k">Ergebnis</div><div class="v" style="color:${res == null || Math.abs(res) < 0.0005 ? "inherit" : res > 0 ? "var(--sw-green)" : "var(--sw-red)"}">${pct(res)}</div></div>
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

  trBar(split, key, label) {
    if (!split) return "";
    const t = key === "cash" ? split.cash : (split.rows || []).find((x) => x.key === key);
    if (!t) return "";
    const diff = (t.ist - t.soll) * 100;
    const warn = Math.abs(diff) >= 5;
    // mehrere Produkte einer Säule: je ein Abschnitt, abgestuft eingefärbt
    const parts = t.parts && t.parts.length > 1 ? t.parts : null;
    let left = 0;
    const fills = parts
      ? parts.map((x, i) => {
          const w = x.ist * 100;
          const seg = `<div class="fill" title="${esc(x.name)} (${esc(x.isin)}): ${Math.round(x.ist * 100)} % · ${eur(x.value, 0)}"
            style="left:${left}%;width:${w}%;background:${TR_SHADES[i % TR_SHADES.length]};border-radius:0"></div>`;
          left += w;
          return seg;
        }).join("")
      : `<div class="fill" style="width:${Math.min(100, t.ist * 100)}%;background:var(--sw-tr)"></div>`;
    const legend = parts
      ? `<div class="trv num">${parts.map((x, i) => `<span style="color:${TR_SHADES[i % TR_SHADES.length]}">■</span> ${esc(x.name)} ${Math.round(x.ist * 100)} %`).join(" · ")}</div>`
      : "";
    return `<div class="bar tr" style="overflow:hidden">${fills}
        <div class="mark" style="left:${t.soll * 100}%"></div></div>
      <div class="trv num${warn ? " warn" : ""}">${label ? esc(label) + " · " : ""}${split.source === "paper" ? "Papierdepot" : "Trade Republic"} ${Math.round(t.ist * 100)} % · soll ${Math.round(t.soll * 100)} % · ${eur(t.value, 0)}</div>${legend}`;
  }

  trExtra(d) {
    const split = d.tr_split;
    const un = (d.depot && d.depot.unassigned) || [];
    if (!split && !un.length) return "";
    const cash = split ? `<div class="pillar"><div class="head"><span>Cash</span></div>${this.trBar(split, "cash")}</div>` : "";
    const list = un.length ? `<div class="note warn">Nicht zugeordnet: ${un.map((u) =>
      `${esc(u.name)} (${esc(u.isin)}, ${eur(u.value, 0)})${u.suggestion_name ? " – vermutlich " + esc(u.suggestion_name) : ""}`).join("; ")}.
      In den Optionen unter „Weitere ISINs …“ eintragen, dann zählt die Position zur Säule.</div>` : "";
    const legend = split ? `<div class="note"><span style="color:var(--sw-tr)">■</span> Aktueller Bestand ${split.source === "paper" ? "im Papierdepot" : "bei Trade Republic (erkannte Positionen"}${d.physical_gold && d.physical_gold.items && d.physical_gold.items.length ? " + physisches Gold" : ""} + Cash = ${eur(split.base, 0)}${split.source === "paper" ? "" : ")"}, Strich = Soll laut aktueller Entscheidung.</div>` : "";
    return cash + legend + list;
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

  interestLine(z) {
    if (!z) return "";
    if (z.rate == null) return `<div class="note">Zinsen auf Cash: Satz noch unbekannt – kommt beim nächsten Abgleich mit Trade Republic.</div>`;
    const rate = `${(z.rate * 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} % p. a.`;
    const src = z.source === "option" ? "eigener Wert" : "laut Trade Republic";
    const earned = z.earned ? ` · bisher gutgeschrieben ${eur(z.earned, 2)}` : "";
    return `<div class="interest"><span>💶 Zinsen auf Cash</span>
      <b>${rate}</b> <span class="muted">(${src})</span> auf ${eur(z.cash, 0)} ≈ <b>${eur(z.per_year, 0)} im Jahr</b>${earned}</div>`;
  }

  rebalanceTable(rows) {
    const pc = (v) => `${(v * 100).toLocaleString("de-DE", { maximumFractionDigits: 1 })} %`;
    const move = (r) => Math.abs(r.delta) < 1 ? "passt"
      : `${r.delta > 0 ? (r.cash ? "Cash +" : "kaufen ") : "verkaufen "}${eur(Math.abs(r.delta), 0)}`;
    return `<table class="alarm-table">
      <tr><th>Säule</th><th class="num">Ist</th><th class="num">Ziel</th><th class="num">Anteil</th><th>Umsetzen</th></tr>
      ${rows.map((r) => `<tr><td>${esc(r.name)}</td><td class="num">${eur(r.value, 0)}</td>
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
    const row = (r) => `<tr>
        <td>${esc(r.name)}</td>
        <td class="num">${eur(r.value, 0)}</td>
        <td class="num">${r.cost != null ? eur(r.cost, 0) : (r.invested === false ? "Cash" : "–")}</td>
        <td class="num" style="color:${color(r.pnl)}">${signed(r.pnl)}</td>
        <td class="num" style="color:${color(r.pnl)}">${r.pnl_pct != null ? pct(r.pnl_pct) : ""}</td></tr>`;
    return `<div class="section">
      <div class="label">Säulenstatistik · ${d.mode === "paper" ? "Papierdepot" : "Depot"}</div>
      <div class="stat-top num">
        <div><div class="k">Gesamtwert</div><div class="big">${eur(t.value, 0)}</div></div>
        <div><div class="k">Einstand</div><div class="mid">${t.cost != null ? eur(t.cost, 0) : "–"}</div></div>
        <div><div class="k">Gewinn / Verlust</div><div class="mid" style="color:${color(t.pnl)}">${signed(t.pnl)}${t.pnl_pct != null ? ` · ${pct(t.pnl_pct)}` : ""}</div></div>
      </div>
      <table class="stats"><tr><th>Säule</th><th>Wert</th><th>Einstand</th><th colspan="2">Ergebnis</th></tr>
        ${st.rows.map(row).join("")}</table>
      ${this.interestLine(st.interest)}
      <div class="note">Gewinn/Verlust der offenen Positionen zum Geldkurs; Säulen in Cash ohne Gewinn/Verlust.</div>
      ${this.history(d)}
    </div>`;
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
    const rows = ov.rows.map((r) => {
      const warn = Math.abs(r.diff_pp) >= 5;
      const isActive = r.key === active;
      return `<div class="pillar">
        <div class="head"><span>${isActive ? `<b>${esc(r.name)}</b>` : esc(r.name)}</span>
          <span class="num" style="color:${warn ? "var(--sw-orange)" : "inherit"}">${Math.round(r.ist * 100)} % / ${Math.round(r.soll * 100)} %</span></div>
        <div class="bar"><div class="fill" style="width:${Math.min(100, r.ist * 100)}%;background:${esc(r.color)}"></div>
          <div class="mark" style="left:${r.soll * 100}%"></div></div>
        <div class="val num">${ov.due ? `${eur(r.value, 0)} → ${eur(r.target_value, 0)}` : eur(r.value, 0)}</div>
        ${this.trBar(d.tr_split, r.key)}
      </div>`;
    }).join("") + this.trExtra(d);
    const note = ov.due
      ? `<div class="note warn">Um ${ov.drift_pp.toLocaleString("de-DE", { maximumFractionDigits: 1 })} Pp von den Soll-Anteilen abgewichen – die Beträge nach dem Pfeil stellen sie wieder her.</div>
         <div class="buttons" style="margin-top:8px"><button class="sw" data-action="rebalance">Angleichung übernehmen</button></div>`
      : `<div class="note">Nahe an den Soll-Anteilen (Ist / Soll) – einmal im Jahr angleichen.</div>`;
    return `<div class="section"><div class="label">Säulen · ${eur(ov.total, 0)}</div>${rows}${note}</div>`;
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
      body = this.alert(d, p.key) + this.hero(p, d) + this.position(p) + this.signals(p) + this.pillars(d, p.key);
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
      const log = (d.log || []).slice().reverse().map((l) =>
        `<div class="log"><b>${new Date(l.time).toLocaleString("de-DE")}</b>\n${esc(l.text)}</div>`).join("") || `<div class="note">Noch keine Meldungen.</div>`;
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
                  <div class="kv"><div class="k">Trade Republic</div><div class="v" style="color:${depot.connected ? "var(--sw-green)" : "var(--secondary-text-color)"}">${depot.connected ? "verbunden" : esc(depot.error || "–")}</div></div>
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
            <ha-card style="margin-top:16px"><div class="section"><div class="label">Letzte Meldungen</div>${log}</div></ha-card>
          </div>
          <div>
            <div class="buttons" style="margin-bottom:12px">${tabs}</div>
            <ha-card>${this.hero(p, d)}${this.position(p)}${this.signals(p)}</ha-card>
          </div>
        </div>`;
    }
    this.shadowRoot.innerHTML = `<style>${STYLE}
      :host { padding: 16px; box-sizing: border-box; min-height: 100vh; background: var(--primary-background-color); }
      .top { display:flex; align-items:center; gap:10px; margin-bottom:16px; }
      .top h1 { font-size:22px; margin:0; font-weight:600; color: var(--primary-text-color); }
      .cols { display:grid; grid-template-columns: minmax(0,1fr) minmax(0,1.2fr); gap:16px; align-items:start; }
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
