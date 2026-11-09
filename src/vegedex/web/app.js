"use strict";
const $ = (s, el = document) => el.querySelector(s);
const MONTHS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const STATUS_LABEL = { grown: "Grown", growing: "Growing", failed: "Failed", wishlist: "Wishlist" };
const MOVE_LABEL = { growing: "Mark as growing", failed: "Mark as failed", grown: "Log harvest" };
const DATE_FIELD = { grown: "harvested", growing: "planted", failed: "failed", wishlist: "added" };

let state = { cards: [], counts: {}, categories: [], filter: "all", current: null };

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const no = (id) => "No. " + String(id).padStart(3, "0");

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 2600);
}

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  let body = {};
  try { body = await r.json(); } catch { /* non-JSON */ }
  if (!r.ok && !body.log) throw new Error(body.error || r.statusText);
  return body;
}

/* ---------- tabs ---------- */
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + name));
  if (name === "tree") $("#tree-img").src = "/api/tree.svg?t=" + Date.now();
  if (name === "timeline" && state.cards.length) renderTimeline();
  try { localStorage.setItem("vegedex-tab", name); } catch {}
}

/* ---------- cards ---------- */
async function loadCards() {
  const d = await api("/api/cards");
  Object.assign(state, { cards: d.cards, counts: d.counts, categories: d.categories });
  $("#vault").textContent = d.vault ? "Vault: " + d.vault : "Vault folder not found (check config.json)";
  renderStats(d.total);
  renderGrid();
  if ($("#tab-timeline").classList.contains("active")) renderTimeline();
}

function renderStats(total) {
  const bar = $("#bar"); bar.innerHTML = "";
  for (const s of ["grown", "growing", "failed", "wishlist"]) {
    const n = state.counts[s] || 0;
    if (n) bar.append(h("span", { class: "s-" + s, style: `width:${(100 * n) / total}%`, title: `${n} ${s}` }));
  }
  const f = $("#filters"); f.innerHTML = "";
  const opts = [["all", `All ${total}`]].concat(["grown", "growing", "failed", "wishlist"].map((s) => [s, `${STATUS_LABEL[s]} ${state.counts[s] || 0}`]));
  for (const [k, label] of opts) {
    f.append(h("button", { class: "chip" + (state.filter === k ? " active" : ""), onclick: () => { state.filter = k; renderStats(total); renderGrid(); } },
      k !== "all" ? h("span", { class: "dot s-" + k }) : null, label));
  }
}

function renderGrid() {
  const g = $("#grid"); g.innerHTML = "";
  const list = state.cards.filter((c) => state.filter === "all" || c.status === state.filter);
  for (const c of list) {
    const img = c.pdf ? h("img", { src: `/api/cards/${c.id}/preview.png?v=${c.pdf_version}`, alt: c.name, loading: "lazy" })
                      : h("div", { class: "placeholder" }, "Not rendered yet");
    g.append(h("button", { class: "tile", onclick: () => openDetail(c.id) },
      h("div", { class: "imgbox" }, img),
      h("div", { class: "cap" }, h("b", {}, c.name), h("span", { class: "muted" }, no(c.id)))));
  }
  if (!list.length) g.append(h("p", { class: "muted" }, "No cards here yet."));
}

/* ---------- detail ---------- */
const dlg = $("#detail");
$("#detail-close").onclick = () => dlg.close();
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
document.addEventListener("keydown", (e) => {
  if (!dlg.open || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
  const list = state.cards.filter((c) => state.filter === "all" || c.status === state.filter);
  const i = list.findIndex((c) => c.id === state.current);
  if (e.key === "ArrowRight" && i < list.length - 1) openDetail(list[i + 1].id);
  if (e.key === "ArrowLeft" && i > 0) openDetail(list[i - 1].id);
});

function openDetail(id, extra) {
  const c = state.cards.find((x) => x.id === id);
  if (!c) return;
  state.current = id;
  $("#detail-img").src = c.pdf ? `/api/cards/${c.id}/preview.png?v=${c.pdf_version}` : "";
  $("#detail-img").alt = c.name;
  const body = $("#detail-body"); body.innerHTML = "";
  const months = (m) => (m && m.length ? m.map((x) => MONTH_NAMES[x - 1]).join(", ") : "Unknown");
  const facts = [["Variety", c.variant], ["Latin", c.latin], ["Family", c.family], ["Category", c.category],
    ["Harvested", c.harvested], ["Planted", c.planted], ["Failed", c.failed], ["Added", c.added],
    ["Sow", months(c.sow_months)], ["Harvest", months(c.harvest_months)], ["Photo credit", c.photo_credit]].filter(([, v]) => v);
  body.append(
    h("div", {}, h("span", { class: "badge" }, h("span", { class: "dot s-" + c.status }), STATUS_LABEL[c.status]),
      h("h2", { style: "margin-top:10px;font-size:26px" }, c.name), h("div", { class: "muted" }, no(c.id))),
    h("dl", { class: "facts" }, facts.map(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])),
    h("div", { class: "actions" },
      c.pdf ? h("a", { class: "button", href: `/api/cards/${c.id}/pdf`, target: "_blank" }, "Open PDF") : null,
      c.moves.map((to) => h("button", { class: to === "failed" ? "danger" : "primary", onclick: () => moveForm(c, to) }, MOVE_LABEL[to])),
      h("button", { onclick: () => editCard(c) }, "Edit card"),
      h("button", { class: "ghost", onclick: (e) => reResearch(c, e.currentTarget) }, "Re-research with Mistral")),
    h("div", { id: "detail-extra" }),
    c.sources && c.sources.length ? h("div", { class: "sources" }, h("b", {}, "Sources"),
      h("ol", {}, c.sources.map((u) => h("li", {}, h("a", { href: u, target: "_blank", rel: "noopener" }, u))))) : null);
  if (extra) $("#detail-extra").append(extra);
  if (!dlg.open) dlg.showModal();
}

function moveForm(c, to) {
  const box = $("#detail-extra"); box.innerHTML = "";
  const f = h("form", { class: "move-form" },
    h("b", {}, `${MOVE_LABEL[to]}: ${STATUS_LABEL[c.status]} → ${STATUS_LABEL[to]}`),
    to === "grown" ? h("label", {}, "Harvest photo (required)", h("input", { type: "file", name: "photo", accept: ".jpg,.jpeg,.png,.webp", required: true })) : null,
    h("div", { class: "cols" },
      h("label", {}, to === "grown" ? "Harvested" : to === "failed" ? "Failed" : "Planted",
        h("input", { type: "month", name: "date" }), h("span", { class: "muted" }, to === "grown" ? "Default: date in the photo's file name, else this month" : "Default: this month")),
      to !== "failed" ? h("label", {}, "Variety (if now known)", h("input", { name: "variant", placeholder: c.variant })) : h("span")),
    h("div", { class: "row" }, h("button", { class: "primary", type: "submit" }, "Confirm"), h("button", { type: "button", class: "ghost", onclick: () => (box.innerHTML = "") }, "Cancel")));
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(f); fd.append("to", to);
    await runAction(box, f, () => api(`/api/cards/${c.id}/transition`, { method: "POST", body: fd }), c.id, `${c.name} is now ${to}.`);
  });
  box.append(f);
}

async function runAction(box, form, fn, id, okMsg) {
  form.querySelectorAll("button").forEach((b) => (b.disabled = true));
  const status = h("div", { class: "status" }, h("div", { class: "spinner" }), "Rendering card, family tree and gallery (about a minute)…");
  box.append(status);
  try {
    const r = await fn();
    status.remove();
    await loadCards();
    const out = logBlock(r);
    if (r.ok) { toast(okMsg); openDetail(r.id ?? id, out); }
    else box.append(h("div", { class: "status err" }, "Something failed: see the log."), out);
  } catch (err) {
    status.className = "status err"; status.textContent = err.message;
  } finally {
    form.querySelectorAll("button").forEach((b) => (b.disabled = false));
  }
}

function logBlock(r) {
  return h("div", { class: "log" },
    (r.notices || []).map((n) => h("div", { class: "notice" }, n.startsWith("STALE") ? n + " — move these notes into Family Tree/_to_delete/." : n + " — add the family's APG IV order to data/taxonomy.json.")),
    h("details", { open: !r.ok }, h("summary", {}, "Script output"), h("pre", {}, r.log || r.error || "")));
}

function editCard(c, draft) {
  const box = $("#detail-extra"); box.innerHTML = "";
  const merged = draft ? { ...c, ...draft.card } : c;
  box.append(editor(merged, {
    submitLabel: "Save and re-render",
    notes: draft && draft.notes,
    editPhoto: true,
    onSubmit: async (data, form, photo, removePhoto) => {
      const fd = new FormData();
      fd.append("card", JSON.stringify(data));
      if (photo) fd.append("photo", photo);
      if (removePhoto) fd.append("remove_photo", "1");
      await runAction(box, form, () => api(`/api/cards/${c.id}`, { method: "PUT", body: fd }), c.id, "Card saved.");
    },
    onCancel: () => (box.innerHTML = ""),
  }));
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function reResearch(c, btn) {
  const box = $("#detail-extra"); box.innerHTML = "";
  btn.disabled = true;
  const status = researchStatus(c.name); box.append(status);
  try {
    const d = await api("/api/research", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: c.name, variant: c.variant }) });
    if (d.error) throw new Error(d.error);
    editCard(c, d);
    $("#detail-extra").prepend(h("div", { class: "notice" }, "Mistral's draft is filled in below. Nothing is saved until you press Save."));
  } catch (err) {
    status.className = "status err"; status.textContent = "Research failed: " + err.message;
  } finally { btn.disabled = false; }
}

function researchStatus(name) {
  const s = h("div", { class: "status" }, h("div", { class: "spinner" }), h("span", {}, `Mistral is searching the web for ${name}…`));
  const steps = ["Searching RHS grow-your-own…", "Finding the Latin name and family…", "Looking for recipes…", "Drafting the card…"];
  let i = 0; const t = setInterval(() => { if (!s.isConnected) return clearInterval(t); s.lastChild.textContent = steps[Math.min(i++, steps.length - 1)]; }, 9000);
  return s;
}

/* ---------- shared card editor ---------- */
function monthPicker(selected, cls) {
  const sel = new Set(selected || []);
  const el = h("div", { class: "months " + cls });
  MONTHS.forEach((m, i) => el.append(h("button", { type: "button", class: sel.has(i + 1) ? "on" : "", title: MONTH_NAMES[i],
    onclick: (e) => e.currentTarget.classList.toggle("on") }, m)));
  el.value = () => [...el.children].map((b, i) => (b.classList.contains("on") ? i + 1 : 0)).filter(Boolean);
  return el;
}

function editor(c, { submitLabel, onSubmit, onCancel, notes, editPhoto }) {
  const lines = (a) => (a || []).join("\n");
  const sow = monthPicker(c.sow_months, "sow"), harv = monthPicker(c.harvest_months, "harvest");
  const focus = c.photo_focus || [0.5, 0.5];
  const dateKey = DATE_FIELD[c.status];
  const srcList = h("ol");
  const f = h("form", { class: "form" },
    h("fieldset", {}, h("legend", {}, "Name"),
      h("div", { class: "cols" }, h("label", {}, "Vegetable", h("input", { name: "name", value: c.name, required: true })),
        h("label", {}, "Variety", h("input", { name: "variant", value: c.variant || "Unknown" }))),
      h("div", { class: "cols" }, h("label", {}, "Latin name", h("input", { name: "latin", value: c.latin || "Unknown" })),
        h("label", {}, "Family", h("input", { name: "family", value: c.family || "Unknown" }))),
      h("div", { class: "cols" },
        h("label", {}, "Category", h("select", { name: "category" }, state.categories.map((k) => h("option", { value: k, selected: k === c.category }, k)))),
        dateKey ? h("label", {}, dateKey[0].toUpperCase() + dateKey.slice(1), h("input", { name: dateKey, value: c[dateKey] || "", placeholder: "e.g. Oct 2026" })) : h("span"))),
    h("fieldset", {}, h("legend", {}, "Growing"),
      h("label", {}, "Sow / plant months", sow),
      h("label", {}, "Planting window", h("input", { name: "planting_window", value: c.planting_window || "Unknown" })),
      h("label", {}, "Harvest months", harv),
      h("label", {}, "Harvest window", h("input", { name: "harvest_window", value: c.harvest_window || "Unknown" })),
      h("label", {}, "Special instructions (one per line, 2–3)", h("textarea", { name: "special_instructions", rows: 3 }, lines(c.special_instructions))),
      h("label", {}, "Recipes (dish names, one per line, 2–3)", h("textarea", { name: "recipes", rows: 3 }, lines(c.recipes)))),
    h("fieldset", { class: "sources" }, h("legend", {}, "Sources"),
      h("label", {}, "One URL per line; [n] in the text is the n-th line", h("textarea", { name: "sources", rows: 4, oninput: (e) => showSources(e.target.value) }, lines(c.sources))),
      srcList),
    c.photo || editPhoto ? h("fieldset", {}, h("legend", {}, "Photo"),
      editPhoto ? h("label", {}, c.status === "grown" ? "Replace harvest photo" : "Add or replace photo", h("input", { type: "file", name: "photo", accept: ".jpg,.jpeg,.png,.webp" })) : null,
      c.status !== "grown" ? h("label", {}, "Photo credit (if not yours)", h("input", { name: "photo_credit", value: c.photo_credit || "" })) : null,
      c.photo ? h("div", { class: "cols" },
        h("label", {}, "Focus left ↔ right", h("input", { type: "range", name: "fx", min: 0, max: 1, step: 0.01, value: focus[0] })),
        h("label", {}, "Focus top ↕ bottom", h("input", { type: "range", name: "fy", min: 0, max: 1, step: 0.01, value: focus[1] }))) : null,
      c.photo ? h("label", {}, "Zoom", h("input", { type: "range", name: "zoom", min: 1, max: 2.5, step: 0.05, value: c.photo_zoom || 1 })) : null,
      c.photo && c.status !== "grown" && editPhoto ? h("label", { style: "flex-direction:row;align-items:center;font-weight:400" }, h("input", { type: "checkbox", name: "remove_photo", style: "width:auto" }), "Remove the photo (back to the “?”)") : null) : null,
    notes ? h("details", {}, h("summary", {}, "Mistral's research notes"), h("pre", {}, notes)) : null,
    h("div", { class: "row" }, h("button", { class: "primary", type: "submit" }, submitLabel), onCancel ? h("button", { type: "button", class: "ghost", onclick: onCancel }, "Cancel") : null));

  function showSources(text) {
    srcList.innerHTML = "";
    text.split("\n").map((s) => s.trim()).filter(Boolean).forEach((u) => srcList.append(h("li", {}, h("a", { href: u, target: "_blank", rel: "noopener" }, u))));
  }
  showSources(lines(c.sources));

  f.addEventListener("submit", (e) => {
    e.preventDefault();
    const v = (n) => (f.elements[n] ? f.elements[n].value.trim() : undefined);
    const arr = (n) => v(n).split("\n").map((s) => s.trim()).filter(Boolean);
    const data = {
      name: v("name"), variant: v("variant") || "Unknown", latin: v("latin") || "Unknown", family: v("family") || "Unknown",
      category: v("category"), planting_window: v("planting_window") || "Unknown", harvest_window: v("harvest_window") || "Unknown",
      special_instructions: arr("special_instructions"), recipes: arr("recipes"), sources: arr("sources"),
      sow_months: sow.value(), harvest_months: harv.value(),
    };
    if (dateKey && f.elements[dateKey]) data[dateKey] = v(dateKey);
    if (f.elements.photo_credit) data.photo_credit = v("photo_credit");
    if (f.elements.fx) { data.photo_focus = [+v("fx"), +v("fy")]; data.photo_zoom = +v("zoom"); }
    const bad = citationProblems(data);
    if (bad.length && !confirm("Citation check:\n\n" + bad.join("\n") + "\n\nSave anyway?")) return;
    const photo = f.elements.photo && f.elements.photo.files[0];
    onSubmit(data, f, photo, f.elements.remove_photo && f.elements.remove_photo.checked);
  });
  return f;
}

function citationProblems(d) {
  const texts = [d.latin, d.family, d.planting_window, d.harvest_window, ...d.special_instructions, ...d.recipes];
  const out = [];
  for (const t of texts) {
    for (const m of t.matchAll(/\[(\d+)\]/g)) if (+m[1] < 1 || +m[1] > d.sources.length) out.push(`“${t}” cites [${m[1]}] but there are ${d.sources.length} sources`);
  }
  return out;
}

/* ---------- add ---------- */
const startForm = $("#add-start");
function syncAddForm() {
  const s = startForm.elements.status.value;
  $("#date-label").textContent = { wishlist: "Added", growing: "Planted", grown: "Harvested" }[s];
  $("#photo-hint").textContent = { wishlist: "(optional reference image, greyed out on the card)", growing: "(optional photo of the plant growing)", grown: "(required: your harvest photo)" }[s];
  startForm.elements.photo.required = s === "grown";
  $("#credit-field").style.display = s === "grown" ? "none" : "";
}
startForm.elements.status.addEventListener("change", syncAddForm);
syncAddForm();

startForm.addEventListener("submit", (e) => { e.preventDefault(); startAdd(true); });
$("#skip-research").addEventListener("click", () => { if (startForm.reportValidity()) startAdd(false); });

async function startAdd(withResearch) {
  const f = startForm.elements;
  const name = f.name.value.trim(), variant = f.variant.value.trim() || "Unknown", status = f.status.value;
  const box = $("#add-editor"), st = $("#research-status");
  box.innerHTML = ""; st.innerHTML = "";
  const existing = state.cards.filter((c) => c.name.toLowerCase() === name.toLowerCase());
  if (existing.length) st.append(h("div", { class: "notice" }, `Already in the Vegedex: ${existing.map((c) => `${c.name} (${no(c.id)}, ${c.status})`).join(", ")}. To change its status, open it from Cards instead.`));
  let draft = { card: {}, notes: null };
  if (withResearch) {
    $("#research-btn").disabled = true;
    const s = researchStatus(name); st.append(s);
    try {
      draft = await api("/api/research", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, variant }) });
      if (draft.error) throw new Error(draft.error);
      s.remove();
    } catch (err) {
      s.className = "status err"; s.textContent = "Research failed: " + err.message + " — you can still fill the card in by hand below.";
      draft = { card: {}, notes: null };
    } finally { $("#research-btn").disabled = false; }
  }
  const card = { name, variant, status, category: "Other", ...draft.card, photo_credit: f.photo_credit.value.trim() };
  card[DATE_FIELD[status]] = f.date.value ? monthLabel(f.date.value) : "";
  const photo = f.photo.files[0];
  box.append(h("h3", { style: "margin-top:20px" }, "Check the draft"), editor(card, {
    submitLabel: "Create card",
    notes: draft.notes,
    onSubmit: async (data, form) => {
      data.status = status;
      const fd = new FormData(); fd.append("card", JSON.stringify(data));
      if (photo) fd.append("photo", photo);
      form.querySelectorAll("button").forEach((b) => (b.disabled = true));
      const s = h("div", { class: "status" }, h("div", { class: "spinner" }), "Creating the card and rebuilding the family tree and gallery (about a minute)…"); box.append(s);
      try {
        const r = await api("/api/cards", { method: "POST", body: fd });
        s.remove();
        await loadCards();
        if (r.ok) {
          toast(`${data.name} added as ${no(r.id)}.`);
          startForm.reset(); syncAddForm(); box.innerHTML = ""; st.innerHTML = "";
          showTab("cards"); openDetail(r.id, logBlock(r));
        } else box.append(h("div", { class: "status err" }, "Rendering failed: see the log."), logBlock(r));
      } catch (err) { s.className = "status err"; s.textContent = err.message; }
      finally { form.querySelectorAll("button").forEach((b) => (b.disabled = false)); }
    },
  }));
}
function monthLabel(v) { const [y, m] = v.split("-"); return `${MONTH_NAMES[+m - 1]} ${y}`; }

/* ---------- timeline ---------- */
let tlFilter = "all";
$("#tl-sort").addEventListener("change", renderTimeline);

function timelineMonths() {
  // the next 12 months, starting with this one: [{m: 1-12, y: 2026}, ...]
  const now = new Date();
  return Array.from({ length: 12 }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    return { m: d.getMonth() + 1, y: d.getFullYear() };
  });
}

function renderTimeline() {
  const months = timelineMonths();
  const first = months[0], last = months[11];
  $("#tl-range").textContent = `${MONTH_NAMES[first.m - 1]} ${first.y} to ${MONTH_NAMES[last.m - 1]} ${last.y}`;

  // filters (same statuses as the Cards tab)
  const f = $("#tl-filters"); f.innerHTML = "";
  for (const k of ["all", "wishlist", "growing", "grown", "failed"]) {
    const n = k === "all" ? state.cards.length : state.counts[k] || 0;
    f.append(h("button", { class: "chip" + (tlFilter === k ? " active" : ""), onclick: () => { tlFilter = k; renderTimeline(); } },
      k !== "all" ? h("span", { class: "dot s-" + k }) : null, (k === "all" ? "All" : STATUS_LABEL[k]) + " " + n));
  }
  const cards = state.cards.filter((c) => tlFilter === "all" || c.status === tlFilter);

  // "sow soon": the next three months
  const soon = $("#tl-soon"); soon.innerHTML = "";
  months.slice(0, 3).forEach(({ m, y }, i) => {
    const list = cards.filter((c) => (c.sow_months || []).includes(m));
    const label = i === 0 ? "This month" : i === 1 ? "Next month" : "In two months";
    soon.append(h("div", { class: "soon-card" },
      h("h3", {}, label, " · ", h("b", {}, `${MONTH_NAMES[m - 1]} ${y}`)),
      list.length ? h("ul", {}, list.map((c) => h("li", {}, h("button", { onclick: () => openDetail(c.id), title: STATUS_LABEL[c.status] },
        h("span", { class: "dot s-" + c.status }), " ", c.name, c.variant && !c.variant.startsWith("Unknown") ? ` (${c.variant})` : ""))))
        : h("div", { class: "none" }, "Nothing to sow")));
  });

  // index (0-11) of the first upcoming sowing month, or 99 if none
  const nextSow = (c) => { const i = months.findIndex(({ m }) => (c.sow_months || []).includes(m)); return i < 0 ? 99 : i; };
  const sort = $("#tl-sort").value;
  const cmp = { next: (a, b) => nextSow(a) - nextSow(b) || a.name.localeCompare(b.name),
                name: (a, b) => a.name.localeCompare(b.name), id: (a, b) => a.id - b.id }[sort];
  const timed = cards.filter((c) => (c.sow_months || []).length || (c.harvest_months || []).length).sort(cmp);
  const untimed = cards.filter((c) => !timed.includes(c)).sort(cmp);

  const g = $("#tl-grid"); g.innerHTML = "";
  g.append(h("div", { class: "hd" }));
  months.forEach(({ m, y }, i) => g.append(h("div", { class: "hd" + (i === 0 ? " now" : "") }, MONTH_NAMES[m - 1],
    i === 0 || m === 1 ? h("small", {}, y) : h("small", {}, " "))));

  const bar = (set, kind) => months.map(({ m }, i) => {
    if (!set.has(m)) return h("i", { class: "off" });
    const prev = i > 0 && set.has(months[i - 1].m), next = i < 11 && set.has(months[i + 1].m);
    return h("i", { class: [kind, prev ? "" : "first", next ? "" : "last"].join(" ").trim(), title: `${kind === "sow" ? "Sow / plant" : "Harvest"}: ${MONTH_NAMES[m - 1]}` });
  });
  const row = (c) => {
    const sow = bar(new Set(c.sow_months || []), "sow"), harv = bar(new Set(c.harvest_months || []), "harvest");
    g.append(h("div", { class: "name" }, h("span", { class: "dot s-" + c.status, title: STATUS_LABEL[c.status] }),
      h("div", {}, h("button", { onclick: () => openDetail(c.id) }, c.name),
        c.variant && !c.variant.startsWith("Unknown") ? h("div", { class: "muted" }, c.variant) : null)));
    months.forEach((_, i) => g.append(h("div", { class: "cell" + (i === 0 ? " now" : "") }, sow[i], harv[i])));
  };
  timed.forEach(row);
  if (untimed.length) {
    g.append(h("div", { class: "group" }, "No sow or harvest months on the card yet"));
    untimed.forEach(row);
  }
  if (!cards.length) g.append(h("div", { class: "group" }, "No cards here."));
}

/* ---------- tools ---------- */
async function tool(btn, url, body, label) {
  const out = $("#tool-out"); out.innerHTML = "";
  btn.disabled = true;
  out.append(h("div", { class: "status" }, h("div", { class: "spinner" }), label));
  try {
    const r = await api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    out.innerHTML = ""; out.append(logBlock({ ...r, ok: true }));
    $("details", out).open = true;
    await loadCards();
    return r;
  } catch (err) { out.innerHTML = ""; out.append(h("div", { class: "status err" }, err.message)); }
  finally { btn.disabled = false; }
}
$("#rebuild").onclick = (e) => tool(e.currentTarget, "/api/rebuild", {}, "Rebuilding…").then(() => toast("Gallery and family tree rebuilt."));
$("#reshuffle-dry").onclick = async (e) => {
  const r = await tool(e.currentTarget, "/api/reshuffle", { dry_run: true }, "Working out the new order…");
  if (r && r.log && !/Nothing to do/.test(r.log)) {
    const b = h("button", { class: "primary", onclick: async (ev) => {
      if (!confirm("Renumber the cards and rename their PDFs in the vault?")) return;
      await tool(ev.currentTarget, "/api/reshuffle", { dry_run: false }, "Reshuffling and re-rendering…"); toast("Reshuffled.");
    } }, "Apply reshuffle");
    $("#tool-out").append(h("div", { class: "row", style: "margin-top:12px" }, b));
  }
};

/* ---------- start ---------- */
let saved = "cards"; try { saved = localStorage.getItem("vegedex-tab") || "cards"; } catch {}
showTab(saved);
loadCards().catch((e) => { $("#grid").append(h("div", { class: "status err" }, "Couldn't load cards: " + e.message)); });
