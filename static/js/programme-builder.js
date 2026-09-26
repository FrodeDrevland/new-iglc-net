/* The programme builder (templates/programme/builder.html, apps/programme/builder.py).
   A day as a grid of rooms by time. Sessions are drawn, moved and resized with the pointer (15-minute
   steps); papers and contributions are dragged into them. Every change is sent to the server at once,
   which checks it and answers with the new state of the day, drawn again from scratch. */
(function () {
  "use strict";
  const cfg = JSON.parse(document.getElementById("builder-config").textContent);
  const PX = 1.6, STEP = 15;
  const $ = id => document.getElementById(id);
  const grid = $("b-grid"), poolBox = $("b-pool"), panel = $("b-panel"), statusBox = $("b-status");
  let S = null, day = cfg.day, open = null, poolTab = "papers", poolFilter = "", poolSearch = "";

  const esc = text => String(text == null ? "" : text).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const mins = t => { const [h, m] = t.split(":").map(Number); return h * 60 + m; };
  const hm = n => String(Math.floor(n / 60)).padStart(2, "0") + ":" + String(n % 60).padStart(2, "0");
  const snap = n => Math.round(n / STEP) * STEP;
  const part = id => S.parts.find(p => p.id === id) || {};
  const room = id => S.rooms.find(r => r.id === id);
  const editableParts = () => S.parts.filter(p => p.editable);
  // A day belongs to a part (the industry day, the academic conference ...), sometimes two side by side.
  const dayParts = () => S.parts.filter(p => S.day_parts.includes(p.id));
  const editableDayParts = () => dayParts().filter(p => p.editable);
  const KIND_FOR_PART = {industry: "industry", workshop: "workshop", phd: "other", academic: "papers", other: "other"};

  function say(text, bad) { statusBox.textContent = text || ""; statusBox.classList.toggle("bad", !!bad); }

  async function load(newDay) {
    day = newDay || day;
    const response = await fetch(cfg.url + "?format=json&day=" + day, {credentials: "same-origin"});
    S = await response.json();
    history.replaceState(null, "", cfg.url + "?day=" + S.day);
    render();
  }

  async function send(data) {
    say("Saving…");
    try {
      const response = await fetch(cfg.url + "?day=" + day, {method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": cfg.csrf}, body: JSON.stringify(data)});
      const answer = await response.json();
      if (!response.ok) { say(answer.error || "Not saved.", true); render(); return false; }
      S = answer;
      render();
      say(answer.note || "Saved.");
      return true;
    } catch (e) {
      say("The connection failed; nothing was saved. Reload the page.", true);
      return false;
    }
  }

  function render() {
    renderDays();
    renderGrid();
    if (open && S.sessions.some(s => s.id === open)) renderPanel(open); else closePanel();
    renderPool();
    $("b-room").hidden = !S.can_rooms;
  }

  // ------------------------------------------------------------ days
  function renderDays() {
    $("b-days").innerHTML = S.days.map(d =>
      `<button type="button" class="b-day${d.date === S.day ? " current" : ""}" data-day="${d.date}"${d.date === S.day ? ' aria-current="date"' : ""}>${esc(d.label)}${d.count ? ` <span class="b-count">${d.count}</span>` : ""}
        <span class="b-day-parts">${d.parts.map(id => { const p = part(id); return `<span class="b-day-part" style="--part:${esc(p.colour)}">${esc(p.name)}</span>`; }).join("")}</span></button>`).join("");
    const box = $("b-dayparts");
    box.innerHTML = S.can_days
      ? `<span class="b-dayparts-label">This day belongs to</span> ${S.parts.map(p => `<label class="b-daypart" style="--part:${esc(p.colour)}"><input type="checkbox" value="${p.id}"${S.day_parts.includes(p.id) ? " checked" : ""}> ${esc(p.name)}</label>`).join("")}`
      : `<span class="b-dayparts-label">This day belongs to</span> ${dayParts().map(p => `<strong class="b-daypart" style="--part:${esc(p.colour)}">${esc(p.name)}</strong>`).join(" and ")}${editableDayParts().length ? "" : " – you can look, but not change it"}`;
    const copyTo = $("b-copy-to");
    if (copyTo) copyTo.innerHTML = S.days.filter(d => d.date !== S.day).map(d => `<option value="${d.date}">${esc(d.label)}</option>`).join("");
  }
  $("b-lanes").addEventListener("click", e => {
    const b = e.target.closest("[data-lanes]");
    if (b) send({action: "lanes", count: Number(b.dataset.lanes)});
  });
  grid.addEventListener("change", e => {
    const select = e.target.closest("[data-lane-room]");
    if (select && select.value) send({action: "lane_room", lane: Number(select.dataset.laneRoom), location: Number(select.value)});
  });
  $("b-dayparts").addEventListener("change", e => {
    if (!e.target.matches("input[type=checkbox]")) return;
    const parts = [...$("b-dayparts").querySelectorAll("input:checked")].map(i => Number(i.value));
    send({action: "day_parts", parts});
  });
  $("b-days").addEventListener("click", e => { const b = e.target.closest("[data-day]"); if (b) { open = null; load(b.dataset.day); } });

  // ------------------------------------------------------------ the grid
  function layout() {
    // Blocks in the same room that overlap share the room's width.
    const placed = [];
    for (const s of S.sessions) {
      const index = s.spans || !s.lane ? -1 : s.lane - 1;
      placed.push({s, index: index, lane: 0, lanes: 1});
    }
    for (const a of placed) {
      if (a.index < 0) continue;
      const clash = placed.filter(b => b !== a && b.index === a.index && mins(b.s.start) < mins(a.s.end) && mins(a.s.start) < mins(b.s.end));
      if (clash.length) { a.lanes = clash.length + 1; a.lane = placed.filter(b => b.index === a.index && clash.includes(b) && placed.indexOf(b) < placed.indexOf(a)).length; }
    }
    return placed;
  }

  function renderGrid() {
    const n = Math.max(S.lanes, 1);
    const start = mins(S.range.start), end = mins(S.range.end), height = (end - start) * PX;
    let hours = "", lines = "";
    for (let t = start; t <= end; t += 60) {
      hours += `<div class="bg-hour" style="top:${(t - start) * PX}px">${hm(t)}</div>`;
      lines += `<div class="bg-line" style="top:${(t - start) * PX}px"></div>`;
      if (t + 30 < end) lines += `<div class="bg-line half" style="top:${(t + 30 - start) * PX}px"></div>`;
    }
    const cols = Array.from({length: n}, (_, i) => `<div class="bg-col" data-lane="${i + 1}" style="left:${i * 100 / n}%;width:${100 / n}%"></div>`).join("");
    const blocks = layout().map(({s, index, lane, lanes}) => {
      const p = part(s.part);
      const takes = s.kind !== "break" && s.kind !== "meal";
      const top = (mins(s.start) - start) * PX, h = Math.max((mins(s.end) - mins(s.start)) * PX, 18);
      const left = index < 0 ? 0 : (index + lane / lanes) * 100 / n, width = index < 0 ? 100 : 100 / n / lanes;
      const where = s.room ? ` · ${esc(s.room)}` : (takes || s.kind === "social" ? ' · <span class="bb-noroom">no room yet</span>' : "");
      const chairs = s.people.filter(x => x.role === "chair" || x.role === "co_chair").map(x => esc(x.name)).join(", ");
      const items = s.items.map(i => `<li draggable="${s.editable}" data-entry="i${i.id}" data-item="${i.id}" title="${esc(i.sub)}"><span class="bi-label">${esc(i.label)}</span> ${esc(i.title)}</li>`).join("");
      return `<div class="bb kind-${s.kind}${s.editable ? "" : " locked"}${s.spans ? " spans" : ""}${s.problems.length ? " flagged" : ""}${s.cancelled ? " cancelled" : ""}${open === s.id ? " selected" : ""}"
          data-id="${s.id}" style="top:${top}px;height:${h}px;left:${left}%;width:${width}%;--part:${esc(p.colour || "#888")}">
        <div class="bb-head"><span class="bb-time">${s.start}–${s.end}</span> ${s.code ? `<strong>${esc(s.code)}</strong> ` : ""}${esc(s.display)}</div>
        <div class="bb-meta">${esc(s.kind_label)}${s.plenary ? " · plenary" : ""}${where}${chairs ? " · " + chairs : ""}${s.items.length ? ` · ${s.items.length}` : ""}</div>
        ${takes ? `<ol class="bb-items" data-session="${s.id}">${items}</ol>` : ""}
        ${s.problems.length ? `<span class="bb-flag" title="${esc(s.problems.join("\n"))}">!</span>` : ""}
        ${s.editable ? '<div class="bb-resize" title="Drag to change the end"></div>' : ""}
      </div>`;
    }).join("");
    grid.style.setProperty("--rooms", n);
    const canRoom = editableDayParts().length && S.rooms.length;
    const heads = Array.from({length: n}, (_, i) => `<div class="bg-room">Parallel ${i + 1}
      ${canRoom ? `<select class="bg-lane-room" data-lane-room="${i + 1}" aria-label="Give a room to the sessions in parallel ${i + 1} that have none">
        <option value="">Give a room…</option>${S.rooms.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("")}</select>` : ""}</div>`).join("");
    grid.innerHTML = `
      <div class="bg-head"><div class="bg-gutter"></div><div class="bg-rooms">${heads}</div></div>
      <div class="bg-body" style="height:${height}px">
        <div class="bg-times">${hours}</div>
        <div class="bg-cols" id="bg-cols" data-start="${start}">${lines}${cols}${blocks}</div>
      </div>`;
    const lanes = $("b-lanes");
    lanes.innerHTML = editableDayParts().length ? `<span class="b-dayparts-label">Parallel lanes</span>
      <button type="button" class="button button-small button-secondary" data-lanes="${n - 1}" aria-label="One lane fewer"${n <= 1 ? " disabled" : ""}>−</button>
      <strong>${n}</strong>
      <button type="button" class="button button-small button-secondary" data-lanes="${n + 1}" aria-label="One lane more">+</button>
      <span class="small muted">how many sessions can run at the same time; rooms are given to the sessions</span>` : "";
  }

  // Drawing a new session, and moving and resizing sessions, with the pointer.
  let gesture = null;
  grid.addEventListener("pointerdown", e => {
    if (e.button !== 0 || !S) return;
    const cols = $("bg-cols");
    if (!cols) return;
    const block = e.target.closest(".bb");
    if (e.target.closest(".bb-items li")) return;  // an item: dragged with drag and drop
    const box = cols.getBoundingClientRect(), start = Number(cols.dataset.start);
    const at = y => start + snap((y - box.top) / PX);
    if (block) {
      const s = S.sessions.find(x => x.id === Number(block.dataset.id));
      if (!s) return;
      gesture = {kind: e.target.closest(".bb-resize") ? "resize" : "move", s, block, x0: e.clientX, y0: e.clientY, moved: false,
                 top0: parseFloat(block.style.top), height0: parseFloat(block.style.height), box};
      if (!s.editable) gesture.kind = "view";
    } else if (e.target.closest(".bg-col") && editableDayParts().length) {
      const col = e.target.closest(".bg-col");
      const t = at(e.clientY);
      const ghost = document.createElement("div");
      ghost.className = "bb ghost";
      ghost.style.cssText = `top:${(t - start) * PX}px;height:${STEP * PX}px;left:${col.style.left};width:${col.style.width}`;
      cols.appendChild(ghost);
      gesture = {kind: "draw", lane: Number(col.dataset.lane), t0: t, t1: t + STEP, ghost, start, at, moved: false};
    } else return;
    grid.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  grid.addEventListener("pointermove", e => {
    if (!gesture) return;
    const g = gesture;
    if (g.kind === "draw") {
      const t = g.at(e.clientY);
      g.t1 = Math.max(t, g.t0 + STEP);
      g.moved = g.moved || t !== g.t0;
      g.ghost.style.height = (g.t1 - g.t0) * PX + "px";
      g.ghost.textContent = hm(g.t0) + "–" + hm(g.t1);
      return;
    }
    if (g.kind === "view") return;
    const dy = e.clientY - g.y0, dx = e.clientX - g.x0;
    if (!g.moved && Math.abs(dy) < 4 && Math.abs(dx) < 4) return;
    g.moved = true;
    g.block.classList.add("dragging");
    const delta = snap(dy / PX);
    if (g.kind === "resize") {
      g.newEnd = Math.max(mins(g.s.end) + delta, mins(g.s.start) + STEP);
      g.block.style.height = (g.newEnd - mins(g.s.start)) * PX + "px";
      g.block.querySelector(".bb-time").textContent = g.s.start + "–" + hm(g.newEnd);
    } else {
      g.delta = delta;
      g.block.style.top = g.top0 + delta * PX + "px";
      if (!g.s.spans) {
        const n = Math.max(S.lanes, 1);
        const index = Math.min(n - 1, Math.max(0, Math.floor((e.clientX - g.box.left) / (g.box.width / n))));
        g.lane = index + 1;
        g.block.style.left = index * 100 / n + "%";
        g.block.style.width = 100 / n + "%";
      }
      g.block.querySelector(".bb-time").textContent = hm(mins(g.s.start) + delta) + "–" + hm(mins(g.s.end) + delta);
    }
  });
  grid.addEventListener("pointerup", () => {
    const g = gesture;
    gesture = null;
    if (!g) return;
    if (g.kind === "draw") {
      g.ghost.remove();
      openCreate(g.lane, hm(g.t0), hm(g.moved ? g.t1 : g.t0 + 60));
    } else if (!g.moved) {
      openPanel(g.s.id);
    } else if (g.kind === "resize") {
      send({action: "update", id: g.s.id, end: hm(g.newEnd)});
    } else if (g.kind === "move") {
      const data = {action: "update", id: g.s.id, start: hm(mins(g.s.start) + (g.delta || 0)), end: hm(mins(g.s.end) + (g.delta || 0))};
      if (g.lane && g.lane !== g.s.lane) data.lane = g.lane;
      send(data);
    }
  });
  grid.addEventListener("pointercancel", () => { if (gesture && gesture.ghost) gesture.ghost.remove(); gesture = null; render(); });

  // ------------------------------------------------------------ a new session
  const dialog = $("b-create"), createForm = $("b-create-form");
  function openCreate(lane, from, to) {
    const f = createForm.elements;
    f.kind.innerHTML = S.kinds.map(([k, label]) => `<option value="${k}">${esc(label)}</option>`).join("");
    const parts = editableDayParts();
    f.part.innerHTML = parts.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
    createForm.querySelector("[data-part-choice]").hidden = parts.length < 2;
    f.location.innerHTML = '<option value="">none yet</option>' + S.rooms.map(r => `<option value="${r.id}">${esc(r.name)}</option>`).join("");
    f.location.value = "";
    f.start.value = from; f.end.value = to; f.title.value = "";
    f.kind.value = KIND_FOR_PART[(parts[0] || {}).kind] || "papers";
    createForm.querySelector("[data-room-name]").textContent = "parallel " + lane;
    createForm.dataset.lane = lane;
    f.mode.value = "lane";
    dialog.showModal();
    f.kind.focus();
  }
  $("b-create-kind").addEventListener("change", e => {
    if (["break", "meal"].includes(e.target.value)) createForm.elements.mode.value = "all";
    if (e.target.value === "keynote") createForm.elements.mode.value = "all";
  });
  dialog.addEventListener("close", () => {
    if (dialog.returnValue !== "ok") return;
    const f = createForm.elements;
    send({action: "create", part: Number(f.part.value), kind: f.kind.value, title: f.title.value, start: f.start.value,
          end: f.end.value, mode: f.mode.value, location: f.location.value || null, lane: Number(createForm.dataset.lane)});
  });

  // ------------------------------------------------------------ papers and contributions: drag and drop
  let dragged = null;
  document.addEventListener("dragstart", e => {
    const li = e.target.closest("li[data-entry]");
    if (!li || li.getAttribute("draggable") !== "true") return;
    dragged = li.dataset.entry;
    li.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragged);
  });
  document.addEventListener("dragend", e => { const li = e.target.closest && e.target.closest("li"); if (li) li.classList.remove("dragging"); dragged = null; showGhost(null); document.querySelectorAll(".drop").forEach(x => x.classList.remove("drop")); });
  function target(e) {
    const block = e.target.closest(".bb");
    if (block) {
      const s = S.sessions.find(x => x.id === Number(block.dataset.id));
      if (!s || !s.editable || s.kind === "break" || s.kind === "meal") return null;
      return {block, s};
    }
    if (e.target.closest("#b-pool") && dragged && dragged[0] === "i") return {pool: true};
    // A contribution dropped where there is no session gets a session as long as the contribution.
    const col = e.target.closest(".bg-col");
    if (col && dragged && dragged[0] === "c" && editableDayParts().length) {
      const c = S.pool.contributions.find(x => x.entry === dragged);
      if (!c) return null;
      const cols = $("bg-cols"), box = cols.getBoundingClientRect(), start = Number(cols.dataset.start);
      const t = start + Math.floor((e.clientY - box.top) / PX / STEP) * STEP;
      return {col, lane: Number(col.dataset.lane), start: t, minutes: c.minutes || 60,
              everyone: ["welcome", "keynote", "awards", "closing"].includes(c.kind)};
    }
    return null;
  }
  function showGhost(t) {
    let ghost = $("b-dropghost");
    if (!t || !t.col) { if (ghost) ghost.remove(); return; }
    if (!ghost) { ghost = document.createElement("div"); ghost.id = "b-dropghost"; ghost.className = "bb ghost"; $("bg-cols").appendChild(ghost); }
    const start = Number($("bg-cols").dataset.start);
    ghost.style.cssText = `top:${(t.start - start) * PX}px;height:${t.minutes * PX}px;` +
      (t.everyone ? "left:0;width:100%" : `left:${t.col.style.left};width:${t.col.style.width}`);
    ghost.textContent = `${hm(t.start)}–${hm(t.start + t.minutes)} new session`;
  }
  document.addEventListener("dragover", e => {
    if (!dragged) return;
    const t = target(e);
    document.querySelectorAll(".drop").forEach(x => x.classList.remove("drop"));
    showGhost(t);
    if (!t) return;
    e.preventDefault();
    if (!t.col) (t.block || poolBox).classList.add("drop");
  });
  document.addEventListener("drop", e => {
    if (!dragged) return;
    const t = target(e);
    if (!t) return;
    e.preventDefault();
    const entry = dragged;
    dragged = null;
    showGhost(null);
    if (t.pool) { send({action: "unplace", item: Number(entry.slice(1))}); return; }
    if (t.col) { send({action: "new_session", entry, start: hm(t.start), lane: t.lane}); return; }
    const items = [...t.block.querySelectorAll(".bb-items > li")].filter(li => li.dataset.entry !== entry);
    let index = items.findIndex(li => { const box = li.getBoundingClientRect(); return e.clientY < box.top + box.height / 2; });
    if (index < 0) index = items.length;
    send({action: "place", session: t.s.id, entry, index});
  });

  // ------------------------------------------------------------ the list of papers and contributions
  function renderPool() {
    if (!panel.hidden) { poolBox.hidden = true; return; }
    poolBox.hidden = false;
    const papers = S.pool.papers, contributions = S.pool.contributions, canDrag = editableParts().length > 0;
    let list = poolTab === "papers" ? papers : contributions;
    if (poolFilter) list = list.filter(x => String(poolTab === "papers" ? x.track_id : x.part) === poolFilter);
    if (poolSearch) list = list.filter(x => (x.label + " " + x.title + " " + x.sub).toLowerCase().includes(poolSearch.toLowerCase()));
    const filter = poolTab === "papers"
      ? `<option value="">All tracks</option>${S.tracks.map(t => `<option value="${t.id}"${String(t.id) === poolFilter ? " selected" : ""}>${esc(t.title)}</option>`).join("")}`
      : `<option value="">All parts</option>${S.parts.map(p => `<option value="${p.id}"${String(p.id) === poolFilter ? " selected" : ""}>${esc(p.name)}</option>`).join("")}`;
    poolBox.innerHTML = `
      <div class="bp-tabs" role="tablist">
        <button type="button" role="tab" data-tab="papers" aria-selected="${poolTab === "papers"}">Papers (${papers.length})</button>
        <button type="button" role="tab" data-tab="contributions" aria-selected="${poolTab === "contributions"}">Contributions (${contributions.length})</button>
      </div>
      <p class="bp-hint small muted">${poolTab === "papers" ? "Accepted papers not in a session yet." : "Welcomes, keynotes, talks, workshops and panels not in a session yet."} Drag them into a session; drag items here to take them out.${poolTab === "contributions" ? " Dropped where there is no session, a contribution gets a session as long as it is." : ""}</p>
      <div class="bp-filters"><select data-filter aria-label="Filter">${filter}</select> <input type="search" data-search placeholder="Search" value="${esc(poolSearch)}" aria-label="Search"></div>
      <ul class="bp-list">${list.map(x => `<li draggable="${canDrag}" data-entry="${x.entry}"><span class="bi-label">${esc(x.label)}</span> ${esc(x.title)}${x.minutes ? ` <span class="muted small">(${x.minutes} min)</span>` : ""}${x.sub ? `<br><span class="muted small">${esc(x.sub)}</span>` : ""}</li>`).join("") || '<li class="bp-none">None.</li>'}</ul>
      ${poolTab === "contributions" && canDrag ? `
      <form class="bp-add" data-add>
        <h3>Add a contribution</h3>
        <select name="kind" aria-label="Kind">${S.contribution_kinds.map(([k, label]) => `<option value="${k}">${esc(label)}</option>`).join("")}</select>
        <select name="part" aria-label="Part">${editableParts().map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select>
        <input type="text" name="title" placeholder="Title, e.g. Welcome by the dean" required>
        <input type="text" name="speakers" placeholder="Speaker(s), e.g. Ann Smith (TUM)">
        <label class="small">Minutes <input type="number" name="minutes" min="5" step="5" style="width:4.5rem"></label>
        <button class="button button-small" type="submit">Add</button>
        <a class="small" href="${cfg.contributions_url}">All contributions, and from Speakers</a>
      </form>` : ""}`;
  }
  poolBox.addEventListener("click", e => {
    const tab = e.target.closest("[data-tab]");
    if (tab) { poolTab = tab.dataset.tab; poolFilter = ""; renderPool(); }
  });
  poolBox.addEventListener("change", e => { if (e.target.matches("[data-filter]")) { poolFilter = e.target.value; renderPool(); } });
  poolBox.addEventListener("input", e => {
    if (!e.target.matches("[data-search]")) return;
    poolSearch = e.target.value;
    const at = e.target.selectionStart;
    renderPool();
    const input = poolBox.querySelector("[data-search]");
    input.focus(); input.setSelectionRange(at, at);
  });
  poolBox.addEventListener("submit", e => {
    if (!e.target.matches("[data-add]")) return;
    e.preventDefault();
    const f = e.target.elements;
    send({action: "contribution", kind: f.kind.value, part: Number(f.part.value), title: f.title.value, speakers: f.speakers.value, minutes: f.minutes.value});
  });

  // ------------------------------------------------------------ a session's details
  function openPanel(id) { open = id; renderGrid(); renderPanel(id); poolBox.hidden = true; }
  function closePanel() { open = null; panel.hidden = true; panel.innerHTML = ""; }
  function renderPanel(id) {
    const s = S.sessions.find(x => x.id === id);
    if (!s) return closePanel();
    panel.hidden = false;
    const ro = s.editable ? "" : " disabled";
    const options = (list, value) => list.map(([k, label]) => `<option value="${k}"${String(k) === String(value) ? " selected" : ""}>${esc(label)}</option>`).join("");
    const parts = s.editable ? editableDayParts() : dayParts();
    panel.innerHTML = `
      <form class="bpanel" data-panel="${s.id}">
        <p class="bpanel-top"><button type="button" class="button button-small button-secondary" data-close>Back to the list</button></p>
        <h2>${esc(s.code ? s.code + " " : "")}${esc(s.display)}</h2>
        ${s.editable ? "" : '<p class="small muted">This session belongs to a part you do not edit.</p>'}
        ${s.problems.map(p => `<p class="bpanel-problem">${esc(p)}</p>`).join("")}
        <div class="b-form">
          <label class="wide">Title <input name="title" value="${esc(s.title)}"${ro}></label>
          <label>Code <input name="code" value="${esc(s.code)}" size="6"${ro}></label>
          <label>Kind <select name="kind"${ro}>${options(S.kinds, s.kind)}</select></label>
          <label${parts.length < 2 ? " hidden" : ""}>Part <select name="part"${ro}>${options(parts.map(p => [p.id, p.name]), s.part)}</select></label>
          <label>Day <select name="date"${ro}>${options(S.days.map(d => [d.date, d.label]), S.day)}</select></label>
          <label>From <input type="time" step="900" name="start" value="${s.start}"${ro}></label>
          <label>To <input type="time" step="900" name="end" value="${s.end}"${ro}></label>
          <label>Room <select name="location"${ro}><option value="">none</option>${options(S.rooms.map(r => [r.id, r.name]), s.location)}</select></label>
          <label class="check"><input type="checkbox" name="plenary"${s.plenary ? " checked" : ""}${ro}> Plenary (across all rooms)</label>
          <label>Track <select name="track"${ro}><option value="">none</option>${options(S.tracks.map(t => [t.id, t.title]), s.track)}</select></label>
          <label class="wide">Notes <textarea name="notes" rows="2"${ro}>${esc(s.notes)}</textarea></label>
          <label class="check"><input type="checkbox" name="cancelled"${s.cancelled ? " checked" : ""}${ro}> Cancelled</label>
          <label class="wide">Late change <input name="change_note" value="${esc(s.change_note)}" placeholder="e.g. Moved to Room 103"${ro}></label>
        </div>
        <h3>People</h3>
        <table class="bpanel-people"><tbody>${s.people.map(p => personRow(p, ro)).join("")}</tbody></table>
        ${s.editable ? '<p><button type="button" class="button button-small button-secondary" data-add-person>Add a person</button></p>' : ""}
        <h3>Papers and contributions (${s.items.length})</h3>
        <ol class="bpanel-items">${s.items.map(i => `<li data-item="${i.id}"><span class="bi-label">${esc(i.label)}</span> ${esc(i.title)}
          ${i.sub ? `<br><span class="muted small">${esc(i.sub)}</span>` : ""}
          ${i.paper ? `<br><label class="small">Presenter <input data-field="presenter" value="${esc(i.presenter)}" list="authors-${i.id}"${ro}></label><datalist id="authors-${i.id}">${i.sub.split(", ").map(n => `<option value="${esc(n)}">`).join("")}</datalist>` : ""}
          <label class="small">Minutes <input data-field="minutes" type="number" min="1" value="${i.minutes || ""}" style="width:4.5rem"${ro}></label>
          ${s.editable ? `<button type="button" class="linklike small" data-remove="${i.id}">take out</button>` : ""}</li>`).join("") || '<li class="muted">None yet: drag them in from the list.</li>'}</ol>
        ${s.editable ? `<p class="bpanel-buttons"><button class="button" type="submit">Save</button>
          <button type="button" class="button button-secondary no" data-delete>Delete the session</button>
          <a class="small" href="${cfg.session_url.replace("/0/", "/" + s.id + "/")}">Full form</a></p>` : ""}
      </form>`;
  }
  function personRow(p, ro) {
    return `<tr><td><select data-p="role"${ro}>${S.roles.map(([k, label]) => `<option value="${k}"${k === p.role ? " selected" : ""}>${esc(label)}</option>`).join("")}</select></td>
      <td><input data-p="name" value="${esc(p.name)}" placeholder="Name"${ro}></td>
      <td><input data-p="affiliation" value="${esc(p.affiliation)}" placeholder="Affiliation"${ro}></td>
      <td>${ro ? "" : '<button type="button" class="linklike" data-remove-person aria-label="Remove">×</button>'}</td></tr>`;
  }
  panel.addEventListener("click", e => {
    if (e.target.closest("[data-close]")) { closePanel(); renderGrid(); renderPool(); return; }
    if (e.target.closest("[data-add-person]")) { panel.querySelector(".bpanel-people tbody").insertAdjacentHTML("beforeend", personRow({role: "chair", name: "", affiliation: ""}, "")); return; }
    if (e.target.closest("[data-remove-person]")) { e.target.closest("tr").remove(); return; }
    const remove = e.target.closest("[data-remove]");
    if (remove) { send({action: "unplace", item: Number(remove.dataset.remove)}); return; }
    if (e.target.closest("[data-delete]") && confirm("Delete this session? Its papers go back to the list.")) {
      const id = open; open = null; send({action: "delete", id});
    }
  });
  panel.addEventListener("change", e => {
    const field = e.target.dataset.field;
    if (!field) return;
    send({action: "item", item: Number(e.target.closest("[data-item]").dataset.item), [field]: e.target.value});
  });
  panel.addEventListener("submit", e => {
    e.preventDefault();
    const f = e.target.elements;
    const people = [...panel.querySelectorAll(".bpanel-people tr")].map(tr => ({
      role: tr.querySelector('[data-p="role"]').value, name: tr.querySelector('[data-p="name"]').value,
      affiliation: tr.querySelector('[data-p="affiliation"]').value}));
    const data = {action: "update", id: open, title: f.title.value, code: f.code.value, kind: f.kind.value, part: Number(f.part.value),
      start: f.start.value, end: f.end.value, location: f.location.value || null, plenary: f.plenary.checked, track: f.track.value,
      notes: f.notes.value, cancelled: f.cancelled.checked, change_note: f.change_note.value, people};
    const moving = f.date.value !== S.day;
    if (moving) data.date = f.date.value;
    send(data).then(ok => { if (ok && moving) { load(f.date.value); } });
  });

  // ------------------------------------------------------------ the toolbar
  const copy = $("b-copy");
  if (copy) copy.addEventListener("submit", e => {
    e.preventDefault();
    const to = copy.elements.to.value;
    if (to) send({action: "copy_day", to, replace: copy.elements.replace.checked});
  });
  const renumber = $("b-renumber");
  if (renumber) renumber.addEventListener("click", () => {
    if (confirm("Give the parallel sessions codes by time slot (1A, 1B ...), in every part you edit? Codes typed by hand are replaced.")) send({action: "renumber"});
  });
  $("b-room").addEventListener("submit", e => {
    e.preventDefault();
    const name = e.target.elements.name.value.trim();
    if (name) send({action: "room", name}).then(ok => { if (ok) e.target.reset(); });
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !panel.hidden && !dialog.open) { closePanel(); renderGrid(); renderPool(); } });

  load();
})();
