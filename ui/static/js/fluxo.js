/* =========================================================================
   FLUXO — Categorias → Modelos → Sessões → Perguntas
   + Importar Google Forms (cria novo modelo)
   + Visualizador de imagem inline
   + Mensagem inicial (intro_message) no modelo
   + Editar metadados do modelo sem criar nova versão
   + Tooltip via portal global
   + Cache buster estável nas imagens dos cards
   + Tipos de pergunta simplificados:
       - Adicionado: single_choice ("Escolha única")
       - Removidos da UI: grid_single, grid_multiple, scale, long_text
         (mantidos em questionTypeIcon/Label para não quebrar dados antigos)
   ========================================================================= */

(function () {
    'use strict';

    const API = {
        categories: '/api/briefing-template-categories/',
        categoryDetail: (id) => `/api/briefing-template-categories/${id}/`,
        categoryReorder: '/api/briefing-template-categories/reorder/',

        templates: '/api/briefing-templates/',
        templateDetail: (id) => `/api/briefing-templates/${id}/`,
        templateSections: (id) => `/api/briefing-templates/${id}/sections/`,
        templateSetPublished: (id) => `/api/briefing-templates/${id}/set-published/`,
        templateCover: (id) => `/api/briefing-templates/${id}/cover/`,
        templateCoverClear: (id) => `/api/briefing-templates/${id}/cover/clear/`,
        templateReorder: '/api/briefing-templates/reorder/',
        templateVersions: (id) => `/api/briefing-templates/${id}/versions/`,
        templateVersionDetail: (tid, vid) =>
            `/api/briefing-templates/${tid}/versions/${vid}/`,

        sectionDetail: (tid, sid) => `/api/briefing-templates/${tid}/sections/${sid}/`,
        sectionQuestions: (tid, sid) =>
            `/api/briefing-templates/${tid}/sections/${sid}/questions/`,
        sectionReorder: (tid) => `/api/briefing-templates/${tid}/sections/reorder/`,

        questionDetail: (tid, qid) =>
            `/api/briefing-templates/${tid}/questions/${qid}/`,
        questionReorder: (tid, sid) =>
            `/api/briefing-templates/${tid}/sections/${sid}/questions/reorder/`,

        documents: '/api/documents/',

        formsSearch: '/api/integrations/google/forms/search/',
        formsPreview: '/api/integrations/google/forms/preview/',
        formsImport: '/api/integrations/google/forms/import/',
        googleOAuthStart: '/integrations/google/start/',
    };

    const state = {
        categories: [],
        templates: [],
        selectedCategoryId: null,
        selectedTemplateId: null,
        selectedSectionId: null,
        selectedVersionId: null,
        viewingVersion: null,
        editingQuestion: null,
        editingTemplateId: null,
        editingCategoryId: null,
        editingSectionId: null,
        options: [],
        gridRows: [],
        gridColumns: [],
        templatesSearch: '',
        sectionsSearch: '',
        questionsSearch: '',
        templatesStatus: 'all',
        coverFile: null,
        coverPreviewUrl: null,
        originalCoverUrl: null,
        mounted: false,
        versions: [],
        versionsTemplateId: null,
        catDropdownOpen: false,
        pendingNewVersionAction: null,

        formsList: [],
        formsFiltered: [],
        formsQuery: '',
        formsLoading: false,
        importingFormId: null,
        formsBinded: false,
        formsPreview: null,

        viewerUrl: '',
    };

    const versionCache = new Map();

    const FORMS_PENDING_URL_KEY = 'clivo.pending_import_url';

    /* =====================================================================
       HELPERS
       ===================================================================== */
    const $ = (sel, ctx = document) => ctx.querySelector(sel);
    const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

    function getCookie(name) {
        const v = document.cookie.match('(^|;) ?' + name + '=([^;]+)');
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
            const err = new Error(
                (data && (data.error || data.detail)) || `Erro ${res.status}`
            );
            err.status = res.status;
            err.code = data && data.code ? data.code : null;
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

    let _iconsScheduled = false;
    function refreshIcons() {
        if (_iconsScheduled) return;
        _iconsScheduled = true;
        requestAnimationFrame(() => {
            _iconsScheduled = false;
            if (window.lucide && typeof window.lucide.createIcons === 'function') {
                window.lucide.createIcons();
            }
        });
    }

    function toast(message, type) {
        if (typeof window.clivoShowToast === 'function') {
            window.clivoShowToast(message, type || 'info');
        } else if (type === 'error') {
            console.error('[fluxo]', message);
        }
    }

    function withCacheBuster(url, version) {
        if (!url) return url;
        if (url.startsWith('http://') || url.startsWith('https://')) {
            if (url.includes('X-Amz-Signature') || url.includes('Signature=')) return url;
        }
        const sep = url.includes('?') ? '&' : '?';
        const v = version != null ? String(version) : String(Date.now());
        return url + sep + 'v=' + encodeURIComponent(v);
    }

    const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    /* =====================================================================
       VIEW SWAP
       ===================================================================== */
    function setColumnView(colEl, viewName) {
        if (!colEl) return;
        colEl.dataset.view = viewName;
        const views = $$('.fx-col-view', colEl);
        for (let i = 0; i < views.length; i++) {
            const v = views[i];
            const isTarget = v.dataset.view === viewName;
            v.classList.toggle('is-hidden', !isTarget);
        }
        const head = $('.fx-col-head', colEl);
        if (head) {
            const isList = viewName === 'list';
            const listScoped = $$('[data-view="list"]', head);
            for (let i = 0; i < listScoped.length; i++) {
                listScoped[i].classList.toggle('is-hidden', !isList);
            }
        }
        const scroll = $('.fx-col-scroll', colEl);
        if (scroll) scroll.scrollTop = 0;
    }

    /* =====================================================================
       DERIVADO
       ===================================================================== */
    function isPublishedTemplate(t) {
        return !!t && t.status === 'published';
    }

    function currentTemplate() {
        if (!state.selectedTemplateId) return null;
        return state.templates.find(
            t => String(t.id) === String(state.selectedTemplateId)
        ) || null;
    }

    function currentSection() {
        if (state.selectedVersionId) {
            const version = state.viewingVersion;
            if (!version) return null;
            const sections = (version.structure && version.structure.sections) || [];
            return sections.find(
                s => String(s.id) === String(state.selectedSectionId)
            ) || null;
        }
        const tpl = currentTemplate();
        if (!tpl || !state.selectedSectionId) return null;
        return (tpl.sections || []).find(
            s => String(s.id) === String(state.selectedSectionId)
        ) || null;
    }

    function isViewingVersion() {
        return !!state.selectedVersionId;
    }

    function isGridType(type) {
        return type === 'grid_single' || type === 'grid_multiple';
    }

    function isChoiceType(type) {
        return (
            type === 'single_choice'
            || type === 'multiple_choice'
            || type === 'dropdown'
            || type === 'choice'
        );
    }

    /* =====================================================================
       MODAIS
       ===================================================================== */
    function openModal(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.add('is-open');
        document.body.classList.add('fx-modal-open');
        document.body.style.overflow = 'hidden';
        refreshIcons();
    }

    function closeModal(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.remove('is-open');
        if (!$('.fx-modal-overlay.is-open')) {
            document.body.classList.remove('fx-modal-open');
            document.body.style.overflow = '';
        }
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

    /* =====================================================================
       TOOLTIP — portal global
       ===================================================================== */
    function bindTooltips() {
        let portal = null;

        function ensurePortal() {
            if (!portal) {
                portal = document.createElement('div');
                portal.className = 'fx-tooltip-portal';
                document.body.appendChild(portal);
            }
            return portal;
        }

        function showTooltip(anchor) {
            const text = anchor.getAttribute('data-tooltip');
            if (!text) return;
            const p = ensurePortal();
            p.textContent = text;
            p.style.left = '0px';
            p.style.top = '0px';
            const pw = p.offsetWidth;
            const ph = p.offsetHeight;
            const rect = anchor.getBoundingClientRect();
            let left = rect.left + rect.width / 2 - pw / 2;
            let top = rect.top - ph - 8;
            if (left < 8) left = 8;
            if (left + pw > window.innerWidth - 8) left = window.innerWidth - pw - 8;
            if (top < 8) top = rect.bottom + 8;
            p.style.left = left + 'px';
            p.style.top = top + 'px';
            p.classList.add('is-visible');
        }

        function hideTooltip() {
            if (portal) portal.classList.remove('is-visible');
        }

        function bindAll() {
            $$('.fx-tooltip').forEach(anchor => {
                if (anchor.dataset.tooltipBound === '1') return;
                anchor.dataset.tooltipBound = '1';
                anchor.addEventListener('mouseenter', () => showTooltip(anchor));
                anchor.addEventListener('focus', () => showTooltip(anchor));
                anchor.addEventListener('mouseleave', hideTooltip);
                anchor.addEventListener('blur', hideTooltip);
            });
        }

        bindAll();
        new MutationObserver(bindAll).observe(document.body, {
            childList: true, subtree: true,
        });

        window.addEventListener('scroll', hideTooltip, true);
        window.addEventListener('resize', hideTooltip);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') hideTooltip();
        });
    }

    /* =====================================================================
       VISUALIZADOR DE IMAGEM
       ===================================================================== */
    function openImageViewer(url) {
        if (!url) return;
        state.viewerUrl = url;
        const img = $('#fxImageViewerImg');
        const link = $('#fxImageViewerOpenNewTab');
        if (img) img.src = url;
        if (link) link.dataset.url = url;
        openModal('fxModalImageViewer');
    }

    function bindImageViewer() {
        const img = $('#fxImageViewerImg');
        const overlay = $('#fxModalImageViewer');
        const closeBtn = $('#fxImageViewerClose');
        const openNewTab = $('#fxImageViewerOpenNewTab');

        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                closeModal('fxModalImageViewer');
                if (img) img.src = '';
            });
        }

        if (openNewTab) {
            openNewTab.addEventListener('click', () => {
                const u = openNewTab.dataset.url || state.viewerUrl;
                if (u) window.open(u, '_blank', 'noopener');
            });
        }

        if (overlay) {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    closeModal('fxModalImageViewer');
                    if (img) img.src = '';
                }
            });
        }
    }

    /* =====================================================================
       BOTÃO COM SPINNER
       ===================================================================== */
    function setButtonLoading(btn, loading) {
        if (!btn) return;
        if (loading) {
            btn.classList.add('is-loading');
            btn.disabled = true;
        } else {
            btn.classList.remove('is-loading');
            btn.disabled = false;
        }
    }

    /* =====================================================================
       CONFIRMAÇÃO GENÉRICA
       ===================================================================== */
    let pendingConfirm = null;

    function confirmAction({
        title,
        subtitle,
        confirmLabel,
        confirmVariant = 'danger',
        icon = 'alert-triangle',
        onConfirm,
    }) {
        const titleEl = $('#fxConfirmTitle');
        const subEl = $('#fxConfirmSub');
        const iconWrap = $('#fxConfirmIcon');
        const btn = $('#fxConfirmBtn');

        if (titleEl) titleEl.textContent = title || 'Confirmar?';
        if (subEl) subEl.textContent = subtitle || 'Esta ação não pode ser desfeita.';

        if (iconWrap) {
            iconWrap.classList.toggle('is-primary', confirmVariant === 'primary');
            iconWrap.innerHTML = `<i data-lucide="${icon}"></i>`;
        }

        const labelText = confirmLabel || (
            confirmVariant === 'danger' ? 'Excluir' : 'Confirmar'
        );

        if (btn) {
            btn.className = 'fx-btn ' +
                (confirmVariant === 'danger' ? 'fx-btn--danger' : 'fx-btn--primary');
            btn.innerHTML =
                `<span class="fx-btn-label">${escapeHtml(labelText)}</span>` +
                `<span class="fx-btn-spinner"></span>`;
            btn.disabled = false;
        }

        pendingConfirm = onConfirm;
        openModal('fxModalConfirm');
        refreshIcons();
    }

    function bindConfirmModal() {
        const btn = $('#fxConfirmBtn');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            if (!pendingConfirm) return;
            const cb = pendingConfirm;
            pendingConfirm = null;
            setButtonLoading(btn, true);
            try {
                await cb();
            } catch (e) {
                console.error(e);
            } finally {
                setButtonLoading(btn, false);
                closeModal('fxModalConfirm');
            }
        });
    }

    /* =====================================================================
       PROMPT "CRIAR NOVA VERSÃO?"
       ===================================================================== */
    function promptNewVersion(onConfirm) {
        state.pendingNewVersionAction = onConfirm;
        openModal('fxModalNewVersionPrompt');
    }

    function bindNewVersionPrompt() {
        const btn = $('#fxNewVersionConfirm');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            const cb = state.pendingNewVersionAction;
            state.pendingNewVersionAction = null;
            closeModal('fxModalNewVersionPrompt');
            if (cb) {
                try { await cb(); } catch (e) { console.error(e); }
            }
        });
    }

    /* =====================================================================
       MENU "⋮"
       ===================================================================== */
    let openMenuEl = null;
    let openMenuAnchor = null;
    let openMenuCleanup = null;

    function closeKebabMenu() {
        if (openMenuCleanup) {
            try { openMenuCleanup(); } catch (_) {}
            openMenuCleanup = null;
        }
        if (openMenuEl) {
            openMenuEl.remove();
            openMenuEl = null;
        }
        if (openMenuAnchor) {
            openMenuAnchor.classList.remove('is-open');
            openMenuAnchor = null;
        }
    }

    function openKebabMenu(anchorBtn, items) {
        closeKebabMenu();

        const rect = anchorBtn.getBoundingClientRect();
        const menu = document.createElement('div');
        menu.className = 'fx-menu';

        const frag = document.createDocumentFragment();
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
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
            frag.appendChild(btn);
        }
        menu.appendChild(frag);
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
        openMenuAnchor = anchorBtn;

        refreshIcons();

        const off = (ev) => {
            if (menu.contains(ev.target) || anchorBtn.contains(ev.target)) return;
            closeKebabMenu();
        };
        const onKey = (ev) => {
            if (ev.key === 'Escape') closeKebabMenu();
        };
        const onScroll = () => closeKebabMenu();

        setTimeout(() => {
            document.addEventListener('click', off, true);
            document.addEventListener('keydown', onKey, true);
            window.addEventListener('scroll', onScroll, true);
            window.addEventListener('resize', onScroll, true);
            openMenuCleanup = () => {
                document.removeEventListener('click', off, true);
                document.removeEventListener('keydown', onKey, true);
                window.removeEventListener('scroll', onScroll, true);
                window.removeEventListener('resize', onScroll, true);
            };
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
            if (openMenuAnchor === btn) {
                closeKebabMenu();
                return;
            }
            openKebabMenu(btn, items);
        });
        return btn;
    }

    /* =====================================================================
       ANIMAÇÃO DE EXCLUSÃO
       ===================================================================== */
    async function animateRemoveAndDelete(el, deleteRequest) {
        if (!el) return;
        el.classList.add('fx-is-removing');
        const deletionPromise = Promise.resolve().then(deleteRequest);
        await delay(200);
        try {
            await deletionPromise;
        } catch (err) {
            el.classList.remove('fx-is-removing');
            throw err;
        }
        el.remove();
    }

    /* =====================================================================
       DRAG-AND-DROP
       ===================================================================== */
    function makeSortable(container, itemSelector, options = {}) {
        if (!container) return () => {};
        const onReorder = options.onReorder || (() => {});

        let draggingEl = null;

        function getItems() {
            return Array.from(container.querySelectorAll(itemSelector));
        }

        function onDragStart(e) {
            const item = e.target.closest(itemSelector);
            if (!item) return;
            if (e.target.closest('.fx-kebab') || e.target.closest('button') ||
                e.target.closest('input') || e.target.closest('label')) {
                e.preventDefault();
                return;
            }
            if (!item.draggable) return;

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
            if (ref === draggingEl || over === draggingEl) return;
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
        populateCategorySelect();
        renderCatDropdown();
    }

    function renderCatDropdown() {
        const list = $('#fxCatDropdownList');
        const label = $('#fxCatBtnLabel');
        if (!list) return;

        if (label) {
            if (state.selectedCategoryId) {
                const cat = state.categories.find(
                    c => String(c.id) === String(state.selectedCategoryId)
                );
                label.textContent = cat ? cat.name : 'Categorias';
            } else {
                label.textContent = 'Categorias';
            }
        }

        list.innerHTML = '';
        const frag = document.createDocumentFragment();

        const allLi = document.createElement('li');
        allLi.className = 'fx-cat-item' + (state.selectedCategoryId === null ? ' is-active' : '');
        allLi.innerHTML = `
            <i data-lucide="layers" style="width:12px;height:12px;"></i>
            <span class="fx-cat-item-name">Todas</span>
            <span class="fx-cat-item-count">${state.templates.length}</span>
        `;
        allLi.addEventListener('click', () => {
            state.selectedCategoryId = null;
            renderTemplates();
            renderCatDropdown();
            closeCatDropdown();
        });
        frag.appendChild(allLi);

        if (!state.categories.length) {
            const empty = document.createElement('li');
            empty.className = 'fx-cat-empty';
            empty.textContent = 'Nenhuma categoria ainda.';
            frag.appendChild(empty);
            list.appendChild(frag);
            refreshIcons();
            return;
        }

        for (let i = 0; i < state.categories.length; i++) {
            const cat = state.categories[i];
            const count = state.templates.filter(t =>
                String(t.category_id || t.category || '') === String(cat.id)
            ).length;

            const li = document.createElement('li');
            li.className = 'fx-cat-item' +
                (String(state.selectedCategoryId) === String(cat.id) ? ' is-active' : '');
            li.innerHTML = `
                <i data-lucide="folder" style="width:12px;height:12px;"></i>
                <span class="fx-cat-item-name">${escapeHtml(cat.name || '—')}</span>
                <span class="fx-cat-item-count">${count}</span>
            `;
            li.addEventListener('click', () => {
                state.selectedCategoryId = cat.id;
                renderTemplates();
                renderCatDropdown();
                closeCatDropdown();
            });
            frag.appendChild(li);
        }

        list.appendChild(frag);
        refreshIcons();
    }

    function positionCatDropdown() {
        const dd = $('#fxCatDropdown');
        const btn = $('#fxTopCategoriesBtn');
        if (!dd || !btn) return;
        const rect = btn.getBoundingClientRect();
        const ddRect = dd.getBoundingClientRect();
        const gap = 6;
        const vw = window.innerWidth;
        const vh = window.innerHeight;

        let left = rect.right - ddRect.width;
        if (left < 8) left = 8;
        if (left + ddRect.width > vw - 8) left = vw - ddRect.width - 8;

        let top = rect.bottom + gap;
        if (top + ddRect.height > vh - 8) {
            top = Math.max(8, rect.top - ddRect.height - gap);
        }

        dd.style.left = left + 'px';
        dd.style.top = top + 'px';
    }

    function openCatDropdown() {
        const dd = $('#fxCatDropdown');
        const btn = $('#fxTopCategoriesBtn');
        if (!dd) return;

        dd.hidden = false;
        state.catDropdownOpen = true;
        if (btn) btn.setAttribute('aria-expanded', 'true');

        positionCatDropdown();
        refreshIcons();

        const onReposition = () => positionCatDropdown();
        window.addEventListener('resize', onReposition);
        window.addEventListener('scroll', onReposition, true);

        setTimeout(() => {
            const off = (ev) => {
                if (dd.contains(ev.target)) return;
                const anchor = $('#fxCatAnchor');
                if (anchor && anchor.contains(ev.target)) return;
                closeCatDropdown();
                document.removeEventListener('click', off, true);
            };
            document.addEventListener('click', off, true);
        }, 0);

        dd._cleanup = () => {
            window.removeEventListener('resize', onReposition);
            window.removeEventListener('scroll', onReposition, true);
        };
    }

    function closeCatDropdown() {
        const dd = $('#fxCatDropdown');
        const btn = $('#fxTopCategoriesBtn');
        if (!dd) return;
        if (dd._cleanup) {
            try { dd._cleanup(); } catch (_) {}
            dd._cleanup = null;
        }
        dd.hidden = true;
        state.catDropdownOpen = false;
        if (btn) btn.setAttribute('aria-expanded', 'false');
    }

    function toggleCatDropdown() {
        if (state.catDropdownOpen) closeCatDropdown();
        else openCatDropdown();
    }

    function populateCategorySelect() {
        const sel = $('#fxTplCategory');
        if (!sel) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">Sem categoria</option>';
        const frag = document.createDocumentFragment();
        for (let i = 0; i < state.categories.length; i++) {
            const cat = state.categories[i];
            const opt = document.createElement('option');
            opt.value = cat.id;
            opt.textContent = cat.name;
            frag.appendChild(opt);
        }
        sel.appendChild(frag);
        if (current) sel.value = current;
    }

    /* =====================================================================
       GERENCIAR CATEGORIAS
       ===================================================================== */
    function openManageCategoriesModal() {
        renderManageCategoriesList();
        const input = $('#fxCatNewInput');
        if (input) input.value = '';
        openModal('fxModalCategoriesManage');
        setTimeout(() => { if (input) input.focus(); }, 60);
    }

    function renderManageCategoriesList() {
        const list = $('#fxCatManageList');
        if (!list) return;
        list.innerHTML = '';

        if (!state.categories.length) {
            const empty = document.createElement('div');
            empty.className = 'fx-cat-manage-empty';
            empty.textContent = 'Nenhuma categoria ainda.';
            list.appendChild(empty);
            return;
        }

        const frag = document.createDocumentFragment();
        for (let i = 0; i < state.categories.length; i++) {
            const cat = state.categories[i];
            const count = state.templates.filter(t =>
                String(t.category_id || t.category || '') === String(cat.id)
            ).length;

            const item = document.createElement('div');
            item.className = 'fx-cat-manage-item';
            item.dataset.id = cat.id;

            const nameWrap = document.createElement('span');
            nameWrap.className = 'fx-cat-manage-item-name';
            nameWrap.textContent = cat.name || '—';
            item.appendChild(nameWrap);

            const countEl = document.createElement('span');
            countEl.className = 'fx-cat-manage-item-count';
            countEl.textContent = count === 1 ? '1 modelo' : `${count} modelos`;
            item.appendChild(countEl);

            const actions = document.createElement('div');
            actions.className = 'fx-cat-manage-item-actions';

            const editBtn = document.createElement('button');
            editBtn.type = 'button';
            editBtn.className = 'fx-cat-manage-item-action';
            editBtn.title = 'Editar';
            editBtn.innerHTML = '<i data-lucide="pencil"></i>';
            editBtn.addEventListener('click', () => {
                startEditCategoryInline(item, cat);
            });
            actions.appendChild(editBtn);

            const delBtn = document.createElement('button');
            delBtn.type = 'button';
            delBtn.className = 'fx-cat-manage-item-action is-danger';
            delBtn.title = 'Excluir';
            delBtn.innerHTML = '<i data-lucide="trash-2"></i>';
            delBtn.addEventListener('click', () => {
                confirmAction({
                    title: `Excluir "${cat.name}"?`,
                    subtitle: 'Os modelos dessa categoria ficarão sem categoria.',
                    confirmLabel: 'Excluir',
                    confirmVariant: 'danger',
                    icon: 'alert-triangle',
                    onConfirm: async () => {
                        try {
                            await animateRemoveAndDelete(item, () =>
                                api(API.categoryDetail(cat.id), { method: 'DELETE' })
                            );
                            toast('Categoria excluída.', 'success');
                            if (String(state.selectedCategoryId) === String(cat.id)) {
                                state.selectedCategoryId = null;
                            }
                            state.categories = state.categories.filter(
                                x => String(x.id) !== String(cat.id)
                            );
                            await loadCategories();
                            await loadTemplates();
                            if (document.getElementById('fxModalCategoriesManage')?.classList.contains('is-open')) {
                                renderManageCategoriesList();
                            }
                        } catch (err) {
                            console.error(err);
                            toast(err.message || 'Erro ao excluir.', 'error');
                            throw err;
                        }
                    },
                });
            });
            actions.appendChild(delBtn);

            item.appendChild(actions);
            frag.appendChild(item);
        }
        list.appendChild(frag);
        refreshIcons();
    }

    function startEditCategoryInline(itemEl, cat) {
        itemEl.innerHTML = '';

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'fx-cat-manage-item-input';
        input.value = cat.name || '';
        input.maxLength = 60;
        itemEl.appendChild(input);

        const actions = document.createElement('div');
        actions.className = 'fx-cat-manage-item-actions';

        const saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.className = 'fx-cat-manage-item-action';
        saveBtn.title = 'Salvar';
        saveBtn.innerHTML = '<i data-lucide="check"></i>';
        saveBtn.addEventListener('click', async () => {
            const newName = input.value.trim();
            if (!newName) {
                toast('Informe o nome.', 'error');
                input.focus();
                return;
            }
            try {
                await api(API.categoryDetail(cat.id), {
                    method: 'PATCH',
                    body: { name: newName },
                });
                toast('Categoria atualizada.', 'success');
                await loadCategories();
                await loadTemplates();
                renderManageCategoriesList();
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao salvar.', 'error');
            }
        });
        actions.appendChild(saveBtn);

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'fx-cat-manage-item-action';
        cancelBtn.title = 'Cancelar';
        cancelBtn.innerHTML = '<i data-lucide="x"></i>';
        cancelBtn.addEventListener('click', () => {
            renderManageCategoriesList();
        });
        actions.appendChild(cancelBtn);

        itemEl.appendChild(actions);
        refreshIcons();
        input.focus();
        input.select();

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveBtn.click();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cancelBtn.click();
            }
        });
    }

    function setupManageCategoriesForm() {
        const form = $('#fxCatNewForm');
        const input = $('#fxCatNewInput');
        const submit = $('#fxCatNewSubmit');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = (input.value || '').trim();
            if (!name) {
                toast('Informe o nome.', 'error');
                input.focus();
                return;
            }

            const original = submit.innerHTML;
            submit.disabled = true;
            try {
                await api(API.categories, { method: 'POST', body: { name } });
                toast('Categoria criada.', 'success');
                input.value = '';
                await loadCategories();
                renderManageCategoriesList();
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao criar.', 'error');
            } finally {
                submit.disabled = false;
                submit.innerHTML = original;
                refreshIcons();
                input.focus();
            }
        });
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
        renderCatDropdown();
    }

    function templatesFiltered() {
        let list = state.templates;

        if (state.selectedCategoryId !== null) {
            list = list.filter(t =>
                String(t.category_id || t.category || '') === String(state.selectedCategoryId)
            );
        }

        if (state.templatesSearch) {
            const q = state.templatesSearch.toLowerCase();
            list = list.filter(t => {
                const name = (t.name || '').toLowerCase();
                const desc = (t.description || '').toLowerCase();
                return name.includes(q) || desc.includes(q);
            });
        }

        if (state.templatesStatus && state.templatesStatus !== 'all') {
            list = list.filter(t => t.status === state.templatesStatus);
        }

        return list;
    }

    function renderTemplates() {
        const grid = $('#fxTemplatesList');
        const count = $('#fxTemplatesCount');
        if (!grid) return;

        const items = templatesFiltered();
        if (count) count.textContent = String(items.length);

        grid.innerHTML = '';
        if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'fx-list-empty';
            if (state.templatesSearch) {
                empty.textContent = `Nada encontrado para "${state.templatesSearch}".`;
            } else if (state.templates.length) {
                empty.textContent = 'Nada nesta categoria.';
            } else {
                empty.textContent = 'Nenhum modelo criado ainda.';
            }
            grid.appendChild(empty);
            refreshIcons();
            return;
        }

        const frag = document.createDocumentFragment();
        for (let i = 0; i < items.length; i++) {
            frag.appendChild(buildTemplateCard(items[i]));
        }
        grid.appendChild(frag);
        refreshIcons();
    }

    function buildTemplateCard(t) {
        const isPublished = isPublishedTemplate(t);
        const card = document.createElement('div');
        card.className = 'fx-tpl-card' +
            (String(state.selectedTemplateId) === String(t.id) ? ' is-active' : '');
        card.dataset.id = t.id;

        const coverUrl = t.cover_url || '';
        const sectionsCount = t.sections_count || 0;
        const questionsCount = t.questions_count || 0;
        const hasIntro = !!(t.intro_message && String(t.intro_message).trim());

        const thumb = document.createElement('div');
        thumb.className = 'fx-tpl-thumb';
        if (coverUrl) {
            const imgUrl = withCacheBuster(coverUrl, t.updated_at || '');
            thumb.innerHTML = `<img src="${escapeHtml(imgUrl)}" alt="" loading="lazy" decoding="async" onerror="this.style.display='none';this.parentNode.innerHTML='<i data-lucide=\\'image\\'></i>';if(window.lucide)window.lucide.createIcons();">`;
        } else {
            thumb.innerHTML = `<i data-lucide="image"></i>`;
        }
        const dot = document.createElement('span');
        dot.className = 'fx-tpl-thumb-dot' + (isPublished ? '' : ' is-off');
        thumb.appendChild(dot);

        const info = document.createElement('div');
        info.className = 'fx-tpl-info';

        const nameRow = document.createElement('div');
        nameRow.className = 'fx-tpl-name-row';

        const nameEl = document.createElement('div');
        nameEl.className = 'fx-tpl-name';
        nameEl.textContent = t.name || '—';
        nameRow.appendChild(nameEl);

        const sep = document.createElement('span');
        sep.className = 'fx-tpl-name-sep';
        sep.textContent = '·';
        nameRow.appendChild(sep);

        const badge = document.createElement('span');
        badge.className = 'fx-tpl-status-badge ' +
            (isPublished ? 'is-published' : 'is-draft');
        badge.textContent = isPublished ? 'Publicado' : 'Rascunho';
        nameRow.appendChild(badge);

        info.appendChild(nameRow);

        const meta = document.createElement('div');
        meta.className = 'fx-tpl-meta';
        meta.innerHTML = `
            <span class="fx-tpl-meta-item"><i data-lucide="layers"></i>${sectionsCount} sessões</span>
            <span class="fx-tpl-meta-sep"></span>
            <span class="fx-tpl-meta-item"><i data-lucide="help-circle"></i>${questionsCount} perguntas</span>
            ${hasIntro ? '<span class="fx-tpl-meta-sep"></span><span class="fx-tpl-meta-item"><i data-lucide="message-square-quote"></i>intro</span>' : ''}
        `;
        info.appendChild(meta);

        const actions = document.createElement('div');
        actions.className = 'fx-tpl-actions';

        const toggleWrap = document.createElement('label');
        toggleWrap.className = 'fx-mini-switch';
        toggleWrap.title = isPublished
            ? 'Publicado — clique para voltar a rascunho'
            : 'Rascunho — clique para publicar';
        toggleWrap.innerHTML = `
            <input type="checkbox" ${isPublished ? 'checked' : ''}>
            <span class="fx-mini-switch-track"><span class="fx-mini-switch-thumb"></span></span>
        `;
        const toggleInput = toggleWrap.querySelector('input');

        toggleInput.addEventListener('click', (e) => e.stopPropagation());
        toggleInput.addEventListener('change', async (e) => {
            e.stopPropagation();
            const newPublished = toggleInput.checked;
            const previousPublished = !newPublished;

            applyPublishedStateOptimistic(t, newPublished, { card, toggleWrap });

            try {
                await api(API.templateSetPublished(t.id), {
                    method: 'POST',
                    body: { published: newPublished },
                });
                toast(
                    newPublished ? 'Modelo publicado.' : 'Modelo voltou para rascunho.',
                    'success'
                );
                if (String(state.selectedTemplateId) === String(t.id)) {
                    loadTemplateDetail(t.id).catch(() => {});
                }
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao alterar estado.', 'error');
                applyPublishedStateOptimistic(t, previousPublished, { card, toggleWrap });
            }
        });

        const kebabItems = [
            {
                label: 'Editar', icon: 'pencil',
                onClick: () => openEditTemplateForm(t),
            },
            {
                label: 'Versões', icon: 'git-branch',
                onClick: () => openVersionsPanel(t.id),
            },
            {
                label: 'Excluir', icon: 'trash-2', danger: true,
                onClick: () => confirmAction({
                    title: `Excluir "${t.name}"?`,
                    subtitle: 'Sessões e perguntas vinculadas serão removidas.',
                    confirmLabel: 'Excluir',
                    confirmVariant: 'danger',
                    icon: 'alert-triangle',
                    onConfirm: async () => {
                        await animateRemoveAndDelete(card, () =>
                            api(API.templateDetail(t.id), { method: 'DELETE' })
                        );
                        toast('Modelo excluído.', 'success');
                        if (String(state.selectedTemplateId) === String(t.id)) {
                            state.selectedTemplateId = null;
                            state.selectedSectionId = null;
                            state.selectedVersionId = null;
                            state.viewingVersion = null;
                            renderSections(null);
                            renderQuestions(null);
                            renderPreview();
                        }
                        state.templates = state.templates.filter(
                            x => String(x.id) !== String(t.id)
                        );
                        renderCatDropdown();
                    },
                }),
            },
        ];
        const kebab = buildKebab(kebabItems);

        actions.appendChild(toggleWrap);
        actions.appendChild(kebab);

        card.appendChild(thumb);
        card.appendChild(info);
        card.appendChild(actions);

        card.draggable = true;
        card.addEventListener('dragstart', (e) => {
            if (e.target.closest('.fx-mini-switch') || e.target.closest('.fx-kebab')) {
                e.preventDefault();
                return;
            }
            card.classList.add('is-dragging');
            e.dataTransfer.effectAllowed = 'move';
            try { e.dataTransfer.setData('text/plain', ''); } catch (_) {}
        });
        card.addEventListener('dragend', () => {
            card.classList.remove('is-dragging');
            const orderedIds = Array.from(
                $('#fxTemplatesList').querySelectorAll('.fx-tpl-card[data-id]')
            ).map(el => el.dataset.id);
            reorderTemplatesOptimistic(orderedIds);
        });

        card.addEventListener('click', (e) => {
            if (e.target.closest('.fx-tpl-actions')) return;
            selectTemplate(t.id);
        });

        return card;
    }

    function applyPublishedStateOptimistic(t, newPublished, { card, toggleWrap }) {
        const idx = state.templates.findIndex(x => String(x.id) === String(t.id));
        if (idx !== -1) {
            state.templates[idx].status = newPublished ? 'published' : 'draft';
        }

        const input = toggleWrap.querySelector('input');
        if (input) input.checked = newPublished;

        const badge = card.querySelector('.fx-tpl-status-badge');
        if (badge) {
            badge.classList.toggle('is-published', newPublished);
            badge.classList.toggle('is-draft', !newPublished);
            badge.textContent = newPublished ? 'Publicado' : 'Rascunho';
        }

        const dot = card.querySelector('.fx-tpl-thumb-dot');
        if (dot) {
            dot.classList.toggle('is-off', !newPublished);
        }

        toggleWrap.title = newPublished
            ? 'Publicado — clique para voltar a rascunho'
            : 'Rascunho — clique para publicar';
    }

    function reorderTemplatesOptimistic(orderedIds) {
        const byId = Object.fromEntries(state.templates.map(t => [String(t.id), t]));
        const newList = [];
        const seen = new Set();

        for (const id of orderedIds) {
            const item = byId[String(id)];
            if (item && !seen.has(String(id))) {
                newList.push(item);
                seen.add(String(id));
            }
        }
        for (const t of state.templates) {
            if (!seen.has(String(t.id))) {
                newList.push(t);
            }
        }
        state.templates = newList;

        api(API.templateReorder, {
            method: 'POST',
            body: { ordered_ids: orderedIds },
        }).catch((err) => {
            console.error('Erro ao reordenar templates:', err);
            toast('Falha ao salvar a nova ordem.', 'error');
            loadTemplates();
        });
    }

    /* =====================================================================
       FORM DE MODELO
       ===================================================================== */
    function openNewTemplateForm() {
        state.editingTemplateId = null;
        state.coverFile = null;
        state.coverPreviewUrl = null;
        state.originalCoverUrl = null;
        $('#fxFormTemplate').reset();
        populateCategorySelect();
        if (state.selectedCategoryId) $('#fxTplCategory').value = state.selectedCategoryId;
        const introEl = $('#fxTplIntroMessage');
        if (introEl) introEl.value = '';
        updateCoverPreview(null);
        $('#fxTplModalTitle').textContent = 'Novo modelo';
        $('#fxTplModalSub').textContent = 'Modelo reutilizável de briefing';
        $('#fxTplSubmit').querySelector('.fx-btn-label').textContent = 'Criar modelo';
        const banner = $('#fxTplEditBanner');
        if (banner) banner.classList.add('is-hidden');
        setColumnView($('#fxTemplates'), 'form');
        refreshIcons();
        setTimeout(() => { const el = $('#fxTplName'); if (el) el.focus(); }, 60);
    }

    function openEditTemplateForm(t) {
        state.editingTemplateId = t.id;
        state.coverFile = null;
        state.coverPreviewUrl = t.cover_url || null;
        state.originalCoverUrl = t.cover_url || null;
        populateCategorySelect();
        $('#fxTplName').value = t.name || '';
        $('#fxTplCategory').value = t.category_id || t.category || '';
        $('#fxTplDescription').value = t.description || '';
        const introEl = $('#fxTplIntroMessage');
        if (introEl) introEl.value = t.intro_message || '';
        updateCoverPreview(state.coverPreviewUrl);

        $('#fxTplModalTitle').textContent = 'Editar modelo';
        $('#fxTplModalSub').textContent = isPublishedTemplate(t)
            ? 'As alterações valem imediatamente. Sessões e perguntas exigem nova versão.'
            : 'Modelo reutilizável de briefing';
        $('#fxTplSubmit').querySelector('.fx-btn-label').textContent = 'Salvar';

        const banner = $('#fxTplEditBanner');
        if (banner) {
            banner.classList.toggle('is-hidden', !isPublishedTemplate(t));
        }

        setColumnView($('#fxTemplates'), 'form');
        refreshIcons();
    }

    function closeTemplateForm() {
        state.editingTemplateId = null;
        state.coverFile = null;
        state.originalCoverUrl = null;
        if (state.coverPreviewUrl && state.coverPreviewUrl.startsWith('blob:')) {
            URL.revokeObjectURL(state.coverPreviewUrl);
        }
        state.coverPreviewUrl = null;
        setColumnView($('#fxTemplates'), 'list');
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

    function setupTemplateForm() {
        const form = $('#fxFormTemplate');
        const submit = $('#fxTplSubmit');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = $('#fxTplName').value.trim();
            const categoryId = $('#fxTplCategory').value;
            const description = $('#fxTplDescription').value.trim();
            const introEl = $('#fxTplIntroMessage');
            const introMessage = introEl ? introEl.value.trim() : '';

            if (!name) { toast('Informe o nome.', 'error'); return; }

            const payload = {
                name,
                description: description || '',
                intro_message: introMessage || '',
                category_id: categoryId || null,
            };

            const originalLabel = submit.querySelector('.fx-btn-label').textContent;
            submit.querySelector('.fx-btn-label').textContent = 'Salvando…';
            submit.disabled = true;
            setButtonLoading(submit, true);

            try {
                let updatedTemplate = null;
                let templateId = state.editingTemplateId;

                if (state.editingTemplateId) {
                    updatedTemplate = await api(API.templateDetail(state.editingTemplateId), {
                        method: 'PATCH', body: payload,
                    });
                    toast('Modelo atualizado.', 'success');
                } else {
                    updatedTemplate = await api(API.templates, { method: 'POST', body: payload });
                    toast('Modelo criado.', 'success');
                    templateId = updatedTemplate && updatedTemplate.id;
                }

                if (templateId) {
                    if (state.coverFile) {
                        submit.querySelector('.fx-btn-label').textContent = 'Enviando capa…';
                        try {
                            const withCover = await uploadTemplateCover(templateId, state.coverFile);
                            if (withCover) updatedTemplate = withCover;
                        } catch (err) {
                            console.error(err);
                            toast(err.message || 'Falha ao enviar capa.', 'error');
                        }
                    } else if (
                        state.editingTemplateId
                        && !state.coverPreviewUrl
                        && state.originalCoverUrl
                    ) {
                        submit.querySelector('.fx-btn-label').textContent = 'Removendo capa…';
                        try {
                            const withoutCover = await clearTemplateCover(templateId);
                            if (withoutCover) updatedTemplate = withoutCover;
                        } catch (err) {
                            console.error(err);
                            toast(err.message || 'Falha ao remover capa.', 'error');
                        }
                    }
                }

                state.editingTemplateId = null;
                state.coverFile = null;
                state.originalCoverUrl = null;
                if (state.coverPreviewUrl && state.coverPreviewUrl.startsWith('blob:')) {
                    URL.revokeObjectURL(state.coverPreviewUrl);
                }
                state.coverPreviewUrl = null;

                if (updatedTemplate && updatedTemplate.id) {
                    const idx = state.templates.findIndex(
                        t => String(t.id) === String(updatedTemplate.id)
                    );
                    if (idx !== -1) {
                        state.templates[idx] = { ...state.templates[idx], ...updatedTemplate };
                    } else {
                        state.templates.unshift(updatedTemplate);
                    }
                    renderTemplates();
                } else {
                    await loadTemplates();
                }

                setColumnView($('#fxTemplates'), 'list');

                if (updatedTemplate && updatedTemplate.id) {
                    await selectTemplate(updatedTemplate.id);
                }
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao salvar.', 'error');
            } finally {
                submit.querySelector('.fx-btn-label').textContent = originalLabel;
                submit.disabled = false;
                setButtonLoading(submit, false);
            }
        });
    }

    /* =====================================================================
       PAINEL DE VERSÕES
       ===================================================================== */
    async function openVersionsPanel(templateId) {
        state.versionsTemplateId = templateId;
        state.selectedVersionId = null;
        state.viewingVersion = null;
        state.selectedSectionId = null;

        const t = state.templates.find(x => String(x.id) === String(templateId));
        $('#fxVersionsTitle').textContent = t ? `Versões · ${t.name}` : 'Versões';
        $('#fxVersionsSub').textContent = 'Histórico de versões do modelo.';
        setColumnView($('#fxTemplates'), 'versions');
        await loadVersions(templateId);
        refreshIcons();
    }

    function closeVersionsPanel() {
        const closingTemplateId = state.versionsTemplateId;

        state.versionsTemplateId = null;
        state.versions = [];
        state.selectedVersionId = null;
        state.viewingVersion = null;

        if (closingTemplateId) {
            _clearVersionCacheForTemplate(closingTemplateId);
        }

        setColumnView($('#fxTemplates'), 'list');
        renderSections(currentTemplate());
        renderQuestions(null);
        renderPreview();
    }

    async function loadVersions(templateId) {
        const list = $('#fxVersionsList');
        if (!list) return;
        list.innerHTML = '<div class="fx-list-empty">Carregando…</div>';
        try {
            const data = await api(API.templateVersions(templateId));
            state.versions = pickArray(data, 'results');
        } catch (err) {
            if (err.status === 404) {
                state.versions = [];
            } else {
                console.error(err);
                state.versions = [];
                toast('Erro ao carregar versões.', 'error');
            }
        }
        renderVersions();
    }

    function renderVersions() {
        const list = $('#fxVersionsList');
        if (!list) return;
        list.innerHTML = '';
        if (!state.versions.length) {
            const empty = document.createElement('div');
            empty.className = 'fx-list-empty';
            empty.textContent = 'Nenhuma versão registrada ainda.';
            list.appendChild(empty);
            return;
        }

        const frag = document.createDocumentFragment();
        for (let i = 0; i < state.versions.length; i++) {
            frag.appendChild(buildVersionCard(state.versions[i]));
        }
        list.appendChild(frag);
        refreshIcons();
    }

    function buildVersionCard(v) {
        const item = document.createElement('div');
        item.className = 'fx-version-item' +
            (String(state.selectedVersionId) === String(v.id) ? ' is-active' : '');
        item.dataset.id = v.id;

        const main = document.createElement('div');
        main.className = 'fx-version-main';

        const title = document.createElement('div');
        title.className = 'fx-version-title';
        title.innerHTML = `<span>v${v.version_number}</span>`;
        const badge = document.createElement('span');
        badge.className = 'fx-version-badge is-' + (v.status || 'draft');
        badge.textContent = v.status_display || v.status || '—';
        title.appendChild(badge);
        main.appendChild(title);

        const meta = document.createElement('div');
        meta.className = 'fx-version-meta';
        const dateToShow = v.published_at || v.created_at;
        const formattedDate = dateToShow
            ? new Date(dateToShow).toLocaleString('pt-BR', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            })
            : '';
        const sectionsCount = v.sections_count || 0;
        const questionsCount = v.questions_count || 0;
        meta.innerHTML = `
            <span>${escapeHtml(formattedDate)}</span>
            <span>·</span>
            <span>${sectionsCount} sessões</span>
            <span>·</span>
            <span>${questionsCount} perguntas</span>
        `;
        main.appendChild(meta);

        item.appendChild(main);

        const actions = document.createElement('div');
        actions.className = 'fx-version-actions';

        const kebabItems = [
            {
                label: 'Restaurar como nova versão',
                icon: 'rotate-ccw',
                onClick: () => restoreVersion(v),
            },
            {
                label: 'Excluir versão',
                icon: 'trash-2',
                danger: true,
                onClick: () => {
                    if (v.status === 'published') {
                        toast(
                            'Despublique o modelo antes de excluir esta versão.',
                            'info'
                        );
                        return;
                    }
                    deleteVersion(v);
                },
            },
        ];
        const kebab = buildKebab(kebabItems);
        actions.appendChild(kebab);

        item.appendChild(actions);

        item.addEventListener('click', () => {
            selectVersionForReading(v);
        });

        return item;
    }

    async function restoreVersion(v) {
        const tpl = state.templates.find(
            x => String(x.id) === String(v.template)
        );
        const isPublished = tpl && tpl.status === 'published';

        const subtitle = isPublished
            ? 'O modelo será despublicado (voltará a rascunho) e a estrutura atual será substituída por esta versão. Você poderá revisar e publicar novamente depois.'
            : 'A estrutura atual do modelo será substituída por esta versão. Você poderá revisar e publicar depois.';

        confirmAction({
            title: `Restaurar v${v.version_number}?`,
            subtitle,
            confirmLabel: 'Restaurar',
            confirmVariant: 'primary',
            icon: 'rotate-ccw',
            onConfirm: async () => {
                try {
                    await api(API.templateVersions(v.template), {
                        method: 'POST',
                        body: {
                            mode: 'restore_from_version',
                            source_version_id: v.id,
                        },
                    });
                    toast(
                        isPublished
                            ? 'Versão restaurada. O modelo voltou a rascunho — revise e publique.'
                            : 'Versão restaurada. Revise e publique.',
                        'success'
                    );

                    await loadVersions(v.template);

                    if (String(state.selectedTemplateId) === String(v.template)) {
                        await loadTemplateDetail(v.template);
                    }
                    await loadTemplates();
                } catch (err) {
                    console.error(err);
                    toast(err.message || 'Erro ao restaurar versão.', 'error');
                    throw err;
                }
            },
        });
    }

    function deleteVersion(v) {
        confirmAction({
            title: `Excluir v${v.version_number}?`,
            subtitle: 'Esta versão será removida permanentemente.',
            confirmLabel: 'Excluir',
            confirmVariant: 'danger',
            icon: 'alert-triangle',
            onConfirm: async () => {
                try {
                    const el = $(`.fx-version-item[data-id="${CSS.escape(String(v.id))}"]`);
                    const req = () => api(API.templateVersionDetail(v.template, v.id), {
                        method: 'DELETE',
                    });
                    if (el) {
                        await animateRemoveAndDelete(el, req);
                    } else {
                        await req();
                    }
                    toast('Versão excluída.', 'success');
                    _invalidateVersionInCache(v.id);

                    if (String(state.selectedVersionId) === String(v.id)) {
                        state.selectedVersionId = null;
                        state.viewingVersion = null;
                        renderSections(currentTemplate());
                        renderQuestions(null);
                        renderPreview();
                    }
                    state.versions = state.versions.filter(
                        x => String(x.id) !== String(v.id)
                    );
                } catch (err) {
                    console.error(err);
                    toast(err.message || 'Erro ao excluir versão.', 'error');
                    throw err;
                }
            },
        });
    }

    /* =====================================================================
       LEITURA DE VERSÃO
       ===================================================================== */
    function _clearVersionCacheForTemplate(templateId) {
        for (const [vid, v] of versionCache.entries()) {
            if (String(v.template) === String(templateId)) {
                versionCache.delete(vid);
            }
        }
    }

    function _invalidateVersionInCache(versionId) {
        versionCache.delete(String(versionId));
    }

    async function selectVersionForReading(v) {
        if (String(state.selectedVersionId) === String(v.id) && state.viewingVersion) {
            return;
        }

        state.selectedVersionId = v.id;
        state.selectedSectionId = null;

        const list = $('#fxVersionsList');
        if (list) {
            $$('.fx-version-item', list).forEach(el => {
                el.classList.toggle('is-active', String(el.dataset.id) === String(v.id));
            });
        }

        const cached = versionCache.get(String(v.id));
        if (cached) {
            state.viewingVersion = cached;
            renderVersionStructure(cached);
            renderPreview();

            if (cached.status !== 'published') {
                _revalidateInBackground(v);
            }
            return;
        }

        state.viewingVersion = null;
        renderVersionLoading();
        try {
            const full = await _fetchVersionDetail(v.template, v.id);
            versionCache.set(String(v.id), full);
            state.viewingVersion = full;
            renderVersionStructure(full);
            renderPreview();
        } catch (err) {
            console.error('Erro ao carregar versão:', err);
            renderVersionError(v, err);
        }
    }

    async function _revalidateInBackground(v) {
        try {
            const fresh = await _fetchVersionDetail(v.template, v.id);
            versionCache.set(String(v.id), fresh);
            if (String(state.selectedVersionId) === String(v.id)) {
                state.viewingVersion = fresh;
                renderVersionStructure(fresh);
                renderPreview();
            }
        } catch (_) { /* silencioso */ }
    }

    async function _fetchVersionDetail(templateId, versionId) {
        return await api(API.templateVersionDetail(templateId, versionId));
    }

    function renderVersionLoading() {
        const list = $('#fxSectionsList');
        const count = $('#fxSectionsCount');
        const sub = $('#fxSectionsSub');
        const newBtn = $('#fxNewSectionBtn');
        if (list) {
            list.innerHTML = `
                <li class="fx-list-empty">
                    <i data-lucide="loader-2" class="fx-spin"></i>
                    Carregando versão…
                </li>
            `;
        }
        if (count) count.textContent = '0';
        if (sub) sub.textContent = 'Carregando…';
        if (newBtn) newBtn.disabled = true;

        const qList = $('#fxQuestionsList');
        if (qList) qList.innerHTML = '<li class="fx-list-empty">Aguardando sessão…</li>';
        const qCount = $('#fxQuestionsCount');
        if (qCount) qCount.textContent = '0';

        refreshIcons();
    }

    function renderVersionError(v, err) {
        const list = $('#fxSectionsList');
        const sub = $('#fxSectionsSub');
        const count = $('#fxSectionsCount');

        if (count) count.textContent = '0';
        if (sub) sub.textContent = 'Falha ao carregar versão';

        if (list) {
            list.innerHTML = '';
            const li = document.createElement('li');
            li.className = 'fx-list-empty';
            li.innerHTML = `
                <div style="display:flex;flex-direction:column;gap:8px;align-items:center;">
                    <i data-lucide="alert-circle"></i>
                    <span>Não foi possível carregar esta versão.</span>
                    <span style="font-size:11px;opacity:.7;">${escapeHtml(err && err.message ? err.message : 'Erro desconhecido')}</span>
                    <button type="button" class="fx-btn fx-btn--sm" id="fxVersionRetryBtn">
                        <i data-lucide="refresh-cw"></i>
                        <span>Tentar novamente</span>
                    </button>
                </div>
            `;
            list.appendChild(li);

            const retry = li.querySelector('#fxVersionRetryBtn');
            if (retry) {
                retry.addEventListener('click', () => {
                    _invalidateVersionInCache(v.id);
                    state.selectedVersionId = null;
                    selectVersionForReading(v);
                });
            }
        }

        const qList = $('#fxQuestionsList');
        if (qList) qList.innerHTML = '<li class="fx-list-empty">Sem sessão.</li>';

        refreshIcons();
    }

    function renderVersionStructure(version) {
        const sections = (version.structure && version.structure.sections) || [];
        const fakeTemplate = {
            id: version.template,
            name: `v${version.version_number}`,
            sections: sections.map(sec => ({
                id: sec.id,
                title: sec.title || '',
                description: sec.description || '',
                position: sec.position || 0,
                questions: (sec.questions || []).map(q => ({
                    id: q.id,
                    text: q.text || '',
                    instructions: q.instructions || '',
                    question_type: q.question_type || 'text',
                    allowed_response_formats: q.allowed_response_formats || [],
                    options: q.options || [],
                    is_required: q.is_required !== false,
                    position: q.position || 0,
                    is_custom: !!q.is_custom,
                })),
            })),
        };
        renderSections(fakeTemplate, { readOnly: true, version });
        renderQuestions(null);
    }

    /* =====================================================================
       SELEÇÃO DE MODELO
       ===================================================================== */
    async function selectTemplate(templateId) {
        const previousId = state.selectedTemplateId;

        if (state.selectedVersionId) {
            state.selectedVersionId = null;
            state.viewingVersion = null;
        }

        state.selectedTemplateId = templateId;
        state.selectedSectionId = null;

        if (previousId && String(previousId) !== String(templateId)) {
            const prevCard = $(`.fx-tpl-card[data-id="${CSS.escape(String(previousId))}"]`);
            if (prevCard) prevCard.classList.remove('is-active');
        }
        const newCard = $(`.fx-tpl-card[data-id="${CSS.escape(String(templateId))}"]`);
        if (newCard) newCard.classList.add('is-active');

        await loadTemplateDetail(templateId);
    }

    async function loadTemplateDetail(templateId) {
        try {
            const data = await api(API.templateDetail(templateId));
            const idx = state.templates.findIndex(t => String(t.id) === String(templateId));
            if (idx !== -1) state.templates[idx] = { ...state.templates[idx], ...data };
            renderSections(data);
            showQuestionsListView();
            renderPreview();
            renderCatDropdown();
        } catch (err) {
            console.error('Erro ao carregar modelo:', err);
            toast('Erro ao carregar modelo.', 'error');
        }
    }

    /* =====================================================================
       requireEditableVersion — SÓ para sessões e perguntas
       ===================================================================== */
    function requireEditableVersion(onReady) {
        const tpl = currentTemplate();
        if (!tpl) {
            toast('Selecione um modelo.', 'info');
            return;
        }

        if (!isPublishedTemplate(tpl)) {
            onReady();
            return;
        }

        promptNewVersion(async () => {
            try {
                await api(API.templateSetPublished(tpl.id), {
                    method: 'POST',
                    body: { published: false },
                });
                await loadTemplateDetail(tpl.id);
                await loadTemplates();
                toast('Nova versão em rascunho criada. Você já pode editar.', 'success');
                onReady();
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao criar nova versão.', 'error');
            }
        });
    }

    /* =====================================================================
       SESSÕES
       ===================================================================== */
    function sectionsFiltered(template) {
        if (!template) return [];
        let list = (template.sections || []).slice();
        if (state.sectionsSearch) {
            const q = state.sectionsSearch.toLowerCase();
            list = list.filter(s =>
                (s.title || '').toLowerCase().includes(q) ||
                (s.description || '').toLowerCase().includes(q)
            );
        }
        return list;
    }

    function renderSections(template, opts = {}) {
        const list = $('#fxSectionsList');
        const count = $('#fxSectionsCount');
        const sub = $('#fxSectionsSub');
        const newBtn = $('#fxNewSectionBtn');
        if (!list) return;

        const readOnly = !!opts.readOnly;
        const canEdit = !!template && !readOnly;

        const allSections = (template && template.sections) || [];
        const sections = sectionsFiltered(template);

        if (count) count.textContent = String(allSections.length);
        if (sub) {
            if (readOnly && opts.version) {
                sub.textContent = `v${opts.version.version_number} · ${opts.version.status_display || opts.version.status} (somente leitura)`;
            } else {
                sub.textContent = template ? (template.name || '—') : 'Selecione um modelo';
            }
        }
        if (newBtn) {
            newBtn.disabled = !canEdit;
            newBtn.title = readOnly
                ? 'Modo leitura de versão'
                : 'Nova sessão';
        }

        list.innerHTML = '';

        if (!template) {
            list.innerHTML = '<li class="fx-list-empty">Nenhum modelo selecionado.</li>';
            return;
        }

        if (readOnly && opts.version) {
            const banner = document.createElement('li');
            banner.className = 'fx-version-banner';
            banner.innerHTML =
                '<i data-lucide="eye"></i>' +
                `<span>Visualizando <strong>v${opts.version.version_number}</strong> ` +
                `(${escapeHtml(opts.version.status_display || opts.version.status || '')}) em modo leitura.</span>`;
            list.appendChild(banner);
        }

        if (!allSections.length) {
            const empty = document.createElement('li');
            empty.className = 'fx-list-empty';
            empty.textContent = 'Nenhuma sessão ainda.';
            list.appendChild(empty);
            refreshIcons();
            return;
        }

        if (!sections.length) {
            const empty = document.createElement('li');
            empty.className = 'fx-list-empty';
            empty.textContent = `Nada encontrado para "${state.sectionsSearch}".`;
            list.appendChild(empty);
            refreshIcons();
            return;
        }

        const frag = document.createDocumentFragment();
        for (let i = 0; i < sections.length; i++) {
            const s = sections[i];
            const originalIdx = allSections.findIndex(x => String(x.id) === String(s.id));
            const idx = originalIdx >= 0 ? originalIdx : 0;
            const qCount = (s.questions && s.questions.length) || 0;

            const li = document.createElement('li');
            li.className = 'fx-list-item fx-list-item--card fx-list-item--section' +
                (String(state.selectedSectionId) === String(s.id) ? ' is-active' : '');
            li.dataset.id = s.id;
            li.draggable = canEdit;

            const num = document.createElement('span');
            num.className = 'fx-num fx-num--circle';
            num.textContent = String(idx + 1);

            const body = document.createElement('div');
            body.className = 'fx-card-body';

            const titleEl = document.createElement('span');
            titleEl.className = 'fx-card-title';
            titleEl.textContent = s.title || '—';
            body.appendChild(titleEl);

            const foot = document.createElement('span');
            foot.className = 'fx-card-foot';
            foot.innerHTML = `<i data-lucide="help-circle"></i>${qCount}`;
            body.appendChild(foot);

            li.appendChild(num);
            li.appendChild(body);

            if (canEdit) {
                const kebab = buildKebab([
                    {
                        label: 'Editar', icon: 'pencil',
                        onClick: () => openEditSectionForm(s),
                    },
                    {
                        label: 'Excluir', icon: 'trash-2', danger: true,
                        onClick: () => confirmAction({
                            title: `Excluir "${s.title}"?`,
                            subtitle: 'As perguntas dessa sessão serão removidas.',
                            confirmLabel: 'Excluir',
                            confirmVariant: 'danger',
                            icon: 'alert-triangle',
                            onConfirm: async () => {
                                try {
                                    await animateRemoveAndDelete(li, () =>
                                        api(API.sectionDetail(state.selectedTemplateId, s.id), {
                                            method: 'DELETE',
                                        })
                                    );
                                    toast('Sessão excluída.', 'success');
                                    if (String(state.selectedSectionId) === String(s.id)) {
                                        state.selectedSectionId = null;
                                        renderQuestions(null);
                                    }
                                    const tpl = currentTemplate();
                                    if (tpl && tpl.sections) {
                                        tpl.sections = tpl.sections.filter(
                                            x => String(x.id) !== String(s.id)
                                        );
                                    }
                                } catch (err) {
                                    console.error(err);
                                    toast(err.message || 'Erro ao excluir sessão.', 'error');
                                    throw err;
                                }
                            },
                        }),
                    },
                ]);
                li.appendChild(kebab);
            }

            li.addEventListener('click', (e) => {
                if (e.target.closest('.fx-kebab') || e.target.closest('button')) return;
                selectSection(template.id, s.id);
            });
            frag.appendChild(li);
        }
        list.appendChild(frag);

        makeSortable(list, '.fx-list-item--section', {
            onReorder: (orderedIds) => {
                const tpl = currentTemplate();
                if (tpl && tpl.sections) {
                    const byId = Object.fromEntries(tpl.sections.map(s => [String(s.id), s]));
                    const newList = [];
                    const seen = new Set();
                    for (const id of orderedIds) {
                        const item = byId[String(id)];
                        if (item && !seen.has(String(id))) {
                            newList.push(item);
                            seen.add(String(id));
                        }
                    }
                    for (const s of tpl.sections) {
                        if (!seen.has(String(s.id))) newList.push(s);
                    }
                    tpl.sections = newList;
                }
                api(API.sectionReorder(state.selectedTemplateId), {
                    method: 'POST',
                    body: { ordered_ids: orderedIds },
                }).catch((err) => {
                    console.error('Erro ao reordenar sessões:', err);
                    toast('Falha ao salvar a nova ordem.', 'error');
                    loadTemplateDetail(state.selectedTemplateId);
                });
            },
        });

        refreshIcons();
    }

    function selectSection(templateId, sectionId) {
        state.selectedSectionId = sectionId;

        if (state.selectedVersionId && state.viewingVersion) {
            const sec = (state.viewingVersion.structure?.sections || []).find(
                s => String(s.id) === String(sectionId)
            );
            if (sec) {
                const list = $('#fxSectionsList');
                if (list) {
                    $$('.fx-list-item', list).forEach(el => {
                        el.classList.toggle('is-active', String(el.dataset.id) === String(sectionId));
                    });
                }
                renderQuestions(readOnlySection(sec), { readOnly: true });
                showQuestionsListView();
                renderPreview();
            }
            return;
        }

        const template = state.templates.find(t => String(t.id) === String(templateId));
        if (!template) return;

        renderSections(template);
        const section = (template.sections || []).find(s => String(s.id) === String(sectionId));
        renderQuestions(section);
        showQuestionsListView();
        renderPreview();
    }

    function readOnlySection(sec) {
        return {
            id: sec.id,
            title: sec.title || '',
            description: sec.description || '',
            questions: (sec.questions || []).map(q => ({
                id: q.id,
                text: q.text || '',
                instructions: q.instructions || '',
                question_type: q.question_type || 'text',
                allowed_response_formats: q.allowed_response_formats || [],
                options: q.options || [],
                is_required: q.is_required !== false,
                position: q.position || 0,
                is_custom: !!q.is_custom,
            })),
        };
    }

    /* =====================================================================
       FORM DE SESSÃO
       ===================================================================== */
    function openNewSectionForm() {
        if (isViewingVersion()) {
            toast('Saia do modo leitura de versão para editar.', 'info');
            return;
        }
        requireEditableVersion(() => {
            state.editingSectionId = null;
            $('#fxFormSection').reset();
            $('#fxSecModalTitle').textContent = 'Nova sessão';
            $('#fxSecSubmit').textContent = 'Criar sessão';
            setColumnView($('#fxSections'), 'form');
            refreshIcons();
            setTimeout(() => { const el = $('#fxSecTitle'); if (el) el.focus(); }, 60);
        });
    }

    function openEditSectionForm(s) {
        if (isViewingVersion()) {
            toast('Saia do modo leitura de versão para editar.', 'info');
            return;
        }
        requireEditableVersion(() => {
            state.editingSectionId = s.id;
            $('#fxSecTitle').value = s.title || '';
            $('#fxSecDescription').value = s.description || '';
            $('#fxSecModalTitle').textContent = 'Editar sessão';
            $('#fxSecSubmit').textContent = 'Salvar';
            setColumnView($('#fxSections'), 'form');
            refreshIcons();
        });
    }

    function closeSectionForm() {
        state.editingSectionId = null;
        setColumnView($('#fxSections'), 'list');
    }

    function setupSectionForm() {
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
                state.editingSectionId = null;
                await loadTemplateDetail(templateId);
                setColumnView($('#fxSections'), 'list');
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
       PERGUNTAS
       ===================================================================== */
    function questionsFiltered(section) {
        if (!section) return [];
        let list = (section.questions || []).slice();
        if (state.questionsSearch) {
            const q = state.questionsSearch.toLowerCase();
            list = list.filter(item =>
                (item.text || '').toLowerCase().includes(q) ||
                (item.instructions || '').toLowerCase().includes(q)
            );
        }
        return list;
    }

    function renderQuestions(section, opts = {}) {
        const list = $('#fxQuestionsList');
        const count = $('#fxQuestionsCount');
        const sub = $('#fxQuestionsSub');
        const newBtn = $('#fxNewQuestionBtn');
        if (!list) return;

        const readOnly = !!opts.readOnly;
        const canEdit = !!section && !readOnly;

        const allQuestions = (section && section.questions) || [];
        const questions = questionsFiltered(section);

        if (count) count.textContent = String(allQuestions.length);
        if (sub) sub.textContent = section ? (section.title || '—') : 'Selecione uma sessão';
        if (newBtn) {
            newBtn.disabled = !canEdit;
            newBtn.title = readOnly ? 'Modo leitura' : 'Nova pergunta';
        }

        list.innerHTML = '';

        if (!section) {
            list.innerHTML = '<li class="fx-list-empty">Nenhuma sessão selecionada.</li>';
            return;
        }

        if (readOnly) {
            const banner = document.createElement('li');
            banner.className = 'fx-version-banner';
            banner.innerHTML =
                '<i data-lucide="eye"></i>' +
                '<span>Modo leitura — não é possível editar esta versão.</span>';
            list.appendChild(banner);
        }

        if (!allQuestions.length) {
            list.innerHTML = '<li class="fx-list-empty">Nenhuma pergunta ainda.</li>';
            return;
        }

        if (!questions.length) {
            const empty = document.createElement('li');
            empty.className = 'fx-list-empty';
            empty.textContent = `Nada encontrado para "${state.questionsSearch}".`;
            list.appendChild(empty);
            refreshIcons();
            return;
        }

        const frag = document.createDocumentFragment();
        for (let i = 0; i < questions.length; i++) {
            const q = questions[i];
            const originalIdx = allQuestions.findIndex(x => String(x.id) === String(q.id));
            const idx = originalIdx >= 0 ? originalIdx : 0;

            const li = document.createElement('li');
            li.className = 'fx-list-item fx-list-item--card fx-list-item--question';
            li.dataset.id = q.id;
            li.draggable = canEdit;

            const num = document.createElement('span');
            num.className = 'fx-q-index';
            num.textContent = String(idx + 1);

            const iconWrap = document.createElement('span');
            iconWrap.className = 'fx-q-icon';
            iconWrap.title = questionTypeLabel(q.question_type) || 'Pergunta';
            iconWrap.innerHTML = `<i data-lucide="${questionTypeIcon(q.question_type)}"></i>`;

            const body = document.createElement('div');
            body.className = 'fx-card-body';

            const titleEl = document.createElement('span');
            titleEl.className = 'fx-card-title';
            titleEl.textContent = q.text || '—';
            body.appendChild(titleEl);

            const tags = document.createElement('div');
            tags.className = 'fx-tags';

            const isReq = q.is_required !== false;
            const t2 = document.createElement('span');
            t2.className = 'fx-tag' + (isReq ? ' fx-tag--green' : ' fx-tag--optional');
            t2.title = isReq ? 'Obrigatória' : 'Opcional';
            t2.innerHTML = isReq
                ? '<i data-lucide="asterisk"></i><span>Obrigatória</span>'
                : '<i data-lucide="circle-slash-2"></i><span>Opcional</span>';
            tags.appendChild(t2);

            body.appendChild(tags);

            li.appendChild(num);
            li.appendChild(iconWrap);
            li.appendChild(body);

            if (canEdit) {
                const kebab = buildKebab([
                    {
                        label: 'Editar', icon: 'pencil',
                        onClick: () => openEditQuestionForm(q),
                    },
                    {
                        label: 'Excluir', icon: 'trash-2', danger: true,
                        onClick: () => confirmAction({
                            title: 'Excluir esta pergunta?',
                            subtitle: 'A pergunta será removida da sessão.',
                            confirmLabel: 'Excluir',
                            confirmVariant: 'danger',
                            icon: 'alert-triangle',
                            onConfirm: async () => {
                                try {
                                    await animateRemoveAndDelete(li, () =>
                                        api(API.questionDetail(state.selectedTemplateId, q.id), {
                                            method: 'DELETE',
                                        })
                                    );
                                    toast('Pergunta excluída.', 'success');
                                    const sec = currentSection();
                                    if (sec && sec.questions) {
                                        sec.questions = sec.questions.filter(
                                            x => String(x.id) !== String(q.id)
                                        );
                                        renderQuestions(sec);
                                    }
                                    renderPreview();
                                } catch (err) {
                                    console.error(err);
                                    toast(err.message || 'Erro ao excluir pergunta.', 'error');
                                    throw err;
                                }
                            },
                        }),
                    },
                ]);
                li.appendChild(kebab);

                li.addEventListener('click', (e) => {
                    if (e.target.closest('.fx-kebab') || e.target.closest('button')) return;
                    openEditQuestionForm(q);
                });
            }

            frag.appendChild(li);
        }
        list.appendChild(frag);

        makeSortable(list, '.fx-list-item--question', {
            onReorder: (orderedIds) => {
                const sec = currentSection();
                if (sec && sec.questions) {
                    const byId = Object.fromEntries(sec.questions.map(q => [String(q.id), q]));
                    const newList = [];
                    const seen = new Set();
                    for (const id of orderedIds) {
                        const item = byId[String(id)];
                        if (item && !seen.has(String(id))) {
                            newList.push(item);
                            seen.add(String(id));
                        }
                    }
                    for (const q of sec.questions) {
                        if (!seen.has(String(q.id))) newList.push(q);
                    }
                    sec.questions = newList;
                }
                if (!state.selectedTemplateId || !state.selectedSectionId) return;
                api(API.questionReorder(state.selectedTemplateId, state.selectedSectionId), {
                    method: 'POST',
                    body: { ordered_ids: orderedIds },
                }).catch((err) => {
                    console.error('Erro ao reordenar perguntas:', err);
                    toast('Falha ao salvar a nova ordem.', 'error');
                    loadTemplateDetail(state.selectedTemplateId);
                });
            },
        });

        refreshIcons();
    }

    // Ícones dos tipos. Mantemos entradas para tipos legados que
    // ainda podem existir em dados antigos (grid_single, grid_multiple,
    // scale, long_text) — apenas para não quebrar a renderização do
    // card de perguntas que já existiam. Novos tipos não são mais
    // oferecidos no formulário.
    function questionTypeIcon(type) {
        const map = {
            text: 'type',
            short_text: 'minus',
            long_text: 'align-left',
            single_choice: 'circle-dot',
            multiple_choice: 'check-square',
            dropdown: 'chevron-down-square',
            choice: 'circle-dot',
            scale: 'sliders',
            rating: 'star',
            number: 'hash',
            grid_single: 'grid-2x2',
            grid_multiple: 'grid-3x3',
            date: 'calendar',
            time: 'clock',
            url: 'link',
            yes_no: 'toggle-left',
            file_upload: 'upload',
        };
        return map[type] || 'help-circle';
    }

    function questionTypeLabel(type) {
        const map = {
            text: 'Texto livre',
            short_text: 'Resposta curta',
            long_text: 'Parágrafo',
            single_choice: 'Escolha única',
            multiple_choice: 'Múltipla escolha',
            dropdown: 'Lista suspensa',
            choice: 'Escolha (legado)',
            scale: 'Escala linear',
            rating: 'Classificação',
            number: 'Número',
            grid_single: 'Grade de múltipla escolha',
            grid_multiple: 'Grade da caixa de seleção',
            date: 'Data',
            time: 'Horário',
            url: 'Link',
            yes_no: 'Sim / Não',
            file_upload: 'Upload de arquivo',
        };
        return map[type] || '';
    }

    /* =====================================================================
       FORM DE PERGUNTA — VIEW INLINE
       ===================================================================== */
    function showQuestionsListView() {
        setColumnView($('#fxQuestions'), 'list');
        state.editingQuestion = null;
    }

    function showQuestionsFormView() {
        setColumnView($('#fxQuestions'), 'form');
    }

    function openNewQuestionForm() {
        if (isViewingVersion()) {
            toast('Saia do modo leitura de versão para editar.', 'info');
            return;
        }
        if (!state.selectedTemplateId || !state.selectedSectionId) {
            toast('Selecione um modelo e uma sessão antes.', 'info');
            return;
        }
        state.editingQuestion = null;
        resetQuestionForm();
        openQuestionForm({ mode: 'create' });
    }

    function openEditQuestionForm(q) {
        if (isViewingVersion()) {
            toast('Saia do modo leitura de versão para editar.', 'info');
            return;
        }
        state.editingQuestion = q;
        resetQuestionForm();

        $('#fxQText').value = q.text || '';
        $('#fxQInstructions').value = q.instructions || '';
        $('#fxQType').value = q.question_type || 'text';
        $('#fxQRequired').checked = q.is_required !== false;

        const formats = q.allowed_response_formats || ['text', 'audio', 'image'];
        $$('input[name="fxQFormat"]').forEach(el => {
            el.checked = formats.includes(el.value);
        });

        if (isGridType(q.question_type) && q.options && typeof q.options === 'object' && !Array.isArray(q.options)) {
            const rawRows = Array.isArray(q.options.rows) ? q.options.rows : [];
            state.gridRows = rawRows.map(r => ({ text: typeof r === 'string' ? r : (r?.text || '') }));
            const rawCols = Array.isArray(q.options.columns) ? q.options.columns : [];
            state.gridColumns = rawCols.map(c => ({
                text: typeof c === 'string' ? c : (c?.text || ''),
                image_url: (typeof c === 'object' && c?.image_url) || '',
                image_document_id: (typeof c === 'object' && c?.image_document_id) || null,
                _file: null,
            }));
            state.options = [];
        } else {
            state.options = Array.isArray(q.options)
                ? q.options.map(o => ({
                    text: o.text || '',
                    image_url: o.image_url || '',
                    image_document_id: o.image_document_id || null,
                    _file: null,
                }))
                : [];
            state.gridRows = [];
            state.gridColumns = [];
        }
        renderOptions();
        renderGridEditors();
        syncQuestionTypeUI();
        toggleOptionsVisibility();

        openQuestionForm({ mode: 'edit' });
    }

    function openQuestionForm({ mode }) {
        const titleEl = $('#fxQModalTitle');
        const subEl = $('#fxQModalSub');
        const submitBtn = $('#fxQSubmit');
        const backBtn = $('#fxQBackBtn');
        const cancelBtn = $('#fxQCancelBtn');

        const sec = currentSection();
        const sectionName = sec ? (sec.title || '—') : '';

        if (mode === 'create') {
            if (titleEl) titleEl.textContent = 'Nova pergunta';
            if (subEl) subEl.textContent = sectionName ? `Em "${sectionName}"` : 'Na sessão selecionada';
            if (submitBtn) submitBtn.querySelector('.fx-btn-label').textContent = 'Criar pergunta';
        } else {
            if (titleEl) titleEl.textContent = 'Editar pergunta';
            if (subEl) subEl.textContent = sectionName ? `Em "${sectionName}"` : 'Na sessão selecionada';
            if (submitBtn) submitBtn.querySelector('.fx-btn-label').textContent = 'Salvar alterações';
        }

        syncQuestionTypeUI();
        toggleOptionsVisibility();
        showQuestionsFormView();
        refreshIcons();

        if (backBtn) backBtn.onclick = () => showQuestionsListView();
        if (cancelBtn) cancelBtn.onclick = () => showQuestionsListView();
    }

    function closeQuestionForm() {
        showQuestionsListView();
    }

    function resetQuestionForm() {
        const form = $('#fxQForm');
        if (form) form.reset();
        $('#fxQRequired').checked = true;
        $$('input[name="fxQFormat"]').forEach(el => { el.checked = true; });
        $('#fxQType').value = 'text';
        state.options = [];
        state.gridRows = [];
        state.gridColumns = [];
        renderOptions();
        renderGridEditors();
        syncQuestionTypeUI();
        toggleOptionsVisibility();
    }

    function syncQuestionTypeUI() {
        const type = $('#fxQType').value || 'text';
        $$('.fx-q-type-btn').forEach(btn => {
            btn.classList.toggle('is-active', btn.dataset.type === type);
        });
    }

    function toggleOptionsVisibility() {
        const type = $('#fxQType').value;
        const field = $('#fxQOptionsField');
        const gridField = $('#fxQGridField');

        const isChoice = isChoiceType(type);
        const isGrid = isGridType(type);

        if (field) field.classList.toggle('is-hidden', !isChoice);
        if (gridField) gridField.classList.toggle('is-hidden', !isGrid);

        if (isChoice && state.options.length === 0) {
            state.options.push({ text: '', image_url: '', image_document_id: null, _file: null });
            state.options.push({ text: '', image_url: '', image_document_id: null, _file: null });
            renderOptions();
        }

        if (isGrid) {
            if (state.gridRows.length === 0) {
                state.gridRows.push({ text: '' });
                state.gridRows.push({ text: '' });
            }
            if (state.gridColumns.length === 0) {
                state.gridColumns.push({ text: '', image_url: '', image_document_id: null, _file: null });
                state.gridColumns.push({ text: '', image_url: '', image_document_id: null, _file: null });
            }
            renderGridEditors();
        }
    }

    /* =====================================================================
       EDITOR DE OPÇÕES (escolha)
       ===================================================================== */
    function renderOptions() {
        const list = $('#fxQOptionsList');
        if (!list) return;
        list.innerHTML = '';

        const frag = document.createDocumentFragment();
        for (let idx = 0; idx < state.options.length; idx++) {
            const opt = state.options[idx];
            const row = document.createElement('div');
            row.className = 'fx-option-row';

            const drag = document.createElement('span');
            drag.className = 'fx-option-drag';
            drag.innerHTML = '<i data-lucide="grip-vertical"></i>';

            const thumb = document.createElement('div');
            thumb.className = 'fx-option-thumb';
            thumb.title = opt.image_url
                ? 'Clique para expandir'
                : 'Adicionar imagem';

            if (opt.image_url) {
                const img = document.createElement('img');
                img.src = opt.image_url;
                img.alt = '';
                img.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    openImageViewer(opt.image_url);
                });
                img.addEventListener('error', () => {
                    thumb.innerHTML = '<i data-lucide="image-plus"></i>';
                    refreshIcons();
                });
                thumb.appendChild(img);

                const uploadBtn = document.createElement('label');
                uploadBtn.className = 'fx-option-thumb-upload';
                uploadBtn.title = 'Trocar imagem';
                uploadBtn.innerHTML = '<i data-lucide="upload"></i>';
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
                uploadBtn.appendChild(fileInput);
                thumb.appendChild(uploadBtn);
            } else {
                const plus = document.createElement('i');
                plus.setAttribute('data-lucide', 'image-plus');
                thumb.appendChild(plus);

                const fileInput = document.createElement('input');
                fileInput.type = 'file';
                fileInput.accept = 'image/*';
                fileInput.style.position = 'absolute';
                fileInput.style.inset = '0';
                fileInput.style.opacity = '0';
                fileInput.style.cursor = 'pointer';
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
            }

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
            frag.appendChild(row);
        }
        list.appendChild(frag);
        refreshIcons();
    }

    /* =====================================================================
       EDITOR DE GRID (linhas × colunas)
       — mantido para renderizar perguntas legadas que já usam grade.
       Como o tipo não é mais oferecido no form, este editor só aparece
       ao abrir uma pergunta que já era grid.
       ===================================================================== */
    function renderGridEditors() {
        const rowsWrap = $('#fxQGridRows');
        if (rowsWrap) {
            rowsWrap.innerHTML = '';
            const frag = document.createDocumentFragment();
            for (let idx = 0; idx < state.gridRows.length; idx++) {
                const r = state.gridRows[idx];
                const row = document.createElement('div');
                row.className = 'fx-grid-row';

                const drag = document.createElement('span');
                drag.className = 'fx-grid-row-drag';
                drag.innerHTML = '<i data-lucide="grip-vertical"></i>';

                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'fx-grid-row-input';
                input.placeholder = 'Nome da linha';
                input.value = r.text || '';
                input.maxLength = 200;
                input.addEventListener('input', () => { r.text = input.value; });

                const remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'fx-grid-row-remove';
                remove.title = 'Remover linha';
                remove.innerHTML = '<i data-lucide="x"></i>';
                remove.addEventListener('click', () => {
                    state.gridRows.splice(idx, 1);
                    renderGridEditors();
                });

                row.appendChild(drag);
                row.appendChild(input);
                row.appendChild(remove);
                frag.appendChild(row);
            }
            rowsWrap.appendChild(frag);
        }

        const colsWrap = $('#fxQGridCols');
        if (colsWrap) {
            colsWrap.innerHTML = '';
            const frag = document.createDocumentFragment();
            for (let idx = 0; idx < state.gridColumns.length; idx++) {
                const c = state.gridColumns[idx];
                const row = document.createElement('div');
                row.className = 'fx-grid-row';

                const drag = document.createElement('span');
                drag.className = 'fx-grid-row-drag';
                drag.innerHTML = '<i data-lucide="grip-vertical"></i>';

                const thumb = document.createElement('div');
                thumb.className = 'fx-grid-row-thumb';
                thumb.title = c.image_url
                    ? 'Clique para expandir'
                    : 'Adicionar imagem';

                if (c.image_url) {
                    const img = document.createElement('img');
                    img.src = c.image_url;
                    img.alt = '';
                    img.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        openImageViewer(c.image_url);
                    });
                    img.addEventListener('error', () => {
                        thumb.innerHTML = '<i data-lucide="image-plus"></i>';
                        refreshIcons();
                    });
                    thumb.appendChild(img);

                    const uploadBtn = document.createElement('label');
                    uploadBtn.className = 'fx-grid-row-thumb-upload';
                    uploadBtn.title = 'Trocar imagem';
                    uploadBtn.innerHTML = '<i data-lucide="upload"></i>';
                    const fileInput = document.createElement('input');
                    fileInput.type = 'file';
                    fileInput.accept = 'image/*';
                    fileInput.addEventListener('change', (e) => {
                        const file = e.target.files && e.target.files[0];
                        if (!file) return;
                        c._file = file;
                        if (c.image_url && c.image_url.startsWith('blob:')) {
                            URL.revokeObjectURL(c.image_url);
                        }
                        c.image_url = URL.createObjectURL(file);
                        renderGridEditors();
                    });
                    uploadBtn.appendChild(fileInput);
                    thumb.appendChild(uploadBtn);
                } else {
                    const plus = document.createElement('i');
                    plus.setAttribute('data-lucide', 'image-plus');
                    thumb.appendChild(plus);

                    const fileInput = document.createElement('input');
                    fileInput.type = 'file';
                    fileInput.accept = 'image/*';
                    fileInput.style.position = 'absolute';
                    fileInput.style.inset = '0';
                    fileInput.style.opacity = '0';
                    fileInput.style.cursor = 'pointer';
                    fileInput.addEventListener('change', (e) => {
                        const file = e.target.files && e.target.files[0];
                        if (!file) return;
                        c._file = file;
                        if (c.image_url && c.image_url.startsWith('blob:')) {
                            URL.revokeObjectURL(c.image_url);
                        }
                        c.image_url = URL.createObjectURL(file);
                        renderGridEditors();
                    });
                    thumb.appendChild(fileInput);
                }

                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'fx-grid-row-input';
                input.placeholder = 'Nome da coluna';
                input.value = c.text || '';
                input.maxLength = 200;
                input.addEventListener('input', () => { c.text = input.value; });

                const remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'fx-grid-row-remove';
                remove.title = 'Remover coluna';
                remove.innerHTML = '<i data-lucide="x"></i>';
                remove.addEventListener('click', () => {
                    if (c.image_url && c.image_url.startsWith('blob:')) {
                        URL.revokeObjectURL(c.image_url);
                    }
                    state.gridColumns.splice(idx, 1);
                    renderGridEditors();
                });

                row.appendChild(drag);
                row.appendChild(thumb);
                row.appendChild(input);
                row.appendChild(remove);
                frag.appendChild(row);
            }
            colsWrap.appendChild(frag);
        }
        refreshIcons();
    }

    /* =====================================================================
       UPLOAD DE IMAGENS
       ===================================================================== */
    async function uploadOptionImage(file) {
        const fd = new FormData();
        fd.append('file', file);
        fd.append('kind', 'image');
        return await api(API.documents, { method: 'POST', body: fd });
    }

    /* =====================================================================
       SUBMIT DO FORM DE PERGUNTA
       ===================================================================== */
    async function submitQuestionForm(e) {
        e.preventDefault();

        if (isViewingVersion()) {
            toast('Modo leitura — não é possível salvar.', 'info');
            return;
        }

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

        const isChoice = isChoiceType(questionType);
        const isGrid = isGridType(questionType);

        let cleanedOptions = null;
        let cleanedGrid = null;

        if (isChoice) {
            cleanedOptions = state.options
                .map(o => ({ ...o, text: (o.text || '').trim() }))
                .filter(o => o.text);
            if (cleanedOptions.length < 2) {
                toast('Adicione pelo menos 2 opções com texto.', 'error');
                return;
            }
        }

        if (isGrid) {
            const rows = state.gridRows
                .map(r => (r.text || '').trim())
                .filter(Boolean);
            const cols = state.gridColumns
                .map(c => ({ ...c, text: (c.text || '').trim() }))
                .filter(c => c.text);

            if (!rows.length) {
                toast('Adicione pelo menos uma linha.', 'error');
                return;
            }
            if (cols.length < 2) {
                toast('Adicione pelo menos duas colunas com texto.', 'error');
                return;
            }
            cleanedGrid = { rows, columns: cols };
        }

        requireEditableVersion(async () => {
            const submitBtn = $('#fxQSubmit');
            if (submitBtn) setButtonLoading(submitBtn, true);

            try {
                let optionsPayload = null;

                if (isChoice) {
                    for (const opt of cleanedOptions) {
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
                    optionsPayload = cleanedOptions.map(o => ({
                        text: o.text,
                        image_document_id: o.image_document_id || null,
                    }));
                }

                if (isGrid) {
                    const cleanCols = [];
                    for (const col of cleanedGrid.columns) {
                        let docId = col.image_document_id || null;
                        if (col._file) {
                            const doc = await uploadOptionImage(col._file);
                            if (doc && doc.id) {
                                docId = doc.id;
                                if (doc.file_url || doc.preview_url) {
                                    if (col.image_url && col.image_url.startsWith('blob:')) {
                                        URL.revokeObjectURL(col.image_url);
                                    }
                                    col.image_url = doc.file_url || doc.preview_url;
                                }
                            }
                            col._file = null;
                        }
                        cleanCols.push({
                            text: col.text,
                            image_document_id: docId,
                        });
                    }
                    optionsPayload = {
                        rows: cleanedGrid.rows,
                        columns: cleanCols,
                    };
                }

                const payload = {
                    text,
                    instructions,
                    question_type: questionType,
                    allowed_response_formats: formats,
                    is_required: isRequired,
                };
                if (optionsPayload !== null) payload.options = optionsPayload;

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
                const sec = currentSection();
                if (sec) renderQuestions(sec);
                renderPreview();
                showQuestionsListView();
            } catch (err) {
                console.error(err);
                toast(err.message || 'Erro ao salvar pergunta.', 'error');
            } finally {
                if (submitBtn) setButtonLoading(submitBtn, false);
            }
        });
    }

    /* =====================================================================
       PRÉVIA
       ===================================================================== */
    function renderPreview() {
        const emptyEl = $('#fxPvEmpty');
        const contentEl = $('#fxPvContent');
        const coverEl = $('#fxPvCover');
        const introWrap = $('#fxPvIntroWrap');
        const introText = $('#fxPvIntroText');
        if (!emptyEl || !contentEl) return;

        let title = null;
        let description = null;
        let cover = null;
        let introMessage = '';
        let sections = [];

        if (state.selectedVersionId && state.viewingVersion) {
            const v = state.viewingVersion;
            const tpl = currentTemplate();
            const tplName = tpl?.name || '';
            title = `v${v.version_number}${tplName ? ' · ' + tplName : ''}`;
            description = v.status_display
                ? `Versão ${v.status_display.toLowerCase()}`
                : '';
            cover = tpl?.cover_url || null;
            introMessage = tpl?.intro_message || '';
            sections = (v.structure?.sections || []);
        } else {
            const tpl = currentTemplate();
            if (!tpl) {
                emptyEl.classList.remove('is-hidden');
                contentEl.classList.add('is-hidden');
                coverEl.style.backgroundImage = '';
                return;
            }
            title = tpl.name || '—';
            description = tpl.description || 'Vamos entender melhor o seu projeto.';
            cover = tpl.cover_url || null;
            introMessage = tpl.intro_message || '';
            sections = tpl.sections || [];
        }

        emptyEl.classList.add('is-hidden');
        contentEl.classList.remove('is-hidden');

        if (cover) {
            coverEl.style.backgroundImage = `url("${withCacheBuster(cover, 'cover-' + (state.selectedTemplateId || ''))}")`;
        } else {
            coverEl.style.backgroundImage = '';
        }

        $('#fxPvTitle').textContent = title;
        $('#fxPvText').textContent = description || '';

        const introTrimmed = (introMessage || '').trim();
        if (introWrap && introText) {
            if (introTrimmed) {
                introText.textContent = introTrimmed;
                introWrap.classList.remove('is-hidden');
            } else {
                introText.textContent = '';
                introWrap.classList.add('is-hidden');
            }
        }

        const currentSectionIdx = Math.max(0, sections.findIndex(
            s => String(s.id) === String(state.selectedSectionId)
        ));
        const sec = sections[currentSectionIdx];

        if (sections.length) {
            const percent = sections.length > 1
                ? Math.round((currentSectionIdx / (sections.length - 1)) * 100)
                : 100;
            $('#fxPvProgressFill').style.width = percent + '%';
            $('#fxPvProgressLabel').textContent =
                `${currentSectionIdx + 1} de ${sections.length}`;
        } else {
            $('#fxPvProgressFill').style.width = '0%';
            $('#fxPvProgressLabel').textContent = '0 de 0';
        }

        const fieldsWrap = $('#fxPvFieldsWrap');
        fieldsWrap.innerHTML = '';

        if (sec) {
            $('#fxPvSecTitle').textContent = sec.title || '—';
            $('#fxPvSecDesc').textContent = sec.description || '';

            const questions = sec.questions || [];
            const frag = document.createDocumentFragment();
            for (let idx = 0; idx < questions.length; idx++) {
                frag.appendChild(buildPreviewField(questions[idx], idx));
            }
            fieldsWrap.appendChild(frag);
        } else {
            $('#fxPvSecTitle').textContent = '—';
            $('#fxPvSecDesc').textContent = '';
        }

        $('#fxPreviewSub').textContent = title
            ? `Como o cliente verá "${title}".`
            : 'Como o cliente verá o briefing.';

        refreshIcons();
    }

    function buildPreviewField(q, idx) {
        const field = document.createElement('div');
        field.className = 'fx-pv-field';

        const label = document.createElement('label');
        label.textContent = `${idx + 1}. ${q.text || ''}`;
        field.appendChild(label);

        const type = q.question_type || 'text';

        if (type === 'single_choice' || type === 'multiple_choice' || type === 'dropdown') {
            const opts = document.createElement('div');
            opts.className = 'fx-pv-options';
            (q.options || []).forEach(o => {
                const opt = document.createElement('div');
                opt.className = 'fx-pv-option';
                const thumb = document.createElement('span');
                thumb.className = 'fx-pv-option-thumb';
                if (o.image_url) {
                    thumb.innerHTML = `<img src="${escapeHtml(o.image_url)}" alt="">`;
                } else {
                    thumb.innerHTML = `<i data-lucide="${type === 'single_choice' || type === 'dropdown' ? 'circle' : 'square'}"></i>`;
                }
                opt.appendChild(thumb);
                const text = document.createElement('span');
                text.textContent = o.text || '';
                opt.appendChild(text);
                opts.appendChild(opt);
            });
            field.appendChild(opts);
        } else if (type === 'grid_single' || type === 'grid_multiple') {
            const rawOpts = q.options && !Array.isArray(q.options) ? q.options : { rows: [], columns: [] };
            const rows = Array.isArray(rawOpts.rows) ? rawOpts.rows : [];
            const cols = Array.isArray(rawOpts.columns) ? rawOpts.columns : [];

            const grid = document.createElement('div');
            grid.className = 'fx-pv-grid';
            grid.style.display = 'grid';
            grid.style.gridTemplateColumns = `1.5fr repeat(${cols.length}, 1fr)`;
            grid.style.gap = '6px';
            grid.style.alignItems = 'center';
            grid.style.fontSize = '11px';

            const emptyHeader = document.createElement('div');
            grid.appendChild(emptyHeader);
            cols.forEach(c => {
                const cell = document.createElement('div');
                cell.style.fontWeight = '600';
                cell.style.textAlign = 'center';
                cell.style.color = 'var(--text-secondary)';
                cell.textContent = c.text || '';
                grid.appendChild(cell);
            });

            rows.forEach(r => {
                const rowLabel = document.createElement('div');
                rowLabel.style.fontSize = '12px';
                rowLabel.style.color = 'var(--text-primary)';
                rowLabel.textContent = typeof r === 'string' ? r : (r?.text || '');
                grid.appendChild(rowLabel);

                cols.forEach(() => {
                    const cell = document.createElement('div');
                    cell.style.textAlign = 'center';
                    cell.style.color = 'var(--text-tertiary)';
                    cell.innerHTML = `<i data-lucide="${type === 'grid_single' ? 'circle' : 'square'}" style="width:12px;height:12px;opacity:0.5;"></i>`;
                    grid.appendChild(cell);
                });
            });

            field.appendChild(grid);
        } else if (type === 'date') {
            const inp = document.createElement('input');
            inp.type = 'date';
            inp.className = 'fx-pv-input';
            inp.readOnly = true;
            inp.tabIndex = -1;
            field.appendChild(inp);
        } else if (type === 'time') {
            const inp = document.createElement('input');
            inp.type = 'time';
            inp.className = 'fx-pv-input';
            inp.readOnly = true;
            inp.tabIndex = -1;
            field.appendChild(inp);
        } else if (type === 'file_upload') {
            const drop = document.createElement('div');
            drop.className = 'fx-pv-input';
            drop.style.display = 'flex';
            drop.style.alignItems = 'center';
            drop.style.justifyContent = 'center';
            drop.style.gap = '8px';
            drop.style.cursor = 'default';
            drop.innerHTML = `<i data-lucide="upload" style="width:14px;height:14px;opacity:0.6;"></i><span>Enviar arquivo</span>`;
            field.appendChild(drop);
        } else if (type === 'yes_no') {
            const wrap = document.createElement('div');
            wrap.style.display = 'flex';
            wrap.style.gap = '8px';
            ['Sim', 'Não'].forEach(opt => {
                const b = document.createElement('div');
                b.className = 'fx-pv-option';
                b.style.flex = '1';
                b.style.justifyContent = 'center';
                b.innerHTML = `<i data-lucide="circle" style="width:12px;height:12px;"></i><span>${opt}</span>`;
                wrap.appendChild(b);
            });
            field.appendChild(wrap);
        } else if (type === 'number') {
            const grp = document.createElement('div');
            grp.className = 'fx-pv-input-group';
            const addon = document.createElement('span');
            addon.className = 'fx-pv-addon';
            addon.textContent = '#';
            grp.appendChild(addon);
            const inp = document.createElement('input');
            inp.type = 'text';
            inp.className = 'fx-pv-input';
            inp.placeholder = 'Digite um número…';
            inp.readOnly = true;
            inp.tabIndex = -1;
            grp.appendChild(inp);
            field.appendChild(grp);
        } else if (type === 'scale') {
            const wrap = document.createElement('div');
            wrap.style.display = 'flex';
            wrap.style.gap = '4px';
            wrap.style.flexWrap = 'wrap';
            for (let i = 1; i <= 10; i++) {
                const b = document.createElement('div');
                b.className = 'fx-pv-option';
                b.style.width = '32px';
                b.style.height = '32px';
                b.style.padding = '0';
                b.style.justifyContent = 'center';
                b.textContent = String(i);
                b.style.fontSize = '12px';
                b.style.fontWeight = '600';
                wrap.appendChild(b);
            }
            field.appendChild(wrap);
        } else if (type === 'rating') {
            const wrap = document.createElement('div');
            wrap.style.display = 'flex';
            wrap.style.gap = '4px';
            for (let i = 0; i < 5; i++) {
                const b = document.createElement('div');
                b.style.color = 'var(--text-tertiary)';
                b.innerHTML = '<i data-lucide="star" style="width:18px;height:18px;"></i>';
                wrap.appendChild(b);
            }
            field.appendChild(wrap);
        } else if (type === 'url') {
            const inp = document.createElement('input');
            inp.type = 'text';
            inp.className = 'fx-pv-input';
            inp.placeholder = 'https://…';
            inp.readOnly = true;
            inp.tabIndex = -1;
            field.appendChild(inp);
        } else {
            const inp = document.createElement('input');
            inp.type = 'text';
            inp.className = 'fx-pv-input';
            inp.placeholder = 'Digite sua resposta…';
            inp.readOnly = true;
            inp.tabIndex = -1;
            field.appendChild(inp);
        }

        return field;
    }

    /* =====================================================================
       BIND
       ===================================================================== */
    function bindCreateButtons() {
        const topCatBtn = $('#fxTopCategoriesBtn');
        if (topCatBtn) {
            topCatBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleCatDropdown();
            });
        }
        const topNewCatBtn = $('#fxCatDropdownAdd');
        if (topNewCatBtn) {
            topNewCatBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                closeCatDropdown();
                openManageCategoriesModal();
            });
        }

        const newTplBtn = $('#fxNewTemplateBtn');
        if (newTplBtn) newTplBtn.addEventListener('click', openNewTemplateForm);

        const tplBackBtn = $('#fxTplFormBackBtn');
        if (tplBackBtn) tplBackBtn.addEventListener('click', closeTemplateForm);

        const tplCancelBtn = $('#fxTplCancelBtn');
        if (tplCancelBtn) tplCancelBtn.addEventListener('click', closeTemplateForm);

        const versionsBtn = $('#fxManageVersionsBtn');
        if (versionsBtn) versionsBtn.addEventListener('click', () => {
            const tpl = currentTemplate();
            if (!tpl) {
                toast('Selecione um modelo para ver as versões.', 'info');
                return;
            }
            openVersionsPanel(tpl.id);
        });

        const versionsBackBtn = $('#fxVersionsBackBtn');
        if (versionsBackBtn) versionsBackBtn.addEventListener('click', closeVersionsPanel);

        const versionsHelpBtn = $('#fxVersionsHelpBtn');
        if (versionsHelpBtn) versionsHelpBtn.addEventListener('click', () => {
            openModal('fxModalVersionsHelp');
        });

        const newSecBtn = $('#fxNewSectionBtn');
        if (newSecBtn) newSecBtn.addEventListener('click', openNewSectionForm);

        const secBackBtn = $('#fxSecFormBackBtn');
        if (secBackBtn) secBackBtn.addEventListener('click', closeSectionForm);

        const secCancelBtn = $('#fxSecCancelBtn');
        if (secCancelBtn) secCancelBtn.addEventListener('click', closeSectionForm);

        const newQBtn = $('#fxNewQuestionBtn');
        if (newQBtn) newQBtn.addEventListener('click', openNewQuestionForm);

        const qBackBtn = $('#fxQBackBtn');
        if (qBackBtn) qBackBtn.addEventListener('click', showQuestionsListView);

        const qCancelBtn = $('#fxQCancelBtn');
        if (qCancelBtn) qCancelBtn.addEventListener('click', showQuestionsListView);

        $$('.fx-q-type-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const type = btn.dataset.type || 'text';
                $('#fxQType').value = type;
                syncQuestionTypeUI();
                toggleOptionsVisibility();
            });
        });

        const typeSel = $('#fxQType');
        if (typeSel) typeSel.addEventListener('change', () => {
            syncQuestionTypeUI();
            toggleOptionsVisibility();
        });

        const addOptBtn = $('#fxQAddOptionBtn');
        if (addOptBtn) addOptBtn.addEventListener('click', () => {
            state.options.push({ text: '', image_url: '', image_document_id: null, _file: null });
            renderOptions();
        });

        const addGridRowBtn = $('#fxQAddGridRowBtn');
        if (addGridRowBtn) addGridRowBtn.addEventListener('click', () => {
            state.gridRows.push({ text: '' });
            renderGridEditors();
        });

        const addGridColBtn = $('#fxQAddGridColBtn');
        if (addGridColBtn) addGridColBtn.addEventListener('click', () => {
            state.gridColumns.push({ text: '', image_url: '', image_document_id: null, _file: null });
            renderGridEditors();
        });

        const qForm = $('#fxQForm');
        if (qForm) qForm.addEventListener('submit', submitQuestionForm);

        const templatesSearch = $('#fxTemplatesSearch');
        if (templatesSearch) {
            let tTimer = null;
            templatesSearch.addEventListener('input', () => {
                clearTimeout(tTimer);
                const val = templatesSearch.value.trim();
                tTimer = setTimeout(() => {
                    state.templatesSearch = val;
                    renderTemplates();
                }, 90);
            });
        }

        const sectionsSearch = $('#fxSectionsSearch');
        if (sectionsSearch) {
            let sTimer = null;
            sectionsSearch.addEventListener('input', () => {
                clearTimeout(sTimer);
                const val = sectionsSearch.value.trim();
                sTimer = setTimeout(() => {
                    state.sectionsSearch = val;
                    if (state.selectedVersionId && state.viewingVersion) {
                        const fake = {
                            sections: (state.viewingVersion.structure?.sections || []),
                        };
                        renderSections(fake, { readOnly: true, version: state.viewingVersion });
                    } else {
                        renderSections(currentTemplate());
                    }
                }, 90);
            });
        }

        const questionsSearch = $('#fxQuestionsSearch');
        if (questionsSearch) {
            let qTimer = null;
            questionsSearch.addEventListener('input', () => {
                clearTimeout(qTimer);
                const val = questionsSearch.value.trim();
                qTimer = setTimeout(() => {
                    state.questionsSearch = val;
                    const sec = currentSection();
                    if (sec) {
                        renderQuestions(sec, { readOnly: isViewingVersion() });
                    } else {
                        renderQuestions(null);
                    }
                }, 90);
            });
        }

        $$('#fxTemplatesStatusFilter .fx-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                $$('#fxTemplatesStatusFilter .fx-chip').forEach(c => c.classList.remove('is-active'));
                chip.classList.add('is-active');
                state.templatesStatus = chip.dataset.status || 'all';
                renderTemplates();
            });
        });

        const aiBtn = $('#fxAiBtn');
        if (aiBtn) aiBtn.addEventListener('click', () => {
            openModal('fxModalAi');
        });
    }

    /* =====================================================================
       IMPORTAR FORMS
       ===================================================================== */
    function showFormsState(which) {
        const ids = {
            'loading': 'fxFormsLoading',
            'no-integration': 'fxFormsNoIntegration',
            'with-integration': 'fxFormsWithIntegration',
            'confirm': 'fxFormsConfirm',
        };
        Object.keys(ids).forEach(function (k) {
            const el = document.getElementById(ids[k]);
            if (el) el.hidden = (k !== which);
        });

        const confirmBtn = $('#fxFormsConfirmBtn');
        if (confirmBtn) {
            confirmBtn.hidden = (which !== 'confirm');
        }

        const cancelBtn = $('#fxFormsCancelBtn');
        if (cancelBtn) {
            cancelBtn.textContent = (which === 'confirm')
                ? 'Voltar'
                : 'Cancelar';
        }
    }

    function resetFormsModal() {
        state.formsList = [];
        state.formsFiltered = [];
        state.formsQuery = '';
        state.importingFormId = null;
        state.formsLoading = false;
        state.formsPreview = null;

        const search = $('#fxFormsSearchInput');
        if (search) search.value = '';

        const searchClear = $('#fxFormsSearchClear');
        if (searchClear) searchClear.classList.add('hidden');

        const urlInput = $('#fxFormsUrl');
        if (urlInput) urlInput.value = '';

        const urlError = $('#fxFormsUrlError');
        if (urlError) {
            urlError.classList.add('hidden');
            urlError.textContent = '';
        }

        const count = $('#fxFormsSectionCount');
        if (count) count.textContent = '';

        const sub = $('#fxFormsSub');
        if (sub) {
            sub.textContent = 'Escolha um formulário da sua conta ou adicione um link.';
        }

        const newName = $('#fxFormsNewName');
        if (newName) newName.value = '';

        const previewError = $('#fxFormsPreviewError');
        if (previewError) {
            previewError.classList.add('hidden');
            previewError.textContent = '';
        }

        showFormsState('loading');
    }

    function updateFormsCount() {
        const countEl = $('#fxFormsSectionCount');
        if (!countEl) return;
        if (state.formsQuery) {
            countEl.textContent =
                state.formsFiltered.length + ' de ' + state.formsList.length;
        } else if (state.formsList.length) {
            countEl.textContent = String(state.formsList.length);
        } else {
            countEl.textContent = '';
        }
    }

    function renderFormsList() {
        const list = $('#fxFormsList');
        if (!list) return;

        const items = state.formsFiltered;

        if (!items.length) {
            if (state.formsQuery) {
                list.innerHTML =
                    '<div class="fx-gforms-list-empty">' +
                    '<i data-lucide="search-x"></i>' +
                    '<span>Nada encontrado para "' +
                    escapeHtml(state.formsQuery) +
                    '".</span>' +
                    '</div>';
            } else {
                list.innerHTML =
                    '<div class="fx-gforms-list-empty">' +
                    '<i data-lucide="file-question"></i>' +
                    '<span>Você ainda não tem formulários no Google Forms.</span>' +
                    '</div>';
            }
            refreshIcons();
            updateFormsCount();
            return;
        }

        list.innerHTML = '';
        const frag = document.createDocumentFragment();

        items.forEach(function (form) {
            const isImporting = state.importingFormId === form.id;
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'fx-gforms-item' + (isImporting ? ' is-importing' : '');
            row.dataset.formId = form.id;
            row.setAttribute('role', 'option');
            row.disabled = isImporting;

            row.innerHTML =
                '<div class="fx-gforms-item-icon">' +
                '<i data-lucide="file-text"></i>' +
                '</div>' +
                '<div class="fx-gforms-item-body">' +
                '<div class="fx-gforms-item-name">' +
                escapeHtml(form.name || 'Formulário sem título') +
                '</div>' +
                '<div class="fx-gforms-item-meta">Formulário Google</div>' +
                '</div>' +
                '<div class="fx-gforms-item-action">' +
                (isImporting
                    ? '<i data-lucide="loader-2" class="fx-spin"></i>'
                    : '<i data-lucide="arrow-right"></i>') +
                '</div>';

            if (!isImporting) {
                row.addEventListener('click', function () {
                    startFormPreview(form.id);
                });
            }

            frag.appendChild(row);
        });

        list.appendChild(frag);
        refreshIcons();
        updateFormsCount();
    }

    function applyFormsFilter() {
        const q = (state.formsQuery || '').trim().toLowerCase();
        if (!q) {
            state.formsFiltered = state.formsList.slice();
        } else {
            state.formsFiltered = state.formsList.filter(function (f) {
                return (f.name || '').toLowerCase().indexOf(q) !== -1;
            });
        }
        renderFormsList();
    }

    function loadFormsList() {
        if (state.formsLoading) return;
        state.formsLoading = true;
        showFormsState('loading');

        api(API.formsSearch, { method: 'GET' })
            .then(function (data) {
                state.formsList = (data && data.results) || [];
                state.formsFiltered = state.formsList.slice();
                showFormsState('with-integration');
                renderFormsList();

                setTimeout(function () {
                    const search = $('#fxFormsSearchInput');
                    if (search && !search.value) {
                        const active = document.activeElement;
                        if (active && active.id === 'fxFormsUrl') return;
                        search.focus();
                    }
                }, 80);
            })
            .catch(function (err) {
                handleFormsLoadError(err);
            })
            .then(function () {
                state.formsLoading = false;
            });
    }

    function handleFormsLoadError(err) {
        if (err.status === 428) {
            showFormsState('no-integration');
            return;
        }

        const list = $('#fxFormsList');
        if (list) {
            list.innerHTML =
                '<div class="fx-gforms-list-empty fx-gforms-list-empty--error">' +
                '<i data-lucide="alert-circle"></i>' +
                '<span>' +
                escapeHtml(err.message || 'Erro ao carregar formulários.') +
                '</span>' +
                '<button type="button" class="fx-btn fx-btn--sm" id="fxFormsRetryBtn">' +
                '<i data-lucide="refresh-cw"></i>' +
                '<span>Tentar novamente</span>' +
                '</button>' +
                '</div>';
            refreshIcons();

            const retry = $('#fxFormsRetryBtn');
            if (retry) retry.addEventListener('click', loadFormsList);
        }
        showFormsState('with-integration');
    }

    function openImportFormsModal() {
        resetFormsModal();
        openModal('fxModalImportForms');
        loadFormsList();
    }

    function closeImportFormsModal() {
        state.importingFormId = null;
        state.formsPreview = null;
        closeModal('fxModalImportForms');
    }

    function startFormPreview(formValue) {
        state.importingFormId = (typeof formValue === 'string' && formValue.length < 50)
            ? formValue
            : null;
        if (!state.importingFormId) renderFormsList();

        showFormsState('confirm');
        const loadingEl = $('#fxFormsPreviewLoading');
        const previewEl = $('#fxFormsPreview');
        if (loadingEl) loadingEl.hidden = false;
        if (previewEl) previewEl.hidden = true;

        api(API.formsPreview, {
            method: 'POST',
            body: { form: formValue },
        })
            .then(function (preview) {
                state.formsPreview = {
                    form_value: formValue,
                    form_id: preview.form_id,
                    form_name: preview.form_name,
                    sections_count: preview.sections_count,
                    questions_count: preview.questions_count,
                };
                renderFormsPreview();
            })
            .catch(function (err) {
                handlePreviewError(err);
            })
            .then(function () {
                state.importingFormId = null;
                if (document.getElementById('fxFormsWithIntegration')?.hidden === false) {
                    renderFormsList();
                }
            });
    }

    function renderFormsPreview() {
        const preview = state.formsPreview;
        if (!preview) return;

        const loadingEl = $('#fxFormsPreviewLoading');
        const previewEl = $('#fxFormsPreview');
        if (loadingEl) loadingEl.hidden = true;
        if (previewEl) previewEl.hidden = false;

        const refName = $('#fxFormsPreviewRefName');
        if (refName) refName.textContent = preview.form_name || '—';

        const refMeta = $('#fxFormsPreviewRefMeta');
        if (refMeta) {
            const parts = [];
            parts.push(preview.sections_count + ' ' +
                (preview.sections_count === 1 ? 'sessão' : 'sessões'));
            parts.push(preview.questions_count + ' ' +
                (preview.questions_count === 1 ? 'pergunta' : 'perguntas'));
            refMeta.textContent = parts.join(' · ');
        }

        const nameInput = $('#fxFormsNewName');
        if (nameInput) {
            nameInput.value = preview.form_name || '';
        }

        const previewError = $('#fxFormsPreviewError');
        if (previewError) {
            previewError.classList.add('hidden');
            previewError.textContent = '';
        }

        setTimeout(function () {
            const el = $('#fxFormsNewName');
            if (el) {
                el.focus();
                el.select();
            }
        }, 60);
    }

    function handlePreviewError(err) {
        if (err.status === 428) {
            showFormsState('no-integration');
            return;
        }

        if (err.status === 501) {
            toast(
                'A leitura de formulários ainda não está disponível. Estamos finalizando esta integração.',
                'info'
            );
            showFormsState('with-integration');
            return;
        }

        showFormsState('with-integration');
        toast(err.message || 'Erro ao ler o formulário.', 'error');
    }

    function confirmFormImport() {
        const preview = state.formsPreview;
        if (!preview) return;

        const nameInput = $('#fxFormsNewName');
        const templateName = (nameInput ? nameInput.value : '').trim();

        if (!templateName) {
            const previewError = $('#fxFormsPreviewError');
            if (previewError) {
                previewError.textContent = 'Informe um nome para o novo modelo.';
                previewError.classList.remove('hidden');
            }
            if (nameInput) nameInput.focus();
            return;
        }

        const btn = $('#fxFormsConfirmBtn');
        if (btn) setButtonLoading(btn, true);

        const previewError = $('#fxFormsPreviewError');
        if (previewError) {
            previewError.classList.add('hidden');
            previewError.textContent = '';
        }

        api(API.formsImport, {
            method: 'POST',
            body: {
                form: preview.form_value,
                template_name: templateName,
            },
        })
            .then(function (result) {
                const newTemplateId = result && result.template_id;

                toast(
                    result && result.template_name
                        ? '"' + result.template_name + '" criado.'
                        : 'Modelo criado.',
                    'success'
                );

                closeImportFormsModal();

                return loadTemplates().then(function () {
                    if (newTemplateId) {
                        return selectTemplate(newTemplateId);
                    }
                    return Promise.resolve();
                });
            })
            .catch(function (err) {
                handleConfirmError(err);
            })
            .then(function () {
                if (btn) setButtonLoading(btn, false);
            });
    }

    function handleConfirmError(err) {
        if (err.status === 428) {
            const urlInput = $('#fxFormsUrl');
            if (urlInput && urlInput.value.trim()) {
                try {
                    sessionStorage.setItem(FORMS_PENDING_URL_KEY, urlInput.value.trim());
                } catch (_) {}
            }
            showFormsState('no-integration');
            return;
        }

        if (err.status === 501) {
            toast(
                'A leitura de formulários ainda não está disponível. Estamos finalizando esta integração.',
                'info'
            );
            return;
        }

        const previewError = $('#fxFormsPreviewError');
        if (previewError) {
            previewError.textContent = err.message || 'Erro ao criar modelo.';
            previewError.classList.remove('hidden');
        } else {
            toast(err.message || 'Erro ao criar modelo.', 'error');
        }
    }

    function importFormByUrl() {
        const input = $('#fxFormsUrl');
        if (!input) return;

        const url = (input.value || '').trim();
        const errorEl = $('#fxFormsUrlError');

        if (errorEl) {
            errorEl.classList.add('hidden');
            errorEl.textContent = '';
        }

        if (!url) {
            if (errorEl) {
                errorEl.textContent = 'Cole a URL do formulário.';
                errorEl.classList.remove('hidden');
            }
            input.focus();
            return;
        }

        const submitBtn = $('#fxFormsUrlSubmit');
        if (submitBtn) setButtonLoading(submitBtn, true);

        startFormPreview(url);

        if (submitBtn) setButtonLoading(submitBtn, false);
    }

    function connectGoogleForImport() {
        const urlInput = $('#fxFormsUrl');
        if (urlInput && urlInput.value.trim()) {
            try {
                sessionStorage.setItem(FORMS_PENDING_URL_KEY, urlInput.value.trim());
            } catch (_) {}
        }

        const next = encodeURIComponent(window.location.pathname);
        window.location.href = API.googleOAuthStart + '?next=' + next;
    }

    function checkGoogleConnectedReturn() {
        const params = new URLSearchParams(window.location.search);
        if (!params.get('google_connected')) return false;

        const cleanUrl =
            window.location.pathname +
            window.location.search
                .replace(/[?&]google_connected=1/, '')
                .replace(/^&/, '?') +
            window.location.hash;

        window.history.replaceState({}, '', cleanUrl);

        setTimeout(function () {
            if (!document.getElementById('fxPage')) return;

            openImportFormsModal();

            let pending = null;
            try {
                pending = sessionStorage.getItem(FORMS_PENDING_URL_KEY);
            } catch (_) {}

            if (pending) {
                try {
                    sessionStorage.removeItem(FORMS_PENDING_URL_KEY);
                } catch (_) {}

                const urlInput = $('#fxFormsUrl');
                if (urlInput) {
                    urlInput.value = pending;
                }
            }
        }, 250);

        return true;
    }

    function bindImportForms() {
        if (state.formsBinded) return;
        state.formsBinded = true;

        const openBtn = $('#fxImportFormsBtn');
        if (openBtn) {
            openBtn.addEventListener('click', openImportFormsModal);
        }

        const modal = $('#fxModalImportForms');
        if (modal) {
            $$('[data-fx-close="fxModalImportForms"]', modal).forEach(function (el) {
                el.addEventListener('click', function (e) {
                    e.preventDefault();
                    closeImportFormsModal();
                });
            });
            modal.addEventListener('click', function (e) {
                if (e.target === modal) closeImportFormsModal();
            });
        }

        const search = $('#fxFormsSearchInput');
        if (search) {
            let timer = null;
            search.addEventListener('input', function () {
                const value = search.value;
                const clearBtn = $('#fxFormsSearchClear');
                if (clearBtn) clearBtn.classList.toggle('hidden', !value.trim());
                clearTimeout(timer);
                timer = setTimeout(function () {
                    state.formsQuery = value.trim();
                    applyFormsFilter();
                }, 90);
            });
        }

        const searchClear = $('#fxFormsSearchClear');
        if (searchClear) {
            searchClear.addEventListener('click', function () {
                const searchInput = $('#fxFormsSearchInput');
                if (searchInput) {
                    searchInput.value = '';
                    searchInput.focus();
                }
                state.formsQuery = '';
                searchClear.classList.add('hidden');
                applyFormsFilter();
            });
        }

        const urlSubmit = $('#fxFormsUrlSubmit');
        if (urlSubmit) urlSubmit.addEventListener('click', importFormByUrl);

        const urlInput = $('#fxFormsUrl');
        if (urlInput) {
            urlInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    importFormByUrl();
                }
            });
        }

        const connectBtn = $('#fxFormsConnectBtn');
        if (connectBtn) {
            connectBtn.addEventListener('click', connectGoogleForImport);
        }

        const cancelBtn = $('#fxFormsCancelBtn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', function () {
                const confirmEl = $('#fxFormsConfirm');
                const isConfirmOpen = confirmEl && !confirmEl.hidden;

                if (isConfirmOpen) {
                    state.formsPreview = null;
                    showFormsState('with-integration');
                    renderFormsList();
                } else {
                    closeImportFormsModal();
                }
            });
        }

        const confirmBtn = $('#fxFormsConfirmBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', confirmFormImport);
        }

        const newName = $('#fxFormsNewName');
        if (newName) {
            newName.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    confirmFormImport();
                }
            });
        }
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
        state.selectedVersionId = null;
        state.viewingVersion = null;
        state.editingQuestion = null;
        state.editingTemplateId = null;
        state.editingCategoryId = null;
        state.editingSectionId = null;
        state.options = [];
        state.gridRows = [];
        state.gridColumns = [];
        state.templatesSearch = '';
        state.sectionsSearch = '';
        state.questionsSearch = '';
        state.templatesStatus = 'all';
        state.coverFile = null;
        state.coverPreviewUrl = null;
        state.originalCoverUrl = null;
        state.versions = [];
        state.versionsTemplateId = null;
        state.pendingNewVersionAction = null;
        state.viewerUrl = '';

        versionCache.clear();

        const tSearch = $('#fxTemplatesSearch'); if (tSearch) tSearch.value = '';
        const sSearch = $('#fxSectionsSearch'); if (sSearch) sSearch.value = '';
        const qSearch = $('#fxQuestionsSearch'); if (qSearch) qSearch.value = '';

        bindCreateButtons();
        bindModalClosers();
        bindConfirmModal();
        bindNewVersionPrompt();
        bindImageViewer();
        bindTooltips();
        setupManageCategoriesForm();
        setupTemplateForm();
        setupSectionForm();
        setupCoverPicker();
        renderOptions();
        renderGridEditors();
        showQuestionsListView();
        setColumnView($('#fxTemplates'), 'list');
        setColumnView($('#fxSections'), 'list');
        setColumnView($('#fxQuestions'), 'list');
        closeCatDropdown();
        syncQuestionTypeUI();

        bindImportForms();
        checkGoogleConnectedReturn();

        await Promise.all([loadTemplates(), loadCategories()]);
        renderPreview();
        refreshIcons();
    }

    function unmount() {
        state.mounted = false;
        document.body.style.overflow = '';
        document.body.classList.remove('fx-modal-open');
        closeKebabMenu();
        closeCatDropdown();
        versionCache.clear();
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