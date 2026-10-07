/* =========================================================================
   CLIENTES — página registrada no shell ClivoPages
   Layout master/detail — alta performance
   ========================================================================= */

(function() {
    'use strict';

    const DEBUG = false;

    function log() {
        if (DEBUG) console.log.apply(console, ['[clientes]'].concat(Array.from(arguments)));
    }

    function showToast(msg, type) {
        if (typeof window.clivoShowToast === 'function') {
            window.clivoShowToast(msg, type);
        }
    }

    async function api(url, method, body) {
        return window.clivoApi(url, method, body);
    }

    function escapeHtml(s) {
        if (s === null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function setLoading(btn, loading, label) {
        if (!btn) return;
        if (loading) {
            btn.disabled = true;
            btn.dataset.originalText = btn.innerHTML;
            btn.innerHTML =
                '<span class="loading-spinner" style="width:12px;height:12px;border-width:2px;border-color:rgba(255,255,255,0.3);border-top-color:#fff;"></span> ' +
                (label || 'Aguarde...');
        } else {
            btn.disabled = false;
            btn.innerHTML = btn.dataset.originalText || btn.textContent;
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

    function capitalize(s) {
        if (!s) return '';
        return s.charAt(0).toUpperCase() + s.slice(1);
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

    const CTX = {
        PROFILE: 'profile',
        KNOWLEDGE: 'knowledge',
        WISHES: 'wishes',
        DISLIKES: 'dislikes',
    };

    function updateGreeting() {
        const el = document.getElementById('clGreeting');
        if (!el) return;

        const hour = new Date().getHours();
        let greeting = 'Olá';
        if (hour < 12) greeting = 'Bom dia';
        else if (hour < 18) greeting = 'Boa tarde';
        else greeting = 'Boa noite';

        const user = window.Clivo.user;
        const firstName = user && user.full_name
            ? user.full_name.split(' ')[0]
            : (user && user.email ? user.email.split('@')[0] : '');

        el.textContent = firstName ? (greeting + ', ' + firstName) : 'Clientes';
    }

    // =====================================================================
    // ESTADO
    // =====================================================================
    let clientsCache = [];
    let clientsLoaded = false;
    let clientsPromise = null;     // dedup de fetch da lista
    let currentClient = null;
    let contactsCache = [];
    let notesCache = [];
    let tasksCache = [];
    let editingNoteId = null;
    let isOpening = false;
    let detailCache = {};          // { clientId: clientObject }
    let detailPromises = {};       // { clientId: Promise }

    // =====================================================================
    // LISTA
    // =====================================================================
    async function loadClients(force) {
        const listEl = document.getElementById('clList');
        if (!listEl) return;

        const CACHE_TTL = 30000;
        const now = Date.now();

        // --- Cache em memória ---
        if (!force && clientsLoaded && clientsCache.length) {
            log('loadClients: memória');
            renderClients();
            updateListSubtitle();
            return;
        }

        // --- Cache do shell ---
        if (!force && window.Clivo.cache.clients &&
            (now - window.Clivo.cache.clients.timestamp) < CACHE_TTL) {
            log('loadClients: shell');
            clientsCache = window.Clivo.cache.clients.data || [];
            clientsLoaded = true;
            renderClients();
            updateListSubtitle();
            return;
        }

        // --- Dedup: se já tem um fetch em andamento, reaproveita ---
        if (clientsPromise) {
            log('loadClients: reusando promise');
            await clientsPromise;
            renderClients();
            updateListSubtitle();
            return;
        }

        // --- Fetch ---
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
            listEl.innerHTML =
                '<div class="cl-empty">' +
                '<i data-lucide="alert-circle"></i>' +
                '<p>Erro ao carregar clientes</p>' +
                '<span style="font-size:11.5px;color:var(--text-tertiary);">' +
                escapeHtml(e.message || 'Erro desconhecido') +
                '</span>' +
                '</div>';
            refreshIcons();
            updateListSubtitle();
            return;
        }

        renderClients();
        updateListSubtitle();
    }

    function updateListSubtitle() {
        const subtitle = document.getElementById('clListSubtitle');
        if (!subtitle) return;
        const total = clientsCache.length;
        if (total === 0) subtitle.textContent = '';
        else if (total === 1) subtitle.textContent = '1 cliente';
        else subtitle.textContent = total + ' clientes';
    }

    function getFilteredClients() {
        const searchInput = document.getElementById('clSearchInput');
        const query = (searchInput && searchInput.value || '').trim().toLowerCase();

        const statusSelect = document.getElementById('clStatusFilter');
        const statusFilter = statusSelect ? statusSelect.value : '';

        let items = clientsCache.slice();

        if (statusFilter) {
            items = items.filter(function(c) { return c.status === statusFilter; });
        }

        if (query) {
            items = items.filter(function(c) {
                return (c.name || '').toLowerCase().indexOf(query) !== -1
                    || (c.email || '').toLowerCase().indexOf(query) !== -1;
            });
        }

        return items;
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
                '<div class="cl-empty">' +
                '<i data-lucide="users"></i>' +
                '<p>' + (hasQuery ? 'Nada encontrado' : 'Nenhum cliente ainda') + '</p>' +
                '</div>';
            refreshIcons();
            return;
        }

        let html = '';
        items.forEach(function(c) {
            const initial = (c.name || '?').charAt(0).toUpperCase();
            const email = c.email || '—';
            const isSelected = currentClient && currentClient.id === c.id;
            const status = c.status || 'active';
            const statusText = statusLabel(status);
            html +=
                '<div class="cl-card-item' + (isSelected ? ' is-selected' : '') + '" data-client-id="' + c.id + '">' +
                    '<div class="cl-card-avatar">' + escapeHtml(initial) + '</div>' +
                    '<div class="cl-card-info">' +
                        '<div class="cl-card-name">' +
                            '<span class="cl-status-led ' + escapeHtml(status) + '" title="' + escapeHtml(statusText) + '"></span>' +
                            '<span>' + escapeHtml(c.name) + '</span>' +
                        '</div>' +
                        '<div class="cl-card-meta">' + escapeHtml(email) + '</div>' +
                    '</div>' +
                '</div>';
        });

        listEl.innerHTML = html;
        refreshIcons();

        listEl.querySelectorAll('.cl-card-item').forEach(function(card) {
            // Prefetch no hover (economiza clique)
            card.addEventListener('mouseenter', function() {
                const id = this.dataset.clientId;
                if (id) prefetchClientDetail(id);
            });

            card.addEventListener('click', function() {
                const id = this.dataset.clientId;
                if (currentClient && currentClient.id === id) return;
                openClient(id);
            });
        });
    }

    function updateSelection() {
        const listEl = document.getElementById('clList');
        if (!listEl) return;
        const currentId = currentClient ? currentClient.id : null;

        listEl.querySelectorAll('.cl-card-item').forEach(function(card) {
            const isSelected = card.dataset.clientId === currentId;
            card.classList.toggle('is-selected', isSelected);
        });
    }

    // =====================================================================
    // DETALHE — com cache e prefetch
    // =====================================================================
    function showDetailEmpty() {
        const empty = document.getElementById('clDetailEmpty');
        const content = document.getElementById('clDetailContent');
        if (empty) empty.classList.remove('hidden');
        if (content) content.classList.add('hidden');
    }

    function showDetailContent() {
        const empty = document.getElementById('clDetailEmpty');
        const content = document.getElementById('clDetailContent');
        if (empty) empty.classList.add('hidden');
        if (content) content.classList.remove('hidden');
    }

    function prefetchClientDetail(clientId) {
        if (!clientId) return;
        if (detailCache[clientId]) return;
        if (detailPromises[clientId]) return;

        detailPromises[clientId] = api('/api/clients/' + clientId + '/')
            .then(function(client) {
                detailCache[clientId] = client;
                return client;
            })
            .catch(function() { /* silencioso */ })
            .finally(function() {
                delete detailPromises[clientId];
            });
    }

    function fetchClientDetail(clientId) {
        // Cache em memória
        if (detailCache[clientId]) {
            return Promise.resolve(detailCache[clientId]);
        }
        // Promise em andamento
        if (detailPromises[clientId]) {
            return detailPromises[clientId];
        }
        // Fetch novo
        const p = api('/api/clients/' + clientId + '/')
            .then(function(client) {
                detailCache[clientId] = client;
                return client;
            })
            .finally(function() {
                delete detailPromises[clientId];
            });
        detailPromises[clientId] = p;
        return p;
    }

    async function openClient(clientId) {
        if (isOpening) return;
        if (currentClient && currentClient.id === clientId) {
            updateSelection();
            return;
        }

        isOpening = true;
        try {
            const client = await fetchClientDetail(clientId);
            currentClient = client;

            if (window.location.hash !== '#' + clientId) {
                history.replaceState(
                    { soft: true, path: window.location.pathname + '#' + clientId },
                    '',
                    window.location.pathname + '#' + clientId
                );
            }

            renderDetail();
            showDetailContent();
            updateSelection();
            switchTab('geral');
        } catch (e) {
            showToast('Erro ao carregar cliente', 'error');
            showDetailEmpty();
        } finally {
            isOpening = false;
        }
    }

    function closeClient() {
        currentClient = null;
        showDetailEmpty();
        updateSelection();

        if (window.location.hash) {
            history.replaceState(
                { soft: true, path: window.location.pathname },
                '',
                window.location.pathname
            );
        }

        const items = getFilteredClients();
        if (items.length) {
            openClient(items[0].id);
        }
    }

    function renderDetail() {
        if (!currentClient) return;
        const c = currentClient;
        const status = c.status || 'active';
        const statusText = statusLabel(status);
        const initial = (c.name || '?').charAt(0).toUpperCase();

        const setText = function(id, val) {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        const av = document.getElementById('clDetailAvatar');
        if (av) av.textContent = initial;

        const nameEl = document.getElementById('clDetailName');
        if (nameEl) {
            nameEl.innerHTML =
                '<span>' + escapeHtml(c.name || '—') + '</span>' +
                '<span class="cl-status-badge ' + escapeHtml(status) + '">' +
                    escapeHtml(statusText) +
                '</span>';
        }

        setText('clDetailCode', c.public_code || '—');
        setText('clDetailCreatedAt',
            c.created_at ? ('Criado em ' + formatDate(c.created_at)) : '—');
        setText('clDetailCreatedBy',
            c.created_by_name ? ('por ' + c.created_by_name) : '—');

        const nameInput = document.getElementById('clFieldName');
        const emailInput = document.getElementById('clFieldEmail');
        const phoneInput = document.getElementById('clFieldPhone');
        const statusSelect = document.getElementById('clFieldStatus');
        if (nameInput) nameInput.value = c.name || '';
        if (emailInput) emailInput.value = c.email || '';
        if (phoneInput) phoneInput.value = c.phone || '';
        if (statusSelect) statusSelect.value = status;

        renderContextViews();

        setText('clCodeDisplay', c.public_code || '—');
        setText('clDeleteWord', c.name || '');

        document.title = 'Clientes · Clivo';
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

        pairs.forEach(function(pair) {
            const el = document.getElementById(pair.el);
            if (!el) return;
            if (pair.value) {
                el.innerHTML = '<p>' + escapeHtml(pair.value) + '</p>';
            } else {
                el.innerHTML = '<p class="cl-panel-empty">Sem informações ainda.</p>';
            }
        });
    }

    function switchTab(tabName) {
        document.querySelectorAll('#clDetailTabs button').forEach(function(b) {
            b.classList.toggle('active', b.dataset.tab === tabName);
        });
        document.querySelectorAll('.cl-tab-content').forEach(function(c) {
            c.classList.remove('active');
        });
        const target = document.getElementById('tab' + capitalize(tabName));
        if (target) target.classList.add('active');

        if (tabName === 'contatos') loadContacts();
        else if (tabName === 'relacionamento') loadRelacionamento();
        else if (tabName === 'timeline') loadTimeline();
    }

    // =====================================================================
    // ABA DE DETALHAMENTO SEMPRE ATIVA
    // =====================================================================
    function ensureActive() {
        // Se não há currentClient mas há clientes na lista, abre o primeiro
        if (currentClient) return;
        if (isOpening) return;

        const items = getFilteredClients();
        if (!items.length) return;

        openClient(items[0].id);
    }

    // =====================================================================
    // RELACIONAMENTO (Notas + Tarefas)
    // =====================================================================
    async function loadRelacionamento() {
        if (!currentClient) return;
        const results = await Promise.allSettled([
            api('/api/clients/' + currentClient.id + '/notes/'),
            api('/api/clients/' + currentClient.id + '/tasks/'),
        ]);

        notesCache = results[0].status === 'fulfilled'
            ? (Array.isArray(results[0].value) ? results[0].value : (results[0].value.results || []))
            : [];

        tasksCache = results[1].status === 'fulfilled'
            ? (Array.isArray(results[1].value) ? results[1].value : (results[1].value.results || []))
            : [];

        renderNotes();
        renderTasks();
    }

    function renderNotes() {
        const el = document.getElementById('clNotesList');
        const countEl = document.getElementById('clNotesCount');
        if (countEl) countEl.textContent = String(notesCache.length);
        if (!el) return;

        if (!notesCache.length) {
            el.innerHTML = '<div class="cl-empty"><i data-lucide="sticky-note"></i><p>Nenhuma nota</p></div>';
            refreshIcons();
            return;
        }
        let html = '';
        notesCache.forEach(function(n) {
            const author = n.author_name || n.author_email || 'Sistema';
            const pinned = n.is_pinned
                ? '<span class="cl-item-badge pinned">Fixada</span>'
                : '';
            html +=
                '<div class="cl-item">' +
                    '<div class="cl-item-body">' +
                        '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
                            '<span class="cl-item-meta">' + escapeHtml(author) + ' · ' + formatDateTime(n.created_at) + '</span>' +
                            pinned +
                        '</div>' +
                        '<p class="cl-item-content">' + escapeHtml(n.content) + '</p>' +
                    '</div>' +
                    '<div class="cl-item-actions">' +
                        '<button class="btn-minimal" data-note-edit="' + n.id + '" title="Editar">' +
                            '<i data-lucide="pencil"></i>' +
                        '</button>' +
                        '<button class="btn-minimal btn-minimal-danger" data-note-delete="' + n.id + '" title="Excluir">' +
                            '<i data-lucide="trash-2"></i>' +
                        '</button>' +
                    '</div>' +
                '</div>';
        });
        el.innerHTML = html;
        refreshIcons();

        el.querySelectorAll('[data-note-edit]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const id = this.dataset.noteEdit;
                const note = notesCache.find(function(n) { return n.id === id; });
                if (note) openNoteModal(note);
            });
        });
        el.querySelectorAll('[data-note-delete]').forEach(function(btn) {
            btn.addEventListener('click', async function() {
                const id = this.dataset.noteDelete;
                if (!confirm('Excluir esta nota?')) return;
                try {
                    await api('/api/clients/' + currentClient.id + '/notes/' + id + '/', 'DELETE');
                    showToast('Nota removida', 'success');
                    loadRelacionamento();
                } catch (e) {
                    showToast(e.message || 'Erro', 'error');
                }
            });
        });
    }

    function renderTasks() {
        const el = document.getElementById('clTasksList');
        const countEl = document.getElementById('clTasksCount');
        if (countEl) countEl.textContent = String(tasksCache.length);
        if (!el) return;

        if (!tasksCache.length) {
            el.innerHTML = '<div class="cl-empty"><i data-lucide="check-square"></i><p>Nenhuma tarefa</p></div>';
            refreshIcons();
            return;
        }
        let html = '';
        tasksCache.forEach(function(t) {
            const statusLabel_ = t.status_display || t.status;
            const statusClass = t.status;
            const doneClass = t.status === 'done' ? ' done' : '';
            const isOpen = t.status === 'open';
            const createdBy = t.created_by_name || '—';
            html +=
                '<div class="cl-item cl-task-row' + doneClass + '" data-task-id="' + t.id + '">' +
                    '<div class="cl-item-body">' +
                        '<p class="cl-item-title">' + escapeHtml(t.title) + '</p>' +
                        (t.description
                            ? '<p class="cl-item-content">' + escapeHtml(t.description) + '</p>'
                            : '') +
                        '<div class="cl-item-meta">' + escapeHtml(createdBy) +
                            (t.due_at ? ' · ' + formatDate(t.due_at) : '') + '</div>' +
                    '</div>' +
                    '<span class="cl-item-badge ' + statusClass + '">' + escapeHtml(statusLabel_) + '</span>' +
                    '<div class="cl-item-actions">' +
                        (isOpen
                            ? '<button class="btn-minimal" data-task-complete="' + t.id + '" title="Concluir">' +
                                  '<i data-lucide="check"></i>' +
                              '</button>'
                            : '<button class="btn-minimal" data-task-reopen="' + t.id + '" title="Reabrir">' +
                                  '<i data-lucide="rotate-ccw"></i>' +
                              '</button>') +
                        '<button class="btn-minimal btn-minimal-danger" data-task-delete="' + t.id + '" title="Excluir">' +
                            '<i data-lucide="trash-2"></i>' +
                        '</button>' +
                    '</div>' +
                '</div>';
        });
        el.innerHTML = html;
        refreshIcons();

        el.querySelectorAll('[data-task-complete]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                updateTaskStatus(this.dataset.taskComplete, 'complete');
            });
        });
        el.querySelectorAll('[data-task-reopen]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                updateTaskStatus(this.dataset.taskReopen, 'reopen');
            });
        });
        el.querySelectorAll('[data-task-delete]').forEach(function(btn) {
            btn.addEventListener('click', async function() {
                if (!confirm('Excluir esta tarefa?')) return;
                try {
                    await api('/api/clients/' + currentClient.id + '/tasks/' + this.dataset.taskDelete + '/', 'DELETE');
                    showToast('Tarefa removida', 'success');
                    loadRelacionamento();
                } catch (e) {
                    showToast(e.message || 'Erro', 'error');
                }
            });
        });
    }

    async function updateTaskStatus(taskId, action) {
        try {
            await api(
                '/api/clients/' + currentClient.id + '/tasks/' + taskId + '/' + action + '/',
                'POST'
            );
            showToast('Tarefa atualizada', 'success');
            loadRelacionamento();
        } catch (e) {
            showToast(e.message || 'Erro', 'error');
        }
    }

    // =====================================================================
    // CONTATOS
    // =====================================================================
    async function loadContacts() {
        const el = document.getElementById('clContactsList');
        if (!el) return;
        el.innerHTML = '<div class="cl-empty"><p>Carregando…</p></div>';
        try {
            const data = await api('/api/clients/' + currentClient.id + '/contacts/');
            contactsCache = Array.isArray(data) ? data : [];
        } catch (e) {
            contactsCache = [];
        }
        renderContacts();
    }

    function renderContacts() {
        const el = document.getElementById('clContactsList');
        if (!el) return;
        if (!contactsCache.length) {
            el.innerHTML = '<div class="cl-empty"><i data-lucide="user"></i><p>Nenhum contato</p></div>';
            refreshIcons();
            return;
        }
        let html = '';
        contactsCache.forEach(function(c) {
            const initial = (c.name || '?').charAt(0).toUpperCase();
            html +=
                '<div class="cl-item">' +
                    '<div class="cl-item-avatar">' + escapeHtml(initial) + '</div>' +
                    '<div class="cl-item-body">' +
                        '<p class="cl-item-title">' + escapeHtml(c.name) + '</p>' +
                        '<div class="cl-item-meta">' + escapeHtml(c.role_display || c.role || '') +
                            (c.email ? ' · ' + escapeHtml(c.email) : '') + '</div>' +
                    '</div>' +
                    '<div class="cl-item-actions">' +
                        '<button class="btn-minimal btn-minimal-danger" data-contact-delete="' + c.id + '" title="Remover">' +
                            '<i data-lucide="trash-2"></i>' +
                        '</button>' +
                    '</div>' +
                '</div>';
        });
        el.innerHTML = html;
        refreshIcons();

        el.querySelectorAll('[data-contact-delete]').forEach(function(btn) {
            btn.addEventListener('click', async function() {
                const id = this.dataset.contactDelete;
                if (!confirm('Remover este contato?')) return;
                try {
                    await api('/api/clients/' + currentClient.id + '/contacts/' + id + '/', 'DELETE');
                    showToast('Contato removido', 'success');
                    loadContacts();
                } catch (e) {
                    showToast(e.message || 'Erro', 'error');
                }
            });
        });
    }

    // =====================================================================
    // TIMELINE
    // =====================================================================
    async function loadTimeline() {
        const el = document.getElementById('clTimeline');
        if (!el) return;
        el.innerHTML = '<div class="cl-empty"><p>Carregando…</p></div>';
        let items = [];
        try {
            items = await api('/api/clients/' + currentClient.id + '/timeline/');
        } catch (e) {
            items = [];
        }

        if (!items.length) {
            el.innerHTML = '<div class="cl-empty"><i data-lucide="activity"></i><p>Nenhuma atividade ainda</p></div>';
            refreshIcons();
            return;
        }

        let html = '';
        items.forEach(function(i) {
            html +=
                '<div class="cl-tl-item">' +
                    '<div class="cl-tl-time">' + formatDateTime(i.occurred_at) +
                        (i.actor_name ? ' · ' + escapeHtml(i.actor_name) : '') + '</div>' +
                    '<p class="cl-tl-title">' + escapeHtml(i.title) + '</p>' +
                    (i.subtitle ? '<p class="cl-tl-sub">' + escapeHtml(i.subtitle) + '</p>' : '') +
                '</div>';
        });
        el.innerHTML = html;
    }

    // =====================================================================
    // MODAIS
    // =====================================================================
    function openNoteModal(note) {
        editingNoteId = note ? note.id : null;
        const titleEl = document.getElementById('clNoteModalTitle');
        const contentEl = document.getElementById('clNoteContent');
        const pinnedEl = document.getElementById('clNotePinned');
        const modal = document.getElementById('clNewNoteModal');
        if (titleEl) titleEl.textContent = note ? 'Editar nota' : 'Nova nota';
        if (contentEl) contentEl.value = note ? note.content : '';
        if (pinnedEl) pinnedEl.checked = note ? !!note.is_pinned : false;
        if (modal) modal.classList.add('active');
        setTimeout(function() { if (contentEl) contentEl.focus(); }, 100);
    }

    function setupNoteModal() {
        const modal = document.getElementById('clNewNoteModal');
        const saveBtn = document.getElementById('clSaveNoteBtn');
        if (!modal || !saveBtn) return;

        saveBtn.addEventListener('click', async function() {
            const contentEl = document.getElementById('clNoteContent');
            const pinnedEl = document.getElementById('clNotePinned');
            const content = contentEl ? contentEl.value.trim() : '';
            const isPinned = pinnedEl ? pinnedEl.checked : false;
            if (!content) { showToast('Escreva algo', 'error'); return; }

            setLoading(saveBtn, true, 'Salvando…');
            try {
                if (editingNoteId) {
                    await api(
                        '/api/clients/' + currentClient.id + '/notes/' + editingNoteId + '/',
                        'PATCH',
                        { content: content, is_pinned: isPinned }
                    );
                    showToast('Nota atualizada', 'success');
                } else {
                    await api(
                        '/api/clients/' + currentClient.id + '/notes/',
                        'POST',
                        { content: content, is_pinned: isPinned }
                    );
                    showToast('Nota criada', 'success');
                }
                modal.classList.remove('active');
                editingNoteId = null;
                loadRelacionamento();
            } catch (e) {
                showToast(e.message || 'Erro', 'error');
            } finally {
                setLoading(saveBtn, false);
            }
        });

        modal.querySelectorAll('[data-close="clNewNoteModal"]').forEach(function(el) {
            el.addEventListener('click', function() { modal.classList.remove('active'); });
        });
    }

    function openTaskModal() {
        const titleEl = document.getElementById('clTaskTitle');
        const descEl = document.getElementById('clTaskDescription');
        const prioEl = document.getElementById('clTaskPriority');
        const dueEl = document.getElementById('clTaskDueAt');
        const modal = document.getElementById('clNewTaskModal');
        if (titleEl) titleEl.value = '';
        if (descEl) descEl.value = '';
        if (prioEl) prioEl.value = 'normal';
        if (dueEl) dueEl.value = '';
        if (modal) modal.classList.add('active');
        setTimeout(function() { if (titleEl) titleEl.focus(); }, 100);
    }

    function setupTaskModal() {
        const modal = document.getElementById('clNewTaskModal');
        const saveBtn = document.getElementById('clSaveTaskBtn');
        if (!modal || !saveBtn) return;

        saveBtn.addEventListener('click', async function() {
            const titleEl = document.getElementById('clTaskTitle');
            const descEl = document.getElementById('clTaskDescription');
            const prioEl = document.getElementById('clTaskPriority');
            const dueEl = document.getElementById('clTaskDueAt');

            const title = titleEl ? titleEl.value.trim() : '';
            const description = descEl ? descEl.value.trim() : '';
            const priority = prioEl ? prioEl.value : 'normal';
            const dueAtRaw = dueEl ? dueEl.value : '';

            if (!title) { showToast('Informe o título', 'error'); return; }

            const payload = {
                title: title,
                description: description,
                priority: priority,
            };
            if (dueAtRaw) {
                payload.due_at = new Date(dueAtRaw + 'T12:00:00').toISOString();
            }

            setLoading(saveBtn, true, 'Salvando…');
            try {
                await api(
                    '/api/clients/' + currentClient.id + '/tasks/',
                    'POST',
                    payload
                );
                showToast('Tarefa criada', 'success');
                modal.classList.remove('active');
                loadRelacionamento();
            } catch (e) {
                showToast(e.message || 'Erro', 'error');
            } finally {
                setLoading(saveBtn, false);
            }
        });

        modal.querySelectorAll('[data-close="clNewTaskModal"]').forEach(function(el) {
            el.addEventListener('click', function() { modal.classList.remove('active'); });
        });
    }

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
            setLoading(btn, true, 'Excluindo…');
            try {
                const deletedId = currentClient.id;
                await api('/api/clients/' + deletedId + '/', 'DELETE');
                showToast('Cliente excluído', 'success');
                modal.classList.remove('active');
                window.Clivo.cache.clients = null;

                delete detailCache[deletedId];
                clientsCache = clientsCache.filter(function(c) {
                    return c.id !== deletedId;
                });
                window.Clivo.cache.clients = {
                    data: clientsCache,
                    timestamp: Date.now(),
                };

                currentClient = null;
                showDetailEmpty();
                if (window.location.hash) {
                    history.replaceState(
                        { soft: true, path: window.location.pathname },
                        '',
                        window.location.pathname
                    );
                }
                renderClients();
                updateListSubtitle();
                ensureActive();
            } catch (e) {
                showToast(e.message || 'Erro', 'error');
                setLoading(btn, false);
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
    // AÇÕES
    // =====================================================================
    function setupDetailActions() {
        const saveBtn = document.getElementById('clSaveIdentityBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', async function() {
                if (!currentClient) return;
                const btn = this;
                const nameEl = document.getElementById('clFieldName');
                const emailEl = document.getElementById('clFieldEmail');
                const phoneEl = document.getElementById('clFieldPhone');
                const statusEl = document.getElementById('clFieldStatus');
                const payload = {
                    name: nameEl ? nameEl.value.trim() : '',
                    email: emailEl ? emailEl.value.trim() : '',
                    phone: phoneEl ? phoneEl.value.trim() : '',
                    status: statusEl ? statusEl.value : 'active',
                };
                if (!payload.name) { showToast('Informe o nome', 'error'); return; }

                setLoading(btn, true, 'Salvando…');
                try {
                    currentClient = await api('/api/clients/' + currentClient.id + '/', 'PATCH', payload);
                    detailCache[currentClient.id] = currentClient;
                    renderDetail();

                    const idx = clientsCache.findIndex(function(c) { return c.id === currentClient.id; });
                    if (idx !== -1) {
                        clientsCache[idx] = Object.assign({}, clientsCache[idx], {
                            name: currentClient.name,
                            email: currentClient.email,
                            phone: currentClient.phone,
                            status: currentClient.status,
                        });
                        window.Clivo.cache.clients = {
                            data: clientsCache,
                            timestamp: Date.now(),
                        };
                        renderClients();
                    }
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
                if (navigator.clipboard) navigator.clipboard.writeText(currentClient.public_code);
                showToast('Código copiado', 'success');
            });
        }

        const sendBtn = document.getElementById('clSendCodeBtn');
        if (sendBtn) {
            sendBtn.addEventListener('click', async function() {
                if (!currentClient) return;
                const btn = this;
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

        const addContactBtn = document.getElementById('clAddContactBtn');
        if (addContactBtn) {
            addContactBtn.addEventListener('click', function() {
                const name = prompt('Nome do contato:');
                if (!name) return;
                const email = prompt('Email (opcional):') || '';
                const phone = prompt('Telefone (opcional):') || '';
                api('/api/clients/' + currentClient.id + '/contacts/', 'POST', {
                    name: name.trim(),
                    role: 'other',
                    email: email.trim(),
                    phone: phone.trim(),
                }).then(function() {
                    showToast('Contato adicionado', 'success');
                    loadContacts();
                }).catch(function(e) {
                    showToast(e.message || 'Erro', 'error');
                });
            });
        }

        const addNoteBtn = document.getElementById('clAddNoteBtn');
        if (addNoteBtn) {
            addNoteBtn.addEventListener('click', function() {
                openNoteModal(null);
            });
        }

        const addTaskBtn = document.getElementById('clAddTaskBtn');
        if (addTaskBtn) {
            addTaskBtn.addEventListener('click', function() {
                openTaskModal();
            });
        }
    }

    // =====================================================================
    // ROUTE
    // =====================================================================
    function route() {
        const hash = (window.location.hash || '').replace('#', '');

        if (hash) {
            openClient(hash);
            return;
        }

        // Sem hash — garante que a aba de detalhamento fique ativa
        if (clientsLoaded && clientsCache.length) {
            renderClients();
            updateListSubtitle();
            ensureActive();
        } else {
            loadClients().then(ensureActive);
        }
    }

    window.clivoOnClientCreated = function() {
        window.Clivo.cache.clients = null;
        clientsLoaded = false;
        if (window.Clivo.currentPage === 'clientes') {
            loadClients(true).then(ensureActive);
        }
    };

    // =====================================================================
    // MOUNT / UNMOUNT
    // =====================================================================
    function mount() {
        if (!clientsLoaded) clientsCache = [];
        currentClient = null;
        contactsCache = [];
        notesCache = [];
        tasksCache = [];
        editingNoteId = null;
        isOpening = false;

        updateGreeting();

        document.querySelectorAll('#clDetailTabs button').forEach(function(btn) {
            btn.addEventListener('click', function() {
                switchTab(this.dataset.tab);
            });
        });

        const searchInput = document.getElementById('clSearchInput');
        if (searchInput) searchInput.addEventListener('input', function() {
            renderClients();
        });

        const statusFilter = document.getElementById('clStatusFilter');
        if (statusFilter) statusFilter.addEventListener('change', function() {
            renderClients();
        });

        setupDetailActions();
        setupNoteModal();
        setupTaskModal();
        setupDeleteModal();

        loadClients().then(ensureActive);
    }

    function unmount() {
        // Nada a limpar.
    }

    window.ClivoPages = window.ClivoPages || {};
    window.ClivoPages.clientes = {
        mount: mount,
        unmount: unmount,
        route: route,
    };

    if (typeof window.requestIdleCallback !== 'function') {
        window.requestIdleCallback = function(cb, opts) {
            const start = Date.now();
            return setTimeout(function() {
                cb({
                    didTimeout: false,
                    timeRemaining: function() {
                        return Math.max(0, 50 - (Date.now() - start));
                    }
                });
            }, 1);
        };
    }

})();