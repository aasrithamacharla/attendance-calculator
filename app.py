import os
import datetime
import calendar
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from database import get_db, init_db, persist_to_json
from firebase_db import (
    FIREBASE_DATABASE_URL,
    check_connection as check_firebase_connection,
    get_firebase_config,
    get_last_error,
    set_auth_secret,
    export_full_database,
    sync_all_sqlite_to_firebase,
    async_sync_employee,
    async_delete_employee,
    async_sync_worker,
    async_delete_worker,
    async_sync_attendance,
    async_delete_attendance,
    async_sync_payment_status,
    async_sync_all_sqlite
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.secret_key = os.environ.get('SECRET_KEY', 'attendance-portal-secret-key-2026-secure')

def to_dmy(val):
    """Convert YYYY-MM-DD or date object to DD/MM/YYYY."""
    if not val:
        return ""
    if isinstance(val, str):
        parts = val.strip().split('-')
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return val
    if hasattr(val, 'strftime'):
        return val.strftime('%d/%m/%Y')
    return str(val)

@app.template_filter('dmy')
def dmy_filter(val):
    return to_dmy(val)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': 'Admin login required. Password: attendance'}), 401
            return redirect(url_for('dashboard', admin_modal='1'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/favicon.ico')
def favicon():
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#6366f1"><path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5z"/></svg>', 200, {'Content-Type': 'image/svg+xml'})

def sync_from_firebase():
    """Syncs in-memory cache directly from Firebase Realtime Database. Firebase is the ONLY source of truth."""
    if os.environ.get('SKIP_FIREBASE_NETWORK') == '1':
        return
    try:
        from firebase_db import _firebase_request
        fb_data = _firebase_request('/', method='GET', timeout=3)
        if isinstance(fb_data, dict) and 'error' not in fb_data:
            with get_db() as conn:
                conn.execute("DELETE FROM employees")
                conn.execute("DELETE FROM workers")
                conn.execute("DELETE FROM attendance_records")
                conn.execute("DELETE FROM payroll_payments")

                employees_map = fb_data.get('employees') or {}
                if isinstance(employees_map, dict):
                    for ek, ev in employees_map.items():
                        if not isinstance(ev, dict): continue
                        p = ev.get('profile') or {}
                        try:
                            emp_id = int(p.get('id') or str(ek).replace('emp_', ''))
                        except Exception:
                            continue
                        p_sal = p.get('salary')
                        try:
                            sal_val = float(p_sal) if p_sal is not None and str(p_sal).strip() != '' else 0.0
                        except (ValueError, TypeError):
                            sal_val = 0.0
                        conn.execute(
                            "INSERT OR REPLACE INTO employees (id, name, salary, emp_type, narration, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (emp_id, p.get('name', f'Employee #{emp_id}'), sal_val, p.get('emp_type', 'Full Day'), p.get('narration', ''), p.get('created_at', ''))
                        )
                        for d_str, att in (ev.get('attendance') or {}).items():
                            if not isinstance(att, dict): continue
                            slots = att.get('slots', [])
                            slots_str = ','.join(slots) if isinstance(slots, list) else str(slots)
                            conn.execute(
                                "INSERT OR REPLACE INTO attendance_records (employee_id, date, status, notes, slots, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                                (emp_id, d_str, att.get('status', 'Full Day'), att.get('notes', ''), slots_str, att.get('updated_at', ''))
                            )
                        for m, pay in (ev.get('payroll') or {}).items():
                            if not isinstance(pay, dict): continue
                            conn.execute(
                                "INSERT OR REPLACE INTO payroll_payments (recipient_type, target_id, month, is_paid, paid_at) VALUES (?, ?, ?, ?, ?)",
                                ('employee', emp_id, m, 1 if pay.get('is_paid') else 0, pay.get('paid_at', ''))
                            )

                workers_map = fb_data.get('workers') or {}
                if isinstance(workers_map, dict):
                    for wk, wv in workers_map.items():
                        if not isinstance(wv, dict): continue
                        p = wv.get('profile') or {}
                        try:
                            w_id = int(p.get('id') or str(wk).replace('worker_', ''))
                        except Exception:
                            continue
                        w_sal = p.get('salary')
                        try:
                            wsal_val = float(w_sal) if w_sal is not None and str(w_sal).strip() != '' else 0.0
                        except (ValueError, TypeError):
                            wsal_val = 0.0
                        conn.execute(
                            "INSERT OR REPLACE INTO workers (id, name, role, salary, narration, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (w_id, p.get('name', f'Worker #{w_id}'), p.get('role', 'Worker'), wsal_val, p.get('narration', ''), p.get('created_at', ''))
                        )
                        for m, pay in (wv.get('payroll') or {}).items():
                            if not isinstance(pay, dict): continue
                            conn.execute(
                                "INSERT OR REPLACE INTO payroll_payments (recipient_type, target_id, month, is_paid, paid_at) VALUES (?, ?, ?, ?, ?)",
                                ('worker', w_id, m, 1 if pay.get('is_paid') else 0, pay.get('paid_at', ''))
                            )
                conn.commit()
    except Exception:
        pass

# 1. Main Dashboard: Direct Access
@app.route('/')
def dashboard():
    sync_from_firebase()
    selected_date = (request.args.get('date') or datetime.date.today().strftime('%Y-%m-%d')).strip()
    
    with get_db() as conn:
        emps = conn.execute("SELECT id, name, emp_type, narration FROM employees ORDER BY id ASC").fetchall()
        employees = [dict(e) for e in emps]
        
        workers = conn.execute("SELECT id, name, role, salary, narration, created_at FROM workers ORDER BY id ASC").fetchall()
        workers_list = [dict(w) for w in workers]

        # Check if selected date is a Sunday
        try:
            parsed_date = datetime.date.fromisoformat(selected_date)
            is_sunday = (parsed_date.weekday() == 6)
        except ValueError:
            is_sunday = False

        # Get attendance records for selected date
        att_rows = conn.execute(
            "SELECT employee_id, status, notes, slots FROM attendance_records WHERE date = ?",
            (selected_date,)
        ).fetchall()
        att_map = {r['employee_id']: dict(r) for r in att_rows}
        
        for emp in employees:
            if is_sunday:
                # Sundays remain unselected
                emp['attendance_status'] = ''
                emp['day_notes'] = ''
                emp['day_slots'] = []
            else:
                record = att_map.get(emp['id'])
                if record:
                    emp['attendance_status'] = record['status']
                    emp['day_notes'] = record['notes'] or ''
                    emp['day_slots'] = (record['slots'] or '').split(',') if record['slots'] else []
                else:
                    emp['attendance_status'] = ''
                    emp['day_notes'] = ''
                    emp['day_slots'] = []
            
        full_count = 0 if is_sunday else sum(1 for e in employees if e['attendance_status'] == 'Full Day')
        half_count = 0 if is_sunday else sum(1 for e in employees if e['attendance_status'] == 'Half Day')
        leave_count = 0 if is_sunday else sum(1 for e in employees if e['attendance_status'] == 'Leave')
        unmarked_count = len(employees) if is_sunday else max(0, len(employees) - (full_count + half_count + leave_count))

    return render_template(
        'dashboard.html',
        employees=employees,
        workers=workers_list,
        selected_date=selected_date,
        is_sunday=is_sunday,
        full_count=full_count,
        half_count=half_count,
        leave_count=leave_count,
        unmarked_count=unmarked_count,
        total_employees=len(employees),
        total_workers=len(workers_list),
        is_admin=session.get('is_admin', False),
        show_admin_modal=request.args.get('admin_modal') == '1',
        firebase_database_url=FIREBASE_DATABASE_URL
    )

@app.route('/auth')
@app.route('/login')
def legacy_auth_redirect():
    return redirect(url_for('dashboard'))

# 2. Record or Deselect daily attendance for an employee
@app.route('/api/attendance', methods=['POST'])
@app.route('/api/attendance/mark', methods=['POST'])
def save_attendance():
    data = request.get_json() or request.form
    emp_id = data.get('employee_id')
    date_str = (data.get('date') or datetime.date.today().strftime('%Y-%m-%d')).strip()
    status = (data.get('status') or '').strip()
    action = (data.get('action') or '').strip()
    slots = data.get('slots') # list or comma string
    notes = data.get('notes')

    if isinstance(slots, list):
        slots_str = ','.join(s.strip() for s in slots if s.strip())
    elif isinstance(slots, str):
        slots_str = slots.strip()
    else:
        slots_str = ''
    
    if not emp_id or not date_str:
        return jsonify({'success': False, 'message': 'Employee ID and date are required.'}), 400

    # Sunday check: "Sundays remain unselected Sundays are not considered for any kind of salary calculation."
    try:
        parsed_date = datetime.date.fromisoformat(date_str)
        is_sunday = (parsed_date.weekday() == 6)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format (expected YYYY-MM-DD).'}), 400

    if is_sunday:
        if action == 'deselect' or status == 'deselect':
            with get_db() as conn:
                conn.execute("DELETE FROM attendance_records WHERE employee_id = ? AND date = ?", (emp_id, date_str))
                conn.commit()
            return jsonify({'success': True, 'message': 'Cleared attendance for Sunday.', 'status': '', 'is_sunday': True})
        return jsonify({
            'success': False,
            'message': 'Sundays remain unselected (Weekly Off). Sundays are not considered for salary calculation or attendance counts.',
            'is_sunday': True
        }), 400

    with get_db() as conn:
        emp = conn.execute("SELECT name, emp_type FROM employees WHERE id = ?", (emp_id,)).fetchone()
        if not emp:
            return jsonify({'success': False, 'message': 'Employee not found.'}), 404

        # Part-time mandatory slot rule: "For part-time employees if opted full day they mandatorily need to select one option from morning, afternoon , evening"
        if emp['emp_type'] == 'Part Time' and status == 'Full Day' and action != 'deselect':
            valid_slots = [s for s in ['Morning', 'Afternoon', 'Evening'] if s in [x.strip() for x in slots_str.split(',') if x.strip()]]
            if not valid_slots:
                return jsonify({
                    'success': False,
                    'message': 'For part-time employees opting Full Day, selecting at least one option (Morning, Afternoon, or Evening) is mandatory.'
                }), 400
            slots_str = ','.join(valid_slots)

        existing = conn.execute(
            "SELECT status, notes, slots FROM attendance_records WHERE employee_id = ? AND date = ?",
            (emp_id, date_str)
        ).fetchone()

        # Check for deselect option (if action == 'deselect' or empty status or clicking same status)
        if action == 'deselect' or status == 'deselect' or (existing and status and existing['status'] == status and not slots_str):
            conn.execute("DELETE FROM attendance_records WHERE employee_id = ? AND date = ?", (emp_id, date_str))
            conn.commit()
            persist_to_json()
            new_status = ''
            message = f"Cleared attendance for {emp['name']}"
            async_delete_attendance(emp_id, date_str)
        else:
            if status not in ['Full Day', 'Half Day', 'Leave']:
                return jsonify({'success': False, 'message': 'Status must be Full Day, Half Day, or Leave.'}), 400

            # Preserve existing notes if not provided
            notes_val = notes if notes is not None else (existing['notes'] if existing else '')
            # Preserve existing slots if not provided
            slots_val = slots_str if slots_str or status != 'Full Day' else (existing['slots'] if existing else '')

            conn.execute('''
                INSERT INTO attendance_records (employee_id, date, status, notes, slots, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(employee_id, date) DO UPDATE SET
                    status = excluded.status,
                    notes = CASE WHEN ? != '' THEN excluded.notes ELSE attendance_records.notes END,
                    slots = excluded.slots,
                    updated_at = CURRENT_TIMESTAMP
            ''', (emp_id, date_str, status, notes_val, slots_val, notes_val))
            conn.commit()
            persist_to_json()
            new_status = status
            message = f"Marked {status} for {emp['name']}"
            async_sync_attendance(emp_id, date_str, status, notes_val, slots_val)

        att_rows = conn.execute("SELECT status FROM attendance_records WHERE date = ?", (date_str,)).fetchall()
        full_count = sum(1 for r in att_rows if r['status'] == 'Full Day')
        half_count = sum(1 for r in att_rows if r['status'] == 'Half Day')
        leave_count = sum(1 for r in att_rows if r['status'] == 'Leave')

    return jsonify({
        'success': True,
        'message': message,
        'employee_id': emp_id,
        'date': date_str,
        'status': new_status,
        'slots': slots_str.split(',') if slots_str else [],
        'counts': {
            'full_count': full_count,
            'half_count': half_count,
            'leave_count': leave_count
        }
    })

# 3. Save daily note/narration via dropdown arrow
@app.route('/api/attendance/note', methods=['POST'])
def save_attendance_note():
    data = request.get_json() or request.form
    emp_id = data.get('employee_id')
    date_str = (data.get('date') or datetime.date.today().strftime('%Y-%m-%d')).strip()
    notes = (data.get('notes') or '').strip()

    if not emp_id or not date_str:
        return jsonify({'success': False, 'message': 'Employee ID and date are required.'}), 400

    with get_db() as conn:
        emp = conn.execute("SELECT name FROM employees WHERE id = ?", (emp_id,)).fetchone()
        if not emp:
            return jsonify({'success': False, 'message': 'Employee not found.'}), 404

        existing = conn.execute(
            "SELECT status FROM attendance_records WHERE employee_id = ? AND date = ?",
            (emp_id, date_str)
        ).fetchone()

        status_val = existing['status'] if existing else 'Full Day'

        conn.execute('''
            INSERT INTO attendance_records (employee_id, date, status, notes, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(employee_id, date) DO UPDATE SET
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
        ''', (emp_id, date_str, status_val, notes))
        conn.commit()
        persist_to_json()
        async_sync_attendance(emp_id, date_str, status_val, notes, '')

    return jsonify({
        'success': True,
        'message': f"Narration saved for {emp['name']}",
        'employee_id': emp_id,
        'date': date_str,
        'notes': notes
    })

# 4. Get daily attendance for dynamic date picking
@app.route('/api/attendance', methods=['GET'])
def get_daily_attendance():
    date_str = (request.args.get('date') or datetime.date.today().strftime('%Y-%m-%d')).strip()
    try:
        parsed_date = datetime.date.fromisoformat(date_str)
        is_sunday = (parsed_date.weekday() == 6)
    except ValueError:
        is_sunday = False

    with get_db() as conn:
        emps = conn.execute("SELECT id, name, emp_type FROM employees ORDER BY id ASC").fetchall()
        
        if is_sunday:
            # Sundays remain unselected and are not counted in present or leaves
            records = [{
                'id': e['id'],
                'name': e['name'],
                'emp_type': e['emp_type'],
                'status': '',
                'notes': '',
                'slots': []
            } for e in emps]
            return jsonify({
                'success': True,
                'date': date_str,
                'is_sunday': True,
                'employees': records,
                'counts': {
                    'full_count': 0,
                    'half_count': 0,
                    'leave_count': 0,
                    'unmarked_count': len(emps),
                    'total': len(emps)
                }
            })

        att_rows = conn.execute("SELECT employee_id, status, notes, slots FROM attendance_records WHERE date = ?", (date_str,)).fetchall()
        att_map = {r['employee_id']: dict(r) for r in att_rows}
        
    records = []
    for e in emps:
        rec = att_map.get(e['id'])
        records.append({
            'id': e['id'],
            'name': e['name'],
            'emp_type': e['emp_type'],
            'status': rec['status'] if rec else '',
            'notes': rec['notes'] if rec else '',
            'slots': (rec['slots'] or '').split(',') if rec and rec['slots'] else []
        })
        
    full_count = sum(1 for s in records if s['status'] == 'Full Day')
    half_count = sum(1 for s in records if s['status'] == 'Half Day')
    leave_count = sum(1 for s in records if s['status'] == 'Leave')

    return jsonify({
        'success': True,
        'date': date_str,
        'is_sunday': False,
        'employees': records,
        'counts': {
            'full_count': full_count,
            'half_count': half_count,
            'leave_count': leave_count,
            'unmarked_count': max(0, len(emps) - (full_count + half_count + leave_count)),
            'total': len(emps)
        }
    })

# 5. Get monthly calendar attendance for an employee
@app.route('/api/employees/<int:emp_id>/calendar', methods=['GET'])
def get_employee_monthly_calendar(emp_id):
    month_str = (request.args.get('month') or datetime.date.today().strftime('%Y-%m')).strip()
    try:
        year, month = map(int, month_str.split('-'))
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid month format (expected YYYY-MM)'}), 400

    num_days = calendar.monthrange(year, month)[1]
    first_weekday = calendar.monthrange(year, month)[0] # 0 = Monday

    with get_db() as conn:
        emp = conn.execute("SELECT id, name, emp_type FROM employees WHERE id = ?", (emp_id,)).fetchone()
        if not emp:
            return jsonify({'success': False, 'message': 'Employee not found'}), 404
            
        att_rows = conn.execute(
            "SELECT date, status, notes, slots FROM attendance_records WHERE employee_id = ? AND date LIKE ? ORDER BY date ASC",
            (emp_id, f"{month_str}%")
        ).fetchall()
        records_map = {r['date']: dict(r) for r in att_rows}

    days_data = []
    for d in range(1, num_days + 1):
        dt_obj = datetime.date(year, month, d)
        dt_str = f"{year:04d}-{month:02d}-{d:02d}"
        is_sun = (dt_obj.weekday() == 6)
        rec = records_map.get(dt_str)
        # Sundays remain unselected:
        status_val = '' if is_sun else (rec['status'] if rec else '')
        days_data.append({
            'day': d,
            'date': dt_str,
            'is_sunday': is_sun,
            'status': status_val,
            'notes': '' if is_sun else (rec['notes'] if rec else ''),
            'slots': [] if is_sun else ((rec['slots'] or '').split(',') if rec and rec['slots'] else [])
        })

    # Sundays are excluded from present, half day and leave day counts
    non_sunday_rows = [
        r for r in att_rows 
        if datetime.date.fromisoformat(r['date']).weekday() != 6
    ]
    full_days = sum(1 for r in non_sunday_rows if r['status'] == 'Full Day')
    half_days = sum(1 for r in non_sunday_rows if r['status'] == 'Half Day')
    leaves = sum(1 for r in non_sunday_rows if r['status'] == 'Leave')

    emp_type = emp['emp_type'] or 'Full Day'
    if emp_type == 'Half Day':
        total_leaves = float(leaves)
    else:
        total_leaves = leaves + (half_days * 0.5)

    return jsonify({
        'success': True,
        'employee': dict(emp),
        'month': month_str,
        'year': year,
        'month_num': month,
        'first_weekday': first_weekday,
        'num_days': num_days,
        'days': days_data,
        'counts': {
            'full_days': full_days,
            'half_days': half_days,
            'leaves': leaves,
            'total_leaves': total_leaves
        }
    })

# 6. Add new employee (option for Full Day, Half Day, Part Time)
@app.route('/api/employees', methods=['POST'])
def add_employee():
    data = request.get_json() or request.form
    name = (data.get('name') or '').strip()
    emp_type = (data.get('emp_type') or 'Full Day').strip()
    narration = (data.get('narration') or '').strip()
    
    if emp_type not in ['Full Day', 'Half Day', 'Part Time']:
        emp_type = 'Full Day'

    salary = data.get('salary')
    try:
        salary = float(salary) if salary is not None and str(salary).strip() != '' else 0.0
    except (ValueError, TypeError):
        salary = 0.0
        
    if not name:
        return jsonify({'success': False, 'message': 'Employee name is required.'}), 400
        
    date_str = (data.get('date') or '').strip()

    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO employees (name, salary, emp_type, narration) VALUES (?, ?, ?, ?)",
            (name, salary, emp_type, narration)
        )
        emp_id = cursor.lastrowid

        # If a date was provided from the dashboard, also record attendance for today (unless Sunday)
        if date_str:
            try:
                parsed_d = datetime.date.fromisoformat(date_str)
                is_sun = (parsed_d.weekday() == 6)
            except ValueError:
                is_sun = False

            if not is_sun:
                initial_status = 'Full Day' if emp_type in ['Full Day', 'Part Time'] else ('Half Day' if emp_type == 'Half Day' else '')
                initial_slots = 'Morning' if emp_type == 'Part Time' else ''
                if initial_status:
                    conn.execute(
                        "INSERT INTO attendance_records (employee_id, date, status, notes, slots) VALUES (?, ?, ?, '', ?)",
                        (emp_id, date_str, initial_status, initial_slots)
                    )
                    async_sync_attendance(emp_id, date_str, initial_status, '', initial_slots)
        conn.commit()
        persist_to_json()
        async_sync_employee(emp_id, {
            'id': emp_id,
            'name': name,
            'salary': salary,
            'emp_type': emp_type,
            'narration': narration
        })

    return jsonify({
        'success': True,
        'message': f"Employee '{name}' ({emp_type}) added successfully!",
        'employee': {
            'id': emp_id,
            'name': name,
            'salary': salary,
            'emp_type': emp_type,
            'narration': narration
        }
    })

# 7. Update Employee Name, Type, Narration from Admin Portal
@app.route('/api/admin/employees/update', methods=['POST'])
@admin_required
def update_employee_details():
    data = request.get_json() or request.form
    emp_id = data.get('employee_id')
    name = (data.get('name') or '').strip()
    emp_type = (data.get('emp_type') or 'Full Day').strip()
    narration = (data.get('narration') or '').strip()

    if not emp_id or not name:
        return jsonify({'success': False, 'message': 'Employee ID and name are required.'}), 400
    if emp_type not in ['Full Day', 'Half Day', 'Part Time']:
        emp_type = 'Full Day'

    salary = data.get('salary')
    has_salary = salary is not None and str(salary).strip() != ''
    salary_val = 0.0
    if has_salary:
        try:
            salary_val = float(salary)
        except (ValueError, TypeError):
            has_salary = False

    with get_db() as conn:
        emp = conn.execute("SELECT id, salary FROM employees WHERE id = ?", (emp_id,)).fetchone()
        if not emp:
            return jsonify({'success': False, 'message': 'Employee not found.'}), 404

        if has_salary:
            final_salary = salary_val
            conn.execute(
                "UPDATE employees SET name = ?, salary = ?, emp_type = ?, narration = ? WHERE id = ?",
                (name, final_salary, emp_type, narration, emp_id)
            )
            sync_payload = {'id': emp_id, 'name': name, 'salary': final_salary, 'emp_type': emp_type, 'narration': narration}
        else:
            final_salary = float(emp['salary'] or 0.0)
            conn.execute(
                "UPDATE employees SET name = ?, emp_type = ?, narration = ? WHERE id = ?",
                (name, emp_type, narration, emp_id)
            )
            sync_payload = {'id': emp_id, 'name': name, 'emp_type': emp_type, 'narration': narration}

        conn.commit()
        persist_to_json()
        async_sync_employee(emp_id, sync_payload)

    return jsonify({
        'success': True,
        'message': f"Employee '{name}' details updated successfully!",
        'employee': {
            'id': emp_id,
            'name': name,
            'salary': final_salary,
            'emp_type': emp_type,
            'narration': narration
        }
    })

# 8. Delete Employee & Bulk Delete
@app.route('/api/employees/<int:emp_id>', methods=['DELETE'])
def delete_employee(emp_id):
    with get_db() as conn:
        emp = conn.execute("SELECT name FROM employees WHERE id = ?", (emp_id,)).fetchone()
        if not emp:
            return jsonify({'success': False, 'message': 'Employee not found.'}), 404
        name = emp['name']
        conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
        conn.commit()
        persist_to_json()
        async_delete_employee(emp_id)
    return jsonify({'success': True, 'message': f"Employee '{name}' removed successfully."})

@app.route('/api/admin/employees/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_employees():
    data = request.get_json() or {}
    emp_ids = data.get('employee_ids', [])
    if not emp_ids:
        return jsonify({'success': False, 'message': 'No employees selected.'}), 400

    with get_db() as conn:
        placeholders = ','.join('?' for _ in emp_ids)
        conn.execute(f"DELETE FROM employees WHERE id IN ({placeholders})", emp_ids)
        conn.commit()
        persist_to_json()
        for eid in emp_ids:
            async_delete_employee(eid)

    return jsonify({
        'success': True,
        'message': f"Successfully deleted {len(emp_ids)} employees."
    })

# 9. Workers Management (Fixed Salary, No Attendance Required)
@app.route('/api/workers', methods=['GET'])
def get_workers():
    with get_db() as conn:
        rows = conn.execute("SELECT id, name, role, salary, narration, created_at FROM workers ORDER BY id ASC").fetchall()
        workers = [dict(r) for r in rows]
    return jsonify({'success': True, 'workers': workers})

@app.route('/api/workers', methods=['POST'])
def add_worker():
    data = request.get_json() or request.form
    name = (data.get('name') or '').strip()
    role = (data.get('role') or 'Worker').strip()
    narration = (data.get('narration') or '').strip()
    salary = data.get('salary')
    try:
        salary = float(salary) if salary is not None and str(salary).strip() != '' else 0.0
    except (ValueError, TypeError):
        salary = 0.0

    if not name:
        return jsonify({'success': False, 'message': 'Worker name is required.'}), 400

    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO workers (name, role, salary, narration) VALUES (?, ?, ?, ?)",
            (name, role, salary, narration)
        )
        conn.commit()
        persist_to_json()
        worker_id = cursor.lastrowid
        async_sync_worker(worker_id, {
            'id': worker_id,
            'name': name,
            'role': role,
            'salary': salary,
            'narration': narration
        })

    return jsonify({
        'success': True,
        'message': f"Worker '{name}' added successfully (Fixed Salary, Attendance-Exempt).",
        'worker': {
            'id': worker_id,
            'name': name,
            'role': role,
            'salary': salary,
            'narration': narration
        }
    })

@app.route('/api/admin/workers/update', methods=['POST'])
@admin_required
def update_worker_details():
    data = request.get_json() or request.form
    worker_id = data.get('worker_id')
    name = (data.get('name') or '').strip()
    role = (data.get('role') or 'Worker').strip()
    narration = (data.get('narration') or '').strip()

    if not worker_id or not name:
        return jsonify({'success': False, 'message': 'Worker ID and name are required.'}), 400

    salary = data.get('salary')
    has_salary = salary is not None and str(salary).strip() != ''
    salary_val = 0.0
    if has_salary:
        try:
            salary_val = float(salary)
        except (ValueError, TypeError):
            has_salary = False

    with get_db() as conn:
        worker = conn.execute("SELECT id, salary FROM workers WHERE id = ?", (worker_id,)).fetchone()
        if not worker:
            return jsonify({'success': False, 'message': 'Worker not found.'}), 404

        if has_salary:
            final_salary = salary_val
            conn.execute('''
                UPDATE workers SET name = ?, role = ?, salary = ?, narration = ?
                WHERE id = ?
            ''', (name, role, final_salary, narration, worker_id))
            sync_payload = {'id': worker_id, 'name': name, 'role': role, 'salary': final_salary, 'narration': narration}
        else:
            final_salary = float(worker['salary'] or 0.0)
            conn.execute('''
                UPDATE workers SET name = ?, role = ?, narration = ?
                WHERE id = ?
            ''', (name, role, narration, worker_id))
            sync_payload = {'id': worker_id, 'name': name, 'role': role, 'narration': narration}

        conn.commit()
        persist_to_json()
        async_sync_worker(worker_id, sync_payload)

    return jsonify({
        'success': True,
        'message': f"Worker '{name}' updated successfully!",
        'worker': {
            'id': worker_id,
            'name': name,
            'role': role,
            'salary': final_salary,
            'narration': narration
        }
    })

@app.route('/api/workers/<int:worker_id>', methods=['DELETE'])
def delete_worker(worker_id):
    with get_db() as conn:
        worker = conn.execute("SELECT name FROM workers WHERE id = ?", (worker_id,)).fetchone()
        if not worker:
            return jsonify({'success': False, 'message': 'Worker not found.'}), 404
        name = worker['name']
        conn.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        conn.commit()
        persist_to_json()
        async_delete_worker(worker_id)
    return jsonify({'success': True, 'message': f"Worker '{name}' removed successfully."})

@app.route('/api/admin/workers/salary', methods=['POST'])
@admin_required
def update_worker_salary():
    data = request.get_json() or request.form
    worker_id = data.get('worker_id')
    try:
        new_salary = float(data.get('salary', 0))
        if new_salary < 0:
            return jsonify({'success': False, 'message': 'Salary cannot be negative.'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid salary amount.'}), 400

    with get_db() as conn:
        worker = conn.execute("SELECT name FROM workers WHERE id = ?", (worker_id,)).fetchone()
        if not worker:
            return jsonify({'success': False, 'message': 'Worker not found.'}), 404
        conn.execute("UPDATE workers SET salary = ? WHERE id = ?", (new_salary, worker_id))
        conn.commit()
        persist_to_json()
        async_sync_worker(worker_id, {'salary': new_salary})

    return jsonify({
        'success': True,
        'message': f"Fixed salary for worker '{worker['name']}' updated to ₹{new_salary:,.2f}",
        'worker_id': worker_id,
        'salary': new_salary
    })

# 10. Payment Status Toggle (Ticked/Unticked)
@app.route('/api/admin/payments/toggle', methods=['POST'])
@admin_required
def toggle_payment_status():
    data = request.get_json() or request.form
    recipient_type = data.get('recipient_type') # 'employee' or 'worker'
    target_id = data.get('target_id')
    month = (data.get('month') or datetime.date.today().strftime('%Y-%m')).strip()
    is_paid = bool(data.get('is_paid'))

    if not recipient_type or not target_id or not month:
        return jsonify({'success': False, 'message': 'Missing recipient type, target id, or month.'}), 400

    paid_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') if is_paid else None

    with get_db() as conn:
        conn.execute('''
            INSERT INTO payroll_payments (recipient_type, target_id, month, is_paid, paid_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(recipient_type, target_id, month) DO UPDATE SET
                is_paid = excluded.is_paid,
                paid_at = excluded.paid_at
        ''', (recipient_type, target_id, month, 1 if is_paid else 0, paid_at))
        conn.commit()
        persist_to_json()
        async_sync_payment_status(recipient_type, target_id, month, is_paid)

    return jsonify({
        'success': True,
        'message': f"Marked as {'Paid' if is_paid else 'Pending'}",
        'is_paid': is_paid,
        'paid_at': paid_at
    })

# 11. Admin Login & Logout (password: attendance)
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or request.form
    password = (data.get('password') or '').strip()
    
    if password.lower() == 'attendance':
        session['is_admin'] = True
        return jsonify({
            'success': True,
            'message': 'Admin login successful!',
            'redirect': url_for('admin_portal')
        })
    return jsonify({
        'success': False,
        'message': 'Invalid admin password. Please enter "attendance".'
    }), 401

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('dashboard'))

# 12. Admin Portal: Salary Calculation, Monthly Attendance Check, Category Rules
@app.route('/admin')
@admin_required
def admin_portal():
    sync_from_firebase()
    selected_month = (request.args.get('month') or datetime.date.today().strftime('%Y-%m')).strip()
    try:
        year, month_num = map(int, selected_month.split('-'))
        days_in_month = calendar.monthrange(year, month_num)[1]
    except ValueError:
        year = datetime.date.today().year
        month_num = datetime.date.today().month
        days_in_month = 30

    # Calculate total working days in month (excluding Sundays)
    working_days_in_month = sum(
        1 for d in range(1, days_in_month + 1)
        if datetime.date(year, month_num, d).weekday() != 6
    )

    force_calculate = request.args.get('force') == '1'

    with get_db() as conn:
        emps = conn.execute("SELECT id, name, salary, emp_type, narration FROM employees ORDER BY id ASC").fetchall()
        workers = conn.execute("SELECT id, name, role, salary, narration FROM workers ORDER BY id ASC").fetchall()
        
        # Fetch payment statuses for this month
        pay_rows = conn.execute(
            "SELECT recipient_type, target_id, is_paid, paid_at FROM payroll_payments WHERE month = ?",
            (selected_month,)
        ).fetchall()
        payments_map = {(r['recipient_type'], r['target_id']): bool(r['is_paid']) for r in pay_rows}

        # Fetch all attendance records for selected month
        att_rows = conn.execute(
            "SELECT employee_id, date, status, notes, slots FROM attendance_records WHERE date LIKE ? ORDER BY date ASC",
            (f"{selected_month}%",)
        ).fetchall()
        
        emp_records = {}
        daily_narrations_log = []
        for r in att_rows:
            emp_records.setdefault(r['employee_id'], []).append(dict(r))
            if r['notes']:
                try:
                    is_sun = (datetime.date.fromisoformat(r['date']).weekday() == 6)
                except ValueError:
                    is_sun = False
                if not is_sun:
                    e_name = next((e['name'] for e in emps if e['id'] == r['employee_id']), 'Employee')
                    daily_narrations_log.append({
                        'employee_id': r['employee_id'],
                        'employee_name': e_name,
                        'date': r['date'],
                        'status': r['status'],
                        'notes': r['notes'],
                        'slots': r['slots']
                    })
            
        payroll = []
        total_emp_base_payroll = 0.0
        total_emp_deductions = 0.0
        total_emp_bonuses = 0.0
        total_emp_net_payroll = 0.0
        total_leaves_month = 0.0
        
        for e in emps:
            all_records = emp_records.get(e['id'], [])

            # Sundays rule: "Sundays remain unselected Sundays are not considered for any kind of salary calculation. Even in counting present and leave days also count should not include Sundays ."
            valid_non_sunday_records = [
                r for r in all_records
                if datetime.date.fromisoformat(r['date']).weekday() != 6
            ]
            recorded_days_count = len(valid_non_sunday_records)
            is_month_complete = (recorded_days_count >= working_days_in_month) or force_calculate

            full_days = sum(1 for r in valid_non_sunday_records if r['status'] == 'Full Day')
            half_days = sum(1 for r in valid_non_sunday_records if r['status'] == 'Half Day')
            leaves = sum(1 for r in valid_non_sunday_records if r['status'] == 'Leave')
            
            emp_type = e['emp_type'] or 'Full Day'
            monthly_or_daily_salary = float(e['salary'] or 0.0)
            narration = e['narration'] or ''
            is_paid = payments_map.get(('employee', e['id']), False)

            if emp_type == 'Part Time':
                # Rule: For part-time employees consider half days as 1 day.
                # If opted full day give 3 options as morning, afternoon, evening.
                # 1 slot = 1 day, 2 slots = 2 days, 3 slots = 3 days.
                per_day_wage = monthly_or_daily_salary
                calculated_days = 0.0

                for r in valid_non_sunday_records:
                    if r['status'] == 'Half Day':
                        calculated_days += 1.0 # Half days count as 1 day
                    elif r['status'] == 'Full Day':
                        slots = [s.strip() for s in (r['slots'] or '').split(',') if s.strip()]
                        slot_count = len(slots)
                        if slot_count == 3:
                            calculated_days += 3.0 # all 3 = 3 days
                        elif slot_count == 2:
                            calculated_days += 2.0 # any two = 2 days
                        elif slot_count == 1:
                            calculated_days += 1.0 # any one = 1 day
                        else:
                            calculated_days += 1.0

                final_salary = round(per_day_wage * calculated_days, 2)
                daily_rate = per_day_wage
                deduction = 0.0
                bonus = 0.0
                total_leaves = float(leaves)
                considered_leaves = 0.0
                unused_free_leaves = 0.0
                base_display_salary = per_day_wage
                days_worked_display = calculated_days

            elif emp_type == 'Half Day':
                # Rule: "If saved as half day employee leave is only considered for total leaves, halfday is not considered as 0.5 day"
                # Rule: "While calculating half day employee if marked as full day double the day salary"
                total_leaves = float(leaves)
                total_leaves_month += total_leaves
                base_display_salary = monthly_or_daily_salary
                daily_rate = base_display_salary / 30.0

                # Double the day salary for each non-Sunday full day worked (+1 extra day salary added per full day)
                full_day_double_bonus = full_days * daily_rate

                if total_leaves > 2.0:
                    considered_leaves = total_leaves - 2.0
                    unused_free_leaves = 0.0
                    deduction = round(daily_rate * considered_leaves, 2)
                    bonus = round(full_day_double_bonus, 2)
                    final_salary = round(base_display_salary - deduction + bonus, 2)
                else:
                    considered_leaves = 0.0
                    unused_free_leaves = round(2.0 - total_leaves, 2)
                    deduction = 0.0
                    leave_bonus = daily_rate * unused_free_leaves
                    bonus = round(leave_bonus + full_day_double_bonus, 2)
                    final_salary = round(base_display_salary + bonus, 2)

                days_worked_display = full_days + half_days

            else: # 'Full Day'
                total_leaves = leaves + (half_days * 0.5)
                total_leaves_month += total_leaves
                base_display_salary = monthly_or_daily_salary
                daily_rate = base_display_salary / 30.0

                if total_leaves > 2.0:
                    considered_leaves = total_leaves - 2.0
                    unused_free_leaves = 0.0
                    deduction = round(daily_rate * considered_leaves, 2)
                    bonus = 0.0
                    final_salary = round(base_display_salary - deduction, 2)
                else:
                    considered_leaves = 0.0
                    unused_free_leaves = round(2.0 - total_leaves, 2)
                    deduction = 0.0
                    bonus = round(daily_rate * unused_free_leaves, 2)
                    final_salary = round(base_display_salary + bonus, 2)

                days_worked_display = full_days + (half_days * 0.5)

            total_emp_base_payroll += base_display_salary
            total_emp_deductions += deduction
            total_emp_bonuses += bonus
            total_emp_net_payroll += final_salary
            
            payroll.append({
                'id': e['id'],
                'name': e['name'],
                'emp_type': emp_type,
                'narration': narration,
                'salary': base_display_salary,
                'full_days': full_days,
                'half_days': half_days,
                'leaves': leaves,
                'total_leaves': total_leaves,
                'considered_leaves': considered_leaves,
                'unused_free_leaves': unused_free_leaves,
                'daily_rate': round(daily_rate, 2),
                'deduction': deduction,
                'bonus': bonus,
                'final_salary': final_salary,
                'is_paid': is_paid,
                'recorded_days_count': recorded_days_count,
                'working_days_in_month': working_days_in_month,
                'days_in_month': days_in_month,
                'is_month_complete': is_month_complete,
                'days_worked_display': days_worked_display,
                'records': valid_non_sunday_records
            })

        # Workers Payroll (Fixed Salary, No Attendance)
        workers_payroll = []
        total_workers_payroll = 0.0
        for w in workers:
            w_sal = float(w['salary'] or 0.0)
            total_workers_payroll += w_sal
            is_w_paid = payments_map.get(('worker', w['id']), False)
            workers_payroll.append({
                'id': w['id'],
                'name': w['name'],
                'role': w['role'],
                'narration': w['narration'] or '',
                'salary': w_sal,
                'final_payout': w_sal,
                'is_paid': is_w_paid
            })

    total_gross = total_emp_base_payroll + total_workers_payroll
    total_net = total_emp_net_payroll + total_workers_payroll

    return render_template(
        'admin.html',
        selected_month=selected_month,
        days_in_month=days_in_month,
        working_days_in_month=working_days_in_month,
        force_calculate=force_calculate,
        payroll=payroll,
        workers=workers_payroll,
        daily_narrations_log=daily_narrations_log,
        total_employees=len(emps),
        total_workers=len(workers),
        total_gross=round(total_gross, 2),
        total_emp_base_payroll=round(total_emp_base_payroll, 2),
        total_workers_payroll=round(total_workers_payroll, 2),
        total_deductions=round(total_emp_deductions, 2),
        total_bonuses=round(total_emp_bonuses, 2),
        total_net=round(total_net, 2),
        total_leaves_month=total_leaves_month,
        firebase_database_url=FIREBASE_DATABASE_URL
    )

# 13. Update Employee Monthly Salary from Admin Portal
@app.route('/api/admin/salary', methods=['POST'])
@admin_required
def update_salary():
    data = request.get_json() or request.form
    emp_id = data.get('employee_id')
    try:
        new_salary = float(data.get('salary', 0))
        if new_salary < 0:
            return jsonify({'success': False, 'message': 'Salary cannot be negative.'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid salary amount.'}), 400
        
    with get_db() as conn:
        emp = conn.execute("SELECT name FROM employees WHERE id = ?", (emp_id,)).fetchone()
        if not emp:
            return jsonify({'success': False, 'message': 'Employee not found.'}), 404
        conn.execute("UPDATE employees SET salary = ? WHERE id = ?", (new_salary, emp_id))
        conn.commit()
        async_sync_employee(emp_id, {'salary': new_salary})

    return jsonify({
        'success': True,
        'message': f"Salary for {emp['name']} updated to ₹{new_salary:,.2f}",
        'employee_id': emp_id,
        'salary': new_salary
    })

# 14. Firebase Realtime Database Integration APIs
@app.route('/api/firebase/config', methods=['GET'])
def get_firebase_settings():
    return jsonify({
        'success': True,
        'config': get_firebase_config()
    })

@app.route('/api/firebase/status', methods=['GET'])
def get_firebase_status():
    connected = check_firebase_connection()
    last_err = get_last_error()
    return jsonify({
        'success': True,
        'connected': connected,
        'last_error': last_err,
        'databaseURL': FIREBASE_DATABASE_URL
    })

@app.route('/api/firebase/export', methods=['GET'])
@app.route('/api/firebase/full-export', methods=['GET'])
def export_firebase_data():
    payload = export_full_database(get_db)
    return jsonify({
        'success': True,
        'data': payload,
        'databaseURL': FIREBASE_DATABASE_URL
    })

@app.route('/api/firebase/set-secret', methods=['POST'])
def save_firebase_secret():
    data = request.get_json() or request.form
    secret = (data.get('secret') or '').strip()
    set_auth_secret(secret)
    return jsonify({
        'success': True,
        'message': 'Firebase Auth Secret updated.',
        'hasAuthSecret': bool(secret)
    })

@app.route('/api/firebase/sync', methods=['POST'])
def sync_to_firebase():
    report = sync_all_sqlite_to_firebase(get_db)
    msg = f"Synced {report.get('employees', 0)} employees, {report.get('workers', 0)} workers, {report.get('attendance', 0)} attendance records, {report.get('payments', 0)} payments to Firebase Realtime Database." if report.get('success') else (report.get('error') or 'Sync failed')
    return jsonify({
        'success': report.get('success', False),
        'report': report,
        'error': report.get('error'),
        'message': msg
    })

if __name__ == '__main__':
    import sys
    init_db()
    port = int(os.environ.get('PORT', 8080))
    if '--port' in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index('--port') + 1])
        except (IndexError, ValueError):
            pass
    elif '-p' in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index('-p') + 1])
        except (IndexError, ValueError):
            pass

    host = '0.0.0.0'
    print(f"\n==================================================")
    print(f"🚀 Attendance Portal is running on port {port}")
    print(f"🔑 Admin Password: attendance")
    print(f"==================================================\n")
    app.run(host=host, port=port, debug=False)
