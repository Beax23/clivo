/* =========================================================================
   CLIENTE — master/detail.
   Cache por aba — sem re-fetch ao alternar.
   ========================================================================= */

(function() {
    'use strict';

    function showToast(msg, type) {
        if (typeof window.clivoShowToast === 'function') {
            window.clivoShowToast(msg, type);
        }
    }

    function api(url, method, body) {
        return window.clivoApi(url, method, body);
    }

    const _escCache = new Map();
    function escapeHtml(s) {
        if (s === null || s === undefined) return '';
        s = String(s);
        if (_escCache.has(s)) return _escCache.get(s);
        const r = s
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
        if (_escCache.size < 500) _escCache.set(s, r);
        return r;
    }

    function setLoading(btn, loading, label) {
        if (!btn) return;
        if (loading) {
            if (!btn.dataset.loading) {
                btn.dataset.originalText = btn.innerHTML;
                btn.dataset.loading = '1';
            }
            btn.disabled = true;
            btn.innerHTML =
                '<span class="loading-spinner" style="width:12px;height:12px;border-width:2px;border-color:rgba(255,255,255,0.3);border-top-color:#fff;display:inline-block;border-radius:50%;"></span> ' +
                (label || 'Aguarde...');
        } else {
            btn.disabled = false;
            if (btn.dataset.originalText !== undefined) {
                btn.innerHTML = btn.dataset.originalText;
            }
            delete btn.dataset.loading;
            delete btn.dataset.originalText;
        }
    }

    function formatDate(iso) {
        if (!iso) return '';
        try {
            const d = new Date(iso);
            return d.toLocaleDateString('pt-BR', { day: 'numeric', month: 'short' });
        } catch (e) { return ''; }
    }

    function formatDateTime(iso) {
        if (!iso) return '';
        try {
            const d = new Date(iso);
            return d.toLocaleString('pt-BR', {
                day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
            });
        } catch (e) { return ''; }
    }

    function formatDeadlineFull(iso) {
        if (!iso) return '';
        try {
            const d = new Date(iso);
            const now = new Date();
            const sameYear = d.getFullYear() === now.getFullYear();
            return d.toLocaleDateString('pt-BR', {
                day: 'numeric',
                month: 'short',
                ...(sameYear ? {} : { year: 'numeric' }),
            });
        } catch (e) { return ''; }
    }

    function computeDeadlineInfo(expiresAt, status) {
        if (!expiresAt) {
            return { label: 'Sem prazo', cls: '' };
        }
        let date;
        try {
            date = new Date(expiresAt);
            if (isNaN(date.getTime())) return { label: 'Sem prazo', cls: '' };
        } catch (e) {
            return { label: 'Sem prazo', cls: '' };
        }

        const now = Date.now();
        const diffMs = date.getTime() - now;
        const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

        if (status === 'completed' || status === 'closed') {
            return { label: formatDeadlineFull(expiresAt), cls: '' };
        }

        if (diffMs < 0) {
            const over = Math.abs(diffDays);
            return {
                label: over <= 1 ? 'Venceu ontem' : 'Venceu há ' + over + ' dias',
                cls: 'is-danger',
            };
        }

        if (diffDays === 0) {
            return { label: 'Vence hoje', cls: 'is-danger' };
        }
        if (diffDays === 1) {
            return { label: 'Vence amanhã', cls: 'is-warning' };
        }
        if (diffDays <= 3) {
            return { label: 'Vence em ' + diffDays + ' dias', cls: 'is-warning' };
        }
        return { label: formatDeadlineFull(expiresAt), cls: '' };
    }

    function refreshIcons() {
        if (typeof window.clivoRefreshIcons === 'function') {
            window.clivoRefreshIcons();
        }
    }

    const STATUS_LABELS = {
        active: 'Ativo',
        inactive: 'Inativo',
        suspended: 'Suspenso',
    };

    function statusLabel(status) {
        return STATUS_LABELS[status] || status || '—';
    }

    const BRIEFING_STATUS_LABELS = {
        in_progress: 'Em andamento',
        paused: 'Pausado',
        completed: 'Concluído',
        closed: 'Encerrado',
        expired: 'Expirado',
        cancelled: 'Cancelado',
    };

    const CTX = {
        PROFILE: 'profile',
        KNOWLEDGE: 'knowledge',
        WISHES: 'wishes',
        DISLIKES: 'dislikes',
    };

    // =====================================================================
    // ESTADO
    // =====================================================================
    let clientsCache = [];
    let clientsLoaded = false;
    let clientsPromise = null;
    let currentClient = null;
    let briefingsCache = [];
    let briefingsSearch = '';
    let isOpening = false;
    let detailCache = new Map();
    let detailPromises = new Map();
    let briefingsCacheByClient = new Map();

    // =====================================================================
    // LISTA
    // =====================================================================
    async function loadClients(force) {
        const listEl = document.getElementById('clList');
        if (!listEl) return;

        const CACHE_TTL = 30000;
        const now = Date.now();

        if (!force && clientsLoaded && clientsCache.length) {
            renderClients();
            updateListSubtitle();
            schedulePrefetch();
            return;
        }

        if (!force && window.Clivo.cache.clients &&
            (now - window.Clivo.cache.clients.timestamp) < CACHE_TTL) {
            clientsCache = window.Clivo.cache.clients.data || [];
            clientsLoaded = true;
            renderClients();
            updateListSubtitle();
            schedulePrefetch();
            return;
        }

        if (clientsPromise) {
            await clientsPromise;
            renderClients();
            updateListSubtitle();
            return;
        }

        clientsPromise = (async function() {
            try {
                const data = await api('/api/clients/');
                clientsCache = Array.isArray(data) ? data : (data.results || []);
                clientsLoaded = true;
                window.Clivo.cache.clients = {
                    data: clientsCache,
                    timestamp: Date.now(),
                };
                return clientsCache;
            } catch (e) {
                clientsCache = [];
                clientsLoaded = true;
                throw e;
            } finally {
                clientsPromise = null;
            }
        })();

        try {
            await clientsPromise;
        } catch (e) {
            listEl.innerHTML = '<li class="cl-list-empty">Erro ao carregar clientes</li>';
            updateListSubtitle();
            return;
        }

        renderClients();
        updateListSubtitle();
        schedulePrefetch();
    }

    function schedulePrefetch() {
        const run = function() {
            clientsCache.slice(0, 5).forEach(function(c) {
                prefetchClientDetail(c.id);
            });
        };
        if (typeof requestIdleCallback === 'function') {
            requestIdleCallback(run, { timeout: 1500 });
        } else {
            setTimeout(run, 300);
        }
    }

    function updateListSubtitle() {
        const countEl = document.getElementById('clCount');
        if (countEl) countEl.textContent = String(clientsCache.length);
    }

    function getFilteredClients() {
        const searchInput = document.getElementById('clSearchInput');
        const query = (searchInput && searchInput.value || '').trim().toLowerCase();
        const statusSelect = document.getElementById('clStatusFilter');
        const statusFilter = statusSelect ? statusSelect.value : '';

        if (!query && !statusFilter) return clientsCache.slice();

        let items = clientsCache;
        if (statusFilter) {
            items = items.filter(function(c) { return c.status === statusFilter; });
        }
        if (query) {
            items = items.filter(function(c) {
                return (c.name || '').toLowerCase().indexOf(query) !== -1
                    || (c.email || '').toLowerCase().indexOf(query) !== -1;
            });
        }
        return items.slice();
    }

    function renderClients() {
        const listEl = document.getElementById('clList');
        if (!listEl) return;

        const items = getFilteredClients();

        if (!items.length) {
            const searchInput = document.getElementById('clSearchInput');
            const statusSelect = document.getElementById('clStatusFilter');
            const hasQuery = (searchInput && searchInput.value.trim()) ||
                             (statusSelect && statusSelect.value);
            listEl.innerHTML =
                '<li class="cl-list-empty">' +
                (hasQuery ? 'Nada encontrado' : 'Nenhum cliente ainda') +
                '</li>';
            return;
        }

        const currentId = currentClient ? currentClient.id : null;
        const parts = [];
        for (let i = 0; i < items.length; i++) {
            const c = items[i];
            const initial = (c.name || '?').charAt(0).toUpperCase();
            const email = c.email || '—';
            const status = c.status || 'active';
            const statusText = statusLabel(status);
            const isSel = currentId && currentId === c.id;
            parts.push(
                '<li class="cl-list-item' + (isSel ? ' is-active' : '') + '" data-client-id="' + c.id + '">' +
                    '<div class="cl-avatar">' + escapeHtml(initial) + '</div>' +
                    '<div class="cl-list-item-body">' +
                        '<div class="cl-list-item-title">' +
                            '<span class="cl-status-led ' + escapeHtml(status) + '" title="' + escapeHtml(statusText) + '"></span>' +
                            '<span>' + escapeHtml(c.name || '—') + '</span>' +
                        '</div>' +
                        '<div class="cl-list-item-meta">' + escapeHtml(email) + '</div>' +
                    '</div>' +
                '</li>'
            );
        }
        listEl.innerHTML = parts.join('');
    }

    function bindListEvents() {
        const listEl = document.getElementById('clList');
        if (!listEl || listEl.__clBound) return;
        listEl.__clBound = true;

        listEl.addEventListener('mouseover', function(e) {
            const card = e.target.closest('.cl-list-item');
            if (!card) return;
            const id = card.dataset.clientId;
            if (id) prefetchClientDetail(id);
        });

        listEl.addEventListener('click', function(e) {
            const card = e.target.closest('.cl-list-item');
            if (!card) return;
            const id = card.dataset.clientId;
            if (!id) return;
            if (currentClient && currentClient.id === id) return;
            openClient(id);
        });
    }

    function updateSelection() {
        const listEl = document.getElementById('clList');
        if (!listEl) return;
        const currentId = currentClient ? currentClient.id : null;
        const items = listEl.querySelectorAll('.cl-list-item');
        for (let i = 0; i < items.length; i++) {
            items[i].classList.toggle('is-active', items[i].dataset.clientId === currentId);
        }
    }

    // =====================================================================
    // DETALHE
    // =====================================================================
    function setDetailOpen(open) {
        const body = document.getElementById('clBody');
        if (body) body.classList.toggle('detail-open', !!open);
    }

    function showDetailEmpty() {
        const empty = document.getElementById('clDetailEmpty');
        const content = document.getElementById('clDetailContent');
        if (empty) empty.classList.remove('is-hidden');
        if (content) content.classList.add('is-hidden');
    }

    function showDetailContent() {
        const empty = document.getElementById('clDetailEmpty');
        const content = document.getElementById('clDetailContent');
        if (empty) empty.classList.add('is-hidden');
        if (content) content.classList.remove('is-hidden');
    }

    function prefetchClientDetail(clientId) {
        if (!clientId) return;
        if (detailCache.has(clientId) || detailPromises.has(clientId)) return;
        const p = api('/api/clients/' + clientId + '/')
            .then(function(client) {
                detailCache.set(clientId, client);
                return client;
            })
            .catch(function() {})
            .finally(function() {
                detailPromises.delete(clientId);
            });
        detailPromises.set(clientId, p);
    }

    function fetchClientDetail(clientId) {
        if (detailCache.has(clientId)) {
            return Promise.resolve(detailCache.get(clientId));
        }
        if (detailPromises.has(clientId)) {
            return detailPromises.get(clientId);
        }
        const p = api('/api/clients/' + clientId + '/')
            .then(function(client) {
                detailCache.set(clientId, client);
                return client;
            })
            .finally(function() {
                detailPromises.delete(clientId);
            });
        detailPromises.set(clientId, p);
        return p;
    }

    async function openClient(clientId) {
        if (isOpening) return;
        if (currentClient && currentClient.id === clientId) {
            setDetailOpen(true);
            updateSelection();
            return;
        }

        isOpening = true;
        try {
            const client = await fetchClientDetail(clientId);
            currentClient = client;

            briefingsCache = [];
            briefingsSearch = '';

            if (window.location.hash !== '#' + clientId) {
                history.replaceState(
                    { soft: true, path: window.location.pathname + '#' + clientId },
                    '',
                    window.location.pathname + '#' + clientId
                );
            }

            renderDetail();
            showDetailContent();
            setDetailOpen(true);
            updateSelection();
        } catch (e) {
            showToast('Erro ao carregar cliente', 'error');
            showDetailEmpty();
        } finally {
            isOpening = false;
        }
    }

    function closeDetail() {
        setDetailOpen(false);
        if (window.location.hash) {
            history.replaceState(
                { soft: true, path: window.location.pathname },
                '',
                window.location.pathname
            );
        }
        currentClient = null;
        updateSelection();
        showDetailEmpty();
    }

    function renderDetail() {
        if (!currentClient) return;
        const c = currentClient;
        const status = c.status || 'active';
        const initial = (c.name || '?').charAt(0).toUpperCase();

        const setText = function(id, val) {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        const av = document.getElementById('clDetailAvatar');
        if (av) av.textContent = initial;

        setText('clDetailName', c.name || '—');
        setText('clDetailCode', c.public_code || '—');
        setText('clDetailCreatedAt',
            c.created_at ? ('Criado em ' + formatDate(c.created_at)) : '—');
        setText('clDetailCreatedBy',
            c.created_by_name ? ('por ' + c.created_by_name) : '—');

        updateStatusPill(status);

        const nameInput = document.getElementById('clFieldName');
        const emailInput = document.getElementById('clFieldEmail');
        const phoneInput = document.getElementById('clFieldPhone');
        if (nameInput) nameInput.value = c.name || '';
        if (emailInput) emailInput.value = c.email || '';
        if (phoneInput) phoneInput.value = c.phone || '';

        renderContextViews();
        setText('clDeleteWord', c.name || '');

        // Reset search input de briefings ao trocar de cliente
        const bSearch = document.getElementById('clBriefingsSearchInput');
        if (bSearch) bSearch.value = '';
        briefingsSearch = '';

        loadBriefings();
        loadHistorico();

        document.title = 'Cliente · Clivo';
    }

    function renderContextViews() {
        if (!currentClient) return;
        const ctx = currentClient.context || {};

        const pairs = [
            { el: 'clViewProfile',   value: (ctx[CTX.PROFILE] || '').trim() },
            { el: 'clViewKnowledge', value: (ctx[CTX.KNOWLEDGE] || '').trim() },
            { el: 'clViewWishes',    value: (ctx[CTX.WISHES] || '').trim() },
            { el: 'clViewDislikes',  value: (ctx[CTX.DISLIKES] || '').trim() },
        ];

        for (let i = 0; i < pairs.length; i++) {
            const pair = pairs[i];
            const el = document.getElementById(pair.el);
            if (!el) continue;
            if (pair.value) {
                el.innerHTML = '<p>' + escapeHtml(pair.value) + '</p>';
            } else {
                el.innerHTML = '<p class="cl-prop-empty">Sem informações ainda.</p>';
            }
        }
    }

    // =====================================================================
    // STATUS PILL
    // =====================================================================
    function updateStatusPill(status) {
        const pill = document.getElementById('clStatusPill');
        const label = document.getElementById('clStatusPillLabel');
        const dot = document.getElementById('clStatusPillDot');
        if (pill) pill.setAttribute('data-status', status);
        if (label) label.textContent = statusLabel(status);
        if (dot) dot.className = 'cl-status-pill-dot ' + status;
        document.querySelectorAll('#clStatusMenu .cl-status-menu-item').forEach(function(item) {
            item.classList.toggle('is-current', item.dataset.status === status);
        });
    }

    function openStatusMenu() {
        const menu = document.getElementById('clStatusMenu');
        const pill = document.getElementById('clStatusPill');
        if (!menu || !pill) return;
        menu.classList.add('is-open');
        pill.setAttribute('aria-expanded', 'true');
    }

    function closeStatusMenu() {
        const menu = document.getElementById('clStatusMenu');
        const pill = document.getElementById('clStatusPill');
        if (!menu || !pill) return;
        menu.classList.remove('is-open');
        pill.setAttribute('aria-expanded', 'false');
    }

    function setupStatusMenu() {
        const pill = document.getElementById('clStatusPill');
        const menu = document.getElementById('clStatusMenu');
        if (!pill || !menu) return;

        pill.addEventListener('click', function(e) {
            e.stopPropagation();
            if (menu.classList.contains('is-open')) {
                closeStatusMenu();
            } else {
                openStatusMenu();
            }
        });

        menu.querySelectorAll('.cl-status-menu-item').forEach(function(item) {
            item.addEventListener('click', async function(e) {
                e.stopPropagation();
                if (!currentClient) return;
                const newStatus = this.dataset.status;
                const oldStatus = currentClient.status;
                closeStatusMenu();
                if (newStatus === oldStatus) return;

                try {
                    const updated = await api(
                        '/api/clients/' + currentClient.id + '/',
                        'PATCH',
                        { status: newStatus }
                    );
                    currentClient = updated;
                    detailCache.set(currentClient.id, currentClient);
                    updateStatusPill(newStatus);

                    const idx = clientsCache.findIndex(function(c) {
                        return c.id === currentClient.id;
                    });
                    if (idx !== -1) {
                        clientsCache[idx] = Object.assign({}, clientsCache[idx], {
                            status: currentClient.status,
                        });
                        window.Clivo.cache.clients = {
                            data: clientsCache,
                            timestamp: Date.now(),
                        };
                        renderClients();
                        updateSelection();
                    }
                    loadHistorico();
                    showToast('Status atualizado', 'success');
                } catch (err) {
                    showToast(err.message || 'Erro ao atualizar status', 'error');
                }
            });
        });

        document.addEventListener('click', function(e) {
            if (!menu.classList.contains('is-open')) return;
            if (menu.contains(e.target) || pill.contains(e.target)) return;
            closeStatusMenu();
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeStatusMenu();
        });
    }

    // =====================================================================
    // BRIEFINGS — cards verticais clássicos
    // =====================================================================
    function getFilteredBriefings() {
        const q = (briefingsSearch || '').trim().toLowerCase();
        if (!q) return briefingsCache.slice();
        return briefingsCache.filter(function(b) {
            const title = (b.title || '').toLowerCase();
            const tpl = (b.template_name || '').toLowerCase();
            return title.indexOf(q) !== -1 || tpl.indexOf(q) !== -1;
        });
    }

    async function loadBriefings(force) {
        const el = document.getElementById('clBriefingsList');
        if (!el || !currentClient) return;

        if (!force && briefingsCacheByClient.has(currentClient.id)) {
            briefingsCache = briefingsCacheByClient.get(currentClient.id);
            renderBriefings();
            return;
        }

        el.innerHTML = '<div class="cl-empty">Carregando…</div>';
        try {
            const data = await api('/api/briefings/?client=' + currentClient.id);
            briefingsCache = Array.isArray(data) ? data : (data.results || []);
            briefingsCacheByClient.set(currentClient.id, briefingsCache);
        } catch (e) {
            briefingsCache = [];
        }
        renderBriefings();
    }

    function renderBriefings() {
        const el = document.getElementById('clBriefingsList');
        const countEl = document.getElementById('clBriefingsCount');
        if (!el) return;

        const items = getFilteredBriefings();
        const total = briefingsCache.length;

        if (countEl) countEl.textContent = String(total);

        if (!items.length) {
            el.innerHTML = '<div class="cl-empty">' +
                (total ? 'Nada encontrado' : 'Nenhum briefing ainda') +
                '</div>';
            return;
        }

        const parts = [];
        for (let i = 0; i < items.length; i++) {
            const b = items[i];
            const status = b.status || 'in_progress';
            const statusText = BRIEFING_STATUS_LABELS[status] || status;
            const progress = b.progress || {};
            const pct = typeof progress.percent === 'number' ? Math.round(progress.percent) : 0;
            const answered = progress.answered || 0;
            const totalQ = progress.total_required || 0;

            const deadline = computeDeadlineInfo(b.expires_at, status);
            const deadlineClass = deadline.cls ? ' ' + deadline.cls : '';
            const deadlineIcon = deadline.cls === 'is-danger'
                ? 'alert-triangle'
                : (deadline.cls === 'is-warning' ? 'clock-alert' : 'calendar');

            const coverUrl = b.cover_url || '';
            const title = b.title || 'Briefing';

            const progressText = totalQ
                ? answered + ' de ' + totalQ + ' perguntas'
                : '—';

            const coverInner = coverUrl
                ? '<img src="' + escapeHtml(coverUrl) + '" alt="" loading="lazy" ' +
                  'onerror="this.style.display=\'none\';this.parentNode.classList.add(\'is-empty\');' +
                  'this.parentNode.innerHTML=\'<i data-lucide=\\\'image\\\'></i>\';' +
                  'if(window.lucide)window.lucide.createIcons();">'
                : '<i data-lucide="image"></i>';

            const coverHtml = '<div class="cl-briefing-cover' +
                (coverUrl ? '' : ' is-empty') + '">' +
                coverInner +
            '</div>';

            parts.push(
                '<button type="button" class="cl-briefing status-' + escapeHtml(status) + '" data-briefing-open="' + b.id + '">' +
                    coverHtml +
                    '<div class="cl-briefing-content">' +
                        '<p class="cl-briefing-title">' + escapeHtml(title) + '</p>' +
                        '<div class="cl-briefing-meta">' +
                            '<span class="cl-briefing-status">' + escapeHtml(statusText) + '</span>' +
                            '<span class="cl-briefing-deadline' + deadlineClass + '">' +
                                '<i data-lucide="' + deadlineIcon + '"></i>' +
                                '<span>' + escapeHtml(deadline.label) + '</span>' +
                            '</span>' +
                        '</div>' +
                        '<div class="cl-briefing-progress">' +
                            '<div class="cl-briefing-bar">' +
                                '<div class="cl-briefing-bar-fill" style="width:' + pct + '%"></div>' +
                            '</div>' +
                            '<span class="cl-briefing-pct">' + escapeHtml(progressText) + '</span>' +
                        '</div>' +
                    '</div>' +
                '</button>'
            );
        }
        el.innerHTML = parts.join('');
        refreshIcons();

        el.querySelectorAll('[data-briefing-open]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const id = this.dataset.briefingOpen;
                if (typeof window.clivoSoftNavigate === 'function') {
                    window.clivoSoftNavigate('/fluxo/', {
                        afterMount: function() {
                            window.location.hash = id;
                        }
                    });
                } else {
                    window.location.href = '/fluxo/#' + id;
                }
            });
        });
    }

    function setupBriefingsSearch() {
        const input = document.getElementById('clBriefingsSearchInput');
        if (!input || input.__clBound) return;
        input.__clBound = true;
        input.addEventListener('input', function() {
            briefingsSearch = this.value || '';
            renderBriefings();
        });
    }

    // =====================================================================
    // HISTÓRICO
    // =====================================================================
    async function loadHistorico() {
        const el = document.getElementById('clHistoryList');
        if (!el || !currentClient) return;

        el.innerHTML = '<div class="cl-empty">Carregando…</div>';

        const [notes, briefings] = await Promise.all([
            loadNotasForHistory(),
            loadBriefingsForHistory(),
        ]);

        const events = [];

        notes.forEach(function(n) {
            const wasEdited = n.updated_at && n.created_at &&
                              n.updated_at !== n.created_at;
            events.push({
                kind: 'note',
                icon: wasEdited ? 'pencil' : 'sticky-note',
                label: wasEdited ? 'Nota editada' : 'Nota criada',
                detail: n.content ? n.content.slice(0, 140) : '',
                at: wasEdited ? n.updated_at : n.created_at,
                author: n.author_name || n.author_email || '',
            });
        });

        briefings.forEach(function(b) {
            events.push({
                kind: 'briefing',
                icon: 'workflow',
                label: 'Briefing: ' + (b.title || '—'),
                detail: 'Status: ' + (BRIEFING_STATUS_LABELS[b.status] || b.status || '—'),
                at: b.created_at,
                author: b.created_by_name || '',
            });
        });

        if (currentClient.created_at) {
            events.push({
                kind: 'status',
                icon: 'user-plus',
                label: 'Cliente criado',
                detail: currentClient.public_code || '',
                at: currentClient.created_at,
                author: currentClient.created_by_name || '',
            });
        }

        if (currentClient.updated_at && currentClient.created_at &&
            currentClient.updated_at !== currentClient.created_at) {
            events.push({
                kind: 'status',
                icon: 'activity',
                label: 'Cliente atualizado',
                detail: 'Status: ' + statusLabel(currentClient.status),
                at: currentClient.updated_at,
                author: '',
            });
        }

        events.sort(function(a, b) {
            const da = a.at ? new Date(a.at).getTime() : 0;
            const db = b.at ? new Date(b.at).getTime() : 0;
            return db - da;
        });

        renderHistory(events);
    }

    function loadNotasForHistory() {
        if (!currentClient) return Promise.resolve([]);
        return api('/api/clients/' + currentClient.id + '/notes/')
            .then(function(data) {
                return Array.isArray(data) ? data : (data.results || []);
            })
            .catch(function() { return []; });
    }

    function loadBriefingsForHistory() {
        if (!currentClient) return Promise.resolve([]);
        if (briefingsCacheByClient.has(currentClient.id)) {
            return Promise.resolve(briefingsCacheByClient.get(currentClient.id));
        }
        return api('/api/briefings/?client=' + currentClient.id)
            .then(function(data) {
                const list = Array.isArray(data) ? data : (data.results || []);
                briefingsCacheByClient.set(currentClient.id, list);
                return list;
            })
            .catch(function() { return []; });
    }

    function renderHistory(events) {
        const el = document.getElementById('clHistoryList');
        if (!el) return;

        if (!events.length) {
            el.innerHTML = '<div class="cl-empty">Nada por aqui ainda</div>';
            return;
        }

        const parts = [];
        for (let i = 0; i < events.length; i++) {
            const e = events[i];
            const detail = e.detail ? e.detail.replace(/\n+/g, ' ').trim() : '';

            parts.push(
                '<div class="cl-feed-item">' +
                    '<div class="cl-feed-icon is-' + escapeHtml(e.kind) + '">' +
                        '<i data-lucide="' + escapeHtml(e.icon) + '"></i>' +
                    '</div>' +
                    '<div class="cl-feed-stack">' +
                        '<p class="cl-feed-label">' + escapeHtml(e.label) + '</p>' +
                        (detail
                            ? '<p class="cl-feed-detail">' + escapeHtml(detail) + '</p>'
                            : '') +
                    '</div>' +
                    '<div class="cl-feed-meta">' +
                        '<span class="cl-feed-meta-date">' + formatDateTime(e.at) + '</span>' +
                        (e.author
                            ? '<span class="cl-feed-meta-author">' + escapeHtml(e.author) + '</span>'
                            : '') +
                    '</div>' +
                '</div>'
            );
        }
        el.innerHTML = parts.join('');
        refreshIcons();
    }

    // =====================================================================
    // MODAL EXCLUIR CLIENTE
    // =====================================================================
    function setupDeleteModal() {
        const modal = document.getElementById('clDeleteModal');
        const input = document.getElementById('clDeleteInput');
        const btn = document.getElementById('clDeleteConfirmBtn');
        if (!modal || !input || !btn) return;

        input.addEventListener('input', function() {
            const expected = (currentClient && currentClient.name) || '';
            btn.disabled = this.value.trim() !== expected;
        });

        btn.addEventListener('click', async function() {
            if (!currentClient) return;

            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Excluindo…';

            try {
                const deletedId = currentClient.id;
                await api('/api/clients/' + deletedId + '/', 'DELETE');
                showToast('Cliente excluído', 'success');
                modal.classList.remove('active');
                window.Clivo.cache.clients = null;

                detailCache.delete(deletedId);
                briefingsCacheByClient.delete(deletedId);
                clientsCache = clientsCache.filter(function(c) {
                    return c.id !== deletedId;
                });
                window.Clivo.cache.clients = {
                    data: clientsCache,
                    timestamp: Date.now(),
                };

                currentClient = null;
                closeDetail();
                renderClients();
                updateListSubtitle();
                ensureActive();
            } catch (e) {
                showToast(e.message || 'Erro', 'error');
                btn.disabled = false;
                btn.textContent = originalText;
            }
        });

        modal.querySelectorAll('[data-close="clDeleteModal"]').forEach(function(el) {
            el.addEventListener('click', function() {
                modal.classList.remove('active');
                input.value = '';
                btn.disabled = true;
            });
        });
    }

    // =====================================================================
    // AÇÕES DO DETALHE
    // =====================================================================
    function setupDetailActions() {
        const backBtn = document.getElementById('clBackBtn');
        if (backBtn) backBtn.addEventListener('click', closeDetail);

        const saveBtn = document.getElementById('clSaveIdentityBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', async function() {
                if (!currentClient) return;
                const btn = this;
                const nameEl = document.getElementById('clFieldName');
                const emailEl = document.getElementById('clFieldEmail');
                const phoneEl = document.getElementById('clFieldPhone');
                const payload = {
                    name: nameEl ? nameEl.value.trim() : '',
                    email: emailEl ? emailEl.value.trim() : '',
                    phone: phoneEl ? phoneEl.value.trim() : '',
                };
                if (!payload.name) { showToast('Informe o nome', 'error'); return; }

                setLoading(btn, true, 'Salvando…');
                try {
                    currentClient = await api('/api/clients/' + currentClient.id + '/', 'PATCH', payload);
                    detailCache.set(currentClient.id, currentClient);
                    renderDetail();

                    const idx = clientsCache.findIndex(function(c) { return c.id === currentClient.id; });
                    if (idx !== -1) {
                        clientsCache[idx] = Object.assign({}, clientsCache[idx], {
                            name: currentClient.name,
                            email: currentClient.email,
                            phone: currentClient.phone,
                        });
                        window.Clivo.cache.clients = {
                            data: clientsCache,
                            timestamp: Date.now(),
                        };
                        renderClients();
                        updateSelection();
                    }
                    loadHistorico();
                    showToast('Cliente atualizado', 'success');
                } catch (e) {
                    showToast(e.message || 'Erro', 'error');
                } finally {
                    setLoading(btn, false);
                }
            });
        }

        const copyBtn = document.getElementById('clCopyCodeBtn');
        if (copyBtn) {
            copyBtn.addEventListener('click', function() {
                if (!currentClient) return;
                if (navigator.clipboard) {
                    navigator.clipboard.writeText(currentClient.public_code || '');
                }
                showToast('Código copiado', 'success');
            });
        }

        const sendBtn = document.getElementById('clSendCodeBtn');
        if (sendBtn) {
            sendBtn.addEventListener('click', function() {
                sendClientCode(sendBtn);
            });
        }

        const delBtn = document.getElementById('clDeleteBtn');
        if (delBtn) {
            delBtn.addEventListener('click', function() {
                if (!currentClient) return;
                const input = document.getElementById('clDeleteInput');
                const confirmBtn = document.getElementById('clDeleteConfirmBtn');
                const modal = document.getElementById('clDeleteModal');
                if (input) input.value = '';
                if (confirmBtn) confirmBtn.disabled = true;
                if (modal) modal.classList.add('active');
                setTimeout(function() { if (input) input.focus(); }, 100);
            });
        }
    }

    async function sendClientCode(btn) {
        if (!currentClient) return;
        if (!currentClient.email) {
            showToast('Cliente não possui email cadastrado', 'error');
            return;
        }
        setLoading(btn, true, 'Enviando…');
        try {
            await api('/api/clients/' + currentClient.id + '/send-code/', 'POST');
            showToast('Código enviado por email', 'success');
        } catch (e) {
            showToast(e.message || 'Erro ao enviar', 'error');
        } finally {
            setLoading(btn, false);
        }
    }

    // =====================================================================
    // ROUTE / MOUNT / UNMOUNT
    // =====================================================================
    function route() {
        const hash = (window.location.hash || '').replace('#', '');

        if (hash) {
            openClient(hash);
            return;
        }

        if (clientsLoaded && clientsCache.length) {
            renderClients();
            updateListSubtitle();
            ensureActive();
        } else {
            loadClients().then(ensureActive);
        }
    }

    function ensureActive() {
        if (currentClient) return;
        if (window.innerWidth < 800) return;
        if (!clientsCache.length) return;
        openClient(clientsCache[0].id);
    }

    window.clivoOnClientCreated = function(created) {
        window.Clivo.cache.clients = null;
        clientsLoaded = false;
        if (window.Clivo.currentPage === 'cliente') {
            loadClients(true).then(function() {
                if (created && created.id) openClient(created.id);
            });
        }
    };

    window.clivoOnBriefingCreated = function(briefing, clientId) {
        if (!briefing || !clientId) return;
        if (window.Clivo.currentPage !== 'cliente') return;
        if (!currentClient || currentClient.id !== clientId) return;

        briefingsCacheByClient.delete(clientId);
        loadBriefings(true);
        loadHistorico();
    };

    window.clivoRefreshClientes = function() {
        if (window.Clivo.currentPage !== 'cliente') return;
        if (!currentClient) return;
        briefingsCacheByClient.delete(currentClient.id);
        loadBriefings(true);
        loadHistorico();
    };

    function mount() {
        if (!clientsLoaded) clientsCache = [];
        currentClient = null;
        briefingsCache = [];
        briefingsSearch = '';
        isOpening = false;

        const searchInput = document.getElementById('clSearchInput');
        if (searchInput) searchInput.addEventListener('input', function() {
            renderClients();
        });

        const statusFilter = document.getElementById('clStatusFilter');
        if (statusFilter) statusFilter.addEventListener('change', function() {
            renderClients();
        });

        setupDetailActions();
        setupDeleteModal();
        setupStatusMenu();
        setupBriefingsSearch();
        bindListEvents();

        loadClients().then(ensureActive);
    }

    function unmount() {
        closeStatusMenu();
    }

    window.ClivoPages = window.ClivoPages || {};
    window.ClivoPages.cliente = {
        mount: mount,
        unmount: unmount,
        route: route,
    };
})();