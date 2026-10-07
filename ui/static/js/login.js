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
            button.innerHTML = '<span class="spinner"></span> ' + (label || 'Aguarde...');
        } else {
            button.disabled = false;
            button.innerHTML = button.dataset.originalText || button.textContent;
        }
    }

    function setMessage(containerId, type, text) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';
        if (!text) return;
        const div = document.createElement('div');
        div.className = 'message ' + type;
        div.textContent = text;
        container.appendChild(div);
    }

    // =========================================================================
    // RESOLUÇÃO DE ENTRADA PÓS-LOGIN
    // =========================================================================
    // Pergunta ao backend para onde ir. Nunca "adivinha" no JS.
    //   target == "console"   → /console/
    //   target == "workspace" → /workspaces/entrar/
    // =========================================================================
    async function resolveEntryUrl() {
        try {
            const resp = await fetch('/api/auth/entry/', {
                method: 'GET',
                credentials: 'include',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
            });
            if (resp.ok) {
                const data = await resp.json();
                if (data && data.target === 'console') {
                    return '/console/';
                }
            }
        } catch (e) {
            console.error('Falha ao resolver entrada:', e);
        }
        // Fallback conservador: fluxo de Workspace
        return '/workspaces/entrar/';
    }

    async function goAfterLogin() {
        const target = await resolveEntryUrl();
        window.location.href = target;
    }

    // =========================================================================
    // TOGGLE PASSWORD
    // =========================================================================
    function setupPasswordToggles() {
        const toggles = [
            { btn: 'togglePassword', input: 'password' },
            { btn: 'toggleSignupPassword', input: 'signupPassword' },
            { btn: 'toggleSignupConfirm', input: 'signupConfirm' },
        ];
        toggles.forEach(function(t) {
            const btn = document.getElementById(t.btn);
            const input = document.getElementById(t.input);
            if (!btn || !input) return;
            btn.addEventListener('click', function() {
                const isPassword = input.type === 'password';
                input.type = isPassword ? 'text' : 'password';
                const icon = btn.querySelector('i');
                if (icon) {
                    icon.className = isPassword ? 'far fa-eye-slash' : 'far fa-eye';
                }
            });
        });
    }

    // =========================================================================
    // LOGIN (email + senha)
    // =========================================================================
    function setupLoginForm() {
        const form = document.getElementById('loginForm');
        const btn = document.getElementById('loginBtn');
        if (!form || !btn) return;

        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            const email = document.getElementById('email').value.trim();
            const password = document.getElementById('password').value;

            if (!email || !password) {
                setMessage('messageContainer', 'error', 'Preencha email e senha');
                return;
            }

            setMessage('messageContainer', '', '');
            setLoading(btn, true, 'Entrando...');

            try {
                const response = await fetch('/api/auth/login/', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                    },
                    body: JSON.stringify({ email: email, password: password }),
                });

                if (response.ok) {
                    await goAfterLogin();
                    return;
                }

                let data = null;
                try { data = await response.json(); } catch (err) { /* sem body */ }
                const msg = (data && (data.detail || data.error)) || 'Credenciais inválidas';
                setMessage('messageContainer', 'error', msg);
                setLoading(btn, false);

            } catch (err) {
                console.error('Erro de rede:', err);
                setMessage('messageContainer', 'error', 'Não foi possível conectar. Tente novamente.');
                setLoading(btn, false);
            }
        });
    }

    // =========================================================================
    // CADASTRO
    // =========================================================================
    function setupSignupForm() {
        const form = document.getElementById('signupForm');
        const btn = document.getElementById('signupBtn');
        if (!form || !btn) return;

        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            const name = document.getElementById('signupName').value.trim();
            const email = document.getElementById('signupEmail').value.trim();
            const password = document.getElementById('signupPassword').value;
            const confirm = document.getElementById('signupConfirm').value;

            if (!name || !email || !password || !confirm) {
                setMessage('signupMessageContainer', 'error', 'Preencha todos os campos');
                return;
            }
            if (password !== confirm) {
                setMessage('signupMessageContainer', 'error', 'As senhas não coincidem');
                return;
            }
            if (password.length < 6) {
                setMessage('signupMessageContainer', 'error', 'A senha deve ter no mínimo 6 caracteres');
                return;
            }

            const parts = name.split(/\s+/);
            const firstName = parts[0] || '';
            const lastName = parts.slice(1).join(' ') || '';

            setMessage('signupMessageContainer', '', '');
            setLoading(btn, true, 'Cadastrando...');

            try {
                const response = await fetch('/api/users/', {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                    },
                    body: JSON.stringify({
                        email: email,
                        first_name: firstName,
                        last_name: lastName,
                        password: password,
                        password_confirm: confirm,
                    }),
                });

                if (response.ok) {
                    await goAfterLogin();
                    return;
                }

                let data = null;
                try { data = await response.json(); } catch (err) { /* sem body */ }

                let msg = 'Erro ao cadastrar';
                if (data) {
                    if (typeof data.detail === 'string') msg = data.detail;
                    else if (typeof data.email === 'object') msg = data.email[0];
                    else if (typeof data.password === 'object') msg = data.password[0];
                    else if (typeof data.password_confirm === 'object') msg = data.password_confirm[0];
                    else if (typeof data.error === 'string') msg = data.error;
                }
                setMessage('signupMessageContainer', 'error', msg);
                setLoading(btn, false);

            } catch (err) {
                console.error('Erro de rede:', err);
                setMessage('signupMessageContainer', 'error', 'Não foi possível conectar. Tente novamente.');
                setLoading(btn, false);
            }
        });
    }

    // =========================================================================
    // TROCA LOGIN ⇄ CADASTRO
    // =========================================================================
    function setupFormSwitch() {
        const loginForm = document.getElementById('loginForm');
        const signupContainer = document.getElementById('signupContainer');
        const loginDivider = document.getElementById('loginDivider');
        const loginFooter = document.getElementById('loginFooter');
        const backBtn = document.getElementById('backToLoginFromSignup');
        const formTitle = document.getElementById('formTitle');
        const formSubtitle = document.getElementById('formSubtitle');
        const loginTerms = document.getElementById('loginTerms');

        const createAccountBtn = document.getElementById('createAccountBtn');
        const backToLoginBtn = document.getElementById('backToLoginBtn');

        function showSignup() {
            loginForm.classList.add('hidden');
            loginDivider.classList.add('hidden');
            loginFooter.classList.add('hidden');
            signupContainer.classList.add('active');
            backBtn.style.display = 'inline-flex';
            formTitle.textContent = 'Criar sua conta';
            formSubtitle.textContent = 'Comece gratuitamente';
            if (loginTerms) loginTerms.style.display = 'none';
        }

        function showLogin() {
            loginForm.classList.remove('hidden');
            loginDivider.classList.remove('hidden');
            loginFooter.classList.remove('hidden');
            signupContainer.classList.remove('active');
            backBtn.style.display = 'none';
            formTitle.textContent = 'Bem-vindo de volta';
            formSubtitle.textContent = 'Entre para continuar';
            if (loginTerms) loginTerms.style.display = '';
        }

        if (createAccountBtn) createAccountBtn.addEventListener('click', showSignup);
        if (backToLoginBtn) backToLoginBtn.addEventListener('click', showLogin);
        if (backBtn) backBtn.addEventListener('click', showLogin);
    }

    // =========================================================================
    // GOOGLE LOGIN
    // =========================================================================
    function setupGoogleLogin() {
        const btn = document.getElementById('googleLoginBtn');
        if (!btn) return;

        btn.addEventListener('click', function() {
            // O allauth redireciona o callback para LOGIN_REDIRECT_URL.
            // O PostLoginRedirectView decide console vs workspaces usando
            // o mesmo resolve_entry_target() do endpoint /api/auth/entry/.
            window.location.href = '/auth/google/?surface=app';
        });
    }

    // =========================================================================
    // ESQUECI A SENHA
    // =========================================================================
    function setupForgotPassword() {
        const modal = document.getElementById('forgotPasswordModal');
        const openBtn = document.getElementById('forgotPasswordBtn');
        const closeBtn = document.getElementById('closeForgotPassword');
        const backBtn = document.getElementById('backToLoginFromForgot');
        const resetBtn = document.getElementById('resetBtn');
        const resetForm = document.getElementById('forgotPasswordForm');
        const resetSuccess = document.getElementById('resetSuccess');
        const resetSuccessBtn = document.getElementById('resetSuccessBtn');
        const resetEmail = document.getElementById('resetEmail');
        const resetMessage = document.getElementById('resetMessageContainer');

        if (!modal || !openBtn) return;

        function open() {
            resetForm.classList.remove('hidden');
            resetSuccess.classList.remove('active');
            resetMessage.innerHTML = '';
            resetEmail.value = '';
            modal.classList.add('active');
            setTimeout(function() { resetEmail.focus(); }, 100);
        }

        function close() {
            modal.classList.remove('active');
        }

        openBtn.addEventListener('click', open);
        if (closeBtn) closeBtn.addEventListener('click', close);
        if (backBtn) backBtn.addEventListener('click', close);
        if (resetSuccessBtn) resetSuccessBtn.addEventListener('click', close);

        modal.addEventListener('click', function(e) {
            if (e.target === modal) close();
        });

        if (resetBtn) {
            resetBtn.addEventListener('click', async function() {
                const email = resetEmail.value.trim();
                if (!email) {
                    resetMessage.innerHTML = '<div class="message error">Informe seu email</div>';
                    return;
                }

                resetMessage.innerHTML = '';
                setLoading(resetBtn, true, 'Enviando...');

                try {
                    const response = await fetch('/api/auth/password/reset/', {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken'),
                        },
                        body: JSON.stringify({ email: email }),
                    });

                    setLoading(resetBtn, false);

                    if (response.ok) {
                        resetForm.classList.add('hidden');
                        resetSuccess.classList.add('active');
                    } else {
                        resetMessage.innerHTML = '<div class="message error">Erro ao enviar. Tente novamente.</div>';
                    }

                } catch (err) {
                    setLoading(resetBtn, false);
                    resetMessage.innerHTML = '<div class="message error">Erro de conexão. Tente novamente.</div>';
                }
            });
        }
    }

    // =========================================================================
    // BOOT
    // =========================================================================
    function boot() {
        setupPasswordToggles();
        setupLoginForm();
        setupSignupForm();
        setupFormSwitch();
        setupGoogleLogin();
        setupForgotPassword();

        fetch('/api/auth/csrf/', {
            credentials: 'include',
        }).catch(function() { /* best effort */ });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();