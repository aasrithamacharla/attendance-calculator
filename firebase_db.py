import os
import json
import urllib.request
import urllib.error
import datetime
import threading

FIREBASE_DATABASE_URL = os.environ.get(
    'FIREBASE_DATABASE_URL', 
    'https://attendance-90920-default-rtdb.asia-southeast1.firebasedatabase.app'
).rstrip('/')

FIREBASE_AUTH_SECRET = os.environ.get('FIREBASE_AUTH_SECRET', '')
_last_error = None

def get_last_error():
    global _last_error
    return _last_error

def set_auth_secret(secret):
    global FIREBASE_AUTH_SECRET
    FIREBASE_AUTH_SECRET = (secret or '').strip()

def _build_url(path):
    clean_path = path.strip('/')
    url = f"{FIREBASE_DATABASE_URL}/{clean_path}.json" if clean_path else f"{FIREBASE_DATABASE_URL}/.json"
    if FIREBASE_AUTH_SECRET:
        url += f"?auth={FIREBASE_AUTH_SECRET}"
    return url

def _firebase_request(path, method='GET', data=None, timeout=4):
    """
    Executes an HTTP request to the Firebase Realtime Database REST API.
    Returns parsed JSON on success, or dict with 'error' on error.
    """
    global _last_error
    if os.environ.get('SKIP_FIREBASE_NETWORK') == '1':
        return {'status': 'mocked_in_test'}
    url = _build_url(path)
    try:
        req = urllib.request.Request(url, method=method)
        req.add_header('Content-Type', 'application/json')
        req.add_header('User-Agent', 'AttendanceApp/1.0')
        
        encoded_data = None
        if data is not None:
            encoded_data = json.dumps(data).encode('utf-8')
            
        with urllib.request.urlopen(req, data=encoded_data, timeout=timeout) as response:
            resp_body = response.read().decode('utf-8')
            _last_error = None
            return json.loads(resp_body) if resp_body else {'success': True}
    except urllib.error.HTTPError as e:
        body = ''
        try:
            body = e.read().decode('utf-8')
        except Exception:
            pass
        _last_error = f"HTTP {e.code}: {body or e.reason}"
        return {'error': _last_error, 'http_code': e.code}
    except Exception as e:
        _last_error = f"{type(e).__name__}: {str(e)}"
        return {'error': _last_error}

def run_async(func, *args, **kwargs):
    """Executes a function in a detached daemon background thread to keep Flask endpoints instantaneous."""
    thread = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread

def check_connection():
    """
    Checks if Firebase Realtime Database is accessible and writable.
    """
    res = _firebase_request('status/ping', method='PUT', data={
        'last_ping': datetime.datetime.now().isoformat(),
        'source': 'Attendance Portal Backend'
    }, timeout=3)
    return res is not None and not (isinstance(res, dict) and 'error' in res)

def sync_employee_to_firebase(emp_id, emp_data):
    """
    Updates an employee's profile in Firebase Realtime Database without overwriting other fields:
    /employees/emp_{emp_id}/profile
    """
    return _firebase_request(f"employees/emp_{emp_id}/profile", method='PATCH', data=emp_data)

def delete_employee_from_firebase(emp_id):
    """
    Deletes an employee and ALL of their nested subdata:
    /employees/emp_{emp_id}
    """
    return _firebase_request(f"employees/emp_{emp_id}", method='DELETE')

def sync_worker_to_firebase(worker_id, worker_data):
    """
    Updates a worker's profile in Firebase Realtime Database without overwriting other fields:
    /workers/worker_{worker_id}/profile
    """
    return _firebase_request(f"workers/worker_{worker_id}/profile", method='PATCH', data=worker_data)

def delete_worker_from_firebase(worker_id):
    """
    Deletes a worker and all nested subdata:
    /workers/worker_{worker_id}
    """
    return _firebase_request(f"workers/worker_{worker_id}", method='DELETE')

def sync_attendance_to_firebase(emp_id, date_str, status, notes='', slots=''):
    """
    Uploads daily attendance directly into the employee's attendance subdata:
    /employees/emp_{emp_id}/attendance/{date_str}
    """
    slots_list = [s.strip() for s in slots.split(',') if s.strip()] if isinstance(slots, str) else (slots or [])
    data = {
        'date': date_str,
        'status': status,
        'notes': notes or '',
        'slots': slots_list,
        'updated_at': datetime.datetime.now().isoformat()
    }
    return _firebase_request(f"employees/emp_{emp_id}/attendance/{date_str}", method='PUT', data=data)

def delete_attendance_from_firebase(emp_id, date_str):
    """
    Removes a single day's attendance record from the employee's attendance subdata:
    /employees/emp_{emp_id}/attendance/{date_str}
    """
    return _firebase_request(f"employees/emp_{emp_id}/attendance/{date_str}", method='DELETE')

def sync_payment_status_to_firebase(recipient_type, target_id, month, is_paid, notes=''):
    """
    Uploads salary payment status into the recipient's payroll subdata:
    /employees/emp_{target_id}/payroll/{month} OR /workers/worker_{target_id}/payroll/{month}
    """
    data = {
        'month': month,
        'is_paid': bool(is_paid),
        'notes': notes or '',
        'updated_at': datetime.datetime.now().isoformat()
    }
    if recipient_type == 'employee':
        return _firebase_request(f"employees/emp_{target_id}/payroll/{month}", method='PUT', data=data)
    else:
        return _firebase_request(f"workers/worker_{target_id}/payroll/{month}", method='PUT', data=data)

def export_full_database(get_db_func):
    """
    Exports a highly organized hierarchical Firebase structure where all data
    (profile, attendance by date, payroll by month) is nested directly inside each employee's subdata.
    """
    payload = {
        'employees': {},
        'workers': {},
        'metadata': {
            'organization_version': '2.0_hierarchical',
            'exported_at': datetime.datetime.now().isoformat(),
            'database_structure': 'employees/emp_{id}/[profile, attendance, payroll]'
        }
    }
    with get_db_func() as conn:
        # 1. Employees & initialize their subdata containers
        emp_rows = conn.execute("SELECT id, name, salary, emp_type, narration, created_at FROM employees ORDER BY id ASC").fetchall()
        for r in emp_rows:
            d = dict(r)
            key = f"emp_{d['id']}"
            payload['employees'][key] = {
                'profile': {
                    'id': d['id'],
                    'name': d['name'],
                    'salary': float(d['salary'] or 0.0),
                    'emp_type': d['emp_type'] or 'Full Day',
                    'narration': d['narration'] or '',
                    'created_at': d.get('created_at') or ''
                },
                'attendance': {},
                'payroll': {}
            }

        # 2. Workers & initialize their subdata containers
        worker_rows = conn.execute("SELECT id, name, role, salary, narration, created_at FROM workers ORDER BY id ASC").fetchall()
        for r in worker_rows:
            d = dict(r)
            key = f"worker_{d['id']}"
            payload['workers'][key] = {
                'profile': {
                    'id': d['id'],
                    'name': d['name'],
                    'role': d['role'] or 'Worker',
                    'salary': float(d['salary'] or 0.0),
                    'narration': d['narration'] or '',
                    'created_at': d.get('created_at') or ''
                },
                'payroll': {}
            }

        # 3. Attendance records -> nested into each employee's 'attendance' subdata
        att_rows = conn.execute("SELECT employee_id, date, status, notes, slots, updated_at FROM attendance_records ORDER BY date ASC, employee_id ASC").fetchall()
        total_att_count = 0
        for r in att_rows:
            d = dict(r)
            emp_key = f"emp_{d['employee_id']}"
            if emp_key not in payload['employees']:
                payload['employees'][emp_key] = {
                    'profile': {'id': d['employee_id'], 'name': f'Employee #{d["employee_id"]}'},
                    'attendance': {},
                    'payroll': {}
                }
            
            slots_raw = d.get('slots') or ''
            slots_list = [s.strip() for s in slots_raw.split(',') if s.strip()] if isinstance(slots_raw, str) else (slots_raw or [])

            payload['employees'][emp_key]['attendance'][d['date']] = {
                'date': d['date'],
                'status': d['status'],
                'notes': d.get('notes') or '',
                'slots': slots_list,
                'updated_at': d.get('updated_at') or datetime.datetime.now().isoformat()
            }
            total_att_count += 1

        # 4. Payroll Payments -> nested into employee's or worker's 'payroll' subdata
        pay_rows = conn.execute("SELECT recipient_type, target_id, month, is_paid, paid_at FROM payroll_payments").fetchall()
        total_pay_count = 0
        for r in pay_rows:
            d = dict(r)
            rec_type = d['recipient_type']
            month = d['month']
            target_id = d['target_id']
            pay_data = {
                'month': month,
                'is_paid': bool(d['is_paid']),
                'paid_at': d.get('paid_at') or ''
            }
            if rec_type == 'employee':
                emp_key = f"emp_{target_id}"
                if emp_key in payload['employees']:
                    payload['employees'][emp_key]['payroll'][month] = pay_data
                    total_pay_count += 1
            elif rec_type == 'worker':
                w_key = f"worker_{target_id}"
                if w_key in payload['workers']:
                    payload['workers'][w_key]['payroll'][month] = pay_data
                    total_pay_count += 1

    payload['metadata']['counts'] = {
        'employees': len(payload['employees']),
        'workers': len(payload['workers']),
        'attendance': total_att_count,
        'payments': total_pay_count
    }
    return payload

def sync_all_sqlite_to_firebase(get_db_func):
    """
    Uploads all data from local SQLite database to Firebase Realtime Database in a single atomic PATCH request.
    """
    payload = export_full_database(get_db_func)
    counts = payload['metadata']['counts']
    report = {
        'employees': counts['employees'],
        'workers': counts['workers'],
        'attendance': counts['attendance'],
        'payments': counts['payments'],
        'success': False,
        'error': None
    }
    res = _firebase_request('', method='PATCH', data=payload, timeout=8)
    if res and not (isinstance(res, dict) and 'error' in res):
        report['success'] = True
    else:
        err_msg = res.get('error') if isinstance(res, dict) else _last_error
        report['error'] = err_msg or 'Connection failed or permission denied'
    return report

def get_firebase_config():
    """
    Returns the Firebase database configuration dictionary for frontend/API use.
    """
    return {
        'databaseURL': FIREBASE_DATABASE_URL,
        'hasAuthSecret': bool(FIREBASE_AUTH_SECRET)
    }

# Asynchronous non-blocking wrappers:
def async_sync_employee(emp_id, emp_data):
    return run_async(sync_employee_to_firebase, emp_id, emp_data)

def async_delete_employee(emp_id):
    return run_async(delete_employee_from_firebase, emp_id)

def async_sync_worker(worker_id, worker_data):
    return run_async(sync_worker_to_firebase, worker_id, worker_data)

def async_delete_worker(worker_id):
    return run_async(delete_worker_from_firebase, worker_id)

def async_sync_attendance(emp_id, date_str, status, notes='', slots=''):
    return run_async(sync_attendance_to_firebase, emp_id, date_str, status, notes, slots)

def async_delete_attendance(emp_id, date_str):
    return run_async(delete_attendance_from_firebase, emp_id, date_str)

def async_sync_payment_status(recipient_type, target_id, month, is_paid, notes=''):
    return run_async(sync_payment_status_to_firebase, recipient_type, target_id, month, is_paid, notes)

def async_sync_all_sqlite(get_db_func):
    return run_async(sync_all_sqlite_to_firebase, get_db_func)
