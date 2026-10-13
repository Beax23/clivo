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

    function formatBytes(n) {
        n = Number(n) || 0;
        if (n < 1024) return n + ' B';
        if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
        if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
        return (n / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
    }

    // =====================================================================
    // SVG — pasta e arquivo
    // =====================================================================

    function folderSvg() {
        return (
            '<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
                '<path d="M6 14c0-1.1.9-2 2-2h10.2c.6 0 1.2.3 1.6.7l2.2 2.3c.4.4 1 .7 1.6.7H40c1.1 0 2 .9 2 2v20c0 1.1-.9 2-2 2H8c-1.1 0-2-.9-2-2V14z" fill="currentColor" opacity="0.28"/>' +
                '<path d="M4 20c0-1.1.9-2 2-2h14l2 2h20c1.1 0 2 .9 2 2v16c0 1.1-.9 2-2 2H6c-1.1 0-2-.9-2-2V20z" fill="currentColor" opacity="0.55"/>' +
                '<path d="M4 20c0-1.1.9-2 2-2h14l2 2h20" stroke="currentColor" stroke-width="0.75" stroke-linejoin="round" opacity="0.9"/>' +
            '</svg>'
        );
    }

    function fileSvg() {
        return (
            '<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
                '<path d="M10 8c0-1.1.9-2 2-2h16l12 12v22c0 1.1-.9 2-2 2H12c-1.1 0-2-.9-2-2V8z" fill="currentColor" opacity="0.18"/>' +
                '<path d="M10 8c0-1.1.9-2 2-2h16l12 12v22c0 1.1-.9 2-2 2H12c-1.1 0-2-.9-2-2V8z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>' +
                '<path d="M28 6v10c0 1.1.9 2 2 2h10" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" fill="currentColor" fill-opacity="0.22"/>' +
                '<path d="M15 22h12" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" opacity="0.45"/>' +
                '<path d="M15 27h16" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" opacity="0.45"/>' +
                '<path d="M15 32h10" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" opacity="0.45"/>' +
            '</svg>'
        );
    }

    // =====================================================================
    // SCRIPT LOADER
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
    // TIPOS / CORES
    // =====================================================================

    const EXT_TYPE_MAP = {
        'pdf':  { type: 'pdf' },
        'doc':  { type: 'doc' },
        'docx': { type: 'doc' },
        'txt':  { type: 'doc' },
        'md':   { type: 'doc' },
        'rtf':  { type: 'doc' },
        'odt':  { type: 'doc' },
        'xls':  { type: 'xls' },
        'xlsx': { type: 'xls' },
        'csv':  { type: 'xls' },
        'ods':  { type: 'xls' },
        'jpg':  { type: 'img' },
        'jpeg': { type: 'img' },
        'png':  { type: 'img' },
        'gif':  { type: 'img' },
        'svg':  { type: 'img' },
        'webp': { type: 'img' },
        'bmp':  { type: 'img' },
        'tiff': { type: 'img' },
        'ico':  { type: 'img' },
        'mp3':  { type: 'audio' },
        'wav':  { type: 'audio' },
        'm4a':  { type: 'audio' },
        'ogg':  { type: 'audio' },
        'flac': { type: 'audio' },
        'mp4':  { type: 'video' },
        'mov':  { type: 'video' },
        'avi':  { type: 'video' },
        'mkv':  { type: 'video' },
        'webm': { type: 'video' },
        'zip':  { type: 'archive' },
        'rar':  { type: 'archive' },
        '7z':   { type: 'archive' },
        'tar':  { type: 'archive' },
        'gz':   { type: 'archive' },
        'dwg':  { type: 'cad' },
        'dxf':  { type: 'cad' },
        'skp':  { type: 'cad' },
    };

    const THUMBNAIL_EXTS = ['jpg','jpeg','png','gif','webp','svg','bmp','ico','tiff'];

    function fileMeta(ext) {
        if (!ext) return { type: 'default' };
        const key = String(ext).toLowerCase();
        return EXT_TYPE_MAP[key] || { type: 'default' };
    }

    function toneClassForExtension(ext) { return 'dc-tone-' + fileMeta(ext).type; }

    function isImageExt(ext) {
        return THUMBNAIL_EXTS.indexOf(String(ext || '').toLowerCase()) !== -1;
    }

    function previewKind(mimeType, ext) {
        const t = String(mimeType || '').toLowerCase();
        const e = String(ext || '').toLowerCase();

        if (t.indexOf('image/') === 0 || THUMBNAIL_EXTS.indexOf(e) !== -1) return 'image';
        if (t === 'application/pdf' || e === 'pdf') return 'pdf';
        if (t.indexOf('text/') === 0 ||
            ['txt','md','csv','json','xml','html','css','js','py','log'].indexOf(e) !== -1) return 'text';
        if (['doc','docx','xls','xlsx','ppt','pptx','odt','ods','odp'].indexOf(e) !== -1) return 'office';
        return 'none';
    }

    // =====================================================================
    // ESTADO
    // =====================================================================

    let documentsCache = [];
    let documentsLoaded = false;
    let currentDocument = null;
    let clientsCache = [];
    let clientsLoaded = false;
    let foldersCache = [];
    let foldersLoaded = false;
    let activeFolderId = null;
    let folderFilter = 'all';
    let activeTab = 'preview';
    let viewMode = 'list';

    let detailAbortController = null;
    let historyAbortController = null;
    let officeLinkAbortController = null;

    let zoomLevel = 1;
    let isPanning = false;
    let panStart = { x: 0, y: 0, scrollLeft: 0, scrollTop: 0 };

    let rotationDeg = 0;

    let gdriveSelectedFiles = {};
    let gdriveFilesCache = [];
    let gdriveSearchTimer = null;
    let gdriveStatusCache = null;

    let draggingDocumentId = null;
    let renamingFolderId = null;

    let ctxMenuTarget = null;
    let ctxMenuVisible = false;

    let pendingDeleteFolderId = null;

    // Fila de exclusão de arquivos
    let deleteQueue = [];
    let deleteQueueIndex = 0;

    let visibilitySaveTimer = null;

    let projectSearchTimer = null;
    let projectSearchAbort = null;

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

    function fillFolderSelect(selectEl, selectedId, emptyLabel) {
        if (!selectEl) return;
        selectEl.innerHTML = '<option value="">' + escapeHtml(emptyLabel || 'Sem pasta (solto)') + '</option>';
        foldersCache.forEach(function(f) {
            const opt = document.createElement('option');
            opt.value = f.id;
            opt.textContent = f.name;
            if (selectedId && String(selectedId) === String(f.id)) {
                opt.selected = true;
            }
            selectEl.appendChild(opt);
        });
    }

    // =====================================================================
    // PASTAS
    // =====================================================================

    async function loadFolders(force) {
        if (foldersLoaded && !force) return foldersCache;
        try {
            const data = await api('/api/documents/folders/');
            foldersCache = (data && data.folders) || [];
            foldersLoaded = true;
        } catch (e) {
            foldersCache = [];
            foldersLoaded = true;
        }
        return foldersCache;
    }

    /**
     * Recarrega pastas E lista de arquivos em sequência.
     * Usar sempre que uma operação mudar a distribuição de arquivos
     * entre pastas (mover, excluir, upload, importar, excluir pasta).
     *
     * Isso garante que `document_count` de cada pasta esteja atualizado
     * ao mesmo tempo que a lista de arquivos.
     */
    async function refreshFoldersAndList() {
        foldersLoaded = false;
        documentsLoaded = false;
        await loadFolders(true);
        await loadDocuments(true);
    }

    // =====================================================================
    // ARMAZENAMENTO (PILL NO HEADER)
    // =====================================================================

    async function loadStorageUsage() {
        const pill = document.getElementById('dcStorageFooter');
        const valueEl = document.getElementById('dcStorageValue');
        const fillEl = document.getElementById('dcStorageFill');
        const barEl = document.getElementById('dcStorageBar');

        if (!pill || !valueEl || !fillEl || !barEl) return;

        try {
            const stats = await api('/api/documents/storage-usage/');
            const used = Number(stats && stats.used_bytes) || 0;
            const quota = Number(stats && stats.quota_bytes) || 0;
            const percent = Number(stats && stats.percent) || 0;

            valueEl.textContent = formatBytes(used) + ' / ' + formatBytes(quota);

            const clamped = Math.max(0, Math.min(100, percent));
            fillEl.style.width = clamped + '%';
            barEl.setAttribute('aria-valuenow', String(Math.round(clamped)));

            pill.classList.remove('is-warning', 'is-danger');
            if (clamped >= 90) pill.classList.add('is-danger');
            else if (clamped >= 75) pill.classList.add('is-warning');

            pill.title = 'Armazenamento: ' + formatBytes(used) + ' de ' + formatBytes(quota)
                + ' (' + percent.toFixed(1) + '%)';
        } catch (e) {
            valueEl.textContent = '—';
        }
    }

    // =====================================================================
    // MOVER
    // =====================================================================

    async function moveDocumentToFolder(docId, folderId) {
        const doc = documentsCache.find(function(d) { return d.id === docId; });
        if (!doc) return;

        const currentFolderId = doc.folder || null;
        const targetFolderId = folderId || null;

        if (currentFolderId === targetFolderId) return;

        // Otimista: atualiza local imediatamente
        doc.folder = targetFolderId;
        const folder = foldersCache.find(function(f) { return f.id === targetFolderId; });
        doc.folder_name = folder ? folder.name : null;

        if (currentFolderId) {
            const old = foldersCache.find(function(f) { return f.id === currentFolderId; });
            if (old) old.document_count = Math.max(0, (old.document_count || 0) - 1);
        }
        if (targetFolderId) {
            const nf = foldersCache.find(function(f) { return f.id === targetFolderId; });
            if (nf) nf.document_count = (nf.document_count || 0) + 1;
        }

        renderList();

        try {
            const updated = await api(
                '/api/documents/' + docId + '/move/',
                'POST',
                { folder_id: targetFolderId }
            );
            const idx = documentsCache.findIndex(function(d) { return d.id === docId; });
            if (idx !== -1) documentsCache[idx] = updated;
            if (currentDocument && currentDocument.id === docId) {
                currentDocument = updated;
                renderDetail();
            }

            // Recarrega pastas + lista para sincronizar contadores com o backend
            await refreshFoldersAndList();
            loadStorageUsage();
            showToast(
                targetFolderId ? 'Arquivo movido' : 'Arquivo removido da pasta',
                'success'
            );
        } catch (err) {
            await refreshFoldersAndList();
            showToast(err.message || 'Erro ao mover arquivo', 'error');
        }
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
        loadStorageUsage();
    }

    function getFilteredDocuments() {
        const searchInput = document.getElementById('dcSearchInput');
        const query = (searchInput && searchInput.value || '').trim().toLowerCase();

        let items = documentsCache.slice();

        if (activeFolderId) {
            items = items.filter(function(d) { return d.folder === activeFolderId; });
        } else {
            if (folderFilter === 'loose') {
                items = items.filter(function(d) { return !d.folder; });
            } else if (folderFilter === 'foldered') {
                items = [];
            }
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

    function getVisibleFolders() {
        const searchInput = document.getElementById('dcSearchInput');
        const query = (searchInput && searchInput.value || '').trim().toLowerCase();

        if (activeFolderId !== null) {
            return [];
        }

        if (folderFilter === 'loose') {
            return [];
        }

        let folders = foldersCache.slice();

        if (query) {
            folders = folders.filter(function(f) {
                return (f.name || '').toLowerCase().indexOf(query) !== -1;
            });
        }

        return folders;
    }

    function updateBreadcrumb() {
        const bcEl = document.getElementById('dcBreadcrumb');
        const bcName = document.getElementById('dcBreadcrumbName');
        const sectionTitle = document.getElementById('dcSectionTitle');

        if (!bcEl || !bcName || !sectionTitle) return;

        if (activeFolderId) {
            const folder = foldersCache.find(function(f) { return f.id === activeFolderId; });
            if (folder) {
                bcName.textContent = folder.name;
                bcEl.classList.remove('hidden');
                sectionTitle.textContent = 'Arquivos';
                return;
            }
        }

        bcEl.classList.add('hidden');
        sectionTitle.textContent = 'Arquivos';
    }

    function renderList() {
        const listEl = document.getElementById('dcList');
        if (!listEl) return;

        const items = getFilteredDocuments();
        const folders = getVisibleFolders();

        const countEl = document.getElementById('dcFilesCount');
        if (countEl) countEl.textContent = items.length;

        updateBreadcrumb();

        if (folders.length === 0 && items.length === 0) {
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

        // Pastas
        folders.forEach(function(f) {
            const isRenaming = renamingFolderId === f.id;

            html +=
                '<div class="dc-folder" data-folder-id="' + escapeHtml(f.id) + '">' +
                    '<div class="dc-folder-icon">' + folderSvg() + '</div>' +
                    '<div class="dc-folder-info">';

            if (isRenaming) {
                html += '<input type="text" class="dc-folder-name-input" ' +
                        'data-folder-rename="' + escapeHtml(f.id) + '" ' +
                        'value="' + escapeHtml(f.name) + '" maxlength="100">';
                html += '<div class="dc-folder-meta">' + (f.document_count || 0) + ' arquivo(s)</div>';
            } else {
                html += '<div class="dc-folder-name">' + escapeHtml(f.name) + '</div>';
                html += '<div class="dc-folder-meta">' + (f.document_count || 0) + ' arquivo(s)</div>';
            }

            html += '</div>';

            if (!isRenaming) {
                html +=
                    '<div class="dc-folder-actions">' +
                        '<button class="dc-folder-action" data-folder-action="rename" ' +
                                'data-folder-id="' + escapeHtml(f.id) + '" title="Renomear">' +
                            '<i data-lucide="pencil"></i>' +
                        '</button>' +
                        '<button class="dc-folder-action is-danger" data-folder-action="delete" ' +
                                'data-folder-id="' + escapeHtml(f.id) + '" title="Excluir">' +
                            '<i data-lucide="trash-2"></i>' +
                        '</button>' +
                    '</div>';
            }

            html += '</div>';
        });

        // Arquivos
        items.forEach(function(d) {
            const isSelected = currentId === d.id;
            const toneClass = toneClassForExtension(d.extension);
            const fullName = d.full_name || d.name || '—';
            const folderName = d.folder_name || null;

            const folderLabel = folderName ? folderName : 'Sem pasta';
            const folderClass = folderName ? 'dc-item-folder' : 'dc-item-folder is-empty';
            const metaHTML = '<span class="' + folderClass + '">' + escapeHtml(folderLabel) + '</span>';

            let thumbHTML;
            if (isImageExt(d.extension) && d.file_url) {
                thumbHTML =
                    '<div class="dc-item-thumb ' + toneClass + '">' +
                        '<img src="' + escapeHtml(d.file_url) + '" alt="" loading="lazy">' +
                    '</div>';
            } else {
                thumbHTML =
                    '<div class="dc-item-thumb ' + toneClass + '">' +
                        fileSvg() +
                    '</div>';
            }

            html +=
                '<div class="dc-item ' + toneClass + (isSelected ? ' is-selected' : '') + '" ' +
                     'data-document-id="' + escapeHtml(d.id) + '" draggable="true">' +
                    thumbHTML +
                    '<div class="dc-item-info">' +
                        '<div class="dc-item-name">' + escapeHtml(fullName) + '</div>' +
                        '<div class="dc-item-meta">' + metaHTML + '</div>' +
                    '</div>' +
                    '<button class="dc-item-menu" data-doc-menu="' + escapeHtml(d.id) + '" title="Mais opções">' +
                        '<i data-lucide="more-vertical"></i>' +
                    '</button>' +
                '</div>';
        });

        listEl.innerHTML = html;
        refreshIcons();

        // Bind pastas
        listEl.querySelectorAll('.dc-folder').forEach(function(el) {
            el.addEventListener('click', function(e) {
                if (e.target.closest('.dc-folder-action')) return;
                if (e.target.closest('.dc-folder-name-input')) return;

                const fid = this.dataset.folderId;
                if (fid) setActiveFolder(fid);
            });

            el.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                this.classList.add('is-droptarget');
            });

            el.addEventListener('dragleave', function(e) {
                if (this.contains(e.relatedTarget)) return;
                this.classList.remove('is-droptarget');
            });

            el.addEventListener('drop', function(e) {
                e.preventDefault();
                this.classList.remove('is-droptarget');

                const fid = this.dataset.folderId;
                const docId = e.dataTransfer.getData('text/x-document-id') || draggingDocumentId;
                if (!docId || !fid) return;

                moveDocumentToFolder(docId, fid);
            });
        });

        listEl.querySelectorAll('.dc-folder-action').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const action = this.dataset.folderAction;
                const fid = this.dataset.folderId;
                if (!fid) return;

                if (action === 'rename') {
                    startRenameFolder(fid);
                } else if (action === 'delete') {
                    openDeleteFolderModal(fid);
                }
            });
        });

        const renameInput = listEl.querySelector('.dc-folder-name-input');
        if (renameInput) {
            renameInput.focus();
            renameInput.select();

            renameInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    commitRenameFolder(this.dataset.folderRename, this.value.trim());
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    cancelRenameFolder();
                }
            });

            renameInput.addEventListener('blur', function() {
                setTimeout(function() {
                    if (renamingFolderId) {
                        commitRenameFolder(renamingFolderId, renameInput.value.trim());
                    }
                }, 50);
            });
        }

        // Bind arquivos
        listEl.querySelectorAll('.dc-item').forEach(function(el) {
            const docId = el.dataset.documentId;

            el.addEventListener('click', function(e) {
                if (e.target.closest('.dc-item-menu')) return;
                if (docId) openDocument(docId);
            });

            el.addEventListener('dragstart', function(e) {
                draggingDocumentId = docId;
                el.classList.add('is-dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/x-document-id', docId);
                e.dataTransfer.setData('text/plain', docId);
            });

            el.addEventListener('dragend', function() {
                draggingDocumentId = null;
                el.classList.remove('is-dragging');
                listEl.querySelectorAll('.dc-folder.is-droptarget').forEach(function(f) {
                    f.classList.remove('is-droptarget');
                });
            });
        });

        // Bind menu 3 pontinhos
        listEl.querySelectorAll('.dc-item-menu').forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                e.preventDefault();
                const docId = this.dataset.docMenu;
                if (!docId) return;
                openCtxMenu(this, docId);
            });
        });
    }

    // =====================================================================
    // CONTEXT MENU
    // =====================================================================

    function openCtxMenu(anchorEl, docId) {
        const menu = document.getElementById('dcCtxMenu');
        if (!menu) return;

        closeCtxMenu();

        ctxMenuTarget = docId;
        ctxMenuVisible = true;

        const rect = anchorEl.getBoundingClientRect();
        const menuWidth = 180;

        let left = rect.right - menuWidth;
        let top = rect.bottom + 6;

        if (left < 8) left = 8;
        if (left + menuWidth > window.innerWidth - 8) {
            left = window.innerWidth - menuWidth - 8;
        }
        if (top + 100 > window.innerHeight - 8) {
            top = rect.top - 100 - 6;
        }

        menu.style.left = left + 'px';
        menu.style.top = top + 'px';
        menu.classList.remove('hidden');

        anchorEl.classList.add('is-open');
        refreshIcons();
    }

    function closeCtxMenu() {
        const menu = document.getElementById('dcCtxMenu');
        if (!menu) return;

        menu.classList.add('hidden');
        document.querySelectorAll('.dc-item-menu.is-open').forEach(function(b) {
            b.classList.remove('is-open');
        });

        ctxMenuTarget = null;
        ctxMenuVisible = false;
    }

    function setupCtxMenu() {
        const menu = document.getElementById('dcCtxMenu');
        if (!menu) return;

        menu.querySelectorAll('.dc-ctx-item').forEach(function(item) {
            item.addEventListener('click', function() {
                const action = this.dataset.ctxAction;
                const docId = ctxMenuTarget;
                closeCtxMenu();

                if (!docId) return;

                if (action === 'edit') {
                    openDocument(docId).then(function() {
                        setTimeout(function() {
                            const input = document.getElementById('dcNameInput');
                            const nameEl = document.getElementById('dcDetailName');
                            if (input && nameEl && currentDocument && currentDocument.id === docId) {
                                input.value = currentDocument.name || '';
                                nameEl.classList.add('hidden');
                                input.classList.remove('hidden');
                                input.focus();
                                input.select();
                            }
                        }, 250);
                    });
                } else if (action === 'delete') {
                    // NÃO abre o documento no painel direito — vai direto para o modal
                    enqueueDelete([docId]);
                }
            });
        });

        document.addEventListener('click', function(e) {
            if (!ctxMenuVisible) return;
            if (menu.contains(e.target)) return;
            if (e.target.closest('.dc-item-menu')) return;
            closeCtxMenu();
        });

        document.addEventListener('scroll', function() {
            if (ctxMenuVisible) closeCtxMenu();
        }, true);

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && ctxMenuVisible) closeCtxMenu();
        });
    }

    // =====================================================================
    // SELEÇÃO / NAVEGAÇÃO
    // =====================================================================

    function updateSelectionHighlight() {
        const listEl = document.getElementById('dcList');
        if (!listEl) return;
        const currentId = currentDocument ? currentDocument.id : null;
        listEl.querySelectorAll('.dc-item').forEach(function(el) {
            el.classList.toggle('is-selected', el.dataset.documentId === currentId);
        });
    }

    function setActiveFolder(folderId) {
        activeFolderId = folderId;
        renderList();
    }

    function exitFolder() {
        activeFolderId = null;
        renderList();
    }

    function startRenameFolder(folderId) {
        renamingFolderId = folderId;
        renderList();
    }

    function cancelRenameFolder() {
        renamingFolderId = null;
        renderList();
    }

    async function commitRenameFolder(folderId, newName) {
        if (!folderId) return;
        if (renamingFolderId !== folderId) return;

        renamingFolderId = null;

        if (!newName) {
            renderList();
            return;
        }

        const folder = foldersCache.find(function(f) { return f.id === folderId; });
        if (!folder) {
            renderList();
            return;
        }

        if (folder.name === newName) {
            renderList();
            return;
        }

        const previousName = folder.name;
        folder.name = newName;
        renderList();

        try {
            const updated = await api(
                '/api/documents/folders/' + folderId + '/',
                'PATCH',
                { name: newName }
            );
            const idx = foldersCache.findIndex(function(f) { return f.id === folderId; });
            if (idx !== -1) foldersCache[idx] = updated;
            renderList();
            showToast('Pasta renomeada', 'success');
        } catch (err) {
            folder.name = previousName;
            renderList();
            showToast(err.message || 'Erro ao renomear pasta', 'error');
        }
    }

    // =====================================================================
    // FILTRO (Todos / Pastas / Soltos)
    // =====================================================================

    function setFolderFilter(filter) {
        folderFilter = (filter === 'foldered' || filter === 'loose') ? filter : 'all';

        document.querySelectorAll('.dc-filter-btn').forEach(function(btn) {
            const isActive = btn.dataset.filter === folderFilter;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        try {
            localStorage.setItem('clivo-documents-filter', folderFilter);
        } catch (e) {}

        if (activeFolderId !== null && folderFilter !== 'all') {
            activeFolderId = null;
        }

        renderList();
    }

    function setupFolderFilter() {
        document.querySelectorAll('.dc-filter-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                setFolderFilter(this.dataset.filter);
            });
        });
    }

    // =====================================================================
    // MODAL: NOVA PASTA
    // =====================================================================

    function openNewFolderModal() {
        const form = document.getElementById('dcNewFolderForm');
        const input = document.getElementById('dcNewFolderName');
        if (!form) return;

        form.reset();
        if (input) input.value = '';

        openModal('dcNewFolderModal');
        refreshIcons();

        setTimeout(function() {
            if (input) input.focus();
        }, 100);
    }

    function setupNewFolderModal() {
        const form = document.getElementById('dcNewFolderForm');
        if (!form) return;

        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            const input = document.getElementById('dcNewFolderName');
            const submitBtn = document.getElementById('dcNewFolderSubmitBtn');
            const name = (input && input.value || '').trim();

            if (!name) {
                showToast('Informe o nome da pasta', 'error');
                return;
            }

            submitBtn.disabled = true;
            submitBtn.classList.add('is-loading');

            try {
                const created = await api('/api/documents/folders/', 'POST', { name: name });
                foldersCache.push(created);
                foldersCache.sort(function(a, b) {
                    return a.name.localeCompare(b.name);
                });
                closeModal('dcNewFolderModal');
                renderList();
                showToast('Pasta criada', 'success');
                setActiveFolder(created.id);
            } catch (err) {
                showToast(err.message || 'Erro ao criar pasta', 'error');
            } finally {
                submitBtn.disabled = false;
                submitBtn.classList.remove('is-loading');
            }
        });
    }

    // =====================================================================
    // MODAL: EXCLUIR PASTA
    // =====================================================================

    function openDeleteFolderModal(folderId) {
        const folder = foldersCache.find(function(f) { return f.id === folderId; });
        if (!folder) return;

        pendingDeleteFolderId = folderId;

        const hintEl = document.getElementById('dcDeleteFolderHint');
        const count = folder.document_count || 0;

        if (hintEl) {
            if (count > 0) {
                hintEl.textContent = 'Tem certeza que deseja excluir a pasta "' +
                    folder.name + '"? Os ' + count +
                    ' arquivo(s) dentro dela NÃO serão excluídos — eles voltam a ficar soltos na biblioteca.';
            } else {
                hintEl.textContent = 'Tem certeza que deseja excluir a pasta "' +
                    folder.name + '"? Esta ação não pode ser desfeita.';
            }
        }

        openModal('dcDeleteFolderModal');
        refreshIcons();
    }

    function setupDeleteFolderModal() {
        const btn = document.getElementById('dcDeleteFolderConfirmBtn');
        if (!btn) return;

        btn.addEventListener('click', async function() {
            if (!pendingDeleteFolderId) return;

            btn.disabled = true;
            btn.classList.add('is-loading');

            try {
                await api('/api/documents/folders/' + pendingDeleteFolderId + '/', 'DELETE');
                showToast('Pasta excluída', 'success');

                foldersCache = foldersCache.filter(function(f) {
                    return f.id !== pendingDeleteFolderId;
                });

                if (activeFolderId === pendingDeleteFolderId) {
                    activeFolderId = null;
                }

                closeModal('dcDeleteFolderModal');
                pendingDeleteFolderId = null;

                await refreshFoldersAndList();
            } catch (err) {
                showToast(err.message || 'Erro ao excluir pasta', 'error');
                btn.disabled = false;
                btn.classList.remove('is-loading');
            }
        });
    }

    // =====================================================================
    // MODAL: EXCLUIR ARQUIVO — fila
    // =====================================================================

    function enqueueDelete(docIds) {
        // Monta a fila com os nomes legíveis dos arquivos
        deleteQueue = docIds.map(function(id) {
            const doc = documentsCache.find(function(d) { return d.id === id; });
            return {
                id: id,
                name: doc ? (doc.full_name || doc.name || '—') : '—',
            };
        }).filter(function(item) { return !!item.id; });

        deleteQueueIndex = 0;

        if (!deleteQueue.length) return;

        renderDeleteModal();
        openModal('dcDeleteModal');
        refreshIcons();
    }

    function renderDeleteModal() {
        const nameEl = document.getElementById('dcDeleteFileName');
        const titleEl = document.getElementById('dcDeleteTitle');
        const labelEl = document.getElementById('dcDeleteConfirmLabel');
        const queueEl = document.getElementById('dcDeleteQueue');
        const queueListEl = document.getElementById('dcDeleteQueueList');
        const queueCountEl = document.getElementById('dcDeleteQueueCount');

        if (!deleteQueue.length) return;

        const current = deleteQueue[deleteQueueIndex];

        if (nameEl) nameEl.textContent = current.name;

        if (titleEl) {
            if (deleteQueue.length > 1) {
                titleEl.textContent = 'Excluir arquivos';
            } else {
                titleEl.textContent = 'Excluir arquivo';
            }
        }

        if (labelEl) {
            if (deleteQueue.length > 1 && deleteQueueIndex < deleteQueue.length - 1) {
                labelEl.textContent = 'Excluir e próximo';
            } else {
                labelEl.textContent = 'Excluir';
            }
        }

        // Fila (só se tiver mais de 1)
        if (queueEl && queueListEl && queueCountEl) {
            if (deleteQueue.length > 1) {
                queueEl.classList.remove('hidden');
                queueCountEl.textContent = String(deleteQueue.length - deleteQueueIndex);

                let html = '';
                for (let i = deleteQueueIndex; i < deleteQueue.length; i++) {
                    const item = deleteQueue[i];
                    const cls = (i === deleteQueueIndex) ? ' class="is-current"' : '';
                    html += '<li' + cls + '>' + escapeHtml(item.name) + '</li>';
                }
                queueListEl.innerHTML = html;
            } else {
                queueEl.classList.add('hidden');
                queueListEl.innerHTML = '';
            }
        }
    }

    function setupDelete() {
        const btn = document.getElementById('dcDeleteBtn');
        const confirmBtn = document.getElementById('dcDeleteConfirmBtn');

        if (btn) {
            btn.addEventListener('click', function() {
                if (!currentDocument) return;
                enqueueDelete([currentDocument.id]);
            });
        }

        if (confirmBtn) {
            confirmBtn.addEventListener('click', async function() {
                if (!deleteQueue.length) return;
                if (deleteQueueIndex >= deleteQueue.length) return;

                const current = deleteQueue[deleteQueueIndex];
                const docId = current.id;

                confirmBtn.disabled = true;
                confirmBtn.classList.add('is-loading');

                try {
                    await api('/api/documents/' + docId + '/', 'DELETE');

                    // Remove do cache local
                    documentsCache = documentsCache.filter(function(d) {
                        return d.id !== docId;
                    });

                    // Se era o doc aberto no painel direito, limpa
                    if (currentDocument && currentDocument.id === docId) {
                        currentDocument = null;
                        resetDetail();
                    }

                    // Avança na fila
                    deleteQueueIndex++;

                    if (deleteQueueIndex >= deleteQueue.length) {
                        // Fim da fila
                        const total = deleteQueue.length;
                        closeModal('dcDeleteModal');
                        deleteQueue = [];
                        deleteQueueIndex = 0;

                        showToast(
                            total === 1 ? 'Arquivo excluído' : total + ' arquivos excluídos',
                            'success'
                        );

                        // Recarrega pastas + lista (contadores sincronizados)
                        await refreshFoldersAndList();
                    } else {
                        // Ainda há itens na fila: avança visualmente e recarrega em background
                        renderDeleteModal();
                        await refreshFoldersAndList();
                    }
                } catch (err) {
                    showToast(err.message || 'Erro ao excluir', 'error');
                } finally {
                    confirmBtn.disabled = false;
                    confirmBtn.classList.remove('is-loading');
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
    // VIEW MODE
    // =====================================================================

    function setViewMode(mode) {
        viewMode = (mode === 'grid') ? 'grid' : 'list';

        const listEl = document.getElementById('dcList');
        if (listEl) listEl.dataset.view = viewMode;

        document.querySelectorAll('.dc-view-btn').forEach(function(btn) {
            const isActive = btn.dataset.view === viewMode;
            btn.classList.toggle('is-active', isActive);
            btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        try {
            localStorage.setItem('clivo-documents-view', viewMode);
        } catch (e) {}

        renderList();
    }

    function setupViewToggle() {
        document.querySelectorAll('.dc-view-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                setViewMode(this.dataset.view);
            });
        });
    }

    // =====================================================================
    // DETALHE
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

        setText('dcInfoName', d.full_name || d.name || '—');
        setText('dcInfoType', d.extension ? d.extension.toUpperCase() : '—');
        setText('dcInfoSize', d.size_display || '—');
        setText('dcInfoFolder', d.folder_name || 'Sem pasta');
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
            const toneClass = toneClassForExtension(d.extension);
            iconEl.className = 'dc-detail-icon ' + toneClass;
            iconEl.innerHTML = fileSvg();
        }

        const associateClientSelect = document.getElementById('dcAssociateClientSelect');
        if (associateClientSelect) {
            fillClientSelect(associateClientSelect, d.client, 'Sem cliente');
        }

        const projectSearch = document.getElementById('dcAssociateProjectSearch');
        const projectValue = document.getElementById('dcAssociateProjectValue');
        const projectHint = document.getElementById('dcAssociateProjectHint');
        const projectMenu = document.getElementById('dcProjectMenu');

        if (projectMenu) {
            projectMenu.classList.add('hidden');
            projectMenu.innerHTML = '';
        }

        if (projectSearch && projectValue) {
            if (d.project_name) {
                projectSearch.value = d.project_name;
                projectValue.value = d.project_id || '';
                if (projectHint) projectHint.textContent = 'Associado a "' + d.project_name + '".';
            } else if (d.project_id) {
                projectSearch.value = '';
                projectValue.value = d.project_id;
                if (projectHint) {
                    projectHint.textContent = 'Projeto associado. Busque pelo nome para substituir.';
                }
            } else {
                projectSearch.value = '';
                projectValue.value = '';
                if (projectHint) projectHint.textContent = 'Nenhum projeto associado.';
            }
        }

        const visibilityCheckbox = document.getElementById('dcVisibleToClient');
        const visibilityHint = document.getElementById('dcVisibilityHint');
        if (visibilityCheckbox) {
            visibilityCheckbox.checked = !!d.visible_to_client;
        }
        if (visibilityHint) {
            visibilityHint.textContent = d.visible_to_client
                ? 'O cliente também vê este arquivo.'
                : 'Somente o escritório vê este arquivo.';
        }

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

    function resetRotation() { rotationDeg = 0; }

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

        if (!container || !currentDocument) return;

        const d = currentDocument;
        const kind = previewKind(d.mime_type, d.extension);
        const url = previewUrlFor(d);

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
    // DOCX PREVIEW
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

            renderOfficeError(container, toneClassForExtension(d.extension), d);

            const hint = document.createElement('small');
            hint.style.cssText = 'display:block;margin-top:10px;font-size:11px;color:#c00;max-width:100%;word-break:break-word;';
            hint.textContent = String(e && (e.message || e));
            const office = container.querySelector('.dc-preview-office');
            if (office) office.appendChild(hint);
        }
    }

    function renderOfficePreview(container, d) {
        const toneClass = toneClassForExtension(d.extension);

        container.innerHTML =
            '<div class="dc-preview-office">' +
                '<div class="dc-preview-office-icon ' + toneClass + '">' +
                    '<i data-lucide="file-text"></i>' +
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
                    renderOfficeLocalhostFallback(container, d, toneClass);
                    return;
                }

                mountOfficeViewer(container, data.url, d, toneClass, docId);
            })
            .catch(function(e) {
                if (e.name === 'AbortError') return;
                if (!currentDocument || currentDocument.id !== docId) return;
                renderOfficeError(container, toneClass, d);
            });
    }

    function mountOfficeViewer(container, publicUrl, doc, toneClass, docId) {
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

    function renderOfficeLocalhostFallback(container, doc, toneClass) {
        const url = previewUrlFor(doc);
        container.innerHTML =
            '<div class="dc-preview-office">' +
                '<div class="dc-preview-office-icon ' + toneClass + '">' +
                    '<i data-lucide="file-text"></i>' +
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

    function renderOfficeError(container, toneClass, doc) {
        container.innerHTML =
            '<div class="dc-preview-office">' +
                '<div class="dc-preview-office-icon ' + toneClass + '">' +
                    '<i data-lucide="file-text"></i>' +
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
                if (id) {
                    if (id === 'dcDeleteModal') {
                        deleteQueue = [];
                        deleteQueueIndex = 0;
                    }
                    closeModal(id);
                }
            });
        });

        document.querySelectorAll('.cl-modal-overlay').forEach(function(overlay) {
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay) {
                    if (overlay.id === 'dcDeleteModal') {
                        deleteQueue = [];
                        deleteQueueIndex = 0;
                    }
                    overlay.classList.remove('active');
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
        await loadFolders();
        form.reset();

        const dropzone = document.getElementById('dcDropzone');
        if (dropzone && dropzone._reset) dropzone._reset();

        const select = document.getElementById('dcUploadClient');
        fillClientSelect(select, null, 'Sem cliente');

        const folderSelect = document.getElementById('dcUploadFolder');
        const preFolder = activeFolderId ? activeFolderId : null;
        fillFolderSelect(folderSelect, preFolder, 'Sem pasta (solto)');

        const visibleCheckbox = document.getElementById('dcUploadVisibleToClient');
        if (visibleCheckbox) visibleCheckbox.checked = false;

        openModal('dcUploadModal');
        refreshIcons();
    }

    function setupUpload() {
        const btn = document.getElementById('dcUploadBtn');
        if (btn) {
            btn.addEventListener('click', function() {
                openUploadModal();
            });
        }

        const form = document.getElementById('dcUploadForm');
        if (!form) return;

        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            const fileInput = document.getElementById('dcUploadFile');
            const nameInput = document.getElementById('dcUploadName');
            const clientSelect = document.getElementById('dcUploadClient');
            const projectInput = document.getElementById('dcUploadProject');
            const folderSelect = document.getElementById('dcUploadFolder');
            const visibleCheckbox = document.getElementById('dcUploadVisibleToClient');

            if (!fileInput.files || !fileInput.files.length) {
                showToast('Selecione um arquivo', 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            if (nameInput.value.trim()) formData.append('name', nameInput.value.trim());
            if (clientSelect.value) formData.append('client_id', clientSelect.value);
            if (projectInput.value.trim()) formData.append('project_id', projectInput.value.trim());
            if (folderSelect.value) formData.append('folder_id', folderSelect.value);

            formData.append(
                'visible_to_client',
                (visibleCheckbox && visibleCheckbox.checked) ? 'true' : 'false'
            );

            const submitBtn = document.getElementById('dcUploadSubmitBtn');
            submitBtn.disabled = true;
            submitBtn.classList.add('is-loading');

            try {
                const created = await api('/api/documents/', 'POST', formData);
                showToast('Arquivo enviado', 'success');
                closeModal('dcUploadModal');
                await refreshFoldersAndList();
                if (created && created.id) openDocument(created.id);
            } catch (err) {
                showToast(err.message || 'Erro ao enviar arquivo', 'error');
            } finally {
                submitBtn.disabled = false;
                submitBtn.classList.remove('is-loading');
            }
        });
    }

    // =====================================================================
    // VISIBILIDADE (CHECKBOX)
    // =====================================================================

    function setupVisibilityToggle() {
        const checkbox = document.getElementById('dcVisibleToClient');
        if (!checkbox) return;

        checkbox.addEventListener('change', function() {
            if (!currentDocument) return;

            const docId = currentDocument.id;
            const newValue = !!checkbox.checked;

            const hintEl = document.getElementById('dcVisibilityHint');
            if (hintEl) {
                hintEl.textContent = newValue
                    ? 'O cliente também vê este arquivo.'
                    : 'Somente o escritório vê este arquivo.';
            }

            const idx = documentsCache.findIndex(function(d) { return d.id === docId; });
            if (idx !== -1) {
                documentsCache[idx].visible_to_client = newValue;
            }
            currentDocument.visible_to_client = newValue;
            renderList();

            if (visibilitySaveTimer) clearTimeout(visibilitySaveTimer);
            visibilitySaveTimer = setTimeout(function() {
                persistVisibility(docId, newValue);
            }, 220);
        });
    }

    async function persistVisibility(docId, visible) {
        try {
            const updated = await api(
                '/api/documents/' + docId + '/visibility/',
                'POST',
                { visible_to_client: visible }
            );

            if (currentDocument && currentDocument.id === docId) {
                currentDocument = updated;
            }
            const idx = documentsCache.findIndex(function(d) { return d.id === docId; });
            if (idx !== -1) documentsCache[idx] = updated;

            renderList();
            loadHistory();
            showToast(
                visible ? 'Arquivo visível ao cliente' : 'Arquivo somente do escritório',
                'success'
            );
        } catch (err) {
            showToast(err.message || 'Erro ao alterar visibilidade', 'error');
            await refreshFoldersAndList();
            if (currentDocument && currentDocument.id === docId) {
                try {
                    const fresh = await api('/api/documents/' + docId + '/');
                    currentDocument = fresh;
                    const idx = documentsCache.findIndex(function(d) { return d.id === docId; });
                    if (idx !== -1) documentsCache[idx] = fresh;
                } catch (e) {}
                renderDetail();
            }
        }
    }

    // =====================================================================
    // COMBOBOX DE PROJETO
    // =====================================================================

    function setupProjectCombobox() {
        const input = document.getElementById('dcAssociateProjectSearch');
        const hidden = document.getElementById('dcAssociateProjectValue');
        const menu = document.getElementById('dcProjectMenu');
        if (!input || !hidden || !menu) return;

        function closeMenu() {
            menu.classList.add('hidden');
            menu.innerHTML = '';
        }

        function renderItems(items) {
            menu.innerHTML = '';

            if (!items.length) {
                const empty = document.createElement('div');
                empty.className = 'dc-combobox-item-empty';
                empty.textContent = 'Nenhum projeto encontrado';
                menu.appendChild(empty);
                return;
            }

            items.forEach(function(p) {
                const el = document.createElement('div');
                el.className = 'dc-combobox-item';
                el.dataset.projectId = p.id;
                el.innerHTML =
                    '<i data-lucide="folder-kanban" style="width:13px;height:13px;color:var(--text-tertiary);"></i>' +
                    '<span>' + escapeHtml(p.name || '(sem nome)') + '</span>';
                el.addEventListener('click', function() {
                    input.value = p.name || '';
                    hidden.value = p.id || '';

                    const hintEl = document.getElementById('dcAssociateProjectHint');
                    if (hintEl) {
                        hintEl.textContent = 'Pronto para aplicar: "' + (p.name || '') + '".';
                    }

                    closeMenu();
                });
                menu.appendChild(el);
            });

            refreshIcons();
        }

        input.addEventListener('input', function() {
            const q = this.value.trim();
            hidden.value = '';

            if (projectSearchTimer) clearTimeout(projectSearchTimer);
            if (projectSearchAbort) projectSearchAbort.abort();

            if (!q) { closeMenu(); return; }

            projectSearchTimer = setTimeout(async function() {
                projectSearchAbort = new AbortController();
                try {
                    const res = await fetch(
                        '/api/projects/?search=' + encodeURIComponent(q) + '&limit=8',
                        { credentials: 'same-origin', signal: projectSearchAbort.signal }
                    );
                    if (!res.ok) throw new Error('Falha');
                    const data = await res.json();
                    const items = Array.isArray(data) ? data : (data.results || []);
                    renderItems(items);
                    menu.classList.remove('hidden');
                } catch (e) {
                    if (e.name === 'AbortError') return;
                    renderItems([]);
                    menu.classList.remove('hidden');
                }
            }, 250);
        });

        input.addEventListener('focus', function() {
            if (menu.innerHTML) menu.classList.remove('hidden');
        });

        document.addEventListener('click', function(e) {
            if (menu.classList.contains('hidden')) return;
            if (e.target.closest('#dcProjectCombobox')) return;
            closeMenu();
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeMenu();
        });
    }

    // =====================================================================
    // GOOGLE DRIVE
    // =====================================================================

    function setDriveError(message) {
        const errEl = document.getElementById('dcDriveError');
        const errText = document.getElementById('dcDriveErrorText');
        const errActions = document.getElementById('dcDriveErrorActions');
        if (!errEl || !errText) return;

        if (!message) {
            errEl.classList.add('hidden');
            if (errActions) {
                errActions.style.display = 'none';
                errActions.innerHTML = '';
            }
            return;
        }
        errText.textContent = message;
        if (errActions) {
            errActions.style.display = 'none';
            errActions.innerHTML = '';
        }
        errEl.classList.remove('hidden');
    }

    function setDriveReconnectAction() {
        const errActions = document.getElementById('dcDriveErrorActions');
        if (!errActions) return;
        errActions.innerHTML =
            '<a class="btn-apple btn-apple-primary" ' +
               'href="/accounts/google/login/?process=login&next=/documents/" ' +
               'style="text-decoration:none;margin-top:10px;display:inline-flex;">' +
                'Reconectar conta Google' +
            '</a>';
        errActions.style.display = 'block';
    }

    function showDriveIntro() {
        const introEl = document.getElementById('dcDriveIntro');
        const connectedEl = document.getElementById('dcDriveConnected');
        const loadingEl = document.getElementById('dcDriveLoading');
        if (introEl) introEl.style.display = 'flex';
        if (connectedEl) connectedEl.style.display = 'none';
        if (loadingEl) loadingEl.style.display = 'none';
    }

    function showDriveConnected() {
        const introEl = document.getElementById('dcDriveIntro');
        const connectedEl = document.getElementById('dcDriveConnected');
        const loadingEl = document.getElementById('dcDriveLoading');
        if (introEl) introEl.style.display = 'none';
        if (connectedEl) connectedEl.style.display = 'flex';
        if (loadingEl) loadingEl.style.display = 'none';
    }

    function showDriveLoading() {
        const introEl = document.getElementById('dcDriveIntro');
        const connectedEl = document.getElementById('dcDriveConnected');
        const loadingEl = document.getElementById('dcDriveLoading');
        if (introEl) introEl.style.display = 'none';
        if (connectedEl) connectedEl.style.display = 'none';
        if (loadingEl) loadingEl.style.display = 'flex';
    }

    function setDriveButtonLoading(isLoading) {
        const btn = document.getElementById('dcDriveBtn');
        if (!btn) return;
        if (isLoading) {
            btn.classList.add('is-loading');
            btn.disabled = true;
        } else {
            btn.classList.remove('is-loading');
            btn.disabled = false;
        }
    }

    async function openDriveModal() {
        gdriveSelectedFiles = {};
        updateDriveSummary();
        setDriveError('');

        const introEl = document.getElementById('dcDriveIntro');
        const connectedEl = document.getElementById('dcDriveConnected');
        const loadingEl = document.getElementById('dcDriveLoading');
        if (!introEl || !connectedEl || !loadingEl) return;

        openModal('dcDriveModal');
        showDriveLoading();
        refreshIcons();

        setDriveButtonLoading(true);

        try {
            let status = gdriveStatusCache;
            if (!status) {
                status = await api('/api/documents/gdrive/status/');
                gdriveStatusCache = status;
            }

            const connected = !!(status && status.connected);
            const needsReconnect = !!(status && status.needs_reconnect);

            if (needsReconnect) {
                showDriveIntro();
                setDriveError(
                    'Sua conexão com o Google está incompleta. ' +
                    'Por favor, reconecte sua conta Google para permitir ' +
                    'que o Clivo acesse seu Drive.'
                );
                setDriveReconnectAction();
                return;
            }

            if (!connected) {
                showDriveIntro();
                return;
            }

            showDriveConnected();
            const filesEl = document.getElementById('dcDriveFiles');
            if (filesEl) {
                filesEl.innerHTML = '<p class="dc-drive-empty">Carregando…</p>';
            }
            await loadDriveFiles('');

        } catch (err) {
            showDriveIntro();
        } finally {
            setDriveButtonLoading(false);
        }
    }

    async function enterDriveAndLoadFiles() {
        let connected = false;
        try {
            const status = await api('/api/documents/gdrive/status/');
            gdriveStatusCache = status;
            connected = !!(status && status.connected);
        } catch (e) {
            connected = false;
        }

        if (!connected) {
            window.location.href = '/accounts/google/login/?process=login&next=/documents/';
            return;
        }

        showDriveConnected();

        const filesEl = document.getElementById('dcDriveFiles');
        if (filesEl) {
            filesEl.innerHTML = '<p class="dc-drive-empty">Carregando…</p>';
        }

        await loadDriveFiles('');
    }

    async function loadDriveFiles(query) {
        const listEl = document.getElementById('dcDriveFiles');
        if (!listEl) return;

        setDriveError('');
        listEl.innerHTML = '<p class="dc-drive-empty">Carregando…</p>';

        try {
            const url = '/api/documents/gdrive/list/' + (query ? ('?q=' + encodeURIComponent(query)) : '');
            const data = await api(url);
            gdriveFilesCache = (data && data.files) || [];
            renderDriveFiles();
        } catch (err) {
            const msg = (err && err.message) || 'Erro ao carregar arquivos do Google Drive.';
            setDriveError(msg);

            if (msg.indexOf('incompleta') !== -1 || msg.indexOf('novamente') !== -1) {
                setDriveReconnectAction();
            }

            listEl.innerHTML = '<p class="dc-drive-empty">—</p>';
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
        const driveBtn = document.getElementById('dcDriveBtn');
        if (driveBtn) {
            driveBtn.addEventListener('click', function() {
                openDriveModal();
            });
        }

        const connectBtn = document.getElementById('dcDriveConnectBtn');
        if (connectBtn) {
            connectBtn.addEventListener('click', function() {
                enterDriveAndLoadFiles();
            });
        }

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

                const payload = { files: files };
                if (activeFolderId) {
                    payload.folder_id = activeFolderId;
                }

                try {
                    const result = await api('/api/documents/gdrive/import/', 'POST', payload);
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
                    await refreshFoldersAndList();

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
                submitBtn.classList.add('is-loading');

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

                    await refreshFoldersAndList();
                    renderDetail();
                    loadHistory();
                    updateSelectionHighlight();
                } catch (err) {
                    showToast(err.message || 'Erro ao substituir', 'error');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.classList.remove('is-loading');
                }
            });
        }
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
                    await refreshFoldersAndList();
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
                const hidden = document.getElementById('dcAssociateProjectValue');
                const projectId = hidden ? hidden.value.trim() : '';

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
                    await refreshFoldersAndList();
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

        const refresh = document.getElementById('dcRefreshHistoryBtn');
        if (refresh) refresh.addEventListener('click', loadHistory);

        const newFolderBtn = document.getElementById('dcNewFolderBtn');
        if (newFolderBtn) newFolderBtn.addEventListener('click', openNewFolderModal);

        const bcBack = document.getElementById('dcBreadcrumbBack');
        if (bcBack) bcBack.addEventListener('click', exitFolder);
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
        foldersLoaded = false;
        currentDocument = null;
        activeFolderId = null;
        activeTab = 'preview';
        resetZoom();
        resetRotation();
        gdriveSelectedFiles = {};
        gdriveFilesCache = [];
        gdriveStatusCache = null;
        draggingDocumentId = null;
        renamingFolderId = null;
        ctxMenuTarget = null;
        ctxMenuVisible = false;
        pendingDeleteFolderId = null;
        deleteQueue = [];
        deleteQueueIndex = 0;

        if (visibilitySaveTimer) {
            clearTimeout(visibilitySaveTimer);
            visibilitySaveTimer = null;
        }
        if (projectSearchTimer) {
            clearTimeout(projectSearchTimer);
            projectSearchTimer = null;
        }
        if (projectSearchAbort) {
            projectSearchAbort.abort();
            projectSearchAbort = null;
        }

        try {
            const savedView = localStorage.getItem('clivo-documents-view');
            viewMode = (savedView === 'grid') ? 'grid' : 'list';
        } catch (e) {
            viewMode = 'list';
        }

        try {
            const savedFilter = localStorage.getItem('clivo-documents-filter');
            folderFilter = (savedFilter === 'loose' || savedFilter === 'foldered') ? savedFilter : 'all';
        } catch (e) {
            folderFilter = 'all';
        }

        resetDetail();
        setupModals();
        setupTabs();
        setupUpload();
        setupDrive();
        setupInlineRename();
        setupReplace();
        setupDelete();
        setupDownload();
        setupAssociations();
        setupProjectCombobox();
        setupFilters();
        setupFolderFilter();
        setupZoomButtons();
        setupRotateButtons();
        setupViewToggle();
        setupCtxMenu();
        setupNewFolderModal();
        setupDeleteFolderModal();
        setupVisibilityToggle();

        setupDropzone('dcDropzone', 'dcUploadFile', 'dcDropzoneTitle', 'dcDropzoneSub');
        setupDropzone('dcReplaceDropzone', 'dcReplaceFile', 'dcReplaceDropzoneTitle', 'dcReplaceDropzoneSub');

        setViewMode(viewMode);
        setFolderFilter(folderFilter);

        loadClients();

        loadFolders().then(function() {
            loadDocuments(true);
            loadStorageUsage();
        });
    }

    function unmount() {
        if (detailAbortController) detailAbortController.abort();
        if (historyAbortController) historyAbortController.abort();
        if (officeLinkAbortController) officeLinkAbortController.abort();
        if (gdriveSearchTimer) clearTimeout(gdriveSearchTimer);
        if (visibilitySaveTimer) {
            clearTimeout(visibilitySaveTimer);
            visibilitySaveTimer = null;
        }
        if (projectSearchTimer) {
            clearTimeout(projectSearchTimer);
            projectSearchTimer = null;
        }
        if (projectSearchAbort) {
            projectSearchAbort.abort();
            projectSearchAbort = null;
        }
        closeCtxMenu();
    }

    window.ClivoPages = window.ClivoPages || {};
    window.ClivoPages.documents = {
        mount: mount,
        unmount: unmount,
    };
})();