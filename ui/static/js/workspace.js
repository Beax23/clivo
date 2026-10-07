(function() {
    'use strict';

    // =========================================================================
    // HELPERS
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

    const toastContainer = document.getElementById('toastContainer');
    let toastTimeout = null;

    function showToast(message, type) {
        type = type || 'info';
        while (toastContainer.firstChild) toastContainer.removeChild(toastContainer.firstChild);

        const toast = document.createElement('div');
        toast.className = 'toast toast-' + type;
        const iconMap = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            info: 'fa-info-circle'
        };
        toast.innerHTML =
            '<span class="toast-icon"><i class="fas ' + (iconMap[type] || iconMap.info) + '"></i></span>' +
            '<span class="toast-content">' + message + '</span>' +
            '<button class="toast-close"><i class="fas fa-times"></i></button>';

        toastContainer.appendChild(toast);

        toast.querySelector('.toast-close').addEventListener('click', function() {
            toast.classList.add('hiding');
            setTimeout(function() { toast.remove(); }, 300);
        });

        clearTimeout(toastTimeout);
        toastTimeout = setTimeout(function() {
            toast.classList.add('hiding');
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    }

    function setLoading(button, loading, label) {
        if (loading) {
            button.disabled = true;
            button.dataset.originalText = button.innerHTML;
            button.innerHTML = '<span class="spinner"></span> ' + (label || 'Criando...');
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.originalText || button.textContent;
        }
    }

    // =========================================================================
    // FORMATAÇÃO DE UF E CNPJ
    // =========================================================================
    function setupStateInput() {
        const input = document.getElementById('state');
        if (!input) return;
        input.addEventListener('input', function() {
            this.value = (this.value || '').toUpperCase().replace(/[^A-Z]/g, '').slice(0, 2);
        });
    }

    function setupCnpjInput() {
        const input = document.getElementById('cnpj');
        if (!input) return;
        input.addEventListener('input', function() {
            let v = this.value.replace(/\D/g, '').slice(0, 14);
            v = v
                .replace(/^(\d{2})(\d)/, '$1.$2')
                .replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3')
                .replace(/\.(\d{3})(\d)/, '.$1/$2')
                .replace(/(\d{4})(\d)/, '$1-$2');
            this.value = v;
        });
    }

    // =========================================================================
    // BARRA DE PROGRESSO — helpers
    // =========================================================================
    function showProgressBar() {
        const topbar = document.getElementById('workspaceTopbar');
        if (topbar) topbar.classList.add('is-loading');
    }

    function hideProgressBar() {
        const topbar = document.getElementById('workspaceTopbar');
        if (topbar) topbar.classList.remove('is-loading');
    }

    // =========================================================================
    // BOTÃO VOLTAR — faz logout e só então navega para /login/
    //
    // Durante o POST de logout, a barra de progresso no topo do header
    // fica visível e animada, dando feedback visual ao usuário.
    // =========================================================================
    function setupBackButton() {
        const btn = document.getElementById('backToLogin');
        if (!btn) return;

        btn.addEventListener('click', async function() {
            btn.disabled = true;
            showProgressBar();

            try {
                await fetch('/api/auth/logout/', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'X-CSRFToken': getCookie('csrftoken') },
                });
            } catch (e) {
                // Mesmo se o logout falhar (rede, CSRF, etc.),
                // seguimos para /login/.
                console.warn('Logout falhou, seguindo para /login/:', e);
            }

            // Mantém a barra visível durante a navegação.
            // A página é destruída no redirect e a barra vai junto.
            window.location.href = '/login/';
        });
    }

    // =========================================================================
    // GUARD: já tem Workspace? Vai para /workspaces/entrar/
    // =========================================================================
    async function checkExistingWorkspace() {
        try {
            const resp = await fetch('/api/workspaces/', {
                method: 'GET',
                credentials: 'include',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            if (!resp.ok) return false;

            const data = await resp.json();
            const list = Array.isArray(data) ? data : (data.results || []);
            if (list.length > 0) {
                window.location.href = '/workspaces/entrar/';
                return true;
            }
            return false;
        } catch (e) {
            return false;
        }
    }

    // =========================================================================
    // SUBMIT
    // =========================================================================
    function setupForm() {
        const form = document.getElementById('workspaceForm');
        const btn = document.getElementById('submitBtn');
        if (!form || !btn) return;

        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            const name = document.getElementById('name').value.trim();
            const city = document.getElementById('city').value.trim();
            const state = document.getElementById('state').value.trim().toUpperCase();
            const cnpj = document.getElementById('cnpj').value.trim();

            if (!name) {
                showToast('Informe o nome do escritório', 'error');
                document.getElementById('name').focus();
                return;
            }
            if (state && state.length !== 2) {
                showToast('UF deve ter 2 letras', 'error');
                document.getElementById('state').focus();
                return;
            }

            setLoading(btn, true, 'Criando seu espaço...');

            try {
                const response = await fetch('/api/workspaces/', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                    },
                    body: JSON.stringify({
                        name: name,
                        city: city,
                        state: state,
                        cnpj: cnpj,
                    }),
                });

                if (response.status === 201) {
                    const data = await response.json();

                    if (data && data.public_id) {
                        window.location.href = '/mesa/' + data.public_id + '/';
                    } else {
                        window.location.href = '/workspaces/entrar/';
                    }
                    return;
                }

                let data = null;
                try { data = await response.json(); } catch (err) { /* sem body */ }

                let msg = 'Erro ao criar o workspace';
                if (data) {
                    if (typeof data.error === 'string') msg = data.error;
                    else if (typeof data.detail === 'string') msg = data.detail;
                    else if (typeof data.name === 'object') msg = data.name[0];
                    else if (typeof data.state === 'object') msg = data.state[0];
                }
                showToast(msg, 'error');
                setLoading(btn, false);

            } catch (err) {
                console.error('Erro de rede:', err);
                showToast('Não foi possível criar. Verifique sua conexão.', 'error');
                setLoading(btn, false);
            }
        });
    }

    // =========================================================================
    // BOOT
    // =========================================================================
    async function boot() {
        setupStateInput();
        setupCnpjInput();
        setupBackButton();

        const redirected = await checkExistingWorkspace();
        if (redirected) return;

        setupForm();

        document.body.classList.remove('loading');
        document.body.classList.add('loaded');

        const nameInput = document.getElementById('name');
        if (nameInput) nameInput.focus();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();