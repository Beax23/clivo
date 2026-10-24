/* =========================================================================
   SIDEBAR — Application Shell (JS)
   ========================================================================= */

(function() {
    'use strict';

    window.Clivo = window.Clivo || {
        user: null,
        workspace: null,
        capabilities: [],
        isOwner: false,
        governanceKey: null,
        currentPage: null,
        workspacePublicIdFromUrl: null,
        cache: { clients: null },
    };

    window.clivoCurrentUser = window.clivoCurrentUser || null;
    window.clivoCurrentWorkspace = window.clivoCurrentWorkspace || null;

    window.ClivoPages = window.ClivoPages || {};

    (function readWorkspacePublicIdFromUrl() {
        const appEl = document.getElementById('app');
        const raw = appEl ? (appEl.dataset.workspacePublicId || '') : '';
        window.Clivo.workspacePublicIdFromUrl = raw || null;
    })();

    // ============================================================
    // ASSET LOADER
    // ============================================================
    const GLOBAL_CSS = [
        '/static/css/sidebar.css',
        '/static/css/mesa.css',
        '/static/css/cliente.css',
    ];
    const GLOBAL_JS = [
        '/static/js/sidebar.js',
        '/static/js/mesa.js',
        '/static/js/cliente.js',
    ];

    function isGlobalCss(href) {
        if (!href) return false;
        return GLOBAL_CSS.some(function(g) { return href.indexOf(g) !== -1; });
    }
    function isGlobalJs(src) {
        if (!src) return false;
        return GLOBAL_JS.some(function(g) { return src.indexOf(g) !== -1; });
    }

    const _injectedLinks = {};
    function ensureStylesheetLoaded(href) {
        if (!href || isGlobalCss(href) || _injectedLinks[href]) return;
        const existing = document.querySelector('link[rel="stylesheet"][href="' + href + '"]');
        if (existing) { _injectedLinks[href] = existing; return; }
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        link.setAttribute('data-clivo-softnav', 'css');
        document.head.appendChild(link);
        _injectedLinks[href] = link;
    }

    const _loadedScripts = {};
    function ensureScriptLoaded(src) {
        if (!src || isGlobalJs(src)) return Promise.resolve();
        if (_loadedScripts[src]) return _loadedScripts[src];
        const existing = document.querySelector('script[src="' + src + '"]');
        if (existing) { _loadedScripts[src] = Promise.resolve(); return _loadedScripts[src]; }
        _loadedScripts[src] = new Promise(function(resolve, reject) {
            const s = document.createElement('script');
            s.src = src; s.async = false;
            s.setAttribute('data-clivo-softnav', 'js');
            s.onload = function() { resolve(); };
            s.onerror = function() {
                delete _loadedScripts[src];
                try { s.remove(); } catch (e) {}
                reject(new Error('Falha ao carregar ' + src));
            };
            document.body.appendChild(s);
        });
        return _loadedScripts[src];
    }

    // ============================================================
    // HELPERS
    // ============================================================
    window.clivoGetCookie = function(name) {
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
    };

    let toastTimeout = null;
    window.clivoShowToast = function(message, type) {
        type = type || 'info';
        const container = document.getElementById('toastContainer');
        if (!container) return;
        while (container.firstChild) container.removeChild(container.firstChild);
        const toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        const iconMap = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle' };
        toast.innerHTML =
            '<span class="toast-icon"><i class="fas ' + (iconMap[type] || iconMap.info) + '"></i></span>' +
            '<span class="toast-content">' + message + '</span>' +
            '<button class="toast-close" type="button"><i class="fas fa-times"></i></button>';
        container.appendChild(toast);
        toast.querySelector('.toast-close').addEventListener('click', function() {
            toast.classList.add('hiding');
            setTimeout(function() { toast.remove(); }, 300);
        });
        clearTimeout(toastTimeout);
        toastTimeout = setTimeout(function() {
            toast.classList.add('hiding');
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    };

    window.clivoApi = async function(url, method, body) {
        const isFormData = body instanceof FormData;
        const options = {
            method: method || 'GET',
            credentials: 'include',
            headers: { 'X-CSRFToken': window.clivoGetCookie('csrftoken') }
        };
        if (!isFormData) options.headers['Content-Type'] = 'application/json';
        if (body !== undefined && body !== null) {
            options.body = isFormData ? body : JSON.stringify(body);
        }
        const response = await fetch(url, options);
        if (response.status === 204) return null;
        let data = null;
        try { data = await response.json(); } catch (e) {}
        if (!response.ok) {
            const msg = (data && (data.error || data.detail ||
                (data.non_field_errors && data.non_field_errors[0]))) ||
                'Erro na requisição';
            const err = new Error(msg);
            err.status = response.status;
            err.data = data;
            throw err;
        }
        return data;
    };

    window.clivoRefreshIcons = function() {
        if (typeof lucide === 'undefined') return;
        if (typeof lucide.createIcons !== 'function') return;
        lucide.createIcons();
    };

    // ============================================================
    // MOBILE DRAWER
    // ============================================================
    function isMobile() {
        return window.matchMedia('(max-width: 767px)').matches;
    }

    function openSidebar() {
        document.body.classList.add('sidebar-open');
    }

    function closeSidebar() {
        document.body.classList.remove('sidebar-open');
    }

    function bindMobileDrawer() {
        const logoBtn = document.getElementById('logoBtn');
        const overlay = document.getElementById('sidebarOverlay');
        const sidebar = document.getElementById('sidebar');

        if (logoBtn) {
            logoBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                if (!isMobile()) return;
                if (document.body.classList.contains('sidebar-open')) {
                    closeSidebar();
                } else {
                    openSidebar();
                }
            });
        }

        if (overlay) {
            overlay.addEventListener('click', function(e) {
                e.stopPropagation();
                closeSidebar();
            });
        }

        if (sidebar) {
            sidebar.addEventListener('click', function(e) {
                const link = e.target.closest('.sidebar-nav a');
                if (link && !link.dataset.navLocked) {
                    if (isMobile()) {
                        setTimeout(closeSidebar, 60);
                    }
                }
            });
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && document.body.classList.contains('sidebar-open')) {
                closeSidebar();
            }
        });

        let resizeTimer = null;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function() {
                if (!isMobile()) closeSidebar();
            }, 120);
        });
    }

    // ============================================================
    // THEME
    // ============================================================
    let currentTheme = localStorage.getItem('clivo-theme') || 'light';
    document.documentElement.setAttribute('data-theme', currentTheme);

    function updateThemeIcon(theme) {
        const wrapper = document.getElementById('themeIconWrapper');
        if (!wrapper) return;
        const iconName = theme === 'dark' ? 'moon' : 'sun';
        wrapper.innerHTML = '<i data-lucide="' + iconName + '"></i>';
        window.clivoRefreshIcons();
    }
    updateThemeIcon(currentTheme);

    window.clivoToggleTheme = function() {
        currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', currentTheme);
        localStorage.setItem('clivo-theme', currentTheme);
        updateThemeIcon(currentTheme);
    };

    // ============================================================
    // LOGOUT
    // ============================================================
    window.clivoLogout = async function() {
        const btn = document.getElementById('logoutBtn');
        const icon = document.getElementById('logoutIcon');
        if (btn) btn.classList.add('is-loading');
        if (icon) icon.classList.add('hidden');
        if (btn) {
            const spinner = document.createElement('span');
            spinner.className = 'logout-spinner';
            spinner.id = 'logoutSpinner';
            btn.appendChild(spinner);
        }
        try {
            const response = await fetch('/api/auth/logout/', {
                method: 'POST',
                credentials: 'include',
                headers: { 'X-CSRFToken': window.clivoGetCookie('csrftoken') }
            });
            if (response.ok) { window.location.href = '/login/'; return; }
            window.clivoShowToast('Erro ao fazer logout', 'error');
            restoreLogoutButton();
        } catch (e) {
            window.clivoShowToast('Erro ao fazer logout', 'error');
            restoreLogoutButton();
        }
    };

    function restoreLogoutButton() {
        const btn = document.getElementById('logoutBtn');
        const icon = document.getElementById('logoutIcon');
        const spinner = document.getElementById('logoutSpinner');
        if (spinner) spinner.remove();
        if (icon) icon.classList.remove('hidden');
        if (btn) btn.classList.remove('is-loading');
    }

    // ============================================================
    // ESCAPE
    // ============================================================
    function escapeHtml(s) {
        if (s === null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // ============================================================
    // NOVO CLIENTE — MODAL
    // ============================================================
    let gLastCreatedId = null;

    const gModal = {
        root: null, form: null, success: null, title: null, submitBtn: null,
        nameInput: null, emailInput: null, phoneInput: null,
        nameSuggest: null, emailSuggest: null,
        emailAlert: null, emailAlertDesc: null, emailAlertAction: null,
        codeEl: null, copyBtn: null, sendCodeBtn: null, openBtn: null,
        existingByEmail: null, clientsList: [], activeSuggest: null,
    };

    function gReset() {
        gLastCreatedId = null;
        gModal.existingByEmail = null;
        gCloseSuggest();
        gHideEmailAlert();
        if (gModal.form) {
            gModal.form.reset();
            gModal.form.classList.remove('hidden');
        }
        if (gModal.success) gModal.success.classList.add('hidden');
        if (gModal.emailInput) gModal.emailInput.classList.remove('has-error');
        if (gModal.title) gModal.title.textContent = 'Novo cliente';
    }

    function gOpenModal() {
        gReset();
        if (gModal.root) gModal.root.classList.add('active');
        gLoadClientsForSuggest();
        setTimeout(function() {
            if (gModal.nameInput) gModal.nameInput.focus();
        }, 100);
    }

    function gCloseModal() {
        if (gModal.root) gModal.root.classList.remove('active');
        gCloseSuggest();
    }

    async function gLoadClientsForSuggest() {
        try {
            const data = await window.clivoApi('/api/clients/');
            gModal.clientsList = Array.isArray(data) ? data : (data.results || []);
        } catch (e) {
            gModal.clientsList = [];
        }
    }

    function gCloseSuggest() {
        if (gModal.nameSuggest) gModal.nameSuggest.classList.remove('open');
        if (gModal.emailSuggest) gModal.emailSuggest.classList.remove('open');
        gModal.activeSuggest = null;
    }

    function gShowSuggest(inputEl, containerEl, items) {
        if (!containerEl) return;
        containerEl.innerHTML = '';
        items.forEach(function(c) {
            const initial = (c.name || '?').charAt(0).toUpperCase();
            const item = document.createElement('div');
            item.className = 'g-suggest-item';
            item.innerHTML =
                '<div class="g-suggest-avatar">' + escapeHtml(initial) + '</div>' +
                '<div class="g-suggest-body">' +
                    '<div class="g-suggest-name">' + escapeHtml(c.name || '—') + '</div>' +
                    '<div class="g-suggest-meta">' + escapeHtml(c.email || '—') + '</div>' +
                '</div>';
            item.addEventListener('mousedown', function(ev) {
                ev.preventDefault();
                gCloseSuggest();
                if (inputEl === gModal.emailInput) {
                    inputEl.value = c.email || '';
                    gCheckEmailInline();
                } else {
                    gModal.nameInput.value = c.name || '';
                    gModal.emailInput.value = c.email || '';
                    gModal.phoneInput.value = c.phone || '';
                    gCheckEmailInline();
                }
            });
            containerEl.appendChild(item);
        });
        containerEl.classList.add('open');
        gModal.activeSuggest = containerEl;
    }

    function gNameSuggestHandler() {
        const q = (gModal.nameInput.value || '').trim().toLowerCase();
        if (!q) { gCloseSuggest(); return; }
        const items = gModal.clientsList.filter(function(c) {
            return (c.name || '').toLowerCase().indexOf(q) !== -1;
        }).slice(0, 6);
        if (!items.length) { gCloseSuggest(); return; }
        gShowSuggest(gModal.nameInput, gModal.nameSuggest, items);
    }

    function gEmailSuggestHandler() {
        const q = (gModal.emailInput.value || '').trim().toLowerCase();
        if (!q) { gCloseSuggest(); gHideEmailAlert(); return; }
        const items = gModal.clientsList.filter(function(c) {
            return (c.email || '').toLowerCase().indexOf(q) !== -1;
        }).slice(0, 6);
        if (items.length) gShowSuggest(gModal.emailInput, gModal.emailSuggest, items);
        else gCloseSuggest();
        gCheckEmailInline();
    }

    function gHideEmailAlert() {
        if (gModal.emailAlert) gModal.emailAlert.classList.remove('open');
        if (gModal.emailInput) gModal.emailInput.classList.remove('has-error');
    }

    function gCheckEmailInline() {
        const email = (gModal.emailInput.value || '').trim().toLowerCase();
        if (!email) { gHideEmailAlert(); return; }
        const found = gModal.clientsList.find(function(c) {
            return (c.email || '').toLowerCase() === email;
        });
        if (found) {
            gModal.emailInput.classList.add('has-error');
            if (gModal.emailAlertDesc) {
                gModal.emailAlertDesc.textContent =
                    '"' + (found.name || '') + '" já está cadastrado com este email.';
            }
            gModal.existingByEmail = found;
            if (gModal.emailAlert) gModal.emailAlert.classList.add('open');
        } else {
            gHideEmailAlert();
        }
    }

    function gGoToExistingClient() {
        if (!gModal.existingByEmail) return;
        const id = gModal.existingByEmail.id;
        gCloseModal();
        if (window.Clivo.currentPage === 'cliente') {
            window.location.hash = id;
        } else {
            softNavigate('/clientes/', { afterMount: function() {
                setTimeout(function() { window.location.hash = id; }, 50);
            }});
        }
    }

    function gSetupNewClientModal() {
        gModal.root = document.getElementById('gNewClientModal');
        gModal.form = document.getElementById('gNewClientForm');
        gModal.success = document.getElementById('gNewClientSuccess');
        gModal.title = document.getElementById('gNewClientTitle');
        gModal.submitBtn = document.getElementById('gNewSubmitBtn');
        gModal.nameInput = document.getElementById('gNewName');
        gModal.emailInput = document.getElementById('gNewEmail');
        gModal.phoneInput = document.getElementById('gNewPhone');
        gModal.nameSuggest = document.getElementById('gNameSuggest');
        gModal.emailSuggest = document.getElementById('gEmailSuggest');
        gModal.emailAlert = document.getElementById('gEmailAlert');
        gModal.emailAlertDesc = document.getElementById('gEmailAlertDesc');
        gModal.emailAlertAction = document.getElementById('gEmailAlertAction');
        gModal.codeEl = document.getElementById('gNewCode');
        gModal.copyBtn = document.getElementById('gCopyNewCodeBtn');
        gModal.sendCodeBtn = document.getElementById('gSendCodeFromModalBtn');
        gModal.openBtn = document.getElementById('gOpenClientBtn');

        if (!gModal.form) return;

        gModal.nameInput.addEventListener('input', gNameSuggestHandler);
        gModal.nameInput.addEventListener('focus', function() {
            if (gModal.nameInput.value.trim()) gNameSuggestHandler();
        });
        gModal.nameInput.addEventListener('blur', function() {
            setTimeout(gCloseSuggest, 150);
        });

        gModal.emailInput.addEventListener('input', gEmailSuggestHandler);
        gModal.emailInput.addEventListener('focus', function() {
            if (gModal.emailInput.value.trim()) gEmailSuggestHandler();
        });
        gModal.emailInput.addEventListener('blur', function() {
            setTimeout(gCloseSuggest, 150);
        });

        if (gModal.emailAlertAction) {
            gModal.emailAlertAction.addEventListener('click', gGoToExistingClient);
        }

        gModal.form.addEventListener('submit', async function(e) {
            e.preventDefault();
            const name = (gModal.nameInput.value || '').trim();
            const email = (gModal.emailInput.value || '').trim().toLowerCase();
            const phone = (gModal.phoneInput.value || '').trim();

            if (!name) { window.clivoShowToast('Informe o nome', 'error'); return; }
            if (!email) { window.clivoShowToast('Informe o email', 'error'); return; }

            const existing = gModal.clientsList.find(function(c) {
                return (c.email || '').toLowerCase() === email;
            });
            if (existing) {
                gCheckEmailInline();
                window.clivoShowToast('Já existe um cliente com este email', 'error');
                return;
            }

            gModal.submitBtn.disabled = true;
            const original = gModal.submitBtn.innerHTML;
            gModal.submitBtn.innerHTML = 'Criando…';

            try {
                const created = await window.clivoApi('/api/clients/', 'POST', {
                    name: name, email: email, phone: phone,
                });
                gLastCreatedId = created.id;
                if (gModal.codeEl) gModal.codeEl.textContent = created.public_code;
                if (gModal.title) gModal.title.textContent = 'Cliente criado';
                gModal.form.classList.add('hidden');
                if (gModal.success) gModal.success.classList.remove('hidden');
                window.clivoRefreshIcons();
                window.clivoShowToast('Cliente criado e email enviado', 'success');
                window.Clivo.cache.clients = null;
                if (typeof window.clivoOnClientCreated === 'function') {
                    window.clivoOnClientCreated(created);
                }
            } catch (err) {
                if (err.status === 409) {
                    gCheckEmailInline();
                }
                window.clivoShowToast(err.message || 'Erro ao criar', 'error');
            } finally {
                gModal.submitBtn.disabled = false;
                gModal.submitBtn.innerHTML = original;
            }
        });

        if (gModal.copyBtn) {
            gModal.copyBtn.addEventListener('click', function() {
                const code = gModal.codeEl.textContent || '';
                if (navigator.clipboard) navigator.clipboard.writeText(code);
                window.clivoShowToast('Código copiado', 'success');
            });
        }

        if (gModal.sendCodeBtn) {
            gModal.sendCodeBtn.addEventListener('click', async function() {
                if (!gLastCreatedId) return;
                gModal.sendCodeBtn.disabled = true;
                const original = gModal.sendCodeBtn.innerHTML;
                gModal.sendCodeBtn.innerHTML = 'Enviando…';
                try {
                    await window.clivoApi('/api/clients/' + gLastCreatedId + '/send-code/', 'POST');
                    window.clivoShowToast('Código reenviado por email', 'success');
                } catch (err) {
                    window.clivoShowToast(err.message || 'Erro ao enviar', 'error');
                } finally {
                    gModal.sendCodeBtn.disabled = false;
                    gModal.sendCodeBtn.innerHTML = original;
                }
            });
        }

        if (gModal.openBtn) {
            gModal.openBtn.addEventListener('click', function() {
                if (!gLastCreatedId) return;
                gCloseModal();
                if (window.Clivo.currentPage === 'cliente') {
                    window.location.hash = gLastCreatedId;
                } else {
                    softNavigate('/clientes/', { afterMount: function() {
                        setTimeout(function() { window.location.hash = gLastCreatedId; }, 50);
                    }});
                }
            });
        }

        gModal.root.querySelectorAll('[data-g-close="gNewClientModal"]').forEach(function(el) {
            el.addEventListener('click', function() { gCloseModal(); });
        });
        gModal.root.addEventListener('click', function(e) {
            if (e.target === gModal.root) gCloseModal();
        });
    }

    window.clivoOpenNewClientModal = gOpenModal;

    // ============================================================
    // NOVO BRIEFING — MODAL
    // ============================================================
    const gBrief = {
        root: null, form: null, submitBtn: null, clientSwitch: null,
        newClientFields: null, existingClientFields: null,
        existingClientSelect: null,
        clientSearchInput: null, clientSearchClear: null,
        clientSuggest: null,
        clientSelectedInfo: null, clientSelectedAvatar: null,
        clientSelectedName: null, clientSelectedMeta: null,
        clientSelectedClear: null,
        nameInput: null, emailInput: null, phoneInput: null, emailSuggest: null,
        templateSelect: null, titleInput: null,
        deadlineDate: null, deadlineTime: null,
        clientsList: null, clientsPromise: null,
        templatesList: null, templatesPromise: null,
        clientMode: 'new', lastCreatedBriefingId: null, lastCreatedClientId: null,
        activeSuggest: null,
        selectedClient: null,
        submitBound: false,
    };

    function gBriefPad2(n) { return (n < 10 ? '0' : '') + n; }

    function gBriefFormatDateInput(d) {
        return d.getFullYear() + '-' + gBriefPad2(d.getMonth() + 1) + '-' + gBriefPad2(d.getDate());
    }

    function gBriefFormatTimeInput(d) {
        return gBriefPad2(d.getHours()) + ':' + gBriefPad2(d.getMinutes());
    }

    function gBriefDefaultDeadline() {
        const d = new Date();
        d.setDate(d.getDate() + 7);
        d.setHours(18, 0, 0, 0);
        return d;
    }

    function gBriefApplyDefaultDeadline() {
        const d = gBriefDefaultDeadline();
        if (gBrief.deadlineDate) gBrief.deadlineDate.value = gBriefFormatDateInput(d);
        if (gBrief.deadlineTime) gBrief.deadlineTime.value = gBriefFormatTimeInput(d);
    }

    function gBriefReset() {
        gBrief.clientMode = 'new';
        gBrief.lastCreatedBriefingId = null;
        gBrief.lastCreatedClientId = null;
        gBriefCloseSuggest();
        gBriefCloseClientSuggest();
        gBriefClearSelectedClient();
        if (gBrief.form) gBrief.form.reset();
        gBriefSetClientMode('new');
        if (gBrief.existingClientSelect) gBrief.existingClientSelect.value = '';
        if (gBrief.clientSearchInput) gBrief.clientSearchInput.value = '';
        if (gBrief.templateSelect) gBrief.templateSelect.value = '';
        gBriefApplyDefaultDeadline();
    }

    async function gBriefOpenModal() {
        // Garante que o form e o botão estão ligados mesmo após soft-nav
        if (!gBrief.root || !document.body.contains(gBrief.root)) {
            gBriefSetupModal();
        }
        gBriefReset();
        if (gBrief.root) gBrief.root.classList.add('active');
        await Promise.all([
            gBriefLoadClients(),
            gBriefLoadTemplates(),
        ]);
        setTimeout(function() {
            if (gBrief.clientMode === 'new' && gBrief.nameInput) {
                gBrief.nameInput.focus();
            } else if (gBrief.clientMode === 'existing' && gBrief.clientSearchInput) {
                gBrief.clientSearchInput.focus();
            }
        }, 100);
    }

    function gBriefCloseModal() {
        if (gBrief.root) gBrief.root.classList.remove('active');
        gBriefCloseSuggest();
        gBriefCloseClientSuggest();
    }

    function gBriefSetClientMode(mode) {
        gBrief.clientMode = mode;
        const btns = gBrief.root.querySelectorAll('.gb-switch-btn');
        btns.forEach(function(b) {
            b.classList.toggle('is-active', b.dataset.mode === mode);
        });
        if (gBrief.newClientFields) {
            gBrief.newClientFields.style.display = (mode === 'new') ? '' : 'none';
        }
        if (gBrief.existingClientFields) {
            gBrief.existingClientFields.style.display = (mode === 'existing') ? '' : 'none';
        }
        if (mode === 'new' && gBrief.nameInput) {
            setTimeout(function() { gBrief.nameInput.focus(); }, 50);
        }
        if (mode === 'existing' && gBrief.clientSearchInput) {
            setTimeout(function() { gBrief.clientSearchInput.focus(); }, 50);
        }
    }

    async function gBriefLoadClients(force) {
        if (!force && gBrief.clientsList) {
            return gBrief.clientsList;
        }
        if (gBrief.clientsPromise) return gBrief.clientsPromise;
        gBrief.clientsPromise = (async function() {
            try {
                const data = await window.clivoApi('/api/clients/');
                gBrief.clientsList = Array.isArray(data) ? data : (data.results || []);
                return gBrief.clientsList;
            } catch (e) {
                gBrief.clientsList = [];
                throw e;
            } finally {
                gBrief.clientsPromise = null;
            }
        })();
        return gBrief.clientsPromise;
    }

    async function gBriefLoadTemplates(force) {
        if (!force && gBrief.templatesList) {
            gBriefRenderTemplateOptions();
            return gBrief.templatesList;
        }
        if (gBrief.templatesPromise) return gBrief.templatesPromise;
        gBrief.templatesPromise = (async function() {
            try {
                const data = await window.clivoApi(
                    '/api/briefing-templates/?status=published'
                );
                gBrief.templatesList = Array.isArray(data) ? data : (data.results || []);
                gBriefRenderTemplateOptions();
                return gBrief.templatesList;
            } catch (e) {
                gBrief.templatesList = [];
                gBriefRenderTemplateOptions();
                throw e;
            } finally {
                gBrief.templatesPromise = null;
            }
        })();
        return gBrief.templatesPromise;
    }

    function gBriefRenderTemplateOptions() {
        const sel = gBrief.templateSelect;
        if (!sel) return;
        const list = gBrief.templatesList || [];
        if (!list.length) {
            sel.innerHTML = '<option value="">Nenhum modelo publicado</option>';
            return;
        }
        let html = '<option value="">Selecione…</option>';
        list.forEach(function(t) {
            html += '<option value="' + t.id + '">' +
                    escapeHtml(t.name || '—') +
                    '</option>';
        });
        sel.innerHTML = html;
    }

    function gBriefSuggestHandler() {
        if (!gBrief.emailInput || !gBrief.emailSuggest) return;
        const q = (gBrief.emailInput.value || '').trim().toLowerCase();
        if (!q) { gBriefCloseSuggest(); return; }
        const items = (gBrief.clientsList || []).filter(function(c) {
            return (c.email || '').toLowerCase().indexOf(q) !== -1;
        }).slice(0, 6);
        if (!items.length) { gBriefCloseSuggest(); return; }
        gBrief.emailSuggest.innerHTML = '';
        items.forEach(function(c) {
            const initial = (c.name || '?').charAt(0).toUpperCase();
            const item = document.createElement('div');
            item.className = 'g-suggest-item';
            item.innerHTML =
                '<div class="g-suggest-avatar">' + escapeHtml(initial) + '</div>' +
                '<div class="g-suggest-body">' +
                    '<div class="g-suggest-name">' + escapeHtml(c.name || '—') + '</div>' +
                    '<div class="g-suggest-meta">' + escapeHtml(c.email || '—') + '</div>' +
                '</div>';
            item.addEventListener('mousedown', function(ev) {
                ev.preventDefault();
                gBriefCloseSuggest();
                gBriefSetClientMode('existing');
                gBriefSelectClient(c);
            });
            gBrief.emailSuggest.appendChild(item);
        });
        gBrief.emailSuggest.classList.add('open');
        gBrief.activeSuggest = gBrief.emailSuggest;
    }

    function gBriefCloseSuggest() {
        if (gBrief.emailSuggest) gBrief.emailSuggest.classList.remove('open');
        gBrief.activeSuggest = null;
    }

    function gBriefClientSearchHandler() {
        if (!gBrief.clientSearchInput || !gBrief.clientSuggest) return;
        const q = (gBrief.clientSearchInput.value || '').trim().toLowerCase();
        if (gBrief.clientSearchClear) {
            gBrief.clientSearchClear.classList.toggle('hidden', !q);
        }
        if (!q) {
            gBriefCloseClientSuggest();
            return;
        }
        const items = (gBrief.clientsList || []).filter(function(c) {
            const name = (c.name || '').toLowerCase();
            const email = (c.email || '').toLowerCase();
            return name.indexOf(q) !== -1 || email.indexOf(q) !== -1;
        }).slice(0, 20);

        gBriefRenderClientSuggest(items, q);
    }

    function gBriefRenderClientSuggest(items, query) {
        const box = gBrief.clientSuggest;
        if (!box) return;
        box.innerHTML = '';

        if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'gb-client-suggest-empty';
            empty.textContent = 'Nenhum cliente encontrado.';
            box.appendChild(empty);
            box.classList.add('open');
            return;
        }

        items.forEach(function(c) {
            const initial = (c.name || '?').charAt(0).toUpperCase();
            const item = document.createElement('div');
            item.className = 'g-suggest-item';
            item.innerHTML =
                '<div class="g-suggest-avatar">' + escapeHtml(initial) + '</div>' +
                '<div class="g-suggest-body">' +
                    '<div class="g-suggest-name">' + escapeHtml(c.name || '—') + '</div>' +
                    '<div class="g-suggest-meta">' + escapeHtml(c.email || '—') + '</div>' +
                '</div>';
            item.addEventListener('mousedown', function(ev) {
                ev.preventDefault();
                gBriefCloseClientSuggest();
                gBriefSelectClient(c);
            });
            box.appendChild(item);
        });
        box.classList.add('open');
    }

    function gBriefCloseClientSuggest() {
        if (gBrief.clientSuggest) gBrief.clientSuggest.classList.remove('open');
    }

    function gBriefSelectClient(c) {
        if (!c) return;
        gBrief.selectedClient = c;
        if (gBrief.existingClientSelect) gBrief.existingClientSelect.value = c.id;
        if (gBrief.clientSearchInput) gBrief.clientSearchInput.value = c.name || '';
        if (gBrief.clientSearchClear) gBrief.clientSearchClear.classList.remove('hidden');

        if (gBrief.clientSelectedInfo) {
            gBrief.clientSelectedInfo.style.display = '';
        }
        if (gBrief.clientSelectedAvatar) {
            gBrief.clientSelectedAvatar.textContent =
                (c.name || '?').charAt(0).toUpperCase();
        }
        if (gBrief.clientSelectedName) {
            gBrief.clientSelectedName.textContent = c.name || '—';
        }
        if (gBrief.clientSelectedMeta) {
            const parts = [];
            if (c.email) parts.push(c.email);
            if (c.phone) parts.push(c.phone);
            gBrief.clientSelectedMeta.textContent = parts.join(' · ') || '—';
        }
        const wrap = document.getElementById('gbClientSearchWrap');
        if (wrap) wrap.classList.add('is-selected');
    }

    function gBriefClearSelectedClient() {
        gBrief.selectedClient = null;
        if (gBrief.existingClientSelect) gBrief.existingClientSelect.value = '';
        if (gBrief.clientSelectedInfo) gBrief.clientSelectedInfo.style.display = 'none';
        const wrap = document.getElementById('gbClientSearchWrap');
        if (wrap) wrap.classList.remove('is-selected');
        if (gBrief.clientSearchInput) {
            gBrief.clientSearchInput.value = '';
            gBrief.clientSearchInput.focus();
        }
        if (gBrief.clientSearchClear) gBrief.clientSearchClear.classList.add('hidden');
    }

    // ------------------------------------------------------------
    // SUBMIT DO FORM DE BRIEFING — handler único e idempotente
    // ------------------------------------------------------------
    async function gBriefSubmitHandler(e) {
        if (e) e.preventDefault();

        if (!gBrief.form) return;

        const templateId = gBrief.templateSelect ? gBrief.templateSelect.value : '';
        if (!templateId) {
            window.clivoShowToast('Selecione um modelo de briefing', 'error');
            return;
        }

        const titleRaw = (gBrief.titleInput.value || '').trim();
        if (!titleRaw) {
            window.clivoShowToast('Informe o título do briefing', 'error');
            if (gBrief.titleInput) gBrief.titleInput.focus();
            return;
        }

        const dateVal = gBrief.deadlineDate ? gBrief.deadlineDate.value : '';
        const timeVal = gBrief.deadlineTime ? gBrief.deadlineTime.value : '';
        if (!dateVal || !timeVal) {
            window.clivoShowToast('Informe a data e a hora do prazo', 'error');
            return;
        }
        const deadlineLocal = new Date(dateVal + 'T' + timeVal + ':00');
        if (isNaN(deadlineLocal.getTime())) {
            window.clivoShowToast('Prazo inválido', 'error');
            return;
        }
        if (deadlineLocal.getTime() <= Date.now()) {
            window.clivoShowToast('O prazo precisa ser no futuro', 'error');
            return;
        }

        let clientId = null;

        if (gBrief.clientMode === 'existing') {
            clientId = gBrief.existingClientSelect ? gBrief.existingClientSelect.value : '';
            if (!clientId) {
                window.clivoShowToast('Selecione um cliente existente', 'error');
                if (gBrief.clientSearchInput) gBrief.clientSearchInput.focus();
                return;
            }
        } else {
            const name = (gBrief.nameInput.value || '').trim();
            const email = (gBrief.emailInput.value || '').trim().toLowerCase();
            const phone = (gBrief.phoneInput.value || '').trim();
            if (!name) { window.clivoShowToast('Informe o nome do cliente', 'error'); return; }
            if (!email) { window.clivoShowToast('Informe o email do cliente', 'error'); return; }

            gBrief.submitBtn.disabled = true;
            const orig = gBrief.submitBtn.innerHTML;
            gBrief.submitBtn.innerHTML = 'Criando cliente…';
            try {
                const created = await window.clivoApi('/api/clients/', 'POST', {
                    name: name, email: email, phone: phone,
                });
                clientId = created.id;
                gBrief.lastCreatedClientId = created.id;
                window.Clivo.cache.clients = null;
                if (typeof window.clivoOnClientCreated === 'function') {
                    window.clivoOnClientCreated(created);
                }
            } catch (err) {
                window.clivoShowToast(err.message || 'Erro ao criar cliente', 'error');
                gBrief.submitBtn.disabled = false;
                gBrief.submitBtn.innerHTML = orig;
                return;
            }
        }

        const payload = {
            template_id: templateId,
            client_id: clientId,
            title: titleRaw,
            expires_at: deadlineLocal.toISOString(),
        };

        gBrief.submitBtn.disabled = true;
        const orig2 = gBrief.submitBtn.innerHTML;
        gBrief.submitBtn.innerHTML = 'Criando briefing…';

        try {
            const briefing = await window.clivoApi('/api/briefings/', 'POST', payload);
            gBrief.lastCreatedBriefingId = briefing.id;
            window.clivoShowToast('Briefing criado', 'success');

            if (typeof window.clivoOnBriefingCreated === 'function') {
                try {
                    window.clivoOnBriefingCreated(briefing, clientId);
                } catch (cbErr) {
                    console.error('clivoOnBriefingCreated falhou:', cbErr);
                }
            }

            if (window.Clivo.currentPage === 'clientes' &&
                typeof window.clivoRefreshClientes === 'function') {
                try {
                    window.clivoRefreshClientes();
                } catch (rfErr) {
                    console.error('clivoRefreshClientes falhou:', rfErr);
                }
            }

            gBriefCloseModal();
        } catch (err) {
            window.clivoShowToast(err.message || 'Erro ao criar briefing', 'error');
        } finally {
            gBrief.submitBtn.disabled = false;
            gBrief.submitBtn.innerHTML = orig2;
        }
    }

    function gBriefSetupModal() {
        gBrief.root = document.getElementById('gNewBriefingModal');
        gBrief.form = document.getElementById('gNewBriefingForm');
        gBrief.submitBtn = document.getElementById('gbSubmitBtn');
        gBrief.clientSwitch = document.getElementById('gbClientSwitch');
        gBrief.newClientFields = document.getElementById('gbNewClientFields');
        gBrief.existingClientFields = document.getElementById('gbExistingClientFields');
        gBrief.existingClientSelect = document.getElementById('gbExistingClient');
        gBrief.clientSearchInput = document.getElementById('gbClientSearch');
        gBrief.clientSearchClear = document.getElementById('gbClientSearchClear');
        gBrief.clientSuggest = document.getElementById('gbClientSuggest');
        gBrief.clientSelectedInfo = document.getElementById('gbClientSelectedInfo');
        gBrief.clientSelectedAvatar = document.getElementById('gbClientSelectedAvatar');
        gBrief.clientSelectedName = document.getElementById('gbClientSelectedName');
        gBrief.clientSelectedMeta = document.getElementById('gbClientSelectedMeta');
        gBrief.clientSelectedClear = document.getElementById('gbClientSelectedClear');
        gBrief.nameInput = document.getElementById('gbBriefName');
        gBrief.emailInput = document.getElementById('gbBriefEmail');
        gBrief.phoneInput = document.getElementById('gbBriefPhone');
        gBrief.emailSuggest = document.getElementById('gbBriefEmailSuggest');
        gBrief.templateSelect = document.getElementById('gbBriefTemplate');
        gBrief.titleInput = document.getElementById('gbBriefTitle');
        gBrief.deadlineDate = document.getElementById('gbBriefDeadlineDate');
        gBrief.deadlineTime = document.getElementById('gbBriefDeadlineTime');

        if (!gBrief.form) return;

        if (gBrief.clientSwitch) {
            gBrief.clientSwitch.querySelectorAll('.gb-switch-btn').forEach(function(b) {
                b.addEventListener('click', function() {
                    gBriefSetClientMode(this.dataset.mode);
                });
            });
        }

        if (gBrief.clientSearchInput) {
            gBrief.clientSearchInput.addEventListener('input', gBriefClientSearchHandler);
            gBrief.clientSearchInput.addEventListener('focus', function() {
                if (gBrief.clientSearchInput.value.trim()) gBriefClientSearchHandler();
            });
            gBrief.clientSearchInput.addEventListener('blur', function() {
                setTimeout(gBriefCloseClientSuggest, 150);
            });
            gBrief.clientSearchInput.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') {
                    gBriefCloseClientSuggest();
                }
            });
        }

        if (gBrief.clientSearchClear) {
            gBrief.clientSearchClear.addEventListener('click', function(e) {
                e.preventDefault();
                if (gBrief.clientSearchInput) gBrief.clientSearchInput.value = '';
                gBrief.clientSearchClear.classList.add('hidden');
                gBriefCloseClientSuggest();
                gBriefClearSelectedClient();
                if (gBrief.clientSearchInput) gBrief.clientSearchInput.focus();
            });
        }

        if (gBrief.clientSelectedClear) {
            gBrief.clientSelectedClear.addEventListener('click', function(e) {
                e.preventDefault();
                gBriefClearSelectedClient();
            });
        }

        if (gBrief.emailInput) {
            gBrief.emailInput.addEventListener('input', gBriefSuggestHandler);
            gBrief.emailInput.addEventListener('focus', function() {
                if (gBrief.emailInput.value.trim()) gBriefSuggestHandler();
            });
            gBrief.emailInput.addEventListener('blur', function() {
                setTimeout(gBriefCloseSuggest, 150);
            });
        }

        // Submit — ligado no form E no botão, com flag de idempotência.
        if (!gBrief.submitBound) {
            gBrief.form.addEventListener('submit', gBriefSubmitHandler);
            if (gBrief.submitBtn) {
                // O botão fica fora do form (no footer). O form="..." nativo
                // submete no clique, mas garantimos também via listener.
                gBrief.submitBtn.addEventListener('click', function(ev) {
                    // Só intercepta se o form association não disparar submit.
                    // Prevenimos o clique para evitar duplo submit nativo,
                    // e chamamos o handler diretamente.
                    ev.preventDefault();
                    gBriefSubmitHandler(ev);
                });
            }
            gBrief.submitBound = true;
        }

        gBrief.root.querySelectorAll('[data-g-close="gNewBriefingModal"]').forEach(function(el) {
            el.addEventListener('click', gBriefCloseModal);
        });
        gBrief.root.addEventListener('click', function(e) {
            if (e.target === gBrief.root) gBriefCloseModal();
        });
    }

    window.clivoOpenNewBriefingModal = gBriefOpenModal;

    // ============================================================
    // RAIL
    // ============================================================
    function bindRail() {
        const themeBtn = document.getElementById('themeToggle');
        const logoutBtn = document.getElementById('logoutBtn');
        const newBriefingBtn = document.getElementById('newBriefingBtn');
        const newClientBtn = document.getElementById('newClientBtn');
        const configBtn = document.getElementById('configToggle');

        if (themeBtn) themeBtn.addEventListener('click', window.clivoToggleTheme);
        if (logoutBtn) logoutBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            window.clivoLogout();
        });
        if (newBriefingBtn) newBriefingBtn.addEventListener('click', function() {
            gBriefOpenModal();
        });
        if (newClientBtn) newClientBtn.addEventListener('click', function() {
            gOpenModal();
        });
        if (configBtn) configBtn.addEventListener('click', function() {
            softNavigate('/configuracoes/');
        });
    }

    // ============================================================
    // SOFT NAV
    // ============================================================
    const navProgress = document.getElementById('softNavProgress');
    const pageCache = new Map();
    const CACHE_TTL_MS = 60000;
    let isNavigating = false;

    function findLinkByPath(path) {
        let found = null;
        document.querySelectorAll('.sidebar-nav a[href]').forEach(function(a) {
            const href = a.getAttribute('href');
            if (!href || href === '#') return;
            if (href === path || href === path + '/') {
                found = a;
            } else if (a.dataset.nav === 'mesa' && path.indexOf('/mesa/') === 0) {
                found = a;
            } else if (a.dataset.nav === 'clientes' && path.indexOf('/clientes') === 0) {
                found = a;
            } else if (a.dataset.nav === 'briefings' && path.indexOf('/fluxo') === 0) {
                found = a;
            }
        });
        return found;
    }

    function setActiveNav(path) {
        document.querySelectorAll('.sidebar-nav a').forEach(function(l) {
            l.classList.remove('active');
        });
        const link = findLinkByPath(path);
        if (link) link.classList.add('active');
        const cfgBtn = document.getElementById('configToggle');
        if (cfgBtn) {
            if (path.indexOf('/configuracoes') === 0) cfgBtn.classList.add('is-active');
            else cfgBtn.classList.remove('is-active');
        }
    }

    function extractMain(html) {
        const tpl = document.createElement('template');
        tpl.innerHTML = html;
        const mainEl = tpl.content.querySelector('main#mainContent');
        const titleEl = tpl.content.querySelector('title');
        const links = [];
        tpl.content.querySelectorAll('link[rel="stylesheet"]').forEach(function(link) {
            const href = link.getAttribute('href');
            if (href && !isGlobalCss(href)) links.push(href);
        });
        const scripts = [];
        tpl.content.querySelectorAll('script[src]').forEach(function(script) {
            const src = script.getAttribute('src');
            if (src && !isGlobalJs(src)) scripts.push(src);
        });
        if (!mainEl) {
            return {
                mainHTML: '',
                mainPage: '',
                title: titleEl ? titleEl.textContent : document.title,
                links: links, scripts: scripts, timestamp: Date.now(),
            };
        }
        return {
            mainHTML: mainEl.innerHTML,
            mainPage: mainEl.dataset.page || '',
            title: titleEl ? titleEl.textContent : document.title,
            links: links, scripts: scripts, timestamp: Date.now(),
        };
    }

    async function getPage(href) {
        const cached = pageCache.get(href);
        if (cached && (Date.now() - cached.timestamp) < CACHE_TTL_MS) return cached;
        const resp = await fetch(href, {
            credentials: 'include',
            headers: { 'X-Requested-With': 'soft-nav' }
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const finalUrl = resp.url || href;
        const html = await resp.text();
        const parsed = extractMain(html);
        parsed.finalUrl = finalUrl;
        pageCache.set(href, parsed);
        return parsed;
    }

    function preloadPage(href) {
        if (!href || href === '#') return;
        if (pageCache.has(href)) return;
        fetch(href, {
            credentials: 'include',
            headers: { 'X-Requested-With': 'soft-nav' }
        })
            .then(function(r) {
                if (!r.ok) return '';
                const finalUrl = r.url || href;
                return r.text().then(function(html) {
                    const parsed = extractMain(html);
                    parsed.finalUrl = finalUrl;
                    pageCache.set(href, parsed);
                });
            })
            .catch(function() {});
    }

    async function softNavigate(href, opts) {
        opts = opts || {};
        if (isNavigating) return;
        isNavigating = true;
        if (navProgress) navProgress.classList.add('active');
        try {
            const page = await getPage(href);
            const curMain = document.getElementById('mainContent');
            if (!curMain || !page.mainHTML) {
                window.location.href = href;
                return;
            }
            const oldPage = window.Clivo.currentPage;
            const newPage = page.mainPage || null;
            if (oldPage && window.ClivoPages[oldPage] &&
                typeof window.ClivoPages[oldPage].unmount === 'function') {
                try { window.ClivoPages[oldPage].unmount(); }
                catch (e) { console.error('unmount ' + oldPage + ' falhou:', e); }
            }
            (page.links || []).forEach(ensureStylesheetLoaded);
            let assetsReady = Promise.resolve();
            (page.scripts || []).forEach(function(src) {
                assetsReady = assetsReady.then(function() {
                    return ensureScriptLoaded(src);
                });
            });
            await assetsReady;
            curMain.innerHTML = page.mainHTML;
            curMain.dataset.page = newPage || '';
            window.Clivo.currentPage = newPage;
            if (page.title) document.title = page.title;
            setActiveNav(page.finalUrl || href);
            if (!opts.replace) {
                const displayUrl = page.finalUrl || href;
                history.pushState({ soft: true, path: displayUrl }, '', displayUrl);
            }
            if (newPage && window.ClivoPages[newPage] &&
                typeof window.ClivoPages[newPage].mount === 'function') {
                try { window.ClivoPages[newPage].mount(); }
                catch (e) { console.error('mount ' + newPage + ' falhou:', e); }
            }
            if (typeof opts.afterMount === 'function') {
                try { opts.afterMount(); } catch (e) { console.error(e); }
            }
            requestAnimationFrame(function() {
                requestAnimationFrame(function() {
                    window.clivoRefreshIcons();
                    curMain.classList.add('is-entering');
                    requestAnimationFrame(function() {
                        curMain.classList.remove('is-entering');
                    });
                });
            });
            requestAnimationFrame(function() { window.scrollTo(0, 0); });
        } catch (e) {
            console.error('soft navigation falhou:', e);
            window.location.href = href;
        } finally {
            if (navProgress) navProgress.classList.remove('active');
            isNavigating = false;
        }
    }

    window.clivoSoftNavigate = softNavigate;

    // ============================================================
    // NAV
    // ============================================================
    function bindSidebarNav() {
        document.querySelectorAll('.sidebar-nav a').forEach(function(link) {
            const href = link.getAttribute('href');
            const isLocked = link.dataset.navLocked === '1';

            if (!isLocked && href && href !== '#') {
                link.addEventListener('mouseenter', function() {
                    preloadPage(href);
                });
            }

            link.addEventListener('click', function(e) {
                if (isLocked) {
                    e.preventDefault();
                    window.clivoShowToast('Esta área está em desenvolvimento.', 'info');
                    return;
                }

                const currentHref = link.getAttribute('href');

                if (!currentHref || currentHref === '#') {
                    e.preventDefault();
                    return;
                }

                e.preventDefault();

                if (link.classList.contains('active') &&
                    currentHref === window.location.pathname) {
                    if (isMobile()) closeSidebar();
                    return;
                }

                softNavigate(currentHref);
            });
        });
    }

    window.addEventListener('popstate', function() {
        softNavigate(window.location.pathname, { replace: true });
    });

    // ============================================================
    // WORKSPACE SWITCH
    // ============================================================
    const wsSwitch = document.getElementById('workspaceSwitch');
    const wsDropdown = document.getElementById('wsDropdown');
    const wsDropdownItems = document.getElementById('wsDropdownItems');
    const wsCreateBtn = document.getElementById('wsCreateBtn');

    function toggleWsDropdown(force) {
        if (!wsDropdown || !wsSwitch) return;
        const willOpen = (typeof force === 'boolean')
            ? force
            : !wsDropdown.classList.contains('open');
        wsDropdown.classList.toggle('open', willOpen);
        wsSwitch.classList.toggle('open', willOpen);
        if (willOpen) loadWorkspaceSwitcher();
    }

    async function loadWorkspaceSwitcher() {
        if (!wsDropdownItems) return;
        try {
            const list = await window.clivoApi('/api/workspaces/my/');
            renderWsDropdownItems(list || []);
        } catch (e) {
            wsDropdownItems.innerHTML =
                '<div style="padding:8px 10px; font-size:12px; color:var(--text-tertiary);">' +
                'Erro ao carregar workspaces</div>';
        }
    }

    function renderWsDropdownItems(list) {
        if (!list.length) {
            wsDropdownItems.innerHTML =
                '<div style="padding:8px 10px; font-size:12px; color:var(--text-tertiary);">' +
                'Nenhum workspace</div>';
            return;
        }
        let html = '';
        list.forEach(function(ws) {
            const initial = (ws.name || 'W').charAt(0).toUpperCase();
            const role = ws.governance_name || ws.governance_key || '';
            html +=
                '<div class="ws-item' + (ws.is_current ? ' is-current' : '') + '" ' +
                     'data-ws-public-id="' + escapeHtml(ws.public_id || '') + '">' +
                    '<div class="ws-item-avatar">' + initial + '</div>' +
                    '<div class="ws-item-info">' +
                        '<div class="ws-item-name">' + escapeHtml(ws.name) + '</div>' +
                        '<div class="ws-item-role">' + escapeHtml(role) + '</div>' +
                    '</div>' +
                    (ws.is_current ? '<i data-lucide="check" class="ws-item-check"></i>' : '') +
                '</div>';
        });
        wsDropdownItems.innerHTML = html;
        window.clivoRefreshIcons();
        wsDropdownItems.querySelectorAll('.ws-item').forEach(function(el) {
            el.addEventListener('click', function() {
                const publicId = this.dataset.wsPublicId;
                if (this.classList.contains('is-current')) {
                    toggleWsDropdown(false);
                    return;
                }
                if (!publicId) { window.location.href = '/workspaces/entrar/'; return; }
                window.location.href = '/mesa/' + publicId + '/';
            });
        });
    }

    function bindWorkspaceSwitch() {
        if (wsSwitch) {
            wsSwitch.addEventListener('click', function(e) {
                e.stopPropagation();
                toggleWsDropdown();
            });
        }
        if (wsCreateBtn) {
            wsCreateBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                toggleWsDropdown(false);
                window.location.href = '/workspaces/novo/';
            });
        }
        document.addEventListener('click', function(e) {
            if (!wsDropdown || !wsDropdown.classList.contains('open')) return;
            if (wsDropdown.contains(e.target) || (wsSwitch && wsSwitch.contains(e.target))) return;
            toggleWsDropdown(false);
        });
    }

    // ============================================================
    // PLANO
    // ============================================================
    function renderSidebarPlan(workspace) {
        const card = document.getElementById('sidebarPlan');
        const nameEl = document.getElementById('sidebarPlanName');
        const priceEl = document.getElementById('sidebarPlanPrice');
        const badgeEl = document.getElementById('sidebarPlanBadge');
        if (!card) return;
        const plan = workspace && workspace.plan;
        card.hidden = false;
        if (!plan) {
            if (nameEl) nameEl.textContent = 'Essencial';
            if (priceEl) priceEl.textContent = 'BRL 89.90 /mês';
            if (badgeEl) { badgeEl.classList.remove('inactive'); badgeEl.textContent = 'Ativo'; }
            return;
        }
        if (nameEl) nameEl.textContent = plan.name || 'Essencial';
        if (priceEl) {
            if (plan.price) {
                const cur = plan.currency || 'BRL';
                const periodLabel = (
                    plan.billing_period === 'monthly' ? 'mês' :
                    plan.billing_period === 'yearly' ? 'ano' :
                    plan.billing_period === 'lifetime' ? 'vitalício' :
                    plan.billing_period || 'mês'
                );
                priceEl.textContent = cur + ' ' + plan.price + ' /' + periodLabel;
            } else {
                priceEl.textContent = 'BRL 89.90 /mês';
            }
        }
        if (badgeEl) { badgeEl.classList.remove('inactive'); badgeEl.textContent = 'Ativo'; }
    }

    function rewriteMesaLink(workspace) {
        if (!workspace || !workspace.public_id) return;
        const link = document.getElementById('navMesaLink');
        if (link) link.setAttribute('href', '/mesa/' + workspace.public_id + '/');
    }

    // ============================================================
    // CAPABILITIES
    // ============================================================
    async function loadCapabilities() {
        try {
            const data = await window.clivoApi('/api/workspaces/my-capabilities/');
            if (data) {
                window.Clivo.capabilities = data.capabilities || [];
                window.Clivo.isOwner = !!data.is_owner;
                window.Clivo.governanceKey = data.governance_key || null;
            }
        } catch (e) {
            window.Clivo.capabilities = [];
        }
    }

    // ============================================================
    // USER + WORKSPACE
    // ============================================================
    async function loadUserAndWorkspace() {
        try {
            const userResp = await fetch('/api/users/me/', {
                method: 'GET',
                credentials: 'include',
                headers: { 'X-CSRFToken': window.clivoGetCookie('csrftoken') }
            });
            if (userResp.ok) {
                const user = await userResp.json();
                window.Clivo.user = user;
                window.clivoCurrentUser = user;
                const fullName = user.full_name || user.email || 'Usuário';
                const initial = fullName.charAt(0).toUpperCase();
                const avatarUrl = user.avatar_url || user.avatar || null;
                const img = document.getElementById('userAvatarImg');
                const fallback = document.getElementById('userAvatarFallback');
                if (avatarUrl && img && fallback) {
                    img.onerror = function() {
                        img.onerror = null;
                        img.style.display = 'none';
                        fallback.style.display = 'block';
                        fallback.textContent = initial;
                    };
                    img.src = avatarUrl;
                    img.style.display = 'block';
                    fallback.style.display = 'none';
                } else if (fallback) {
                    fallback.style.display = 'block';
                    fallback.textContent = initial;
                }
            }
        } catch (e) {
            console.error('Falha ao carregar usuário:', e);
        }

        try {
            const wsResp = await fetch('/api/workspaces/current/', {
                method: 'GET',
                credentials: 'include',
                headers: { 'X-CSRFToken': window.clivoGetCookie('csrftoken') }
            });
            if (wsResp.ok) {
                const ws = await wsResp.json();
                window.Clivo.workspace = ws;
                window.clivoCurrentWorkspace = ws;
                const publicIdFromUrl = window.Clivo.workspacePublicIdFromUrl;
                if (publicIdFromUrl) ws.public_id = publicIdFromUrl;
                const wsName = document.getElementById('wsName');
                const wsAvatarText = document.getElementById('wsAvatarText');
                const wsAvatarImg = document.getElementById('wsAvatarImg');
                if (wsName) wsName.textContent = ws.name || 'Workspace';
                if (wsAvatarText) wsAvatarText.textContent = (ws.name || 'W').charAt(0).toUpperCase();
                if (ws.avatar_url && wsAvatarImg && wsAvatarText) {
                    wsAvatarImg.src = ws.avatar_url;
                    wsAvatarImg.style.display = 'block';
                    wsAvatarText.style.display = 'none';
                }
                renderSidebarPlan(ws);
                rewriteMesaLink(ws);
            } else if (wsResp.status === 404) {
                renderSidebarPlan(null);
            }
        } catch (e) {
            console.error('Falha ao carregar workspace:', e);
            renderSidebarPlan(null);
        }
    }

    // ============================================================
    // BOOT
    // ============================================================
    async function shellBoot() {
        const loadingState = document.getElementById('loadingState');
        const appContent = document.getElementById('appContent');
        try {
            const sessionResp = await fetch('/api/auth/session/', {
                method: 'GET',
                credentials: 'include'
            });
            if (!sessionResp.ok) { window.location.href = '/login/'; return; }
            if (loadingState) loadingState.classList.add('hidden');
            if (appContent) appContent.classList.remove('hidden');
            window.clivoRefreshIcons();
            await loadUserAndWorkspace();
            await loadCapabilities();
            setActiveNav(window.location.pathname);
            const curMain = document.getElementById('mainContent');
            const initialPage = curMain && curMain.dataset.page;
            window.Clivo.currentPage = initialPage || null;
            if (initialPage && window.ClivoPages[initialPage] &&
                typeof window.ClivoPages[initialPage].mount === 'function') {
                try { window.ClivoPages[initialPage].mount(); }
                catch (e) { console.error('mount inicial falhou:', e); }
            }
            requestAnimationFrame(function() { window.clivoRefreshIcons(); });

            setTimeout(function() {
                preloadPage('/clientes/');
                preloadPage('/fluxo/');
                if (window.Clivo.workspace && window.Clivo.workspace.public_id) {
                    preloadPage('/mesa/' + window.Clivo.workspace.public_id + '/');
                } else {
                    preloadPage('/mesa/');
                }
            }, 800);
        } catch (e) {
            console.error('Erro na inicialização:', e);
            if (loadingState) {
                loadingState.innerHTML =
                    '<div style="text-align:center; padding:40px;">' +
                    '<i class="fas fa-exclamation-triangle" style="font-size:32px; color:#E5484D; display:block; margin-bottom:12px;"></i>' +
                    'Erro ao carregar.<br>' +
                    '<button onclick="window.location.href=\'/login/\'" style="margin-top:12px; padding:8px 20px; border:1px solid #E9E9EC; border-radius:6px; background:white; cursor:pointer; font-family:inherit;">' +
                    'Voltar ao login' +
                    '</button>' +
                    '</div>';
            }
        }
    }

    // ============================================================
    // DOM READY
    // ============================================================
    document.addEventListener('DOMContentLoaded', function() {
        bindMobileDrawer();
        bindRail();
        bindSidebarNav();
        bindWorkspaceSwitch();
        gSetupNewClientModal();
        gBriefSetupModal();
        shellBoot();
    });
})();