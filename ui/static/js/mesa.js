/* =========================================================================
   MESA — página registrada no shell ClivoPages
   ========================================================================= */

(function() {
    'use strict';

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

    function capitalize(s) {
        if (!s) return '';
        return s.charAt(0).toUpperCase() + s.slice(1);
    }

    function refreshIcons(scope) {
        if (typeof window.clivoRefreshIcons === 'function') {
            window.clivoRefreshIcons(scope);
        }
    }

    let currentWorkspace = null;
    let currentGovernanceKey = null;
    let myCapabilities = [];
    let isOwner = false;
    let teamMembers = [];
    let pendingInvitations = [];
    let availableGovernances = [];
    let governanceFilter = '';
    let memberToEdit = null;
    let memberToRemove = null;

    function hasCapability(code) {
        if (isOwner) return true;
        if (myCapabilities.indexOf('*') !== -1) return true;
        return myCapabilities.indexOf(code) !== -1;
    }

    function requireCapability(code, actionLabel) {
        if (hasCapability(code)) return true;
        showToast(
            'Sua governança não permite ' + (actionLabel || 'esta ação') + '.',
            'error'
        );
        return false;
    }

    function applyCapabilitiesToUI() {
        const canView = hasCapability('workspaces.workspace.view');
        const canUpdate = hasCapability('workspaces.workspace.update');

        const notice = document.getElementById('wsReadOnlyNotice');
        if (notice) {
            notice.classList.toggle('hidden', canUpdate || !canView);
        }

        // O card de plano é controlado EXCLUSIVAMENTE pelo shell
        // (renderSidebarPlan em sidebar.html). Não esconder aqui.
    }

    async function loadMyCapabilities() {
        try {
            const data = await api('/api/workspaces/my-capabilities/');
            myCapabilities = (data && data.capabilities) || [];
            currentGovernanceKey = (data && data.governance_key) || null;
            isOwner = !!(data && data.is_owner);

            window.Clivo.capabilities = myCapabilities;
            window.Clivo.isOwner = isOwner;
            window.Clivo.governanceKey = currentGovernanceKey;

            applyCapabilitiesToUI();
        } catch (e) {
            console.error('Falha ao carregar capabilities:', e);
            myCapabilities = [];
            isOwner = false;
            applyCapabilitiesToUI();
        }
    }

    function updateTodayDate() {
        const el = document.getElementById('todayDate');
        if (!el) return;
        const now = new Date();
        el.textContent = now.toLocaleDateString('pt-BR', {
            weekday: 'long', day: 'numeric', month: 'long'
        });
    }

    function updateGreeting() {
        const el = document.getElementById('pageGreeting');
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
        el.textContent = firstName ? (greeting + ', ' + firstName) : 'Início';
    }

    function updateWorkspaceTabVisibility() {
        const tabBtn = document.getElementById('tabWorkspaceBtn');
        if (!tabBtn) return;
        tabBtn.style.display = '';
    }

    function setupViewTabs() {
        const tabs = document.querySelectorAll('#viewTabs button');
        tabs.forEach(function(btn) {
            btn.addEventListener('click', function() {
                tabs.forEach(function(b) { b.classList.remove('active'); });
                this.classList.add('active');
                const tab = this.dataset.tab;
                document.querySelectorAll('.tab-content').forEach(function(c) {
                    c.classList.remove('active');
                });
                const target = document.getElementById('tab' + capitalize(tab));
                if (target) target.classList.add('active');
                if (tab === 'workspace') loadWorkspaceData();
            });
        });
    }

    function setupSubTabs() {
        const tabs = document.querySelectorAll('#subTabs button');
        tabs.forEach(function(btn) {
            btn.addEventListener('click', function() {
                tabs.forEach(function(b) { b.classList.remove('active'); });
                this.classList.add('active');
                const subtab = this.dataset.subtab;
                document.querySelectorAll('.subtab-content').forEach(function(c) {
                    c.classList.remove('active');
                });
                const target = document.getElementById('subtab' + capitalize(subtab));
                if (target) target.classList.add('active');
                if (subtab === 'equipe') loadTeam();
            });
        });
    }

    async function loadWorkspaceData() {
        if (!currentWorkspace) {
            currentWorkspace = window.Clivo.workspace || null;
        }
        if (!currentWorkspace) {
            try {
                currentWorkspace = await api('/api/workspaces/current/');
                window.Clivo.workspace = currentWorkspace;
            } catch (e) {
                showToast('Erro ao carregar workspace', 'error');
                return;
            }
        }

        const nameEl = document.getElementById('wsFieldName');
        const cityEl = document.getElementById('wsFieldCity');
        const stateEl = document.getElementById('wsFieldState');
        const cnpjEl = document.getElementById('wsFieldCnpj');
        if (nameEl) nameEl.value = currentWorkspace.name || '';
        if (cityEl) cityEl.value = currentWorkspace.city || '';
        if (stateEl) stateEl.value = currentWorkspace.state || '';
        if (cnpjEl) cnpjEl.value = currentWorkspace.cnpj || '';

        const wordEl = document.getElementById('deleteConfirmWord');
        if (wordEl) wordEl.textContent = currentWorkspace.name || '';

        applyCapabilitiesToUI();
    }

    function bindWorkspaceForm() {
        const nameEl = document.getElementById('wsFieldName');
        const cityEl = document.getElementById('wsFieldCity');
        const stateEl = document.getElementById('wsFieldState');
        const cnpjEl = document.getElementById('wsFieldCnpj');
        const saveBtn = document.getElementById('wsSaveBtn');

        if (stateEl) {
            stateEl.addEventListener('input', function() {
                this.value = (this.value || '').toUpperCase().replace(/[^A-Z]/g, '').slice(0, 2);
            });
        }
        if (cnpjEl) {
            cnpjEl.addEventListener('input', function() {
                let v = this.value.replace(/\D/g, '').slice(0, 14);
                v = v.replace(/^(\d{2})(\d)/, '$1.$2')
                     .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
                     .replace(/\.(\d{3})(\d)/, '.$1/$2')
                     .replace(/(\d{4})(\d)/, '$1-$2');
                this.value = v;
            });
        }

        if (saveBtn) {
            saveBtn.addEventListener('click', async function() {
                if (!requireCapability(
                    'workspaces.workspace.update',
                    'salvar as alterações'
                )) return;

                const payload = {
                    name: (nameEl && nameEl.value.trim()) || '',
                    city: (cityEl && cityEl.value.trim()) || '',
                    state: (stateEl && stateEl.value.trim().toUpperCase()) || '',
                    cnpj: (cnpjEl && cnpjEl.value.trim()) || '',
                };
                if (!payload.name) { showToast('Informe o nome', 'error'); return; }
                if (payload.state && payload.state.length !== 2) {
                    showToast('UF deve ter 2 letras', 'error'); return;
                }

                setLoading(saveBtn, true, 'Salvando...');
                try {
                    const updated = await api('/api/workspaces/' + currentWorkspace.id + '/', 'PATCH', payload);
                    currentWorkspace = updated;
                    window.Clivo.workspace = updated;
                    showToast('Workspace atualizado', 'success');

                    const wsNameEl = document.getElementById('wsName');
                    if (wsNameEl) wsNameEl.textContent = updated.name;
                    const wsAvatarText = document.getElementById('wsAvatarText');
                    if (wsAvatarText) {
                        wsAvatarText.textContent = (updated.name || 'W').charAt(0).toUpperCase();
                    }
                    loadWorkspaceData();
                } catch (e) {
                    showToast(e.message || 'Erro ao salvar', 'error');
                } finally {
                    setLoading(saveBtn, false);
                }
            });
        }
    }

    function bindDeleteWorkspace() {
        const btn = document.getElementById('wsDeleteBtn');
        const modal = document.getElementById('deleteWorkspaceModal');
        const input = document.getElementById('deleteConfirmInput');
        const confirmBtn = document.getElementById('deleteWorkspaceConfirmBtn');

        if (btn) {
            btn.addEventListener('click', function() {
                if (!requireCapability(
                    'workspaces.workspace.delete',
                    'excluir o workspace'
                )) return;
                if (!currentWorkspace) return;
                if (input) input.value = '';
                if (confirmBtn) confirmBtn.disabled = true;
                if (modal) modal.classList.add('active');
                setTimeout(function() { if (input) input.focus(); }, 100);
            });
        }
        if (input) {
            input.addEventListener('input', function() {
                const expected = (currentWorkspace && currentWorkspace.name) || '';
                if (confirmBtn) confirmBtn.disabled = (this.value.trim() !== expected);
            });
        }
        if (confirmBtn) {
            confirmBtn.addEventListener('click', async function() {
                if (!currentWorkspace) return;
                setLoading(confirmBtn, true, 'Excluindo...');
                try {
                    await api('/api/workspaces/' + currentWorkspace.id + '/', 'DELETE');
                    showToast('Workspace excluído', 'success');
                    window.location.href = '/workspaces/entrar/';
                } catch (e) {
                    showToast(e.message || 'Erro ao excluir', 'error');
                    setLoading(confirmBtn, false);
                }
            });
        }
    }

    async function loadTeam() {
        const membersContainer = document.getElementById('teamList');
        const govsContainer = document.getElementById('governanceList');
        if (!membersContainer || !currentWorkspace) return;

        membersContainer.innerHTML =
            '<div class="mesa-empty" style="padding:30px 20px;"><p>Carregando equipe...</p></div>';
        if (govsContainer) {
            govsContainer.innerHTML =
                '<div class="mesa-empty" style="padding:30px 20px;"><p>Carregando governanças...</p></div>';
        }

        const results = await Promise.allSettled([
            api('/api/workspaces/' + currentWorkspace.id + '/members/'),
            api('/api/workspaces/' + currentWorkspace.id + '/invitations/'),
            fetchGovernances(),
        ]);

        if (results[0].status === 'fulfilled') {
            const m = results[0].value;
            teamMembers = Array.isArray(m) ? m : (m.results || []);
        } else {
            teamMembers = [];
        }

        if (results[1].status === 'fulfilled') {
            const inv = results[1].value;
            pendingInvitations = Array.isArray(inv) ? inv : (inv.results || []);
        } else {
            pendingInvitations = [];
        }

        if (results[2].status === 'fulfilled') {
            availableGovernances = results[2].value || [];
        } else {
            availableGovernances = [];
        }

        renderTeam();
        renderGovernances();
        renderTeamFilter();
        updateMembersCount();
        updateGovernancesCount();
        applyCapabilitiesToUI();

        refreshIcons(membersContainer);
        if (govsContainer) refreshIcons(govsContainer);
    }

    async function fetchGovernances() {
        try {
            const data = await api('/api/workspaces/governances/');
            return Array.isArray(data) ? data : (data.results || []);
        } catch (e) {
            return [];
        }
    }

    function renderTeam() {
        const container = document.getElementById('teamList');
        if (!container) return;

        let items = [];
        teamMembers.forEach(function(m) {
            items.push({
                kind: 'member',
                governance_key: m.governance_key,
                data: m,
            });
        });
        pendingInvitations.forEach(function(inv) {
            items.push({
                kind: 'invite',
                governance_key: inv.governance_key,
                data: inv,
            });
        });

        if (governanceFilter) {
            items = items.filter(function(i) {
                return i.governance_key === governanceFilter;
            });
        }

        if (!items.length) {
            const msg = governanceFilter
                ? 'Nada nesta governança'
                : 'Nenhum membro ou convite ainda';
            const sub = governanceFilter
                ? 'Ajuste o filtro'
                : 'Clique em Convidar para começar';
            container.innerHTML =
                '<div class="mesa-empty" style="padding:60px 20px;">' +
                '<i class="lucide" data-lucide="users"></i>' +
                '<p>' + escapeHtml(msg) + '</p>' +
                '<span>' + escapeHtml(sub) + '</span>' +
                '</div>';
            refreshIcons(container);
            return;
        }

        items.sort(function(a, b) {
            if (a.kind === 'invite' && b.kind !== 'invite') return -1;
            if (a.kind !== 'invite' && b.kind === 'invite') return 1;
            return 0;
        });

        let html = '';
        items.forEach(function(item) {
            if (item.kind === 'member') html += renderMemberRow(item.data);
            else html += renderInviteRow(item.data);
        });

        container.innerHTML = html;
        refreshIcons(container);

        container.querySelectorAll('.edit-member-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const id = this.dataset.memberId;
                const m = teamMembers.find(function(x) { return x.id === id; });
                if (m) openEditMemberModal({ kind: 'member', data: m });
            });
        });
        container.querySelectorAll('.remove-member-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const id = this.dataset.memberId;
                const m = teamMembers.find(function(x) { return x.id === id; });
                if (m) openRemoveMemberModal({ kind: 'member', data: m });
            });
        });

        container.querySelectorAll('.edit-invite-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const id = this.dataset.inviteId;
                const inv = pendingInvitations.find(function(x) { return x.id === id; });
                if (inv) openEditMemberModal({ kind: 'invite', data: inv });
            });
        });
        container.querySelectorAll('.resend-invite-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const id = this.dataset.inviteId;
                resendInvitation(id, this);
            });
        });
        container.querySelectorAll('.remove-invite-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const id = this.dataset.inviteId;
                const inv = pendingInvitations.find(function(x) { return x.id === id; });
                if (inv) openRemoveMemberModal({ kind: 'invite', data: inv });
            });
        });
    }

    function renderMemberRow(m) {
        const name = m.user_full_name || m.user_email || 'Usuário';
        const email = m.user_email || '';
        const initial = name.charAt(0).toUpperCase();
        const govKey = m.governance_key || '';
        const govName = m.governance_name || govKey || '';
        const isOwnerRow = govKey === 'proprietario';
        const avatar = m.user_avatar;

        const avatarHtml = avatar
            ? '<img src="' + escapeHtml(avatar) + '" alt="' + escapeHtml(name) + '">'
            : initial;

        return (
            '<div class="team-row" data-member-id="' + m.id + '">' +
                '<div class="team-avatar">' + avatarHtml + '</div>' +
                '<div class="team-info">' +
                    '<div class="team-name">' + escapeHtml(name) + '</div>' +
                    '<div class="team-email">' + escapeHtml(email) + '</div>' +
                '</div>' +
                '<span class="team-governance ' + escapeHtml(govKey) + '">' + escapeHtml(govName) + '</span>' +
                '<div class="team-actions">' +
                    '<button class="edit-member-btn" data-member-id="' + m.id + '" title="Editar governança">' +
                        '<i class="lucide" data-lucide="pencil"></i>' +
                    '</button>' +
                    (isOwnerRow
                        ? '' 
                        : '<button class="danger remove-member-btn" data-member-id="' + m.id + '" title="Remover">' +
                            '<i class="lucide" data-lucide="trash-2"></i>' +
                          '</button>') +
                '</div>' +
            '</div>'
        );
    }

    function renderInviteRow(inv) {
        const email = inv.email || '';
        const govKey = inv.governance_key || '';
        const govName = inv.governance_name || govKey || '';
        const isPending = inv.status === 'pending';
        const isExpired = inv.status === 'expired' || inv.is_expired;

        const statusBadge = isPending
            ? '<span class="team-badge pending">Pendente</span>'
            : (isExpired
                ? '<span class="team-badge expired">Expirado</span>'
                : '');

        return (
            '<div class="team-row invite-row" data-invite-id="' + inv.id + '">' +
                '<div class="team-avatar invite-avatar">' +
                    '<i class="lucide" data-lucide="mail"></i>' +
                '</div>' +
                '<div class="team-info">' +
                    '<div class="team-name">' + escapeHtml(email) + '</div>' +
                    '<div class="team-email">' +
                        'Convite · ' + escapeHtml(govName) + ' ' + statusBadge +
                    '</div>' +
                '</div>' +
                '<span class="team-governance ' + escapeHtml(govKey) + '">' + escapeHtml(govName) + '</span>' +
                '<div class="team-actions">' +
                    (isPending
                        ? '<button class="resend-invite-btn" data-invite-id="' + inv.id + '" title="Reenviar convite">' +
                            '<i class="lucide" data-lucide="send"></i>' +
                          '</button>'
                        : '') +
                    '<button class="edit-invite-btn" data-invite-id="' + inv.id + '" title="Alterar governança">' +
                        '<i class="lucide" data-lucide="pencil"></i>' +
                    '</button>' +
                    '<button class="danger remove-invite-btn" data-invite-id="' + inv.id + '" title="Cancelar convite">' +
                        '<i class="lucide" data-lucide="x"></i>' +
                    '</button>' +
                '</div>' +
            '</div>'
        );
    }

    function updateMembersCount() {
        const el = document.getElementById('teamMembersCount');
        if (!el) return;
        const total = teamMembers.length + pendingInvitations.length;
        const filtered = governanceFilter
            ? (
                teamMembers.filter(function(m) { return m.governance_key === governanceFilter; }).length +
                pendingInvitations.filter(function(i) { return i.governance_key === governanceFilter; }).length
              )
            : total;
        el.textContent = governanceFilter ? (filtered + '/' + total) : String(total);
    }

    function renderGovernances() {
        const container = document.getElementById('governanceList');
        if (!container) return;

        if (!availableGovernances.length) {
            container.innerHTML =
                '<div class="mesa-empty" style="padding:60px 20px;">' +
                '<i class="lucide" data-lucide="shield"></i>' +
                '<p>Nenhuma governança disponível</p>' +
                '</div>';
            refreshIcons(container);
            return;
        }

        let html = '';
        availableGovernances.forEach(function(g) {
            const caps = g.capabilities || [];
            const initial = (g.name || g.key || '?').charAt(0).toUpperCase();

            let capsHtml = '';
            if (caps.length) {
                const visible = caps.slice(0, 8);
                const hidden = caps.length - visible.length;

                capsHtml = '<div class="governance-capabilities">';
                visible.forEach(function(c) {
                    const label = c.name || c.code;
                    capsHtml +=
                        '<div class="cap-line">' +
                            '<span class="cap-dot"></span>' +
                            '<span class="cap-label">' + escapeHtml(label) + '</span>' +
                        '</div>';
                });
                if (hidden > 0) {
                    capsHtml += '<div class="cap-more">+ ' + hidden + ' mais</div>';
                }
                capsHtml += '</div>';
            } else {
                capsHtml = '<div class="governance-empty-caps">Sem capabilities atribuídas</div>';
            }

            const systemBadge = g.is_system
                ? '<span class="governance-badge">Sistema</span>'
                : '';

            html +=
                '<div class="governance-row" data-gov-key="' + escapeHtml(g.key) + '">' +
                    '<div class="governance-marker">' + escapeHtml(initial) + '</div>' +
                    '<div class="governance-info">' +
                        '<div class="governance-name">' +
                            escapeHtml(g.name || g.key) + systemBadge +
                        '</div>' +
                        (g.description
                            ? '<p class="governance-description">' + escapeHtml(g.description) + '</p>'
                            : '') +
                        capsHtml +
                    '</div>' +
                '</div>';
        });

        container.innerHTML = html;
        refreshIcons(container);
    }

    function updateGovernancesCount() {
        const el = document.getElementById('governancesCount');
        if (!el) return;
        el.textContent = String(availableGovernances.length);
    }

    function renderTeamFilter() {
        const select = document.getElementById('teamGovernanceFilter');
        if (!select) return;
        const current = governanceFilter;
        select.innerHTML = '<option value="">Todas</option>';
        availableGovernances.forEach(function(g) {
            const opt = document.createElement('option');
            opt.value = g.key;
            opt.textContent = g.name || g.key;
            select.appendChild(opt);
        });
        if (current && select.querySelector('option[value="' + current + '"]')) {
            select.value = current;
        } else {
            governanceFilter = '';
        }
    }

    function bindTeamFilter() {
        const select = document.getElementById('teamGovernanceFilter');
        if (!select) return;
        select.addEventListener('change', function() {
            governanceFilter = this.value || '';
            renderTeam();
            updateMembersCount();
        });
    }

    function fillGovernanceSelect(selectEl, selectedKey) {
        if (!selectEl) return;
        selectEl.innerHTML = '';
        const list = availableGovernances.length
            ? availableGovernances
            : [
                { key: 'membro', name: 'Membro' },
                { key: 'administrador', name: 'Administrador' },
                { key: 'proprietario', name: 'Proprietário' },
            ];
        list.forEach(function(g) {
            const opt = document.createElement('option');
            opt.value = g.key;
            opt.textContent = g.name || g.key;
            if (selectedKey && selectedKey === g.key) opt.selected = true;
            selectEl.appendChild(opt);
        });
    }

    function setupAddMember() {
        const addBtn = document.getElementById('teamAddBtn');
        const modal = document.getElementById('addMemberModal');
        const form = document.getElementById('addMemberForm');
        const select = document.getElementById('memberGovernance');
        const submitBtn = document.getElementById('addMemberSubmitBtn');
        const emailInput = document.getElementById('memberEmail');

        if (!addBtn || !modal || !form) return;

        addBtn.addEventListener('click', function() {
            if (!requireCapability(
                'workspaces.member.invite',
                'convidar membros'
            )) return;
            fillGovernanceSelect(select, 'membro');
            form.reset();
            if (emailInput) emailInput.value = '';
            if (select) select.value = 'membro';
            modal.classList.add('active');
            setTimeout(function() { if (emailInput) emailInput.focus(); }, 100);
        });

        form.addEventListener('submit', async function(e) {
            e.preventDefault();
            if (!currentWorkspace) return;
            const email = (emailInput && emailInput.value.trim()) || '';
            const govKey = (select && select.value) || 'membro';
            if (!email) { showToast('Informe o email', 'error'); return; }

            setLoading(submitBtn, true, 'Enviando...');
            try {
                await api(
                    '/api/workspaces/' + currentWorkspace.id + '/invitations/',
                    'POST',
                    { email: email, governance_key: govKey }
                );
                showToast('Convite enviado', 'success');
                modal.classList.remove('active');
                loadTeam();
            } catch (e) {
                showToast(e.message || 'Erro ao enviar convite', 'error');
            } finally {
                setLoading(submitBtn, false);
            }
        });
    }

    function openEditMemberModal(target) {
        if (!requireCapability(
            'workspaces.member.change_governance',
            'alterar a governança'
        )) return;

        memberToEdit = target;
        const modal = document.getElementById('editMemberModal');
        const titleEl = document.getElementById('editMemberTitle');
        const nameEl = document.getElementById('editMemberName');
        const emailEl = document.getElementById('editMemberEmail');
        const select = document.getElementById('editMemberGovernance');

        if (target.kind === 'member') {
            const m = target.data;
            if (titleEl) titleEl.textContent = 'Alterar governança';
            if (nameEl) nameEl.textContent = m.user_full_name || 'Usuário';
            if (emailEl) emailEl.textContent = m.user_email || '';
            fillGovernanceSelect(select, m.governance_key);
        } else {
            const inv = target.data;
            if (titleEl) titleEl.textContent = 'Alterar governança do convite';
            if (nameEl) nameEl.textContent = inv.email || '';
            if (emailEl) emailEl.textContent = 'Convite pendente';
            fillGovernanceSelect(select, inv.governance_key);
        }
        if (modal) modal.classList.add('active');
    }

    function setupEditMember() {
        const saveBtn = document.getElementById('editMemberSaveBtn');
        if (!saveBtn) return;

        saveBtn.addEventListener('click', async function() {
            if (!memberToEdit || !currentWorkspace) return;
            const select = document.getElementById('editMemberGovernance');
            const newGov = select ? select.value : '';

            setLoading(saveBtn, true, 'Salvando...');
            try {
                if (memberToEdit.kind === 'member') {
                    await api(
                        '/api/workspaces/' + currentWorkspace.id + '/members/' + memberToEdit.data.id + '/',
                        'PATCH',
                        { governance_key: newGov }
                    );
                } else {
                    await api(
                        '/api/workspaces/' + currentWorkspace.id + '/invitations/' + memberToEdit.data.id + '/',
                        'PATCH',
                        { governance_key: newGov }
                    );
                }
                showToast('Governança atualizada', 'success');
                document.getElementById('editMemberModal').classList.remove('active');
                memberToEdit = null;
                loadTeam();
            } catch (e) {
                showToast(e.message || 'Erro ao salvar', 'error');
            } finally {
                setLoading(saveBtn, false);
            }
        });
    }

    function openRemoveMemberModal(target) {
        if (!requireCapability(
            'workspaces.member.remove',
            'remover'
        )) return;

        memberToRemove = target;
        const modal = document.getElementById('removeMemberModal');
        const titleEl = document.getElementById('removeMemberTitle');
        const textEl = document.getElementById('removeMemberText');

        if (target.kind === 'member') {
            const m = target.data;
            if (titleEl) titleEl.textContent = 'Remover membro';
            if (textEl) {
                textEl.innerHTML =
                    'Tem certeza que deseja remover <strong>' +
                    escapeHtml(m.user_full_name || m.user_email) +
                    '</strong> deste workspace?';
            }
        } else {
            const inv = target.data;
            if (titleEl) titleEl.textContent = 'Cancelar convite';
            if (textEl) {
                textEl.innerHTML =
                    'Tem certeza que deseja cancelar o convite para <strong>' +
                    escapeHtml(inv.email) +
                    '</strong>?';
            }
        }
        if (modal) modal.classList.add('active');
    }

    function setupRemoveMember() {
        const confirmBtn = document.getElementById('removeMemberConfirmBtn');
        if (!confirmBtn) return;

        confirmBtn.addEventListener('click', async function() {
            if (!memberToRemove || !currentWorkspace) return;
            setLoading(confirmBtn, true, 'Removendo...');
            try {
                if (memberToRemove.kind === 'member') {
                    await api(
                        '/api/workspaces/' + currentWorkspace.id + '/members/' + memberToRemove.data.id + '/',
                        'DELETE'
                    );
                    showToast('Membro removido', 'success');
                } else {
                    await api(
                        '/api/workspaces/' + currentWorkspace.id + '/invitations/' + memberToRemove.data.id + '/',
                        'DELETE'
                    );
                    showToast('Convite cancelado', 'success');
                }
                document.getElementById('removeMemberModal').classList.remove('active');
                memberToRemove = null;
                loadTeam();
            } catch (e) {
                showToast(e.message || 'Erro', 'error');
            } finally {
                setLoading(confirmBtn, false);
            }
        });
    }

    async function resendInvitation(invitationId, btn) {
        if (!currentWorkspace) return;
        if (!requireCapability(
            'workspaces.member.invite',
            'reenviar convites'
        )) return;

        setLoading(btn, true, '');
        try {
            await api(
                '/api/workspaces/' + currentWorkspace.id + '/invitations/' + invitationId + '/resend/',
                'POST'
            );
            showToast('Convite reenviado', 'success');
            loadTeam();
        } catch (e) {
            showToast(e.message || 'Erro ao reenviar', 'error');
            setLoading(btn, false);
        }
    }

    function setupModals() {
        document.querySelectorAll('.modal-close, [data-modal]').forEach(function(el) {
            el.addEventListener('click', function() {
                const modalId = this.dataset.modal;
                if (modalId) {
                    const modal = document.getElementById(modalId);
                    if (modal) modal.classList.remove('active');
                }
            });
        });
        document.querySelectorAll('.modal-overlay').forEach(function(modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === this) this.classList.remove('active');
            });
        });
    }

    function mount() {
        currentWorkspace = window.Clivo.workspace || null;
        currentGovernanceKey = window.Clivo.governanceKey || null;
        myCapabilities = (window.Clivo.capabilities || []).slice();
        isOwner = !!window.Clivo.isOwner;

        teamMembers = [];
        pendingInvitations = [];
        availableGovernances = [];
        governanceFilter = '';
        memberToEdit = null;
        memberToRemove = null;

        updateTodayDate();
        updateGreeting();
        setupViewTabs();
        setupSubTabs();
        bindWorkspaceForm();
        bindDeleteWorkspace();
        bindTeamFilter();
        setupAddMember();
        setupEditMember();
        setupRemoveMember();
        setupModals();
        updateWorkspaceTabVisibility();

        requestIdleCallback(async function() {
            try {
                // 1) SEMPRE carrega capabilities ANTES de qualquer decisão de UI.
                //    Sem isso, hasCapability() sempre retorna false quando o
                //    workspace já foi hidratado pelo shell (window.Clivo.workspace
                //    != null), e o proprietário fica bloqueado.
                await loadMyCapabilities();

                // 2) Carrega/atualiza os dados do workspace atual.
                await loadWorkspaceData();

                // 3) Redundante, mas defensivo: garante que a UI reflita
                //    o estado mais recente de capabilities.
                applyCapabilitiesToUI();
            } catch (e) {
                console.error('Falha no boot do mesa:', e);
                applyCapabilitiesToUI();
            }
        }, { timeout: 100 });
    }

    function unmount() {
        // Nada a limpar.
    }

    window.ClivoPages = window.ClivoPages || {};
    window.ClivoPages.mesa = {
        mount: mount,
        unmount: unmount,
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