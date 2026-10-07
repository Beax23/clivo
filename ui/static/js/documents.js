/* =========================================================================
   DOCUMENTS — Arquivos
   ========================================================================= */

(function() {
    'use strict';

    // =====================================================================
    // HELPERS
    // =====================================================================

    function showToast(msg, type) {
        if (typeof window.clivoShowToast === 'function') {
            window.clivoShowToast(msg, type);
        }
    }

    function api(url, method, body) {
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

    function refreshIcons() {
        if (typeof window.clivoRefreshIcons === 'function') {
            window.clivoRefreshIcons();
        }
    }

    function formatDateTime(iso) {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            return d.toLocaleString('pt-BR', {
                day: '2-digit', month: 'short',
                year: 'numeric',
                hour: '2-digit', minute: '2-digit',
            });
        } catch (e) { return '—'; }
    }

    function formatDateOnly(iso) {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            return d.toLocaleDateString('pt-BR', {
                day: '2-digit', month: 'short', year: 'numeric',
            });
        } catch (e) { return '—'; }
    }

    function buildCacheBustedUrl(baseUrl, doc) {
        const v = doc && doc.updated_at
            ? new Date(doc.updated_at).getTime()
            : Date.now();
        const sep = baseUrl.indexOf('?') === -1 ? '?' : '&';
        return baseUrl + sep + 'v=' + v;
    }

    // =====================================================================
    // SCRIPT LOADER (uma vez por sessão, não cacheia falhas)
    // =====================================================================

    const _loadedScripts = {};

    function loadScriptOnce(src) {
        if (_loadedScripts[src]) return _loadedScripts[src];
        _loadedScripts[src] = new Promise(function(resolve, reject) {
            if (document.querySelector('script[src="' + src + '"]')) {
                resolve();
                return;
            }
            const s = document.createElement('script');
            s.src = src;
            s.async = true;
            s.onload = function() { resolve(); };
            s.onerror = function() {
                delete _loadedScripts[src];
                try { s.remove(); } catch (e) {}
                reject(new Error('Falha ao carregar ' + src));
            };
            document.head.appendChild(s);
        });
        return _loadedScripts[src];
    }

    // =====================================================================
    // ÍCONES + CORES
    // =====================================================================

    const EXT_TYPE_MAP = {
        'pdf':  { icon: 'file-text',        type: 'pdf' },
        'doc':  { icon: 'file-text',        type: 'doc' },
        'docx': { icon: 'file-text',        type: 'doc' },
        'txt':  { icon: 'file-text',        type: 'doc' },
        'md':   { icon: 'file-text',        type: 'doc' },
        'rtf':  { icon: 'file-text',        type: 'doc' },
        'odt':  { icon: 'file-text',        type: 'doc' },
        'xls':  { icon: 'file-spreadsheet', type: 'xls' },
        'xlsx': { icon: 'file-spreadsheet', type: 'xls' },
        'csv':  { icon: 'file-spreadsheet', type: 'xls' },
        'ods':  { icon: 'file-spreadsheet', type: 'xls' },
        'jpg':  { icon: 'file-image',       type: 'img' },
        'jpeg': { icon: 'file-image',       type: 'img' },
        'png':  { icon: 'file-image',       type: 'img' },
        'gif':  { icon: 'file-image',       type: 'img' },
        'svg':  { icon: 'file-image',       type: 'img' },
        'webp': { icon: 'file-image',       type: 'img' },
        'bmp':  { icon: 'file-image',       type: 'img' },
        'tiff': { icon: 'file-image',       type: 'img' },
        'ico':  { icon: 'file-image',       type: 'img' },
        'mp3':  { icon: 'file-audio',       type: 'audio' },
        'wav':  { icon: 'file-audio',       type: 'audio' },
        'm4a':  { icon: 'file-audio',       type: 'audio' },
        'ogg':  { icon: 'file-audio',       type: 'audio' },
        'flac': { icon: 'file-audio',       type: 'audio' },
        'mp4':  { icon: 'file-video',       type: 'video' },
        'mov':  { icon: 'file-video',       type: 'video' },
        'avi':  { icon: 'file-video',       type: 'video' },
        'mkv':  { icon: 'file-video',       type: 'video' },
        'webm': { icon: 'file-video',       type: 'video' },
        'zip':  { icon: 'file-archive',     type: 'archive' },
        'rar':  { icon: 'file-archive',     type: 'archive' },
        '7z':   { icon: 'file-archive',     type: 'archive' },
        'tar':  { icon: 'file-archive',     type: 'archive' },
        'gz':   { icon: 'file-archive',     type: 'archive' },
        'dwg':  { icon: 'ruler',            type: 'cad' },
        'dxf':  { icon: 'ruler',            type: 'cad' },
        'skp':  { icon: 'ruler',            type: 'cad' },
    };

    function fileMeta(ext) {
        if (!ext) return { icon: 'file', type: 'default' };
        const key = String(ext).toLowerCase();
        return EXT_TYPE_MAP[key] || { icon: 'file', type: 'default' };
    }

    function iconForExtension(ext) { return fileMeta(ext).icon; }
    function typeClassForExtension(ext) { return 'dc-icon--' + fileMeta(ext).type; }

    // =====================================================================
    // PREVIEW — TIPO
    // =====================================================================

    function previewKind(mimeType, ext) {
        const t = String(mimeType || '').toLowerCase();
        const e = String(ext || '').toLowerCase();

        if (t.indexOf('image/') === 0 ||
            ['jpg','jpeg','png','gif','svg','webp','bmp','ico','tiff'].indexOf(e) !== -1) {
            return 'image';
        }
        if (t === 'application/pdf' || e === 'pdf') {
            return 'pdf';
        }
        if (t.indexOf('text/') === 0 ||
            ['txt','md','csv','json','xml','html','css','js','py','log'].indexOf(e) !== -1) {
            return 'text';
        }
        if (['doc','docx','xls','xlsx','ppt','pptx','odt','ods','odp'].indexOf(e) !== -1) {
            return 'office';
        }
        return 'none';
    }

    function previewKindLabel(kind, ext) {
        switch (kind) {
            case 'image':  return 'Imagem';
            case 'pdf':    return 'PDF';
            case 'text':   return 'Texto';
            case 'office': return 'Documento Office';
            default:       return (ext ? '.' + ext : 'Arquivo');
        }
    }

    // =====================================================================
    // ESTADO
    // =====================================================================

    let documentsCache = [];
    let documentsLoaded = false;
    let currentDocument = null;
    let clientsCache = [];
    let clientsLoaded = false;
    let activeTab = 'preview';

    let detailAbortController = null;
    let historyAbortController = null;
    let officeLinkAbortController = null;

    let zoomLevel = 1;
    let isPanning = false;
    let panStart = { x: 0, y: 0, scrollLeft: 0, scrollTop: 0 };

    let rotationDeg = 0;

    // Google Drive
    let gdriveSelectedFiles = {};       // id -> meta
    let gdriveFilesCache = [];
    let gdriveSearchTimer = null;
    let gdriveLoaded = false;

    // =====================================================================
    // CLIENTES
    // =====================================================================

    async function loadClients(force) {
        if (clientsLoaded && !force) return clientsCache;
        try {
            const data = await api('/api/clients/');
            clientsCache = Array.isArray(data) ? data : (data.results || []);
            clientsLoaded = true;
        } catch (e) {
            clientsCache = [];
            clientsLoaded = true;
        }
        return clientsCache;
    }

    function fillClientSelect(selectEl, selectedId, emptyLabel) {
        if (!selectEl) return;
        selectEl.innerHTML = '<option value="">' + escapeHtml(emptyLabel || 'Sem cliente') + '</option>';
        clientsCache.forEach(function(c) {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name || c.email || 'Cliente';
            if (selectedId && String(selectedId) === String(c.id)) {
                opt.selected = true;
            }
            selectEl.appendChild(opt);
        });
    }

    // =====================================================================
    // LISTA
    // =====================================================================

    async function loadDocuments(force) {
        const listEl = document.getElementById('dcList');
        if (!listEl) return;

        if (documentsLoaded && !force) {
            renderList();
            return;
        }

        listEl.innerHTML = '<div class="dc-list-empty"><p>Carregando...</p></div>';

        try {
            const data = await api('/api/documents/');
            documentsCache = Array.isArray(data) ? data : (data.results || []);
            documentsLoaded = true;
        } catch (e) {
            documentsCache = [];
            documentsLoaded = true;
            listEl.innerHTML =
                '<div class="dc-list-empty">' +
                    '<i data-lucide="alert-circle"></i>' +
                    '<p>Erro ao carregar arquivos</p>' +
                '</div>';
            refreshIcons();
            return;
        }

        renderList();
        renderExtensionFilter();
    }

    function renderExtensionFilter() {
        const select = document.getElementById('dcExtensionFilter');
        if (!select) return;

        const extensions = {};
        documentsCache.forEach(function(d) {
            const ext = (d.extension || '').toLowerCase();
            if (ext) extensions[ext] = (extensions[ext] || 0) + 1;
        });

        const current = select.value;
        select.innerHTML = '<option value="">Extensão</option>';
        Object.keys(extensions).sort().forEach(function(ext) {
            const opt = document.createElement('option');
            opt.value = ext;
            opt.textContent = '.' + ext;
            select.appendChild(opt);
        });

        if (current && extensions[current]) select.value = current;
    }

    function getFilteredDocuments() {
        const searchInput = document.getElementById('dcSearchInput');
        const query = (searchInput && searchInput.value || '').trim().toLowerCase();

        const extSelect = document.getElementById('dcExtensionFilter');
        const extFilter = (extSelect && extSelect.value || '').toLowerCase();

        const clientSelect = document.getElementById('dcClientFilter');
        const clientFilter = clientSelect ? clientSelect.value : '';

        const contextSelect = document.getElementById('dcContextFilter');
        const contextFilter = contextSelect ? contextSelect.value : '';

        const sourceSelect = document.getElementById('dcSourceFilter');
        const sourceFilter = sourceSelect ? sourceSelect.value : '';

        let items = documentsCache.slice();

        if (extFilter) {
            items = items.filter(function(d) {
                return (d.extension || '').toLowerCase() === extFilter;
            });
        }

        if (clientFilter) {
            items = items.filter(function(d) {
                return String(d.client) === String(clientFilter);
            });
        }

        if (contextFilter) {
            items = items.filter(function(d) {
                const hasClient = d.client !== null && d.client !== undefined && d.client !== '';
                const hasProject = d.project_id !== null && d.project_id !== undefined && d.project_id !== '';
                if (contextFilter === 'with_client') return hasClient;
                if (contextFilter === 'without_client') return !hasClient;
                if (contextFilter === 'with_project') return hasProject;
                if (contextFilter === 'without_project') return !hasProject;
                if (contextFilter === 'without_any') return !hasClient && !hasProject;
                return true;
            });
        }

        if (sourceFilter) {
            items = items.filter(function(d) {
                return (d.source || 'upload') === sourceFilter;
            });
        }

        if (query) {
            items = items.filter(function(d) {
                const name = (d.full_name || '').toLowerCase();
                const client = (d.client_name || '').toLowerCase();
                return name.indexOf(query) !== -1 || client.indexOf(query) !== -1;
            });
        }

        return items;
    }

    function renderList() {
        const listEl = document.getElementById('dcList');
        if (!listEl) return;

        const items = getFilteredDocuments();

        if (!items.length) {
            listEl.innerHTML =
                '<div class="dc-list-empty">' +
                    '<i data-lucide="file"></i>' +
                    '<p>Nenhum arquivo</p>' +
                '</div>';
            refreshIcons();
            return;
        }

        const currentId = currentDocument ? currentDocument.id : null;

        let html = '';
        items.forEach(function(d) {
            const isSelected = currentId === d.id;
            const iconName = iconForExtension(d.extension);
            const typeClass = typeClassForExtension(d.extension);
            const fullName = d.full_name || d.name || '—';
            const size = d.size_display || '—';
            const client = d.client_name || 'Sem cliente';
            const source = d.source || 'upload';

            const sourceBadge = source === 'gdrive'
                ? '<span class="dc-item-source" title="Google Drive"><i data-lucide="hard-drive"></i>Drive</span>'
                : '';

            html +=
                '<div class="dc-item' + (isSelected ? ' is-selected' : '') + '" data-document-id="' + escapeHtml(d.id) + '">' +
                    '<div class="dc-item-icon ' + typeClass + '">' +
                        '<i data-lucide="' + iconName + '"></i>' +
                    '</div>' +
                    '<div class="dc-item-info">' +
                        '<div class="dc-item-name">' + escapeHtml(fullName) + '</div>' +
                        '<div class="dc-item-meta">' +
                            '<span>' + escapeHtml(size) + '</span>' +
                            '<span>·</span>' +
                            '<span>' + escapeHtml(client) + '</span>' +
                            (sourceBadge ? '<span>·</span>' + sourceBadge : '') +
                        '</div>' +
                    '</div>' +
                '</div>';
        });

        listEl.innerHTML = html;
        refreshIcons();

        listEl.querySelectorAll('.dc-item').forEach(function(el) {
            el.addEventListener('click', function() {
                const id = this.dataset.documentId;
                if (id) openDocument(id);
            });
        });
    }

    function updateSelectionHighlight() {
        const listEl = document.getElementById('dcList');
        if (!listEl) return;
        const currentId = currentDocument ? currentDocument.id : null;
        listEl.querySelectorAll('.dc-item').forEach(function(el) {
            el.classList.toggle('is-selected', el.dataset.documentId === currentId);
        });
    }

    // =====================================================================
    // DETALHE — abertura
    // =====================================================================

    async function openDocument(id) {
        if (detailAbortController) detailAbortController.abort();
        if (historyAbortController) historyAbortController.abort();
        if (officeLinkAbortController) officeLinkAbortController.abort();

        detailAbortController = new AbortController();
        const signal = detailAbortController.signal;

        let doc = documentsCache.find(function(d) { return d.id === id; });

        if (doc) {
            currentDocument = doc;
            activeTab = 'preview';
            resetZoom();
            resetRotation();

            const empty = document.getElementById('dcDetailEmpty');
            const content = document.getElementById('dcDetailContent');
            if (empty) empty.classList.add('hidden');
            if (content) content.classList.remove('hidden');

            renderDetail();
            updateSelectionHighlight();
            switchTab('preview', false);
            loadHistory();
        }

        try {
            const detail = await fetch('/api/documents/' + id + '/', {
                credentials: 'same-origin',
                signal: signal,
            }).then(function(r) {
                if (!r.ok) throw new Error('Falha');
                return r.json();
            });

            if (!detail) return;
            if (currentDocument && currentDocument.id !== id) return;

            currentDocument = detail;
            renderDetail();
            const idx = documentsCache.findIndex(function(d) { return d.id === id; });
            if (idx !== -1) documentsCache[idx] = detail;
            renderList();
            loadHistory();
        } catch (e) {
            if (e.name === 'AbortError') return;
            if (!doc) showToast('Erro ao carregar arquivo', 'error');
        }
    }

    function renderDetail() {
        if (!currentDocument) return;
        const d = currentDocument;

        const setText = function(id, val) {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };

        const nameEl = document.getElementById('dcDetailName');
        if (nameEl) nameEl.textContent = d.name || '—';

        setText('dcDetailSize', d.size_display || '—');
        setText('dcDetailMime', d.mime_type || '—');
        setText('dcDetailCreatedAt', d.created_at ? formatDateTime(d.created_at) : '—');
        setText('dcDetailClient', d.client_name || 'Sem cliente');
        setText('dcDetailProject', d.project_id || '—');

        // Painel de informações
        setText('dcInfoName', d.full_name || d.name || '—');
        setText('dcInfoType', d.extension ? d.extension.toUpperCase() : '—');
        setText('dcInfoSize', d.size_display || '—');
        setText('dcInfoCreatedBy', d.created_by_name || '—');
        setText('dcInfoCreatedAt', d.created_at ? formatDateOnly(d.created_at) : '—');

        const sourceEl = document.getElementById('dcInfoSource');
        if (sourceEl) {
            const sourceLabel = d.source_display || 'Upload';
            if (d.source === 'gdrive' && d.source_url) {
                sourceEl.innerHTML =
                    '<a href="' + escapeHtml(d.source_url) + '" target="_blank" rel="noopener">' +
                        escapeHtml(sourceLabel) + ' ↗' +
                    '</a>';
            } else {
                sourceEl.textContent = sourceLabel;
            }
        }

        const iconEl = document.getElementById('dcDetailIcon');
        if (iconEl) {
            const iconName = iconForExtension(d.extension);
            const typeClass = typeClassForExtension(d.extension);
            iconEl.className = 'dc-detail-icon ' + typeClass;
            iconEl.innerHTML = '<i data-lucide="' + iconName + '"></i>';
        }

        const associateClientSelect = document.getElementById('dcAssociateClientSelect');
        if (associateClientSelect) {
            fillClientSelect(associateClientSelect, d.client, 'Sem cliente');
        }

        const projectInput = document.getElementById('dcAssociateProjectInput');
        if (projectInput) projectInput.value = d.project_id || '';

        renderPreview();
        refreshIcons();
    }

    // =====================================================================
    // NOME INLINE
    // =====================================================================

    function setupInlineRename() {
        const editBtn = document.getElementById('dcNameEditBtn');
        const nameEl = document.getElementById('dcDetailName');
        const inputEl = document.getElementById('dcNameInput');

        if (!editBtn || !nameEl || !inputEl) return;

        function enterEditMode() {
            if (!currentDocument) return;
            inputEl.value = currentDocument.name || '';
            nameEl.classList.add('hidden');
            inputEl.classList.remove('hidden');
            inputEl.focus();
            inputEl.select();
        }

        function exitEditMode() {
            inputEl.classList.add('hidden');
            nameEl.classList.remove('hidden');
        }

        editBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            enterEditMode();
        });

        nameEl.addEventListener('dblclick', function(e) {
            e.preventDefault();
            enterEditMode();
        });

        inputEl.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const newName = inputEl.value.trim();
                exitEditMode();
                if (newName && currentDocument && newName !== currentDocument.name) {
                    saveInlineName(newName);
                }
            } else if (e.key === 'Escape') {
                e.preventDefault();
                exitEditMode();
            }
        });

        inputEl.addEventListener('blur', function() {
            const newName = inputEl.value.trim();
            exitEditMode();
            if (newName && currentDocument && newName !== currentDocument.name) {
                saveInlineName(newName);
            }
        });
    }

    async function saveInlineName(newName) {
        if (!currentDocument) return;

        const docId = currentDocument.id;
        const previousName = currentDocument.name;

        currentDocument.name = newName;
        currentDocument.full_name = currentDocument.extension
            ? (newName + '.' + currentDocument.extension)
            : newName;

        const nameEl = document.getElementById('dcDetailName');
        if (nameEl) nameEl.textContent = newName;

        const idx = documentsCache.findIndex(function(d) { return d.id === docId; });
        if (idx !== -1) {
            documentsCache[idx].name = newName;
            documentsCache[idx].full_name = currentDocument.full_name;
        }
        renderList();

        try {
            const updated = await api(
                '/api/documents/' + docId + '/',
                'PATCH',
                { name: newName }
            );
            currentDocument = updated;
            if (idx !== -1) documentsCache[idx] = updated;
            renderDetail();
            updateSelectionHighlight();
            showToast('Nome atualizado', 'success');
        } catch (err) {
            currentDocument.name = previousName;
            currentDocument.full_name = currentDocument.extension
                ? (previousName + '.' + currentDocument.extension)
                : previousName;
            if (idx !== -1) {
                documentsCache[idx].name = previousName;
                documentsCache[idx].full_name = currentDocument.full_name;
            }
            renderDetail();
            renderList();
            showToast(err.message || 'Erro ao renomear', 'error');
        }
    }

    // =====================================================================
    // ROTAÇÃO
    // =====================================================================

    function resetRotation() {
        rotationDeg = 0;
    }

    function applyRotation() {
        const img = document.querySelector('#dcPreviewContainer img');
        const pdfWrap = document.querySelector('#dcPreviewContainer .dc-preview-pdf-wrap');

        if (img) {
            img.style.transform = 'rotate(' + rotationDeg + 'deg) scale(' + zoomLevel + ')';
        }
        if (pdfWrap) {
            pdfWrap.style.transform = 'rotate(' + rotationDeg + 'deg)';
        }
    }

    function setupRotateButtons() {
        const rotateLeft = document.getElementById('dcRotateLeft');
        const rotateRight = document.getElementById('dcRotateRight');

        if (rotateLeft) {
            rotateLeft.addEventListener('click', function() {
                rotationDeg = (rotationDeg - 90 + 360) % 360;
                applyRotation();
            });
        }

        if (rotateRight) {
            rotateRight.addEventListener('click', function() {
                rotationDeg = (rotationDeg + 90) % 360;
                applyRotation();
            });
        }
    }

    // =====================================================================
    // PREVIEW
    // =====================================================================

    function previewUrlFor(doc) {
        const base = '/api/documents/' + doc.id + '/preview/';
        return buildCacheBustedUrl(base, doc);
    }

    function renderPreview() {
        const container = document.getElementById('dcPreviewContainer');
        const toolbar = document.getElementById('dcPreviewToolbar');
        const zoomControls = document.getElementById('dcZoomControls');
        const rotateControls = document.getElementById('dcRotateControls');
        const kindLabel = document.getElementById('dcPreviewKind');

        if (!container || !currentDocument) return;

        const d = currentDocument;
        const kind = previewKind(d.mime_type, d.extension);
        const url = previewUrlFor(d);

        if (kindLabel) kindLabel.textContent = previewKindLabel(kind, d.extension);
        if (zoomControls) zoomControls.classList.toggle('is-hidden', kind !== 'image');

        if (rotateControls) {
            const canRotate = (kind === 'image' || kind === 'pdf');
            rotateControls.classList.toggle('is-hidden', !canRotate);
        }

        if (toolbar) toolbar.style.display = kind === 'none' ? 'none' : 'flex';

        resetRotation();
        resetZoom();

        container.innerHTML = '';

        if (kind === 'none') {
            container.innerHTML =
                '<div class="dc-preview-empty">' +
                    '<i data-lucide="eye-off"></i>' +
                    '<p>Visualização não disponível para este tipo de arquivo.</p>' +
                    '<span>Use o botão <strong>Baixar</strong> para acessar o conteúdo.</span>' +
                '</div>';
            refreshIcons();
            return;
        }

        if (kind === 'image') {
            const wrap = document.createElement('div');
            wrap.className = 'dc-preview-image-wrap';
            const img = document.createElement('img');
            img.src = url;
            img.alt = d.full_name || '';
            img.draggable = false;
            wrap.appendChild(img);
            container.appendChild(wrap);
            setupZoomAndPan(wrap, img);
            return;
        }

        if (kind === 'pdf') {
            const pdfWrap = document.createElement('div');
            pdfWrap.className = 'dc-preview-pdf-wrap';
            const embed = document.createElement('embed');
            embed.src = url + '#toolbar=1&view=FitH&navpanes=0';
            embed.type = 'application/pdf';
            pdfWrap.appendChild(embed);
            container.appendChild(pdfWrap);
            return;
        }

        if (kind === 'text') {
            const wrap = document.createElement('div');
            wrap.className = 'dc-preview-text-wrap';
            wrap.innerHTML = '<pre>Carregando…</pre>';
            container.appendChild(wrap);

            fetch(url, { credentials: 'same-origin' })
                .then(function(r) {
                    if (!r.ok) throw new Error('Falha');
                    return r.text();
                })
                .then(function(text) {
                    const truncated = text.length > 200000
                        ? text.slice(0, 200000) + '\n\n… (arquivo truncado para visualização)'
                        : text;
                    wrap.innerHTML = '<pre>' + escapeHtml(truncated) + '</pre>';
                })
                .catch(function() {
                    container.innerHTML =
                        '<div class="dc-preview-empty">' +
                            '<i data-lucide="alert-circle"></i>' +
                            '<p>Não foi possível carregar o conteúdo.</p>' +
                            '<span>Use o botão <strong>Baixar</strong>.</span>' +
                        '</div>';
                    refreshIcons();
                });
            return;
        }

        if (kind === 'office') {
            const ext = (d.extension || '').toLowerCase();
            if (ext === 'docx') {
                renderDocxPreview(container, d);
                return;
            }
            renderOfficePreview(container, d);
            return;
        }

        refreshIcons();
    }

    // =====================================================================
    // DOCX PREVIEW — docx-preview
    // =====================================================================

    async function renderDocxPreview(container, d) {
        const docId = d.id;

        container.innerHTML =
            '<div class="dc-preview-office">' +
                '<p>Preparando visualização…</p>' +
                '<span>Carregando renderizador</span>' +
            '</div>';

        try {
            try {
                await loadScriptOnce('https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js');
                await loadScriptOnce('https://cdnjs.cloudflare.com/ajax/libs/docx-preview/0.3.2/docx-preview.min.js');
            } catch (e1) {
                console.warn('cdnjs falhou, tentando unpkg...', e1);
                await loadScriptOnce('https://unpkg.com/jszip@3.10.1/dist/jszip.min.js');
                await loadScriptOnce('https://unpkg.com/docx-preview@0.3.2/dist/docx-preview.min.js');
            }

            if (!window.docx || typeof window.docx.renderAsync !== 'function') {
                throw new Error('docx-preview não disponível após carregar scripts');
            }

            const res = await fetch(previewUrlFor(d), { credentials: 'same-origin' });
            if (!res.ok) {
                throw new Error('Falha ao baixar: HTTP ' + res.status);
            }

            const ct = res.headers.get('content-type') || '';
            if (ct.indexOf('text/html') !== -1) {
                throw new Error('Backend devolveu HTML em vez do arquivo. Verifique /preview/ no servidor.');
            }

            const buf = await res.arrayBuffer();

            if (buf.byteLength < 4) {
                throw new Error('Arquivo vazio ou corrompido (length=' + buf.byteLength + ')');
            }

            const head = new Uint8Array(buf.slice(0, 4));
            if (head[0] !== 0x50 || head[1] !== 0x4b) {
                const hex = Array.from(head).map(x => x.toString(16).padStart(2, '0')).join(' ');
                throw new Error('Conteúdo não é um docx válido (esperado "PK..", recebido "' + hex + '")');
            }

            if (!currentDocument || currentDocument.id !== docId) return;

            container.innerHTML = '';
            const holder = document.createElement('div');
            holder.className = 'dc-preview-docx';
            container.appendChild(holder);

            await window.docx.renderAsync(buf, holder, null, {
                inWrapper: true,
                ignoreWidth: false,
                breakPages: true,
                ignoreLastRenderedPageBreak: true,
                experimental: true,
            });
        } catch (e) {
            if (!currentDocument || currentDocument.id !== docId) return;
            console.error('Erro no docx-preview:', e);

            renderOfficeError(
                container,
                typeClassForExtension(d.extension),
                iconForExtension(d.extension),
                d
            );

            const hint = document.createElement('small');
            hint.style.cssText = 'display:block;margin-top:10px;font-size:11px;color:#c00;max-width:100%;word-break:break-word;';
            hint.textContent = String(e && (e.message || e));
            const office = container.querySelector('.dc-preview-office');
            if (office) office.appendChild(hint);
        }
    }

    // =====================================================================
    // OFFICE PREVIEW (xlsx / pptx / outros)
    // =====================================================================

    function renderOfficePreview(container, d) {
        const iconName = iconForExtension(d.extension);
        const typeClass = typeClassForExtension(d.extension);

        container.innerHTML =
            '<div class="dc-preview-office">' +
                '<div class="dc-preview-office-icon ' + typeClass + '">' +
                    '<i data-lucide="' + iconName + '"></i>' +
                '</div>' +
                '<p>Preparando visualização…</p>' +
                '<span>Conectando ao visualizador</span>' +
            '</div>';
        refreshIcons();

        if (officeLinkAbortController) officeLinkAbortController.abort();
        officeLinkAbortController = new AbortController();
        const signal = officeLinkAbortController.signal;
        const docId = d.id;

        fetch('/api/documents/' + docId + '/public-preview-link/', {
            credentials: 'same-origin',
            signal: signal,
        })
            .then(function(r) {
                if (!r.ok) throw new Error('Falha ao gerar link');
                return r.json();
            })
            .then(function(data) {
                if (!currentDocument || currentDocument.id !== docId) return;
                if (!data || !data.url) throw new Error('Link inválido');

                const isLocalhost = /^https?:\/\/(localhost|127\.0\.0\.1)/i.test(data.url);
                if (isLocalhost) {
                    renderOfficeLocalhostFallback(container, d, typeClass, iconName);
                    return;
                }

                mountOfficeViewer(container, data.url, d, typeClass, iconName, docId);
            })
            .catch(function(e) {
                if (e.name === 'AbortError') return;
                if (!currentDocument || currentDocument.id !== docId) return;
                renderOfficeError(container, typeClass, iconName, d);
            });
    }

    function mountOfficeViewer(container, publicUrl, doc, typeClass, iconName, docId) {
        const officeUrl =
            'https://view.officeapps.live.com/op/embed.aspx?src=' +
            encodeURIComponent(publicUrl);

        const googleUrl =
            'https://docs.google.com/viewer?url=' +
            encodeURIComponent(publicUrl) +
            '&embedded=true';

        container.innerHTML = '';
        const iframe = document.createElement('iframe');
        iframe.title = doc.full_name || '';
        iframe.setAttribute('allowfullscreen', 'true');
        iframe.src = officeUrl;
        container.appendChild(iframe);

        let settled = false;
        const fallbackTimer = setTimeout(function() {
            if (settled) return;
            if (!currentDocument || currentDocument.id !== docId) return;
            if (!iframe.parentNode) return;
            iframe.src = googleUrl;
        }, 6000);

        iframe.addEventListener('load', function() {
            settled = true;
            clearTimeout(fallbackTimer);
        });
    }

    function renderOfficeLocalhostFallback(container, doc, typeClass, iconName) {
        const url = previewUrlFor(doc);
        container.innerHTML =
            '<div class="dc-preview-office">' +
                '<div class="dc-preview-office-icon ' + typeClass + '">' +
                    '<i data-lucide="' + iconName + '"></i>' +
                '</div>' +
                '<p>Documento Office</p>' +
                '<span>A visualização embutida de ' +
                escapeHtml((doc.extension || '').toUpperCase()) +
                ' requer uma URL pública HTTPS. ' +
                'Em produção, o arquivo abre no visualizador. ' +
                'Agora, use <strong>Baixar</strong> ou abra em nova aba.</span>' +
                '<div class="dc-preview-office-actions">' +
                    '<a class="btn-minimal" href="' + escapeHtml(url) + '" target="_blank" rel="noopener">' +
                        '<i data-lucide="external-link"></i>' +
                        '<span>Abrir em nova aba</span>' +
                    '</a>' +
                '</div>' +
            '</div>';
        refreshIcons();
    }

    function renderOfficeError(container, typeClass, iconName, doc) {
        container.innerHTML =
            '<div class="dc-preview-office">' +
                '<div class="dc-preview-office-icon ' + typeClass + '">' +
                    '<i data-lucide="' + iconName + '"></i>' +
                '</div>' +
                '<p>Documento Office</p>' +
                '<span>Não foi possível preparar a visualização. ' +
                'Use o botão <strong>Baixar</strong> para abrir o arquivo.</span>' +
            '</div>';
        refreshIcons();
    }

    // =====================================================================
    // ZOOM / PAN
    // =====================================================================

    function applyZoom(wrap, img) {
        img.style.transform = 'rotate(' + rotationDeg + 'deg) scale(' + zoomLevel + ')';
        const levelEl = document.getElementById('dcZoomLevel');
        if (levelEl) levelEl.textContent = Math.round(zoomLevel * 100) + '%';
    }

    function resetZoom() {
        zoomLevel = 1;
        const levelEl = document.getElementById('dcZoomLevel');
        if (levelEl) levelEl.textContent = '100%';
    }

    function setupZoomAndPan(wrap, img) {
        applyZoom(wrap, img);

        wrap.addEventListener('wheel', function(e) {
            if (!e.ctrlKey && !e.metaKey) return;
            e.preventDefault();
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            zoomLevel = Math.min(6, Math.max(0.2, zoomLevel + delta));
            applyZoom(wrap, img);
        }, { passive: false });

        wrap.addEventListener('mousedown', function(e) {
            if (e.button !== 0) return;
            if (img.naturalWidth * zoomLevel <= wrap.clientWidth &&
                img.naturalHeight * zoomLevel <= wrap.clientHeight) return;
            isPanning = true;
            panStart.x = e.clientX;
            panStart.y = e.clientY;
            panStart.scrollLeft = wrap.scrollLeft;
            panStart.scrollTop = wrap.scrollTop;
            wrap.classList.add('is-panning');
            e.preventDefault();
        });
    }

    document.addEventListener('mousemove', function(e) {
        if (!isPanning) return;
        const wrap = document.querySelector('#dcPreviewContainer .dc-preview-image-wrap');
        if (!wrap) return;
        wrap.scrollLeft = panStart.scrollLeft - (e.clientX - panStart.x);
        wrap.scrollTop = panStart.scrollTop - (e.clientY - panStart.y);
    });

    document.addEventListener('mouseup', function() {
        if (!isPanning) return;
        isPanning = false;
        const wrap = document.querySelector('#dcPreviewContainer .dc-preview-image-wrap');
        if (wrap) wrap.classList.remove('is-panning');
    });

    function setupZoomButtons() {
        const zoomIn = document.getElementById('dcZoomIn');
        const zoomOut = document.getElementById('dcZoomOut');
        const zoomReset = document.getElementById('dcZoomReset');

        function getImgAndWrap() {
            return {
                img: document.querySelector('#dcPreviewContainer img'),
                wrap: document.querySelector('#dcPreviewContainer .dc-preview-image-wrap'),
            };
        }

        if (zoomIn) zoomIn.addEventListener('click', function() {
            const r = getImgAndWrap();
            if (!r.img || !r.wrap) return;
            zoomLevel = Math.min(6, zoomLevel + 0.2);
            applyZoom(r.wrap, r.img);
        });

        if (zoomOut) zoomOut.addEventListener('click', function() {
            const r = getImgAndWrap();
            if (!r.img || !r.wrap) return;
            zoomLevel = Math.max(0.2, zoomLevel - 0.2);
            applyZoom(r.wrap, r.img);
        });

        if (zoomReset) zoomReset.addEventListener('click', function() {
            const r = getImgAndWrap();
            if (!r.img || !r.wrap) return;
            resetZoom();
            resetRotation();
            applyZoom(r.wrap, r.img);
            r.wrap.scrollLeft = 0;
            r.wrap.scrollTop = 0;
        });
    }

    // =====================================================================
    // ABAS
    // =====================================================================

    function switchTab(tab, refresh) {
        activeTab = tab || 'preview';

        document.querySelectorAll('.dc-tab').forEach(function(btn) {
            const isActive = btn.dataset.tab === activeTab;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        document.querySelectorAll('.dc-tab-panel').forEach(function(panel) {
            const targetId = 'dcTab' + activeTab.charAt(0).toUpperCase() + activeTab.slice(1);
            panel.classList.toggle('is-active', panel.id === targetId);
        });

        if (refresh !== false) refreshIcons();
    }

    function setupTabs() {
        document.querySelectorAll('.dc-tab').forEach(function(btn) {
            btn.addEventListener('click', function() {
                switchTab(this.dataset.tab);

                if (this.dataset.tab === 'details' && currentDocument) {
                    const listEl = document.getElementById('dcHistoryList');
                    if (listEl) {
                        const onlyEmpty = listEl.children.length === 1 &&
                            listEl.firstElementChild.classList.contains('dc-empty-inline');
                        if (onlyEmpty) loadHistory();
                    }
                }
            });
        });
    }

    // =====================================================================
    // HISTÓRICO
    // =====================================================================

    async function loadHistory() {
        if (!currentDocument) return;
        const listEl = document.getElementById('dcHistoryList');
        if (!listEl) return;

        if (historyAbortController) historyAbortController.abort();
        historyAbortController = new AbortController();
        const signal = historyAbortController.signal;
        const docId = currentDocument.id;

        listEl.innerHTML = '<li class="dc-empty-inline"><p>Carregando...</p></li>';

        try {
            const res = await fetch('/api/documents/' + docId + '/history/', {
                credentials: 'same-origin',
                signal: signal,
            });
            if (!res.ok) throw new Error('Falha');
            const entries = await res.json();
            if (!currentDocument || currentDocument.id !== docId) return;
            renderHistory(entries || []);
        } catch (e) {
            if (e.name === 'AbortError') return;
            listEl.innerHTML = '<li class="dc-empty-inline"><p>Erro ao carregar histórico.</p></li>';
        }
    }

    function renderHistory(entries) {
        const listEl = document.getElementById('dcHistoryList');
        if (!listEl) return;

        if (!entries.length) {
            listEl.innerHTML = '<li class="dc-empty-inline"><p>Sem histórico.</p></li>';
            return;
        }

        let html = '';
        entries.forEach(function(e) {
            const time = formatDateTime(e.timestamp);
            const action = e.action_display || e.action || '—';
            const user = e.user_name || e.user_email || '—';
            html +=
                '<li>' +
                    '<span class="dc-history-time">' + escapeHtml(time) + '</span>' +
                    '<div class="dc-history-content">' +
                        '<span class="dc-history-action">' + escapeHtml(action) + '</span>' +
                        '<span class="dc-history-by">por ' + escapeHtml(user) + '</span>' +
                    '</div>' +
                '</li>';
        });

        listEl.innerHTML = html;
    }

    // =====================================================================
    // MODAIS
    // =====================================================================

    function openModal(id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.add('active');
    }

    function closeModal(id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.remove('active');
    }

    function setupModals() {
        document.querySelectorAll('[data-close]').forEach(function(el) {
            el.addEventListener('click', function() {
                const id = this.dataset.close;
                if (id) closeModal(id);
            });
        });

        document.querySelectorAll('.cl-modal-overlay').forEach(function(overlay) {
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) overlay.classList.remove('active');
            });
        });
    }

    // =====================================================================
    // MENU "ADICIONAR"
    // =====================================================================

    function setupAddMenu() {
        const wrap = document.getElementById('dcAddWrap');
        const btn = document.getElementById('dcAddBtn');
        const menu = document.getElementById('dcAddMenu');

        if (!wrap || !btn || !menu) return;

        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            const isOpen = wrap.classList.toggle('is-open');
            menu.classList.toggle('hidden', !isOpen);
            refreshIcons();
        });

        document.addEventListener('click', function(e) {
            if (!wrap.contains(e.target)) {
                wrap.classList.remove('is-open');
                menu.classList.add('hidden');
            }
        });

        menu.querySelectorAll('.dc-add-item').forEach(function(item) {
            item.addEventListener('click', function() {
                const action = this.dataset.add;
                wrap.classList.remove('is-open');
                menu.classList.add('hidden');

                if (action === 'upload') {
                    openUploadModal();
                } else if (action === 'gdrive') {
                    openDriveModal();
                } else if (action === 'url') {
                    showToast('Importação por URL em breve', 'info');
                }
            });
        });
    }

    // =====================================================================
    // UPLOAD
    // =====================================================================

    async function openUploadModal() {
        const form = document.getElementById('dcUploadForm');
        if (!form) return;

        await loadClients();
        form.reset();

        const dropzone = document.getElementById('dcDropzone');
        if (dropzone && dropzone._reset) dropzone._reset();

        const select = document.getElementById('dcUploadClient');
        fillClientSelect(select, null, 'Sem cliente');

        openModal('dcUploadModal');
        refreshIcons();
    }

    function setupUpload() {
        const form = document.getElementById('dcUploadForm');
        if (!form) return;

        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            const fileInput = document.getElementById('dcUploadFile');
            const nameInput = document.getElementById('dcUploadName');
            const clientSelect = document.getElementById('dcUploadClient');
            const projectInput = document.getElementById('dcUploadProject');

            if (!fileInput.files || !fileInput.files.length) {
                showToast('Selecione um arquivo', 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            if (nameInput.value.trim()) formData.append('name', nameInput.value.trim());
            if (clientSelect.value) formData.append('client_id', clientSelect.value);
            if (projectInput.value.trim()) formData.append('project_id', projectInput.value.trim());

            const submitBtn = document.getElementById('dcUploadSubmitBtn');
            submitBtn.disabled = true;
            const original = submitBtn.innerHTML;
            submitBtn.innerHTML = 'Enviando...';

            try {
                const created = await api('/api/documents/', 'POST', formData);
                showToast('Arquivo enviado', 'success');
                closeModal('dcUploadModal');
                documentsLoaded = false;
                await loadDocuments(true);
                if (created && created.id) openDocument(created.id);
            } catch (err) {
                showToast(err.message || 'Erro ao enviar arquivo', 'error');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = original;
            }
        });
    }

    // =====================================================================
    // GOOGLE DRIVE
    // =====================================================================

    async function openDriveModal() {
        gdriveSelectedFiles = {};
        updateDriveSummary();

        const connectEl = document.getElementById('dcDriveConnect');
        const connectedEl = document.getElementById('dcDriveConnected');

        if (!connectEl || !connectedEl) return;

        // Checa se o usuário tem conta Google conectada
        let connected = false;
        try {
            const status = await api('/api/documents/gdrive/status/');
            connected = !!(status && status.connected);
        } catch (e) {
            connected = false;
        }

        if (!connected) {
            connectEl.style.display = 'flex';
            connectedEl.style.display = 'none';
            openModal('dcDriveModal');
            refreshIcons();
            return;
        }

        connectEl.style.display = 'none';
        connectedEl.style.display = 'flex';
        openModal('dcDriveModal');
        refreshIcons();

        // Carrega arquivos
        await loadDriveFiles('');
    }

    async function loadDriveFiles(query) {
        const listEl = document.getElementById('dcDriveFiles');
        if (!listEl) return;

        listEl.innerHTML = '<p class="dc-drive-empty">Carregando…</p>';

        try {
            const url = '/api/documents/gdrive/list/' + (query ? ('?q=' + encodeURIComponent(query)) : '');
            const data = await api(url);
            gdriveFilesCache = (data && data.files) || [];
            gdriveLoaded = true;
            renderDriveFiles();
        } catch (err) {
            listEl.innerHTML = '<p class="dc-drive-empty">' +
                escapeHtml(err.message || 'Erro ao carregar arquivos') +
                '</p>';
        }
    }

    function renderDriveFiles() {
        const listEl = document.getElementById('dcDriveFiles');
        if (!listEl) return;

        if (!gdriveFilesCache.length) {
            listEl.innerHTML = '<p class="dc-drive-empty">Nenhum arquivo encontrado</p>';
            return;
        }

        let html = '';
        gdriveFilesCache.forEach(function(f) {
            const id = f.id || '';
            const isSelected = !!gdriveSelectedFiles[id];
            const name = f.name || '—';
            const size = f.size ? formatBytes(parseInt(f.size, 10)) : '';
            const mime = f.mimeType || '';
            const icon = gdriveFileIcon(mime);

            html +=
                '<div class="dc-drive-file' + (isSelected ? ' is-selected' : '') + '" data-file-id="' + escapeHtml(id) + '">' +
                    '<div class="dc-drive-file-check">' +
                        '<i data-lucide="check"></i>' +
                    '</div>' +
                    '<div class="dc-drive-file-icon">' + icon + '</div>' +
                    '<div class="dc-drive-file-info">' +
                        '<div class="dc-drive-file-name">' + escapeHtml(name) + '</div>' +
                        '<div class="dc-drive-file-meta">' + escapeHtml(size) + '</div>' +
                    '</div>' +
                '</div>';
        });

        listEl.innerHTML = html;
        refreshIcons();

        listEl.querySelectorAll('.dc-drive-file').forEach(function(el) {
            el.addEventListener('click', function() {
                const id = this.dataset.fileId;
                const file = gdriveFilesCache.find(function(f) { return f.id === id; });
                if (!file) return;

                if (gdriveSelectedFiles[id]) {
                    delete gdriveSelectedFiles[id];
                    this.classList.remove('is-selected');
                } else {
                    gdriveSelectedFiles[id] = file;
                    this.classList.add('is-selected');
                }
                updateDriveSummary();
            });
        });
    }

    function gdriveFileIcon(mime) {
        if (!mime) return '<i data-lucide="file"></i>';
        if (mime.indexOf('image/') === 0) return '<i data-lucide="file-image"></i>';
        if (mime.indexOf('video/') === 0) return '<i data-lucide="file-video"></i>';
        if (mime.indexOf('audio/') === 0) return '<i data-lucide="file-audio"></i>';
        if (mime === 'application/pdf') return '<i data-lucide="file-text"></i>';
        if (mime.indexOf('spreadsheet') !== -1 || mime.indexOf('excel') !== -1) return '<i data-lucide="file-spreadsheet"></i>';
        if (mime.indexOf('word') !== -1 || mime.indexOf('document') !== -1) return '<i data-lucide="file-text"></i>';
        return '<i data-lucide="file"></i>';
    }

    function formatBytes(n) {
        if (!n || n <= 0) return '';
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
        if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
        return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
    }

    function updateDriveSummary() {
        const count = Object.keys(gdriveSelectedFiles).length;
        const countEl = document.getElementById('dcDriveSelectedCount');
        const summaryEl = document.getElementById('dcDriveSummary');
        const importBtn = document.getElementById('dcDriveImportBtn');

        if (countEl) countEl.textContent = String(count);
        if (summaryEl) summaryEl.classList.toggle('hidden', count === 0);
        if (importBtn) importBtn.disabled = count === 0;
    }

    function setupDrive() {
        const importBtn = document.getElementById('dcDriveImportBtn');
        const searchInput = document.getElementById('dcDriveSearchInput');

        if (importBtn) {
            importBtn.addEventListener('click', async function() {
                const ids = Object.keys(gdriveSelectedFiles);
                if (!ids.length) return;

                const files = ids.map(function(id) { return gdriveSelectedFiles[id]; });

                importBtn.disabled = true;
                const original = importBtn.innerHTML;
                importBtn.innerHTML = 'Importando...';

                try {
                    const result = await api('/api/documents/gdrive/import/', 'POST', { files: files });
                    const imported = (result && result.imported) || [];
                    const errors = (result && result.errors) || [];

                    if (imported.length) {
                        showToast(imported.length + ' arquivo(s) importado(s)', 'success');
                    }
                    if (errors.length) {
                        showToast(errors.length + ' arquivo(s) com erro', 'error');
                    }

                    closeModal('dcDriveModal');
                    gdriveSelectedFiles = {};
                    documentsLoaded = false;
                    await loadDocuments(true);

                    if (imported.length === 1 && imported[0].id) {
                        openDocument(imported[0].id);
                    }
                } catch (err) {
                    showToast(err.message || 'Erro ao importar', 'error');
                } finally {
                    importBtn.disabled = false;
                    importBtn.innerHTML = original;
                }
            });
        }

        if (searchInput) {
            searchInput.addEventListener('input', function() {
                const q = this.value.trim();
                if (gdriveSearchTimer) clearTimeout(gdriveSearchTimer);
                gdriveSearchTimer = setTimeout(function() {
                    loadDriveFiles(q);
                }, 350);
            });
        }
    }

    // =====================================================================
    // SUBSTITUIR
    // =====================================================================

    function setupReplace() {
        const btn = document.getElementById('dcReplaceBtn');
        const form = document.getElementById('dcReplaceForm');

        if (btn) {
            btn.addEventListener('click', function() {
                if (!currentDocument) return;
                form.reset();
                const dz = document.getElementById('dcReplaceDropzone');
                if (dz && dz._reset) dz._reset();
                openModal('dcReplaceModal');
                refreshIcons();
            });
        }

        if (form) {
            form.addEventListener('submit', async function(e) {
                e.preventDefault();
                if (!currentDocument) return;

                const fileInput = document.getElementById('dcReplaceFile');
                if (!fileInput.files || !fileInput.files.length) {
                    showToast('Selecione um arquivo', 'error');
                    return;
                }

                const formData = new FormData();
                formData.append('file', fileInput.files[0]);

                const submitBtn = document.getElementById('dcReplaceSubmitBtn');
                submitBtn.disabled = true;
                const original = submitBtn.innerHTML;
                submitBtn.innerHTML = 'Substituindo...';

                try {
                    const updated = await api(
                        '/api/documents/' + currentDocument.id + '/replace/',
                        'POST',
                        formData
                    );
                    showToast('Arquivo substituído', 'success');
                    closeModal('dcReplaceModal');

                    currentDocument = updated;
                    const idx = documentsCache.findIndex(function(d) { return d.id === updated.id; });
                    if (idx !== -1) documentsCache[idx] = updated;

                    documentsLoaded = false;
                    await loadDocuments(true);
                    renderDetail();
                    loadHistory();
                    updateSelectionHighlight();
                } catch (err) {
                    showToast(err.message || 'Erro ao substituir', 'error');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = original;
                }
            });
        }
    }

    // =====================================================================
    // EXCLUIR
    // =====================================================================

    function setupDelete() {
        const btn = document.getElementById('dcDeleteBtn');
        const input = document.getElementById('dcDeleteInput');
        const confirmBtn = document.getElementById('dcDeleteConfirmBtn');

        if (btn) {
            btn.addEventListener('click', function() {
                if (!currentDocument) return;
                if (input) input.value = '';
                if (confirmBtn) confirmBtn.disabled = true;
                openModal('dcDeleteModal');
                refreshIcons();
                setTimeout(function() { if (input) input.focus(); }, 100);
            });
        }

        if (input && confirmBtn) {
            input.addEventListener('input', function() {
                const expected = (currentDocument && (currentDocument.full_name || currentDocument.name)) || '';
                confirmBtn.disabled = this.value.trim() !== expected;
            });
        }

        if (confirmBtn) {
            confirmBtn.addEventListener('click', async function() {
                if (!currentDocument) return;

                confirmBtn.disabled = true;
                const original = confirmBtn.innerHTML;
                confirmBtn.innerHTML = 'Excluindo...';

                try {
                    await api('/api/documents/' + currentDocument.id + '/', 'DELETE');
                    showToast('Arquivo excluído', 'success');
                    closeModal('dcDeleteModal');
                    currentDocument = null;
                    documentsLoaded = false;
                    resetDetail();
                    await loadDocuments(true);
                } catch (err) {
                    showToast(err.message || 'Erro ao excluir', 'error');
                    confirmBtn.disabled = false;
                    confirmBtn.innerHTML = original;
                }
            });
        }
    }

    function resetDetail() {
        const empty = document.getElementById('dcDetailEmpty');
        const content = document.getElementById('dcDetailContent');
        if (empty) empty.classList.remove('hidden');
        if (content) content.classList.add('hidden');
    }

    // =====================================================================
    // DOWNLOAD
    // =====================================================================

    function setupDownload() {
        const downloadBtn = document.getElementById('dcDownloadBtn');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', function() {
                if (!currentDocument) return;
                window.location.href = '/api/documents/' + currentDocument.id + '/download/';
            });
        }
    }

    // =====================================================================
    // ASSOCIAÇÕES
    // =====================================================================

    function setupAssociations() {
        const clientBtn = document.getElementById('dcAssociateClientBtn');
        if (clientBtn) {
            clientBtn.addEventListener('click', async function() {
                if (!currentDocument) return;
                const select = document.getElementById('dcAssociateClientSelect');
                const clientId = select ? select.value : '';

                clientBtn.disabled = true;
                const original = clientBtn.innerHTML;
                clientBtn.innerHTML = 'Aplicando...';

                try {
                    const updated = await api(
                        '/api/documents/' + currentDocument.id + '/associate-client/',
                        'POST',
                        { client_id: clientId || null }
                    );
                    showToast('Cliente atualizado', 'success');
                    currentDocument = updated;
                    documentsLoaded = false;
                    await loadDocuments(true);
                    renderDetail();
                    loadHistory();
                } catch (err) {
                    showToast(err.message || 'Erro ao associar cliente', 'error');
                } finally {
                    clientBtn.disabled = false;
                    clientBtn.innerHTML = original;
                }
            });
        }

        const projectBtn = document.getElementById('dcAssociateProjectBtn');
        if (projectBtn) {
            projectBtn.addEventListener('click', async function() {
                if (!currentDocument) return;
                const input = document.getElementById('dcAssociateProjectInput');
                const projectId = input ? input.value.trim() : '';

                projectBtn.disabled = true;
                const original = projectBtn.innerHTML;
                projectBtn.innerHTML = 'Aplicando...';

                try {
                    const updated = await api(
                        '/api/documents/' + currentDocument.id + '/associate-project/',
                        'POST',
                        { project_id: projectId || null }
                    );
                    showToast('Projeto atualizado', 'success');
                    currentDocument = updated;
                    documentsLoaded = false;
                    await loadDocuments(true);
                    renderDetail();
                    loadHistory();
                } catch (err) {
                    showToast(err.message || 'Erro ao associar projeto', 'error');
                } finally {
                    projectBtn.disabled = false;
                    projectBtn.innerHTML = original;
                }
            });
        }
    }

    // =====================================================================
    // FILTROS
    // =====================================================================

    function setupFilters() {
        const search = document.getElementById('dcSearchInput');
        if (search) search.addEventListener('input', renderList);

        const ext = document.getElementById('dcExtensionFilter');
        if (ext) ext.addEventListener('change', renderList);

        const client = document.getElementById('dcClientFilter');
        if (client) client.addEventListener('change', renderList);

        const context = document.getElementById('dcContextFilter');
        if (context) context.addEventListener('change', renderList);

        const source = document.getElementById('dcSourceFilter');
        if (source) source.addEventListener('change', renderList);

        const refresh = document.getElementById('dcRefreshHistoryBtn');
        if (refresh) refresh.addEventListener('click', loadHistory);
    }

    // =====================================================================
    // DROPZONES
    // =====================================================================

    function setupDropzone(dropzoneId, inputId, titleId, subId) {
        const dropzone = document.getElementById(dropzoneId);
        const input = document.getElementById(inputId);
        const title = titleId ? document.getElementById(titleId) : null;
        const sub = subId ? document.getElementById(subId) : null;

        if (!dropzone || !input) return;

        function updateLabel() {
            if (!input.files || !input.files.length) {
                if (title) title.textContent = 'Arraste um arquivo aqui';
                if (sub) sub.textContent = 'ou clique para escolher do computador';
                dropzone.classList.remove('is-filled');
                return;
            }
            const file = input.files[0];
            const sizeKb = (file.size / 1024).toFixed(1);
            if (title) title.textContent = file.name;
            if (sub) sub.textContent = sizeKb + ' KB · ' + (file.type || 'tipo desconhecido');
            dropzone.classList.add('is-filled');
        }

        input.addEventListener('change', updateLabel);

        ['dragenter', 'dragover'].forEach(function(ev) {
            dropzone.addEventListener(ev, function(e) {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add('is-dragover');
            });
        });

        ['dragleave', 'drop'].forEach(function(ev) {
            dropzone.addEventListener(ev, function(e) {
                e.preventDefault();
                e.stopPropagation();
                if (ev === 'dragleave' && dropzone.contains(e.relatedTarget)) return;
                dropzone.classList.remove('is-dragover');
            });
        });

        dropzone.addEventListener('drop', function(e) {
            const files = e.dataTransfer && e.dataTransfer.files;
            if (files && files.length) {
                input.files = files;
                updateLabel();
            }
        });

        dropzone._reset = function() {
            input.value = '';
            updateLabel();
        };
        updateLabel();
    }

    // =====================================================================
    // MOUNT / UNMOUNT
    // =====================================================================

    function mount() {
        documentsLoaded = false;
        currentDocument = null;
        activeTab = 'preview';
        resetZoom();
        resetRotation();
        gdriveSelectedFiles = {};
        gdriveFilesCache = [];
        gdriveLoaded = false;

        resetDetail();
        setupModals();
        setupTabs();
        setupAddMenu();
        setupUpload();
        setupDrive();
        setupInlineRename();
        setupReplace();
        setupDelete();
        setupDownload();
        setupAssociations();
        setupFilters();
        setupZoomButtons();
        setupRotateButtons();

        setupDropzone('dcDropzone', 'dcUploadFile', 'dcDropzoneTitle', 'dcDropzoneSub');
        setupDropzone('dcReplaceDropzone', 'dcReplaceFile', 'dcReplaceDropzoneTitle', 'dcReplaceDropzoneSub');

        loadClients().then(function() {
            const clientFilter = document.getElementById('dcClientFilter');
            fillClientSelect(clientFilter, null, 'Todos os clientes');
        });

        loadDocuments(true);
        refreshIcons();
    }

    function unmount() {
        if (detailAbortController) detailAbortController.abort();
        if (historyAbortController) historyAbortController.abort();
        if (officeLinkAbortController) officeLinkAbortController.abort();
        if (gdriveSearchTimer) clearTimeout(gdriveSearchTimer);
    }

    window.ClivoPages = window.ClivoPages || {};
    window.ClivoPages.documents = {
        mount: mount,
        unmount: unmount,
    };
})();