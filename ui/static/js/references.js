/* =========================================================================
   REFERENCES — Referências
   ========================================================================= */

(function () {
    'use strict';

    const API = {
        references: '/api/references/',
        referenceDetail: (id) => `/api/references/${id}/`,
        referenceSetCategories: (id) => `/api/references/${id}/categories/`,
        referenceMove: (id) => `/api/references/${id}/move/`,
        referenceAssociateClient: (id) => `/api/references/${id}/associate-client/`,
        referenceAssociateProject: (id) => `/api/references/${id}/associate-project/`,
        referenceVisibility: (id) => `/api/references/${id}/visibility/`,
        referenceDownload: (id) => `/api/references/${id}/download/`,

        folders: '/api/reference-folders/',
        folderDetail: (id) => `/api/reference-folders/${id}/`,
        folderCover: (id) => `/api/reference-folders/${id}/cover/`,
        folderCoverClear: (id) => `/api/reference-folders/${id}/cover/clear/`,

        categories: '/api/reference-categories/',
        categoryDetail: (id) => `/api/reference-categories/${id}/`,

        clients: '/api/clients/',

        driveStatus: '/api/drive/status/',
        driveFiles: '/api/drive/files/',
        driveImport: '/api/drive/import/',
    };

    const state = {
        allReferences: [],
        references: [],
        folders: [],
        categories: [],
        clients: [],
        selectedId: null,
        currentFolderId: null,
        view: 'grid',
        search: '',
        filterCategory: '',
        filterFolder: '',
        selectedIds: new Set(),
        driveFiles: [],
        driveSelected: new Set(),
        driveStatusCache: null,
        folderCoverTargetId: null,
        uploadSelectedCats: new Set(),
        deleteCategoryTargetId: null,
    };

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
            const err = new Error(data?.error || data?.detail || `Erro ${res.status}`);
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

    function formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    function formatDate(iso) {
        if (!iso) return '—';
        try {
            return new Date(iso).toLocaleDateString('pt-BR', {
                day: '2-digit', month: 'short', year: 'numeric',
            });
        } catch { return '—'; }
    }

    function debounce(fn, ms = 250) {
        let t;
        return (...args) => {
            clearTimeout(t);
            t = setTimeout(() => fn(...args), ms);
        };
    }

    function refreshIcons() {
        if (window.lucide && typeof window.lucide.createIcons === 'function') {
            window.lucide.createIcons();
        }
    }

    function openModal(id) {
        const el = document.getElementById(id);
        if (el) el.classList.add('is-open');
    }
    function closeModal(id) {
        const el = document.getElementById(id);
        if (el) el.classList.remove('is-open');
    }
    function setBtnLoading(btn, loading) {
        if (!btn) return;
        btn.classList.toggle('is-loading', loading);
        btn.disabled = loading;
    }
    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
    function withCacheBust(url, v) {
        if (!url) return '';
        if (/cloudinary\.com/i.test(url)) return url;
        if (/[?&](X-Amz-|Signature|Expires|GoogleAccessId)/i.test(url)) return url;
        if (!url.startsWith('/')) return url;
        if (/[?&]v=/.test(url)) return url;
        return url + (url.includes('?') ? '&' : '?') + 'v=' + v;
    }

    function sourceKeyOf(ref) {
        const s = (ref && ref.source) || 'upload';
        if (s === 'gdrive') return 'gdrive';
        if (s === 'pinterest') return 'pinterest';
        if (s === 'url') return 'url';
        return 'upload';
    }
    function sourceLabelOf(ref) {
        switch (sourceKeyOf(ref)) {
            case 'gdrive': return 'Google Drive';
            case 'pinterest': return 'Pinterest';
            case 'url': return 'URL';
            default: return 'Upload';
        }
    }
    function sourceIconSvg(key) {
        switch (key) {
            case 'gdrive':
                return ('<svg viewBox="0 0 87.3 78" xmlns="http://www.w3.org/2000/svg"><path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z" fill="#0066da"/><path d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0 -1.2 4.5h27.5z" fill="#00ac47"/><path d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.502l5.852 11.5z" fill="#ea4335"/><path d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d"/><path d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc"/><path d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00"/></svg>');
            case 'pinterest':
                return ('<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#E60023" d="M12 0C5.373 0 0 5.372 0 12c0 5.084 3.163 9.426 7.627 11.174-.105-.949-.2-2.405.042-3.441.218-.937 1.407-5.965 1.407-5.965s-.359-.719-.359-1.782c0-1.668.967-2.914 2.171-2.914 1.023 0 1.518.769 1.518 1.69 0 1.029-.655 2.568-.994 3.995-.283 1.194.599 2.169 1.777 2.169 2.133 0 3.772-2.249 3.772-5.495 0-2.873-2.064-4.882-5.012-4.882-3.414 0-5.418 2.561-5.418 5.207 0 1.031.397 2.138.893 2.738.098.119.112.224.083.345l-.333 1.36c-.053.22-.174.267-.402.161-1.499-.698-2.436-2.889-2.436-4.649 0-3.785 2.75-7.262 7.929-7.262 4.163 0 7.398 2.967 7.398 6.931 0 4.136-2.607 7.464-6.227 7.464-1.216 0-2.359-.631-2.75-1.378l-.748 2.853c-.271 1.043-1.002 2.35-1.492 3.146C9.57 23.812 10.763 24 12 24c6.627 0 12-5.373 12-12 0-6.628-5.373-12-12-12z"/></svg>');
            case 'url':
                return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>');
            default:
                return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>');
        }
    }
    function sourceColorClass(key) {
        switch (key) {
            case 'gdrive': return 'rf-source-gdrive';
            case 'pinterest': return 'rf-source-pinterest';
            case 'url': return 'rf-source-url';
            default: return 'rf-source-upload';
        }
    }

    /* =====================================================================
       TOASTS
       ===================================================================== */
    function toast(message, opts = {}) {
        const type = opts.type || 'info';
        let stack = document.getElementById('rfToastStack');
        if (!stack) {
            stack = document.createElement('div');
            stack.className = 'rf-toast-stack';
            stack.id = 'rfToastStack';
            document.body.appendChild(stack);
        }
        const el = document.createElement('div');
        el.className = `rf-toast is-${type}`;
        el.textContent = message;
        stack.appendChild(el);
        setTimeout(() => {
            el.classList.add('is-leaving');
            setTimeout(() => el.remove(), 260);
        }, opts.duration || 3000);
    }

    /* =====================================================================
       CATEGORY SELECTOR — reutilizável (painel + modal)
       =====================================================================
       Estrutura esperada no HTML:
         .rf-cat-field
           .rf-cat-chips    ← chips renderizados aqui
           .rf-cat-input    ← input de busca
           .rf-cat-menu     ← dropdown filtrado
    */
    function createCategorySelector({ fieldEl, chipsEl, inputEl, menuEl, getSelectedIds, onToggle }) {
        if (!fieldEl || !chipsEl || !inputEl || !menuEl) return null;

        let currentSelected = new Set();
        let currentExcludeId = null; // para o modal de upload não haver exclusão

        function renderChips() {
            chipsEl.innerHTML = '';
            const ids = Array.from(currentSelected);
            if (!ids.length) {
                chipsEl.innerHTML = '';
                return;
            }
            ids.forEach((id) => {
                const cat = state.categories.find((c) => String(c.id) === String(id));
                if (!cat) return;
                const chip = document.createElement('span');
                chip.className = 'rf-cat-chip';
                if (cat.color) {
                    chip.style.background = cat.color + '1E';
                    chip.style.color = cat.color;
                    chip.style.borderColor = cat.color + '55';
                }
                chip.innerHTML =
                    '<span class="rf-cat-chip-label">' + escapeHtml(cat.name) + '</span>' +
                    '<button type="button" class="rf-cat-chip-remove" aria-label="Remover">' +
                        '<i data-lucide="x"></i>' +
                    '</button>';
                chip.querySelector('.rf-cat-chip-remove').addEventListener('click', (e) => {
                    e.stopPropagation();
                    toggleCategory(String(cat.id));
                });
                chipsEl.appendChild(chip);
            });
            refreshIcons();
        }

        function renderMenu(query = '') {
            const q = (query || '').trim().toLowerCase();
            menuEl.innerHTML = '';

            let candidates = state.categories.slice();
            if (q) candidates = candidates.filter((c) => (c.name || '').toLowerCase().includes(q));
            candidates = candidates.filter((c) => !currentSelected.has(String(c.id)));

            if (!candidates.length) {
                const empty = document.createElement('div');
                empty.className = 'rf-cat-menu-empty';
                empty.textContent = q ? 'Nenhuma categoria encontrada.' : 'Todas as categorias já estão associadas.';
                menuEl.appendChild(empty);
                return;
            }
            candidates.forEach((cat) => {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'rf-cat-menu-item';
                item.innerHTML =
                    '<span class="rf-cat-menu-dot" style="background:' + (cat.color || '#64748B') + '"></span>' +
                    '<span class="rf-cat-menu-name">' + escapeHtml(cat.name) + '</span>';
                item.addEventListener('click', () => {
                    toggleCategory(String(cat.id));
                    inputEl.value = '';
                    renderMenu('');
                });
                menuEl.appendChild(item);
            });
            refreshIcons();
        }

        function toggleCategory(catId) {
            if (currentSelected.has(catId)) currentSelected.delete(catId);
            else currentSelected.add(catId);
            renderChips();
            renderMenu(inputEl.value);
            onToggle && onToggle(Array.from(currentSelected), currentSelected);
        }

        function openMenu() {
            renderMenu(inputEl.value);
            menuEl.classList.remove('hidden');
        }
        function closeMenu() {
            menuEl.classList.add('hidden');
        }

        inputEl.addEventListener('focus', openMenu);
        inputEl.addEventListener('input', () => {
            openMenu();
            renderMenu(inputEl.value);
        });
        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') { closeMenu(); inputEl.blur(); }
            if (e.key === 'Enter') {
                e.preventDefault();
                const first = menuEl.querySelector('.rf-cat-menu-item');
                if (first) first.click();
            }
        });
        document.addEventListener('click', (e) => {
            if (fieldEl.contains(e.target)) return;
            closeMenu();
        });

        return {
            setSelected(ids) {
                currentSelected = new Set((ids || []).map(String));
                renderChips();
                renderMenu('');
            },
            getSelected() { return Array.from(currentSelected); },
            renderChips,
            renderMenu,
        };
    }

    /* =====================================================================
       RENDER — PASTAS
       ===================================================================== */
    function renderFolders() {
        const wrap = $('#rfFolders');
        if (!wrap) return;
        const tpl = $('#rfFolderTpl');
        if (!tpl) return;

        wrap.innerHTML = '';
        const countEl = $('#rfFoldersCount');

        const q = (state.search || '').trim().toLowerCase();
        let visible = state.folders.slice();
        if (q) visible = visible.filter((f) => (f.name || '').toLowerCase().includes(q));

        if (countEl) countEl.textContent = visible.length;

        visible.forEach((f) => {
            const node = tpl.content.cloneNode(true);
            const el = node.querySelector('.rf-folder');
            el.dataset.folderId = f.id;
            el.setAttribute('draggable', 'true');
            el.querySelector('.rf-folder-name').textContent = f.name || 'Sem nome';

            const count = f.reference_count ?? f.references_count ?? f.items_count ?? 0;
            el.querySelector('.rf-folder-count').textContent =
                count === 0 ? 'Vazia' : `${count} ${count === 1 ? 'item' : 'itens'}`;

            const coverEl = el.querySelector('.rf-folder-cover');
            if (f.cover_url && coverEl) {
                coverEl.innerHTML = '';
                const img = document.createElement('img');
                const v = f.updated_at ? new Date(f.updated_at).getTime() : Date.now();
                img.src = withCacheBust(f.cover_url, v);
                img.alt = f.name || '';
                img.loading = 'lazy';
                coverEl.appendChild(img);
            }

            el.querySelector('.rf-folder-main').addEventListener('click', (e) => {
                e.stopPropagation();
                enterFolder(f.id);
            });
            const moreBtn = el.querySelector('.rf-folder-more');
            if (moreBtn) {
                moreBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    openFolderContextMenu(e, f.id);
                });
            }
            el.addEventListener('dragover', (e) => {
                if (e.dataTransfer.types.includes('text/x-reference-id')) {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                    el.classList.add('is-droptarget');
                }
            });
            el.addEventListener('dragleave', (e) => {
                if (el.contains(e.relatedTarget)) return;
                el.classList.remove('is-droptarget');
            });
            el.addEventListener('drop', async (e) => {
                e.preventDefault();
                el.classList.remove('is-droptarget');
                const refId = e.dataTransfer.getData('text/x-reference-id');
                if (!refId) return;
                try {
                    await api(API.referenceMove(refId), {
                        method: 'POST', body: { folder_id: f.id },
                    });
                    const ref = state.allReferences.find((r) => String(r.id) === String(refId));
                    if (ref) {
                        const oldFolder = ref.folder;
                        ref.folder = f.id;
                        ref.folder_name = f.name;
                        if (oldFolder) {
                            const of = state.folders.find((x) => String(x.id) === String(oldFolder));
                            if (of) of.reference_count = Math.max(0, (of.reference_count || 0) - 1);
                        }
                        f.reference_count = (f.reference_count || 0) + 1;
                    }
                    applyFilters();
                    renderFolders();
                    toast('Referência movida.', { type: 'success' });
                } catch (err) {
                    toast(err.message || 'Erro ao mover.', { type: 'error' });
                }
            });
            el.addEventListener('dragstart', (e) => {
                if (e.target.closest('.rf-folder-more')) { e.preventDefault(); return; }
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/x-folder-id', f.id);
                el.classList.add('is-dragging');
            });
            el.addEventListener('dragend', () => el.classList.remove('is-dragging'));
            wrap.appendChild(node);
        });
        refreshIcons();
    }

    /* =====================================================================
       RENDER — CARDS
       ===================================================================== */
    function renderReferences() {
        const grid = $('#rfGrid');
        if (!grid) return;
        const tpl = $('#rfCardTpl');
        grid.innerHTML = '';
        grid.dataset.view = state.view;

        if (!state.references.length) {
            grid.innerHTML = `
                <div class="rf-list-empty">
                    <i data-lucide="image-off"></i>
                    <p>Nenhuma referência encontrada.</p>
                </div>
            `;
            refreshIcons();
            updateCount();
            updateSelectionUI();
            return;
        }

        state.references.forEach((r) => {
            const node = tpl.content.cloneNode(true);
            const card = node.querySelector('.rf-card');
            card.dataset.id = r.id;
            card.setAttribute('draggable', 'true');

            const img = card.querySelector('.rf-card-img');
            const baseImg = r.image_url || r.thumbnail_url || r.file_url || '';
            const v = r.updated_at ? new Date(r.updated_at).getTime() : Date.now();
            img.src = withCacheBust(baseImg, v);
            img.alt = r.title || '';
            img.loading = 'lazy';

            card.querySelector('.rf-card-title').textContent = r.title || 'Sem título';

            // Chips de categoria
            const catsEl = card.querySelector('.rf-card-categories');
            catsEl.innerHTML = '';
            (r.categories || []).slice(0, 4).forEach((c) => {
                const chip = document.createElement('span');
                chip.className = 'rf-chip-mini';
                chip.textContent = c.name;
                if (c.color) {
                    chip.style.background = c.color + '1E';
                    chip.style.color = c.color;
                    chip.style.borderColor = c.color + '55';
                }
                catsEl.appendChild(chip);
            });

            const sourceEl = card.querySelector('.rf-card-source');
            const key = sourceKeyOf(r);
            sourceEl.className = 'rf-card-source ' + sourceColorClass(key);
            sourceEl.innerHTML =
                sourceIconSvg(key) +
                '<span class="rf-card-source-name">' +
                    escapeHtml(sourceLabelOf(r)) +
                '</span>';

            card.querySelector('.rf-card-meta-text').textContent = formatDate(r.created_at);

            const checkbox = card.querySelector('.rf-card-select');
            checkbox.checked = state.selectedIds.has(r.id);
            checkbox.addEventListener('change', (e) => {
                e.stopPropagation();
                if (e.target.checked) state.selectedIds.add(r.id);
                else state.selectedIds.delete(r.id);
                updateSelectionUI();
            });

            card.addEventListener('click', (e) => {
                if (e.target.closest('.rf-check') || e.target.closest('.rf-card-more')) return;
                selectReference(r.id, r);
            });

            card.addEventListener('dragstart', (e) => {
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/x-reference-id', r.id);
                e.dataTransfer.setData('text/plain', r.id);
                card.classList.add('is-dragging');
            });
            card.addEventListener('dragend', () => {
                card.classList.remove('is-dragging');
                $$('.rf-folder.is-droptarget').forEach((el) =>
                    el.classList.remove('is-droptarget')
                );
            });

            card.querySelector('.rf-card-more').addEventListener('click', (e) => {
                e.stopPropagation();
                openContextMenu(e, r.id);
            });

            if (state.selectedId === r.id) card.classList.add('is-active');
            grid.appendChild(node);
        });

        refreshIcons();
        updateCount();
        updateSelectionUI();
    }

    function updateCount() {
        const el = $('#rfCount');
        if (el) el.textContent = state.references.length || 0;
    }

    function updateSelectionUI() {
        const btn = $('#rfDeleteSelectedBtn');
        const count = state.selectedIds.size;
        if (btn) {
            if (count > 0) btn.classList.remove('hidden');
            else btn.classList.add('hidden');
        }
    }

    function getSelectedIds() { return Array.from(state.selectedIds); }

    /* =====================================================================
       DETALHE
       ===================================================================== */
    let detailCatSelector = null;

    async function selectReference(id, hint = null) {
        state.selectedId = id;
        $$('.rf-card').forEach((c) => {
            c.classList.toggle('is-active', String(c.dataset.id) === String(id));
        });
        const cached = state.allReferences.find((r) => String(r.id) === String(id));
        if (cached) renderDetail({ ...cached, ...(hint || {}) });

        try {
            const ref = await api(API.referenceDetail(id));
            if (String(state.selectedId) !== String(id)) return;
            renderDetail(ref);
            const idx = state.allReferences.findIndex((r) => String(r.id) === String(id));
            if (idx !== -1) state.allReferences[idx] = { ...state.allReferences[idx], ...ref };
        } catch (err) {
            console.error('Erro ao carregar referência:', err);
        }
    }

    function renderDetail(ref) {
        const empty = $('#rfDetailEmpty');
        const content = $('#rfDetailContent');
        const footer = $('#rfPanelFooter');
        if (empty) empty.classList.add('hidden');
        if (content) content.classList.remove('hidden');
        if (footer) footer.classList.remove('hidden');

        const img = $('#rfViewerImg');
        if (img) {
            const base = ref.image_url || ref.thumbnail_url || ref.file_url || '';
            const v = ref.updated_at ? new Date(ref.updated_at).getTime() : Date.now();
            img.src = withCacheBust(base, v);
            img.alt = ref.title || '';
        }

        // Chips no topo da imagem
        const chipsEl = $('#rfViewerCategories');
        if (chipsEl) {
            chipsEl.innerHTML = '';
            (ref.categories || []).forEach((c) => {
                const chip = document.createElement('span');
                chip.className = 'rf-chip-cat';
                chip.textContent = c.name;
                chip.style.background = c.color || '#1D4ED8';
                chipsEl.appendChild(chip);
            });
        }

        const name = $('#rfDetailName');
        if (name) name.textContent = ref.title || '—';
        const desc = $('#rfDetailDescription');
        if (desc) desc.textContent = ref.description || '';

        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val || '—';
        };
        set('rfInfoType', ref.file_type_display || '—');
        set('rfInfoSize', ref.image_size_display || (ref.size ? formatBytes(ref.size) : '—'));
        set('rfInfoCreatedAt', formatDate(ref.created_at));
        set('rfInfoCreatedBy', ref.created_by_name);

        const srcEl = $('#rfInfoSource');
        if (srcEl) {
            const key = sourceKeyOf(ref);
            srcEl.innerHTML =
                '<span class="rf-source-icon ' + sourceColorClass(key) + '">' +
                    sourceIconSvg(key) +
                '</span>' +
                '<span>' + escapeHtml(sourceLabelOf(ref)) + '</span>';
        }

        // Categorias — input longo
        if (!detailCatSelector) {
            detailCatSelector = createCategorySelector({
                fieldEl: $('#rfCatField'),
                chipsEl: $('#rfCatChips'),
                inputEl: $('#rfCatInput'),
                menuEl: $('#rfCatMenu'),
                onToggle: onDetailCatToggle,
            });
        }
        if (detailCatSelector) {
            detailCatSelector.setSelected((ref.categories || []).map((c) => c.id));
        }

        const clientSelect = $('#rfAssociateClientSelect');
        if (clientSelect) clientSelect.value = ref.client ? String(ref.client) : '';
        const folderSelect = $('#rfAssociateFolderSelect');
        if (folderSelect) folderSelect.value = ref.folder ? String(ref.folder) : '';

        const visible = $('#rfVisibleToClient');
        if (visible) visible.checked = !!ref.visible_to_client;
        const hint = $('#rfVisibilityHint');
        if (hint) {
            hint.textContent = ref.visible_to_client
                ? 'O cliente também vê esta referência.'
                : 'Somente o escritório vê esta referência.';
        }

        refreshIcons();
    }

    /* =====================================================================
       CATEGORIA DO DETALHE — toggle otimista
       ===================================================================== */
    let catSaveAbort = null;
    async function onDetailCatToggle(newIds) {
        if (!state.selectedId) return;

        // Atualização otimista
        const ref = state.allReferences.find((r) => String(r.id) === String(state.selectedId));
        if (ref) {
            ref.categories = newIds.map((id) => {
                const cat = state.categories.find((c) => String(c.id) === String(id));
                return cat ? { id: cat.id, name: cat.name, slug: cat.slug, color: cat.color } : null;
            }).filter(Boolean);
        }
        renderViewerChipsFromList(ref ? ref.categories : []);
        applyFilters();

        // Debounce para salvar
        if (catSaveAbort) catSaveAbort.abort();
        catSaveAbort = new AbortController();
        const signal = catSaveAbort.signal;
        try {
            await new Promise((res) => setTimeout(res, 220));
            if (signal.aborted) return;
            const updated = await api(API.referenceSetCategories(state.selectedId), {
                method: 'POST',
                body: { category_ids: newIds },
                headers: {},
            });
            const idx = state.allReferences.findIndex(
                (r) => String(r.id) === String(state.selectedId)
            );
            if (idx !== -1) state.allReferences[idx] = { ...state.allReferences[idx], ...updated };
        } catch (err) {
            if (err && err.name === 'AbortError') return;
            toast(err.message || 'Erro ao salvar categorias.', { type: 'error' });
        }
    }

    function renderViewerChipsFromList(cats) {
        const chipsEl = $('#rfViewerCategories');
        if (!chipsEl) return;
        chipsEl.innerHTML = '';
        (cats || []).forEach((c) => {
            const chip = document.createElement('span');
            chip.className = 'rf-chip-cat';
            chip.textContent = c.name;
            chip.style.background = c.color || '#1D4ED8';
            chipsEl.appendChild(chip);
        });
    }

    /* =====================================================================
       LOAD
       ===================================================================== */
    async function loadReferences() {
        try {
            const data = await api(API.references);
            state.allReferences = pickArray(data, 'results');
            applyFilters();
        } catch (err) {
            console.error('Erro ao carregar referências:', err);
            state.allReferences = [];
            state.references = [];
            renderReferences();
        }
    }

    function applyFilters() {
        let list = state.allReferences.slice();

        if (state.currentFolderId) {
            list = list.filter((r) => String(r.folder) === String(state.currentFolderId));
        } else if (state.filterFolder === 'none') {
            list = list.filter((r) => !r.folder);
        } else if (state.filterFolder) {
            list = list.filter((r) => String(r.folder) === String(state.filterFolder));
        }
        if (state.filterCategory) {
            list = list.filter((r) =>
                (r.categories || []).some((c) => String(c.id) === String(state.filterCategory))
            );
        }
        if (state.search) {
            const q = state.search.toLowerCase();
            list = list.filter((r) => {
                const cats = (r.categories || []).map((c) => c.name).join(' ');
                const haystack = [
                    r.title, r.description, r.client_name, r.folder_name,
                    cats, r.source_display, r.source_url,
                ].filter(Boolean).join(' ').toLowerCase();
                return haystack.includes(q);
            });
        }

        list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        state.references = list;
        renderReferences();
        renderFolders();
    }

    async function loadFolders() {
        try {
            const data = await api(`${API.folders}?flat=1`);
            state.folders = pickArray(data, 'folders');
            renderFolders();
            populateFoldersSelects();
        } catch (err) {
            console.error('Erro ao carregar pastas:', err);
            state.folders = [];
            renderFolders();
        }
    }

    async function loadCategories() {
        try {
            const data = await api(`${API.categories}?flat=1`);
            state.categories = pickArray(data, 'categories');
            populateCategories();
            renderCategoriesModal();
            if (state.selectedId) {
                const ref = state.allReferences.find((r) => String(r.id) === String(state.selectedId));
                if (ref && detailCatSelector) {
                    detailCatSelector.setSelected((ref.categories || []).map((c) => c.id));
                }
            }
        } catch (err) {
            console.error('Erro ao carregar categorias:', err);
            state.categories = [];
            populateCategories();
            renderCategoriesModal();
        }
    }

    async function loadClients() {
        try {
            const data = await api(`${API.clients}?page_size=500`);
            state.clients = pickArray(data, 'results');
            populateClients();
        } catch (err) {
            state.clients = [];
            populateClients();
        }
    }

    /* =====================================================================
       SELECTS
       ===================================================================== */
    function populateCategories() {
        const el = $('#rfFilterCategory');
        if (!el) return;
        const current = el.value;
        const first = el.options[0];
        el.innerHTML = '';
        el.appendChild(first);
        state.categories.forEach((c) => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name;
            el.appendChild(opt);
        });
        el.value = current;
    }
    function populateFoldersSelects() {
        const selects = ['#rfFilterFolder', '#rfUploadFolder', '#rfAssociateFolderSelect'];
        selects.forEach((selId) => {
            const el = $(selId);
            if (!el) return;
            const current = el.value;
            const first = el.options[0];
            const second = el.options[1];
            el.innerHTML = '';
            el.appendChild(first);
            if (selId === '#rfFilterFolder' && second) el.appendChild(second);
            state.folders.forEach((f) => {
                const opt = document.createElement('option');
                opt.value = f.id;
                opt.textContent = f.name || '';
                el.appendChild(opt);
            });
            el.value = current;
        });
    }
    function populateClients() {
        const el = $('#rfAssociateClientSelect');
        if (!el) return;
        const current = el.value;
        const first = el.options[0];
        el.innerHTML = '';
        el.appendChild(first);
        state.clients.forEach((c) => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name || c.nome || '';
            el.appendChild(opt);
        });
        el.value = current;
    }

    /* =====================================================================
       NAV
       ===================================================================== */
    function enterFolder(folderId) {
        state.currentFolderId = folderId;
        state.filterFolder = '';
        const folder = state.folders.find((f) => String(f.id) === String(folderId));
        const bc = $('#rfBreadcrumb');
        const bcName = $('#rfBreadcrumbName');
        if (bc && bcName) {
            bcName.textContent = folder ? folder.name : 'Pasta';
            bc.classList.remove('hidden');
        }
        const title = $('#rfSectionTitle');
        if (title) title.textContent = folder ? folder.name : 'Referências';
        applyFilters();
    }
    function exitFolder() {
        state.currentFolderId = null;
        const bc = $('#rfBreadcrumb');
        if (bc) bc.classList.add('hidden');
        const title = $('#rfSectionTitle');
        if (title) title.textContent = 'Todas as referências';
        applyFilters();
    }

    /* =====================================================================
       CTX MENUS
       ===================================================================== */
    let ctxTargetId = null;
    let folderCtxTargetId = null;

    function openContextMenu(evt, id) {
        ctxTargetId = id;
        const menu = $('#rfCtxMenu');
        if (!menu) return;
        const fm = $('#rfFolderCtxMenu');
        if (fm) fm.classList.add('hidden');
        menu.classList.remove('hidden');
        const rect = menu.getBoundingClientRect();
        const x = Math.min(evt.clientX, window.innerWidth - rect.width - 8);
        const y = Math.min(evt.clientY, window.innerHeight - rect.height - 8);
        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;
    }
    function closeContextMenu() {
        const menu = $('#rfCtxMenu');
        if (menu) menu.classList.add('hidden');
    }
    function openFolderContextMenu(evt, folderId) {
        folderCtxTargetId = folderId;
        const menu = $('#rfFolderCtxMenu');
        if (!menu) return;
        const folder = state.folders.find((f) => String(f.id) === String(folderId));
        const clearBtn = menu.querySelector('[data-folder-action="clear-cover"]');
        if (clearBtn) clearBtn.style.display = (folder && folder.cover_url) ? '' : 'none';
        closeContextMenu();
        menu.classList.remove('hidden');
        const rect = menu.getBoundingClientRect();
        const x = Math.min(evt.clientX, window.innerWidth - rect.width - 8);
        const y = Math.min(evt.clientY, window.innerHeight - rect.height - 8);
        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;
    }
    function closeFolderContextMenu() {
        const menu = $('#rfFolderCtxMenu');
        if (menu) menu.classList.add('hidden');
        folderCtxTargetId = null;
    }

    /* =====================================================================
       UPLOAD
       ===================================================================== */
    let uploadCatSelector = null;
    function validateImageFile(file) {
        if (!file) return false;
        const name = (file.name || '').toLowerCase();
        const ok = /\.(jpe?g|jfif|png|webp|gif)$/i.test(name);
        if (!ok) {
            toast('Formato inválido. Envie uma imagem JPG, JPEG, JFIF, PNG, WEBP ou GIF.', { type: 'warning' });
        }
        return ok;
    }

    function ensureUploadCatSelector() {
        if (uploadCatSelector) return uploadCatSelector;
        uploadCatSelector = createCategorySelector({
            fieldEl: $('#rfUploadCatField'),
            chipsEl: $('#rfUploadCatChips'),
            inputEl: $('#rfUploadCatInput'),
            menuEl: $('#rfUploadCatMenu'),
            onToggle: (ids) => {
                state.uploadSelectedCats = new Set(ids);
            },
        });
        return uploadCatSelector;
    }

    async function submitUpload(e) {
        e.preventDefault();
        const file = $('#rfUploadFile')?.files?.[0];
        const title = $('#rfUploadTitle')?.value?.trim();
        if (!file || !title) return;
        if (!validateImageFile(file)) return;

        const btn = $('#rfUploadSubmitBtn');
        setBtnLoading(btn, true);
        try {
            const fd = new FormData();
            fd.append('image', file);
            fd.append('title', title);
            const description = $('#rfUploadDescription')?.value?.trim();
            if (description) fd.append('description', description);
            state.uploadSelectedCats.forEach((cid) => fd.append('category_ids', cid));
            const folder = $('#rfUploadFolder')?.value;
            if (folder) fd.append('folder_id', folder);
            const visible = $('#rfUploadVisibleToClient')?.checked;
            fd.append('visible_to_client', visible ? 'true' : 'false');

            await api(API.references, { method: 'POST', body: fd });

            closeModal('rfUploadModal');
            resetUploadForm();
            toast('Referência adicionada.', { type: 'success' });
            await Promise.all([loadReferences(), loadFolders()]);
        } catch (err) {
            console.error('Erro no upload:', err);
            toast(err.message || 'Erro ao enviar referência.', { type: 'error' });
        } finally {
            setBtnLoading(btn, false);
        }
    }

    function resetUploadForm() {
        const form = $('#rfUploadForm');
        if (form) form.reset();
        state.uploadSelectedCats = new Set();
        if (uploadCatSelector) uploadCatSelector.setSelected([]);
        const dz = $('#rfDropzone');
        if (dz) dz.classList.remove('is-filled');
        const t = $('#rfDropzoneTitle');
        if (t) t.textContent = 'Arraste uma imagem aqui';
        const s = $('#rfDropzoneSub');
        if (s) s.textContent = 'JPG, JPEG, JFIF, PNG, WEBP ou GIF';
    }

    /* =====================================================================
       FOLDERS CRUD
       ===================================================================== */
    let editingFolderId = null;

    function openNewFolderModal() {
        editingFolderId = null;
        const titleEl = $('#rfNewFolderTitle');
        const submitLabel = $('#rfNewFolderSubmitBtn .rf-btn-label');
        const input = $('#rfNewFolderName');
        if (titleEl) titleEl.textContent = 'Nova pasta';
        if (submitLabel) submitLabel.textContent = 'Criar pasta';
        if (input) input.value = '';
        openModal('rfNewFolderModal');
        setTimeout(() => input?.focus(), 100);
    }
    function openEditFolderModal(folderId) {
        const folder = state.folders.find((f) => String(f.id) === String(folderId));
        if (!folder) return;
        editingFolderId = folderId;
        const titleEl = $('#rfNewFolderTitle');
        const submitLabel = $('#rfNewFolderSubmitBtn .rf-btn-label');
        const input = $('#rfNewFolderName');
        if (titleEl) titleEl.textContent = 'Renomear pasta';
        if (submitLabel) submitLabel.textContent = 'Salvar';
        if (input) input.value = folder.name || '';
        openModal('rfNewFolderModal');
        setTimeout(() => { if (input) { input.focus(); input.select(); } }, 100);
    }
    async function submitNewFolder(e) {
        e.preventDefault();
        const input = $('#rfNewFolderName');
        const name = input?.value?.trim();
        if (!name) return;
        const btn = $('#rfNewFolderSubmitBtn');
        setBtnLoading(btn, true);
        try {
            if (editingFolderId) {
                const updated = await api(API.folderDetail(editingFolderId), {
                    method: 'PATCH', body: { name },
                });
                const idx = state.folders.findIndex((f) => String(f.id) === String(editingFolderId));
                if (idx !== -1) state.folders[idx] = updated;
                toast('Pasta renomeada.', { type: 'success' });
            } else {
                const created = await api(API.folders, { method: 'POST', body: { name } });
                state.folders.push(created);
                state.folders.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
                toast('Pasta criada.', { type: 'success' });
            }
            closeModal('rfNewFolderModal');
            const form = $('#rfNewFolderForm');
            if (form) form.reset();
            editingFolderId = null;
            renderFolders();
            populateFoldersSelects();
        } catch (err) {
            console.error('Erro ao salvar pasta:', err);
            toast(err.message || 'Erro ao salvar pasta.', { type: 'error' });
        } finally {
            setBtnLoading(btn, false);
        }
    }

    function openFolderCoverModal(folderId) {
        const folder = state.folders.find((f) => String(f.id) === String(folderId));
        if (!folder) return;
        state.folderCoverTargetId = folderId;
        const titleEl = $('#rfFolderCoverTitle');
        if (titleEl) titleEl.textContent = folder.cover_url ? 'Trocar capa da pasta' : 'Definir capa da pasta';
        const form = $('#rfFolderCoverForm');
        if (form) form.reset();
        const dz = $('#rfFolderCoverDropzone');
        if (dz) dz.classList.remove('is-filled');
        const title2 = $('#rfFolderCoverTitle2');
        if (title2) title2.textContent = 'Escolher imagem de capa';
        const sub = $('#rfFolderCoverSub');
        if (sub) sub.textContent = 'JPG, PNG, WEBP ou GIF';
        openModal('rfFolderCoverModal');
        refreshIcons();
    }
    async function submitFolderCover(e) {
        e.preventDefault();
        if (!state.folderCoverTargetId) return;
        const file = $('#rfFolderCoverFile')?.files?.[0];
        if (!file) return;
        if (!validateImageFile(file)) return;
        const btn = $('#rfFolderCoverSubmitBtn');
        setBtnLoading(btn, true);
        try {
            const fd = new FormData();
            fd.append('cover', file);
            const updated = await api(API.folderCover(state.folderCoverTargetId), {
                method: 'POST', body: fd,
            });
            const idx = state.folders.findIndex((f) => String(f.id) === String(state.folderCoverTargetId));
            if (idx !== -1) state.folders[idx] = updated;
            toast('Capa atualizada.', { type: 'success' });
            closeModal('rfFolderCoverModal');
            state.folderCoverTargetId = null;
            renderFolders();
        } catch (err) {
            console.error('Erro ao salvar capa:', err);
            toast(err.message || 'Erro ao salvar capa.', { type: 'error' });
        } finally {
            setBtnLoading(btn, false);
        }
    }
    async function clearFolderCover(folderId) {
        try {
            const updated = await api(API.folderCoverClear(folderId), { method: 'DELETE' });
            const idx = state.folders.findIndex((f) => String(f.id) === String(folderId));
            if (idx !== -1) state.folders[idx] = updated;
            toast('Capa removida.', { type: 'success' });
            renderFolders();
        } catch (err) {
            console.error('Erro ao remover capa:', err);
            toast(err.message || 'Erro ao remover capa.', { type: 'error' });
        }
    }

    let pendingDeleteFolderId = null;
    function openDeleteFolderModal(folderId) {
        const folder = state.folders.find((f) => String(f.id) === String(folderId));
        if (!folder) return;
        pendingDeleteFolderId = folderId;
        const nameEl = $('#rfDeleteFolderName');
        if (nameEl) nameEl.textContent = folder.name;
        openModal('rfDeleteFolderModal');
        refreshIcons();
    }
    function setupDeleteFolderModal() {
        const btn = $('#rfDeleteFolderConfirmBtn');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            if (!pendingDeleteFolderId) return;
            setBtnLoading(btn, true);
            try {
                await api(API.folderDetail(pendingDeleteFolderId), { method: 'DELETE' });
                state.folders = state.folders.filter((f) => String(f.id) !== String(pendingDeleteFolderId));
                toast('Pasta excluída.', { type: 'success' });
                closeModal('rfDeleteFolderModal');
                pendingDeleteFolderId = null;
                renderFolders();
                populateFoldersSelects();
                applyFilters();
            } catch (err) {
                toast(err.message || 'Erro ao excluir pasta.', { type: 'error' });
            } finally {
                setBtnLoading(btn, false);
            }
        });
    }

    /* =====================================================================
       CATEGORIES — modal
       ===================================================================== */
    function renderCategoriesModal() {
        const wrap = $('#rfCatList');
        if (!wrap) return;
        if (!state.categories.length) {
            wrap.innerHTML = '<p class="rf-cat-empty">Nenhuma categoria.</p>';
            return;
        }
        wrap.innerHTML = '';
        state.categories.forEach((cat) => {
            const item = document.createElement('div');
            item.className = 'rf-cat-item';
            item.dataset.id = cat.id;

            const badge = cat.is_system
                ? '<span class="rf-cat-item-badge">Sistema</span>' : '';
            const count = cat.reference_count ?? 0;

            item.innerHTML = `
                <span class="rf-cat-item-color" style="background:${cat.color || '#64748B'}"></span>
                <span class="rf-cat-item-name">${escapeHtml(cat.name)}</span>
                ${badge}
                <span class="rf-cat-item-count">${count}</span>
                <div class="rf-cat-item-actions">
                    <button class="rf-cat-item-action" data-action="rename" title="Renomear" type="button">
                        <i data-lucide="pencil"></i>
                    </button>
                    <button class="rf-cat-item-action is-danger" data-action="delete" title="Excluir" type="button" ${cat.is_system ? 'disabled' : ''}>
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
            `;
            item.querySelector('[data-action="rename"]').addEventListener('click', () => {
                startCategoryRename(item, cat);
            });
            if (!cat.is_system) {
                item.querySelector('[data-action="delete"]').addEventListener('click', () => {
                    openDeleteCategoryModal(cat);
                });
            }
            wrap.appendChild(item);
        });
        refreshIcons();
    }

    function startCategoryRename(item, cat) {
        const nameEl = item.querySelector('.rf-cat-item-name');
        if (!nameEl) return;
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'rf-cat-item-name-input';
        input.value = cat.name;
        input.maxLength = 60;
        nameEl.replaceWith(input);
        input.focus();
        input.select();

        const commit = async () => {
            const newName = input.value.trim();
            if (!newName || newName === cat.name) {
                renderCategoriesModal();
                return;
            }
            try {
                const updated = await api(API.categoryDetail(cat.id), {
                    method: 'PATCH', body: { name: newName },
                });
                const idx = state.categories.findIndex((c) => String(c.id) === String(cat.id));
                if (idx !== -1) state.categories[idx] = updated;
                toast('Categoria renomeada.', { type: 'success' });
                renderCategoriesModal();
                populateCategories();
                applyFilters();
            } catch (err) {
                toast(err.message || 'Erro ao renomear.', { type: 'error' });
                renderCategoriesModal();
            }
        };
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            else if (e.key === 'Escape') {
                input.removeEventListener('blur', commit);
                renderCategoriesModal();
            }
        });
    }

    function openDeleteCategoryModal(cat) {
        state.deleteCategoryTargetId = cat.id;
        const nameEl = $('#rfDeleteCategoryName');
        if (nameEl) nameEl.textContent = cat.name;
        openModal('rfDeleteCategoryModal');
        refreshIcons();
    }
    function setupDeleteCategoryModal() {
        const btn = $('#rfDeleteCategoryConfirmBtn');
        if (!btn) return;
        btn.addEventListener('click', async () => {
            if (!state.deleteCategoryTargetId) return;
            setBtnLoading(btn, true);
            try {
                await api(API.categoryDetail(state.deleteCategoryTargetId), { method: 'DELETE' });
                state.categories = state.categories.filter(
                    (c) => String(c.id) !== String(state.deleteCategoryTargetId)
                );
                // remove das referências locais
                state.allReferences.forEach((r) => {
                    r.categories = (r.categories || []).filter(
                        (c) => String(c.id) !== String(state.deleteCategoryTargetId)
                    );
                });
                toast('Categoria excluída.', { type: 'success' });
                closeModal('rfDeleteCategoryModal');
                state.deleteCategoryTargetId = null;
                renderCategoriesModal();
                populateCategories();
                applyFilters();
                if (state.selectedId) selectReference(state.selectedId);
            } catch (err) {
                toast(err.message || 'Erro ao excluir.', { type: 'error' });
            } finally {
                setBtnLoading(btn, false);
            }
        });
    }

    async function submitNewCategory(e) {
        e.preventDefault();
        const input = $('#rfNewCategoryName');
        const name = input?.value?.trim();
        if (!name) return;
        const btn = $('#rfNewCategorySubmitBtn');
        setBtnLoading(btn, true);
        try {
            const created = await api(API.categories, { method: 'POST', body: { name } });
            state.categories.push(created);
            input.value = '';
            toast('Categoria criada.', { type: 'success' });
            renderCategoriesModal();
            populateCategories();
            if (detailCatSelector && state.selectedId) {
                const ref = state.allReferences.find((r) => String(r.id) === String(state.selectedId));
                if (ref) detailCatSelector.setSelected((ref.categories || []).map((c) => c.id));
            }
        } catch (err) {
            toast(err.message || 'Erro ao criar categoria.', { type: 'error' });
        } finally {
            setBtnLoading(btn, false);
        }
    }

    /* =====================================================================
       DELETE REFERENCE
       ===================================================================== */
    let deleteTargetId = null;
    function openDeleteModal(id) {
        deleteTargetId = id;
        const ref = state.references.find((r) => String(r.id) === String(id));
        const nameEl = $('#rfDeleteFileName');
        if (nameEl) nameEl.textContent = ref?.title || '—';
        openModal('rfDeleteModal');
        refreshIcons();
    }
    async function confirmDelete() {
        if (!deleteTargetId) return;
        const btn = $('#rfDeleteConfirmBtn');
        setBtnLoading(btn, true);
        try {
            const id = deleteTargetId;
            await api(API.referenceDetail(id), { method: 'DELETE' });
            state.selectedIds.delete(id);
            state.allReferences = state.allReferences.filter((r) => String(r.id) !== String(id));
            if (String(state.selectedId) === String(id)) {
                state.selectedId = null;
                const empty = $('#rfDetailEmpty');
                const content = $('#rfDetailContent');
                const footer = $('#rfPanelFooter');
                if (empty) empty.classList.remove('hidden');
                if (content) content.classList.add('hidden');
                if (footer) footer.classList.add('hidden');
            }
            closeModal('rfDeleteModal');
            deleteTargetId = null;
            applyFilters();
            updateSelectionUI();
            toast('Referência excluída.', { type: 'success' });
        } catch (err) {
            console.error('Erro ao excluir:', err);
            toast(err.message || 'Erro ao excluir.', { type: 'error' });
        } finally {
            setBtnLoading(btn, false);
        }
    }
    function confirmDeleteSelected() {
        const ids = getSelectedIds();
        if (!ids.length) return;
        if (ids.length === 1) openDeleteModal(ids[0]);
        else deleteMultiple(ids);
    }
    async function deleteMultiple(ids) {
        const btn = $('#rfDeleteSelectedBtn');
        setBtnLoading(btn, true);
        try {
            await Promise.all(ids.map((id) => api(API.referenceDetail(id), { method: 'DELETE' })));
            ids.forEach((id) => {
                state.selectedIds.delete(id);
                state.allReferences = state.allReferences.filter((r) => String(r.id) !== String(id));
            });
            if (ids.includes(String(state.selectedId))) {
                state.selectedId = null;
                const empty = $('#rfDetailEmpty');
                const content = $('#rfDetailContent');
                const footer = $('#rfPanelFooter');
                if (empty) empty.classList.remove('hidden');
                if (content) content.classList.add('hidden');
                if (footer) footer.classList.add('hidden');
            }
            applyFilters();
            updateSelectionUI();
            toast(`${ids.length} referências excluídas.`, { type: 'success' });
        } catch (err) {
            toast(err.message || 'Erro ao excluir.', { type: 'error' });
            await loadReferences();
        } finally {
            setBtnLoading(btn, false);
        }
    }

    /* =====================================================================
       INLINE RENAME / DESC
       ===================================================================== */
    function startRename() {
        const nameEl = $('#rfDetailName');
        const input = $('#rfNameInput');
        if (!nameEl || !input) return;
        input.value = nameEl.textContent === '—' ? '' : nameEl.textContent;
        nameEl.classList.add('hidden');
        input.classList.remove('hidden');
        input.focus();
        input.select();
    }
    function cancelRename() {
        const nameEl = $('#rfDetailName');
        const input = $('#rfNameInput');
        if (!nameEl || !input) return;
        input.classList.add('hidden');
        nameEl.classList.remove('hidden');
    }
    async function commitRename() {
        const input = $('#rfNameInput');
        const nameEl = $('#rfDetailName');
        if (!input || !nameEl) return;
        const newName = input.value.trim();
        if (!newName || newName === nameEl.textContent) { cancelRename(); return; }
        try {
            const updated = await api(API.referenceDetail(state.selectedId), {
                method: 'PATCH', body: { title: newName },
            });
            nameEl.textContent = newName;
            cancelRename();
            const idx = state.allReferences.findIndex((r) => String(r.id) === String(state.selectedId));
            if (idx !== -1) state.allReferences[idx] = { ...state.allReferences[idx], ...updated };
            applyFilters();
        } catch (err) {
            console.error('Erro ao renomear:', err);
            cancelRename();
        }
    }
    function startDescEdit() {
        const descEl = $('#rfDetailDescription');
        const input = $('#rfDescInput');
        if (!descEl || !input) return;
        input.value = descEl.textContent || '';
        descEl.classList.add('hidden');
        input.classList.remove('hidden');
        input.focus();
    }
    function cancelDescEdit() {
        const descEl = $('#rfDetailDescription');
        const input = $('#rfDescInput');
        if (!descEl || !input) return;
        input.classList.add('hidden');
        descEl.classList.remove('hidden');
    }
    async function commitDescEdit() {
        const input = $('#rfDescInput');
        const descEl = $('#rfDetailDescription');
        if (!input || !descEl) return;
        const newDesc = input.value.trim();
        const oldDesc = descEl.textContent || '';
        if (newDesc === oldDesc) { cancelDescEdit(); return; }
        try {
            const updated = await api(API.referenceDetail(state.selectedId), {
                method: 'PATCH', body: { description: newDesc },
            });
            descEl.textContent = newDesc;
            cancelDescEdit();
            const idx = state.allReferences.findIndex((r) => String(r.id) === String(state.selectedId));
            if (idx !== -1) state.allReferences[idx] = { ...state.allReferences[idx], ...updated };
            applyFilters();
            toast('Descrição atualizada.', { type: 'success' });
        } catch (err) {
            toast(err.message || 'Erro ao salvar descrição.', { type: 'error' });
            cancelDescEdit();
        }
    }

    /* =====================================================================
       ASSOCIAÇÕES
       ===================================================================== */
    async function changeClient(e) {
        if (!state.selectedId) return;
        const clientId = e.target.value;
        try {
            const updated = await api(API.referenceAssociateClient(state.selectedId), {
                method: 'POST', body: { client_id: clientId || null },
            });
            const idx = state.allReferences.findIndex((r) => String(r.id) === String(state.selectedId));
            if (idx !== -1) state.allReferences[idx] = { ...state.allReferences[idx], ...updated };
            applyFilters();
            selectReference(state.selectedId);
        } catch (err) {
            toast(err.message || 'Erro ao associar cliente.', { type: 'error' });
        }
    }
    async function changeFolder(e) {
        if (!state.selectedId) return;
        const folderId = e.target.value;
        try {
            const updated = await api(API.referenceMove(state.selectedId), {
                method: 'POST', body: { folder_id: folderId || null },
            });
            const idx = state.allReferences.findIndex((r) => String(r.id) === String(state.selectedId));
            if (idx !== -1) state.allReferences[idx] = { ...state.allReferences[idx], ...updated };
            applyFilters();
            renderFolders();
            selectReference(state.selectedId);
        } catch (err) {
            toast(err.message || 'Erro ao mover para pasta.', { type: 'error' });
        }
    }
    async function changeVisibility(e) {
        if (!state.selectedId) return;
        const visible = e.target.checked;
        const hint = $('#rfVisibilityHint');
        if (hint) {
            hint.textContent = visible
                ? 'O cliente também vê esta referência.'
                : 'Somente o escritório vê esta referência.';
        }
        try {
            const updated = await api(API.referenceVisibility(state.selectedId), {
                method: 'POST', body: { visible_to_client: visible },
            });
            const idx = state.allReferences.findIndex((r) => String(r.id) === String(state.selectedId));
            if (idx !== -1) state.allReferences[idx] = { ...state.allReferences[idx], ...updated };
        } catch (err) {
            toast(err.message || 'Erro ao alterar visibilidade.', { type: 'error' });
            e.target.checked = !visible;
            if (hint) {
                hint.textContent = !visible
                    ? 'O cliente também vê esta referência.'
                    : 'Somente o escritório vê esta referência.';
            }
        }
    }

    function downloadReference(id) {
        const targetId = id || state.selectedId;
        if (!targetId) return;
        window.location.href = API.referenceDownload(targetId);
    }

    /* =====================================================================
       GOOGLE DRIVE
       ===================================================================== */
    function setDriveError(message) {
        const errEl = $('#rfDriveError');
        const errText = $('#rfDriveErrorText');
        const actions = $('#rfDriveErrorActions');
        if (!errEl || !errText) return;
        if (!message) {
            errEl.classList.add('hidden');
            if (actions) { actions.style.display = 'none'; actions.innerHTML = ''; }
            return;
        }
        errText.textContent = message;
        if (actions) { actions.style.display = 'none'; actions.innerHTML = ''; }
        errEl.classList.remove('hidden');
    }
    function setDriveReconnectAction() {
        const actions = $('#rfDriveErrorActions');
        if (!actions) return;
        actions.innerHTML =
            '<a class="btn-apple btn-apple-primary" ' +
            'href="/accounts/google/login/?process=login&next=/references/&prompt=consent" ' +
            'style="text-decoration:none;margin-top:10px;display:inline-flex;">Reconectar conta Google</a>';
        actions.style.display = 'block';
    }
    function showDriveState(which) {
        const intro = $('#rfDriveIntro');
        const connected = $('#rfDriveConnected');
        const loading = $('#rfDriveLoading');
        if (intro) intro.style.display = which === 'intro' ? 'flex' : 'none';
        if (connected) connected.style.display = which === 'connected' ? 'flex' : 'none';
        if (loading) loading.style.display = which === 'loading' ? 'flex' : 'none';
    }
    function setDriveButtonLoading(isLoading) {
        const btn = $('#rfDriveBtn');
        if (!btn) return;
        if (isLoading) { btn.classList.add('is-loading'); btn.disabled = true; }
        else { btn.classList.remove('is-loading'); btn.disabled = false; }
    }

    async function openDriveModal() {
        state.driveSelected.clear();
        updateDriveSummary();
        setDriveError('');
        const introEl = $('#rfDriveIntro');
        const connectedEl = $('#rfDriveConnected');
        const loadingEl = $('#rfDriveLoading');
        if (!introEl || !connectedEl || !loadingEl) return;

        openModal('rfDriveModal');
        showDriveState('loading');
        setDriveButtonLoading(true);

        try {
            let status = state.driveStatusCache;
            if (!status) {
                status = await api(API.driveStatus);
                state.driveStatusCache = status;
            }
            const connected = !!(status && status.connected);
            const needsReconnect = !!(status && status.needs_reconnect);

            if (needsReconnect) {
                showDriveState('intro');
                setDriveError(
                    'Sua conexão com o Google está incompleta. ' +
                    'Reconecte sua conta Google para permitir que o Clivo acesse seu Drive.'
                );
                setDriveReconnectAction();
                return;
            }
            if (!connected) { showDriveState('intro'); return; }

            showDriveState('connected');
            const filesEl = $('#rfDriveFiles');
            if (filesEl) filesEl.innerHTML = '<p class="rf-drive-empty">Carregando…</p>';
            await loadDriveFiles('');
        } catch (err) {
            showDriveState('intro');
        } finally {
            setDriveButtonLoading(false);
        }
    }

    async function loadDriveFiles(query = '') {
        const wrap = $('#rfDriveFiles');
        if (!wrap) return;
        wrap.innerHTML = '<p class="rf-drive-empty">Carregando…</p>';
        try {
            const url = API.driveFiles + (query ? `?q=${encodeURIComponent(query)}` : '');
            const data = await api(url);
            state.driveFiles = (data && data.files) || [];
            renderDriveFiles();
        } catch (err) {
            setDriveError(err.message || 'Erro ao carregar arquivos do Drive.');
            wrap.innerHTML = '<p class="rf-drive-empty">—</p>';
        }
    }
    function renderDriveFiles() {
        const wrap = $('#rfDriveFiles');
        if (!wrap) return;
        wrap.innerHTML = '';
        if (!state.driveFiles.length) {
            wrap.innerHTML = '<p class="rf-drive-empty">Nenhum arquivo encontrado.</p>';
            return;
        }
        state.driveFiles.forEach((f) => {
            const row = document.createElement('div');
            row.className = 'rf-drive-file';
            if (state.driveSelected.has(f.id)) row.classList.add('is-selected');
            const size = f.size ? formatBytes(parseInt(f.size, 10)) : '';
            const meta = [size, f.mimeType || ''].filter(Boolean).join(' · ');
            row.innerHTML = `
                <span class="rf-drive-file-check"><i data-lucide="check"></i></span>
                <span class="rf-drive-file-icon"><i data-lucide="file-image"></i></span>
                <span class="rf-drive-file-info">
                    <span class="rf-drive-file-name">${escapeHtml(f.name)}</span>
                    <span class="rf-drive-file-meta">${escapeHtml(meta)}</span>
                </span>
            `;
            row.addEventListener('click', () => {
                if (state.driveSelected.has(f.id)) state.driveSelected.delete(f.id);
                else state.driveSelected.add(f.id);
                row.classList.toggle('is-selected');
                updateDriveSummary();
            });
            wrap.appendChild(row);
        });
        refreshIcons();
        updateDriveSummary();
    }
    function updateDriveSummary() {
        const count = $('#rfDriveSelectedCount');
        const btn = $('#rfDriveImportBtn');
        if (count) count.textContent = state.driveSelected.size;
        if (btn) btn.disabled = state.driveSelected.size === 0;
    }
    async function importFromDrive() {
        if (!state.driveSelected.size) return;
        const btn = $('#rfDriveImportBtn');
        setBtnLoading(btn, true);
        try {
            const files = state.driveFiles.filter((f) => state.driveSelected.has(f.id));
            await api(API.driveImport, { method: 'POST', body: { files } });
            state.driveSelected.clear();
            closeModal('rfDriveModal');
            toast('Referência(s) importada(s).', { type: 'success' });
            await Promise.all([loadReferences(), loadFolders()]);
        } catch (err) {
            toast(err.message || 'Erro ao importar.', { type: 'error' });
        } finally {
            setBtnLoading(btn, false);
        }
    }

    /* =====================================================================
       EVENTS
       ===================================================================== */
    function bindEvents() {
        const search = $('#rfSearchInput');
        if (search) {
            search.addEventListener('input', debounce((e) => {
                state.search = e.target.value.trim();
                applyFilters();
            }, 180));
        }
        const catFilter = $('#rfFilterCategory');
        if (catFilter) {
            catFilter.addEventListener('change', () => {
                state.filterCategory = catFilter.value;
                applyFilters();
            });
        }
        const folderFilter = $('#rfFilterFolder');
        if (folderFilter) {
            folderFilter.addEventListener('change', () => {
                state.filterFolder = folderFilter.value;
                applyFilters();
            });
        }

        $$('.rf-view-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                $$('.rf-view-btn').forEach((b) => b.classList.remove('is-active'));
                btn.classList.add('is-active');
                state.view = btn.dataset.view;
                const grid = $('#rfGrid');
                if (grid) grid.dataset.view = state.view;
            });
        });

        const newFolderBtn = $('#rfNewFolderBtn');
        if (newFolderBtn) newFolderBtn.addEventListener('click', openNewFolderModal);
        const newFolderForm = $('#rfNewFolderForm');
        if (newFolderForm) newFolderForm.addEventListener('submit', submitNewFolder);

        const manageCatsBtn = $('#rfManageCategoriesBtn');
        if (manageCatsBtn) {
            manageCatsBtn.addEventListener('click', async () => {
                openModal('rfCategoriesModal');
                await loadCategories();
            });
        }
        const newCatForm = $('#rfNewCategoryForm');
        if (newCatForm) newCatForm.addEventListener('submit', submitNewCategory);

        const deleteSelectedBtn = $('#rfDeleteSelectedBtn');
        if (deleteSelectedBtn) deleteSelectedBtn.addEventListener('click', confirmDeleteSelected);

        const uploadBtn = $('#rfUploadBtn');
        if (uploadBtn) {
            uploadBtn.addEventListener('click', () => {
                ensureUploadCatSelector();
                openModal('rfUploadModal');
                populateFoldersSelects();
            });
        }
        const uploadForm = $('#rfUploadForm');
        if (uploadForm) uploadForm.addEventListener('submit', submitUpload);

        const folderCoverForm = $('#rfFolderCoverForm');
        if (folderCoverForm) folderCoverForm.addEventListener('submit', submitFolderCover);

        const setupDropzone = (dzId, inputId, titleId, subId, subDefault) => {
            const dz = $(dzId);
            const input = $(inputId);
            if (!dz || !input) return;
            input.addEventListener('change', () => {
                if (input.files?.length) {
                    dz.classList.add('is-filled');
                    const title = $(titleId);
                    if (title) title.textContent = input.files[0].name;
                    const sub = $(subId);
                    if (sub && subDefault) sub.textContent = subDefault;
                }
            });
            ['dragenter', 'dragover'].forEach((ev) => {
                dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('is-dragover'); });
            });
            ['dragleave', 'drop'].forEach((ev) => {
                dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('is-dragover'); });
            });
            dz.addEventListener('drop', (e) => {
                if (e.dataTransfer?.files?.length) {
                    input.files = e.dataTransfer.files;
                    input.dispatchEvent(new Event('change'));
                }
            });
        };
        setupDropzone('#rfDropzone', '#rfUploadFile', '#rfDropzoneTitle', '#rfDropzoneSub', 'JPG, JPEG, JFIF, PNG, WEBP ou GIF');
        setupDropzone('#rfFolderCoverDropzone', '#rfFolderCoverFile', '#rfFolderCoverTitle2', '#rfFolderCoverSub', 'JPG, PNG, WEBP ou GIF');

        const delConfirm = $('#rfDeleteConfirmBtn');
        if (delConfirm) delConfirm.addEventListener('click', confirmDelete);

        setupDeleteFolderModal();
        setupDeleteCategoryModal();

        $$('#rfCtxMenu [data-ctx-action]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.ctxAction;
                const targetId = ctxTargetId;
                closeContextMenu();
                if (!targetId) return;
                if (action === 'download') downloadReference(targetId);
                else if (action === 'delete') openDeleteModal(targetId);
            });
        });

        $$('#rfFolderCtxMenu [data-folder-action]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const action = btn.dataset.folderAction;
                const targetId = folderCtxTargetId;
                closeFolderContextMenu();
                if (!targetId) return;
                if (action === 'rename') openEditFolderModal(targetId);
                else if (action === 'delete') openDeleteFolderModal(targetId);
                else if (action === 'set-cover') openFolderCoverModal(targetId);
                else if (action === 'clear-cover') clearFolderCover(targetId);
            });
        });

        document.addEventListener('click', (e) => {
            if (!e.target.closest('#rfCtxMenu') && !e.target.closest('.rf-card-more')) closeContextMenu();
            if (!e.target.closest('#rfFolderCtxMenu') && !e.target.closest('.rf-folder-more')) closeFolderContextMenu();
        });

        const nameEditBtn = $('#rfNameEditBtn');
        if (nameEditBtn) nameEditBtn.addEventListener('click', startRename);
        const nameInput = $('#rfNameInput');
        if (nameInput) {
            nameInput.addEventListener('blur', commitRename);
            nameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') { e.preventDefault(); nameInput.blur(); }
                else if (e.key === 'Escape') cancelRename();
            });
        }
        const descEditBtn = $('#rfDescEditBtn');
        if (descEditBtn) descEditBtn.addEventListener('click', startDescEdit);
        const descInput = $('#rfDescInput');
        if (descInput) {
            descInput.addEventListener('blur', commitDescEdit);
            descInput.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') cancelDescEdit();
            });
        }
        const detailMenuBtn = $('#rfDetailMenuBtn');
        if (detailMenuBtn) {
            detailMenuBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (state.selectedId) openContextMenu(e, state.selectedId);
            });
        }
        const bcBack = $('#rfBreadcrumbBack');
        if (bcBack) bcBack.addEventListener('click', exitFolder);

        const clientSelect = $('#rfAssociateClientSelect');
        if (clientSelect) clientSelect.addEventListener('change', changeClient);
        const folderSelect = $('#rfAssociateFolderSelect');
        if (folderSelect) folderSelect.addEventListener('change', changeFolder);
        const visibleCheck = $('#rfVisibleToClient');
        if (visibleCheck) visibleCheck.addEventListener('change', changeVisibility);

        const viewerExpand = $('#rfViewerExpand');
        if (viewerExpand) {
            viewerExpand.addEventListener('click', () => {
                const img = $('#rfViewerImg');
                if (img?.src) window.open(img.src, '_blank');
            });
        }

        const driveBtn = $('#rfDriveBtn');
        if (driveBtn) driveBtn.addEventListener('click', openDriveModal);
        const driveConnect = $('#rfDriveConnectBtn');
        if (driveConnect) {
            driveConnect.addEventListener('click', () => {
                window.location.href =
                    '/accounts/google/login/?process=login&next=/references/&prompt=consent';
            });
        }
        const driveSearch = $('#rfDriveSearchInput');
        if (driveSearch) {
            driveSearch.addEventListener('input', debounce((e) => loadDriveFiles(e.target.value.trim()), 300));
        }
        const driveImport = $('#rfDriveImportBtn');
        if (driveImport) driveImport.addEventListener('click', importFromDrive);

        const pinterestBtn = $('#rfPinterestBtn');
        if (pinterestBtn) {
            pinterestBtn.addEventListener('click', (e) => {
                e.preventDefault();
                toast(
                    'Pinterest ainda não está liberado. Em breve você poderá importar pins diretamente para o Clivo.',
                    { type: 'info', duration: 4000 }
                );
            });
        }

        $$('[data-close]').forEach((btn) => {
            btn.addEventListener('click', () => closeModal(btn.dataset.close));
        });
        $$('.cl-modal-overlay').forEach((overlay) => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) overlay.classList.remove('is-open');
            });
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                $$('.cl-modal-overlay.is-open').forEach((m) => m.classList.remove('is-open'));
                closeContextMenu();
                closeFolderContextMenu();
            }
        });
    }

    function init() {
        bindEvents();
        refreshIcons();
        loadClients();
        loadCategories();
        loadFolders();
        loadReferences();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();