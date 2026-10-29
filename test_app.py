import unittest
import json
import datetime
from app import app
from database import init_db, get_db

class TestAttendanceApp(unittest.TestCase):
    def setUp(self):
        init_db()
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_direct_dashboard_access(self):
        """Dashboard must be accessible directly without login."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Attendance Dashboard', res.data)
        self.assertIn(b'Add Employee', res.data)
        self.assertIn(b'Workers', res.data)
        self.assertIn(b'Month Calendar', res.data)

    def test_add_employee_with_types(self):
        """Add employee supports Full Day, Half Day, Part Time with optional narration."""
        res = self.client.post('/api/employees', json={
            'name': 'Pooja Sharma',
            'emp_type': 'Half Day',
            'narration': 'Morning half-day coordinator'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['employee']['name'], 'Pooja Sharma')
        self.assertEqual(data['employee']['emp_type'], 'Half Day')
        self.assertEqual(data['employee']['narration'], 'Morning half-day coordinator')

    def test_edit_employee_name_and_narration(self):
        """Admin can edit employee name, type, and narration."""
        c = self.client.post('/api/employees', json={'name': 'Old Name', 'emp_type': 'Full Day'})
        emp_id = c.get_json()['employee']['id']

        self.client.post('/api/admin/login', json={'password': 'attendance'})

        upd = self.client.post('/api/admin/employees/update', json={
            'employee_id': emp_id,
            'name': 'Updated New Name',
            'emp_type': 'Part Time',
            'narration': 'Consultant description and terms'
        })
        self.assertEqual(upd.status_code, 200)
        self.assertTrue(upd.get_json()['success'])

        with get_db() as conn:
            row = conn.execute("SELECT name, emp_type, narration FROM employees WHERE id = ?", (emp_id,)).fetchone()
            self.assertEqual(row['name'], 'Updated New Name')
            self.assertEqual(row['emp_type'], 'Part Time')
            self.assertEqual(row['narration'], 'Consultant description and terms')

    def test_attendance_deselect(self):
        """Option to deselect attendance option back to unmarked."""
        c = self.client.post('/api/employees', json={'name': 'Deselect User'})
        emp_id = c.get_json()['employee']['id']
        today = datetime.date.today().strftime('%Y-%m-%d')

        # Mark Full Day
        res1 = self.client.post('/api/attendance', json={
            'employee_id': emp_id,
            'date': today,
            'status': 'Full Day'
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.get_json()['status'], 'Full Day')

        # Deselect attendance (using action: 'deselect')
        res2 = self.client.post('/api/attendance', json={
            'employee_id': emp_id,
            'date': today,
            'action': 'deselect'
        })
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()['status'], '')

        # Verify DB record is removed or status is empty
        with get_db() as conn:
            rec = conn.execute("SELECT status FROM attendance_records WHERE employee_id = ? AND date = ?", (emp_id, today)).fetchone()
            self.assertIsNone(rec)

    def test_daily_narration_dropdown_arrow(self):
        """Save daily note/narration via dropdown arrow API and verify separate admin log."""
        c = self.client.post('/api/employees', json={'name': 'Note Employee'})
        emp_id = c.get_json()['employee']['id']
        test_date = "2026-10-15"

        res = self.client.post('/api/attendance/note', json={
            'employee_id': emp_id,
            'date': test_date,
            'notes': 'Attended external site client inspection'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        # Verify in admin portal view
        self.client.post('/api/admin/login', json={'password': 'attendance'})
        admin_res = self.client.get('/admin?month=2026-10')
        self.assertEqual(admin_res.status_code, 200)
        self.assertIn(b'Attended external site client inspection', admin_res.data)

    def test_payment_status_toggle(self):
        """Payment status can be ticked and persisted for both employees and workers."""
        e = self.client.post('/api/employees', json={'name': 'Pay Employee'}).get_json()['employee']
        w = self.client.post('/api/workers', json={'name': 'Pay Worker', 'salary': 18000}).get_json()['worker']

        self.client.post('/api/admin/login', json={'password': 'attendance'})
        month = "2026-10"

        # Tick employee as paid
        res_e = self.client.post('/api/admin/payments/toggle', json={
            'recipient_type': 'employee',
            'target_id': e['id'],
            'month': month,
            'is_paid': True
        })
        self.assertEqual(res_e.status_code, 200)
        self.assertTrue(res_e.get_json()['is_paid'])

        # Tick worker as paid
        res_w = self.client.post('/api/admin/payments/toggle', json={
            'recipient_type': 'worker',
            'target_id': w['id'],
            'month': month,
            'is_paid': True
        })
        self.assertEqual(res_w.status_code, 200)
        self.assertTrue(res_w.get_json()['is_paid'])

        # Check DB
        with get_db() as conn:
            p_e = conn.execute("SELECT is_paid FROM payroll_payments WHERE recipient_type='employee' AND target_id=? AND month=?", (e['id'], month)).fetchone()
            p_w = conn.execute("SELECT is_paid FROM payroll_payments WHERE recipient_type='worker' AND target_id=? AND month=?", (w['id'], month)).fetchone()
            self.assertEqual(p_e['is_paid'], 1)
            self.assertEqual(p_w['is_paid'], 1)

    def test_worker_edit_and_narration(self):
        """Workers can have narration and details updated via admin portal."""
        w = self.client.post('/api/workers', json={
            'name': 'Gopal Maintenance',
            'role': 'Electrician',
            'salary': 22000,
            'narration': 'Initial description'
        }).get_json()['worker']

        self.client.post('/api/admin/login', json={'password': 'attendance'})

        res = self.client.post('/api/admin/workers/update', json={
            'worker_id': w['id'],
            'name': 'Gopal Sharma',
            'role': 'Senior Electrician',
            'salary': 25000,
            'narration': 'Contract renewed with emergency on-call allowance'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        with get_db() as conn:
            row = conn.execute("SELECT name, role, salary, narration FROM workers WHERE id = ?", (w['id'],)).fetchone()
            self.assertEqual(row['name'], 'Gopal Sharma')
            self.assertEqual(row['role'], 'Senior Electrician')
            self.assertEqual(row['salary'], 25000.0)
            self.assertEqual(row['narration'], 'Contract renewed with emergency on-call allowance')

    def test_half_day_employee_double_pay_for_full_day(self):
        """
        Rule: If saved as half day employee:
        - Leave is only considered for total leaves (half day is not 0.5 leave).
        - If marked as full day, double the day salary!
        """
        with get_db() as conn:
            # Base salary: 30,000 / month => Daily rate = 1,000 / day
            # Marked: 2 Full Days (doubled => +2,000 bonus)
            # Marked: 1 Leave => Total leaves = 1 (half days not leaves)
            # Unused free leaves: 2 - 1 = 1 free leave => +1,000 bonus
            # Expected Final Salary = 30,000 + 1,000 (free leave) + 2,000 (2 full days double bonus) = 33,000
            cursor = conn.execute(
                "INSERT INTO employees (name, salary, emp_type, narration) VALUES ('Half Day Doubled Worker', 30000.0, 'Half Day', 'Works mornings')"
            )
            emp_id = cursor.lastrowid
            m = "2026-11"
            # 2026-11-01 is Sunday, so use non-Sunday working days 02 (Mon), 03 (Tue), 04 (Wed)
            conn.execute("INSERT INTO attendance_records (employee_id, date, status) VALUES (?, ?, 'Full Day')", (emp_id, f"{m}-02"))
            conn.execute("INSERT INTO attendance_records (employee_id, date, status) VALUES (?, ?, 'Full Day')", (emp_id, f"{m}-03"))
            conn.execute("INSERT INTO attendance_records (employee_id, date, status) VALUES (?, ?, 'Leave')", (emp_id, f"{m}-04"))
            conn.commit()

        self.client.post('/api/admin/login', json={'password': 'attendance'})

        # Pass force=1 to calculate provisional or complete
        res = self.client.get(f'/admin?month={m}&force=1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Half Day Doubled Worker', res.data)
        # Expected final salary = 33,000.00
        self.assertIn(b'33,000.00', res.data)

    def test_part_time_employee_shifts_and_slots(self):
        """
        Rule: For part-time employees:
        - Half day is considered as 1 day.
        - Full day options: Morning, Afternoon, Evening.
          - 1 slot (Morning OR Afternoon OR Evening) = 1 day.
          - 2 slots (any two) = 2 days.
          - 3 slots (Morning AND Afternoon AND Evening) = 3 days.
        - Salary = calculated_days * per_day_wage.
        """
        with get_db() as conn:
            # Per day wage = 1,000
            cursor = conn.execute(
                "INSERT INTO employees (name, salary, emp_type, narration) VALUES ('Part Time Shift Worker', 1000.0, 'Part Time', 'Shift consultant')"
            )
            emp_id = cursor.lastrowid
            m = "2026-09"

            # Day 1: Half Day => 1 day
            conn.execute("INSERT INTO attendance_records (employee_id, date, status) VALUES (?, ?, 'Half Day')", (emp_id, f"{m}-01"))

            # Day 2: Full Day with 1 slot (Morning) => 1 day
            conn.execute("INSERT INTO attendance_records (employee_id, date, status, slots) VALUES (?, ?, 'Full Day', 'Morning')", (emp_id, f"{m}-02"))

            # Day 3: Full Day with 2 slots (Morning, Evening) => 2 days
            conn.execute("INSERT INTO attendance_records (employee_id, date, status, slots) VALUES (?, ?, 'Full Day', 'Morning,Evening')", (emp_id, f"{m}-03"))

            # Day 4: Full Day with 3 slots (Morning, Afternoon, Evening) => 3 days
            conn.execute("INSERT INTO attendance_records (employee_id, date, status, slots) VALUES (?, ?, 'Full Day', 'Morning,Afternoon,Evening')", (emp_id, f"{m}-04"))

            conn.commit()

        # Total calculated days = 1 + 1 + 2 + 3 = 7 days
        # Total salary = 7 days * 1,000 = 7,000
        self.client.post('/api/admin/login', json={'password': 'attendance'})

        res = self.client.get(f'/admin?month={m}&force=1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Part Time Shift Worker', res.data)
        self.assertIn(b'7,000.00', res.data)

    def test_bulk_delete_employees(self):
        """Admin can bulk delete employees via checkboxes."""
        e1 = self.client.post('/api/employees', json={'name': 'Bulk 1'}).get_json()['employee']['id']
        e2 = self.client.post('/api/employees', json={'name': 'Bulk 2'}).get_json()['employee']['id']

        self.client.post('/api/admin/login', json={'password': 'attendance'})

        res = self.client.post('/api/admin/employees/bulk-delete', json={'employee_ids': [e1, e2]})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        with get_db() as conn:
            count = conn.execute("SELECT COUNT(*) as c FROM employees WHERE id IN (?, ?)", (e1, e2)).fetchone()['c']
            self.assertEqual(count, 0)

    def test_month_completion_condition(self):
        """Total salary shows Pending Attendance until whole month attendance is logged, or when force=1."""
        with get_db() as conn:
            cursor = conn.execute("INSERT INTO employees (name, salary, emp_type) VALUES ('Complete Check Emp', 30000.0, 'Full Day')")
            emp_id = cursor.lastrowid
            m = "2026-04" # April 2026 has 30 days and 4 Sundays => 26 working days
            # Only mark 2 days (Wednesday & Thursday)
            conn.execute("INSERT INTO attendance_records (employee_id, date, status) VALUES (?, ?, 'Full Day')", (emp_id, f"{m}-01"))
            conn.execute("INSERT INTO attendance_records (employee_id, date, status) VALUES (?, ?, 'Full Day')", (emp_id, f"{m}-02"))
            conn.commit()

        self.client.post('/api/admin/login', json={'password': 'attendance'})

        # Without force=1: Incomplete month shows Pending Attendance
        res_incomplete = self.client.get(f'/admin?month={m}')
        self.assertEqual(res_incomplete.status_code, 200)
        self.assertIn(b'Pending Attendance', res_incomplete.data)
        self.assertIn(b'2/26 working days marked', res_incomplete.data)

        # With force=1: Finalized salary is unlocked for preview
        res_forced = self.client.get(f'/admin?month={m}&force=1')
        self.assertEqual(res_forced.status_code, 200)
        self.assertIn(b'Month Logged (2/26 working days)', res_forced.data)

    def test_sundays_remain_unselected_and_excluded_from_counts_and_salary(self):
        """
        Rule: Sundays remain unselected. Sundays are not considered for any kind of salary calculation.
        Even in counting present and leave days also count should not include Sundays.
        """
        c = self.client.post('/api/employees', json={'name': 'Sunday Test Emp', 'salary': 30000.0, 'emp_type': 'Full Day'})
        emp_id = c.get_json()['employee']['id']

        # 2026-10-25 is a Sunday
        sunday_date = "2026-10-25"

        # 1. Attempting to mark attendance on Sunday is rejected
        res_mark = self.client.post('/api/attendance', json={
            'employee_id': emp_id,
            'date': sunday_date,
            'status': 'Full Day'
        })
        self.assertEqual(res_mark.status_code, 400)
        self.assertIn('Sundays remain unselected', res_mark.get_json()['message'])

        # 2. Daily attendance GET on Sunday returns is_sunday=True and zero counts
        res_get = self.client.get(f'/api/attendance?date={sunday_date}')
        self.assertEqual(res_get.status_code, 200)
        get_data = res_get.get_json()
        self.assertTrue(get_data['is_sunday'])
        self.assertEqual(get_data['counts']['full_count'], 0)
        self.assertEqual(get_data['counts']['leave_count'], 0)

        # 3. Ensure any record on a Sunday is completely excluded from present & leave counts and salary calculations
        with get_db() as conn:
            # Force an insert on Sunday (2026-10-25) as Leave, and weekday (2026-10-26 Monday) as Full Day
            conn.execute("INSERT INTO attendance_records (employee_id, date, status) VALUES (?, ?, 'Leave')", (emp_id, sunday_date))
            conn.execute("INSERT INTO attendance_records (employee_id, date, status) VALUES (?, ?, 'Full Day')", (emp_id, "2026-10-26"))
            conn.commit()

        # Monthly calendar check: Sunday is NOT counted in leaves count
        res_cal = self.client.get(f'/api/employees/{emp_id}/calendar?month=2026-10')
        self.assertEqual(res_cal.status_code, 200)
        cal_data = res_cal.get_json()
        self.assertEqual(cal_data['counts']['leaves'], 0) # Sunday leave is NOT counted!
        self.assertEqual(cal_data['counts']['full_days'], 1) # Monday full day is counted

        # Admin portal check: Sunday is excluded from leaves count and salary deduction
        self.client.post('/api/admin/login', json={'password': 'attendance'})
        admin_res = self.client.get('/admin?month=2026-10&force=1')
        self.assertEqual(admin_res.status_code, 200)
        # 0 leaves counted for this employee, so 2 free leaves unused => bonus = 2 * 1000 = 2000 => salary = 32,000
        # If Sunday was counted, it would be 1 leave (bonus = 1000 => 31,000)
        self.assertIn(b'32,000.00', admin_res.data)

    def test_part_time_mandatory_slot_on_full_day(self):
        """
        Rule: For part-time employees if opted full day they mandatorily need to select
        one option from morning, afternoon, evening.
        """
        c = self.client.post('/api/employees', json={'name': 'Mandatory Slot Worker', 'salary': 1500.0, 'emp_type': 'Part Time'})
        emp_id = c.get_json()['employee']['id']
        test_date = "2026-10-27" # Tuesday

        # 1. Full Day without any slots must be rejected
        res_fail = self.client.post('/api/attendance', json={
            'employee_id': emp_id,
            'date': test_date,
            'status': 'Full Day',
            'slots': []
        })
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn('mandatory', res_fail.get_json()['message'])

        # 2. Full Day with at least one slot succeeds
        res_success = self.client.post('/api/attendance', json={
            'employee_id': emp_id,
            'date': test_date,
            'status': 'Full Day',
            'slots': ['Morning']
        })
        self.assertEqual(res_success.status_code, 200)
        self.assertTrue(res_success.get_json()['success'])
        self.assertEqual(res_success.get_json()['slots'], ['Morning'])

    def test_firebase_integration_endpoints(self):
        """Firebase RTDB config, status and sync endpoints."""
        # 1. Config endpoint
        res_cfg = self.client.get('/api/firebase/config')
        self.assertEqual(res_cfg.status_code, 200)
        cfg_data = res_cfg.get_json()
        self.assertTrue(cfg_data['success'])
        self.assertIn('attendance-90920-default-rtdb.asia-southeast1.firebasedatabase.app', cfg_data['config']['databaseURL'])

        # 2. Status endpoint
        res_stat = self.client.get('/api/firebase/status')
        self.assertEqual(res_stat.status_code, 200)
        stat_data = res_stat.get_json()
        self.assertTrue(stat_data['success'])
        self.assertEqual(stat_data['databaseURL'], 'https://attendance-90920-default-rtdb.asia-southeast1.firebasedatabase.app')

        # 3. Sync endpoint
        res_sync = self.client.post('/api/firebase/sync')
        self.assertEqual(res_sync.status_code, 200)
        sync_data = res_sync.get_json()
        self.assertIn('databaseURL', sync_data)
        self.assertIn('report', sync_data)

        # 4. Export endpoint (Hierarchical subdata structure)
        res_exp = self.client.get('/api/firebase/export')
        self.assertEqual(res_exp.status_code, 200)
        exp_data = res_exp.get_json()
        self.assertTrue(exp_data['success'])
        self.assertIn('employees', exp_data['data'])
        self.assertIn('workers', exp_data['data'])
        if exp_data['data']['employees']:
            first_emp_key = next(iter(exp_data['data']['employees'].keys()))
            first_emp = exp_data['data']['employees'][first_emp_key]
            self.assertIn('profile', first_emp)
            self.assertIn('attendance', first_emp)
            self.assertIn('payroll', first_emp)

        # 5. Set Secret endpoint
        res_sec = self.client.post('/api/firebase/set-secret', json={'secret': 'test_secret_key'})
        self.assertEqual(res_sec.status_code, 200)
        self.assertTrue(res_sec.get_json()['hasAuthSecret'])

    def test_database_reset_and_no_fake_seeding(self):
        """Admin can reset database completely, and init_db does not auto-seed fake records."""
        import os, tempfile
        tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        tmp_db.close()
        old_path = os.environ.get('ATTENDANCE_DB_PATH')
        os.environ['ATTENDANCE_DB_PATH'] = tmp_db.name
        try:
            init_db()
            # Add an employee
            self.client.post('/api/employees', json={'name': 'Temp Worker', 'emp_type': 'Full Day'})
            
            # Login and reset
            self.client.post('/api/admin/login', json={'password': 'attendance'})
            res = self.client.post('/api/admin/reset-database')
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.get_json()['success'])

            with get_db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM workers").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM attendance_records").fetchone()[0], 0)

            # Calling init_db again must NOT auto-insert fake employees
            init_db()
            with get_db() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0], 0)
        finally:
            if old_path is not None:
                os.environ['ATTENDANCE_DB_PATH'] = old_path
            else:
                os.environ.pop('ATTENDANCE_DB_PATH', None)
            if os.path.exists(tmp_db.name):
                os.unlink(tmp_db.name)

if __name__ == '__main__':
    unittest.main()
