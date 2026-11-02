document.addEventListener('DOMContentLoaded', () => {
    const formLogin = document.getElementById('form-login');
    const alertBox = document.getElementById('auth-alert');
    const alertText = document.getElementById('auth-alert-text');
    const alertIcon = document.getElementById('auth-alert-icon');
    const pinInput = document.getElementById('login-pin');

    // Auto-focus the PIN input field
    if (pinInput) {
        pinInput.focus();
    }

    // Toggle PIN Visibility
    document.querySelectorAll('.toggle-password-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const input = document.getElementById('login-pin');
            if (!input) return;
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            const icon = btn.querySelector('.eye-icon');
            if (icon) {
                if (isPassword) {
                    icon.innerHTML = `
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"/>
                    `;
                } else {
                    icon.innerHTML = `
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
                    `;
                }
            }
        });
    });

    // Helper: Show Alert
    function showAlert(msg, isSuccess = false) {
        if (!alertBox) return;
        alertBox.classList.remove('hidden', 'bg-rose-950/70', 'border-rose-500/30', 'text-rose-200', 'bg-emerald-950/70', 'border-emerald-500/30', 'text-emerald-200');
        if (isSuccess) {
            alertBox.classList.add('bg-emerald-950/70', 'border-emerald-500/30', 'text-emerald-200');
            if (alertIcon) alertIcon.innerHTML = `<svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>`;
        } else {
            alertBox.classList.add('bg-rose-950/70', 'border-rose-500/30', 'text-rose-200');
            if (alertIcon) alertIcon.innerHTML = `<svg class="w-5 h-5 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`;
        }
        if (alertText) alertText.textContent = msg;
    }

    function hideAlert() {
        if (alertBox) alertBox.classList.add('hidden');
    }

    // Submit PIN Form via AJAX
    if (formLogin) {
        formLogin.addEventListener('submit', async (e) => {
            e.preventDefault();
            hideAlert();
            const submitBtn = document.getElementById('btn-submit-login');
            const origHTML = submitBtn ? submitBtn.innerHTML : '';
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = `
                    <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Verifying...
                `;
            }

            const pinVal = pinInput ? pinInput.value.trim() : '';
            const rememberVal = document.getElementById('login-remember') ? document.getElementById('login-remember').checked : false;

            try {
                const res = await fetch('/api/site/verify-pin', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pin: pinVal, remember: rememberVal })
                });
                const data = await res.json();

                if (data.success) {
                    showAlert('PIN verified! Access granted.', true);
                    if (typeof showToast === 'function') {
                        showToast('Access granted!', 'success');
                    }
                    setTimeout(() => {
                        window.location.href = '/';
                    }, 300);
                } else {
                    showAlert(data.message || 'Incorrect Security PIN. Please try again.');
                    if (pinInput) {
                        pinInput.value = '';
                        pinInput.focus();
                    }
                }
            } catch (err) {
                formLogin.submit();
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = origHTML;
                }
            }
        });
    }
});
