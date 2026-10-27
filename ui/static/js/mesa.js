/* =========================================================================
   MESA — v42
   - Botão "Salvar" (notas) com spinner real
   - Notas: anti-duplicata reserva o texto ANTES do POST
   - Clicar na nota abre o editor (modal estilo Apple/Notion)
   - Editor de nota: popup com autofocus, ⌘/Ctrl+Enter salva, Esc fecha
   - Performance: cache, delegação, rAF de ícones
   ========================================================================= */
(function () {
  "use strict";

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
  const DETAIL_TTL_MS = 15000;
  const CHOICE_TYPES = new Set([
    "single_choice", "multiple_choice", "dropdown", "choice",
  ]);
  const NOTE_DUPLICATE_WINDOW_MS = 1500;

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
    customQuestions: [],
    activeTab: "summary",
    activeView: "detail",
    listCache: new Map(),
    detailCache: new Map(),
    abortDetail: null,
    prefetching: new Set(),
    lastClickTs: 0,
    mounted: false,
    bound: false,
    root: null,
    newQType: "text",
    newQOptions: [],
    kebabOpen: false,
    viewerUrl: "",
    noteSaving: false,
    lastNoteText: "",
    lastNoteTs: 0,
    editingNoteId: null,
    noteEditorSaving: false,
    _renderScheduled: false,
  };

  const el = {};
  const _iconQueue = { scheduled: false };

  function cacheElements() {
    const root = state.root;
    if (!root) return;
    el.greeting = document.getElementById("msGreeting");
    el.greetingIcon = document.getElementById("msGreetingIcon");
    el.kpis = document.getElementById("msKpis");
    el.kpiAll = document.getElementById("msKpiAll");
    el.kpiOpen = document.getElementById("msKpiOpen");
    el.kpiPending = document.getElementById("msKpiPending");
    el.kpiDone = document.getElementById("msKpiDone");
    el.filterAllBtn = document.getElementById("msFilterAllBtn");
    el.list = document.getElementById("msBriefingsList");
    el.listTpl = document.getElementById("msBriefItemTpl");
    el.search = document.getElementById("msBriefingsSearch");
    el.crumbCurrent = document.getElementById("msCrumbCurrent");
    el.detailTitle = document.getElementById("msDetailTitle");
    el.detailStatus = document.getElementById("msDetailStatus");
    el.detailStatusLabel = document.getElementById("msDetailStatusLabel");
    el.detailSuppPill = document.getElementById("msDetailSuppPill");
    el.detailSuppLabel = document.getElementById("msDetailSuppLabel");
    el.detailClient = document.getElementById("msDetailClient");
    el.detailCreated = document.getElementById("msDetailCreated");
    el.detailExpires = document.getElementById("msDetailExpires");
    el.detailActivity = document.getElementById("msDetailActivity");
    el.viewBtn = document.getElementById("msViewBtn");
    el.editBtn = document.getElementById("msEditBtn");
    el.reopenBtn = document.getElementById("msReopenBtn");
    el.deleteBtn = document.getElementById("msDeleteBtn");
    el.kebabBtn = document.getElementById("msKebabBtn");
    el.kebabMenu = document.getElementById("msKebabMenu");
    el.reanalyzeBtn = document.getElementById("msReanalyzeBtn");
    el.tabs = document.getElementById("msTabs");
    el.panels = root.querySelectorAll(".ms-tabpanel");
    el.views = root.querySelectorAll(".ms-detail-view");
    el.notesList = document.getElementById("msOfficeNotesList");
    el.noteInput = document.getElementById("msBriefNoteInput");
    el.noteSave = document.getElementById("msBriefNoteSave");
    el.noteTpl = document.getElementById("msNoteItemTpl");
    el.noteAttach = document.getElementById("msNoteAttach");
    el.noteImage = document.getElementById("msNoteImage");
    el.noteMention = document.getElementById("msNoteMention");
    el.questionsList = document.getElementById("msQuestionsList");
    el.addCustomQuestionBtn = document.getElementById("msAddCustomQuestionBtn");
    el.historyList = document.getElementById("msHistoryList");
    el.tagsList = document.getElementById("msTagsList");
    el.wishesList = document.getElementById("msWishesList");
    el.attentionList = document.getElementById("msAttentionList");
    el.briefSummary = document.getElementById("msBriefSummary");
    el.moodboardGrid = document.getElementById("msMoodboardGrid");
    el.moodboardCount = document.getElementById("msMoodboardCount");
    el.back = document.getElementById("msBack");
    el.body = document.getElementById("msBody");
    el.editForm = document.getElementById("msEditForm");
    el.editBack = document.getElementById("msEditBack");
    el.editCancel = document.getElementById("msEditCancel");
    el.editSubmit = document.getElementById("msEditSubmit");
    el.editTitleInput = document.getElementById("msEditTitleInput");
    el.editExpiresInput = document.getElementById("msEditExpiresInput");
    el.editStatusInput = document.getElementById("msEditStatusInput");
    el.editIntroInput = document.getElementById("msEditIntroInput");
    el.editClientInput = document.getElementById("msEditClientInput");
    el.newQForm = document.getElementById("msNewQuestionForm");
    el.newQBack = document.getElementById("msNewQBack");
    el.newQCancel = document.getElementById("msNewQCancel");
    el.newQSubmit = document.getElementById("msNewQSubmit");
    el.newQSection = document.getElementById("msNewQSection");
    el.newQText = document.getElementById("msNewQText");
    el.newQInstructions = document.getElementById("msNewQInstructions");
    el.newQType = document.getElementById("msNewQType");
    el.newQRequired = document.getElementById("msNewQRequired");
    el.newQOptionsSection = document.getElementById("msNewQOptionsSection");
    el.newQOptionsList = document.getElementById("msNewQOptionsList");
    el.newQAddOptionBtn = document.getElementById("msNewQAddOptionBtn");
    el.modalConfirm = document.getElementById("msModalConfirm");
    el.confirmTitle = document.getElementById("msConfirmTitle");
    el.confirmSub = document.getElementById("msConfirmSub");
    el.confirmIcon = document.getElementById("msConfirmIcon");
    el.confirmBtn = document.getElementById("msConfirmBtn");
    el.modalPrompt = document.getElementById("msModalPrompt");
    el.promptTitle = document.getElementById("msPromptTitle");
    el.promptLabel = document.getElementById("msPromptLabel");
    el.promptInput = document.getElementById("msPromptInput");
    el.promptConfirm = document.getElementById("msPromptConfirm");
    el.modalAlert = document.getElementById("msModalAlert");
    el.alertTitle = document.getElementById("msAlertTitle");
    el.alertMessage = document.getElementById("msAlertMessage");
    el.alertIcon = document.getElementById("msAlertIcon");
    el.modalImageViewer = document.getElementById("msModalImageViewer");
    el.imageViewerImg = document.getElementById("msImageViewerImg");
    el.imageViewerClose = document.getElementById("msImageViewerClose");
    el.modalNoteEditor = document.getElementById("msModalNoteEditor");
    el.noteEditorInput = document.getElementById("msNoteEditorInput");
    el.noteEditorSave = document.getElementById("msNoteEditorSave");
    el.noteEditorTitle = document.getElementById("msNoteEditorTitle");
  }

  // -------------------- MODAIS --------------------
  let pendingConfirm = null;
  let pendingPrompt = null;

  function openModal(modalEl) {
    if (!modalEl) return;
    modalEl.classList.add("is-open");
    document.body.classList.add("ms-modal-open");
    document.body.style.overflow = "hidden";
    refreshIcons();
  }
  function closeModal(modalEl) {
    if (!modalEl) return;
    modalEl.classList.remove("is-open");
    if (!document.querySelector(".ms-modal-overlay.is-open")) {
      document.body.classList.remove("ms-modal-open");
      document.body.style.overflow = "";
    }
  }
  function bindModalClosers() {
    state.root.querySelectorAll("[data-ms-close]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const id = btn.getAttribute("data-ms-close");
        if (id) closeModal(document.getElementById(id));
      });
    });
    state.root.querySelectorAll(".ms-modal-overlay").forEach((overlay) => {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeModal(overlay);
      });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const open = document.querySelector(".ms-modal-overlay.is-open");
        if (open) {
          closeModal(open);
          if (open.id === "msModalImageViewer" && el.imageViewerImg) {
            el.imageViewerImg.src = "";
          }
          if (open.id === "msModalNoteEditor") {
            state.editingNoteId = null;
          }
        }
      }
    });
  }
  function confirmAction({ title, subtitle, confirmLabel, confirmVariant, icon, onConfirm }) {
    if (el.confirmTitle) el.confirmTitle.textContent = title || "Confirmar?";
    if (el.confirmSub) el.confirmSub.textContent = subtitle || "Esta ação não pode ser desfeita.";
    if (el.confirmIcon) {
      el.confirmIcon.classList.toggle("is-primary", confirmVariant === "primary");
      el.confirmIcon.innerHTML = `<i data-lucide="${icon || "alert-triangle"}"></i>`;
    }
    if (el.confirmBtn) {
      el.confirmBtn.className = "ms-btn " +
        (confirmVariant === "danger" ? "ms-btn--danger" : "ms-btn--primary");
      const labelText = confirmLabel || (confirmVariant === "danger" ? "Excluir" : "Confirmar");
      el.confirmBtn.innerHTML =
        `<span class="ms-btn-label">${escapeHtml(labelText)}</span>` +
        `<span class="ms-btn-spinner"></span>`;
      el.confirmBtn.disabled = false;
    }
    pendingConfirm = onConfirm;
    openModal(el.modalConfirm);
  }
  function bindConfirm() {
    if (!el.confirmBtn) return;
    el.confirmBtn.addEventListener("click", async () => {
      if (!pendingConfirm) return;
      const cb = pendingConfirm;
      pendingConfirm = null;
      setButtonLoading(el.confirmBtn, true);
      try { await cb(); } catch (e) { console.error(e); }
      finally {
        setButtonLoading(el.confirmBtn, false);
        closeModal(el.modalConfirm);
      }
    });
  }
  function promptAction({ title, label, initial, placeholder, confirmLabel, onConfirm }) {
    if (el.promptTitle) el.promptTitle.textContent = title || "Editar";
    if (el.promptLabel) el.promptLabel.textContent = label || "Conteúdo";
    if (el.promptInput) {
      el.promptInput.value = initial || "";
      el.promptInput.placeholder = placeholder || "Digite…";
    }
    if (el.promptConfirm) {
      const labelText = confirmLabel || "Salvar";
      el.promptConfirm.innerHTML =
        `<span class="ms-btn-label">${escapeHtml(labelText)}</span>` +
        `<span class="ms-btn-spinner"></span>`;
      el.promptConfirm.disabled = false;
    }
    pendingPrompt = onConfirm;
    openModal(el.modalPrompt);
    setTimeout(() => { if (el.promptInput) { el.promptInput.focus(); el.promptInput.select(); } }, 60);
  }
  function bindPrompt() {
    if (!el.promptConfirm) return;
    el.promptConfirm.addEventListener("click", async () => {
      if (!pendingPrompt) return;
      const value = el.promptInput ? el.promptInput.value : "";
      const cb = pendingPrompt;
      pendingPrompt = null;
      setButtonLoading(el.promptConfirm, true);
      try { await cb(value); closeModal(el.modalPrompt); }
      catch (e) { console.error(e); }
      finally { setButtonLoading(el.promptConfirm, false); }
    });
    if (el.promptInput) {
      el.promptInput.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          el.promptConfirm.click();
        }
      });
    }
  }
  function showAlert({ title, message, variant, icon }) {
    if (el.alertTitle) el.alertTitle.textContent = title || "Aviso";
    if (el.alertMessage) el.alertMessage.textContent = message || "";
    if (el.alertIcon) {
      el.alertIcon.classList.toggle("is-danger", variant === "danger");
      el.alertIcon.classList.toggle("is-primary", variant !== "danger");
      el.alertIcon.innerHTML = `<i data-lucide="${icon || (variant === "danger" ? "alert-triangle" : "info")}"></i>`;
    }
    openModal(el.modalAlert);
  }
  function openImageViewer(url) {
    if (!url) return;
    state.viewerUrl = url;
    if (el.imageViewerImg) el.imageViewerImg.src = url;
    openModal(el.modalImageViewer);
  }
  function bindImageViewer() {
    if (el.imageViewerClose) {
      el.imageViewerClose.addEventListener("click", () => {
        closeModal(el.modalImageViewer);
        if (el.imageViewerImg) el.imageViewerImg.src = "";
      });
    }
  }
  function setButtonLoading(btn, loading) {
    if (!btn) return;
    if (loading) { btn.classList.add("is-loading"); btn.disabled = true; }
    else { btn.classList.remove("is-loading"); btn.disabled = false; }
  }

  // -------------------- UTIL --------------------
  function getCookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? decodeURIComponent(m.pop()) : "";
  }
  function api(path, opts = {}) {
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
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
  function toLocalDateTimeInput(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  function refreshIcons() {
    if (_iconQueue.scheduled) return;
    _iconQueue.scheduled = true;
    requestAnimationFrame(() => {
      _iconQueue.scheduled = false;
      if (window.lucide && typeof window.lucide.createIcons === "function") {
        try { window.lucide.createIcons(); } catch (e) {}
      }
    });
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
    const supp = briefing.supplementary_state || {};

    if (status === "completed") {
      if (supp.has_pending_required) return "pending";
      return "done";
    }
    if (status === "cancelled" || status === "paused") return "waiting";
    if (p.pending_review > 0 || p.needs_attention) return "pending";
    if (!briefing.first_opened_at) return "waiting";
    return "progress";
  }

  // -------------------- VIEW SWITCH --------------------
  function setDetailView(name) {
    state.activeView = name;
    el.views.forEach((v) => { v.hidden = v.dataset.view !== name; });
    refreshIcons();
  }
  function backToDetail() { setDetailView("detail"); }

  // -------------------- KEBAB --------------------
  let _kebabDocHandler = null;
  function openKebab() {
    if (!el.kebabMenu || !el.kebabBtn) return;
    el.kebabMenu.hidden = false;
    el.kebabBtn.setAttribute("aria-expanded", "true");
    el.kebabBtn.classList.add("is-open");
    state.kebabOpen = true;

    setTimeout(() => {
      _kebabDocHandler = (ev) => {
        if (el.kebabMenu.contains(ev.target)) return;
        if (el.kebabBtn.contains(ev.target)) return;
        closeKebab();
      };
      document.addEventListener("click", _kebabDocHandler, true);
    }, 0);
  }
  function closeKebab() {
    if (!el.kebabMenu || !el.kebabBtn) return;
    el.kebabMenu.hidden = true;
    el.kebabBtn.setAttribute("aria-expanded", "false");
    el.kebabBtn.classList.remove("is-open");
    state.kebabOpen = false;
    if (_kebabDocHandler) {
      document.removeEventListener("click", _kebabDocHandler, true);
      _kebabDocHandler = null;
    }
  }
  function toggleKebab() {
    if (state.kebabOpen) closeKebab();
    else openKebab();
  }
  function bindKebab() {
    if (el.kebabBtn) {
      el.kebabBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleKebab();
      });
    }
    if (el.editBtn) {
      el.editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeKebab();
        openEditView();
      });
    }
    if (el.reopenBtn) {
      el.reopenBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeKebab();
        triggerReopen();
      });
    }
    if (el.deleteBtn) {
      el.deleteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeKebab();
        deleteBriefing();
      });
    }
  }

  // -------------------- FILTROS / LISTA --------------------
  function computeFilterCounts(items) {
    const c = { all: 0, open: 0, pending: 0, done: 0 };
    for (let i = 0; i < items.length; i++) {
      const d = items[i]._derived;
      c.all += 1;
      if (d === "progress") c.open += 1;
      else if (d === "pending") c.pending += 1;
      else if (d === "done") c.done += 1;
    }
    return c;
  }
  function renderFilterCounts() {
    const c = computeFilterCounts(state.briefings);
    if (el.kpiAll) el.kpiAll.textContent = c.all;
    if (el.kpiOpen) el.kpiOpen.textContent = c.open;
    if (el.kpiPending) el.kpiPending.textContent = c.pending;
    if (el.kpiDone) el.kpiDone.textContent = c.done;
  }
  function syncFilterActive() {
    if (el.filterAllBtn) {
      const active = state.filter === "all";
      el.filterAllBtn.classList.toggle("is-active", active);
      el.filterAllBtn.setAttribute("aria-selected", active ? "true" : "false");
    }
    if (el.kpis) {
      el.kpis.querySelectorAll(".ms-filter").forEach((btn) => {
        const kpi = btn.dataset.kpi;
        const map = { open: "progress", pending: "pending", done: "done" };
        const active = map[kpi] === state.filter;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
    }
  }
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
    out.sort((a, b) => (b._ts || 0) - (a._ts || 0));
    return out;
  }
  function populateBriefLi(li, b) {
    li.dataset.id = b.id;
    li.dataset.state = b._derived || "waiting";
    if (b.id === state.activeId) li.classList.add("is-active");
    else li.classList.remove("is-active");
    const thumbImg = li.querySelector(".ms-brief-thumb img");
    if (thumbImg) {
      if (b.cover_url) {
        if (thumbImg.getAttribute("src") !== b.cover_url) thumbImg.src = b.cover_url;
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
    const pct = Math.round((b.progress && b.progress.percent) || 0);
    const fillEl = li.querySelector(".ms-brief-bar-fill");
    const barEl = li.querySelector(".ms-brief-bar");
    const pctEl = li.querySelector(".ms-brief-progress-pct");
    if (fillEl) fillEl.style.width = `${pct}%`;
    if (barEl) barEl.setAttribute("aria-valuenow", String(pct));
    if (pctEl) pctEl.textContent = `${pct}%`;

    const suppEl = li.querySelector(".ms-brief-supp");
    if (suppEl) {
      const ss = b.supplementary_state || {};
      const pending = Number(ss.count_pending_required || 0)
        + Number(ss.count_pending_optional || 0);
      if (pending > 0) {
        suppEl.classList.remove("hidden");
        suppEl.dataset.supp = String(pending);
        const countEl = suppEl.querySelector(".ms-brief-supp-count");
        const labelEl = suppEl.querySelector(".ms-brief-supp-label");
        if (countEl) countEl.textContent = String(pending);
        if (labelEl) {
          labelEl.textContent = pending === 1
            ? "Pergunta complementar"
            : "Perguntas complementares";
        }
      } else {
        suppEl.classList.add("hidden");
        suppEl.dataset.supp = "0";
      }
    }
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
      if (li) populateBriefLi(li, b);
      else li = makeBriefLi(b);
      if (!li) continue;
      nextCache.set(b.id, li);
      frag.appendChild(li);
    }
    state.listCache = nextCache;
    el.list.innerHTML = "";
    el.list.appendChild(frag);
    refreshIcons();
  }

  // -------------------- DETAIL --------------------
  function setActiveTab(tab) {
    state.activeTab = tab;
    if (el.tabs) {
      el.tabs.querySelectorAll(".cl-tab").forEach((btn) => {
        const active = btn.dataset.tab === tab;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
    }
    el.panels.forEach((panel) => { panel.hidden = panel.dataset.panel !== tab; });
    if (tab === "history") renderHistory();
    if (tab === "questions") renderQuestions();
  }

  function applyDetailToHeader(b) {
    if (!b) return;
    if (el.crumbCurrent) el.crumbCurrent.textContent = b.title || "—";
    if (el.detailTitle) el.detailTitle.textContent = b.title || "—";
    if (el.detailClient) el.detailClient.textContent = b.client_name || "—";
    if (el.detailCreated) el.detailCreated.textContent = fmtDate(b.created_at);
    if (el.detailExpires) el.detailExpires.textContent = fmtDate(b.expires_at);
    if (el.detailActivity) el.detailActivity.textContent = relativeTime(b.updated_at);

    const derived = deriveState(b);
    if (el.detailStatus) {
      el.detailStatus.dataset.status = derived;
      if (el.detailStatusLabel) {
        el.detailStatusLabel.textContent = STATUS_LABEL[derived] || "Aguardando";
      }
    }

    const ss = b.supplementary_state || {};
    const totalSuppPending = Number(ss.count_pending_required || 0)
      + Number(ss.count_pending_optional || 0);
    if (el.detailSuppPill && el.detailSuppLabel) {
      if (totalSuppPending > 0) {
        el.detailSuppPill.classList.remove("hidden");
        el.detailSuppPill.dataset.status = ss.has_pending_required ? "pending" : "progress";
        el.detailSuppLabel.textContent = totalSuppPending === 1
          ? "1 complementar pendente"
          : `${totalSuppPending} complementares pendentes`;
      } else if (ss.has_questions) {
        el.detailSuppPill.classList.remove("hidden");
        el.detailSuppPill.dataset.status = "done";
        el.detailSuppLabel.textContent = "Complementares concluídas";
      } else {
        el.detailSuppPill.classList.add("hidden");
      }
    }
  }

  function optimisticApplyFromList(briefingId) {
    const b = state.briefings.find((x) => String(x.id) === String(briefingId));
    if (!b) return;
    applyDetailToHeader(b);
  }

  function getCachedDetail(id) {
    const hit = state.detailCache.get(String(id));
    if (!hit) return null;
    if (Date.now() - hit.ts > DETAIL_TTL_MS) {
      state.detailCache.delete(String(id));
      return null;
    }
    return hit;
  }
  function putCachedDetail(id, detail, events, notes, customQuestions) {
    state.detailCache.set(String(id), {
      detail, events, notes, customQuestions, ts: Date.now(),
    });
  }
  async function fetchBriefingBundle(id, ctrl) {
    const [detail, events, notes, customQs] = await Promise.all([
      api(`/api/briefings/${id}/`, { signal: ctrl ? ctrl.signal : undefined }),
      api(`/api/briefings/${id}/events/`, { signal: ctrl ? ctrl.signal : undefined }).catch(() => []),
      api(`/api/briefings/${id}/notes/`, { signal: ctrl ? ctrl.signal : undefined }).catch(() => []),
      api(`/api/briefings/${id}/custom-questions/`, { signal: ctrl ? ctrl.signal : undefined }).catch(() => []),
    ]);
    return {
      detail,
      events: Array.isArray(events) ? events : [],
      notes: Array.isArray(notes) ? notes : [],
      customQuestions: Array.isArray(customQs) ? customQs : [],
    };
  }
  function hydrateDetail(id, bundle) {
    state.detail = bundle.detail;
    state.events = bundle.events;
    const seen = new Set();
    const dedupNotes = [];
    (bundle.notes || []).forEach((n) => {
      const key = String(n.id);
      if (seen.has(key)) return;
      seen.add(key);
      dedupNotes.push(n);
    });
    dedupNotes.sort((a, b) => {
      const pa = a.is_pinned ? 1 : 0;
      const pb = b.is_pinned ? 1 : 0;
      if (pa !== pb) return pb - pa;
      const ta = new Date(a.created_at || 0).getTime();
      const tb = new Date(b.created_at || 0).getTime();
      return tb - ta;
    });
    state.notes = dedupNotes;
    state.customQuestions = bundle.customQuestions || [];
    applyDetailToHeader(bundle.detail);
    renderNotes();
    if (state.activeTab === "history") renderHistory();
    if (state.activeTab === "questions") renderQuestions();
    if (bundle.detail && bundle.detail.client) {
      loadClient(bundle.detail.client);
    }
    renderMoodboard();
  }
  async function loadBriefing(id) {
    if (state.abortDetail) state.abortDetail.abort();
    const ctrl = new AbortController();
    state.abortDetail = ctrl;
    state.activeId = id;
    optimisticApplyFromList(id);
    const cached = getCachedDetail(id);
    if (cached) { hydrateDetail(id, cached); return; }
    try {
      const bundle = await fetchBriefingBundle(id, ctrl);
      if (ctrl.signal.aborted) return;
      putCachedDetail(id, bundle.detail, bundle.events, bundle.notes, bundle.customQuestions);
      hydrateDetail(id, bundle);
    } catch (err) {
      if (err && err.name === "AbortError") return;
      console.warn("[mesa] falha ao carregar briefing", err, err && err.payload);
    }
  }
  function prefetchBriefing(id) {
    if (!id) return;
    if (String(id) === String(state.activeId)) return;
    if (getCachedDetail(id)) return;
    if (state.prefetching.has(String(id))) return;
    state.prefetching.add(String(id));
    fetchBriefingBundle(id).then((bundle) => {
      putCachedDetail(id, bundle.detail, bundle.events, bundle.notes, bundle.customQuestions);
    }).catch(() => {}).finally(() => {
      state.prefetching.delete(String(id));
    });
  }
  async function loadClient(clientId) {
    state.client = null;
    try { state.client = await api(`/api/clients/${clientId}/`); } catch (e) {}
    renderSideLists();
  }

  // -------------------- HISTÓRICO / PERGUNTAS --------------------
  function renderHistory() {
    if (!el.historyList) return;
    const events = state.events || [];
    if (!events.length) {
      el.historyList.innerHTML = '<li class="cl-empty">Sem eventos registrados.</li>';
      return;
    }
    const out = [];
    const max = Math.min(events.length, 100);
    for (let i = 0; i < max; i++) {
      const e = events[i];
      const kind = e.kind_display || e.kind || "—";
      const when = relativeTime(e.created_at);
      const author = e.author_email || "";
      const q = e.question_id
        ? ` · pergunta ${String(e.question_id).slice(0, 8)}`
        : "";
      out.push(
        `<li><strong>${escapeHtml(kind)}</strong>${q}` +
        `<span style="opacity:.7"> · ${escapeHtml(author)}</span>` +
        `<span style="opacity:.6; float:right">${escapeHtml(when)}</span></li>`
      );
    }
    el.historyList.innerHTML = out.join("");
  }

  function renderQuestions() {
    if (!el.questionsList) return;
    if (!state.customQuestions.length) {
      el.questionsList.innerHTML = '<li class="cl-empty">Nenhuma pergunta adicional.</li>';
      return;
    }
    const snapshot = (state.detail && state.detail.structure_snapshot) || {};
    const suppSnapshot = (state.detail && state.detail.supplementary_snapshot) || {};
    const sectionTitleById = {};
    (snapshot.sections || []).forEach((s) => {
      sectionTitleById[String(s.id)] = s.title || "—";
    });
    (suppSnapshot.sections || []).forEach((s) => {
      if (!sectionTitleById[String(s.id)]) {
        sectionTitleById[String(s.id)] = s.title || "Complementares";
      }
    });
    const grouped = {};
    state.customQuestions.forEach((q) => {
      const key = String(q.section_ref || "");
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(q);
    });
    const out = [];
    Object.keys(grouped).forEach((key) => {
      const title = sectionTitleById[key] || "Sessão";
      out.push(`<li class="ms-q-group-title">${escapeHtml(title)}</li>`);
      grouped[key].forEach((q) => {
        const frozen = q.frozen_in_supplementary_snapshot_at
          ? `<span class="ms-q-supp-badge">complementar</span>`
          : "";
        out.push(
          `<li class="ms-q-item"><strong>${escapeHtml(q.text || "")}</strong>` +
          `<span class="ms-q-item-meta">${escapeHtml(q.question_type || "")}${q.is_required ? " · obrigatória" : ""}${frozen}</span>` +
          `</li>`
        );
      });
    });
    el.questionsList.innerHTML = out.join("");
  }

  // -------------------- NOTAS --------------------
  function classifyNote(content) {
    const lower = String(content || "").toLowerCase();
    if (lower.includes("dúvida") || lower.includes("duvida") || lower.includes("?")) {
      return { type: "doubt", label: "Dúvida" };
    }
    if (lower.includes("pergunta")) {
      return { type: "question", label: "Pergunta" };
    }
    return { type: "observation", label: "Observação" };
  }

  function _sortNotes(arr) {
    return arr.slice().sort((a, b) => {
      const pa = a.is_pinned ? 1 : 0;
      const pb = b.is_pinned ? 1 : 0;
      if (pa !== pb) return pb - pa;
      const ta = new Date(a.created_at || 0).getTime();
      const tb = new Date(b.created_at || 0).getTime();
      return tb - ta;
    });
  }

  function renderNotes() {
    if (!el.notesList || !el.noteTpl) return;
    if (!state.notes.length) {
      el.notesList.innerHTML = '<li class="cl-empty">Nenhuma nota ainda.</li>';
      return;
    }
    const frag = document.createDocumentFragment();
    const seen = new Set();
    const sorted = _sortNotes(state.notes);
    for (let i = 0; i < sorted.length; i++) {
      const n = sorted[i];
      const key = String(n.id);
      if (seen.has(key)) continue;
      seen.add(key);

      const node = el.noteTpl.content.cloneNode(true);
      const li = node.querySelector(".ms-note-item");
      if (!li) continue;
      li.dataset.id = n.id;
      if (n.is_pinned) li.classList.add("is-pinned");

      const { type, label } = classifyNote(n.content);
      const typeEl = li.querySelector(".ms-note-type");
      if (typeEl) {
        typeEl.dataset.type = type;
        typeEl.textContent = label;
      }
      const whenEl = li.querySelector(".ms-note-when");
      if (whenEl) whenEl.textContent = relativeTime(n.created_at);
      const authorEl = li.querySelector(".ms-note-author");
      if (authorEl) authorEl.textContent = n.author_name || n.author_email || "—";
      const textEl = li.querySelector(".ms-note-text");
      if (textEl) {
        textEl.textContent = n.content || "";
        textEl.title = n.content || "";
      }

      const actions = li.querySelector(".ms-note-actions");
      if (actions) {
        const pinBtn = document.createElement("button");
        pinBtn.type = "button";
        pinBtn.className = "cl-icon-btn ms-note-pin" + (n.is_pinned ? " is-pinned" : "");
        pinBtn.setAttribute("data-note-action", "pin");
        pinBtn.setAttribute("aria-label", n.is_pinned ? "Desafixar nota" : "Fixar nota");
        pinBtn.title = n.is_pinned ? "Desafixar" : "Fixar no topo";
        pinBtn.innerHTML = `<i data-lucide="pin"></i>`;
        actions.insertBefore(pinBtn, actions.firstChild);
      }

      frag.appendChild(li);
    }
    el.notesList.innerHTML = "";
    el.notesList.appendChild(frag);
    refreshIcons();
  }

  async function reloadNotesFromBackend() {
    if (!state.activeId) return;
    try {
      const notes = await api(`/api/briefings/${state.activeId}/notes/`);
      const seen = new Set();
      const dedup = [];
      (Array.isArray(notes) ? notes : []).forEach((n) => {
        const key = String(n.id);
        if (seen.has(key)) return;
        seen.add(key);
        dedup.push(n);
      });
      state.notes = _sortNotes(dedup);
      const cached = state.detailCache.get(String(state.activeId));
      if (cached) cached.notes = state.notes;
      renderNotes();
    } catch (err) {
      console.warn("[mesa] falha ao recarregar notas", err);
    }
  }

  async function createNote(content) {
    if (!state.activeId) return;
    if (state.noteSaving) return;
    const text = (content || "").trim();
    if (!text) return;

    const now = Date.now();
    if (
      state.lastNoteText === text &&
      now - state.lastNoteTs < NOTE_DUPLICATE_WINDOW_MS
    ) {
      return;
    }

    // Reserva ANTES do POST. Isso bloqueia cliques/entradas
    // repetidos enquanto a requisição está em voo.
    state.noteSaving = true;
    state.lastNoteText = text;
    state.lastNoteTs = now;
    setButtonLoading(el.noteSave, true);
    try {
      await api(`/api/briefings/${state.activeId}/notes/`, {
        method: "POST",
        body: { content: text },
      });
      state.detailCache.delete(String(state.activeId));
      if (el.noteInput) el.noteInput.value = "";
      await reloadNotesFromBackend();
    } catch (err) {
      console.warn("[mesa] falha ao criar nota", err);
      showAlert({
        title: "Não foi possível salvar",
        message: err.message || "Tente novamente.",
        variant: "danger",
      });
    } finally {
      state.noteSaving = false;
      setButtonLoading(el.noteSave, false);
    }
  }

  async function updateNote(noteId, content) {
    if (!state.activeId || !noteId) return;
    const text = (content || "").trim();
    if (!text) return;
    try {
      await api(
        `/api/briefings/${state.activeId}/notes/${noteId}/`,
        { method: "PATCH", body: { content: text } },
      );
      state.detailCache.delete(String(state.activeId));
      await reloadNotesFromBackend();
    } catch (err) {
      console.warn("[mesa] falha ao editar nota", err);
      showAlert({
        title: "Não foi possível editar",
        message: err.message || "Tente novamente.",
        variant: "danger",
      });
    }
  }

  async function toggleNotePin(noteId) {
    if (!state.activeId || !noteId) return;
    const current = state.notes.find(
      (n) => String(n.id) === String(noteId)
    );
    if (!current) return;

    const nextPinned = !current.is_pinned;
    const previousPinned = current.is_pinned;
    current.is_pinned = nextPinned;
    state.notes = _sortNotes(state.notes);
    renderNotes();

    try {
      await api(
        `/api/briefings/${state.activeId}/notes/${noteId}/`,
        { method: "PATCH", body: { is_pinned: nextPinned } },
      );
      state.detailCache.delete(String(state.activeId));
      await reloadNotesFromBackend();
    } catch (err) {
      current.is_pinned = previousPinned;
      state.notes = _sortNotes(state.notes);
      renderNotes();
      console.warn("[mesa] falha ao fixar nota", err);
      showAlert({
        title: "Não foi possível fixar",
        message: err.message || "Tente novamente.",
        variant: "danger",
      });
    }
  }

  async function deleteNote(noteId) {
    if (!state.activeId || !noteId) return;
    try {
      await api(`/api/briefings/${state.activeId}/notes/${noteId}/`, { method: "DELETE" });
      state.detailCache.delete(String(state.activeId));
      await reloadNotesFromBackend();
    } catch (err) {
      console.warn("[mesa] falha ao excluir nota", err);
      showAlert({
        title: "Não foi possível excluir",
        message: err.message || "Tente novamente.",
        variant: "danger",
      });
    }
  }

  // -------------------- EDITOR DE NOTA (estilo Apple/Notion) --------------------
  function openNoteEditor(noteId) {
    if (!state.activeId || !noteId) return;
    const note = state.notes.find((n) => String(n.id) === String(noteId));
    if (!note) return;

    state.editingNoteId = String(noteId);

    if (el.noteEditorTitle) el.noteEditorTitle.textContent = "Editar nota";
    if (el.noteEditorInput) {
      el.noteEditorInput.value = note.content || "";
      el.noteEditorInput.disabled = false;
    }
    if (el.noteEditorSave) {
      el.noteEditorSave.classList.remove("is-loading");
      el.noteEditorSave.disabled = false;
      const label = el.noteEditorSave.querySelector(".ms-btn-label");
      if (label) label.textContent = "Salvar";
    }

    openModal(el.modalNoteEditor);

    setTimeout(() => {
      if (el.noteEditorInput) {
        el.noteEditorInput.focus();
        const len = el.noteEditorInput.value.length;
        try { el.noteEditorInput.setSelectionRange(len, len); } catch (_) {}
      }
    }, 60);
  }

  async function submitNoteEditor() {
    if (state.noteEditorSaving) return;
    const noteId = state.editingNoteId;
    if (!noteId) return;

    const value = el.noteEditorInput ? el.noteEditorInput.value : "";
    const text = (value || "").trim();
    if (!text) {
      showAlert({
        title: "Nota vazia",
        message: "Escreva algo antes de salvar.",
        variant: "danger",
      });
      return;
    }

    state.noteEditorSaving = true;
    setButtonLoading(el.noteEditorSave, true);

    try {
      await api(
        `/api/briefings/${state.activeId}/notes/${noteId}/`,
        { method: "PATCH", body: { content: text } },
      );
      state.detailCache.delete(String(state.activeId));
      closeModal(el.modalNoteEditor);
      state.editingNoteId = null;
      await reloadNotesFromBackend();
    } catch (err) {
      console.warn("[mesa] falha ao editar nota", err);
      showAlert({
        title: "Não foi possível editar",
        message: err.message || "Tente novamente.",
        variant: "danger",
      });
    } finally {
      state.noteEditorSaving = false;
      setButtonLoading(el.noteEditorSave, false);
    }
  }

  function bindNoteEditor() {
    if (el.noteEditorSave) {
      el.noteEditorSave.addEventListener("click", submitNoteEditor);
    }
    if (el.noteEditorInput) {
      el.noteEditorInput.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          submitNoteEditor();
        }
      });
    }
  }

  // -------------------- SIDE --------------------
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
        if (small) small.textContent = "";
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
    if (el.briefSummary && state.detail) {
      el.briefSummary.textContent = state.detail.description || "—";
    }
  }

  // -------------------- MOODBOARD --------------------
  function _collectClientImages(detail) {
    if (!detail) return [];

    if (Array.isArray(detail.moodboard_images) && detail.moodboard_images.length) {
      return detail.moodboard_images.map((img) => ({
        document_id: String(img.id || ''),
        url: img.url || '',
        name: img.name || '',
        kind: img.kind || 'upload',
        question_id: String(img.question_id || ''),
      })).filter((img) => img.url);
    }

    const result = [];
    const seen = new Set();
    const answers = (detail && detail.answers) || [];
    answers.forEach((a) => {
      const atts = a.attachments || [];
      atts.forEach((att) => {
        if (!att || !att.id) return;
        if (!att.file_url) return;
        const key = String(att.id);
        if (seen.has(key)) return;
        seen.add(key);
        result.push({
          document_id: key,
          url: att.file_url,
          name: att.name || '',
          kind: 'upload',
          question_id: String(a.question_id || ''),
        });
      });
    });
    return result;
  }

  function renderMoodboard() {
    if (!el.moodboardGrid) return;
    const images = _collectClientImages(state.detail);

    if (el.moodboardCount) {
      if (images.length === 0) {
        el.moodboardCount.textContent = "";
      } else {
        el.moodboardCount.textContent =
          `${images.length} imagem${images.length === 1 ? "" : "s"} do cliente`;
      }
    }

    if (!images.length) {
      el.moodboardGrid.innerHTML =
        '<div class="ms-moodboard-empty">' +
        '<i data-lucide="images"></i>' +
        '<span>Nenhuma imagem enviada pelo cliente.</span>' +
        '</div>';
      refreshIcons();
      return;
    }

    const frag = document.createDocumentFragment();
    images.forEach((img) => {
      const card = document.createElement("div");
      card.className = "ms-moodboard-item";
      card.dataset.kind = img.kind || "upload";

      const elImg = document.createElement("img");
      elImg.src = img.url;
      elImg.alt = img.name || "Imagem do cliente";
      elImg.loading = "lazy";
      elImg.addEventListener("error", () => {
        elImg.replaceWith(
          Object.assign(document.createElement("div"), {
            className: "ms-moodboard-item-error",
            textContent: "Falha ao carregar",
          })
        );
      });
      elImg.addEventListener("click", (e) => {
        e.stopPropagation();
        openImageViewer(img.url);
      });
      card.appendChild(elImg);
      frag.appendChild(card);
    });
    el.moodboardGrid.innerHTML = "";
    el.moodboardGrid.appendChild(frag);
    refreshIcons();
  }

  // -------------------- AÇÕES --------------------
  function publicId() { return state.root.dataset.workspacePublicId || ""; }
  function openBriefingPage() {
      if (!state.activeId) return;
      const pid = (window.Clivo && window.Clivo.workspacePublicIdFromUrl) || '';
      if (!pid) {
          showAlert({
              title: "Workspace não identificado",
              message: "Recarregue a página para continuar.",
              variant: "danger",
          });
          return;
      }
      const url = `/w/${pid}/briefings/${state.activeId}/resumo/`;
      window.open(url, "_blank", "noopener,noreferrer");
  }
  function openEditView() {
    if (!state.detail) return;
    const d = state.detail;
    if (el.editTitleInput) el.editTitleInput.value = d.title || "";
    if (el.editExpiresInput) el.editExpiresInput.value = toLocalDateTimeInput(d.expires_at);
    if (el.editStatusInput) el.editStatusInput.value = d.status || "in_progress";
    if (el.editIntroInput) el.editIntroInput.value = d.intro_message || "";
    if (el.editClientInput) el.editClientInput.value = d.client_name || "—";
    setDetailView("edit");
    setTimeout(() => { if (el.editTitleInput) el.editTitleInput.focus(); }, 60);
  }

  // -------------------- NOVA PERGUNTA --------------------
  function resetNewQuestionState() {
    state.newQType = "text";
    state.newQOptions = [];
    if (el.newQText) el.newQText.value = "";
    if (el.newQInstructions) el.newQInstructions.value = "";
    if (el.newQType) el.newQType.value = "text";
    if (el.newQRequired) el.newQRequired.checked = true;
    const formatBoxes = state.root.querySelectorAll('input[name="msNewQFormat"]');
    formatBoxes.forEach((box) => { box.checked = true; });
    state.root.querySelectorAll(".ms-nq-type-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.type === "text");
    });
    renderNewQOptions();
    syncNewQTypeUI();
  }

  function syncNewQTypeUI() {
    const isChoice = CHOICE_TYPES.has(state.newQType);
    if (el.newQOptionsSection) {
      el.newQOptionsSection.classList.toggle("is-hidden", !isChoice);
    }
    if (isChoice && state.newQOptions.length === 0) {
      state.newQOptions.push({ text: "", image_url: "", image_document_id: null });
      state.newQOptions.push({ text: "", image_url: "", image_document_id: null });
      renderNewQOptions();
    }
  }

  function renderNewQOptions() {
    if (!el.newQOptionsList) return;
    el.newQOptionsList.innerHTML = "";
    const frag = document.createDocumentFragment();
    state.newQOptions.forEach((opt, idx) => {
      const row = document.createElement("div");
      row.className = "ms-nq-option-row";

      const thumb = document.createElement("label");
      thumb.className = "ms-nq-option-thumb";
      thumb.title = opt.image_url ? "Trocar imagem" : "Adicionar imagem";
      if (opt.image_url) {
        const img = document.createElement("img");
        img.src = opt.image_url;
        img.alt = "";
        img.addEventListener("error", () => {
          thumb.innerHTML = '<i data-lucide="image-plus"></i>';
          refreshIcons();
        });
        thumb.appendChild(img);
      } else {
        thumb.innerHTML = '<i data-lucide="image-plus"></i>';
      }

      const fileInput = document.createElement("input");
      fileInput.type = "file";
      fileInput.accept = "image/*";
      fileInput.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        opt._file = file;
        if (opt.image_url && opt.image_url.startsWith("blob:")) {
          URL.revokeObjectURL(opt.image_url);
        }
        opt.image_url = URL.createObjectURL(file);
        renderNewQOptions();
      });
      thumb.appendChild(fileInput);

      const input = document.createElement("input");
      input.type = "text";
      input.className = "ms-nq-option-input";
      input.placeholder = "Nome da opção";
      input.value = opt.text || "";
      input.maxLength = 200;
      input.addEventListener("input", () => { opt.text = input.value; });

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "ms-nq-option-remove";
      remove.title = "Remover";
      remove.innerHTML = '<i data-lucide="x"></i>';
      remove.addEventListener("click", () => {
        if (opt.image_url && opt.image_url.startsWith("blob:")) {
          URL.revokeObjectURL(opt.image_url);
        }
        state.newQOptions.splice(idx, 1);
        renderNewQOptions();
      });

      row.appendChild(thumb);
      row.appendChild(input);
      row.appendChild(remove);
      frag.appendChild(row);
    });
    el.newQOptionsList.appendChild(frag);
    refreshIcons();
  }

  function openNewQuestionView() {
    if (!state.detail) return;
    populateNewQSection();
    resetNewQuestionState();
    setDetailView("new-question");
    setTimeout(() => { if (el.newQText) el.newQText.focus(); }, 60);
  }
  function populateNewQSection() {
    if (!el.newQSection) return;
    const snap = (state.detail && state.detail.structure_snapshot) || {};
    const sections = Array.isArray(snap.sections) ? snap.sections : [];
    el.newQSection.innerHTML = "";
    if (!sections.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Nenhuma sessão disponível";
      el.newQSection.appendChild(opt);
      return;
    }
    sections.forEach((s, i) => {
      const opt = document.createElement("option");
      opt.value = String(s.id || "");
      opt.textContent = `${i + 1}. ${s.title || "Sessão"}`;
      el.newQSection.appendChild(opt);
    });
  }

  async function uploadOptionImage(file) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", "image");
    return await api("/api/documents/", { method: "POST", body: fd });
  }

  async function submitNewQuestionForm(ev) {
    ev.preventDefault();
    if (!state.activeId) return;
    const sectionId = el.newQSection ? el.newQSection.value : "";
    const text = el.newQText ? el.newQText.value.trim() : "";
    const instructions = el.newQInstructions ? el.newQInstructions.value.trim() : "";
    const qType = state.newQType || "text";
    const isRequired = el.newQRequired ? el.newQRequired.checked : true;
    const formats = Array.from(state.root.querySelectorAll('input[name="msNewQFormat"]:checked'))
      .map((c) => c.value);

    if (!sectionId) {
      showAlert({ title: "Sessão obrigatória", message: "Escolha a sessão da pergunta.", variant: "danger" });
      return;
    }
    if (!text) {
      showAlert({ title: "Enunciado obrigatório", message: "Escreva o enunciado.", variant: "danger" });
      return;
    }
    if (!formats.length) {
      showAlert({ title: "Formatos obrigatórios", message: "Selecione ao menos um formato.", variant: "danger" });
      return;
    }

    let optionsPayload = undefined;
    if (CHOICE_TYPES.has(qType)) {
      const cleanOpts = state.newQOptions
        .map((o) => ({ ...o, text: (o.text || "").trim() }))
        .filter((o) => o.text);
      if (cleanOpts.length < 2) {
        showAlert({ title: "Opções insuficientes", message: "Adicione pelo menos 2 opções com texto.", variant: "danger" });
        return;
      }

      setButtonLoading(el.newQSubmit, true);
      try {
        for (const opt of cleanOpts) {
          if (opt._file) {
            const doc = await uploadOptionImage(opt._file);
            if (doc && doc.id) {
              opt.image_document_id = doc.id;
            } else {
              opt.image_document_id = null;
            }
            opt._file = null;
          }
        }
      } catch (err) {
        setButtonLoading(el.newQSubmit, false);
        showAlert({
          title: "Falha ao enviar imagem",
          message: (err && err.message) || "Tente novamente.",
          variant: "danger",
        });
        return;
      }

      optionsPayload = cleanOpts.map((o) => ({
        text: o.text,
        image_document_id: o.image_document_id || null,
      }));
    }

    const body = {
      section_ref: sectionId,
      text,
      instructions,
      question_type: qType,
      allowed_response_formats: formats,
      is_required: isRequired,
    };
    if (optionsPayload !== undefined) body.options = optionsPayload;

    setButtonLoading(el.newQSubmit, true);
    try {
      await api(`/api/briefings/${state.activeId}/custom-questions/`, {
        method: "POST",
        body,
      });
      state.detailCache.delete(String(state.activeId));
      const bundle = await fetchBriefingBundle(state.activeId);
      putCachedDetail(state.activeId, bundle.detail, bundle.events, bundle.notes, bundle.customQuestions);
      hydrateDetail(state.activeId, bundle);
      setActiveTab("questions");
      backToDetail();
      reloadListFromBackend();
    } catch (err) {
      console.warn("[mesa] falha ao criar pergunta", err);
      showAlert({
        title: "Não foi possível criar",
        message: (err && err.message) || "Tente novamente.",
        variant: "danger",
      });
    } finally {
      setButtonLoading(el.newQSubmit, false);
    }
  }

  async function submitEditForm(ev) {
    ev.preventDefault();
    if (!state.detail || !state.activeId) return;
    const newTitle = (el.editTitleInput ? el.editTitleInput.value : "").trim();
    const newExpires = el.editExpiresInput ? el.editExpiresInput.value : "";
    const newStatus = el.editStatusInput ? el.editStatusInput.value : "";
    const newIntro = el.editIntroInput ? el.editIntroInput.value : "";
    if (!newTitle) {
      showAlert({ title: "Título obrigatório", message: "Informe um título.", variant: "danger" });
      return;
    }
    const id = state.activeId;
    setButtonLoading(el.editSubmit, true);
    try {
      const payload = {};
      if (newTitle !== (state.detail.title || "")) payload.title = newTitle;
      if (newIntro !== (state.detail.intro_message || "")) payload.intro_message = newIntro;
      if (newExpires) payload.expires_at = new Date(newExpires).toISOString();
      if (newStatus && newStatus !== state.detail.status) payload.status = newStatus;
      if (!Object.keys(payload).length) { backToDetail(); return; }
      let updated = null;
      try {
        updated = await api(`/api/briefings/${id}/`, {
          method: "PATCH",
          body: payload,
        });
      } catch (patchErr) {
        if ((patchErr.status === 404 || patchErr.status === 405) && payload.status) {
          const action = {
            in_progress: "resume",
            paused: "pause",
            cancelled: "close",
            completed: null,
          }[payload.status];
          if (action) {
            await api(`/api/briefings/${id}/${action}/`, { method: "POST" });
          }
          updated = state.detail;
        } else {
          throw patchErr;
        }
      }
      const merged = Object.assign({}, state.detail, updated || payload);
      state.detail = merged;
      const idx = state.briefings.findIndex((x) => String(x.id) === String(id));
      if (idx !== -1) {
        state.briefings[idx] = Object.assign({}, state.briefings[idx], merged, {
          _derived: deriveState(merged),
          _ts: merged.updated_at ? new Date(merged.updated_at).getTime() : (state.briefings[idx]._ts || 0),
        });
      }
      state.detailCache.delete(String(id));
      applyDetailToHeader(merged);
      renderFilterCounts();
      renderList();
      backToDetail();
    } catch (err) {
      console.warn("[mesa] falha ao salvar edição", err);
      showAlert({
        title: "Não foi possível salvar",
        message: (err && err.message) || "Tente novamente.",
        variant: "danger",
      });
    } finally {
      setButtonLoading(el.editSubmit, false);
    }
  }

  async function triggerReanalysis() {
    if (!state.activeId || !el.reanalyzeBtn) return;
    const id = state.activeId;
    if (el.reanalyzeBtn.classList.contains("is-loading")) return;

    el.reanalyzeBtn.classList.add("is-loading");
    el.reanalyzeBtn.disabled = true;
    const startedAt = Date.now();
    try {
      const result = await api(`/api/intelligence/briefings/${id}/reanalyze/`, {
        method: "POST", body: {},
      });
      const jobId = (result && result.job_id) || "";
      const elapsed = Date.now() - startedAt;
      const wait = Math.max(0, 400 - elapsed);
      if (wait > 0) await new Promise((res) => setTimeout(res, wait));
      showAlert({
        title: "Análise agendada",
        message: jobId
          ? `Job ${String(jobId).slice(0, 8)} enfileirado. O resultado aparecerá na coluna Insight.`
          : "A análise foi enfileirada. O resultado aparecerá na coluna Insight.",
        variant: "info",
      });
    } catch (err) {
      if (err && err.status === 404) {
        showAlert({
          title: "Análise manual indisponível",
          message: "O endpoint de reanálise manual ainda não está disponível neste ambiente. O backend precisa ser atualizado.",
          variant: "danger",
        });
      } else if (err && err.status === 403) {
        showAlert({
          title: "Sem permissão",
          message: "Sua governança não permite disparar nova análise.",
          variant: "danger",
        });
      } else if (err && err.status === 400) {
        showAlert({
          title: "Análise bloqueada",
          message: (err && err.message) || "A política de quota bloqueou a execução.",
          variant: "danger",
        });
      } else {
        showAlert({
          title: "Falha ao agendar",
          message: (err && err.message) || "Tente novamente.",
          variant: "danger",
        });
      }
    } finally {
      el.reanalyzeBtn.classList.remove("is-loading");
      el.reanalyzeBtn.disabled = false;
    }
  }

  function triggerReopen() {
    if (!state.activeId) return;
    const id = state.activeId;
    if (!state.detail) return;

    const allowed = new Set(["paused", "cancelled", "completed"]);
    if (!allowed.has(state.detail.status)) {
      showAlert({
        title: "Não é possível reabrir",
        message: "Só é possível reabrir briefings pausados, concluídos ou cancelados.",
        variant: "danger",
      });
      return;
    }

    confirmAction({
      title: "Reabrir briefing?",
      subtitle: "O briefing voltará a aceitar respostas. Se o prazo estiver expirado, informe um novo prazo em Editar antes.",
      confirmLabel: "Reabrir",
      confirmVariant: "primary",
      icon: "rotate-ccw",
      onConfirm: async () => {
        try {
          const updated = await api(`/api/briefings/${id}/reopen/`, {
            method: "POST",
            body: {},
          });
          const merged = Object.assign({}, state.detail, updated);
          state.detail = merged;
          const idx = state.briefings.findIndex((x) => String(x.id) === String(id));
          if (idx !== -1) {
            state.briefings[idx] = Object.assign({}, state.briefings[idx], merged, {
              _derived: deriveState(merged),
            });
          }
          state.detailCache.delete(String(id));
          applyDetailToHeader(merged);
          renderFilterCounts();
          renderList();
        } catch (err) {
          if (err && err.status === 409) {
            showAlert({
              title: "Reabertura bloqueada",
              message: (err && err.message) || "O briefing precisa de um novo prazo antes de reabrir.",
              variant: "danger",
            });
          } else {
            showAlert({
              title: "Não foi possível reabrir",
              message: (err && err.message) || "Tente novamente.",
              variant: "danger",
            });
          }
        }
      },
    });
  }

  function deleteBriefing() {
    if (!state.activeId) return;
    const id = state.activeId;
    const current = state.briefings.find((x) => String(x.id) === String(id));
    const title = (current && current.title) || "este briefing";
    confirmAction({
      title: "Excluir briefing?",
      subtitle: `O briefing "${title}" e todas as notas/respostas serão removidos. Esta ação não pode ser desfeita.`,
      confirmLabel: "Excluir",
      confirmVariant: "danger",
      icon: "trash-2",
      onConfirm: async () => {
        try {
          await api(`/api/briefings/${id}/`, { method: "DELETE" });
        } catch (err) {
          console.error("[mesa] falha ao excluir", err);
          showAlert({
            title: "Não foi possível excluir",
            message: (err && err.message) || "Tente novamente.",
            variant: "danger",
          });
          throw err;
        }
        state.detailCache.delete(String(id));
        state.prefetching.delete(String(id));
        state.briefings = state.briefings.filter((x) => String(x.id) !== String(id));
        state.activeId = null;
        state.detail = null;
        state.events = [];
        state.notes = [];
        state.customQuestions = [];
        renderFilterCounts();
        syncFilterActive();
        renderList();
        if (state.briefings.length) {
          const next = state.briefings[0];
          state.activeId = next.id;
          const li = el.list && el.list.querySelector(`.ms-brief[data-id="${next.id}"]`);
          if (li) li.classList.add("is-active");
          loadBriefing(next.id);
        } else {
          resetDetailPanel();
        }
      },
    });
  }
  function resetDetailPanel() {
    if (el.crumbCurrent) el.crumbCurrent.textContent = "—";
    if (el.detailTitle) el.detailTitle.textContent = "—";
    if (el.detailClient) el.detailClient.textContent = "—";
    if (el.detailCreated) el.detailCreated.textContent = "—";
    if (el.detailExpires) el.detailExpires.textContent = "—";
    if (el.detailActivity) el.detailActivity.textContent = "—";
    if (el.detailSuppPill) el.detailSuppPill.classList.add("hidden");
    if (el.notesList) el.notesList.innerHTML = '<li class="cl-empty">Nenhuma nota ainda.</li>';
    if (el.questionsList) el.questionsList.innerHTML = '<li class="cl-empty">Nenhuma pergunta adicional.</li>';
    if (el.historyList) el.historyList.innerHTML = '<li class="cl-empty">Sem eventos registrados.</li>';
    if (el.briefSummary) el.briefSummary.textContent = "—";
    if (el.tagsList) el.tagsList.innerHTML = '<span class="ms-tag ms-tag--empty">—</span>';
    if (el.moodboardCount) el.moodboardCount.textContent = "";
    renderMoodboard();
    setDetailView("detail");
  }

  function setFilter(filter) {
    if (state.filter === filter) return;
    state.filter = filter;
    syncFilterActive();
    renderList();
  }
  function onSearch() {
    const q = el.search ? el.search.value : "";
    if (q === state.query) return;
    state.query = q;
    renderList();
  }

  function bindEvents() {
    if (el.filterAllBtn) el.filterAllBtn.addEventListener("click", () => setFilter("all"));
    if (el.kpis) {
      el.kpis.addEventListener("click", (e) => {
        const btn = e.target.closest(".ms-filter");
        if (!btn) return;
        const map = { open: "progress", pending: "pending", done: "done" };
        if (map[btn.dataset.kpi]) setFilter(map[btn.dataset.kpi]);
      });
    }
    if (el.search) el.search.addEventListener("input", debounce(onSearch, 80));
    if (el.tabs) {
      el.tabs.addEventListener("click", (e) => {
        const btn = e.target.closest(".cl-tab");
        if (btn) setActiveTab(btn.dataset.tab || "summary");
      });
    }
    if (el.list) {
      el.list.addEventListener("mouseover", (e) => {
        const item = e.target.closest(".ms-brief");
        if (item) prefetchBriefing(item.dataset.id);
      });
      el.list.addEventListener("focusin", (e) => {
        const item = e.target.closest(".ms-brief");
        if (item) prefetchBriefing(item.dataset.id);
      });
      el.list.addEventListener("click", (e) => {
        const item = e.target.closest(".ms-brief");
        if (!item) return;
        const id = item.dataset.id;
        if (!id || id === state.activeId) return;
        const now = Date.now();
        if (now - state.lastClickTs < 80) return;
        state.lastClickTs = now;
        const prev = el.list.querySelector(".ms-brief.is-active");
        if (prev) prev.classList.remove("is-active");
        item.classList.add("is-active");
        if (el.body) el.body.classList.add("detail-open");
        backToDetail();
        loadBriefing(id);
      });
    }
    if (el.back && el.body) {
      el.back.addEventListener("click", () => el.body.classList.remove("detail-open"));
    }
    if (el.viewBtn) el.viewBtn.addEventListener("click", openBriefingPage);
    if (el.reanalyzeBtn) el.reanalyzeBtn.addEventListener("click", triggerReanalysis);

    if (el.editForm) el.editForm.addEventListener("submit", submitEditForm);
    if (el.editBack) el.editBack.addEventListener("click", backToDetail);
    if (el.editCancel) el.editCancel.addEventListener("click", backToDetail);

    if (el.addCustomQuestionBtn) el.addCustomQuestionBtn.addEventListener("click", openNewQuestionView);
    if (el.newQForm) el.newQForm.addEventListener("submit", submitNewQuestionForm);
    if (el.newQBack) el.newQBack.addEventListener("click", backToDetail);
    if (el.newQCancel) el.newQCancel.addEventListener("click", backToDetail);

    state.root.querySelectorAll(".ms-nq-type-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const type = btn.dataset.type || "text";
        state.newQType = type;
        if (el.newQType) el.newQType.value = type;
        state.root.querySelectorAll(".ms-nq-type-btn").forEach((b) => {
          b.classList.toggle("is-active", b === btn);
        });
        syncNewQTypeUI();
      });
    });

    if (el.newQAddOptionBtn) {
      el.newQAddOptionBtn.addEventListener("click", () => {
        state.newQOptions.push({ text: "", image_url: "", image_document_id: null });
        renderNewQOptions();
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
          if (!state.noteSaving) createNote(el.noteInput.value);
        }
      });
    }
    [el.noteAttach, el.noteImage, el.noteMention].forEach((btn) => {
      if (!btn) return;
      btn.addEventListener("click", () => {
        if (el.noteInput) el.noteInput.focus();
      });
    });
    if (el.notesList) {
      el.notesList.addEventListener("click", (e) => {
        const li = e.target.closest(".ms-note-item");
        if (!li) return;
        const noteId = li.dataset.id;
        if (!noteId) return;

        const actionBtn = e.target.closest("[data-note-action]");
        if (actionBtn) {
          const action = actionBtn.dataset.noteAction;

          if (action === "pin") {
            toggleNotePin(noteId);
            return;
          }
          if (action === "delete") {
            confirmAction({
              title: "Excluir nota?",
              subtitle: "Esta ação não pode ser desfeita.",
              confirmLabel: "Excluir",
              confirmVariant: "danger",
              icon: "trash-2",
              onConfirm: () => deleteNote(noteId),
            });
            return;
          }
          if (action === "edit") {
            openNoteEditor(noteId);
            return;
          }
          return;
        }

        // Clique na linha (fora dos botões) abre o editor.
        openNoteEditor(noteId);
      });
    }

    bindNoteEditor();
  }

  async function loadAll() {
    try {
      const list = await api("/api/briefings/");
      state.briefings = (Array.isArray(list) ? list : []).map((b) => {
        const updatedAt = b.updated_at || b.created_at || null;
        return Object.assign({}, b, {
          progress: b.progress || {},
          supplementary_state: b.supplementary_state || {},
          _derived: deriveState(b),
          _ts: updatedAt ? new Date(updatedAt).getTime() || 0 : 0,
        });
      });
      renderFilterCounts();
      syncFilterActive();
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
        resetDetailPanel();
      }
    } catch (err) {
      console.error("[mesa] falha ao carregar lista", err, err && err.status, err && err.payload);
      if (el.list)
        el.list.innerHTML = '<li class="cl-empty">Não foi possível carregar os briefings.</li>';
    }
  }

  async function reloadListFromBackend() {
    try {
      const list = await api("/api/briefings/");
      state.briefings = (Array.isArray(list) ? list : []).map((b) => {
        const updatedAt = b.updated_at || b.created_at || null;
        return Object.assign({}, b, {
          progress: b.progress || {},
          supplementary_state: b.supplementary_state || {},
          _derived: deriveState(b),
          _ts: updatedAt ? new Date(updatedAt).getTime() || 0 : 0,
        });
      });
      renderFilterCounts();
      renderList();
    } catch (err) {
      console.warn("[mesa] falha ao recarregar lista", err);
    }
  }

  function mount() {
    const root = document.getElementById("msPage");
    if (!root) {
      console.warn("[mesa] #msPage não encontrado — abortando mount");
      return;
    }
    if (state.mounted && state.root === root) {
      return;
    }

    state.root = root;
    state.mounted = true;
    state.bound = false;

    state.briefings = [];
    state.filtered = [];
    state.activeId = null;
    state.filter = "all";
    state.query = "";
    state.detail = null;
    state.notes = [];
    state.events = [];
    state.client = null;
    state.customQuestions = [];
    state.activeTab = "summary";
    state.activeView = "detail";
    state.listCache = new Map();
    state.detailCache = new Map();
    state.prefetching = new Set();
    state.lastClickTs = 0;
    state.newQType = "text";
    state.newQOptions = [];
    state.kebabOpen = false;
    state.viewerUrl = "";
    state.noteSaving = false;
    state.lastNoteText = "";
    state.lastNoteTs = 0;
    state.editingNoteId = null;
    state.noteEditorSaving = false;
    if (state.abortDetail) {
      try { state.abortDetail.abort(); } catch (e) {}
      state.abortDetail = null;
    }

    cacheElements();
    applyGreeting();
    bindModalClosers();
    bindConfirm();
    bindPrompt();
    bindKebab();
    bindImageViewer();
    bindEvents();
    setActiveTab("summary");
    setDetailView("detail");
    renderMoodboard();
    loadAll();
    state.bound = true;
  }

  function unmount() {
    state.mounted = false;
    if (state.abortDetail) {
      try { state.abortDetail.abort(); } catch (e) {}
      state.abortDetail = null;
    }
    state.listCache = new Map();
    state.detailCache = new Map();
    state.prefetching = new Set();
    document.querySelectorAll(".ms-modal-overlay.is-open").forEach((ov) => {
      ov.classList.remove("is-open");
    });
    document.body.classList.remove("ms-modal-open");
    document.body.style.overflow = "";
    closeKebab();
  }

  window.ClivoPages = window.ClivoPages || {};
  window.ClivoPages.mesa = { mount, unmount };

  function autoMount() {
    if (document.getElementById("msPage")) {
      mount();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoMount);
  } else {
    autoMount();
  }
})();