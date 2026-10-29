function openProfileModal() {
    const modal = document.getElementById('modal-profile');
    if (modal) modal.classList.remove('hidden');
}

function closeProfileModal() {
    const modal = document.getElementById('modal-profile');
    if (modal) modal.classList.add('hidden');
}

function openPasswordModal() {
    const modal = document.getElementById('modal-password');
    if (modal) modal.classList.remove('hidden');
}

function closePasswordModal() {
    const modal = document.getElementById('modal-password');
    if (modal) modal.classList.add('hidden');
}

function openEmployeeModal() {
    const modal = document.getElementById('modal-employee');
    if (modal) modal.classList.remove('hidden');
    const input = document.getElementById('input-emp-name');
    if (input) input.focus();
}

function closeEmployeeModal() {
    const modal = document.getElementById('modal-employee');
    if (modal) modal.classList.add('hidden');
}

function updateEmployeeCounters(count) {
    const badge = document.getElementById('badge-employee-count');
    const stat = document.getElementById('stat-employee-count');
    if (badge) badge.textContent = `${count} Active`;
    if (stat) stat.textContent = `${count}`;
}

async function deleteEmployee(empId, empName) {
    if (!confirm(`Are you sure you want to remove ${empName} from the employee registry?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/employees/${empId}`, {
            method: 'DELETE'
        });
        const data = await res.json();
        if (data.success) {
            showToast(data.message, 'info');
            const row = document.getElementById(`emp-row-${empId}`);
            if (row) row.remove();

            const tbody = document.getElementById('employees-table-body');
            const remaining = tbody ? tbody.querySelectorAll('tr[id^="emp-row-"]').length : 0;
            updateEmployeeCounters(remaining);

            if (remaining === 0 && tbody) {
                tbody.innerHTML = `
                    <tr id="no-employees-row">
                        <td colspan="6" class="py-6 text-center text-slate-500">No employees recorded yet. Click "Employee" to record your first employee.</td>
                    </tr>
                `;
            }
        } else {
            showToast(data.message || 'Failed to remove employee', 'error');
        }
    } catch (err) {
        showToast('Server error while removing employee', 'error');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Logout Handler
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/logout', {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                const data = await res.json();
                showToast('Signed out successfully', 'info');
                setTimeout(() => {
                    window.location.href = data.redirect || '/auth';
                }, 400);
            } catch (err) {
                window.location.href = '/auth';
            }
        });
    }

    // Record Employee Form Handler
    const empForm = document.getElementById('form-add-employee');
    if (empForm) {
        empForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('input-emp-name').value.trim();
            const dept = document.getElementById('input-emp-dept').value;
            const role = document.getElementById('input-emp-role').value.trim() || 'Staff';
            const status = document.getElementById('input-emp-status').value;

            if (!name) {
                showToast('Please enter an employee name', 'error');
                return;
            }

            const submitBtn = document.getElementById('btn-submit-emp');
            const originalText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = `<span>Recording...</span>`;

            try {
                const res = await fetch('/api/employees', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, department: dept, role, status })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message, 'success');
                    empForm.reset();
                    closeEmployeeModal();

                    // Remove placeholder empty row if present
                    const emptyRow = document.getElementById('no-employees-row');
                    if (emptyRow) emptyRow.remove();

                    // Prepend new employee to table
                    const tbody = document.getElementById('employees-table-body');
                    if (tbody) {
                        const emp = data.employee;
                        const statusBadge = emp.status === 'Present'
                            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                            : emp.status === 'Remote'
                            ? 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                            : 'bg-amber-500/10 text-amber-400 border-amber-500/30';

                        const today = new Date().toISOString().replace('T', ' ').substring(0, 19);

                        const tr = document.createElement('tr');
                        tr.id = `emp-row-${emp.id}`;
                        tr.className = 'hover:bg-slate-800/30 transition-colors animate-pulse';
                        tr.innerHTML = `
                            <td class="py-3 font-medium text-slate-100 flex items-center gap-2.5">
                                <div class="w-7 h-7 rounded-lg bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center text-xs font-bold text-white uppercase shadow-sm">
                                    ${emp.name.charAt(0)}
                                </div>
                                <span class="font-semibold text-slate-200">${emp.name}</span>
                            </td>
                            <td class="py-3 text-slate-300">${emp.department}</td>
                            <td class="py-3 text-slate-400">${emp.role}</td>
                            <td class="py-3">
                                <span class="px-2 py-0.5 rounded-full text-[10px] border ${statusBadge}">
                                    ${emp.status}
                                </span>
                            </td>
                            <td class="py-3 text-slate-400">${today}</td>
                            <td class="py-3 text-right">
                                <button type="button" onclick="deleteEmployee(${emp.id}, '${emp.name}')" class="text-rose-400 hover:text-rose-300 text-xs hover:underline">Remove</button>
                            </td>
                        `;
                        tbody.prepend(tr);
                        setTimeout(() => tr.classList.remove('animate-pulse'), 1000);

                        const total = tbody.querySelectorAll('tr[id^="emp-row-"]').length;
                        updateEmployeeCounters(total);
                    }
                } else {
                    showToast(data.message || 'Failed to record employee', 'error');
                }
            } catch (err) {
                showToast('Server error while recording employee', 'error');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        });
    }

    // Profile Update Handler
    const profileForm = document.getElementById('form-update-profile');
    if (profileForm) {
        profileForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const newName = document.getElementById('input-update-name').value.trim();
            if (!newName) return;

            try {
                const res = await fetch('/api/profile/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ full_name: newName })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message, 'success');
                    const navUser = document.getElementById('nav-user-name');
                    const headerUser = document.getElementById('header-user-name');
                    const profileVal = document.getElementById('profile-name-val');
                    if (navUser) navUser.textContent = newName;
                    if (headerUser) headerUser.textContent = newName;
                    if (profileVal) profileVal.textContent = newName;
                    closeProfileModal();
                } else {
                    showToast(data.message || 'Update failed', 'error');
                }
            } catch (err) {
                showToast('Server error while updating profile', 'error');
            }
        });
    }

    // Password Change Handler
    const passForm = document.getElementById('form-change-password');
    if (passForm) {
        passForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const curr = document.getElementById('input-current-pass').value;
            const newPass = document.getElementById('input-new-pass').value;

            if (newPass.length < 6) {
                showToast('New password must be at least 6 characters', 'error');
                return;
            }

            try {
                const res = await fetch('/api/profile/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        current_password: curr,
                        new_password: newPass
                    })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message, 'success');
                    passForm.reset();
                    closePasswordModal();
                } else {
                    showToast(data.message || 'Failed to update password', 'error');
                }
            } catch (err) {
                showToast('Server error while changing password', 'error');
            }
        });
    }

    // Close modals on clicking outside backdrop
    window.addEventListener('click', (e) => {
        const modalProf = document.getElementById('modal-profile');
        const modalPass = document.getElementById('modal-password');
        const modalEmp = document.getElementById('modal-employee');
        if (e.target === modalProf) closeProfileModal();
        if (e.target === modalPass) closePasswordModal();
        if (e.target === modalEmp) closeEmployeeModal();
    });
});
