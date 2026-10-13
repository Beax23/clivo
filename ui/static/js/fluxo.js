/* =========================================================================
   FLUXO — Categorias → Modelos → Sessões → Perguntas
   Cards compactos de modelo, menu "⋮" em todas as colunas,
   formulário inline de pergunta com opções (single/multiple choice),
   upload de capa e upload de imagem por opção.
   ========================================================================= */

(function () {
    'use strict';

    /* =====================================================================
       ENDPOINTS
       ===================================================================== */
    const API = {
        categories: '/api/briefing-template-categories/',
        categoryDetail: (id) => `/api/briefing-template-categories/${id}/`,
        categoryReorder: '/api/briefing-template-categories/reorder/',

        templates: '/api/briefing-templates/',
        templateDetail: (id) => `/api/briefing-templates/${id}/`,
        templateSections: (id) => `/api/briefing-templates/${id}/sections/`,
        templateSetActive: (id) => `/api/briefing-templates/${id}/set-active/`,
        templateCover: (id) => `/api/briefing-templates/${id}/cover/`,
        templateCoverClear: (id) => `/api/briefing-templates/${id}/cover/clear/`,
        templateReorder: '/api/briefing-templates/reorder/',

        sectionDetail: (tid, sid) => `/api/briefing-templates/${tid}/sections/${sid}/`,
        sectionQuestions: (tid, sid) => `/api/briefing-templates/${tid}/sections/${sid}/questions/`,
        sectionReorder: (tid) => `/api/briefing-templates/${tid}/sections/reorder/`,

        questionDetail: (tid, qid) => `/api/briefing-templates/${tid}/questions/${qid}/`,
        questionReorder: (tid, sid) => `/api/briefing-templates/${tid}/sections/${sid}/questions/reorder/`,

        documents: '/api/documents/',
    };

    /* =====================================================================
       ESTADO
       ===================================================================== */
    const state = {
        categories: [],
        templates: [],
        selectedCategoryId: null,
        selectedTemplateId: null,
        selectedSectionId: null,
        editingQuestion: null,
        editingTemplateId: null,
        editingCategoryId: null,
        editingSectionId: null,
        options: [],
        search: '',
        coverFile: null,
        coverPreviewUrl: null,
        mounted: false,
    };

    /* =====================================================================
       HELPERS
       ===================================================================== */
    const $ = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

    function getCookie(name) {
        const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
        return v ? v.pop() : '';
    }

    async function api(url, options = {}) {
        const opts = {
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'X-Requested-With': 'XMLHttpRequest',
                ...(options.headers || {}),
            },
            credentials: 'same-origin',
            ...options,
        };
        if (!(opts.body instanceof FormData) && opts.body && typeof opts.body === 'object') {
            opts.headers['Content-Type'] = 'application/json';
            opts.body = JSON.stringify(opts.body);
        }
        const res = await fetch(url, opts);
        if (res.status === 204) return null;
        let data;
        const ct = res.headers.get('content-type') || '';
        if (ct.includes('application/json')) data = await res.json();
        else data = await res.text();
        if (!res.ok) {
            const err = new Error((data && (data.error || data.detail)) || `Erro ${res.status}`);
            err.status = res.status;
            err.data = data;
            throw err;
        }
        return data;
    }

    function pickArray(data, key) {
        if (!data) return [];
        if (Array.isArray(data)) return data;
        if (key && Array.isArray(data[key])) return data[key];
        if (Array.isArray(data.results)) return data.results;
        if (Array.isArray(data.items)) return data.items;
        return [];
    }

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function refreshIcons() {
        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            window.lucide.createIcons();
        }
    }

    function toast(message, type) {
        if (typeof window.clivoShowToast === 'function') {
            window.clivoShowToast(message, type || 'info');
        }
    }

    function withCacheBuster(url) {
        if (!url) return url;
        if (url.startsWith('http://') || url.startsWith('https://')) {
            if (url.includes('X-Amz-Signature') || url.includes('Signature=')) return url;
        }
        const sep = url.includes('?') ? '&' : '?';
        return url + sep + 'v=' + Date.now();
    }

    /* =====================================================================
       MODAIS
       ===================================================================== */
    function openModal(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.add('is-open');
        document.body.style.overflow = 'hidden';
        refreshIcons();
    }

    function closeModal(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.remove('is-open');
        if (!$('.fx-modal-overlay.is-open')) document.body.style.overflow = '';
    }

    function bindModalClosers() {
        $$('[data-fx-close]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const id = btn.getAttribute('data-fx-close');
                if (id) closeModal(id);
            });
        });
        $$('.fx-modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) closeModal(overlay.id);
            });
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const open = $('.fx-modal-overlay.is-open');
                if (open) closeModal(open.id);
            }
        });
    }

    let pendingDelete = null;
    function confirmDelete({ title, subtitle, onConfirm }) {
        $('#fxDeleteTitle').textContent = title || 'Excluir?';
        $('#fxDeleteSub').textContent = subtitle || 'Esta ação não pode ser desfeita.';
        pendingDelete = onConfirm;
        openModal('fxModalDelete');
    }
    function bindDeleteModal() {
        const btn = $('#fxDeleteConfirm');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            if (!pendingDelete) return;
            const cb = pendingDelete;
            pendingDelete = null;
            closeModal('fxModalDelete');
            try { await cb(); } catch (e) { console.error(e); }
        });
    }

    /* =====================================================================
       MENU "⋮"
       ===================================================================== */
    let openMenuEl = null;

    function closeKebabMenu() {
        if (!openMenuEl) return;
        openMenuEl.remove();
        openMenuEl = null;
        $$('.fx-kebab.is-open').forEach(b => b.classList.remove('is-open'));
    }

    function openKebabMenu(anchorBtn, items) {
        closeKebabMenu();
        const rect = anchorBtn.getBoundingClientRect();
        const menu = document.createElement('div');
        menu.className = 'fx-menu';
        items.forEach(item => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'fx-menu-item' + (item.danger ? ' fx-menu-item--danger' : '');
            btn.innerHTML =
                '<i data-lucide="' + (item.icon || 'circle') + '"></i>' +
                '<span>' + escapeHtml(item.label) + '</span>';
            btn.addEventListener('click', (ev) => {
                ev.stopPropagation();
                closeKebabMenu();
                try { item.onClick && item.onClick(); } catch (e) { console.error(e); }
            });
            menu.appendChild(btn);
        });
        document.body.appendChild(menu);

        const mw = menu.offsetWidth;
        const mh = menu.offsetHeight;
        let left = rect.right - mw;
        let top = rect.bottom + 4;
        if (left < 8) left = 8;
        if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
        if (top + mh > window.innerHeight - 8) top = rect.top - mh - 4;
        menu.style.left = left + 'px';
        menu.style.top = top + 'px';

        menu.classList.add('is-open');
        anchorBtn.classList.add('is-open');
        openMenuEl = menu;
        refreshIcons();

        setTimeout(() => {
            const off = (ev) => {
                if (menu.contains(ev.target) || anchorBtn.contains(ev.target)) return;
                closeKebabMenu();
                document.removeEventListener('click', off, true);
            };
            document.addEventListener('click', off, true);
        }, 0);
    }

    function buildKebab(items) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'fx-kebab';
        btn.setAttribute('title', 'Mais ações');
        btn.innerHTML = '<i data-lucide="more-vertical"></i>';
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openKebabMenu(btn, items);
        });
        return btn;
    }

    /* =====================================================================
       DRAG-AND-DROP
       ===================================================================== */
    function makeSortable(container, itemSelector, options = {}) {
        if (!container) return () => {};
        const handleSelector = options.handleSelector || '.fx-drag-handle';
        const onReorder = options.onReorder || (() => {});

        let draggingEl = null;

        function getItems() {
            return Array.from(container.querySelectorAll(itemSelector));
        }

        function onDragStart(e) {
            const handle = e.target.closest(handleSelector);
            if (!handle) return;
            const item = handle.closest(itemSelector);
            if (!item) return;
            draggingEl = item;
            item.classList.add('is-dragging');
            e.dataTransfer.effectAllowed = 'move';
            try { e.dataTransfer.setData('text/plain', ''); } catch (_) {}
        }

        function onDragOver(e) {
            if (!draggingEl) return;
            const over = e.target.closest(itemSelector);
            if (!over || over === draggingEl) return;
            e.preventDefault();
            const rect = over.getBoundingClientRect();
            const isAfter = e.clientY > rect.top + rect.height / 2;
            const ref = isAfter ? over.nextSibling : over;
            container.insertBefore(draggingEl, ref);
        }

        function onDragEnd() {
            if (!draggingEl) return;
            draggingEl.classList.remove('is-dragging');
            const orderedIds = getItems()
                .map(el => el.dataset.id)
                .filter(Boolean);
            draggingEl = null;
            onReorder(orderedIds);
        }

        container.addEventListener('dragstart', onDragStart);
        container.addEventListener('dragover', onDragOver);
        container.addEventListener('dragend', onDragEnd);

        return () => {
            container.removeEventListener('dragstart', onDragStart);
            container.removeEventListener('dragover', onDragOver);
            container.removeEventListener('dragend', onDragEnd);
        };
    }

    function buildDragHandle() {
        const h = document.createElement('span');
        h.className = 'fx-drag-handle';
        h.draggable = true;
        h.innerHTML = '<i data-lucide="grip-vertical"></i>';
        return h;
    }

    /* =====================================================================
       CATEGORIAS
       ===================================================================== */
    async function loadCategories() {
        try {
            const data = await api(API.categories);
            state.categories = pickArray(data, 'results');
        } catch (err) {
            if (err.status !== 404) console.error('Erro ao carregar categorias:', err);
            state.categories = [];
        }
        renderCategories();
        populateCategorySelect();
    }

    function renderCategories() {
        const list = $('#fxCategoriesList');
        if (!list) return;
        list.innerHTML = '';

        const allItem = document.createElement('li');
        allItem.className = 'fx-list-item' +
            (state.selectedCategoryId === null ? ' is-active' : '');
        allItem.dataset.id = '__all__';
        allItem.innerHTML =
            '<i data-lucide="layers" style="width:14px;height:14px;flex-shrink:0;opacity:.7;"></i>' +
            '<span class="fx-list-item-name">Todas</span>' +
            '<span class="fx-list-item-meta">' + state.templates.length + '</span>';
        allItem.addEventListener('click', () => {
            state.selectedCategoryId = null;
            renderCategories();
            renderTemplates();
        });
        list.appendChild(allItem);

        if (!state.categories.length) {
            const empty = document.createElement('li');
            empty.className = 'fx-list-empty';
            empty.textContent = 'Nenhuma categoria ainda.';
            list.appendChild(empty);
            refreshIcons();
            attachCategoriesSortable();
            return;
        }

        state.categories.forEach(cat => {
            const count = state.templates.filter(t =>
                String(t.category_id || t.category || '') === String(cat.id)
            ).length;

            const li = document.createElement('li');
            li.className = 'fx-list-item' +
                (String(state.selectedCategoryId) === String(cat.id) ? ' is-active' : '');
            li.dataset.id = cat.id;

            const drag = buildDragHandle();

            const icon = document.createElement('i');
            icon.setAttribute('data-lucide', 'folder');
            icon.style.cssText = 'width:14px;height:14px;flex-shrink:0;opacity:.7;';

            const nameSpan = document.createElement('span');
            nameSpan.className = 'fx-list-item-name';
            nameSpan.textContent = cat.name || '—';

            const metaSpan = document.createElement('span');
            metaSpan.className = 'fx-list-item-meta';
            metaSpan.textContent = count;

            const kebab = buildKebab([
                { label: 'Editar', icon: 'pencil', onClick: () => openEditCategoryModal(cat) },
                {
                    label: 'Excluir', icon: 'trash-2', danger: true,
                    onClick: () => confirmDelete({
                        title: `Excluir "${cat.name}"?`,
                        subtitle: 'Os modelos dessa categoria ficarão sem categoria.',
                        onConfirm: async () => {
                            await api(API.categoryDetail(cat.id), { method: 'DELETE' });
                            toast('Categoria excluída.', 'success');
                            if (String(state.selectedCategoryId) === String(cat.id)) state.selectedCategoryId = null;
                            await loadCategories();
                        },
                    }),
                },
            ]);

            li.appendChild(drag);
            li.appendChild(icon);
            li.appendChild(nameSpan);
            li.appendChild(metaSpan);
            li.appendChild(kebab);

            li.addEventListener('click', (e) => {
                if (e.target.closest('.fx-kebab') || e.target.closest('.fx-drag-handle')) return;
                state.selectedCategoryId = cat.id;
                renderCategories();
                renderTemplates();
            });
            list.appendChild(li);
        });

        refreshIcons();
        attachCategoriesSortable();
    }

    let categoriesSortableCleanup = null;
    function attachCategoriesSortable() {
        if (categoriesSortableCleanup) categoriesSortableCleanup();
        const list = $('#fxCategoriesList');
        if (!list) return;
        categoriesSortableCleanup = makeSortable(list, '.fx-list-item', {
            onReorder: async (orderedIds) => {
                const ids = orderedIds.filter(id => id && id !== '__all__');
                try {
                    await api(API.categoryReorder, {
                        method: 'POST',
                        body: { ordered_ids: ids },
                    });
                    await loadCategories();
                } catch (e) {
                    console.error(e);
                    toast('Erro ao reordenar categorias.', 'error');
                }
            },
        });
    }

    function populateCategorySelect() {
        const sel = $('#fxTplCategory');
        if (!sel) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">Sem categoria</option>';
        state.categories.forEach(cat => {
            const opt = document.createElement('option');
            opt.value = cat.id;
            opt.textContent = cat.name;
            sel.appendChild(opt);
        });
        if (current) sel.value = current;
    }

    /* =====================================================================
       MODELOS
       ===================================================================== */
    async function loadTemplates() {
        try {
            const data = await api(API.templates);
            state.templates = pickArray(data, 'results');
        } catch (err) {
            console.error('Erro ao carregar modelos:', err);
            state.templates = [];
            toast('Erro ao carregar modelos.', 'error');
        }
        renderTemplates();
        renderCategories();
    }

    function templatesInCategory() {
        let list = state.templates.slice();
        if (state.selectedCategoryId !== null) {
            list = list.filter(t =>
                String(t.category_id || t.category || '') === String(state.selectedCategoryId)
            );
        }
        if (state.search) {
            const q = state.search.toLowerCase();
            list = list.filter(t => (t.name || '').toLowerCase().includes(q));
        }
        return list;
    }

    function renderTemplates() {
        const grid = $('#fxTemplatesList');
        const count = $('#fxTemplatesCount');
        if (!grid) return;

        const items = templatesInCategory();
        if (count) count.textContent = String(items.length);

        grid.innerHTML = '';
        if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'fx-list-empty';
            empty.textContent = state.search
                ? 'Nada encontrado.'
                : (state.templates.length ? 'Nada nesta categoria.' : 'Nenhum modelo criado ainda.');
            grid.appendChild(empty);
            refreshIcons();
            attachTemplatesSortable();
            return;
        }

        items.forEach(t => grid.appendChild(buildTemplateCard(t)));
        refreshIcons();
        attachTemplatesSortable();
    }

    function buildTemplateCard(t) {
        const isActive = t.is_active !== false;
        const card = document.createElement('div');
        card.className = 'fx-tpl-card' +
            (String(state.selectedTemplateId) === String(t.id) ? ' is-active' : '') +
            (isActive ? '' : ' is-inactive');
        card.dataset.id = t.id;

        const coverUrl = t.cover_url || '';
        const sectionsCount = t.sections_count || 0;
        const questionsCount = t.questions_count || 0;

        const thumb = document.createElement('div');
        thumb.className = 'fx-tpl-thumb';
        if (coverUrl) {
            const imgUrl = withCacheBuster(coverUrl);
            thumb.innerHTML = `<img src="${escapeHtml(imgUrl)}" alt="" loading="lazy" onerror="this.style.display='none';this.parentNode.innerHTML='<i data-lucide=\\'image\\'></i>';if(window.lucide)window.lucide.createIcons();">`;
        } else {
            thumb.innerHTML = `<i data-lucide="image"></i>`;
        }
        const dot = document.createElement('span');
        dot.className = 'fx-tpl-thumb-dot' + (isActive ? '' : ' is-off');
        thumb.appendChild(dot);

        const info = document.createElement('div');
        info.className = 'fx-tpl-info';
        info.innerHTML = `
            <div class="fx-tpl-name">${escapeHtml(t.name || '—')}</div>
            <div class="fx-tpl-meta">
                <span class="fx-tpl-meta-item"><i data-lucide="layers"></i>${sectionsCount} sessões</span>
                <span class="fx-tpl-meta-sep"></span>
                <span class="fx-tpl-meta-item"><i data-lucide="help-circle"></i>${questionsCount} perguntas</span>
            </div>
        `;

        const actions = document.createElement('div');
        actions.className = 'fx-tpl-actions';

        const toggleWrap = document.createElement('label');
        toggleWrap.className = 'fx-mini-switch';
        toggleWrap.innerHTML = `
            <input type="checkbox" ${isActive ? 'checked' : ''}>
            <span class="fx-mini-switch-track"><span class="fx-mini-switch-thumb"></span></span>
        `;
        const toggleInput = toggleWrap.querySelector('input');
        toggleInput.addEventListener('click', (e) => e.stopPropagation());
        toggleInput.addEventListener('change', async (e) => {
            e.stopPropagation();
            const newValue = toggleInput.checked;
            toggleWrap.classList.add('is-loading');
            try {
                await api(API.templateSetActive(t.id), {
                    method: 'POST', body: { is_active: newValue },
                });
                const idx = state.templates.findIndex(x => String(x.id) === String(t.id));
                if (idx !== -1) state.templates[idx].is_active = newValue;
                const newCard = buildTemplateCard(state.templates[idx]);
                card.replaceWith(newCard);
                refreshIcons();
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao alterar estado.', 'error');
                toggleInput.checked = !newValue;
                toggleWrap.classList.remove('is-loading');
            }
        });

        const kebab = buildKebab([
            { label: 'Editar', icon: 'pencil', onClick: () => openEditTemplateModal(t) },
            { label: 'Trocar capa', icon: 'image-plus', onClick: () => openEditTemplateModal(t, true) },
            {
                label: 'Excluir', icon: 'trash-2', danger: true,
                onClick: () => confirmDelete({
                    title: `Excluir "${t.name}"?`,
                    subtitle: 'Sessões e perguntas vinculadas serão removidas.',
                    onConfirm: async () => {
                        await api(API.templateDetail(t.id), { method: 'DELETE' });
                        toast('Modelo excluído.', 'success');
                        if (String(state.selectedTemplateId) === String(t.id)) {
                            state.selectedTemplateId = null;
                            state.selectedSectionId = null;
                            renderSections(null);
                            renderQuestions(null);
                        }
                        await loadTemplates();
                    },
                }),
            },
        ]);

        actions.appendChild(toggleWrap);
        actions.appendChild(kebab);

        card.appendChild(thumb);
        card.appendChild(info);
        card.appendChild(actions);

        card.draggable = false;
        thumb.draggable = true;
        thumb.addEventListener('dragstart', (e) => {
            card.classList.add('is-dragging');
            e.dataTransfer.effectAllowed = 'move';
            try { e.dataTransfer.setData('text/plain', ''); } catch (_) {}
        });
        thumb.addEventListener('dragend', () => {
            card.classList.remove('is-dragging');
            const orderedIds = Array.from(
                $('#fxTemplatesList').querySelectorAll('.fx-tpl-card[data-id]')
            ).map(el => el.dataset.id);
            reorderTemplates(orderedIds);
        });

        card.addEventListener('click', (e) => {
            if (e.target.closest('.fx-tpl-actions')) return;
            selectTemplate(t.id);
        });

        return card;
    }

    let templatesSortableCleanup = null;
    function attachTemplatesSortable() {
        if (templatesSortableCleanup) templatesSortableCleanup();
        const grid = $('#fxTemplatesList');
        if (!grid) return;

        let dragging = null;

        function onDragStart(e) {
            const card = e.target.closest('.fx-tpl-card');
            if (!card) return;
            dragging = card;
        }
        function onDragOver(e) {
            if (!dragging) return;
            const over = e.target.closest('.fx-tpl-card');
            if (!over || over === dragging) return;
            e.preventDefault();
            const rect = over.getBoundingClientRect();
            const isAfter = e.clientY > rect.top + rect.height / 2;
            const ref = isAfter ? over.nextSibling : over;
            grid.insertBefore(dragging, ref);
        }
        function onDragEnd() {
            if (!dragging) return;
            const orderedIds = Array.from(
                grid.querySelectorAll('.fx-tpl-card[data-id]')
            ).map(el => el.dataset.id);
            dragging = null;
            reorderTemplates(orderedIds);
        }

        grid.addEventListener('dragstart', onDragStart);
        grid.addEventListener('dragover', onDragOver);
        grid.addEventListener('dragend', onDragEnd);

        templatesSortableCleanup = () => {
            grid.removeEventListener('dragstart', onDragStart);
            grid.removeEventListener('dragover', onDragOver);
            grid.removeEventListener('dragend', onDragEnd);
        };
    }

    function reorderTemplates(orderedIds) {
        const byId = Object.fromEntries(state.templates.map(t => [String(t.id), t]));
        const newList = orderedIds.map(id => byId[id]).filter(Boolean);
        state.templates.forEach(t => {
            if (!newList.find(x => String(x.id) === String(t.id))) newList.push(t);
        });
        state.templates = newList;
        api(API.templateReorder, {
            method: 'POST',
            body: { ordered_ids: orderedIds },
        }).catch(() => {});
    }

    /* =====================================================================
       SELEÇÃO DE MODELO
       ===================================================================== */
    async function selectTemplate(templateId) {
        state.selectedTemplateId = templateId;
        state.selectedSectionId = null;
        renderTemplates();
        await loadTemplateDetail(templateId);
    }

    async function loadTemplateDetail(templateId) {
        try {
            const data = await api(API.templateDetail(templateId));
            const idx = state.templates.findIndex(t => String(t.id) === String(templateId));
            if (idx !== -1) state.templates[idx] = { ...state.templates[idx], ...data };
            renderSections(data);
            showQuestionsListView();
        } catch (err) {
            console.error('Erro ao carregar modelo:', err);
            toast('Erro ao carregar modelo.', 'error');
        }
    }

    /* =====================================================================
       SESSÕES
       ===================================================================== */
    function renderSections(template) {
        const list = $('#fxSectionsList');
        const count = $('#fxSectionsCount');
        const sub = $('#fxSectionsSub');
        const newBtn = $('#fxNewSectionBtn');
        if (!list) return;

        const sections = (template && template.sections) || [];
        if (count) count.textContent = String(sections.length);
        if (sub) sub.textContent = template ? (template.name || '—') : 'Selecione um modelo';
        if (newBtn) newBtn.disabled = !template;

        list.innerHTML = '';
        if (!template) {
            list.innerHTML = '<li class="fx-list-empty">Nenhum modelo selecionado.</li>';
            return;
        }
        if (!sections.length) {
            list.innerHTML = '<li class="fx-list-empty">Nenhuma sessão ainda.</li>';
            return;
        }

        sections.forEach((s, idx) => {
            const qCount = (s.questions && s.questions.length) || 0;
            const li = document.createElement('li');
            li.className = 'fx-list-item' +
                (String(state.selectedSectionId) === String(s.id) ? ' is-active' : '');
            li.dataset.id = s.id;

            const drag = buildDragHandle();

            const num = document.createElement('span');
            num.className = 'fx-num';
            num.textContent = String(idx + 1);

            const nameSpan = document.createElement('span');
            nameSpan.className = 'fx-list-item-name';
            nameSpan.textContent = s.title || '—';

            const metaSpan = document.createElement('span');
            metaSpan.className = 'fx-list-item-meta';
            metaSpan.textContent = qCount;

            const kebab = buildKebab([
                { label: 'Editar', icon: 'pencil', onClick: () => openEditSectionModal(s) },
                {
                    label: 'Excluir', icon: 'trash-2', danger: true,
                    onClick: () => confirmDelete({
                        title: `Excluir "${s.title}"?`,
                        subtitle: 'As perguntas dessa sessão serão removidas.',
                        onConfirm: async () => {
                            await api(API.sectionDetail(state.selectedTemplateId, s.id), { method: 'DELETE' });
                            toast('Sessão excluída.', 'success');
                            if (String(state.selectedSectionId) === String(s.id)) {
                                state.selectedSectionId = null;
                                renderQuestions(null);
                            }
                            await loadTemplateDetail(state.selectedTemplateId);
                        },
                    }),
                },
            ]);

            li.appendChild(drag);
            li.appendChild(num);
            li.appendChild(nameSpan);
            li.appendChild(metaSpan);
            li.appendChild(kebab);

            li.addEventListener('click', (e) => {
                if (e.target.closest('.fx-kebab') || e.target.closest('.fx-drag-handle')) return;
                selectSection(template.id, s.id);
            });
            list.appendChild(li);
        });

        refreshIcons();
        attachSectionsSortable();
    }

    let sectionsSortableCleanup = null;
    function attachSectionsSortable() {
        if (sectionsSortableCleanup) sectionsSortableCleanup();
        const list = $('#fxSectionsList');
        if (!list) return;
        sectionsSortableCleanup = makeSortable(list, '.fx-list-item', {
            onReorder: async (orderedIds) => {
                if (!state.selectedTemplateId) return;
                try {
                    await api(API.sectionReorder(state.selectedTemplateId), {
                        method: 'POST',
                        body: { ordered_ids: orderedIds },
                    });
                    await loadTemplateDetail(state.selectedTemplateId);
                } catch (e) {
                    console.error(e);
                    toast('Erro ao reordenar sessões.', 'error');
                }
            },
        });
    }

    function selectSection(templateId, sectionId) {
        state.selectedSectionId = sectionId;
        const template = state.templates.find(t => String(t.id) === String(templateId));
        if (!template) return;

        renderSections(template);
        const section = (template.sections || []).find(s => String(s.id) === String(sectionId));
        renderQuestions(section);
        showQuestionsListView();
    }

    /* =====================================================================
       PERGUNTAS
       ===================================================================== */
    function renderQuestions(section) {
        const list = $('#fxQuestionsList');
        const count = $('#fxQuestionsCount');
        const sub = $('#fxQuestionsSub');
        const newBtn = $('#fxNewQuestionBtn');
        if (!list) return;

        const questions = (section && section.questions) || [];
        if (count) count.textContent = String(questions.length);
        if (sub) sub.textContent = section ? (section.title || '—') : 'Selecione uma sessão';
        if (newBtn) newBtn.disabled = !section;

        list.innerHTML = '';
        if (!section) {
            list.innerHTML = '<li class="fx-list-empty">Nenhuma sessão selecionada.</li>';
            return;
        }
        if (!questions.length) {
            list.innerHTML = '<li class="fx-list-empty">Nenhuma pergunta ainda.</li>';
            return;
        }

        questions.forEach((q, idx) => {
            const li = document.createElement('li');
            li.className = 'fx-list-item';
            li.dataset.id = q.id;

            const drag = buildDragHandle();

            const num = document.createElement('span');
            num.className = 'fx-num';
            num.textContent = String(idx + 1);

            const nameSpan = document.createElement('span');
            nameSpan.className = 'fx-list-item-name';
            nameSpan.textContent = q.text || '—';

            const metaSpan = document.createElement('span');
            metaSpan.className = 'fx-list-item-meta';
            const formats = (q.allowed_response_formats || []).join(' · ');
            metaSpan.textContent = formats;

            const kebab = buildKebab([
                { label: 'Editar', icon: 'pencil', onClick: () => openEditQuestionForm(q) },
                {
                    label: 'Excluir', icon: 'trash-2', danger: true,
                    onClick: () => confirmDelete({
                        title: 'Excluir esta pergunta?',
                        subtitle: 'A pergunta será removida da sessão.',
                        onConfirm: async () => {
                            await api(API.questionDetail(state.selectedTemplateId, q.id), { method: 'DELETE' });
                            toast('Pergunta excluída.', 'success');
                            await loadTemplateDetail(state.selectedTemplateId);
                            const tpl = state.templates.find(t => String(t.id) === String(state.selectedTemplateId));
                            const sec = tpl && (tpl.sections || []).find(s => String(s.id) === String(state.selectedSectionId));
                            if (sec) renderQuestions(sec);
                        },
                    }),
                },
            ]);

            li.appendChild(drag);
            li.appendChild(num);
            li.appendChild(nameSpan);
            li.appendChild(metaSpan);
            li.appendChild(kebab);
            li.addEventListener('click', (e) => {
                if (e.target.closest('.fx-kebab') || e.target.closest('.fx-drag-handle')) return;
                openEditQuestionForm(q);
            });
            list.appendChild(li);
        });

        refreshIcons();
        attachQuestionsSortable();
    }

    let questionsSortableCleanup = null;
    function attachQuestionsSortable() {
        if (questionsSortableCleanup) questionsSortableCleanup();
        const list = $('#fxQuestionsList');
        if (!list) return;
        questionsSortableCleanup = makeSortable(list, '.fx-list-item', {
            onReorder: async (orderedIds) => {
                if (!state.selectedTemplateId || !state.selectedSectionId) return;
                try {
                    await api(API.questionReorder(state.selectedTemplateId, state.selectedSectionId), {
                        method: 'POST',
                        body: { ordered_ids: orderedIds },
                    });
                    await loadTemplateDetail(state.selectedTemplateId);
                    const tpl = state.templates.find(t => String(t.id) === String(state.selectedTemplateId));
                    const sec = tpl && (tpl.sections || []).find(s => String(s.id) === String(state.selectedSectionId));
                    if (sec) renderQuestions(sec);
                } catch (e) {
                    console.error(e);
                    toast('Erro ao reordenar perguntas.', 'error');
                }
            },
        });
    }

    /* =====================================================================
       PERGUNTAS — form inline
       ===================================================================== */
    function showQuestionsListView() {
        const listView = $('#fxQuestionsScroll [data-view="list"]');
        const formView = $('#fxQuestionsScroll [data-view="form"]');
        if (listView) listView.classList.remove('is-hidden');
        if (formView) formView.classList.add('is-hidden');
        state.editingQuestion = null;
    }

    function showQuestionsFormView() {
        const listView = $('#fxQuestionsScroll [data-view="list"]');
        const formView = $('#fxQuestionsScroll [data-view="form"]');
        if (listView) listView.classList.add('is-hidden');
        if (formView) formView.classList.remove('is-hidden');
        const scroll = $('#fxQuestionsScroll');
        if (scroll) scroll.scrollTop = 0;
    }

    function openNewQuestionForm() {
        if (!state.selectedTemplateId || !state.selectedSectionId) {
            toast('Selecione um modelo e uma sessão antes.', 'info');
            return;
        }
        state.editingQuestion = null;
        resetQuestionForm();
        $('#fxQFormTitle').textContent = 'Nova pergunta';
        const tpl = state.templates.find(t => String(t.id) === String(state.selectedTemplateId));
        const sec = tpl && (tpl.sections || []).find(s => String(s.id) === String(state.selectedSectionId));
        $('#fxQFormSub').textContent = sec ? (sec.title || '—') : '';
        $('#fxQSubmit').textContent = 'Criar pergunta';
        showQuestionsFormView();
        refreshIcons();
        setTimeout(() => { const el = $('#fxQText'); if (el) el.focus(); }, 50);
    }

    function openEditQuestionForm(q) {
        state.editingQuestion = q;
        resetQuestionForm();

        $('#fxQText').value = q.text || '';
        $('#fxQInstructions').value = q.instructions || '';
        $('#fxQType').value = q.question_type || 'text';
        $('#fxQRequired').checked = q.is_required !== false;

        const formats = q.allowed_response_formats || ['text', 'audio', 'image'];
        $$('input[name="fxQFormat"]').forEach(el => { el.checked = formats.includes(el.value); });

        state.options = Array.isArray(q.options)
            ? q.options.map(o => ({
                text: o.text || '',
                image_url: o.image_url || '',
                image_document_id: o.image_document_id || null,
                _file: null,
            }))
            : [];
        renderOptions();

        $('#fxQFormTitle').textContent = 'Editar pergunta';
        const tpl = state.templates.find(t => String(t.id) === String(state.selectedTemplateId));
        const sec = tpl && (tpl.sections || []).find(s => String(s.id) === String(state.selectedSectionId));
        $('#fxQFormSub').textContent = sec ? (sec.title || '—') : '';
        $('#fxQSubmit').textContent = 'Salvar';

        toggleOptionsVisibility();
        showQuestionsFormView();
        refreshIcons();
    }

    function resetQuestionForm() {
        const form = $('#fxQForm');
        if (form) form.reset();
        $('#fxQRequired').checked = true;
        $$('input[name="fxQFormat"]').forEach(el => { el.checked = true; });
        $('#fxQType').value = 'text';
        state.options = [];
        renderOptions();
        toggleOptionsVisibility();
    }

    function toggleOptionsVisibility() {
        const type = $('#fxQType').value;
        const field = $('#fxQOptionsField');
        if (!field) return;
        const shouldShow = type === 'single_choice' || type === 'multiple_choice';
        field.classList.toggle('is-hidden', !shouldShow);
        if (shouldShow && state.options.length === 0) {
            state.options.push({ text: '', image_url: '', image_document_id: null, _file: null });
            state.options.push({ text: '', image_url: '', image_document_id: null, _file: null });
            renderOptions();
        }
    }

    function renderOptions() {
        const list = $('#fxQOptionsList');
        if (!list) return;
        list.innerHTML = '';

        state.options.forEach((opt, idx) => {
            const row = document.createElement('div');
            row.className = 'fx-option-row';

            const drag = document.createElement('span');
            drag.className = 'fx-option-drag';
            drag.innerHTML = '<i data-lucide="grip-vertical"></i>';

            const thumb = document.createElement('label');
            thumb.className = 'fx-option-thumb';
            thumb.title = 'Adicionar imagem';
            if (opt.image_url) {
                thumb.innerHTML = `<img src="${escapeHtml(opt.image_url)}" alt="" onerror="this.style.display='none';this.parentNode.innerHTML='<i data-lucide=\\'image-plus\\'></i>';if(window.lucide)window.lucide.createIcons();">`;
            } else {
                thumb.innerHTML = '<i data-lucide="image-plus"></i>';
            }
            const fileInput = document.createElement('input');
            fileInput.type = 'file';
            fileInput.accept = 'image/*';
            fileInput.addEventListener('change', (e) => {
                const file = e.target.files && e.target.files[0];
                if (!file) return;
                opt._file = file;
                if (opt.image_url && opt.image_url.startsWith('blob:')) {
                    URL.revokeObjectURL(opt.image_url);
                }
                opt.image_url = URL.createObjectURL(file);
                renderOptions();
            });
            thumb.appendChild(fileInput);

            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'fx-option-input';
            input.placeholder = 'Nome da opção';
            input.value = opt.text || '';
            input.maxLength = 200;
            input.addEventListener('input', () => { opt.text = input.value; });

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'fx-option-remove';
            remove.title = 'Remover';
            remove.innerHTML = '<i data-lucide="x"></i>';
            remove.addEventListener('click', () => {
                if (opt.image_url && opt.image_url.startsWith('blob:')) {
                    URL.revokeObjectURL(opt.image_url);
                }
                state.options.splice(idx, 1);
                renderOptions();
            });

            row.appendChild(drag);
            row.appendChild(thumb);
            row.appendChild(input);
            row.appendChild(remove);
            list.appendChild(row);
        });

        refreshIcons();
    }

    async function uploadOptionImage(file) {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('kind', 'image');
        const doc = await api(API.documents, { method: 'POST', body: fd });
        return doc;
    }

    async function submitQuestionForm(e) {
        e.preventDefault();
        const templateId = state.selectedTemplateId;
        const sectionId = state.selectedSectionId;
        if (!templateId || !sectionId) {
            toast('Selecione modelo e sessão.', 'error');
            return;
        }

        const text = $('#fxQText').value.trim();
        const instructions = $('#fxQInstructions').value.trim();
        const questionType = $('#fxQType').value;
        const formats = $$('input[name="fxQFormat"]:checked').map(el => el.value);
        const isRequired = $('#fxQRequired').checked;

        if (!text) { toast('Informe o enunciado.', 'error'); return; }
        if (!formats.length) { toast('Escolha ao menos um formato.', 'error'); return; }

        const isChoice = questionType === 'single_choice' || questionType === 'multiple_choice';
        let optionsPayload = [];

        if (isChoice) {
            const cleaned = state.options
                .map(o => ({ ...o, text: (o.text || '').trim() }))
                .filter(o => o.text);

            if (cleaned.length < 2) {
                toast('Adicione pelo menos 2 opções com texto.', 'error');
                return;
            }

            const submitBtn = $('#fxQSubmit');
            const original = submitBtn.textContent;
            submitBtn.disabled = true;
            submitBtn.textContent = 'Enviando imagens…';

            try {
                for (const opt of cleaned) {
                    if (opt._file) {
                        const doc = await uploadOptionImage(opt._file);
                        if (doc && doc.id) {
                            opt.image_document_id = doc.id;
                            if (doc.file_url || doc.preview_url) {
                                if (opt.image_url && opt.image_url.startsWith('blob:')) {
                                    URL.revokeObjectURL(opt.image_url);
                                }
                                opt.image_url = doc.file_url || doc.preview_url;
                            }
                        } else {
                            opt.image_document_id = null;
                        }
                        opt._file = null;
                    }
                }
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao enviar imagem.', 'error');
                submitBtn.disabled = false;
                submitBtn.textContent = original;
                return;
            }

            optionsPayload = cleaned.map(o => ({
                text: o.text,
                image_document_id: o.image_document_id || null,
            }));
        }

        const payload = {
            text,
            instructions,
            question_type: questionType,
            allowed_response_formats: formats,
            is_required: isRequired,
        };
        if (isChoice) payload.options = optionsPayload;

        const submitBtn = $('#fxQSubmit');
        const original = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Salvando…';

        try {
            if (state.editingQuestion) {
                await api(API.questionDetail(templateId, state.editingQuestion.id), {
                    method: 'PATCH', body: payload,
                });
                toast('Pergunta atualizada.', 'success');
            } else {
                await api(API.sectionQuestions(templateId, sectionId), {
                    method: 'POST', body: payload,
                });
                toast('Pergunta criada.', 'success');
            }
            await loadTemplateDetail(templateId);
            const tpl = state.templates.find(t => String(t.id) === String(templateId));
            const sec = tpl && (tpl.sections || []).find(s => String(s.id) === String(sectionId));
            if (sec) renderQuestions(sec);
            showQuestionsListView();
        } catch (err) {
            console.error(err);
            toast(err.message || 'Erro ao salvar pergunta.', 'error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = original;
        }
    }

    /* =====================================================================
       AÇÕES — Categoria
       ===================================================================== */
    function openNewCategoryModal() {
        state.editingCategoryId = null;
        $('#fxFormCategory').reset();
        $('#fxCatModalTitle').textContent = 'Nova categoria';
        $('#fxCatSubmit').textContent = 'Criar categoria';
        openModal('fxModalCategory');
    }

    function openEditCategoryModal(cat) {
        state.editingCategoryId = cat.id;
        $('#fxCatName').value = cat.name || '';
        $('#fxCatModalTitle').textContent = 'Editar categoria';
        $('#fxCatSubmit').textContent = 'Salvar';
        openModal('fxModalCategory');
    }

    function setupCategoryModal() {
        const form = $('#fxFormCategory');
        const submit = $('#fxCatSubmit');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = $('#fxCatName').value.trim();
            if (!name) { toast('Informe o nome.', 'error'); return; }

            const original = submit.textContent;
            submit.disabled = true;
            submit.textContent = 'Salvando…';
            try {
                if (state.editingCategoryId) {
                    await api(API.categoryDetail(state.editingCategoryId), {
                        method: 'PATCH', body: { name },
                    });
                    toast('Categoria atualizada.', 'success');
                } else {
                    await api(API.categories, { method: 'POST', body: { name } });
                    toast('Categoria criada.', 'success');
                }
                closeModal('fxModalCategory');
                form.reset();
                state.editingCategoryId = null;
                await loadCategories();
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao salvar.', 'error');
            } finally {
                submit.disabled = false;
                submit.textContent = original;
            }
        });
    }

    /* =====================================================================
       AÇÕES — Modelo
       ===================================================================== */
    function openNewTemplateModal() {
        state.editingTemplateId = null;
        state.coverFile = null;
        state.coverPreviewUrl = null;
        $('#fxFormTemplate').reset();
        populateCategorySelect();
        if (state.selectedCategoryId) $('#fxTplCategory').value = state.selectedCategoryId;
        updateCoverPreview(null);
        $('#fxTplModalTitle').textContent = 'Novo modelo';
        $('#fxTplSubmit').textContent = 'Criar modelo';
        openModal('fxModalTemplate');
    }

    function openEditTemplateModal(t, focusCover = false) {
        state.editingTemplateId = t.id;
        state.coverFile = null;
        state.coverPreviewUrl = t.cover_url || null;
        populateCategorySelect();
        $('#fxTplName').value = t.name || '';
        $('#fxTplCategory').value = t.category_id || t.category || '';
        $('#fxTplDescription').value = t.description || '';
        updateCoverPreview(state.coverPreviewUrl);
        $('#fxTplModalTitle').textContent = 'Editar modelo';
        $('#fxTplSubmit').textContent = 'Salvar';
        openModal('fxModalTemplate');
        if (focusCover) setTimeout(() => { const el = $('#fxTplCover'); if (el) el.click(); }, 80);
    }

    function updateCoverPreview(url) {
        const preview = $('#fxTplCoverPreview');
        const clear = $('#fxTplCoverClear');
        if (!preview) return;
        if (url) {
            preview.classList.add('has-image');
            const finalUrl = url.startsWith('blob:') ? url : withCacheBuster(url);
            preview.innerHTML = `<img src="${escapeHtml(finalUrl)}" alt="" onerror="this.style.display='none';">`;
            if (clear) clear.classList.remove('is-hidden');
        } else {
            preview.classList.remove('has-image');
            preview.innerHTML = '<i data-lucide="image-plus"></i><span>Adicionar capa</span>';
            if (clear) clear.classList.add('is-hidden');
        }
        refreshIcons();
    }

    function setupCoverPicker() {
        const input = $('#fxTplCover');
        const clear = $('#fxTplCoverClear');
        if (input) {
            input.addEventListener('change', (e) => {
                const file = e.target.files && e.target.files[0];
                if (!file) return;
                state.coverFile = file;
                if (state.coverPreviewUrl && state.coverPreviewUrl.startsWith('blob:')) {
                    URL.revokeObjectURL(state.coverPreviewUrl);
                }
                state.coverPreviewUrl = URL.createObjectURL(file);
                updateCoverPreview(state.coverPreviewUrl);
            });
        }
        if (clear) {
            clear.addEventListener('click', (e) => {
                e.preventDefault();
                state.coverFile = null;
                state.coverPreviewUrl = null;
                if (input) input.value = '';
                updateCoverPreview(null);
            });
        }
    }

    async function uploadTemplateCover(templateId, file) {
        const fd = new FormData();
        fd.append('cover', file);
        return await api(API.templateCover(templateId), { method: 'POST', body: fd });
    }

    async function clearTemplateCover(templateId) {
        return await api(API.templateCoverClear(templateId), { method: 'DELETE' });
    }

    function setupTemplateModal() {
        const form = $('#fxFormTemplate');
        const submit = $('#fxTplSubmit');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = $('#fxTplName').value.trim();
            const categoryId = $('#fxTplCategory').value;
            const description = $('#fxTplDescription').value.trim();
            if (!name) { toast('Informe o nome.', 'error'); return; }

            const payload = { name, description: description || '' };
            if (categoryId) payload.category_id = categoryId;

            const original = submit.textContent;
            submit.disabled = true;
            submit.textContent = 'Salvando…';
            try {
                let updatedTemplate = null;
                let templateId = state.editingTemplateId;

                if (state.editingTemplateId) {
                    try {
                        updatedTemplate = await api(API.templateDetail(state.editingTemplateId), {
                            method: 'PATCH', body: payload,
                        });
                    } catch (err) {
                        if (err.status === 400 && 'category_id' in payload) {
                            delete payload.category_id;
                            updatedTemplate = await api(API.templateDetail(state.editingTemplateId), {
                                method: 'PATCH', body: payload,
                            });
                        } else throw err;
                    }
                    toast('Modelo atualizado.', 'success');
                } else {
                    try {
                        updatedTemplate = await api(API.templates, { method: 'POST', body: payload });
                    } catch (err) {
                        if (err.status === 400 && 'category_id' in payload) {
                            delete payload.category_id;
                            updatedTemplate = await api(API.templates, { method: 'POST', body: payload });
                        } else throw err;
                    }
                    toast('Modelo criado.', 'success');
                    templateId = updatedTemplate && updatedTemplate.id;
                }

                if (templateId && state.coverFile) {
                    submit.textContent = 'Enviando capa…';
                    try {
                        const withCover = await uploadTemplateCover(templateId, state.coverFile);
                        if (withCover) updatedTemplate = withCover;
                    } catch (err) {
                        console.error(err);
                        toast(err.message || 'Falha ao enviar capa.', 'error');
                    }
                }

                closeModal('fxModalTemplate');
                form.reset();
                state.editingTemplateId = null;
                state.coverFile = null;
                if (state.coverPreviewUrl && state.coverPreviewUrl.startsWith('blob:')) {
                    URL.revokeObjectURL(state.coverPreviewUrl);
                }
                state.coverPreviewUrl = null;

                if (updatedTemplate && updatedTemplate.id) {
                    const idx = state.templates.findIndex(t => String(t.id) === String(updatedTemplate.id));
                    if (idx !== -1) {
                        state.templates[idx] = { ...state.templates[idx], ...updatedTemplate };
                    } else {
                        state.templates.unshift(updatedTemplate);
                    }
                    renderTemplates();
                } else {
                    await loadTemplates();
                }

                if (updatedTemplate && updatedTemplate.id) {
                    await selectTemplate(updatedTemplate.id);
                }
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao salvar.', 'error');
            } finally {
                submit.disabled = false;
                submit.textContent = original;
            }
        });
    }

    /* =====================================================================
       AÇÕES — Sessão
       ===================================================================== */
    function openNewSectionModal() {
        if (!state.selectedTemplateId) { toast('Selecione um modelo.', 'info'); return; }
        state.editingSectionId = null;
        $('#fxFormSection').reset();
        $('#fxSecModalTitle').textContent = 'Nova sessão';
        $('#fxSecSubmit').textContent = 'Criar sessão';
        openModal('fxModalSection');
    }

    function openEditSectionModal(s) {
        state.editingSectionId = s.id;
        $('#fxSecTitle').value = s.title || '';
        $('#fxSecDescription').value = s.description || '';
        $('#fxSecModalTitle').textContent = 'Editar sessão';
        $('#fxSecSubmit').textContent = 'Salvar';
        openModal('fxModalSection');
    }

    function setupSectionModal() {
        const form = $('#fxFormSection');
        const submit = $('#fxSecSubmit');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const templateId = state.selectedTemplateId;
            if (!templateId) { toast('Selecione um modelo.', 'error'); return; }

            const title = $('#fxSecTitle').value.trim();
            const description = $('#fxSecDescription').value.trim();
            if (!title) { toast('Informe o título.', 'error'); return; }

            const original = submit.textContent;
            submit.disabled = true;
            submit.textContent = 'Salvando…';
            try {
                if (state.editingSectionId) {
                    await api(API.sectionDetail(templateId, state.editingSectionId), {
                        method: 'PATCH',
                        body: { title, description: description || '' },
                    });
                    toast('Sessão atualizada.', 'success');
                } else {
                    await api(API.templateSections(templateId), {
                        method: 'POST',
                        body: { title, description: description || '' },
                    });
                    toast('Sessão criada.', 'success');
                }
                closeModal('fxModalSection');
                form.reset();
                state.editingSectionId = null;
                await loadTemplateDetail(templateId);
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao salvar.', 'error');
            } finally {
                submit.disabled = false;
                submit.textContent = original;
            }
        });
    }

    /* =====================================================================
       BIND — botões
       ===================================================================== */
    function bindCreateButtons() {
        const newCatBtn = $('#fxNewCategoryBtn');
        if (newCatBtn) newCatBtn.addEventListener('click', openNewCategoryModal);

        const newTplBtn = $('#fxNewTemplateBtn');
        if (newTplBtn) newTplBtn.addEventListener('click', openNewTemplateModal);

        const newSecBtn = $('#fxNewSectionBtn');
        if (newSecBtn) newSecBtn.addEventListener('click', openNewSectionModal);

        const newQBtm = $('#fxNewQuestionBtn');
        if (newQBtm) newQBtm.addEventListener('click', openNewQuestionForm);

        const backBtn = $('#fxQBackBtn');
        if (backBtn) backBtn.addEventListener('click', showQuestionsListView);

        const cancelBtn = $('#fxQCancelBtn');
        if (cancelBtn) cancelBtn.addEventListener('click', showQuestionsListView);

        const addOptBtn = $('#fxQAddOptionBtn');
        if (addOptBtn) addOptBtn.addEventListener('click', () => {
            state.options.push({ text: '', image_url: '', image_document_id: null, _file: null });
            renderOptions();
        });

        const typeSel = $('#fxQType');
        if (typeSel) typeSel.addEventListener('change', toggleOptionsVisibility);

        const qForm = $('#fxQForm');
        if (qForm) qForm.addEventListener('submit', submitQuestionForm);

        const search = $('#fxTemplatesSearch');
        if (search) search.addEventListener('input', () => {
            state.search = search.value.trim();
            renderTemplates();
        });
    }

    /* =====================================================================
       MOUNT / UNMOUNT
       ===================================================================== */
    async function mount() {
        if (state.mounted) return;
        state.mounted = true;

        state.selectedCategoryId = null;
        state.selectedTemplateId = null;
        state.selectedSectionId = null;
        state.editingQuestion = null;
        state.editingTemplateId = null;
        state.editingCategoryId = null;
        state.editingSectionId = null;
        state.options = [];
        state.search = '';
        state.coverFile = null;
        state.coverPreviewUrl = null;

        bindCreateButtons();
        bindModalClosers();
        bindDeleteModal();
        setupCategoryModal();
        setupTemplateModal();
        setupSectionModal();
        setupCoverPicker();
        renderOptions();
        showQuestionsListView();

        await Promise.all([loadTemplates(), loadCategories()]);

        renderCategories();
        refreshIcons();
    }

    function unmount() {
        state.mounted = false;
        document.body.style.overflow = '';
        closeKebabMenu();
    }

    window.ClivoPages = window.ClivoPages || {};
    window.ClivoPages.fluxo = { mount, unmount };

    function autoMount() {
        if (document.getElementById('fxPage')) {
            setTimeout(function () {
                if (!state.mounted) mount();
            }, 0);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoMount);
    } else {
        autoMount();
    }
})();