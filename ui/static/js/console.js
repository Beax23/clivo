(function() {
    'use strict';

    lucide.createIcons();

    const loadingState = document.getElementById('loadingState');
    const appContent = document.getElementById('appContent');
    const userAvatarImg = document.getElementById('userAvatarImg');
    const userAvatarFallback = document.getElementById('userAvatarFallback');
    const wsAvatarImg = document.getElementById('wsAvatarImg');
    const wsAvatarText = document.getElementById('wsAvatarText');

    // =========================================================================
    // THEME
    // =========================================================================
    let currentTheme = localStorage.getItem('clivo-theme') || 'light';
    document.documentElement.setAttribute('data-theme', currentTheme);

    function updateThemeIcon(theme) {
        const wrapper = document.getElementById('themeIconWrapper');
        if (wrapper) {
            const iconName = theme === 'dark' ? 'moon' : 'sun';
            wrapper.innerHTML = '<i class="lucide" data-lucide="' + iconName + '"></i>';
            if (typeof lucide !== 'undefined') lucide.createIcons();
        }
    }
    updateThemeIcon(currentTheme);

    function toggleTheme() {
        currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', currentTheme);
        localStorage.setItem('clivo-theme', currentTheme);
        updateThemeIcon(currentTheme);
        showToast('Tema: ' + (currentTheme === 'dark' ? 'Escuro' : 'Claro'), 'success');
    }

    // =========================================================================
    // COOKIE
    // =========================================================================
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // =========================================================================
    // TOAST
    // =========================================================================
    let toastTimeout = null;
    function showToast(message, type) {
        type = type || 'info';
        const container = document.getElementById('toastContainer');
        while (container.firstChild) container.removeChild(container.firstChild);

        const toast = document.createElement('div');
        toast.className = 'apple-toast apple-toast-' + type;
        const iconMap = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            info: 'fa-info-circle'
        };
        toast.innerHTML =
            '<span class="apple-toast-icon"><i class="fas ' + (iconMap[type] || iconMap.info) + '"></i></span>' +
            '<span class="apple-toast-content">' + message + '</span>' +
            '<button class="apple-toast-close"><i class="fas fa-times"></i></button>';
        container.appendChild(toast);

        toast.querySelector('.apple-toast-close').addEventListener('click', function() {
            toast.classList.add('hiding');
            setTimeout(function() { toast.remove(); }, 300);
        });

        clearTimeout(toastTimeout);
        toastTimeout = setTimeout(function() {
            toast.classList.add('hiding');
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    }

    // =========================================================================
    // LOADING BUTTONS
    // =========================================================================
    function setLoading(button, loading) {
        if (!button) return;
        if (loading) {
            button.disabled = true;
            button.dataset.originalText = button.innerHTML;
            button.innerHTML = '<span class="btn-spinner"></span> Aguarde...';
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.originalText || button.textContent;
            if (typeof lucide !== 'undefined') lucide.createIcons();
        }
    }

    function setLoadingSm(button, loading) {
        if (!button) return;
        if (loading) {
            button.disabled = true;
            button.dataset.originalText = button.innerHTML;
            button.innerHTML = '<span class="btn-spinner"></span>';
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.originalText || button.textContent;
            if (typeof lucide !== 'undefined') lucide.createIcons();
        }
    }

    // =========================================================================
    // API HELPER
    // =========================================================================
    async function apiRequest(url, method, body) {
        const options = {
            method: method || 'GET',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            }
        };
        if (body !== undefined && body !== null) options.body = JSON.stringify(body);

        const response = await fetch(url, options);
        if (response.status === 204) return null;

        let data = null;
        try { data = await response.json(); } catch (e) { /* sem body */ }

        if (!response.ok) {
            const msg = (data && (data.error || data.detail || (data.non_field_errors && data.non_field_errors[0])))
                || 'Erro na requisição';
            const err = new Error(msg);
            err.status = response.status;
            err.data = data;
            throw err;
        }
        return data;
    }

    function unwrapList(data) {
        if (!data) return [];
        return Array.isArray(data) ? data : (data.results || []);
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

    function formatDate(iso) {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            return d.toLocaleDateString('pt-BR', {
                day: '2-digit',
                month: 'short',
                year: 'numeric'
            });
        } catch (e) {
            return '—';
        }
    }

    function formatDateTime(iso) {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            const datePart = d.toLocaleDateString('pt-BR', {
                day: '2-digit', month: '2-digit', year: 'numeric'
            });
            const timePart = d.toLocaleTimeString('pt-BR', {
                hour: '2-digit', minute: '2-digit'
            });
            return datePart + ' ' + timePart;
        } catch (e) {
            return '—';
        }
    }

    function humanizeBytes(numBytes) {
        if (numBytes === null || numBytes === undefined) return null;
        const n = Number(numBytes);
        if (isNaN(n)) return null;
        if (n === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let size = n;
        let i = 0;
        while (size >= 1024 && i < units.length - 1) {
            size /= 1024;
            i += 1;
        }
        return size.toFixed(2) + ' ' + units[i];
    }

    function splitHumanized(human) {
        if (!human) return { value: '—', unit: '' };
        const parts = human.split(' ');
        return { value: parts[0], unit: parts[1] || '' };
    }

    function formatNumber(n) {
        if (n === null || n === undefined) return '—';
        const num = Number(n);
        if (isNaN(num)) return String(n);
        return num.toLocaleString('pt-BR');
    }

    // =========================================================================
    // SESSION & USER
    // =========================================================================
    async function checkSession() {
        try {
            const response = await fetch('/api/auth/session/', { method: 'GET', credentials: 'include' });
            if (!response.ok) { window.location.href = '/login/'; return false; }
            return await response.json();
        } catch (e) {
            window.location.href = '/login/';
            return false;
        }
    }

    async function loadUserData() {
        try {
            const response = await fetch('/api/users/me/', {
                method: 'GET',
                credentials: 'include',
                headers: { 'X-CSRFToken': getCookie('csrftoken') }
            });
            if (!response.ok) throw new Error('Erro ao carregar usuário');
            const user = await response.json();

            const fullName = user.full_name || user.email || 'Usuário';
            const firstName = fullName.split(' ')[0];
            const initial = fullName.charAt(0).toUpperCase();
            const avatarUrl = user.avatar_url || user.avatar || null;

            function showFallback() {
                userAvatarImg.style.display = 'none';
                if (userAvatarFallback) {
                    userAvatarFallback.style.display = 'block';
                    userAvatarFallback.textContent = initial;
                }
                if (wsAvatarImg) wsAvatarImg.style.display = 'none';
                if (wsAvatarText) {
                    wsAvatarText.style.display = 'block';
                    wsAvatarText.textContent = initial;
                }
                const wsAvatarContainer = document.getElementById('wsAvatar');
                if (wsAvatarContainer) wsAvatarContainer.style.background = '';
            }

            function showAvatar() {
                userAvatarImg.style.display = 'block';
                if (userAvatarFallback) userAvatarFallback.style.display = 'none';
                if (wsAvatarImg) {
                    wsAvatarImg.style.display = 'block';
                    wsAvatarImg.style.width = '100%';
                    wsAvatarImg.style.height = '100%';
                    wsAvatarImg.style.objectFit = 'cover';
                    wsAvatarImg.style.borderRadius = '50%';
                    if (wsAvatarText) wsAvatarText.style.display = 'none';
                    const wsAvatarContainer = document.getElementById('wsAvatar');
                    if (wsAvatarContainer) wsAvatarContainer.style.background = 'transparent';
                }
            }

            if (avatarUrl) {
                userAvatarImg.onerror = function() { userAvatarImg.onerror = null; showFallback(); };
                if (wsAvatarImg) wsAvatarImg.onerror = function() { wsAvatarImg.onerror = null; };
                userAvatarImg.src = avatarUrl;
                if (wsAvatarImg) wsAvatarImg.src = avatarUrl;
                showAvatar();
            } else {
                showFallback();
            }

            const wsNameEl = document.getElementById('wsName');
            if (wsNameEl) wsNameEl.textContent = 'Console de ' + firstName;

            return user;
        } catch (e) {
            console.error('Erro ao carregar usuário:', e);
            return null;
        }
    }

    // =========================================================================
    // CHECK CONSOLE ACCESS
    // =========================================================================
    async function checkConsoleAccess() {
        try {
            const response = await fetch('/api/console/members/check-access/', {
                method: 'GET',
                credentials: 'include',
                headers: { 'X-CSRFToken': getCookie('csrftoken') }
            });

            if (!response.ok) {
                window.location.href = '/mesa/';
                return false;
            }

            const data = await response.json();
            if (!data.has_access) {
                window.location.href = '/mesa/';
                return false;
            }
            return true;
        } catch (e) {
            console.error('Erro ao verificar acesso:', e);
            window.location.href = '/mesa/';
            return false;
        }
    }

    // =========================================================================
    // STATE
    // =========================================================================
    let governances = [];
    let selectedGovernanceId = null;
    let selectedCapabilities = [];
    let allCapabilities = [];

    let plans = [];
    let selectedPlanId = null;
    let planFeatures = [];
    let allFeatures = [];
    let allMetrics = [];

    let features = [];
    let selectedFeatureId = null;

    let teamMembers = [];
    let deleteTarget = null;

    let adminWorkspaces = [];
    let adminUsers = [];

    // Storage
    let storageProviders = [];
    let activeProviderKey = null;
    let activeProviderCap = null;
    let activeProviderContracts = [];
    let activeProviderConnections = [];
    let activeBudget = null;
    let activeBreakdown = null;
    let activeBudgetHistory = [];

    // IA
    let aiState = null;
    let aiModelsByProvider = {};

    // =========================================================================
    // GOVERNANÇAS
    // =========================================================================
    async function loadGovernances() {
        try {
            const data = await apiRequest('/api/console/governances/', 'GET');
            governances = unwrapList(data);
            renderGovernances();
        } catch (e) {
            console.error('Erro ao carregar governanças:', e);
        }
    }

    async function loadCapabilities() {
        try {
            const response = await fetch('/api/console/capabilities/by-app/', {
                method: 'GET',
                credentials: 'include',
                headers: { 'X-CSRFToken': getCookie('csrftoken') }
            });
            if (!response.ok) return;

            const data = await response.json();
            allCapabilities = [];
            const select = document.getElementById('capFilter');
            if (!select) return;
            select.innerHTML = '<option value="all">Todos os apps</option>';

            for (const app in data) {
                if (data.hasOwnProperty(app)) {
                    const caps = data[app];
                    allCapabilities.push(...caps);
                    if (caps.length > 0) {
                        const option = document.createElement('option');
                        option.value = app;
                        option.textContent = app.charAt(0).toUpperCase() + app.slice(1);
                        select.appendChild(option);
                    }
                }
            }
            renderCapabilities();
        } catch (e) {
            console.error('Erro ao carregar capabilities:', e);
        }
    }

    async function loadGovernanceCapabilities(id) {
        try {
            const data = await apiRequest('/api/console/governances/' + id + '/capabilities/', 'GET');
            selectedCapabilities = data.map(cap => cap.code);
            renderCapabilities();
        } catch (e) {
            console.error('Erro ao carregar capabilities da governança:', e);
            selectedCapabilities = [];
            renderCapabilities();
        }
    }

    function renderGovernances() {
        const tbody = document.getElementById('governancesTableBody');
        if (!tbody) return;

        const countEl = document.getElementById('govCount');
        if (countEl) countEl.textContent = governances.length;

        if (!governances.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align:center; color:var(--text-tertiary); padding:30px 0; font-size:12.5px;">
                        Nenhuma governança criada
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        governances.forEach(g => {
            const isSelected = g.id === selectedGovernanceId ? 'selected' : '';
            const initial = (g.name || '?').charAt(0).toUpperCase();
            const iconClass = g.is_protected ? 'protected' : '';
            const canDelete = !g.is_protected && !g.is_system;
            const capCount = (g.capabilities_count !== undefined && g.capabilities_count !== null)
                ? g.capabilities_count
                : 0;

            const capBadge = capCount === 0
                ? '<span class="cap-count zero">0</span>'
                : '<span class="cap-count">' + capCount + '</span>';

            const scopeBadge = g.scope
                ? '<span class="scope-badge ' + g.scope + '">' + g.scope + '</span>'
                : '';

            html += `
                <tr class="${isSelected}" data-id="${g.id}">
                    <td>
                        <div class="gov-name-cell">
                            <div class="gov-icon-sm ${iconClass}">${initial}</div>
                            <span class="gov-name-text">${escapeHtml(g.name)}</span>
                            ${scopeBadge}
                        </div>
                    </td>
                    <td style="text-align:center;">${capBadge}</td>
                    <td style="text-align:center;">
                        ${g.is_protected
                            ? '<span class="gov-status-badge protected">Protegida</span>'
                            : '<span class="gov-status-badge">—</span>'}
                    </td>
                    <td class="gov-actions-cell">
                        <div class="gov-actions">
                            <button class="edit-gov-btn" data-id="${g.id}" title="Editar"><i class="lucide" data-lucide="pencil"></i></button>
                            ${canDelete ? `
                                <button class="delete-gov-btn apple-danger" data-id="${g.id}" title="Excluir"><i class="lucide" data-lucide="trash-2"></i></button>
                            ` : ''}
                        </div>
                    </td>
                </tr>
            `;
        });

        tbody.innerHTML = html;
        lucide.createIcons();

        tbody.querySelectorAll('tr[data-id]').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('button')) return;
                const id = this.dataset.id;
                if (selectedGovernanceId === id) deselectGovernance();
                else selectGovernance(id);
            });
        });

        tbody.querySelectorAll('.edit-gov-btn').forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.stopPropagation();
                const id = this.dataset.id;
                const gov = governances.find(g => g.id === id);
                if (gov) {
                    document.getElementById('editGovernanceId').value = id;
                    document.getElementById('govName').value = gov.name;
                    document.getElementById('govDescription').value = gov.description || '';
                    document.getElementById('govProtected').checked = gov.is_protected || false;
                    document.getElementById('cancelGovernanceBtn').style.display = 'inline-flex';
                    document.getElementById('saveGovernanceBtn').innerHTML = '<i class="lucide" data-lucide="check" style="width:14px; height:14px;"></i> Atualizar';
                    lucide.createIcons();
                    await loadGovernanceCapabilities(id);
                    document.getElementById('governanceFormWrapper').scrollIntoView({ behavior: 'smooth' });
                }
            });
        });

        tbody.querySelectorAll('.delete-gov-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const id = this.dataset.id;
                const gov = governances.find(g => g.id === id);
                if (gov) {
                    deleteTarget = { id: gov.id, name: gov.name, type: 'governance' };
                    document.getElementById('deleteTargetName').textContent = `"${gov.name}"`;
                    document.getElementById('confirmDeleteModal').classList.add('active');
                }
            });
        });
    }

    async function selectGovernance(id) {
        selectedGovernanceId = id;
        const gov = governances.find(g => g.id === id);
        if (gov) {
            document.getElementById('selectedGovName').textContent = gov.name;
            document.getElementById('assignCapabilitiesBtn').disabled = false;
            await loadGovernanceCapabilities(id);
            document.querySelectorAll('#governancesTableBody tr').forEach(row => {
                row.classList.toggle('selected', row.dataset.id === id);
            });
        }
    }

    function deselectGovernance() {
        selectedGovernanceId = null;
        selectedCapabilities = [];
        document.getElementById('selectedGovName').textContent = 'Todas as capacidades';
        document.getElementById('assignCapabilitiesBtn').disabled = true;
        renderCapabilities();
        document.querySelectorAll('#governancesTableBody tr').forEach(row => row.classList.remove('selected'));
    }

    function renderCapabilities() {
        const container = document.getElementById('capabilitiesList');
        if (!container) return;
        const filter = document.getElementById('capFilter').value;
        let html = '';

        let caps = allCapabilities;
        if (filter !== 'all') caps = caps.filter(c => c.source_app === filter);

        if (!selectedGovernanceId) {
            const grouped = {};
            caps.forEach(cap => {
                const app = cap.source_app || 'outros';
                if (!grouped[app]) grouped[app] = [];
                grouped[app].push(cap);
            });

            let hasCaps = false;
            for (const app in grouped) {
                if (grouped[app].length === 0) continue;
                hasCaps = true;
                const appLabel = app.charAt(0).toUpperCase() + app.slice(1);
                html += `<div class="apple-cap-group">`;
                html += `<div class="apple-cap-label">${appLabel} (${grouped[app].length})</div>`;
                grouped[app].forEach(cap => {
                    html += `
                        <div class="apple-cap-item" data-app="${cap.source_app}">
                            <input type="checkbox" class="cap-checkbox" value="${cap.code}" disabled>
                            <span class="cap-code">${escapeHtml(cap.code)}</span>
                            <span class="cap-name">${escapeHtml(cap.name)}</span>
                        </div>
                    `;
                });
                html += `</div>`;
            }

            if (!hasCaps) {
                html = `
                    <div class="apple-empty">
                        <i class="lucide" data-lucide="inbox" style="width:32px; height:32px; opacity:0.3; margin-bottom:8px;"></i>
                        <p>Nenhuma capability disponível</p>
                        <span>Nenhuma capability encontrada</span>
                    </div>
                `;
            }

            container.innerHTML = html;
            lucide.createIcons();

            const capCount = document.getElementById('selectedCapCount');
            if (capCount) capCount.textContent = caps.length;
            return;
        }

        const assignedCaps = caps.filter(c => selectedCapabilities.includes(c.code));
        const availableCaps = caps.filter(c => !selectedCapabilities.includes(c.code));

        if (assignedCaps.length > 0) {
            html += `<div class="apple-cap-group">`;
            html += `<div class="apple-cap-label assigned">✓ Atribuídas (${assignedCaps.length})</div>`;
            assignedCaps.forEach(cap => {
                html += `
                    <div class="apple-cap-item assigned" data-app="${cap.source_app}">
                        <input type="checkbox" class="cap-checkbox" value="${cap.code}" checked>
                        <span class="cap-code">${escapeHtml(cap.code)}</span>
                        <span class="cap-name">${escapeHtml(cap.name)}</span>
                    </div>
                `;
            });
            html += `</div>`;
        }

        const grouped = {};
        availableCaps.forEach(cap => {
            const app = cap.source_app || 'outros';
            if (!grouped[app]) grouped[app] = [];
            grouped[app].push(cap);
        });

        let hasAvailable = false;
        for (const app in grouped) {
            if (grouped[app].length === 0) continue;
            hasAvailable = true;
            const appLabel = app.charAt(0).toUpperCase() + app.slice(1);
            html += `<div class="apple-cap-group">`;
            html += `<div class="apple-cap-label">${appLabel} (${grouped[app].length} disponíveis)</div>`;
            grouped[app].forEach(cap => {
                html += `
                    <div class="apple-cap-item" data-app="${cap.source_app}">
                        <input type="checkbox" class="cap-checkbox" value="${cap.code}">
                        <span class="cap-code">${escapeHtml(cap.code)}</span>
                        <span class="cap-name">${escapeHtml(cap.name)}</span>
                    </div>
                `;
            });
            html += `</div>`;
        }

        if (!hasAvailable && assignedCaps.length === 0) {
            html = `
                <div class="apple-empty">
                    <i class="lucide" data-lucide="inbox" style="width:32px; height:32px; opacity:0.3; margin-bottom:8px;"></i>
                    <p>Nenhuma capability disponível</p>
                    <span>Nenhuma capability encontrada</span>
                </div>
            `;
        } else if (!hasAvailable && assignedCaps.length > 0) {
            html += `
                <div class="apple-empty" style="padding:8px 0;">
                    <p style="color:var(--green); font-weight:500;">✓ Todas as capabilities já estão atribuídas</p>
                </div>
            `;
        }

        container.innerHTML = html;
        lucide.createIcons();

        const capCount = document.getElementById('selectedCapCount');
        if (capCount) capCount.textContent = assignedCaps.length;

        container.querySelectorAll('.apple-cap-item .cap-checkbox').forEach(cb => {
            cb.addEventListener('change', function() {
                const code = this.value;
                if (this.checked) {
                    if (!selectedCapabilities.includes(code)) selectedCapabilities.push(code);
                } else {
                    selectedCapabilities = selectedCapabilities.filter(c => c !== code);
                }
                const capCount2 = document.getElementById('selectedCapCount');
                if (capCount2) capCount2.textContent = selectedCapabilities.length;
            });
        });
    }

    // =========================================================================
    // GOVERNANÇAS — FORM
    // =========================================================================
    document.getElementById('governanceForm').addEventListener('submit', async function(e) {
        e.preventDefault();

        const id = document.getElementById('editGovernanceId').value;
        const name = document.getElementById('govName').value.trim();
        const description = document.getElementById('govDescription').value.trim();
        const isProtected = document.getElementById('govProtected').checked;

        if (!name) { showToast('Preencha o nome', 'error'); return; }

        const btn = document.getElementById('saveGovernanceBtn');
        setLoading(btn, true);

        try {
            const key = name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z_]/g, '');
            const url = id ? '/api/console/governances/' + id + '/' : '/api/console/governances/';
            const method = id ? 'PATCH' : 'POST';
            const data = id
                ? { name: name, description: description }
                : { key: key, name: name, description: description, is_protected: isProtected, scope: 'workspace' };

            await apiRequest(url, method, data);

            showToast(id ? 'Governança atualizada!' : 'Governança criada!', 'success');

            document.getElementById('editGovernanceId').value = '';
            document.getElementById('govName').value = '';
            document.getElementById('govDescription').value = '';
            document.getElementById('govProtected').checked = false;
            document.getElementById('cancelGovernanceBtn').style.display = 'none';
            document.getElementById('saveGovernanceBtn').innerHTML = '<i class="lucide" data-lucide="check" style="width:14px; height:14px;"></i> Salvar';
            lucide.createIcons();

            await loadGovernances();
            if (selectedGovernanceId) await loadGovernanceCapabilities(selectedGovernanceId);
            else renderCapabilities();
        } catch (e) {
            showToast(e.message || 'Erro ao salvar governança', 'error');
        } finally {
            setLoading(btn, false);
        }
    });

    document.getElementById('cancelGovernanceBtn').addEventListener('click', function() {
        document.getElementById('editGovernanceId').value = '';
        document.getElementById('govName').value = '';
        document.getElementById('govDescription').value = '';
        document.getElementById('govProtected').checked = false;
        document.getElementById('saveGovernanceBtn').innerHTML = '<i class="lucide" data-lucide="check" style="width:14px; height:14px;"></i> Salvar';
        lucide.createIcons();
        this.style.display = 'none';
        showToast('Edição cancelada', 'info');
    });

    document.getElementById('selectAllCaps').addEventListener('click', function() {
        if (!selectedGovernanceId) { showToast('Selecione uma governança primeiro', 'error'); return; }
        document.querySelectorAll('.apple-cap-item:not(.assigned) .cap-checkbox').forEach(cb => {
            if (!cb.checked) {
                cb.checked = true;
                if (!selectedCapabilities.includes(cb.value)) selectedCapabilities.push(cb.value);
            }
        });
        const capCount = document.getElementById('selectedCapCount');
        if (capCount) capCount.textContent = selectedCapabilities.length;
        showToast('Todas as capacidades disponíveis selecionadas', 'info');
    });

    document.getElementById('deselectAllCaps').addEventListener('click', function() {
        if (!selectedGovernanceId) { showToast('Selecione uma governança primeiro', 'error'); return; }
        document.querySelectorAll('.apple-cap-item:not(.assigned) .cap-checkbox').forEach(cb => {
            cb.checked = false;
            selectedCapabilities = selectedCapabilities.filter(c => c !== cb.value);
        });
        const capCount = document.getElementById('selectedCapCount');
        if (capCount) capCount.textContent = selectedCapabilities.length;
        showToast('Todas as capacidades desmarcadas', 'info');
    });

    document.getElementById('assignCapabilitiesBtn').addEventListener('click', async function() {
        if (!selectedGovernanceId) { showToast('Selecione uma governança primeiro', 'error'); return; }
        const btn = this;
        setLoadingSm(btn, true);
        try {
            await apiRequest(
                '/api/console/governances/' + selectedGovernanceId + '/capabilities/',
                'PATCH',
                { capability_codes: selectedCapabilities }
            );
            showToast(`${selectedCapabilities.length} capacidades atribuídas`, 'success');
            await loadGovernanceCapabilities(selectedGovernanceId);
            await loadGovernances();
        } catch (e) {
            showToast(e.message || 'Erro ao atribuir capacidades', 'error');
        } finally {
            setLoadingSm(btn, false);
        }
    });

    document.getElementById('capFilter').addEventListener('change', renderCapabilities);

    // =========================================================================
    // PLANOS
    // =========================================================================
    async function loadPlans() {
        try {
            const data = await apiRequest('/api/console/plans/', 'GET');
            plans = unwrapList(data);
            renderPlans();
            populatePlanFeatureSelect();
        } catch (e) {
            showToast('Erro ao carregar planos', 'error');
        }
    }

    async function loadMetrics() {
        try {
            const data = await apiRequest('/api/console/metrics/', 'GET');
            allMetrics = unwrapList(data);
        } catch (e) {
            allMetrics = [];
        }
    }

    async function loadAllFeatures() {
        try {
            const data = await apiRequest('/api/console/features/', 'GET');
            allFeatures = unwrapList(data);
            populatePlanFeatureSelect();
        } catch (e) {
            allFeatures = [];
        }
    }

    function populatePlanFeatureSelect() {
        const select = document.getElementById('addFeatureToPlanSelect');
        if (!select) return;
        const current = select.value;
        select.innerHTML = '<option value="">Adicionar feature ao plano...</option>';

        const associatedIds = new Set(planFeatures.map(pf => pf.feature_id));
        allFeatures.forEach(f => {
            if (associatedIds.has(f.id)) return;
            const opt = document.createElement('option');
            opt.value = f.id;
            opt.textContent = f.name;
            select.appendChild(opt);
        });

        if (current && select.querySelector('option[value="' + current + '"]')) {
            select.value = current;
        }

        const btn = document.getElementById('addFeatureToPlanBtn');
        const enabled = !!selectedPlanId && select.value !== '';
        select.disabled = !selectedPlanId;
        btn.disabled = !enabled;
    }

    function extractPlanStorageQuota(plan) {
        if (!plan || !plan.features || !Array.isArray(plan.features)) {
            return { quota_bytes: null, has_quota: false, is_unlimited: false };
        }
        for (const feat of plan.features) {
            if (!feat.limits || !Array.isArray(feat.limits)) continue;
            for (const lim of feat.limits) {
                if (lim.metric_key === 'storage.bytes') {
                    if (lim.limit_value === null || lim.limit_value === undefined) {
                        return { quota_bytes: null, has_quota: true, is_unlimited: true };
                    }
                    return {
                        quota_bytes: parseInt(lim.limit_value, 10),
                        has_quota: true,
                        is_unlimited: false,
                    };
                }
            }
        }
        return { quota_bytes: null, has_quota: false, is_unlimited: false };
    }

    function renderPlans() {
        const tbody = document.getElementById('plansTableBody');
        if (!tbody) return;
        document.getElementById('planCount').textContent = plans.length;

        if (!plans.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center; color:var(--text-tertiary); padding:30px 0; font-size:12.5px;">
                        Nenhum plano criado
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        plans.forEach(p => {
            const isSelected = p.id === selectedPlanId ? 'selected' : '';
            const initial = (p.name || '?').charAt(0).toUpperCase();
            const price = parseFloat(p.price).toFixed(2);
            const canDelete = !p.is_default;
            const wsCount = (p.workspaces_count !== undefined && p.workspaces_count !== null) ? p.workspaces_count : 0;

            const defaultBadge = p.is_default
                ? '<span class="plan-default-badge"><i class="lucide" data-lucide="star" style="width:10px; height:10px;"></i> Inicial</span>'
                : '<span class="plan-default-badge empty">—</span>';

            const quota = extractPlanStorageQuota(p);
            let quotaHtml = '';
            if (!quota.has_quota) {
                quotaHtml = '<span class="plan-quota-cell unconfigured">Não configurada</span>';
            } else if (quota.is_unlimited) {
                quotaHtml = '<span class="plan-quota-cell unlimited">Ilimitada</span>';
            } else {
                const human = humanizeBytes(quota.quota_bytes) || '—';
                quotaHtml = `
                    <div class="plan-quota-cell">
                        <span class="quota-human">${escapeHtml(human)}</span>
                        <span class="quota-bytes">${quota.quota_bytes} B</span>
                    </div>
                `;
            }

            html += `
                <tr class="${isSelected}" data-id="${p.id}">
                    <td>
                        <div class="gov-name-cell">
                            <div class="gov-icon-sm">${initial}</div>
                            <span class="gov-name-text">${escapeHtml(p.name)}</span>
                        </div>
                    </td>
                    <td style="font-size:12px;color:var(--text-secondary);">
                        ${escapeHtml(p.currency)} ${price} / ${escapeHtml(p.billing_period)}
                    </td>
                    <td>${quotaHtml}</td>
                    <td style="text-align:center;">
                        <span class="plan-ws-count ${wsCount === 0 ? 'zero' : ''}">${wsCount}</span>
                    </td>
                    <td style="text-align:center;">${defaultBadge}</td>
                    <td class="gov-actions-cell">
                        <div class="gov-actions">
                            <button class="edit-plan-btn" data-id="${p.id}" title="Editar">
                                <i class="lucide" data-lucide="pencil"></i>
                            </button>
                            ${canDelete ? `
                                <button class="delete-plan-btn apple-danger" data-id="${p.id}" title="Excluir">
                                    <i class="lucide" data-lucide="trash-2"></i>
                                </button>
                            ` : `<span style="font-size:10px; color:var(--text-tertiary);">Padrão</span>`}
                        </div>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        lucide.createIcons();

        tbody.querySelectorAll('tr[data-id]').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('button')) return;
                const id = this.dataset.id;
                if (selectedPlanId === id) deselectPlan();
                else selectPlan(id);
            });
        });

        tbody.querySelectorAll('.edit-plan-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const p = plans.find(x => x.id === this.dataset.id);
                if (p) fillPlanForm(p);
            });
        });

        tbody.querySelectorAll('.delete-plan-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const p = plans.find(x => x.id === this.dataset.id);
                if (!p) return;
                deleteTarget = { id: p.id, name: p.name, type: 'plan' };
                document.getElementById('deleteTargetName').textContent = `"${p.name}"`;
                document.getElementById('confirmDeleteModal').classList.add('active');
            });
        });
    }

    function fillPlanForm(p) {
        document.getElementById('editPlanId').value = p.id;
        document.getElementById('planName').value = p.name;
        document.getElementById('planDescription').value = p.description || '';
        document.getElementById('planPrice').value = p.price;
        document.getElementById('planCurrency').value = p.currency;
        document.getElementById('planBillingPeriod').value = p.billing_period;
        document.getElementById('planTrialDays').value = p.default_trial_days;
        document.getElementById('planIsPublic').checked = p.is_public;
        document.getElementById('planIsActive').checked = p.is_active;
        document.getElementById('planIsDefault').checked = !!p.is_default;

        document.getElementById('cancelPlanBtn').style.display = 'inline-flex';
        document.getElementById('savePlanBtn').innerHTML =
            '<i class="lucide" data-lucide="check" style="width:14px; height:14px;"></i> Atualizar';
        lucide.createIcons();
        document.getElementById('planFormWrapper').scrollIntoView({ behavior: 'smooth' });
    }

    async function selectPlan(id) {
        selectedPlanId = id;
        const p = plans.find(x => x.id === id);
        if (!p) return;
        document.getElementById('selectedPlanName').textContent = p.name;

        try {
            const data = await apiRequest('/api/console/plans/' + id + '/features/', 'GET');
            planFeatures = unwrapList(data);
        } catch (e) {
            planFeatures = [];
        }

        await loadPlanFeatureLimits();

        renderPlanFeatures();
        populatePlanFeatureSelect();

        document.querySelectorAll('#plansTableBody tr').forEach(row => {
            row.classList.toggle('selected', row.dataset.id === id);
        });
    }

    async function loadPlanFeatureLimits() {
        if (!selectedPlanId) return;
        for (const pf of planFeatures) {
            if (pf.limits) continue;
            try {
                const data = await apiRequest(
                    '/api/console/plans/' + selectedPlanId +
                    '/features/' + pf.id + '/limits/',
                    'GET'
                );
                pf.limits = unwrapList(data);
            } catch (e) {
                pf.limits = [];
            }
        }
    }

    function deselectPlan() {
        selectedPlanId = null;
        planFeatures = [];
        document.getElementById('selectedPlanName').textContent = 'Selecione um plano';
        document.getElementById('selectedPlanFeatureCount').textContent = '0';
        renderPlanFeatures();
        populatePlanFeatureSelect();
        document.querySelectorAll('#plansTableBody tr').forEach(row => row.classList.remove('selected'));
    }

    function renderPlanFeatures() {
        const container = document.getElementById('planFeaturesList');
        if (!container) return;
        const countEl = document.getElementById('selectedPlanFeatureCount');
        if (countEl) countEl.textContent = planFeatures.length;

        if (!selectedPlanId) {
            container.innerHTML = `
                <div class="apple-empty">
                    <i class="lucide" data-lucide="package" style="width:32px; height:32px; opacity:0.3; margin-bottom:8px;"></i>
                    <p>Selecione um plano</p>
                    <span>As features do plano aparecerão aqui</span>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        if (!planFeatures.length) {
            container.innerHTML = `
                <div class="apple-empty">
                    <i class="lucide" data-lucide="puzzle" style="width:32px; height:32px; opacity:0.3; margin-bottom:8px;"></i>
                    <p>Nenhuma feature associada</p>
                    <span>Adicione features a este plano</span>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        let html = '';
        planFeatures.forEach(pf => {
            const limits = pf.limits || [];
            const featName = pf.feature_name || pf.feature_key || 'Feature';
            html += `
                <div class="plan-feature-card" data-pf-id="${pf.id}">
                    <div class="plan-feature-header">
                        <div class="pf-icon"><i class="lucide" data-lucide="puzzle" style="width:14px; height:14px;"></i></div>
                        <span class="pf-name">${escapeHtml(featName)}</span>
                        <span class="pf-limits-count">${limits.length} limite${limits.length === 1 ? '' : 's'}</span>
                        <div class="pf-actions">
                            <button class="remove-pf-btn apple-danger" data-pf-id="${pf.id}" title="Remover do plano">
                                <i class="lucide" data-lucide="trash-2" style="width:13px; height:13px;"></i>
                            </button>
                        </div>
                        <i class="lucide pf-chevron" data-lucide="chevron-right"></i>
                    </div>
                    <div class="plan-feature-body">
                        <div class="pf-limits-title">Limites de uso</div>
                        <div class="pf-limits-rows">
                            ${renderPlanFeatureLimitRows(pf, limits)}
                        </div>
                        <div class="pf-add-metric-row">
                            <select class="pf-add-metric-select">
                                <option value="">Adicionar métrica...</option>
                                ${allMetrics
                                    .filter(m => !limits.some(l => l.metric_key === m.key))
                                    .map(m => `<option value="${m.key}">${escapeHtml(m.key)} — ${escapeHtml(m.name)}</option>`)
                                    .join('')}
                            </select>
                            <button class="apple-btn apple-btn-sm pf-add-metric-btn" data-pf-id="${pf.id}">
                                <i class="lucide" data-lucide="plus" style="width:11px; height:11px;"></i> Adicionar
                            </button>
                            <button class="apple-btn apple-btn-sm apple-btn-primary pf-save-limits-btn" data-pf-id="${pf.id}">
                                <i class="lucide" data-lucide="save" style="width:11px; height:11px;"></i> Salvar
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
        lucide.createIcons();

        container.querySelectorAll('.plan-feature-header').forEach(header => {
            header.addEventListener('click', function(e) {
                if (e.target.closest('.pf-actions')) return;
                this.parentElement.classList.toggle('expanded');
            });
        });

        container.querySelectorAll('.remove-pf-btn').forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.stopPropagation();
                const pfId = this.dataset.pfId;
                if (!confirm('Remover esta feature do plano?')) return;
                try {
                    await apiRequest(
                        '/api/console/plans/' + selectedPlanId + '/features/' + pfId + '/',
                        'DELETE'
                    );
                    showToast('Feature removida do plano', 'success');
                    await selectPlan(selectedPlanId);
                } catch (err) {
                    showToast(err.message || 'Erro ao remover', 'error');
                }
            });
        });

        container.querySelectorAll('.pf-add-metric-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const pfId = this.dataset.pfId;
                const card = this.closest('.plan-feature-card');
                const select = card.querySelector('.pf-add-metric-select');
                const metricKey = select.value;
                if (!metricKey) { showToast('Selecione uma métrica', 'error'); return; }

                const pf = planFeatures.find(x => x.id === pfId);
                if (!pf) return;
                if (!pf.limits) pf.limits = [];

                const metric = allMetrics.find(m => m.key === metricKey);
                pf.limits.push({
                    id: null,
                    metric_key: metricKey,
                    metric_name: metric ? metric.name : metricKey,
                    metric_unit: metric ? metric.unit : '',
                    limit_value: null,
                    period: 'monthly',
                    behavior: 'hard_limit',
                });
                renderPlanFeatures();
                const card2 = document.querySelector('.plan-feature-card[data-pf-id="' + pfId + '"]');
                if (card2) card2.classList.add('expanded');
            });
        });

        container.querySelectorAll('.pf-save-limits-btn').forEach(btn => {
            btn.addEventListener('click', async function(e) {
                e.stopPropagation();
                const pfId = this.dataset.pfId;
                const card = this.closest('.plan-feature-card');
                const rows = card.querySelectorAll('.pf-limit-row');

                const limits = [];
                rows.forEach(row => {
                    const metricKey = row.dataset.metric;
                    const limitRaw = row.querySelector('.pf-limit-input').value.trim();
                    const period = row.querySelector('.pf-limit-period').value;
                    const behavior = row.querySelector('.pf-limit-behavior').value;
                    const limitValue = limitRaw === '' ? null : parseInt(limitRaw, 10);
                    if (limitRaw !== '' && (isNaN(limitValue) || limitValue < 0)) return;
                    limits.push({
                        metric_key: metricKey,
                        limit_value: limitValue,
                        period: period,
                        behavior: behavior,
                    });
                });

                setLoadingSm(this, true);
                try {
                    const result = await apiRequest(
                        '/api/console/plans/' + selectedPlanId +
                        '/features/' + pfId + '/limits/',
                        'PUT',
                        { limits: limits }
                    );
                    const pf = planFeatures.find(x => x.id === pfId);
                    if (pf) pf.limits = unwrapList(result);
                    showToast('Limites salvos', 'success');
                    renderPlanFeatures();
                    const card2 = document.querySelector('.plan-feature-card[data-pf-id="' + pfId + '"]');
                    if (card2) card2.classList.add('expanded');
                    await loadPlans();
                } catch (err) {
                    showToast(err.message || 'Erro ao salvar limites', 'error');
                } finally {
                    setLoadingSm(this, false);
                }
            });
        });
    }

    function renderPlanFeatureLimitRows(pf, limits) {
        if (!limits.length) {
            return `<div class="apple-empty" style="padding:10px 0; font-size:11.5px;">Nenhum limite definido</div>`;
        }
        return limits.map(lim => `
            <div class="pf-limit-row" data-metric="${lim.metric_key}">
                <div class="pf-metric">
                    <span class="pf-metric-key">${escapeHtml(lim.metric_key)}</span>
                    <span class="pf-metric-name">${escapeHtml(lim.metric_name || '')}</span>
                </div>
                <input type="number" class="pf-limit-input" placeholder="∞"
                       value="${lim.limit_value === null || lim.limit_value === undefined ? '' : lim.limit_value}"
                       min="0">
                <select class="pf-limit-period">
                    <option value="current" ${lim.period === 'current' ? 'selected' : ''}>Atual</option>
                    <option value="monthly" ${lim.period === 'monthly' ? 'selected' : ''}>Mensal</option>
                    <option value="lifetime" ${lim.period === 'lifetime' ? 'selected' : ''}>Histórico</option>
                </select>
                <select class="pf-limit-behavior">
                    <option value="hard_limit" ${lim.behavior === 'hard_limit' ? 'selected' : ''}>Bloquear</option>
                    <option value="soft_limit" ${lim.behavior === 'soft_limit' ? 'selected' : ''}>Avisar</option>
                    <option value="overage_allowed" ${lim.behavior === 'overage_allowed' ? 'selected' : ''}>Permitir</option>
                </select>
            </div>
        `).join('');
    }

    document.getElementById('addFeatureToPlanSelect').addEventListener('change', populatePlanFeatureSelect);

    document.getElementById('addFeatureToPlanBtn').addEventListener('click', async function() {
        if (!selectedPlanId) return;
        const select = document.getElementById('addFeatureToPlanSelect');
        const featureId = select.value;
        if (!featureId) return;

        setLoadingSm(this, true);
        try {
            await apiRequest(
                '/api/console/plans/' + selectedPlanId + '/features/',
                'POST',
                { feature: featureId }
            );
            showToast('Feature adicionada ao plano', 'success');
            select.value = '';
            await selectPlan(selectedPlanId);
            await loadPlans();
        } catch (e) {
            showToast(e.message || 'Erro ao adicionar feature', 'error');
        } finally {
            setLoadingSm(this, false);
        }
    });

    document.getElementById('planForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const id = document.getElementById('editPlanId').value;
        const payload = {
            name: document.getElementById('planName').value.trim(),
            description: document.getElementById('planDescription').value.trim(),
            price: document.getElementById('planPrice').value,
            currency: document.getElementById('planCurrency').value,
            billing_period: document.getElementById('planBillingPeriod').value,
            default_trial_days: parseInt(document.getElementById('planTrialDays').value, 10) || 0,
            is_public: document.getElementById('planIsPublic').checked,
            is_active: document.getElementById('planIsActive').checked,
            is_default: document.getElementById('planIsDefault').checked,
        };

        if (!payload.name) { showToast('Preencha o nome do plano', 'error'); return; }

        const btn = document.getElementById('savePlanBtn');
        setLoading(btn, true);
        try {
            if (id) {
                await apiRequest('/api/console/plans/' + id + '/', 'PATCH', payload);
                showToast('Plano atualizado', 'success');
            } else {
                await apiRequest('/api/console/plans/', 'POST', payload);
                showToast('Plano criado', 'success');
            }
            resetPlanForm();
            await loadPlans();
        } catch (e) {
            showToast(e.message || 'Erro ao salvar plano', 'error');
        } finally {
            setLoading(btn, false);
        }
    });

    function resetPlanForm() {
        document.getElementById('editPlanId').value = '';
        document.getElementById('planName').value = '';
        document.getElementById('planDescription').value = '';
        document.getElementById('planPrice').value = '';
        document.getElementById('planCurrency').value = 'BRL';
        document.getElementById('planBillingPeriod').value = 'monthly';
        document.getElementById('planTrialDays').value = 0;
        document.getElementById('planIsPublic').checked = true;
        document.getElementById('planIsActive').checked = true;
        document.getElementById('planIsDefault').checked = false;
        document.getElementById('cancelPlanBtn').style.display = 'none';
        document.getElementById('savePlanBtn').innerHTML =
            '<i class="lucide" data-lucide="check" style="width:14px; height:14px;"></i> Salvar';
        lucide.createIcons();
    }

    document.getElementById('cancelPlanBtn').addEventListener('click', function() {
        resetPlanForm();
        showToast('Edição cancelada', 'info');
    });

    // =========================================================================
    // FEATURES
    // =========================================================================
    async function loadFeatures() {
        try {
            const data = await apiRequest('/api/console/features/', 'GET');
            features = unwrapList(data);
            allFeatures = features.slice();
            renderFeatures();
            populatePlanFeatureSelect();
        } catch (e) {
            showToast('Erro ao carregar features', 'error');
        }
    }

    function renderFeatures() {
        const tbody = document.getElementById('featuresTableBody');
        if (!tbody) return;
        document.getElementById('featureCount').textContent = features.length;

        if (!features.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="2" style="text-align:center; color:var(--text-tertiary); padding:30px 0; font-size:12.5px;">
                        Nenhuma feature criada
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        features.forEach(f => {
            const isSelected = f.id === selectedFeatureId ? 'selected' : '';
            const initial = (f.name || '?').charAt(0).toUpperCase();
            const statusBadge = f.is_active
                ? ''
                : '<span class="gov-status-badge" style="background:var(--amber-bg); border-color:rgba(217,119,6,0.2); color:var(--amber); margin-left:8px;">Inativa</span>';

            html += `
                <tr class="${isSelected}" data-id="${f.id}">
                    <td>
                        <div class="gov-name-cell">
                            <div class="gov-icon-sm">${initial}</div>
                            <span class="gov-name-text">${escapeHtml(f.name)}</span>
                            ${statusBadge}
                        </div>
                    </td>
                    <td class="gov-actions-cell">
                        <div class="gov-actions">
                            <button class="edit-feature-btn" data-id="${f.id}" title="Editar">
                                <i class="lucide" data-lucide="pencil"></i>
                            </button>
                            <button class="delete-feature-btn apple-danger" data-id="${f.id}" title="Excluir">
                                <i class="lucide" data-lucide="trash-2"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        lucide.createIcons();

        tbody.querySelectorAll('tr[data-id]').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('button')) return;
                const id = this.dataset.id;
                if (selectedFeatureId === id) deselectFeature();
                else selectFeature(id);
            });
        });

        tbody.querySelectorAll('.edit-feature-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const f = features.find(x => x.id === this.dataset.id);
                if (f) fillFeatureForm(f);
            });
        });

        tbody.querySelectorAll('.delete-feature-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const f = features.find(x => x.id === this.dataset.id);
                if (!f) return;
                deleteTarget = { id: f.id, name: f.name, type: 'feature' };
                document.getElementById('deleteTargetName').textContent = `"${f.name}"`;
                document.getElementById('confirmDeleteModal').classList.add('active');
            });
        });
    }

    function fillFeatureForm(f) {
        document.getElementById('editFeatureId').value = f.id;
        document.getElementById('featureName').value = f.name;
        document.getElementById('featureDescription').value = f.description || '';
        document.getElementById('featureIsActive').checked = f.is_active;

        document.getElementById('cancelFeatureBtn').style.display = 'inline-flex';
        document.getElementById('saveFeatureBtn').innerHTML =
            '<i class="lucide" data-lucide="check" style="width:14px; height:14px;"></i> Atualizar';
        lucide.createIcons();
        document.getElementById('featureFormWrapper').scrollIntoView({ behavior: 'smooth' });
    }

    async function selectFeature(id) {
        selectedFeatureId = id;
        const f = features.find(x => x.id === id);
        if (!f) return;
        document.getElementById('selectedFeatureName').textContent = f.name;

        renderFeatureDetails(f);

        document.querySelectorAll('#featuresTableBody tr').forEach(row => {
            row.classList.toggle('selected', row.dataset.id === id);
        });
    }

    function deselectFeature() {
        selectedFeatureId = null;
        document.getElementById('selectedFeatureName').textContent = 'Selecione uma feature';
        renderFeatureDetails(null);
        document.querySelectorAll('#featuresTableBody tr').forEach(row => row.classList.remove('selected'));
    }

    function renderFeatureDetails(f) {
        const container = document.getElementById('featureDetailsList');
        if (!container) return;

        if (!f) {
            container.innerHTML = `
                <div class="apple-empty">
                    <i class="lucide" data-lucide="puzzle" style="width:32px; height:32px; opacity:0.3; margin-bottom:8px;"></i>
                    <p>Selecione uma feature</p>
                    <span>As informações aparecerão aqui</span>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        const plansWithFeature = [];
        plans.forEach(p => {
            if (p.features && Array.isArray(p.features)) {
                const found = p.features.find(pf => pf.feature_id === f.id);
                if (found) {
                    plansWithFeature.push({
                        plan_name: p.name,
                        limits_count: (found.limits || []).length,
                    });
                }
            }
        });

        const desc = f.description
            ? escapeHtml(f.description)
            : '<span class="muted">Sem descrição</span>';

        let plansHtml;
        if (plansWithFeature.length === 0) {
            plansHtml = '<div class="feature-detail-value muted">Não está associada a nenhum plano</div>';
        } else {
            plansHtml = '<div class="feature-in-plan-list">' + plansWithFeature.map(p => `
                <div class="feature-in-plan-item">
                    <i class="lucide" data-lucide="package" style="width:12px; height:12px; opacity:0.5;"></i>
                    <span class="fip-plan">${escapeHtml(p.plan_name)}</span>
                    <span class="fip-limits">${p.limits_count} limite${p.limits_count === 1 ? '' : 's'}</span>
                </div>
            `).join('') + '</div>';
        }

        container.innerHTML = `
            <div class="feature-detail-block">
                <div class="feature-detail-label">Nome</div>
                <div class="feature-detail-value">${escapeHtml(f.name)}</div>
            </div>
            <div class="feature-detail-block">
                <div class="feature-detail-label">Descrição</div>
                <div class="feature-detail-value">${desc}</div>
            </div>
            <div class="feature-detail-block">
                <div class="feature-detail-label">Identificador técnico</div>
                <div class="feature-detail-value mono">${escapeHtml(f.key)}</div>
            </div>
            <div class="feature-detail-block">
                <div class="feature-detail-label">Status</div>
                <div class="feature-detail-value">${f.is_active ? 'Ativa' : '<span style="color:var(--amber);">Inativa</span>'}</div>
            </div>
            <div class="feature-detail-block">
                <div class="feature-detail-label">Planos que usam esta feature</div>
                ${plansHtml}
            </div>
        `;
        lucide.createIcons();
    }

    document.getElementById('featureForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const id = document.getElementById('editFeatureId').value;
        const payload = {
            name: document.getElementById('featureName').value.trim(),
            description: document.getElementById('featureDescription').value.trim(),
            is_active: document.getElementById('featureIsActive').checked,
        };

        if (!payload.name) { showToast('Preencha o nome da feature', 'error'); return; }

        const btn = document.getElementById('saveFeatureBtn');
        setLoading(btn, true);
        try {
            if (id) {
                await apiRequest('/api/console/features/' + id + '/', 'PATCH', payload);
                showToast('Feature atualizada', 'success');
            } else {
                await apiRequest('/api/console/features/', 'POST', payload);
                showToast('Feature criada', 'success');
            }
            resetFeatureForm();
            await loadFeatures();
            if (selectedFeatureId) {
                const updated = features.find(x => x.id === selectedFeatureId);
                if (updated) renderFeatureDetails(updated);
            }
        } catch (e) {
            showToast(e.message || 'Erro ao salvar feature', 'error');
        } finally {
            setLoading(btn, false);
        }
    });

    function resetFeatureForm() {
        document.getElementById('editFeatureId').value = '';
        document.getElementById('featureName').value = '';
        document.getElementById('featureDescription').value = '';
        document.getElementById('featureIsActive').checked = true;
        document.getElementById('cancelFeatureBtn').style.display = 'none';
        document.getElementById('saveFeatureBtn').innerHTML =
            '<i class="lucide" data-lucide="check" style="width:14px; height:14px;"></i> Salvar';
        lucide.createIcons();
    }

    document.getElementById('cancelFeatureBtn').addEventListener('click', function() {
        resetFeatureForm();
        showToast('Edição cancelada', 'info');
    });

    // =========================================================================
    // IA
    // =========================================================================
    async function loadAiView() {
        await loadAiState();
        await loadAiCosts();
        await loadAiLogs();
    }

    async function loadAiState() {
        try {
            const data = await apiRequest('/api/console/ai/', 'GET');
            aiState = data;
            renderAiState();
            if (aiState && aiState.config) {
                await loadAiModels(aiState.config.provider_key, aiState.config.model);
            }
        } catch (e) {
            console.error('Erro ao carregar estado da IA:', e);
            const stateEl = document.getElementById('aiConfigState');
            if (stateEl) {
                stateEl.className = 'ai-config-state is-inactive';
                stateEl.innerHTML =
                    '<i class="lucide" data-lucide="alert-triangle" style="width:14px; height:14px;"></i>' +
                    '<span>Erro ao carregar configuração: ' + escapeHtml(e.message) + '</span>';
                if (typeof lucide !== 'undefined') lucide.createIcons();
            }
        }
    }

    async function loadAiModels(providerKey, currentModel) {
        const selectEl = document.getElementById('aiModelSelect');
        const customInput = document.getElementById('aiModelCustom');
        const customLabel = document.getElementById('aiModelCustomLabel');
        if (!selectEl) return;

        if (!providerKey) {
            selectEl.innerHTML = '<option value="">Selecione um provider primeiro</option>';
            selectEl.disabled = true;
            if (customInput) { customInput.style.display = 'none'; customInput.value = ''; customInput.required = false; }
            if (customLabel) customLabel.style.display = 'none';
            return;
        }

        selectEl.disabled = true;
        selectEl.innerHTML = '<option value="">Carregando modelos…</option>';

        try {
            const data = await apiRequest(
                '/api/console/ai/models/?provider=' + encodeURIComponent(providerKey),
                'GET'
            );
            aiModelsByProvider[providerKey] = data.models || [];
            renderModelSelect(providerKey, currentModel, data.source, data.warning);
        } catch (e) {
            console.warn('Falha ao carregar modelos:', e);
            aiModelsByProvider[providerKey] = [];
            renderModelSelect(providerKey, currentModel, 'static', e.message);
        }
    }

    function renderModelSelect(providerKey, currentModel, source, warning) {
        const selectEl = document.getElementById('aiModelSelect');
        const customInput = document.getElementById('aiModelCustom');
        const customLabel = document.getElementById('aiModelCustomLabel');
        if (!selectEl) return;

        const models = aiModelsByProvider[providerKey] || [];
        const CUSTOM_VALUE = '__custom__';

        selectEl.innerHTML = '';

        if (!models.length) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Nenhum modelo disponível';
            opt.disabled = true;
            selectEl.appendChild(opt);
        } else {
            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = m.label || m.id;
                selectEl.appendChild(opt);
            });
        }

        const customOpt = document.createElement('option');
        customOpt.value = CUSTOM_VALUE;
        customOpt.textContent = 'Outro (digitar)';
        selectEl.appendChild(customOpt);

        const found = models.some(m => m.id === currentModel);
        const isCustom = !found && !!currentModel;

        if (isCustom) {
            selectEl.value = CUSTOM_VALUE;
            if (customInput) {
                customInput.style.display = 'block';
                customInput.value = currentModel || '';
                customInput.required = true;
            }
            if (customLabel) customLabel.style.display = 'block';
        } else if (found) {
            selectEl.value = currentModel;
            if (customInput) {
                customInput.style.display = 'none';
                customInput.value = '';
                customInput.required = false;
            }
            if (customLabel) customLabel.style.display = 'none';
        } else {
            selectEl.selectedIndex = 0;
            if (customInput) {
                customInput.style.display = 'none';
                customInput.value = '';
                customInput.required = false;
            }
            if (customLabel) customLabel.style.display = 'none';
        }

        selectEl.disabled = false;

        if (source === 'static' && warning) {
            console.info('[ai] modelos estáticos:', warning);
        }

        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    function onAiModelSelectChange() {
        const selectEl = document.getElementById('aiModelSelect');
        const customInput = document.getElementById('aiModelCustom');
        const customLabel = document.getElementById('aiModelCustomLabel');
        if (!selectEl || !customInput) return;

        const isCustom = selectEl.value === '__custom__';
        if (isCustom) {
            customInput.style.display = 'block';
            customInput.required = true;
            if (customLabel) customLabel.style.display = 'block';
            customInput.focus();
        } else {
            customInput.style.display = 'none';
            customInput.value = '';
            customInput.required = false;
            if (customLabel) customLabel.style.display = 'none';
        }
    }

    function renderAiState() {
        const stateEl = document.getElementById('aiConfigState');
        const subEl = document.getElementById('aiStateSub');
        const selectEl = document.getElementById('aiProviderSelect');
        const modelSelect = document.getElementById('aiModelSelect');
        const modelCustom = document.getElementById('aiModelCustom');
        const modelCustomLabel = document.getElementById('aiModelCustomLabel');

        const requestsEl = document.getElementById('aiStatRequests');
        const failedEl = document.getElementById('aiStatFailed');
        const failedHint = document.getElementById('aiStatFailedHint');
        const costEl = document.getElementById('aiStatCost');

        if (aiState && aiState.usage_30d) {
            if (requestsEl) requestsEl.textContent = formatNumber(aiState.usage_30d.requests);
            if (failedEl) failedEl.textContent = formatNumber(aiState.usage_30d.failed);
            if (failedHint) failedHint.textContent = aiState.usage_30d.error_rate_pct + '% de erro';
            if (costEl) costEl.textContent = aiState.usage_30d.total_cost;
        }

        if (selectEl && aiState) {
            selectEl.innerHTML = '';
            (aiState.available_providers || []).forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.key;
                opt.textContent = p.name + (p.is_active ? '' : ' (inativo)');
                if (!p.is_active) opt.disabled = true;
                selectEl.appendChild(opt);
            });
        }

        if (!aiState || !aiState.config) {
            if (stateEl) {
                stateEl.className = 'ai-config-state is-inactive';
                stateEl.innerHTML =
                    '<i class="lucide" data-lucide="alert-triangle" style="width:14px; height:14px;"></i>' +
                    '<span>Nenhuma config de IA. ' +
                    escapeHtml((aiState && aiState.config_error) || 'Escolha um provider e salve.') +
                    '</span>';
            }
            if (subEl) subEl.textContent = 'Não configurada';
            if (modelSelect) {
                modelSelect.innerHTML = '<option value="">Selecione um provider primeiro</option>';
                modelSelect.disabled = true;
            }
            if (modelCustom) {
                modelCustom.style.display = 'none';
                modelCustom.value = '';
                modelCustom.required = false;
            }
            if (modelCustomLabel) modelCustomLabel.style.display = 'none';
            if (typeof lucide !== 'undefined') lucide.createIcons();
            return;
        }

        const cfg = aiState.config;

        if (selectEl) selectEl.value = cfg.provider_key;
        if (subEl) subEl.textContent = cfg.provider_name + ' · ' + cfg.model;

        if (stateEl) {
            if (cfg.is_active) {
                stateEl.className = 'ai-config-state is-active';
                stateEl.innerHTML =
                    '<i class="lucide" data-lucide="check-circle" style="width:14px; height:14px;"></i>' +
                    '<span>Config ativa: <strong>' +
                    escapeHtml(cfg.provider_name) + ' / ' + escapeHtml(cfg.model) +
                    '</strong>' +
                    (cfg.updated_by_email
                        ? ' · atualizada por ' + escapeHtml(cfg.updated_by_email)
                        : '') +
                    '</span>';
            } else {
                stateEl.className = 'ai-config-state is-inactive';
                stateEl.innerHTML =
                    '<i class="lucide" data-lucide="pause-circle" style="width:14px; height:14px;"></i>' +
                    '<span><strong>IA pausada.</strong> Chamadas sem provider_key caem no fallback do settings.</span>';
            }
        }

        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    async function loadAiCosts() {
        const days = document.getElementById('aiCostDays')?.value || '30';
        const tbody = document.getElementById('aiCostsTableBody');
        if (!tbody) return;

        tbody.innerHTML =
            '<tr><td colspan="5" style="text-align:center; padding:30px 0; font-size:12.5px; color:var(--text-tertiary);">Carregando…</td></tr>';

        try {
            const data = await apiRequest(
                '/api/console/ai/costs/by-operation/?days=' + days,
                'GET'
            );
            const rows = data.results || [];

            if (!rows.length) {
                tbody.innerHTML =
                    '<tr><td colspan="5" style="text-align:center; padding:30px 0; font-size:12.5px; color:var(--text-tertiary);">Nenhuma chamada registrada no período</td></tr>';
                return;
            }

            tbody.innerHTML = rows.map(r => `
                <tr>
                    <td style="font-size:12px;color:var(--text-primary);">${escapeHtml(r.operation)}</td>
                    <td style="font-size:12px;color:var(--text-secondary);">${escapeHtml(r.provider_name)}</td>
                    <td style="font-size:12px;text-align:right;color:var(--text-secondary);">${r.count}</td>
                    <td style="font-size:12px;text-align:right;color:var(--text-tertiary);font-variant-numeric:tabular-nums;">${formatNumber(r.tokens)}</td>
                    <td style="font-size:12px;text-align:right;color:var(--text-primary);font-variant-numeric:tabular-nums;">${escapeHtml(r.total_cost)}</td>
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML =
                '<tr><td colspan="5" style="text-align:center; padding:30px 0; color:var(--red);">Erro ao carregar custos: ' + escapeHtml(e.message) + '</td></tr>';
        }
    }

    async function loadAiLogs() {
        const days = document.getElementById('aiLogsDays')?.value || '30';
        const status = document.getElementById('aiLogsStatus')?.value || '';
        const tbody = document.getElementById('aiLogsTableBody');
        const countEl = document.getElementById('aiLogsCount');
        if (!tbody) return;

        tbody.innerHTML =
            '<tr><td colspan="10" style="text-align:center; padding:30px 0; font-size:12.5px; color:var(--text-tertiary);">Carregando…</td></tr>';

        let url = '/api/console/ai/logs/?days=' + days + '&limit=200';
        if (status) url += '&status=' + encodeURIComponent(status);

        try {
            const data = await apiRequest(url, 'GET');
            const rows = data.results || [];

            if (countEl) countEl.textContent = String(data.count || rows.length);

            if (!rows.length) {
                tbody.innerHTML =
                    '<tr><td colspan="10" style="text-align:center; padding:30px 0; font-size:12.5px; color:var(--text-tertiary);">Nenhuma chamada no período</td></tr>';
                return;
            }

            tbody.innerHTML = rows.map(log => {
                const statusCls = 'is-' + (log.status || 'failed');
                const statusLabel = ({
                    'success': 'OK',
                    'failed': 'Falha',
                    'timeout': 'Timeout',
                    'rate_limited': 'Rate limit',
                })[log.status] || log.status;
                return `
                    <tr class="ai-log-row">
                        <td class="cell-mono">${formatDateTime(log.occurred_at)}</td>
                        <td>${escapeHtml(log.provider_key)}</td>
                        <td class="cell-mono">${escapeHtml(log.model || '—')}</td>
                        <td>${escapeHtml(log.operation || '—')}</td>
                        <td style="text-align:center;"><span class="ai-status-badge ${statusCls}">${escapeHtml(statusLabel)}</span></td>
                        <td class="cell-num">${log.latency_ms !== null && log.latency_ms !== undefined ? log.latency_ms + ' ms' : '—'}</td>
                        <td class="cell-num">${log.input_units !== null && log.input_units !== undefined ? formatNumber(log.input_units) : '—'}</td>
                        <td class="cell-num">${log.output_units !== null && log.output_units !== undefined ? formatNumber(log.output_units) : '—'}</td>
                        <td class="cell-num">${log.estimated_cost || '—'}</td>
                        <td class="cell-error" title="${escapeHtml(log.error_message || '')}">${escapeHtml(log.error_message || '')}</td>
                    </tr>
                `;
            }).join('');
        } catch (e) {
            tbody.innerHTML =
                '<tr><td colspan="10" style="text-align:center; padding:30px 0; color:var(--red);">Erro ao carregar logs: ' + escapeHtml(e.message) + '</td></tr>';
        }
    }

    document.getElementById('aiProviderSelect').addEventListener('change', async function() {
        const providerKey = this.value;
        await loadAiModels(providerKey, null);
    });

    document.getElementById('aiModelSelect').addEventListener('change', onAiModelSelectChange);

    document.getElementById('aiConfigForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const providerKey = document.getElementById('aiProviderSelect').value;
        const modelSelect = document.getElementById('aiModelSelect');
        const modelCustom = document.getElementById('aiModelCustom');

        let model = modelSelect ? modelSelect.value : '';
        if (model === '__custom__') {
            model = (modelCustom ? modelCustom.value : '').trim();
        }

        if (!providerKey) { showToast('Selecione um provider', 'error'); return; }
        if (!model || model === '__custom__') { showToast('Informe o modelo', 'error'); return; }

        const btn = document.getElementById('aiConfigSaveBtn');
        setLoading(btn, true);
        try {
            await apiRequest('/api/console/ai/set-provider/', 'POST', {
                provider_key: providerKey,
                model: model,
            });
            showToast('Config de IA atualizada', 'success');
            await loadAiState();
        } catch (e) {
            showToast(e.message || 'Erro ao salvar config', 'error');
        } finally {
            setLoading(btn, false);
        }
    });

    document.getElementById('aiCostDays').addEventListener('change', loadAiCosts);
    document.getElementById('aiLogsDays').addEventListener('change', loadAiLogs);
    document.getElementById('aiLogsStatus').addEventListener('change', loadAiLogs);

    // =========================================================================
    // ARMAZENAMENTO
    // =========================================================================

    function showStorageLoading(show) {
        const el = document.getElementById('storageLoading');
        if (el) el.style.display = show ? 'flex' : 'none';
    }

    function showStorageContent(show) {
        const el = document.getElementById('storageContent');
        if (el) el.style.display = show ? 'flex' : 'none';
    }

    function showStorageEmpty(show) {
        const el = document.getElementById('storageEmptyState');
        if (el) el.style.display = show ? 'block' : 'none';
    }

    function renderStorageEmptyState() {
        const el = document.getElementById('storageEmptyState');
        if (!el) return;
        el.innerHTML = `
            <i class="lucide" data-lucide="hard-drive" style="width:44px; height:44px;"></i>
            <p>Nenhum provider de armazenamento cadastrado</p>
            <span>Cadastre um provider para começar a administrar a capacidade operacional.</span>
        `;
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    async function loadStorageView() {
        const switchEl = document.getElementById('storageProviderSwitch');
        if (switchEl) switchEl.style.display = 'none';
        showStorageEmpty(false);
        showStorageContent(false);
        showStorageLoading(true);

        try {
            const data = await apiRequest('/api/console/providers/', 'GET');
            storageProviders = unwrapList(data);
        } catch (e) {
            storageProviders = [];
        }

        let visible = storageProviders.filter(p => p.category === 'storage');
        if (visible.length === 0) {
            const b2 = storageProviders.find(p => p.key === 'backblaze_b2');
            if (b2) visible = [b2];
        }

        showStorageLoading(false);

        if (visible.length === 0) {
            renderStorageEmptyState();
            showStorageEmpty(true);
            return;
        }

        if (visible.length > 1) {
            renderStorageProviderSwitch(visible);
        } else if (switchEl) {
            switchEl.style.display = 'none';
        }

        if (!activeProviderKey || !visible.some(p => p.key === activeProviderKey)) {
            const b2 = visible.find(p => p.key === 'backblaze_b2');
            activeProviderKey = b2 ? b2.key : visible[0].key;
        }

        await loadProviderData();

        showStorageContent(true);
        renderStorageAll();
    }

    function renderStorageProviderSwitch(providers) {
        const el = document.getElementById('storageProviderSwitch');
        if (!el) return;
        el.style.display = 'inline-flex';

        let options = '';
        providers.forEach(p => {
            const sel = p.key === activeProviderKey ? 'selected' : '';
            options += `<option value="${escapeHtml(p.key)}" ${sel}>${escapeHtml(p.name)}</option>`;
        });

        el.innerHTML = `
            <i class="lucide" data-lucide="database" style="width:14px; height:14px; opacity:0.5;"></i>
            <select id="storageProviderSelect" aria-label="Provider de armazenamento">
                ${options}
            </select>
        `;
        if (typeof lucide !== 'undefined') lucide.createIcons();

        const select = document.getElementById('storageProviderSelect');
        if (select) {
            select.addEventListener('change', function() {
                const key = this.value;
                if (key === activeProviderKey) return;
                activeProviderKey = key;
                activeProviderCap = null;
                activeProviderContracts = [];
                activeProviderConnections = [];
                activeBudget = null;
                activeBreakdown = null;
                activeBudgetHistory = [];
                loadProviderData().then(() => renderStorageAll());
            });
        }
    }

    async function loadProviderData() {
        const provider = storageProviders.find(p => p.key === activeProviderKey);
        if (!provider) return;

        try {
            const cap = await apiRequest(
                '/api/console/storage/provider-cap/?provider_key=' + encodeURIComponent(provider.key),
                'GET'
            );
            activeProviderCap = cap;
        } catch (e) {
            activeProviderCap = null;
        }

        try {
            const contracts = await apiRequest(
                '/api/console/providers/' + provider.id + '/contracts/',
                'GET'
            );
            activeProviderContracts = unwrapList(contracts);
        } catch (e) {
            activeProviderContracts = [];
        }

        try {
            const conns = await apiRequest(
                '/api/console/providers/' + provider.id + '/connections/',
                'GET'
            );
            activeProviderConnections = unwrapList(conns);
        } catch (e) {
            activeProviderConnections = [];
        }

        try {
            const budget = await apiRequest('/api/console/storage/budget/', 'GET');
            activeBudget = { ok: true, data: budget };
        } catch (e) {
            if (e.status === 404) {
                activeBudget = { ok: false, reason: 'not_configured', error: e.message };
            } else if (e.status === 409) {
                activeBudget = {
                    ok: false,
                    reason: (e.data && e.data.code) || 'conflict',
                    error: e.message,
                };
            } else {
                activeBudget = { ok: false, reason: 'error', error: e.message };
            }
        }

        try {
            const breakdown = await apiRequest('/api/console/storage/budget/breakdown/', 'GET');
            activeBreakdown = { ok: true, data: breakdown };
        } catch (e) {
            activeBreakdown = { ok: false, error: e.message };
        }

        try {
            const history = await apiRequest('/api/console/storage/budget/history/?limit=20', 'GET');
            activeBudgetHistory = unwrapList(history);
        } catch (e) {
            activeBudgetHistory = [];
        }
    }

    function renderStorageAll() {
        const provider = storageProviders.find(p => p.key === activeProviderKey);
        renderStorageCapSection(provider);
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    function renderStorageCapSection(provider) {
        const el = document.getElementById('storageCapSection');
        if (!el) return;

        if (!provider) {
            el.innerHTML = '';
            return;
        }

        const cap = activeProviderCap;

        const includedRaw = cap ? cap.included_storage_bytes : null;
        const usageBytes = cap ? cap.usage_bytes : null;
        const isConfigured = !!(cap && cap.is_configured);
        const includedHuman = humanizeBytes(includedRaw);
        const usageHuman = humanizeBytes(usageBytes);

        let capFigureHtml;
        if (!isConfigured) {
            capFigureHtml = `<span class="storage-hero-figure-value muted">Não cadastrado</span>`;
        } else {
            const capSplit = splitHumanized(includedHuman);
            capFigureHtml = `<span class="storage-hero-figure-value">${escapeHtml(capSplit.value)}<span class="unit">${escapeHtml(capSplit.unit)}</span></span>`;
        }

        let usageFigureHtml;
        if (usageBytes === null || usageBytes === undefined) {
            usageFigureHtml = `<span class="storage-hero-figure-value muted">Desconhecido</span>`;
        } else {
            const usageSplit = splitHumanized(usageHuman);
            usageFigureHtml = `<span class="storage-hero-figure-value">${escapeHtml(usageSplit.value)}<span class="unit">${escapeHtml(usageSplit.unit)}</span></span>`;
        }

        let usageBarHtml = '';
        if (isConfigured && includedRaw && includedRaw > 0 && usageBytes !== null && usageBytes !== undefined) {
            const pct = Math.min(100, (usageBytes / includedRaw) * 100);
            const pctRaw = (usageBytes / includedRaw) * 100;
            let fillCls = '';
            let pctCls = '';
            if (pctRaw >= 100) { fillCls = 'is-blocked'; pctCls = 'is-blocked'; }
            else if (pctRaw >= 80) { fillCls = 'is-warning'; pctCls = 'is-warning'; }

            usageBarHtml = `
                <div class="storage-usage-block">
                    <div class="storage-usage-track">
                        <div class="storage-usage-fill ${fillCls}" style="width:${pct}%;"></div>
                    </div>
                    <div class="storage-usage-meta">
                        <span>Uso em relação ao teto</span>
                        <span class="usage-percent ${pctCls}">${pctRaw.toFixed(1)}%</span>
                    </div>
                </div>
            `;
        }

        let syncNoteHtml = '';
        if (cap && cap.last_snapshot_fetched_at) {
            const isStale = !!cap.usage_is_stale;
            const lastStatus = cap.last_snapshot_status || '';
            if (lastStatus === 'error' && cap.last_snapshot_error) {
                syncNoteHtml = `
                    <div class="storage-note error">
                        <i class="lucide" data-lucide="alert-circle"></i>
                        <div>Última tentativa de sincronização falhou: ${escapeHtml(cap.last_snapshot_error)}</div>
                    </div>
                `;
            } else if (isStale) {
                syncNoteHtml = `
                    <div class="storage-note warning">
                        <i class="lucide" data-lucide="clock"></i>
                        <div>O último snapshot de uso está desatualizado.</div>
                    </div>
                `;
            }
        }

        let versionsNoteHtml = '';
        if (cap && cap.last_snapshot_payload) {
            const totalVersions = cap.last_snapshot_payload.total_versions_count;
            const activeVersions = cap.last_snapshot_payload.active_versions_count;
            if (
                typeof totalVersions === 'number' &&
                typeof activeVersions === 'number' &&
                totalVersions > activeVersions
            ) {
                const extras = totalVersions - activeVersions;
                versionsNoteHtml = `
                    <div class="storage-note info">
                        <i class="lucide" data-lucide="layers"></i>
                        <div>
                            ${extras} versão${extras === 1 ? '' : 'ões'} antiga${extras === 1 ? '' : 's'}
                            ${extras === 1 ? 'está' : 'estão'} sendo contabilizada${extras === 1 ? '' : 's'}
                            no uso — o Backblaze B2 cobra por todas as versões, não só a ativa.
                        </div>
                    </div>
                `;
            }
        }

        let notConfiguredNote = '';
        if (!isConfigured) {
            notConfiguredNote = `
                <div class="storage-note info">
                    <i class="lucide" data-lucide="info"></i>
                    <div>
                        Cadastre o <strong>teto operacional</strong> no contrato ativo do provider.
                        A API do Backblaze B2 não expõe este valor — ele é preenchido manualmente
                        a partir do console web (Caps &amp; Alerts).
                    </div>
                </div>
            `;
        }

        let lastSyncHint = '';
        if (cap && cap.last_snapshot_fetched_at) {
            const when = formatDateTime(cap.last_snapshot_fetched_at);
            const lastStatus = cap.last_snapshot_status || '';
            let stateText = 'ok';
            if (lastStatus === 'error') stateText = 'falhou';
            else if (lastStatus === 'unavailable') stateText = 'indisponível';
            lastSyncHint = `Sincronizado em ${escapeHtml(when)} · ${escapeHtml(stateText)}`;
        } else {
            lastSyncHint = 'Nunca sincronizado';
        }

        const contract = activeProviderContracts
            .filter(c => c.is_active)
            .sort((a, b) => (b.started_at || '').localeCompare(a.started_at || ''))[0];

        let actionBtn;
        if (contract) {
            actionBtn = `
                <button class="apple-btn apple-btn-secondary" id="storageEditContractBtn">
                    <i class="lucide" data-lucide="pencil" style="width:12px; height:12px;"></i>
                    Editar contrato
                </button>
            `;
        } else {
            actionBtn = `
                <button class="apple-btn apple-btn-secondary" id="storageCreateContractBtn">
                    <i class="lucide" data-lucide="plus" style="width:12px; height:12px;"></i>
                    Cadastrar contrato
                </button>
            `;
        }

        el.innerHTML = `
            <div class="storage-section-head">
                <div class="storage-section-head-left">
                    <span class="storage-section-title">
                        <i class="lucide" data-lucide="hard-drive"></i>
                        ${escapeHtml(provider.name)}
                    </span>
                    <span class="storage-section-subtitle">
                        Teto contratado e quanto já foi usado dele.
                    </span>
                </div>
                <div class="storage-section-actions">
                    ${actionBtn}
                </div>
            </div>

            <div class="storage-hero">
                <div class="storage-hero-figure">
                    <span class="storage-hero-figure-label">Teto</span>
                    ${capFigureHtml}
                    <span class="storage-hero-figure-hint">Capacidade contratada</span>
                </div>
                <div class="storage-hero-divider"></div>
                <div class="storage-hero-figure">
                    <span class="storage-hero-figure-label">Em uso</span>
                    ${usageFigureHtml}
                    <span class="storage-hero-figure-hint">${escapeHtml(lastSyncHint)}</span>
                </div>
            </div>

            ${usageBarHtml}
            ${syncNoteHtml}
            ${versionsNoteHtml}
            ${notConfiguredNote}
        `;

        const btnEdit = document.getElementById('storageEditContractBtn');
        if (btnEdit && contract) {
            btnEdit.addEventListener('click', function() {
                openContractModal(contract, provider);
            });
        }
        const btnCreate = document.getElementById('storageCreateContractBtn');
        if (btnCreate) {
            btnCreate.addEventListener('click', function() {
                openContractModal(null, provider);
            });
        }

        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    // =========================================================================
    // CONTRACT MODAL
    // =========================================================================

    function openContractModal(contract, provider) {
        const modal = document.getElementById('contractModal');
        const isEdit = !!contract;

        document.getElementById('contractModalTitle').textContent =
            isEdit ? 'Editar contrato' : 'Novo contrato';

        document.getElementById('contractEditId').value = isEdit ? contract.id : '';
        document.getElementById('contractProviderId').value = provider ? provider.id : '';
        document.getElementById('contractName').value = isEdit ? contract.name : '';
        document.getElementById('contractBillingPeriod').value =
            isEdit && contract.billing_period ? contract.billing_period : 'monthly';
        document.getElementById('contractCurrency').value =
            isEdit && contract.currency ? contract.currency : 'BRL';
        document.getElementById('contractFixedCost').value =
            isEdit && contract.fixed_cost !== null && contract.fixed_cost !== undefined
                ? contract.fixed_cost : '';
        document.getElementById('contractStartedAt').value =
            isEdit && contract.started_at ? contract.started_at : '';
        document.getElementById('contractEndsAt').value =
            isEdit && contract.ends_at ? contract.ends_at : '';
        document.getElementById('contractExternalReference').value =
            isEdit && contract.external_reference ? contract.external_reference : '';
        document.getElementById('contractIncludedStorageBytes').value =
            isEdit && contract.included_storage_bytes !== null &&
            contract.included_storage_bytes !== undefined
                ? contract.included_storage_bytes : '';
        document.getElementById('contractNotes').value =
            isEdit && contract.notes ? contract.notes : '';
        document.getElementById('contractIsActive').checked =
            isEdit ? !!contract.is_active : true;

        updateContractStorageHint();
        modal.classList.add('active');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    function updateContractStorageHint() {
        const input = document.getElementById('contractIncludedStorageBytes');
        const hint = document.getElementById('contractIncludedStorageHint');
        if (!input || !hint) return;

        const raw = input.value.trim();
        if (raw === '') { hint.textContent = ''; return; }
        const n = parseInt(raw, 10);
        if (isNaN(n) || n < 0) { hint.textContent = ''; return; }
        const human = humanizeBytes(n);
        hint.textContent = human ? '≈ ' + human : '';
    }

    document.getElementById('contractIncludedStorageBytes').addEventListener('input', updateContractStorageHint);

    document.getElementById('contractForm').addEventListener('submit', async function(e) {
        e.preventDefault();

        const id = document.getElementById('contractEditId').value;
        const providerId = document.getElementById('contractProviderId').value;
        const name = document.getElementById('contractName').value.trim();
        if (!name) { showToast('Preencha o nome do contrato', 'error'); return; }

        const startedAt = document.getElementById('contractStartedAt').value;
        if (!startedAt) { showToast('Preencha a data de início', 'error'); return; }

        const storageRaw = document.getElementById('contractIncludedStorageBytes').value.trim();
        let storageBytes = null;
        if (storageRaw !== '') {
            const n = parseInt(storageRaw, 10);
            if (isNaN(n) || n < 0) {
                showToast('Teto de armazenamento inválido', 'error');
                return;
            }
            storageBytes = n;
        }

        const fixedCostRaw = document.getElementById('contractFixedCost').value.trim();
        const fixedCost = fixedCostRaw === '' ? null : fixedCostRaw;
        const endsAt = document.getElementById('contractEndsAt').value || null;

        const payload = {
            provider: providerId,
            name: name,
            billing_period: document.getElementById('contractBillingPeriod').value,
            currency: document.getElementById('contractCurrency').value,
            fixed_cost: fixedCost,
            included_storage_bytes: storageBytes,
            external_reference: document.getElementById('contractExternalReference').value.trim(),
            started_at: startedAt,
            ends_at: endsAt,
            notes: document.getElementById('contractNotes').value.trim(),
            is_active: document.getElementById('contractIsActive').checked,
        };

        const btn = document.getElementById('contractSubmitBtn');
        setLoading(btn, true);

        try {
            if (id) {
                await apiRequest('/api/console/contracts/' + id + '/', 'PATCH', payload);
                showToast('Contrato atualizado', 'success');
            } else {
                await apiRequest(
                    '/api/console/providers/' + providerId + '/contracts/',
                    'POST',
                    payload
                );
                showToast('Contrato criado', 'success');
            }
            document.getElementById('contractModal').classList.remove('active');

            await loadProviderData();
            renderStorageAll();
        } catch (err) {
            showToast(err.message || 'Erro ao salvar contrato', 'error');
        } finally {
            setLoading(btn, false);
        }
    });

    // =========================================================================
    // WORKSPACES (ADMIN)
    // =========================================================================
    async function loadWorkspacesAdmin() {
        try {
            const data = await apiRequest('/api/console/workspaces/', 'GET');
            adminWorkspaces = unwrapList(data);
            renderWorkspacesAdmin();
        } catch (e) {
            console.error('Erro ao carregar workspaces:', e);
            showToast('Erro ao carregar workspaces', 'error');
        }
    }

    function renderWorkspacesAdmin() {
        const tbody = document.getElementById('workspacesTableBody');
        if (!tbody) return;
        const countEl = document.getElementById('workspaceCount');
        if (countEl) countEl.textContent = adminWorkspaces.length;

        const q = (document.getElementById('workspaceSearch')?.value || '').toLowerCase().trim();
        let list = adminWorkspaces;
        if (q) {
            list = list.filter(w =>
                (w.name || '').toLowerCase().includes(q) ||
                (w.slug || '').toLowerCase().includes(q) ||
                (w.city || '').toLowerCase().includes(q)
            );
        }

        if (!list.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align:center; color:var(--text-tertiary); padding:30px 0; font-size:12.5px;">
                        ${adminWorkspaces.length === 0 ? 'Nenhum workspace criado' : 'Nenhum workspace encontrado'}
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        list.forEach(w => {
            const initial = (w.name || '?').charAt(0).toUpperCase();
            const location = [w.city, w.state].filter(Boolean).join(' · ') || '—';

            const planHtml = w.plan_name
                ? '<div style="font-size:12px;color:var(--text-primary);font-weight:500;">' + escapeHtml(w.plan_name) + '</div>'
                    + '<div style="font-size:10.5px;color:var(--text-tertiary);">'
                    + escapeHtml(w.plan_currency || '') + ' ' + escapeHtml(w.plan_price || '0')
                    + '</div>'
                : '<span style="color:var(--text-tertiary);font-size:12px;">Sem plano</span>';

            html += `
                <tr data-id="${w.id}">
                    <td>
                        <div class="gov-name-cell">
                            <div class="gov-icon-sm">${initial}</div>
                            <div style="min-width:0;">
                                <div class="gov-name-text">${escapeHtml(w.name)}</div>
                                <div style="font-size:10.5px;color:var(--text-tertiary);font-family:ui-monospace,monospace;">${escapeHtml(w.slug)}</div>
                            </div>
                        </div>
                    </td>
                    <td>${planHtml}</td>
                    <td style="text-align:center;font-size:12.5px;font-weight:500;">${w.members_count || 0}</td>
                    <td style="font-size:12px;color:var(--text-secondary);">${escapeHtml(location)}</td>
                    <td style="text-align:center;font-size:12px;color:var(--text-tertiary);">${formatDate(w.created_at)}</td>
                    <td style="text-align:right;">
                        <button class="ws-change-plan-btn" data-id="${w.id}" title="Mudar plano">
                            <i class="lucide" data-lucide="repeat" style="width:12px; height:12px;"></i>
                            Mudar plano
                        </button>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        if (typeof lucide !== 'undefined') lucide.createIcons();

        tbody.querySelectorAll('.ws-change-plan-btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                const wsId = this.dataset.id;
                openChangePlanModal(wsId);
            });
        });
    }

    async function openChangePlanModal(workspaceId) {
        const ws = adminWorkspaces.find(x => x.id === workspaceId);
        if (!ws) {
            showToast('Workspace não encontrado', 'error');
            return;
        }

        document.getElementById('changePlanWorkspaceId').value = ws.id;
        document.getElementById('changePlanWorkspaceName').textContent = ws.name;
        document.getElementById('changePlanCurrentPlan').textContent = ws.plan_name
            ? `Plano atual: ${ws.plan_name}`
            : 'Sem plano ativo';

        const select = document.getElementById('changePlanSelect');
        select.innerHTML = '<option value="">Selecione um plano...</option>';

        const currentKey = ws.plan_key || null;
        const availablePlans = plans.filter(p => p.is_active && p.key !== currentKey);

        if (availablePlans.length === 0) {
            const opt = document.createElement('option');
            opt.value = '';
            opt.disabled = true;
            opt.textContent = currentKey
                ? 'Nenhum outro plano ativo disponível'
                : 'Nenhum plano ativo cadastrado';
            select.appendChild(opt);
            document.getElementById('changePlanSubmitBtn').disabled = true;
        } else {
            availablePlans.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.key;
                opt.textContent = `${p.name} — ${p.currency} ${parseFloat(p.price).toFixed(2)} / ${p.billing_period}`;
                select.appendChild(opt);
            });
            document.getElementById('changePlanSubmitBtn').disabled = false;
        }

        document.getElementById('changePlanReason').value = 'manual';
        document.getElementById('changePlanModal').classList.add('active');
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    document.getElementById('changePlanForm').addEventListener('submit', async function(e) {
        e.preventDefault();

        const workspaceId = document.getElementById('changePlanWorkspaceId').value;
        const planKey = document.getElementById('changePlanSelect').value;
        const reason = document.getElementById('changePlanReason').value;

        if (!workspaceId) { showToast('Workspace inválido', 'error'); return; }
        if (!planKey) { showToast('Escolha um plano', 'error'); return; }

        const btn = document.getElementById('changePlanSubmitBtn');
        setLoading(btn, true);

        try {
            const result = await apiRequest(
                '/api/console/workspaces/' + workspaceId + '/change-plan/',
                'POST',
                { plan_key: planKey, reason: reason }
            );

            const planName = result.plan_name || planKey;
            showToast(`Plano alterado para "${planName}"`, 'success');

            document.getElementById('changePlanModal').classList.remove('active');

            await loadWorkspacesAdmin();
            await loadPlans();
        } catch (err) {
            showToast(err.message || 'Erro ao trocar plano', 'error');
        } finally {
            setLoading(btn, false);
        }
    });

    // =========================================================================
    // USERS (ADMIN)
    // =========================================================================
    async function loadUsersAdmin() {
        try {
            const data = await apiRequest('/api/console/users/', 'GET');
            adminUsers = unwrapList(data);
            renderUsersAdmin();
        } catch (e) {
            console.error('Erro ao carregar usuários:', e);
            showToast('Erro ao carregar usuários', 'error');
        }
    }

    function renderUsersAdmin() {
        const tbody = document.getElementById('usersTableBody');
        if (!tbody) return;
        const countEl = document.getElementById('userCount');
        if (countEl) countEl.textContent = adminUsers.length;

        const q = (document.getElementById('userSearch')?.value || '').toLowerCase().trim();
        let list = adminUsers;
        if (q) {
            list = list.filter(u =>
                (u.email || '').toLowerCase().includes(q) ||
                (u.full_name || '').toLowerCase().includes(q)
            );
        }

        if (!list.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" style="text-align:center; color:var(--text-tertiary); padding:30px 0; font-size:12.5px;">
                        ${adminUsers.length === 0 ? 'Nenhum usuário cadastrado' : 'Nenhum usuário encontrado'}
                    </td>
                </tr>
            `;
            return;
        }

        let html = '';
        list.forEach(u => {
            const name = u.full_name || u.email || '—';
            const initial = (name || '?').charAt(0).toUpperCase();
            const wsCount = (u.workspaces_count !== undefined && u.workspaces_count !== null) ? u.workspaces_count : 0;

            html += `
                <tr data-id="${u.id}">
                    <td>
                        <div class="gov-name-cell">
                            <div class="gov-icon-sm">${initial}</div>
                            <span class="gov-name-text">${escapeHtml(name)}</span>
                        </div>
                    </td>
                    <td style="font-size:12px;color:var(--text-secondary);">${escapeHtml(u.email || '—')}</td>
                    <td style="text-align:center;font-size:12.5px;font-weight:500;">${wsCount}</td>
                    <td style="text-align:center;font-size:12px;color:var(--text-tertiary);">${formatDate(u.created_at)}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        if (typeof lucide !== 'undefined') lucide.createIcons();
    }

    document.getElementById('workspaceSearch')?.addEventListener('input', renderWorkspacesAdmin);
    document.getElementById('userSearch')?.addEventListener('input', renderUsersAdmin);

    // =========================================================================
    // EQUIPE
    // =========================================================================
    async function loadTeamData() {
        try {
            const response = await fetch('/api/console/members/', {
                method: 'GET',
                credentials: 'include',
                headers: { 'X-CSRFToken': getCookie('csrftoken') }
            });
            if (!response.ok) {
                teamMembers = [];
                renderTeam();
                return;
            }
            const data = await response.json();
            const results = unwrapList(data);
            teamMembers = results.map(m => ({
                id: m.id,
                name: m.user_full_name || (m.user_email ? m.user_email.split('@')[0] : 'Usuário'),
                email: m.user_email,
                avatar: m.user_avatar || null,
            }));
            renderTeam();
        } catch (e) {
            teamMembers = [];
            renderTeam();
        }
    }

    function renderTeam() {
        const tbody = document.getElementById('teamTableBody');
        if (!tbody) return;
        const countEl = document.getElementById('teamCount');
        if (countEl) countEl.textContent = teamMembers.length;

        if (!teamMembers.length) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="3" style="text-align:center; color:var(--text-tertiary); padding:30px 0; font-size:13px;">
                        <i class="lucide" data-lucide="users" style="width:24px; height:24px; display:block; margin:0 auto 8px; opacity:0.3;"></i>
                        Nenhum membro na equipe
                    </td>
                </tr>
            `;
            lucide.createIcons();
            return;
        }

        let html = '';
        teamMembers.forEach(m => {
            const initial = (m.name || m.email || '?').charAt(0).toUpperCase();
            const avatarHtml = m.avatar
                ? `<img src="${escapeHtml(m.avatar)}" alt="${escapeHtml(m.name)}">`
                : `<span>${initial}</span>`;
            html += `
                <tr>
                    <td>
                        <span class="user-avatar">${avatarHtml}</span>
                        ${escapeHtml(m.name || m.email)}
                    </td>
                    <td>${escapeHtml(m.email)}</td>
                    <td style="text-align:right;">
                        <div class="apple-table-actions">
                            <button class="delete-team-btn apple-danger" data-id="${m.id}" title="Remover">
                                <i class="lucide" data-lucide="trash-2"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        lucide.createIcons();

        tbody.querySelectorAll('.delete-team-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const m = teamMembers.find(x => x.id === this.dataset.id);
                if (!m) return;
                deleteTarget = { id: m.id, name: m.name || m.email, type: 'team' };
                document.getElementById('deleteTargetName').textContent = `"${m.name || m.email}"`;
                document.getElementById('confirmDeleteModal').classList.add('active');
            });
        });
    }

    document.getElementById('addTeamMemberBtn').addEventListener('click', function() {
        document.getElementById('addMemberForm').reset();
        document.getElementById('addMemberModal').classList.add('active');
        document.getElementById('memberEmail').focus();
    });

    document.getElementById('addMemberForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const email = document.getElementById('memberEmail').value.trim();
        if (!email) { showToast('Preencha o email', 'error'); return; }

        const btn = document.getElementById('addMemberSubmitBtn');
        setLoading(btn, true);
        try {
            await apiRequest('/api/console/members/', 'POST', { email });
            showToast(email + ' adicionado ao Console', 'success');
            document.getElementById('addMemberModal').classList.remove('active');
            document.getElementById('addMemberForm').reset();
            await loadTeamData();
        } catch (e) {
            showToast(e.message || 'Erro ao adicionar membro', 'error');
        } finally {
            setLoading(btn, false);
        }
    });

    // =========================================================================
    // CONFIRM DELETE
    // =========================================================================
    document.getElementById('confirmDeleteBtn').addEventListener('click', async function() {
        if (!deleteTarget) return;
        const btn = this;
        setLoading(btn, true);

        try {
            if (deleteTarget.type === 'governance') {
                await apiRequest('/api/console/governances/' + deleteTarget.id + '/', 'DELETE');
                if (selectedGovernanceId === deleteTarget.id) deselectGovernance();
                await loadGovernances();
                showToast('Governança removida', 'success');
            } else if (deleteTarget.type === 'plan') {
                await apiRequest('/api/console/plans/' + deleteTarget.id + '/', 'DELETE');
                if (selectedPlanId === deleteTarget.id) deselectPlan();
                await loadPlans();
                showToast('Plano removido', 'success');
            } else if (deleteTarget.type === 'feature') {
                await apiRequest('/api/console/features/' + deleteTarget.id + '/', 'DELETE');
                if (selectedFeatureId === deleteTarget.id) deselectFeature();
                await loadFeatures();
                showToast('Feature removida', 'success');
            } else if (deleteTarget.type === 'team') {
                await apiRequest('/api/console/members/' + deleteTarget.id + '/', 'DELETE');
                await loadTeamData();
                showToast('Membro removido', 'success');
            }
            deleteTarget = null;
            document.getElementById('confirmDeleteModal').classList.remove('active');
        } catch (e) {
            showToast(e.message || 'Erro ao remover item', 'error');
        } finally {
            setLoading(btn, false);
        }
    });

    // =========================================================================
    // MODAL CONTROLS
    // =========================================================================
    document.querySelectorAll('.apple-modal-close, [data-modal]').forEach(el => {
        el.addEventListener('click', function() {
            const modalId = this.dataset.modal;
            if (modalId) {
                const modal = document.getElementById(modalId);
                if (modal) modal.classList.remove('active');
            }
        });
    });

    document.querySelectorAll('.apple-modal-overlay').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) this.classList.remove('active');
        });
    });

    // =========================================================================
    // NAVEGAÇÃO
    // =========================================================================
    function switchView(viewName) {
        const views = ['governances', 'plans', 'features', 'storage', 'workspaces', 'users', 'team', 'ai'];
        const titles = {
            governances: 'Governanças',
            plans: 'Planos',
            features: 'Features',
            storage: 'Armazenamento',
            workspaces: 'Workspaces',
            users: 'Usuários',
            team: 'Equipe',
            ai: 'IA',
        };

        views.forEach(v => {
            const el = document.getElementById('view' + v.charAt(0).toUpperCase() + v.slice(1));
            if (el) el.style.display = v === viewName ? 'flex' : 'none';
        });

        document.querySelectorAll('.sidebar-nav a').forEach(link => {
            link.classList.toggle('active', link.dataset.nav === viewName);
        });

        const titleEl = document.getElementById('pageTitle');
        if (titleEl) titleEl.textContent = titles[viewName] || 'Console';

        if (viewName === 'governances') { loadGovernances(); loadCapabilities(); }
        if (viewName === 'plans') { loadPlans(); loadMetrics(); loadAllFeatures(); }
        if (viewName === 'features') { loadFeatures(); loadPlans(); }
        if (viewName === 'storage') { loadStorageView(); }
        if (viewName === 'workspaces') {
            loadPlans();
            loadWorkspacesAdmin();
        }
        if (viewName === 'users') { loadUsersAdmin(); }
        if (viewName === 'team') { loadTeamData(); }
        if (viewName === 'ai') { loadAiView(); }
    }

    // =========================================================================
    // LOGOUT
    // =========================================================================
    async function handleLogout() {
        const btn = document.getElementById('logoutBtn');
        setLoadingSm(btn, true);
        try {
            const response = await fetch('/api/auth/logout/', {
                method: 'POST',
                credentials: 'include',
                headers: { 'X-CSRFToken': getCookie('csrftoken') }
            });
            if (response.ok) window.location.href = '/login/';
            else { showToast('Erro ao fazer logout', 'error'); setLoadingSm(btn, false); }
        } catch (e) {
            showToast('Erro ao fazer logout', 'error');
            setLoadingSm(btn, false);
        }
    }

    // =========================================================================
    // INIT
    // =========================================================================
    async function init() {
        try {
            const session = await checkSession();
            if (!session) return;

            const user = await loadUserData();
            if (!user) return;

            try { await checkConsoleAccess(); } catch (e) { /* redirect já feito */ }

            await loadPlans();
            await loadMetrics();
            await loadTeamData();

            loadingState.classList.add('hidden');
            appContent.classList.remove('hidden');

            switchView('governances');

            setTimeout(function() {
                lucide.createIcons();
                updateThemeIcon(currentTheme);
            }, 100);

            document.querySelectorAll('.sidebar-nav a').forEach(function(link) {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    const view = this.dataset.nav;
                    if (view) switchView(view);
                });
            });

            document.getElementById('themeToggle').addEventListener('click', toggleTheme);
            document.getElementById('logoutBtn').addEventListener('click', function(e) {
                e.stopPropagation();
                handleLogout();
            });

            document.getElementById('newBtn').addEventListener('click', function() {
                const activeNav = document.querySelector('.sidebar-nav a.active')?.dataset.nav;
                if (activeNav === 'plans') {
                    document.getElementById('planFormWrapper').scrollIntoView({ behavior: 'smooth' });
                    document.getElementById('planName').focus();
                } else if (activeNav === 'features') {
                    document.getElementById('featureFormWrapper').scrollIntoView({ behavior: 'smooth' });
                    document.getElementById('featureName').focus();
                } else if (activeNav === 'governances') {
                    document.getElementById('governanceFormWrapper').scrollIntoView({ behavior: 'smooth' });
                    document.getElementById('govName').focus();
                } else if (activeNav === 'storage') {
                    const provider = storageProviders.find(p => p.key === activeProviderKey);
                    if (provider) {
                        openContractModal(null, provider);
                    } else {
                        showToast('Selecione um provider primeiro', 'info');
                    }
                }
            });
            document.getElementById('searchBtn').addEventListener('click', function() {
                showToast('Busca em desenvolvimento!', 'info');
            });
            document.getElementById('notificationsBtn').addEventListener('click', function() {
                showToast('Notificações em desenvolvimento!', 'info');
            });

        } catch (e) {
            console.error('Erro na inicialização:', e);
            loadingState.innerHTML =
                '<div style="text-align:center; padding:40px;">' +
                '<i class="lucide" data-lucide="alert-triangle" style="width:32px; height:32px; display:block; margin:0 auto 12px; opacity:0.5;"></i>' +
                '<p style="font-weight:500; margin-bottom:4px;">Erro ao carregar a aplicação</p>' +
                '<p style="font-size:13px; color:var(--text-tertiary); margin-bottom:16px;">Tente novamente ou volte ao login</p>' +
                '<button onclick="window.location.href=\'/login/\'" style="padding:8px 20px; border:1px solid var(--border-color); border-radius:var(--radius); background:var(--bg-card); color:var(--text-primary); cursor:pointer; font-family:var(--font);">' +
                'Voltar ao login' +
                '</button>' +
                '</div>';
            lucide.createIcons();
        }
    }

    init();

    // =========================================================================
    // DEBUG GLOBAL (temporário — remover depois)
    // =========================================================================
    window.__clivo = {
        getCapabilities: function() { return selectedCapabilities.slice(); },
        getGovernanceId: function() { return selectedGovernanceId; },
        getAllCapabilities: function() { return allCapabilities.slice(); },
        getGovernances: function() { return governances.slice(); },
        setCapabilities: function(arr) {
            selectedCapabilities = arr.slice();
            renderCapabilities();
        },
        forceRender: function() { renderCapabilities(); },
        countCheckboxes: function() {
            return document.querySelectorAll('.cap-checkbox').length;
        },
        countChecked: function() {
            return document.querySelectorAll('.cap-checkbox:checked').length;
        },
        checkedValues: function() {
            return Array.from(document.querySelectorAll('.cap-checkbox:checked')).map(function(cb) { return cb.value; });
        },
        selectGovernance: function(id) { return selectGovernance(id); },
        deselectGovernance: function() { return deselectGovernance(); },
        getWorkspaces: function() { return adminWorkspaces.slice(); },
        openChangePlan: function(id) { return openChangePlanModal(id); },
        getStorageProviders: function() { return storageProviders.slice(); },
        getActiveProviderKey: function() { return activeProviderKey; },
        getActiveProviderCap: function() { return activeProviderCap; },
        getActiveBudget: function() { return activeBudget; },
        getActiveBreakdown: function() { return activeBreakdown; },
        getActiveBudgetHistory: function() { return activeBudgetHistory.slice(); },
        reloadStorage: function() { return loadStorageView(); },
        openContractModal: function(contract) {
            const provider = storageProviders.find(p => p.key === activeProviderKey);
            return openContractModal(contract || null, provider);
        },
        // IA
        getAiState: function() { return aiState; },
        getAiModels: function(providerKey) { return aiModelsByProvider[providerKey] || []; },
        reloadAi: function() { return loadAiView(); },
        reloadAiState: function() { return loadAiState(); },
        reloadAiCosts: function() { return loadAiCosts(); },
        reloadAiLogs: function() { return loadAiLogs(); },
    };
    console.log('[console.js] Debug disponível em window.__clivo');

})();