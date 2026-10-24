/* =========================================================================
   MESA — mesa.js v25
   Performance:
     - renderList() usa fragment + Map de cache (reaproveita <li> existentes)
     - KPIs e filtro calculados em uma única passada por renderList()
     - loadBriefing cancelável via AbortController (evita render fora de ordem)
     - Busca com debounce curto (80ms) e filtro síncrono
   Filtro:
     - 'open' dos KPIs mapeia para 'progress'; 'doubts' e 'attention' → 'pending'
     - applyFilter sempre parte de `state.briefings`, nunca de `filtered`
   ========================================================================= */
(function () {
  "use strict";

  const root = document.getElementById("msPage");
  if (!root) return;

  const CSRF_COOKIE = "csrftoken";
  const STATUS_LABEL = {
    progress: "Em andamento",
    pending: "Pendências",
    done: "Concluído",
    waiting: "Aguardando",
  };
  const FILTER_MAP = {
    all: () => true,
    progress: (b) => b._derived === "progress",
    pending: (b) => b._derived === "pending",
    done: (b) => b._derived === "done",
  };

  const state = {
    briefings: [],
    filtered: [],
    activeId: null,
    filter: "all",
    query: "",
    detail: null,
    notes: [],
    events: [],
    client: null,
    activeTab: "summary",
    listCache: new Map(),      // id → <li> (reaproveitamento)
    abortDetail: null,          // AbortController do loadBriefing corrente
  };

  const el = {
    greeting: document.getElementById("msGreeting"),
    greetingIcon: document.getElementById("msGreetingIcon"),
    kpis: document.getElementById("msKpis"),
    kpiDone: document.getElementById("msKpiDone"),
    kpiOpen: document.getElementById("msKpiOpen"),
    kpiDoubts: document.getElementById("msKpiDoubts"),
    kpiAttention: document.getElementById("msKpiAttention"),
    list: document.getElementById("msBriefingsList"),
    listTpl: document.getElementById("msBriefItemTpl"),
    search: document.getElementById("msBriefingsSearch"),
    crumbCurrent: document.getElementById("msCrumbCurrent"),
    detailTitle: document.getElementById("msDetailTitle"),
    detailStatus: document.getElementById("msDetailStatus"),
    detailStatusLabel: document.getElementById("msDetailStatusLabel"),
    detailClient: document.getElementById("msDetailClient"),
    detailCreated: document.getElementById("msDetailCreated"),
    detailExpires: document.getElementById("msDetailExpires"),
    detailActivity: document.getElementById("msDetailActivity"),
    viewBtn: document.getElementById("msViewBtn"),
    tabs: document.getElementById("msTabs"),
    panels: root.querySelectorAll(".ms-tabpanel"),
    notesList: document.getElementById("msOfficeNotesList"),
    noteAdd: document.getElementById("msNoteAdd"),
    noteComposer: document.getElementById("msNoteComposer"),
    noteInput: document.getElementById("msBriefNoteInput"),
    noteSave: document.getElementById("msBriefNoteSave"),
    noteTpl: document.getElementById("msNoteItemTpl"),
    noteAttach: document.getElementById("msNoteAttach"),
    noteImage: document.getElementById("msNoteImage"),
    noteMention: document.getElementById("msNoteMention"),
    questionsList: document.getElementById("msQuestionsList"),
    historyList: document.getElementById("msHistoryList"),
    tagsList: document.getElementById("msTagsList"),
    wishesList: document.getElementById("msWishesList"),
    wishesCount: document.getElementById("msWishesCount"),
    attentionList: document.getElementById("msAttentionList"),
    attentionCount: document.getElementById("msAttentionCount"),
    briefSummary: document.getElementById("msBriefSummary"),
    back: document.getElementById("msBack"),
    body: document.getElementById("msBody"),
  };

  // ------------------------------------------------------------------
  // UTIL
  // ------------------------------------------------------------------

  function getCookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? decodeURIComponent(m.pop()) : "";
  }

  function api(path, opts = {}) {
    const headers = Object.assign(
      { Accept: "application/json" },
      opts.headers || {},
    );
    if (opts.body && typeof opts.body === "object") {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    if (!/^(GET|HEAD|OPTIONS)$/i.test(opts.method || "GET")) {
      headers["X-CSRFToken"] = getCookie(CSRF_COOKIE);
    }
    return fetch(
      path,
      Object.assign({ credentials: "same-origin" }, opts, { headers }),
    ).then((r) => {
      if (!r.ok)
        return r.text().then((t) => {
          let p;
          try { p = JSON.parse(t); } catch (e) { p = { error: t || r.statusText }; }
          throw Object.assign(new Error(p.error || "Erro"), {
            status: r.status, payload: p,
          });
        });
      const ct = r.headers.get("content-type") || "";
      return ct.includes("application/json") ? r.json() : r.text();
    });
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(
      /[&<>"']/g,
      (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
    );
  }
  function initials(nameOrEmail) {
    if (!nameOrEmail) return "?";
    const parts = String(nameOrEmail).split(/[\s@._-]+/).filter(Boolean).slice(0, 2);
    return parts.map((p) => p[0].toUpperCase()).join("") || "?";
  }
  function relativeTime(iso) {
    if (!iso) return "—";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "—";
    const diff = Math.max(0, Date.now() - then) / 1000;
    if (diff < 60) return "agora";
    if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
    if (diff < 604800) return `há ${Math.floor(diff / 86400)} d`;
    return new Date(iso).toLocaleDateString("pt-BR");
  }
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
  }
  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      try { window.lucide.createIcons(); } catch (e) {}
    }
  }
  function debounce(fn, wait) {
    let t;
    return function () {
      const args = arguments;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function applyGreeting() {
    const hour = new Date().getHours();
    let text = "Bom dia";
    let icon = "sun";
    if (hour >= 12 && hour < 18) text = "Boa tarde";
    else if (hour >= 18 || hour < 5) { text = "Boa noite"; icon = "moon"; }
    if (el.greeting) el.greeting.textContent = text;
    if (el.greetingIcon) {
      el.greetingIcon.setAttribute("data-lucide", icon);
      el.greetingIcon.innerHTML = "";
    }
    refreshIcons();
  }

  function deriveState(briefing) {
    const status = briefing.status;
    const p = briefing.progress || {};
    if (status === "completed") return "done";
    if (status === "cancelled" || status === "paused") return "waiting";
    if (p.pending_review > 0 || p.needs_attention) return "pending";
    if (!briefing.first_opened_at) return "waiting";
    return "progress";
  }

  // ------------------------------------------------------------------
  // KPIs (calculados uma vez ao carregar; atualizados só quando a lista muda)
  // ------------------------------------------------------------------

  function computeKpis(items) {
    const k = { open: 0, doubts: 0, attention: 0, done: 0 };
    for (let i = 0; i < items.length; i++) {
      const b = items[i];
      const p = b.progress || {};
      const d = b._derived;
      if (d === "progress" || d === "pending") k.open += 1;
      if (d === "done") k.done += 1;
      if (p.pending_review) k.attention += Number(p.pending_review) || 0;
      if (p.doubts) k.doubts += Number(p.doubts) || 0;
    }
    return k;
  }

  function renderKpis() {
    const k = computeKpis(state.briefings);
    if (el.kpiDone) el.kpiDone.textContent = k.done;
    if (el.kpiOpen) el.kpiOpen.textContent = k.open;
    if (el.kpiDoubts) el.kpiDoubts.textContent = k.doubts;
    if (el.kpiAttention) el.kpiAttention.textContent = k.attention;
  }

  // ------------------------------------------------------------------
  // FILTRO + RENDER DE LISTA
  // ------------------------------------------------------------------

  function applyFilter(items) {
    const predicate = FILTER_MAP[state.filter] || FILTER_MAP.all;
    const q = state.query.trim().toLowerCase();
    const out = [];
    for (let i = 0; i < items.length; i++) {
      const b = items[i];
      if (!predicate(b)) continue;
      if (q) {
        const hay =
          (b.title || "") + " " +
          (b.client_name || "") + " " +
          (b.template_name || "") + " " +
          (b.status_display || "");
        if (hay.toLowerCase().indexOf(q) === -1) continue;
      }
      out.push(b);
    }
    out.sort((a, b) => {
      const at = a._ts || 0;
      const bt = b._ts || 0;
      return bt - at;
    });
    return out;
  }

  function populateBriefLi(li, b) {
    li.dataset.id = b.id;
    if (b.id === state.activeId) li.classList.add("is-active");
    else li.classList.remove("is-active");

    const thumbImg = li.querySelector(".ms-brief-thumb img");
    if (thumbImg) {
      if (b.cover_url) {
        if (thumbImg.getAttribute("src") !== b.cover_url) {
          thumbImg.src = b.cover_url;
        }
        thumbImg.alt = b.title || "";
      } else if (thumbImg.hasAttribute("src")) {
        thumbImg.removeAttribute("src");
        thumbImg.alt = "";
      }
    }

    const nameEl = li.querySelector(".ms-brief-name");
    if (nameEl) nameEl.textContent = b.title || "—";

    const clientEl = li.querySelector(".ms-brief-client-name");
    if (clientEl) clientEl.textContent = b.client_name || "—";

    const statusEl = li.querySelector(".ms-brief-status");
    if (statusEl) {
      statusEl.dataset.status = b._derived || "waiting";
      const lbl = statusEl.querySelector(".ms-brief-status-label");
      if (lbl) lbl.textContent = STATUS_LABEL[b._derived] || "Aguardando";
    }

    const qEl = li.querySelector(".ms-brief-questions");
    if (qEl) {
      const total = Number((b.progress && b.progress.total_required) || 0);
      qEl.textContent = total === 1 ? "1 pergunta" : `${total} perguntas`;
    }

    const whenEl = li.querySelector(".ms-brief-when");
    if (whenEl) whenEl.textContent = relativeTime(b.updated_at || b.created_at);

    const pct = Math.round((b.progress && b.progress.percent) || 0);
    const fillEl = li.querySelector(".ms-brief-bar-fill");
    const barEl = li.querySelector(".ms-brief-bar");
    const pctEl = li.querySelector(".ms-brief-progress-pct");
    if (fillEl) fillEl.style.width = `${pct}%`;
    if (barEl) barEl.setAttribute("aria-valuenow", String(pct));
    if (pctEl) pctEl.textContent = `${pct}%`;
  }

  function makeBriefLi(b) {
    const node = el.listTpl.content.cloneNode(true);
    const li = node.querySelector(".ms-brief");
    if (!li) return null;
    populateBriefLi(li, b);
    return li;
  }

  function renderList() {
    if (!el.list || !el.listTpl) return;

    state.filtered = applyFilter(state.briefings);
    el.list.innerHTML = "";

    if (!state.filtered.length) {
      state.listCache.clear();
      el.list.innerHTML = '<li class="cl-empty">Nenhum briefing encontrado.</li>';
      return;
    }

    const frag = document.createDocumentFragment();
    const nextCache = new Map();

    for (let i = 0; i < state.filtered.length; i++) {
      const b = state.filtered[i];
      let li = state.listCache.get(b.id);
      if (li) {
        populateBriefLi(li, b);
      } else {
        li = makeBriefLi(b);
      }
      if (!li) continue;
      nextCache.set(b.id, li);
      frag.appendChild(li);
    }

    state.listCache = nextCache;
    el.list.appendChild(frag);
  }

  // ------------------------------------------------------------------
  // DETAIL
  // ------------------------------------------------------------------

  function setActiveTab(tab) {
    state.activeTab = tab;
    if (el.tabs) {
      el.tabs.querySelectorAll(".cl-tab").forEach((btn) => {
        const active = btn.dataset.tab === tab;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
    }
    el.panels.forEach((panel) => {
      panel.hidden = panel.dataset.panel !== tab;
    });
    if (tab === "history") renderHistory();
    if (tab === "questions") renderQuestions();
  }

  function renderDetail(detail) {
    if (!detail) return;
    const b = detail;
    if (el.crumbCurrent) el.crumbCurrent.textContent = b.title || "—";
    if (el.detailTitle) el.detailTitle.textContent = b.title || "—";
    if (el.detailClient) el.detailClient.textContent = b.client_name || "—";
    if (el.detailCreated) el.detailCreated.textContent = fmtDate(b.created_at);
    if (el.detailExpires) el.detailExpires.textContent = fmtDate(b.expires_at);
    if (el.detailActivity)
      el.detailActivity.textContent = relativeTime(b.updated_at);

    if (el.detailStatus) {
      const derived = deriveState(b);
      el.detailStatus.dataset.status = derived;
      if (el.detailStatusLabel) {
        el.detailStatusLabel.textContent = STATUS_LABEL[derived] || "Aguardando";
      }
    }
  }

  async function loadBriefing(id) {
    if (state.abortDetail) state.abortDetail.abort();
    const ctrl = new AbortController();
    state.abortDetail = ctrl;
    state.activeId = id;

    try {
      const [detail, events, notes] = await Promise.all([
        api(`/api/briefings/${id}/`, { signal: ctrl.signal }),
        api(`/api/briefings/${id}/events/`, { signal: ctrl.signal }).catch(() => []),
        api(`/api/briefings/${id}/notes/`, { signal: ctrl.signal }).catch(() => []),
      ]);
      if (ctrl.signal.aborted) return;
      state.detail = detail;
      state.events = Array.isArray(events) ? events : [];
      state.notes = Array.isArray(notes) ? notes : [];
      renderDetail(detail);
      renderNotes();
      if (state.activeTab === "history") renderHistory();
      if (state.activeTab === "questions") renderQuestions();
      if (detail && detail.client) loadClient(detail.client, ctrl);
    } catch (err) {
      if (err && err.name === "AbortError") return;
      console.warn("[mesa] falha ao carregar briefing", err, err && err.payload);
    }
  }

  async function loadClient(clientId, ctrl) {
    state.client = null;
    try {
      state.client = await api(`/api/clients/${clientId}/`, { signal: ctrl ? ctrl.signal : undefined });
    } catch (e) {
      if (e && e.name === "AbortError") return;
    }
    if (ctrl && ctrl.signal.aborted) return;
    renderSideLists();
  }

  // ------------------------------------------------------------------
  // RENDER: HISTÓRICO / PERGUNTAS / NOTAS
  // ------------------------------------------------------------------

  function renderHistory() {
    if (!el.historyList) return;
    const events = state.events || [];
    if (!events.length) {
      el.historyList.innerHTML =
        '<li class="cl-empty">Sem eventos registrados.</li>';
      return;
    }
    el.historyList.innerHTML = events
      .slice(0, 100)
      .map((e) => {
        const kind = e.kind_display || e.kind || "—";
        const when = relativeTime(e.created_at);
        const author = e.author_email || "";
        const q = e.question_id
          ? ` · pergunta ${String(e.question_id).slice(0, 8)}`
          : "";
        return `<li><strong>${escapeHtml(kind)}</strong>${q}<span style="opacity:.7"> · ${escapeHtml(author)}</span><span style="opacity:.6; float:right">${escapeHtml(when)}</span></li>`;
      })
      .join("");
  }

  function renderQuestions() {
    if (!el.questionsList) return;
    const d = state.detail;
    if (!d || !d.structure_snapshot || !Array.isArray(d.structure_snapshot.sections)) {
      el.questionsList.innerHTML =
        '<li class="cl-empty">Nenhuma pergunta adicional.</li>';
      return;
    }
    const customs = [];
    d.structure_snapshot.sections.forEach((sec) => {
      (sec.questions || []).forEach((q) => {
        if (q.is_custom)
          customs.push({ text: q.text, section: sec.title, required: q.is_required });
      });
    });
    if (!customs.length) {
      el.questionsList.innerHTML =
        '<li class="cl-empty">Nenhuma pergunta adicional.</li>';
      return;
    }
    el.questionsList.innerHTML = customs
      .map(
        (q) =>
          `<li><strong>${escapeHtml(q.section || "")}</strong><br>${escapeHtml(q.text || "")} ${q.required ? " · <em>obrigatória</em>" : ""}</li>`,
      )
      .join("");
  }

  function renderNotes() {
    if (!el.notesList || !el.noteTpl) return;
    if (!state.notes.length) {
      el.notesList.innerHTML = '<li class="cl-empty">Nenhuma nota ainda.</li>';
      return;
    }
    const frag = document.createDocumentFragment();
    state.notes.forEach((n) => {
      const node = el.noteTpl.content.cloneNode(true);
      const li = node.querySelector(".ms-note-item");
      if (!li) return;

      li.dataset.id = n.id;

      const typeEl = li.querySelector(".ms-note-type");
      if (typeEl) {
        let type = "observation";
        let label = "Observação";
        if (n.content.toLowerCase().includes("dúvida") || n.content.toLowerCase().includes("?")) {
          type = "doubt"; label = "Dúvida";
        } else if (n.content.toLowerCase().includes("pergunta")) {
          type = "question"; label = "Pergunta";
        }
        typeEl.dataset.type = type;
        typeEl.textContent = label;
      }

      const avatarEl = li.querySelector(".ms-avatar");
      if (avatarEl) {
        const who = n.author_name || n.author_email || "—";
        const ini = initials(who);
        if (n.author_avatar_url) {
          avatarEl.innerHTML = `<img src="${n.author_avatar_url}" alt="${escapeHtml(who)}">`;
        } else {
          avatarEl.innerHTML = `<span class="ms-avatar-initials">${escapeHtml(ini)}</span>`;
        }
      }

      const authorEl = li.querySelector(".ms-note-author");
      if (authorEl) authorEl.textContent = n.author_name || n.author_email || "—";

      const whenEl = li.querySelector(".ms-note-when");
      if (whenEl) whenEl.textContent = `· ${relativeTime(n.created_at)}`;

      const textEl = li.querySelector(".ms-note-text");
      if (textEl) textEl.textContent = n.content || "";

      frag.appendChild(li);
    });
    el.notesList.innerHTML = "";
    el.notesList.appendChild(frag);
    refreshIcons();
  }

  async function createNote(content) {
    if (!state.activeId) return;
    const text = (content || "").trim();
    if (!text) return;
    try {
      const created = await api(`/api/briefings/${state.activeId}/notes/`, {
        method: "POST",
        body: { content: text },
      });
      state.notes.unshift(created);
      renderNotes();
      if (el.noteInput) el.noteInput.value = "";
      if (el.noteComposer) el.noteComposer.hidden = true;
      if (el.noteAdd) el.noteAdd.setAttribute("aria-expanded", "false");
    } catch (err) {
      console.warn("[mesa] falha ao criar nota", err);
      alert("Não foi possível salvar a nota. " + (err.message || ""));
    }
  }

  async function updateNote(noteId, content) {
    if (!state.activeId || !noteId) return;
    const text = (content || "").trim();
    if (!text) return;
    try {
      const updated = await api(
        `/api/briefings/${state.activeId}/notes/${noteId}/`,
        { method: "PATCH", body: { content: text } },
      );
      state.notes = state.notes.map((n) =>
        String(n.id) === String(noteId) ? updated : n,
      );
      renderNotes();
    } catch (err) {
      console.warn("[mesa] falha ao editar nota", err);
      alert("Não foi possível editar a nota. " + (err.message || ""));
    }
  }

  async function deleteNote(noteId) {
    if (!state.activeId || !noteId) return;
    if (!window.confirm("Excluir esta nota?")) return;
    try {
      await api(
        `/api/briefings/${state.activeId}/notes/${noteId}/`,
        { method: "DELETE" },
      );
      state.notes = state.notes.filter((n) => String(n.id) !== String(noteId));
      renderNotes();
    } catch (err) {
      console.warn("[mesa] falha ao excluir nota", err);
      alert("Não foi possível excluir a nota. " + (err.message || ""));
    }
  }

  // ------------------------------------------------------------------
  // RENDER: SIDE (Insight)
  // ------------------------------------------------------------------

  function normalizeList(raw) {
    if (!Array.isArray(raw)) return [];
    return raw
      .map((item) => {
        if (typeof item === "string") return { title: item, subtitle: "" };
        if (item && typeof item === "object")
          return {
            title: item.title || item.name || "",
            subtitle: item.subtitle || item.description || "",
          };
        return null;
      })
      .filter(Boolean)
      .slice(0, 8);
  }

  function fillSlots(ul, items) {
    if (!ul) return;
    const slots = ul.querySelectorAll(".ms-check-slot");
    slots.forEach((li, idx) => {
      const item = items[idx];
      const strong = li.querySelector(".ms-check-text strong");
      const small = li.querySelector(".ms-check-text small");
      if (!strong) return;
      if (item && (item.title || item.subtitle)) {
        li.classList.remove("is-empty");
        strong.textContent = item.title || "—";
        if (small) small.textContent = item.subtitle || "";
      } else {
        li.classList.add("is-empty");
        strong.textContent = "—";
        if (small) small.textContent = "—";
      }
    });
  }

  function renderSideLists() {
    const c = state.client || {};
    const ctx = c.context && typeof c.context === "object" ? c.context : {};

    if (el.tagsList) {
      const tags = Array.isArray(ctx.tags) ? ctx.tags : [];
      if (!tags.length) {
        el.tagsList.innerHTML = '<span class="ms-tag ms-tag--empty">—</span>';
      } else {
        el.tagsList.innerHTML = tags
          .map((t) => `<span class="ms-tag">${escapeHtml(t)}</span>`)
          .join("");
      }
    }

    const wishes = normalizeList(ctx.wishes);
    const attention = normalizeList(ctx.attention);
    fillSlots(el.wishesList, wishes);
    fillSlots(el.attentionList, attention);
    if (el.wishesCount) el.wishesCount.textContent = wishes.length;
    if (el.attentionCount) el.attentionCount.textContent = attention.length;

    if (el.briefSummary && state.detail) {
      el.briefSummary.textContent = state.detail.description || "—";
    }
  }

  // ------------------------------------------------------------------
  // FILTER
  // ------------------------------------------------------------------

  function setFilter(filter) {
    if (state.filter === filter) return;
    state.filter = filter;
    renderList();
  }

  function onSearch() {
    const q = el.search ? el.search.value : "";
    if (q === state.query) return;
    state.query = q;
    renderList();
  }

  // ------------------------------------------------------------------
  // NAVEGAÇÃO
  // ------------------------------------------------------------------

  function openBriefingPage() {
    if (!state.activeId) return;
    const publicId = root.dataset.workspacePublicId || "";
    if (!publicId) {
      console.warn("[mesa] workspace_public_id ausente.");
      return;
    }
    window.location.href = `/w/${publicId}/briefings/${state.activeId}/resumo/`;
  }

  // ------------------------------------------------------------------
  // EVENTS
  // ------------------------------------------------------------------

  function bindEvents() {
    if (el.kpis) {
      el.kpis.addEventListener("click", (e) => {
        const btn = e.target.closest(".ms-kpi");
        if (!btn) return;
        const kpi = btn.dataset.kpi;
        const map = {
          done: "done",
          open: "progress",
          doubts: "pending",
          attention: "pending",
        };
        if (map[kpi]) setFilter(map[kpi]);
      });
    }

    if (el.search) {
      el.search.addEventListener("input", debounce(onSearch, 80));
    }
    if (el.tabs) {
      el.tabs.addEventListener("click", (e) => {
        const btn = e.target.closest(".cl-tab");
        if (btn) setActiveTab(btn.dataset.tab || "summary");
      });
    }
    if (el.list) {
      el.list.addEventListener("click", (e) => {
        const item = e.target.closest(".ms-brief");
        if (!item) return;
        const id = item.dataset.id;
        if (!id || id === state.activeId) return;

        const prev = el.list.querySelector(".ms-brief.is-active");
        if (prev) prev.classList.remove("is-active");
        item.classList.add("is-active");

        if (el.body) el.body.classList.add("detail-open");
        loadBriefing(id);
      });
    }
    if (el.back && el.body) {
      el.back.addEventListener("click", () =>
        el.body.classList.remove("detail-open"),
      );
    }
    if (el.viewBtn) el.viewBtn.addEventListener("click", openBriefingPage);

    if (el.noteAdd && el.noteComposer) {
      el.noteAdd.addEventListener("click", () => {
        const open = !el.noteComposer.hidden;
        el.noteComposer.hidden = open;
        el.noteAdd.setAttribute("aria-expanded", open ? "false" : "true");
        if (!open && el.noteInput) el.noteInput.focus();
      });
    }
    if (el.noteSave) {
      el.noteSave.addEventListener("click", () =>
        createNote(el.noteInput ? el.noteInput.value : ""),
      );
    }
    if (el.noteInput) {
      el.noteInput.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          createNote(el.noteInput.value);
        }
      });
    }

    [el.noteAttach, el.noteImage, el.noteMention].forEach((btn) => {
      if (!btn) return;
      btn.addEventListener("click", () => {
        if (el.noteComposer && el.noteComposer.hidden) {
          el.noteComposer.hidden = false;
          if (el.noteAdd) el.noteAdd.setAttribute("aria-expanded", "true");
        }
        if (el.noteInput) el.noteInput.focus();
      });
    });

    if (el.notesList) {
      el.notesList.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-note-action]");
        if (!btn) return;
        const li = btn.closest(".ms-note-item");
        const noteId = li && li.dataset.id;
        if (!noteId) return;
        const action = btn.dataset.noteAction;
        if (action === "delete") { deleteNote(noteId); return; }
        if (action === "edit") {
          const current = state.notes.find(
            (n) => String(n.id) === String(noteId),
          );
          const next = window.prompt("Editar nota:", (current && current.content) || "");
          if (next == null) return;
          updateNote(noteId, next);
        }
      });
    }
  }

  // ------------------------------------------------------------------
  // BOOT
  // ------------------------------------------------------------------

  async function loadAll() {
    try {
      const list = await api("/api/briefings/");
      state.briefings = (Array.isArray(list) ? list : []).map((b) => {
        const updatedAt = b.updated_at || b.created_at || null;
        return Object.assign({}, b, {
          progress: b.progress || {},
          _derived: deriveState(b),
          _ts: updatedAt ? new Date(updatedAt).getTime() || 0 : 0,
        });
      });
      renderKpis();
      renderList();
      if (state.briefings.length) {
        const first = state.briefings[0];
        state.activeId = first.id;
        const activeEl = el.list
          ? el.list.querySelector(`.ms-brief[data-id="${first.id}"]`)
          : null;
        if (activeEl) activeEl.classList.add("is-active");
        loadBriefing(first.id);
      } else {
        renderSideLists();
      }
    } catch (err) {
      console.error(
        "[mesa] falha ao carregar lista",
        err, err && err.status, err && err.payload,
      );
      if (el.list)
        el.list.innerHTML =
          '<li class="cl-empty">Não foi possível carregar os briefings.</li>';
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    applyGreeting();
    bindEvents();
    setActiveTab("summary");
    loadAll();
  });
})();