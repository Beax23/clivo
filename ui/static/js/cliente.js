/* =========================================================================
   CLIENTES — v12
   - Nova análise: sem popup; dispara POST, faz polling do job e
     recarrega o bundle do cliente quando o worker conclui.
   ========================================================================= */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) =>
    Array.prototype.slice.call((r || document).querySelectorAll(s));

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getCookie(name) {
    const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? decodeURIComponent(m.pop()) : "";
  }

  function api(path, opts) {
    opts = opts || {};
    const headers = Object.assign(
      { Accept: "application/json" },
      opts.headers || {},
    );
    if (
      opts.body &&
      typeof opts.body === "object" &&
      !(opts.body instanceof FormData)
    ) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    if (!/^(GET|HEAD|OPTIONS)$/i.test(opts.method || "GET")) {
      headers["X-CSRFToken"] = getCookie("csrftoken");
    }
    return fetch(
      path,
      Object.assign({ credentials: "same-origin" }, opts, { headers }),
    ).then((r) => {
      if (!r.ok) {
        return r.text().then((t) => {
          let p;
          try {
            p = JSON.parse(t);
          } catch (e) {
            p = { error: t || r.statusText };
          }
          throw Object.assign(new Error(p.error || "Erro"), {
            status: r.status,
            payload: p,
          });
        });
      }
      const ct = r.headers.get("content-type") || "";
      return ct.includes("application/json") ? r.json() : r.text();
    });
  }

  function refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      requestAnimationFrame(() => {
        try {
          window.lucide.createIcons();
        } catch (e) {}
      });
    }
  }
  function showToast(msg, type) {
    if (typeof window.clivoShowToast === "function") {
      window.clivoShowToast(msg, type || "info");
    }
  }
  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("pt-BR");
  }
  function relativeTime(iso) {
    if (!iso) return "—";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "—";
    const diff = Math.max(0, Date.now() - then) / 1000;
    if (diff < 60) return "agora";
    if (diff < 3600) return "há " + Math.floor(diff / 60) + " min";
    if (diff < 86400) return "há " + Math.floor(diff / 3600) + " h";
    if (diff < 604800) return "há " + Math.floor(diff / 86400) + " d";
    return new Date(iso).toLocaleDateString("pt-BR");
  }
  function deadlineInfo(expiresAt, status) {
    if (!expiresAt) return { label: "Sem prazo", cls: "" };
    const d = new Date(expiresAt);
    if (isNaN(d.getTime())) return { label: "Sem prazo", cls: "" };
    if (
      status === "completed" ||
      status === "cancelled" ||
      status === "closed"
    ) {
      return { label: fmtDate(expiresAt), cls: "" };
    }
    const diffMs = d.getTime() - Date.now();
    const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
    if (diffMs < 0) {
      const over = Math.abs(diffDays);
      return {
        label: over <= 1 ? "Venceu ontem" : "Venceu há " + over + " d",
        cls: "is-danger",
      };
    }
    if (diffDays === 0) return { label: "Vence hoje", cls: "is-danger" };
    if (diffDays === 1) return { label: "Vence amanhã", cls: "is-warning" };
    if (diffDays <= 3)
      return { label: "Vence em " + diffDays + " d", cls: "is-warning" };
    return { label: fmtDate(expiresAt), cls: "" };
  }

  const CLIENT_STATUS_FALLBACK = {
    active: "Ativo",
    inactive: "Inativo",
    suspended: "Suspenso",
  };
  const BRIEFING_STATUS = {
    in_progress: "Em andamento",
    paused: "Pausado",
    completed: "Concluído",
    closed: "Encerrado",
    expired: "Expirado",
    cancelled: "Cancelado",
  };

  // Polling do job de reanálise.
  const POLL_INTERVAL_MS = 2500;
  const POLL_MAX_ATTEMPTS = 120; // ~5 min

  const state = {
    clients: [],
    filtered: [],
    activeId: null,
    filter: "all",
    query: "",
    statusChoices: [],
    briefings: [],
    briefingsSearch: "",
    listCache: new Map(),
    detailCache: new Map(),
    abortDetail: null,
    prefetching: new Set(),
    lastClickTs: 0,
    mounted: false,
    root: null,
    kebabOpen: false,
    statusMenuOpen: false,
    reanalyzing: false,
    changingStatus: false,
    codeCopiedTimer: null,
    reanalysisPolling: null,
  };

  const el = {};

  function cacheElements() {
    const root = state.root;
    if (!root) return;
    el.search = document.getElementById("clSearchInput");
    el.list = document.getElementById("clList");
    el.listTpl = document.getElementById("clClientItemTpl");
    el.kpis = document.getElementById("clKpis");
    el.count = document.getElementById("clCount");
    el.detailEmpty = document.getElementById("clDetailEmpty");
    el.detailView = document.getElementById("clDetailView");
    el.detailAvatar = document.getElementById("clDetailAvatar");
    el.detailName = document.getElementById("clDetailName");
    el.detailCreated = document.getElementById("clDetailCreated");
    el.detailCode = document.getElementById("clDetailCode");
    el.detailUpdated = document.getElementById("clDetailUpdated");
    el.codeCopyBtn = document.getElementById("clCodeCopy");
    el.statusPill = document.getElementById("clStatusPill");
    el.statusLabel = document.getElementById("clStatusLabel");
    el.statusMenu = document.getElementById("clStatusMenu");
    el.viewKnowledge = document.getElementById("clViewKnowledge");
    el.countKnowledge = document.getElementById("clCountKnowledge");
    el.viewProfile = document.getElementById("clViewProfile");
    el.wishesList = document.getElementById("clWishesList");
    el.dislikesList = document.getElementById("clDislikesList");
    el.attentionList = document.getElementById("clAttentionList");
    el.tagsList = document.getElementById("clTagsList");
    el.briefingsList = document.getElementById("clBriefingsList");
    el.briefingsCount = document.getElementById("clBriefingsCount");
    el.briefingsSearch = document.getElementById("clBriefingsSearchInput");
    el.kebabBtn = document.getElementById("clKebabBtn");
    el.kebabMenu = document.getElementById("clKebabMenu");
    el.editBtn = document.getElementById("clEditBtn");
    el.sendCodeBtn = document.getElementById("clSendCodeBtn");
    el.deleteBtn = document.getElementById("clDeleteBtn");
    el.backBtn = document.getElementById("clBackBtn");
    el.body = document.getElementById("clBody");
    el.configModal = document.getElementById("clConfigModal");
    el.deleteModal = document.getElementById("clDeleteModal");
    el.fieldName = document.getElementById("clFieldName");
    el.fieldEmail = document.getElementById("clFieldEmail");
    el.fieldPhone = document.getElementById("clFieldPhone");
    el.saveIdentityBtn = document.getElementById("clSaveIdentityBtn");
    el.deleteInput = document.getElementById("clDeleteInput");
    el.deleteConfirmBtn = document.getElementById("clDeleteConfirmBtn");
    el.deleteWord = document.getElementById("clDeleteWord");
    el.reanalyzeBtn = document.getElementById("clReanalyzeBtn");
  }

  function openModal(m) {
    if (!m) return;
    m.classList.add("active");
    document.body.style.overflow = "hidden";
    refreshIcons();
  }
  function closeModal(m) {
    if (!m) return;
    m.classList.remove("active");
    document.body.style.overflow = "";
  }
  function bindModalClosers() {
    state.root.querySelectorAll("[data-close]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const id = btn.getAttribute("data-close");
        if (id) closeModal(document.getElementById(id));
      });
    });
    state.root.querySelectorAll(".cl-modal-overlay").forEach((ov) => {
      ov.addEventListener("click", (e) => {
        if (e.target === ov) closeModal(ov);
      });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const open = document.querySelector(".cl-modal-overlay.active");
        if (open) closeModal(open);
      }
    });
  }

  let _kebabDocHandler = null;
  function openKebab() {
    if (!el.kebabMenu || !el.kebabBtn) return;
    el.kebabMenu.hidden = false;
    el.kebabBtn.setAttribute("aria-expanded", "true");
    el.kebabBtn.classList.add("is-open");
    state.kebabOpen = true;
    setTimeout(() => {
      _kebabDocHandler = (ev) => {
        if (el.kebabMenu.contains(ev.target) || el.kebabBtn.contains(ev.target))
          return;
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

  function statusLabelFor(value, sample) {
    if (sample && sample.status_display && sample.status === value)
      return sample.status_display;
    return CLIENT_STATUS_FALLBACK[value] || value || "—";
  }
  function computeStatusChoices() {
    const seen = {},
      out = [];
    for (let i = 0; i < state.clients.length; i++) {
      const c = state.clients[i];
      if (!c.status || seen[c.status]) continue;
      seen[c.status] = true;
      out.push({ value: c.status, label: statusLabelFor(c.status, c) });
    }
    if (!out.length) {
      Object.keys(CLIENT_STATUS_FALLBACK).forEach((k) => {
        out.push({ value: k, label: CLIENT_STATUS_FALLBACK[k] });
      });
    }
    return out;
  }
  function renderFilters() {
    if (!el.kpis) return;
    const counts = { all: state.clients.length };
    for (let i = 0; i < state.clients.length; i++) {
      const s = state.clients[i].status;
      if (s) counts[s] = (counts[s] || 0) + 1;
    }
    const parts = [
      '<button type="button" class="cl-filter' +
        (state.filter === "all" ? " is-active" : "") +
        '" role="tab" data-kpi="all" aria-selected="' +
        (state.filter === "all" ? "true" : "false") +
        '">' +
        '<span>Todos</span><span class="cl-filter-count">' +
        (counts.all || 0) +
        "</span></button>",
    ];
    for (let i = 0; i < state.statusChoices.length; i++) {
      const ch = state.statusChoices[i];
      const active = state.filter === ch.value;
      parts.push(
        '<button type="button" class="cl-filter' +
          (active ? " is-active" : "") +
          '" role="tab" data-kpi="' +
          esc(ch.value) +
          '" aria-selected="' +
          (active ? "true" : "false") +
          '">' +
          "<span>" +
          esc(ch.label) +
          "</span>" +
          '<span class="cl-filter-count">' +
          (counts[ch.value] || 0) +
          "</span></button>",
      );
    }
    el.kpis.innerHTML = parts.join("");
  }
  function setFilter(kpi) {
    if (state.filter === kpi) return;
    state.filter = kpi;
    renderFilters();
    renderList();
  }

  function applyFilter(items) {
    const q = state.query.trim().toLowerCase();
    const out = [];
    for (let i = 0; i < items.length; i++) {
      const c = items[i];
      if (state.filter !== "all" && c.status !== state.filter) continue;
      if (q) {
        const hay =
          (c.name || "") + " " + (c.email || "") + " " + (c.public_code || "");
        if (hay.toLowerCase().indexOf(q) === -1) continue;
      }
      out.push(c);
    }
    out.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    return out;
  }
  function renderList() {
    if (!el.list || !el.listTpl) return;
    state.filtered = applyFilter(state.clients);
    if (el.count) el.count.textContent = String(state.clients.length);
    if (!state.filtered.length) {
      state.listCache.clear();
      el.list.innerHTML =
        '<li class="cl-empty">Nenhum cliente encontrado.</li>';
      return;
    }
    const frag = document.createDocumentFragment();
    const nextCache = new Map();
    for (let i = 0; i < state.filtered.length; i++) {
      const c = state.filtered[i];
      let li = state.listCache.get(c.id);
      if (li) populateClientLi(li, c);
      else {
        const node = el.listTpl.content.cloneNode(true);
        li = node.querySelector(".cl-client");
        if (!li) continue;
        populateClientLi(li, c);
      }
      nextCache.set(c.id, li);
      frag.appendChild(li);
    }
    state.listCache = nextCache;
    el.list.innerHTML = "";
    el.list.appendChild(frag);
    refreshIcons();
  }
  function populateClientLi(li, c) {
    li.dataset.id = c.id;
    li.classList.toggle("is-active", String(c.id) === String(state.activeId));
    const av = li.querySelector(".cl-client-avatar");
    if (av) av.textContent = (c.name || "?").charAt(0).toUpperCase();
    const name = li.querySelector(".cl-client-name");
    if (name) name.textContent = c.name || "—";
    const email = li.querySelector(".cl-client-email");
    if (email) email.textContent = c.email || "—";
    const code = li.querySelector(".cl-client-code");
    if (code) code.textContent = c.public_code || "—";
    const st = c.status || "active";
    const badge = li.querySelector(".cl-client-status");
    if (badge) {
      badge.dataset.status = st;
      const lbl = badge.querySelector(".cl-client-status-label");
      if (lbl) lbl.textContent = statusLabelFor(st, c);
    }
  }

  function showEmpty() {
    if (el.detailEmpty) el.detailEmpty.hidden = false;
    if (el.detailView) el.detailView.hidden = true;
    if (el.body) el.body.classList.remove("detail-open");
  }
  function showDetail() {
    if (el.detailEmpty) el.detailEmpty.hidden = true;
    if (el.detailView) el.detailView.hidden = false;
    if (el.body) el.body.classList.add("detail-open");
  }
  function applyDetailHeader(c) {
    if (!c) return;
    if (el.detailName) el.detailName.textContent = c.name || "—";
    if (el.detailAvatar)
      el.detailAvatar.textContent = (c.name || "?").charAt(0).toUpperCase();
    if (el.detailCode) el.detailCode.textContent = c.public_code || "—";
    if (el.detailCreated) el.detailCreated.textContent = fmtDate(c.created_at);
    if (el.detailUpdated)
      el.detailUpdated.textContent = relativeTime(c.updated_at);
    const st = c.status || "active";
    if (el.statusPill) el.statusPill.dataset.status = st;
    if (el.statusLabel) el.statusLabel.textContent = statusLabelFor(st, c);
  }

  function renderStatusMenu() {
    if (!el.statusMenu) return;
    const current = state.clients.find(
      (x) => String(x.id) === String(state.activeId),
    );
    const cur = (current && current.status) || "active";
    const parts = [];
    for (let i = 0; i < state.statusChoices.length; i++) {
      const ch = state.statusChoices[i];
      const isCur = ch.value === cur;
      parts.push(
        '<button type="button" class="cl-status-menu-item' +
          (isCur ? " is-current" : "") +
          '" role="option" data-status="' +
          esc(ch.value) +
          '"' +
          (isCur ? " disabled" : "") +
          ">" +
          '<span class="cl-status-pill-dot" data-status="' +
          esc(ch.value) +
          '"></span>' +
          "<span>" +
          esc(ch.label) +
          "</span>" +
          '<i data-lucide="check" class="cl-status-menu-check"></i></button>',
      );
    }
    el.statusMenu.innerHTML = parts.join("");
    refreshIcons();
  }
  function openStatusMenu() {
    if (!el.statusMenu || !el.statusPill) return;
    if (state.changingStatus) return;
    renderStatusMenu();
    el.statusMenu.hidden = false;
    el.statusPill.setAttribute("aria-expanded", "true");
    state.statusMenuOpen = true;
    setTimeout(() => {
      const off = (ev) => {
        if (
          el.statusMenu.contains(ev.target) ||
          el.statusPill.contains(ev.target)
        )
          return;
        closeStatusMenu();
        document.removeEventListener("click", off, true);
      };
      document.addEventListener("click", off, true);
    }, 0);
  }
  function closeStatusMenu() {
    if (!el.statusMenu || !el.statusPill) return;
    el.statusMenu.hidden = true;
    el.statusPill.setAttribute("aria-expanded", "false");
    state.statusMenuOpen = false;
  }

  async function changeStatus(newStatus) {
    if (!state.activeId || !newStatus || state.changingStatus) return;
    const idx = state.clients.findIndex(
      (x) => String(x.id) === String(state.activeId),
    );
    if (idx === -1) return;
    const current = state.clients[idx];
    if (current.status === newStatus) {
      closeStatusMenu();
      return;
    }

    state.changingStatus = true;
    closeStatusMenu();
    if (el.statusPill) el.statusPill.disabled = true;

    try {
      const updated = await api("/api/clients/" + state.activeId + "/", {
        method: "PATCH",
        body: { status: newStatus },
      });
      if (updated && updated.status) {
        state.clients[idx] = Object.assign({}, state.clients[idx], updated);
      } else {
        state.clients[idx].status = newStatus;
      }
      state.detailCache.delete(String(state.activeId));
      applyDetailHeader(state.clients[idx]);
      renderList();
      renderFilters();
      showToast("Status atualizado", "success");
    } catch (err) {
      showToast((err && err.message) || "Erro ao atualizar status", "error");
    } finally {
      state.changingStatus = false;
      if (el.statusPill) el.statusPill.disabled = false;
    }
  }

  async function fetchBundle(clientId, ctrl) {
    const [client, briefings, notes] = await Promise.all([
      api("/api/clients/" + clientId + "/", {
        signal: ctrl ? ctrl.signal : undefined,
      }),
      api("/api/briefings/?client=" + clientId, {
        signal: ctrl ? ctrl.signal : undefined,
      }).catch(() => []),
      api("/api/clients/" + clientId + "/notes/", {
        signal: ctrl ? ctrl.signal : undefined,
      }).catch(() => []),
    ]);
    return {
      client,
      briefings: Array.isArray(briefings)
        ? briefings
        : (briefings && briefings.results) || [],
      notes: Array.isArray(notes) ? notes : (notes && notes.results) || [],
    };
  }
  function putCachedDetail(id, bundle) {
    state.detailCache.set(String(id), { bundle, ts: Date.now() });
  }
  function getCachedDetail(id) {
    const hit = state.detailCache.get(String(id));
    if (!hit) return null;
    if (Date.now() - hit.ts > 30000) {
      state.detailCache.delete(String(id));
      return null;
    }
    return hit.bundle;
  }
  function hydrateDetail(id, bundle) {
    state.briefings = bundle.briefings || [];
    applyDetailHeader(bundle.client);
    renderBriefings();
    renderContext(bundle.client);
    renderProfile(bundle.client);
    renderAttention(bundle.client);
    renderDislikes(bundle.client);
    renderWishes(bundle.client);
    renderTags(bundle.client);
  }
  async function loadClient(id) {
    if (!id) return;
    if (state.abortDetail) state.abortDetail.abort();
    const ctrl = new AbortController();
    state.abortDetail = ctrl;
    state.activeId = id;
    const fromList = state.clients.find((x) => String(x.id) === String(id));
    if (fromList) applyDetailHeader(fromList);
    showDetail();
    const cached = getCachedDetail(id);
    if (cached) {
      hydrateDetail(id, cached);
      return;
    }
    try {
      const bundle = await fetchBundle(id, ctrl);
      if (ctrl.signal.aborted) return;
      putCachedDetail(id, bundle);
      hydrateDetail(id, bundle);
    } catch (err) {
      if (err && err.name === "AbortError") return;
      console.warn("[cliente] falha ao carregar", err);
      showEmpty();
    }
  }
  function prefetchClient(id) {
    if (
      !id ||
      String(id) === String(state.activeId) ||
      getCachedDetail(id) ||
      state.prefetching.has(String(id))
    )
      return;
    state.prefetching.add(String(id));
    fetchBundle(id)
      .then((b) => putCachedDetail(id, b))
      .catch(() => {})
      .finally(() => state.prefetching.delete(String(id)));
  }

  function openBriefingInNewTab(briefingId) {
      if (!briefingId) return;
      const pid = (window.Clivo && window.Clivo.workspacePublicIdFromUrl) || '';
      if (!pid) {
          showToast("Workspace não identificado. Recarregue a página.", "error");
          return;
      }
      const url = "/w/" + pid + "/briefings/" + briefingId + "/resumo/";
      window.open(url, "_blank", "noopener,noreferrer");
  }

  function renderBriefings() {
    if (!el.briefingsList) return;
    const q = (state.briefingsSearch || "").trim().toLowerCase();
    const items = !q
      ? state.briefings
      : state.briefings.filter(
          (b) =>
            (b.title || "").toLowerCase().indexOf(q) !== -1 ||
            (b.template_name || "").toLowerCase().indexOf(q) !== -1,
        );
    if (el.briefingsCount)
      el.briefingsCount.textContent = state.briefings.length;
    if (!items.length) {
      el.briefingsList.innerHTML =
        '<div class="cl-empty">' +
        (state.briefings.length
          ? "Nada encontrado."
          : "Nenhum briefing ainda.") +
        "</div>";
      return;
    }
    const parts = [];
    for (let i = 0; i < items.length; i++) {
      const b = items[i];
      const status = b.status || "in_progress";
      const p = b.progress || {};
      const pct = typeof p.percent === "number" ? Math.round(p.percent) : 0;
      const answered = p.answered || 0;
      const total = p.total_required || 0;
      const progText = total ? answered + "/" + total : "—";
      const dl = deadlineInfo(b.expires_at, status);
      const cover = b.cover_url || "";
      const thumb = cover
        ? '<span class="cl-brief-thumb"><img src="' +
          esc(cover) +
          '" alt="" loading="lazy"></span>'
        : '<span class="cl-brief-thumb is-empty"><i data-lucide="workflow"></i></span>';
      parts.push(
        '<button type="button" class="cl-brief" data-brief-open="' +
          esc(String(b.id)) +
          '">' +
          '<div class="cl-brief-top-row">' +
          thumb +
          '<div class="cl-brief-body">' +
          '<span class="cl-brief-name" title="' +
          esc(b.title || "Briefing") +
          '">' +
          esc(b.title || "Briefing") +
          "</span>" +
          '<span class="cl-brief-status" data-status="' +
          esc(status) +
          '">' +
          esc(BRIEFING_STATUS[status] || status) +
          "</span>" +
          "</div>" +
          "</div>" +
          '<div class="cl-brief-foot">' +
          '<span class="cl-brief-deadline' +
          (dl.cls ? " " + dl.cls : "") +
          '">' +
          "<span>" +
          esc(dl.label) +
          "</span>" +
          "</span>" +
          '<span class="cl-brief-progress">' +
          '<span class="cl-brief-bar"><span class="cl-brief-bar-fill" style="width:' +
          pct +
          '%"></span></span>' +
          '<span class="cl-brief-pct">' +
          esc(progText) +
          "</span>" +
          "</span>" +
          "</div>" +
          "</button>",
      );
    }
    el.briefingsList.innerHTML = parts.join("");
    refreshIcons();
  }

  function normalizeContextList(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) {
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
        .filter(Boolean);
    }
    if (typeof raw === "string") {
      return raw
        .split(/\n+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .map((s) => ({ title: s, subtitle: "" }));
    }
    return [];
  }

  function fillChecks(ul, items) {
    if (!ul) return;
    const slots = ul.querySelectorAll(".cl-check-slot");
    for (let i = 0; i < slots.length; i++) {
      const slot = slots[i];
      const item = items[i];
      const strong = slot.querySelector(".cl-check-text strong");
      const small = slot.querySelector(".cl-check-text small");
      if (!strong) continue;
      if (item && (item.title || item.subtitle)) {
        slot.classList.remove("is-empty");
        strong.textContent = item.title || "—";
        if (small) small.textContent = item.subtitle || "";
      } else {
        slot.classList.add("is-empty");
        strong.textContent = "—";
        if (small) small.textContent = "";
      }
    }
  }

  function renderContext(c) {
    if (!c) return;
    const ctx = c.context || {};
    if (el.viewKnowledge) {
      const text = (ctx.knowledge || "").trim();
      el.viewKnowledge.innerHTML = text
        ? "<p>" + esc(text) + "</p>"
        : '<p class="cl-knowledge-empty">Sem informações ainda.</p>';
    }
    if (el.countKnowledge) {
      const lines = (ctx.knowledge || "").trim()
        ? (ctx.knowledge || "").split(/\n+/).filter(Boolean)
        : [];
      el.countKnowledge.textContent = String(lines.length);
    }
  }

  function renderProfile(c) {
    if (!el.viewProfile) return;
    const ctx = (c && c.context) || {};
    const text = (ctx.profile || "").trim();
    el.viewProfile.innerHTML = text
      ? "<p>" + esc(text) + "</p>"
      : '<p class="cl-profile-empty">Sem informações ainda.</p>';
  }

  function renderAttention(c) {
    if (!el.attentionList) return;
    const ctx = (c && c.context) || {};
    fillChecks(el.attentionList, normalizeContextList(ctx.attention));
  }
  function renderDislikes(c) {
    if (!el.dislikesList) return;
    const ctx = (c && c.context) || {};
    fillChecks(el.dislikesList, normalizeContextList(ctx.dislikes));
  }
  function renderWishes(c) {
    if (!el.wishesList) return;
    const ctx = (c && c.context) || {};
    fillChecks(el.wishesList, normalizeContextList(ctx.wishes));
  }

  function renderTags(c) {
    if (!el.tagsList) return;
    const ctx = (c && c.context) || {};
    const tags = Array.isArray(ctx.tags) ? ctx.tags : [];
    el.tagsList.innerHTML = !tags.length
      ? '<span class="cl-tag cl-tag--empty">—</span>'
      : tags
          .map((t) => '<span class="cl-tag">' + esc(String(t)) + "</span>")
          .join("");
  }

  function openEditModal() {
    if (!state.activeId) return;
    const c = state.clients.find(
      (x) => String(x.id) === String(state.activeId),
    );
    if (!c) return;
    if (el.fieldName) el.fieldName.value = c.name || "";
    if (el.fieldEmail) el.fieldEmail.value = c.email || "";
    if (el.fieldPhone) el.fieldPhone.value = c.phone || "";
    openModal(el.configModal);
  }
  async function saveIdentity() {
    if (!state.activeId) return;
    const payload = {
      name: ((el.fieldName && el.fieldName.value) || "").trim(),
      email: ((el.fieldEmail && el.fieldEmail.value) || "").trim(),
      phone: ((el.fieldPhone && el.fieldPhone.value) || "").trim(),
    };
    if (!payload.name) {
      showToast("Informe o nome", "error");
      return;
    }
    try {
      const updated = await api("/api/clients/" + state.activeId + "/", {
        method: "PATCH",
        body: payload,
      });
      const idx = state.clients.findIndex(
        (x) => String(x.id) === String(state.activeId),
      );
      if (idx !== -1)
        state.clients[idx] = Object.assign({}, state.clients[idx], updated);
      state.detailCache.delete(String(state.activeId));
      applyDetailHeader(updated);
      renderList();
      renderFilters();
      closeModal(el.configModal);
      showToast("Cliente atualizado", "success");
    } catch (err) {
      showToast((err && err.message) || "Erro ao salvar", "error");
    }
  }
  async function sendCode() {
    if (!state.activeId) return;
    const c = state.clients.find(
      (x) => String(x.id) === String(state.activeId),
    );
    if (!c || !c.email) {
      showToast("Cliente sem email cadastrado", "error");
      return;
    }
    try {
      await api("/api/clients/" + state.activeId + "/send-code/", {
        method: "POST",
        body: {},
      });
      showToast("Código enviado por email", "success");
    } catch (err) {
      showToast((err && err.message) || "Erro ao enviar", "error");
    }
  }
  function openDeleteModal() {
    if (!state.activeId) return;
    const c = state.clients.find(
      (x) => String(x.id) === String(state.activeId),
    );
    if (!c) return;
    if (el.deleteWord) el.deleteWord.textContent = c.name || "";
    if (el.deleteInput) el.deleteInput.value = "";
    if (el.deleteConfirmBtn) el.deleteConfirmBtn.disabled = true;
    openModal(el.deleteModal);
    setTimeout(() => {
      if (el.deleteInput) el.deleteInput.focus();
    }, 80);
  }
  async function confirmDelete() {
    if (!state.activeId) return;
    const input = ((el.deleteInput && el.deleteInput.value) || "").trim();
    const c = state.clients.find(
      (x) => String(x.id) === String(state.activeId),
    );
    if (!c || input !== (c.name || "")) return;
    const btn = el.deleteConfirmBtn;
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Excluindo…";
    }
    try {
      await api("/api/clients/" + state.activeId + "/", { method: "DELETE" });
      const removed = state.activeId;
      state.clients = state.clients.filter(
        (x) => String(x.id) !== String(removed),
      );
      state.detailCache.delete(String(removed));
      state.activeId = null;
      closeModal(el.deleteModal);
      renderList();
      renderFilters();
      showEmpty();
      showToast("Cliente excluído", "success");
    } catch (err) {
      showToast((err && err.message) || "Erro ao excluir", "error");
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Excluir";
      }
    }
  }

  // -------------------- REANÁLISE MANUAL --------------------
  function stopReanalysisPolling() {
    if (state.reanalysisPolling) {
      clearTimeout(state.reanalysisPolling);
      state.reanalysisPolling = null;
    }
  }

  async function refreshClientBundle() {
    if (!state.activeId) return;
    state.detailCache.delete(String(state.activeId));
    try {
      const bundle = await fetchBundle(state.activeId);
      putCachedDetail(state.activeId, bundle);
      hydrateDetail(state.activeId, bundle);
    } catch (err) {
      console.warn("[cliente] falha ao recarregar após reanálise", err);
    }
    // Também recarrega a lista de clientes para refletir qualquer
    // mudança de contexto (`wishes`, `attention` etc.) que a análise
    // possa ter produzido.
    try {
      const data = await api("/api/clients/");
      state.clients = Array.isArray(data) ? data : (data && data.results) || [];
      renderFilters();
      renderList();
    } catch (_) {}
  }

  function pollJobStatus(jobId, attempt) {
    if (!jobId) return;
    attempt = attempt || 1;
    stopReanalysisPolling();

    const tick = async () => {
      try {
        const status = await api(
          `/api/intelligence/jobs/${jobId}/status/`,
        );
        if (status.status === "completed" || status.status === "failed") {
          stopReanalysisPolling();
          if (el.reanalyzeBtn) {
            el.reanalyzeBtn.classList.remove("is-loading");
            el.reanalyzeBtn.disabled = false;
          }
          state.reanalyzing = false;
          if (status.status === "completed") {
            await refreshClientBundle();
          } else {
            console.warn(
              "[cliente] job de reanálise falhou", status.error_message,
            );
          }
          return;
        }
        if (attempt >= POLL_MAX_ATTEMPTS) {
          stopReanalysisPolling();
          if (el.reanalyzeBtn) {
            el.reanalyzeBtn.classList.remove("is-loading");
            el.reanalyzeBtn.disabled = false;
          }
          state.reanalyzing = false;
          return;
        }
        state.reanalysisPolling = setTimeout(() => {
          pollJobStatus(jobId, attempt + 1);
        }, POLL_INTERVAL_MS);
      } catch (err) {
        console.warn("[cliente] falha no polling do job", err);
        if (attempt >= POLL_MAX_ATTEMPTS) {
          stopReanalysisPolling();
          if (el.reanalyzeBtn) {
            el.reanalyzeBtn.classList.remove("is-loading");
            el.reanalyzeBtn.disabled = false;
          }
          state.reanalyzing = false;
          return;
        }
        state.reanalysisPolling = setTimeout(() => {
          pollJobStatus(jobId, attempt + 1);
        }, POLL_INTERVAL_MS);
      }
    };
    tick();
  }

  async function triggerReanalysis() {
    if (!state.activeId || !el.reanalyzeBtn) return;
    if (state.reanalyzing) return;
    state.reanalyzing = true;
    el.reanalyzeBtn.classList.add("is-loading");
    el.reanalyzeBtn.disabled = true;

    try {
      const result = await api(
        "/api/intelligence/clients/" + state.activeId + "/reanalyze/",
        { method: "POST", body: {} },
      );
      const jobId = (result && result.job_id) || "";
      if (!jobId) {
        state.reanalyzing = false;
        el.reanalyzeBtn.classList.remove("is-loading");
        el.reanalyzeBtn.disabled = false;
        return;
      }
      // Sem popup. Polling recarrega os containers quando concluir.
      pollJobStatus(jobId, 1);
    } catch (err) {
      state.reanalyzing = false;
      el.reanalyzeBtn.classList.remove("is-loading");
      el.reanalyzeBtn.disabled = false;
      if (err && err.status === 404) {
        showToast(
          "Análise manual ainda não disponível neste ambiente",
          "error",
        );
      } else if (err && err.status === 403) {
        showToast("Sua governança não permite esta ação", "error");
      } else if (err && err.status === 400) {
        showToast(
          (err && err.message) || "Análise bloqueada pela política de quota",
          "error",
        );
      } else {
        showToast((err && err.message) || "Falha ao agendar", "error");
      }
    }
  }

  function copyCode() {
    if (!el.detailCode) return;
    const code = (el.detailCode.textContent || "").trim();
    if (!code || code === "—") return;

    const onCopied = () => {
      if (!el.codeCopyBtn) return;
      el.codeCopyBtn.classList.add("is-copied");
      const icon = el.codeCopyBtn.querySelector("svg, i");
      if (icon) {
        const original = icon.outerHTML;
        if (window.lucide) {
          icon.outerHTML = '<i data-lucide="check"></i>';
          refreshIcons();
        }
        if (state.codeCopiedTimer) clearTimeout(state.codeCopiedTimer);
        state.codeCopiedTimer = setTimeout(() => {
          el.codeCopyBtn.classList.remove("is-copied");
          const cur = el.codeCopyBtn.querySelector("svg, i");
          if (cur) cur.outerHTML = original;
          refreshIcons();
        }, 1500);
      } else {
        if (state.codeCopiedTimer) clearTimeout(state.codeCopiedTimer);
        state.codeCopiedTimer = setTimeout(() => {
          el.codeCopyBtn.classList.remove("is-copied");
        }, 1500);
      }
      showToast("Código copiado", "success");
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(code)
        .then(onCopied)
        .catch(() => {
          fallbackCopy(code, onCopied);
        });
    } else {
      fallbackCopy(code, onCopied);
    }
  }
  function fallbackCopy(text, cb) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "absolute";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      cb();
    } catch (e) {
      showToast("Não foi possível copiar", "error");
    }
  }

  function bindEvents() {
    if (el.kpis)
      el.kpis.addEventListener("click", (e) => {
        const btn = e.target.closest(".cl-filter");
        if (btn) setFilter(btn.dataset.kpi);
      });
    if (el.search) {
      let t;
      el.search.addEventListener("input", () => {
        clearTimeout(t);
        t = setTimeout(() => {
          const q = el.search.value || "";
          if (q === state.query) return;
          state.query = q;
          renderList();
        }, 80);
      });
    }
    if (el.list) {
      el.list.addEventListener("mouseover", (e) => {
        const item = e.target.closest(".cl-client");
        if (item) prefetchClient(item.dataset.id);
      });
      el.list.addEventListener("click", (e) => {
        const item = e.target.closest(".cl-client");
        if (!item) return;
        const id = item.dataset.id;
        if (!id || String(id) === String(state.activeId)) return;
        const now = Date.now();
        if (now - state.lastClickTs < 80) return;
        state.lastClickTs = now;
        const prev = el.list.querySelector(".cl-client.is-active");
        if (prev) prev.classList.remove("is-active");
        item.classList.add("is-active");
        loadClient(id);
      });
    }
    if (el.backBtn)
      el.backBtn.addEventListener("click", () => {
        if (el.body) el.body.classList.remove("detail-open");
        showEmpty();
      });
    if (el.briefingsSearch) {
      let t;
      el.briefingsSearch.addEventListener("input", () => {
        clearTimeout(t);
        t = setTimeout(() => {
          state.briefingsSearch = el.briefingsSearch.value || "";
          renderBriefings();
        }, 80);
      });
    }
    if (el.briefingsList)
      el.briefingsList.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-brief-open]");
        if (!btn) return;
        const id = btn.dataset.briefOpen;
        if (id) openBriefingInNewTab(id);
      });

    if (el.kebabBtn)
      el.kebabBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (state.kebabOpen) closeKebab();
        else openKebab();
      });
    if (el.editBtn)
      el.editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeKebab();
        openEditModal();
      });
    if (el.sendCodeBtn)
      el.sendCodeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeKebab();
        sendCode();
      });
    if (el.deleteBtn)
      el.deleteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeKebab();
        openDeleteModal();
      });

    if (el.statusPill)
      el.statusPill.addEventListener("click", (e) => {
        e.stopPropagation();
        if (state.statusMenuOpen) closeStatusMenu();
        else openStatusMenu();
      });
    if (el.statusMenu)
      el.statusMenu.addEventListener("click", (e) => {
        const btn = e.target.closest(".cl-status-menu-item");
        if (btn && !btn.disabled) changeStatus(btn.dataset.status);
      });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.statusMenuOpen) closeStatusMenu();
    });

    if (el.codeCopyBtn) el.codeCopyBtn.addEventListener("click", copyCode);

    if (el.saveIdentityBtn)
      el.saveIdentityBtn.addEventListener("click", saveIdentity);
    if (el.deleteInput)
      el.deleteInput.addEventListener("input", () => {
        const c = state.clients.find(
          (x) => String(x.id) === String(state.activeId),
        );
        if (el.deleteConfirmBtn)
          el.deleteConfirmBtn.disabled =
            !c || el.deleteInput.value.trim() !== (c.name || "");
      });
    if (el.deleteConfirmBtn)
      el.deleteConfirmBtn.addEventListener("click", confirmDelete);
    if (el.reanalyzeBtn)
      el.reanalyzeBtn.addEventListener("click", triggerReanalysis);
  }

  async function loadClients() {
    try {
      const data = await api("/api/clients/");
      state.clients = Array.isArray(data) ? data : (data && data.results) || [];
    } catch (err) {
      console.warn("[cliente] falha ao carregar lista", err);
      state.clients = [];
    }
    state.statusChoices = computeStatusChoices();
    renderFilters();
    renderList();
    if (state.clients.length && !state.activeId && window.innerWidth >= 800) {
      loadClient(state.clients[0].id);
    } else if (!state.clients.length) {
      showEmpty();
    }
  }

  function mount() {
    const root = document.getElementById("clPage");
    if (!root) return;
    if (state.mounted && state.root === root) return;
    state.root = root;
    state.mounted = true;
    state.clients = [];
    state.filtered = [];
    state.activeId = null;
    state.filter = "all";
    state.query = "";
    state.statusChoices = [];
    state.briefings = [];
    state.briefingsSearch = "";
    state.listCache = new Map();
    state.detailCache = new Map();
    state.prefetching = new Set();
    state.lastClickTs = 0;
    state.kebabOpen = false;
    state.statusMenuOpen = false;
    state.reanalyzing = false;
    state.changingStatus = false;
    state.codeCopiedTimer = null;
    stopReanalysisPolling();

    cacheElements();
    bindEvents();
    bindModalClosers();
    loadClients();
  }

  function unmount() {
    state.mounted = false;
    if (state.abortDetail) {
      try {
        state.abortDetail.abort();
      } catch (e) {}
      state.abortDetail = null;
    }
    stopReanalysisPolling();
    state.listCache = new Map();
    state.detailCache = new Map();
    state.prefetching = new Set();
    document.body.style.overflow = "";
    closeKebab();
    closeStatusMenu();
    if (state.codeCopiedTimer) {
      clearTimeout(state.codeCopiedTimer);
      state.codeCopiedTimer = null;
    }
  }

  window.ClivoPages = window.ClivoPages || {};
  window.ClivoPages.cliente = { mount, unmount };

  function autoMount() {
    if (document.getElementById("clPage")) mount();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoMount);
  } else {
    autoMount();
  }
})();