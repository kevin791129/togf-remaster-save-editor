"use strict";
// ToGf Save Editor frontend: plain JS over the /api endpoints (see togf_save/web/app.py).
// Every edit is sent to the server right away; the save is encoded on download.
// Interface text comes from /api/meta (togf_save/locales/<lang>/ui.json).
// Nothing but the language and the browser tab's session id is remembered across reloads.

const $ = (id) => document.getElementById(id);
const FAILED = Symbol("failed");

const state = {
  lang: null,
  meta: null,
  session: null,
  tab: "overview",
  sub: {},            // group id -> selected table id
  char: null,         // characters tab: selected character id
  section: null,      // characters tab: selected section, kept when the character changes
  filter: "",
  showEmpty: false,   // shards tab
  showHidden: false,  // global: list hidden fields
  force: false,       // global: allow editing read-only fields
};
let renderToken = 0;

// --- storage (may be unavailable: private mode, blocked site data) ---

function storage(kind) {
  return {
    get(key) { try { return window[kind].getItem(key); } catch { return null; } },
    set(key, value) {
      try { value == null ? window[kind].removeItem(key) : window[kind].setItem(key, value); } catch { /* ignore */ }
    },
  };
}
const prefs = storage("localStorage");     // language
const tabStore = storage("sessionStorage"); // session id of this browser tab

// --- helpers ---

function t(key, values = {}) {
  const template = (state.meta && state.meta.ui[key]) || key;
  return template.replace(/\{(\w+)\}/g, (m, k) => (k in values ? values[k] : m));
}

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k.includes("-") || !(k in el)) el.setAttribute(k, v === true ? "" : v);
    else el[k] = v;
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : String(c));
  }
  return el;
}

const hex = (n, width = 5) => "0x" + n.toString(16).padStart(width, "0");

let toastTimer;
function toast(message, error = false) {
  const el = $("toast");
  el.textContent = message;
  el.className = "toast" + (error ? " error" : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, error ? 6000 : 2500);
}

// --- hints: an ⓘ whose text shows on hover or keyboard focus ---

let hintCount = 0;

// [ⓘ, screen-reader copy of the text]; `focusable`: false inside another control (a tab button).
// Returns the id of the screen-reader copy too, for aria-describedby on the related control.
function hintIcon(text, focusable = true) {
  const id = "hint-" + ++hintCount;
  const icon = h("i", { class: "info", "data-hint": text, tabIndex: focusable ? 0 : null,
                        "aria-label": t("web.hint"), "aria-describedby": id }, "i");
  return { id, nodes: [icon, h("span", { id, class: "sr-only" }, text)] };
}

function showTip(target) {
  const tip = $("tip");
  tip.textContent = target.dataset.hint;
  tip.hidden = false;
  const r = target.getBoundingClientRect();
  const left = Math.min(r.left, window.innerWidth - tip.offsetWidth - 8);
  const below = r.bottom + 6 + tip.offsetHeight < window.innerHeight;
  tip.style.left = Math.max(8, left) + "px";
  tip.style.top = (below ? r.bottom + 6 : r.top - tip.offsetHeight - 6) + "px";
}
const hideTip = () => { $("tip").hidden = true; };

for (const ev of ["pointerover", "focusin"]) {
  document.addEventListener(ev, (e) => {
    const target = e.target.closest && e.target.closest("[data-hint]");
    if (target) showTip(target);
  });
}
for (const ev of ["pointerout", "focusout"]) {
  document.addEventListener(ev, (e) => { if (e.target.closest && e.target.closest("[data-hint]")) hideTip(); });
}
document.addEventListener("scroll", hideTip, true);

// --- API ---

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body instanceof FormData) {
    options.body = body;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const res = await fetch(path, options);
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = typeof data.detail === "string" ? data.detail : data.detail.map((d) => d.msg).join("; ");
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? null : res;
}

const json = async (method, path, body) => (await api(method, path, body)).json();
const withLang = (path) => path + (path.includes("?") ? "&" : "?") + "lang=" + encodeURIComponent(state.lang);
const sessionPath = (sub = "") => `/api/sessions/${state.session.id}${sub}`;
const tablePath = (tableId) =>
  withLang(sessionPath(`/tables/${tableId}`)) + (state.showHidden ? "&show_hidden=true" : "");

// Runs an API call; shows errors and returns FAILED instead of throwing.
async function run(call) {
  try {
    return await call();
  } catch (e) {
    if (e instanceof ApiError && e.status === 404 && /unknown session/.test(e.message)) {
      setSession(null);
      toast(t("web.session_lost"), true);
    } else {
      toast(t("common.error", { message: e.message }), true);
    }
    return FAILED;
  }
}

async function refreshSummary() {
  const s = await run(() => json("GET", sessionPath()));
  if (s !== FAILED) {
    state.session = s;
    updateHeader();
  }
}

// --- chrome: header, tabs, global options, language ---

async function loadMeta(lang) {
  state.meta = await json("GET", "/api/meta" + (lang ? "?lang=" + encodeURIComponent(lang) : ""));
  state.lang = lang || state.meta.default_lang;
}

function tabList() {
  const group = (id) => state.meta.groups.find((g) => g.id === id);
  return [
    { id: "overview", label: t("web.tab.overview") },
    { id: "characters", label: t("group.characters") },
    { id: "items", label: group("items").name },
    { id: "shards", label: state.meta.shards.name },
    { id: "misc", label: group("misc").name },
  ];
}

function renderChrome() {
  document.documentElement.lang = state.lang;
  document.title = t("web.title");
  $("title").textContent = t("web.title");
  $("open-text").textContent = t("web.open");
  $("download").textContent = t("web.download");
  $("close").textContent = t("web.close");
  $("modified").textContent = t("web.modified");
  $("lang-label").textContent = t("web.language");
  $("lang").replaceChildren(...Object.entries(state.meta.languages).map(
    ([code, name]) => h("option", { value: code, selected: code === state.lang }, name)));
  $("tabs").replaceChildren(...tabList().map((tab) => h("button", {
    role: "tab",
    "aria-selected": String(tab.id === state.tab),
    onclick: () => { state.tab = tab.id; state.filter = ""; renderChrome(); render(); },
  }, tab.label)));
  $("show-hidden-text").textContent = t("web.show_hidden");
  $("force-text").textContent = t("web.allow_read_only");
  $("force-warning").textContent = t("web.force_warning");
  $("show-hidden").checked = state.showHidden;
  $("force").checked = state.force;
  $("force-warning").classList.toggle("on", state.force);
  updateHeader();
}

function updateHeader() {
  const s = state.session;
  $("filename").textContent = s ? s.filename : "";
  $("modified").hidden = !(s && s.modified);
  $("download").hidden = !s;
  $("close").hidden = !s;
  $("tabs").hidden = !s;
  $("globals").hidden = !s;
}

function setSession(summary) {
  state.session = summary;
  tabStore.set("session", summary ? summary.id : null);
  if (!summary) state.tab = "overview";
  renderChrome();
  render();
}

// --- views ---

async function render() {
  const token = ++renderToken;
  hideTip();
  const main = $("main");
  if (!state.session) {
    main.replaceChildren(h("p", { class: "start" }, t("web.start")));
    return;
  }
  const view = { overview: viewOverview, characters: viewCharacters, items: () => viewGroup("items"),
                 shards: viewShards, misc: viewMisc }[state.tab];
  const content = await view();
  if (token === renderToken && content) main.replaceChildren(...[content].flat(Infinity));
}

async function viewOverview() {
  const s = state.session;
  const slot1 = await run(() => json("GET", sessionPath("/slot1")));
  const out = [];
  if (s.warnings.length) {
    out.push(h("div", { class: "notice warn" }, h("ul", {}, s.warnings.map((w) => h("li", {}, w)))));
  }
  out.push(h("div", { class: "scroll" }, h("table", {},
    h("tr", {}, h("th", {}, t("web.overview.file")), h("td", { class: "mono" }, s.filename)),
    h("tr", {}, h("th", {}, t("web.overview.size")),
      h("td", { class: "mono" }, `${s.size.toLocaleString()} (${hex(s.size)})`)),
  )));

  const rows = [];
  for (const slot of s.info.slots) {
    slot.copies.forEach((c, i) => {
      const same = slot.backup_identical;
      rows.push(h("tr", {},
        h("td", {}, i === 0 ? `slot${slot.slot}` : ""),
        h("td", {}, t("info.copy." + c.copy)),
        h("td", { class: "mono" }, hex(c.offset)),
        c.error
          ? h("td", { class: "bad", colSpan: 2 }, c.error)
          : [h("td", { class: "mono" }, hex(c.length)),
             h("td", { class: "mono" }, hex(c.crc, 8) + " ",
               h("span", { class: c.crc_ok ? "ok" : "bad" }, t(c.crc_ok ? "info.crc_ok" : "info.crc_bad")))],
        h("td", { class: same ? "ok" : "bad" }, i === 0 ? t(same ? "common.yes" : "common.no") : ""),
      ));
    });
  }
  out.push(h("h2", {}, t("web.overview.slot")), h("div", { class: "scroll" }, h("table", {},
    h("thead", {}, h("tr", {}, ["web.overview.slot", "web.overview.copy", "web.overview.offset",
      "web.overview.length", "web.overview.crc", "web.overview.backup_identical"].map((k) => h("th", {}, t(k))))),
    h("tbody", {}, rows))));

  if (slot1 !== FAILED) {
    out.push(h("h2", {}, t("web.overview.slot1")),
      h("div", { class: "scroll" }, h("pre", { class: "json" }, JSON.stringify(slot1.data, null, 2))));
  }
  return out;
}

// Fixed-width columns (see style.css) so widths don't shift between tabs; null = takes the rest.
const colgroup = (...classes) => h("colgroup", {}, classes.map((c) => h("col", { class: c })));

// A row of tabs. items: [{key, label}]; `hint` (if any) is shown as an ⓘ on the selected tab.
function tabRow(items, selected, onPick, { hint = "", label = null } = {}) {
  return h("nav", { class: "subtabs", role: "tablist", "aria-label": label }, items.map((item) => {
    const isSelected = item.key === selected;
    const info = isSelected && hint ? hintIcon(hint, false) : null;
    return h("button", {
      role: "tab", "aria-selected": String(isSelected), "aria-describedby": info ? info.id : null,
      onclick: () => onPick(item.key),
    }, item.label, info ? info.nodes : null);
  }));
}

// The value cell: an input, or the value as text when read-only (and not forced), then a lock slot.
function valueCell(entry, onCommit) {
  const readOnly = entry.read_only && !state.force;
  const lock = h("span", { class: "lock", "aria-hidden": "true",
    title: entry.read_only ? t(state.force ? "web.read_only_forced" : "web.read_only") : null },
    entry.read_only ? (state.force ? "🔓" : "🔒") : "");
  if (readOnly) {
    return { input: null, cell: h("td", { class: "num" }, h("span", { class: "value" },
      h("span", { class: "text", "aria-label": t("web.read_only_value", { name: entry.name, value: entry.value }) },
        entry.value), lock)) };
  }
  const input = h("input", { type: "number", min: 0, max: entry.max, step: 1, value: entry.value,
                             class: entry.read_only ? "forced" : null, "aria-label": entry.name,
                             "aria-describedby": entry.hintId });
  input.addEventListener("change", () => onCommit(input));
  return { input, cell: h("td", { class: "num" }, h("span", { class: "value" }, input, lock)) };
}

// A table of editable values. entries: [{tableId, index, number, id, name, offset, value, max,
// read_only, hidden, hint}]
function valueTable(entries) {
  const byKey = new Map();
  const commit = async (entry, input, tr) => {
    const value = Number(input.value);
    if (input.value === "" || !Number.isInteger(value) || value < 0 || value > entry.max) {
      input.classList.add("invalid");
      toast(t("common.error", { message: `0-${entry.max}` }), true);
      input.value = entry.value;
      setTimeout(() => input.classList.remove("invalid"), 1500);
      return;
    }
    if (value === entry.value) return;
    const res = await run(() => json("PATCH", tablePath(entry.tableId),
                                     { set: { [entry.index]: value }, force: state.force }));
    if (res === FAILED) {
      input.value = entry.value;
      return;
    }
    update(entry.tableId, res.rows);
    tr.classList.remove("flash");
    void tr.offsetWidth; // restart the animation
    tr.classList.add("flash");
    refreshSummary();
  };

  const rows = entries.map((entry) => {
    const hint = entry.hint ? hintIcon(entry.hint) : null;
    entry.hintId = hint ? hint.id : null;
    const tr = h("tr", { class: entry.hidden ? "hidden-row" : null });
    const { input, cell } = valueCell(entry, (inp) => commit(entry, inp, tr));
    tr.append(
      h("td", { class: "num" }, entry.number),
      h("td", { class: entry.name === entry.id ? "unknown" : "", title: entry.name },
        entry.name, hint ? hint.nodes : null, entry.hidden ? h("span", { class: "tag" }, t("web.hidden")) : null),
      h("td", { class: "mono" }, hex(entry.offset)),
      cell);
    byKey.set(`${entry.tableId}/${entry.index}`, { entry, input, tr });
    return tr;
  });

  function update(tableId, tableRows) {
    for (const row of tableRows) {
      const item = byKey.get(`${tableId}/${row.index}`);
      if (item) {
        item.entry.value = row.value;
        if (item.input) item.input.value = row.value;
        else item.tr.querySelector(".value .text").textContent = row.value;
      }
    }
  }

  function filter(text) {
    const q = text.trim().toLowerCase();
    for (const { entry, tr } of byKey.values()) {
      tr.hidden = q !== "" && !`${entry.number} ${entry.name} ${entry.id}`.toLowerCase().includes(q);
    }
  }

  const el = h("div", { class: "scroll" }, h("table", { class: "fixed" },
    colgroup("c-index", null, "c-offset", "c-value"),
    h("thead", {}, h("tr", {},
      h("th", { class: "num" }, t("web.col.index")), h("th", {}, t("web.col.name")),
      h("th", {}, t("web.col.offset")), h("th", { class: "num" }, t("web.col.value")))),
    h("tbody", {}, rows)));
  return { el, update, filter };
}

const entriesOf = (data) => data.rows.map((row) => ({
  tableId: data.id, index: row.index, number: row.number, id: row.id, name: row.name, offset: row.offset,
  value: row.value, max: row.max, read_only: row.read_only, hidden: row.hidden, set_all: row.set_all, hint: row.hint,
}));

// "Set all to max" for the tables in `datas`, or null when none of them has bulk-editable entries.
// Disabled (with a tooltip) when every bulk-editable entry is read-only and forcing is off.
function setAllButton(datas, table) {
  const bulk = datas.filter((d) => d.set_all);
  if (!bulk.length) return null;
  const writable = bulk.some((d) => d.rows.some((r) => r.set_all && (state.force || !r.read_only)));
  const label = bulk.length === 1 && bulk[0].max != null
    ? t("web.set_all_max", { max: bulk[0].max }) : t("web.set_all_to_max");
  return h("button", {
    disabled: !writable, title: writable ? null : t("web.set_all_needs_force"),
    onclick: async () => {
      for (const data of bulk) {
        const res = await run(() => json("PATCH", tablePath(data.id), { set_all: "max", force: state.force }));
        if (res === FAILED) break;
        table.update(data.id, res.rows);
      }
      refreshSummary();
    },
  }, label);
}

// Filter box + set-all button + table, for one table's data.
function tableBlock(data) {
  const table = valueTable(entriesOf(data));
  table.filter(state.filter);
  const toolbar = h("div", { class: "toolbar" },
    h("input", { type: "text", placeholder: t("web.filter"), value: state.filter, "aria-label": t("web.filter"),
                 oninput: (e) => { state.filter = e.target.value; table.filter(state.filter); } }),
    h("span", { class: "spacer" }),
    setAllButton([data], table));
  return [toolbar, table.el];
}

async function viewCharacters() {
  const characters = state.meta.characters;
  let character = characters.find((c) => c.id === state.char);
  if (!character) {
    character = characters[0];
    state.char = character.id;
  }
  if (!character.tables.some((tb) => tb.section === state.section)) state.section = character.tables[0].section;
  const tableId = character.tables.find((tb) => tb.section === state.section).id;

  const data = await run(() => json("GET", tablePath(tableId)));
  if (data === FAILED) return null;

  const pick = (id) => { state.char = id; state.filter = ""; render(); };
  const side = h("div", { class: "side", role: "tablist", "aria-label": t("group.characters"),
                          "aria-orientation": "vertical" },
    characters.map((c) => h("button", { role: "tab", "aria-selected": String(c.id === state.char),
                                        onclick: () => pick(c.id) }, c.name)));
  const select = h("select", { class: "side-select", "aria-label": t("group.characters"),
                               onchange: (e) => pick(e.target.value) },
    characters.map((c) => h("option", { value: c.id, selected: c.id === state.char }, c.name)));
  const sections = tabRow(character.tables.map((tb) => ({ key: tb.section, label: tb.name })), state.section,
    (key) => { state.section = key; state.filter = ""; render(); },
    { hint: data.hint, label: t("web.sections") });

  return h("div", { class: "split" }, side,
    h("div", { class: "content" }, select, sections, tableBlock(data)));
}

async function viewGroup(groupId) {
  const group = state.meta.groups.find((g) => g.id === groupId);
  let tableId = state.sub[groupId];
  if (!group.tables.some((tb) => tb.id === tableId)) tableId = state.sub[groupId] = group.tables[0].id;

  const data = await run(() => json("GET", tablePath(tableId)));
  if (data === FAILED) return null;

  const subtabs = tabRow(group.tables.map((tb) => ({ key: tb.id, label: tb.name })), tableId,
    (key) => { state.sub[groupId] = key; state.filter = ""; render(); }, { hint: data.hint });
  return [subtabs, ...tableBlock(data)];
}

async function viewMisc() {
  const group = state.meta.groups.find((g) => g.id === "misc");
  if (!group.tables.length) return h("p", { class: "start" }, t("web.misc_empty"));

  const datas = await Promise.all(group.tables.map((tb) => run(() => json("GET", tablePath(tb.id)))));
  if (datas.includes(FAILED)) return null;
  const table = valueTable(datas.flatMap(entriesOf));
  return [h("div", { class: "toolbar" }, h("span", { class: "spacer" }), setAllButton(datas, table)), table.el];
}

async function viewShards() {
  const data = await run(() => json("GET", withLang(sessionPath("/shards"))));
  if (data === FAILED) return null;
  const container = h("div");
  drawShards(container, data);
  return container;
}

function drawShards(container, data) {
  const meta = state.meta.shards;
  const typeName = (n) => meta.types[n - 1].name;
  const apply = async (call, flashSlot) => {
    const res = await run(call);
    if (res === FAILED) return;
    drawShards(container, res);
    refreshSummary();
    if (flashSlot != null) {
      const tr = container.querySelector(`tr[data-slot="${flashSlot}"]`);
      if (tr) {
        tr.classList.add("flash");
        tr.scrollIntoView({ block: "nearest" });
      }
    }
  };
  const put = (slot, shard) => apply(() => json("PUT", withLang(sessionPath(`/shards/${slot}`)), shard), slot);
  const remove = (slot) => apply(() => json("DELETE", withLang(sessionPath(`/shards/${slot}`))));
  const fresh = () => ({ type: 1, nature: 1, strength: meta.max_strength });

  const out = [];
  if (data.mismatches.length) {
    out.push(h("div", { class: "notice warn" },
      h("ul", {}, data.mismatches.map((m) => h("li", {},
        t("web.shards.mismatch", { name: typeName(m.type), type: m.type, stored: m.stored, actual: m.actual })))),
      h("button", { onclick: () => apply(() => json("POST", withLang(sessionPath("/shards/fix-counts")))) },
        t("web.shards.fix"))));
  }

  out.push(h("div", { class: "toolbar" },
    h("span", {}, t("shards.used", { used: data.used, slots: meta.slots })),
    h("label", {}, h("input", { type: "checkbox", checked: state.showEmpty,
                               onchange: (e) => { state.showEmpty = e.target.checked; drawShards(container, data); } }),
      " " + t("web.shards.show_empty")),
    h("span", { class: "spacer" }),
    h("button", { class: "primary", onclick: () => {
      const empty = data.rows.find((r) => !r.shard && !r.error);
      if (empty) put(empty.slot, fresh());
      else toast(t("web.shards.full"), true);
    } }, t("web.shards.add")),
    h("button", { onclick: () => {
      if (confirm(t("web.shards.confirm_clear", { slots: meta.slots }))) {
        apply(() => json("POST", withLang(sessionPath("/shards/clear"))));
      }
    } }, t("web.shards.clear_all"))));

  const options = (list, selected) => list.map((o) =>
    h("option", { value: o.value, selected: o.value === selected }, o.name));

  const rows = data.rows.filter((r) => r.shard || r.error || state.showEmpty).map((row) => {
    const head = [h("td", { class: "num" }, row.slot), h("td", { class: "mono" }, hex(row.offset))];
    if (row.error) {
      return h("tr", { "data-slot": row.slot }, head,
        h("td", { class: "bad", colSpan: 4 }, `${row.raw}  ${row.error}`));
    }
    if (!row.shard) {
      return h("tr", { "data-slot": row.slot }, head,
        h("td", { class: "unknown", colSpan: 3 }, t("shard.empty")),
        h("td", { class: "action" }, h("button", { onclick: () => put(row.slot, fresh()) }, "+")));
    }
    const s = row.shard;
    const type = h("select", { "aria-label": t("shard.field.type") }, options(meta.types, s.type));
    const nature = h("select", { "aria-label": t("shard.field.nature") }, options(meta.natures, s.nature));
    const strength = h("input", { type: "number", min: 1, max: meta.max_strength, step: 1, value: s.strength,
                                  "aria-label": t("shard.field.strength") });
    const commit = () => {
      const shard = { type: Number(type.value), nature: Number(nature.value), strength: Number(strength.value) };
      if (!Number.isInteger(shard.strength) || shard.strength < 1 || shard.strength > meta.max_strength) {
        toast(t("common.error", { message: `1-${meta.max_strength}` }), true);
        strength.value = s.strength;
        return;
      }
      put(row.slot, shard);
    };
    for (const control of [type, nature, strength]) control.addEventListener("change", commit);
    return h("tr", { "data-slot": row.slot }, head,
      h("td", {}, type), h("td", {}, nature), h("td", { class: "num" }, strength),
      h("td", { class: "action" }, h("button", { onclick: () => remove(row.slot) }, t("web.remove"))));
  });

  out.push(h("div", { class: "scroll" }, h("table", { class: "fixed" },
    colgroup("c-index", "c-offset", null, null, "c-value", "c-action"),
    h("thead", {}, h("tr", {},
      h("th", { class: "num" }, t("web.slot")), h("th", {}, t("web.col.offset")),
      h("th", {}, t("shard.field.type")), h("th", {}, t("shard.field.nature")),
      h("th", { class: "num" }, t("shard.field.strength")), h("th", {}))),
    h("tbody", {}, rows))));
  container.replaceChildren(...out);
}

// --- actions ---

async function openFile(file) {
  if (state.session) {
    if (state.session.modified && !confirm(t("web.confirm_close"))) return;
    api("DELETE", sessionPath()).catch(() => {});
  }
  $("main").replaceChildren(h("p", { class: "start" }, t("web.loading")));
  const form = new FormData();
  form.append("file", file);
  const summary = await run(() => json("POST", "/api/sessions", form));
  if (summary === FAILED) {
    render();
    return;
  }
  state.tab = "overview";
  setSession(summary);
}

async function download() {
  const res = await run(() => api("GET", sessionPath("/download")));
  if (res === FAILED) return;
  const url = URL.createObjectURL(await res.blob());
  const a = h("a", { href: url, download: state.session.filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function closeSession() {
  if (state.session.modified && !confirm(t("web.confirm_close"))) return;
  await run(() => api("DELETE", sessionPath()));
  setSession(null);
}

async function changeLang(lang) {
  const meta = await run(() => loadMeta(lang));
  if (meta === FAILED) return;
  prefs.set("lang", lang);
  renderChrome();
  render();
}

function setShowHidden(on) {
  state.showHidden = on;
  render();
}

function setForce(on) {
  state.force = on;
  $("force-warning").classList.toggle("on", on);
  render();
}

async function init() {
  try {
    await loadMeta(prefs.get("lang"));
  } catch {
    await loadMeta(null); // stored language no longer exists
  }
  $("open").addEventListener("change", (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (file) openFile(file);
  });
  $("download").addEventListener("click", download);
  $("close").addEventListener("click", closeSession);
  $("lang").addEventListener("change", (e) => changeLang(e.target.value));
  $("show-hidden").addEventListener("change", (e) => setShowHidden(e.target.checked));
  $("force").addEventListener("change", (e) => setForce(e.target.checked));
  window.addEventListener("beforeunload", (e) => {
    if (state.session && state.session.modified) e.preventDefault();
  });

  const sid = tabStore.get("session");
  if (sid) {
    try {
      state.session = await json("GET", `/api/sessions/${encodeURIComponent(sid)}`);
    } catch {
      tabStore.set("session", null);
    }
  }
  renderChrome();
  render();
}

init();
