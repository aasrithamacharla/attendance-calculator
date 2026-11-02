import unittest
import json
import datetime
import os

from app import app
from database import init_db, get_db

class TestAttendanceApp(unittest.TestCase):
    def setUp(self):
        init_db()
        app.config['TESTING'] = True
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess['site_unlocked'] = True

    def test_site_pin_gate_access(self):
        """Website requires PIN 5473 to access; once unlocked, renders dashboard; can lock again."""
        fresh_client = app.test_client()
        # 1. Accessing without PIN shows PIN gate with PIN hidden
        res = fresh_client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'4-Digit Access PIN', res.data)
        self.assertNotIn(b'5473', res.data, "Security PIN must be hidden from lock screen!")
        self.assertNotIn(b'Attendance Dashboard', res.data)

        # 2. Submitting incorrect PIN fails
        res_bad = fresh_client.post('/api/site/verify-pin', json={'pin': '0000'})
        self.assertEqual(res_bad.status_code, 401)
        self.assertFalse(res_bad.get_json()['success'])

        # 3. Submitting correct PIN 5473 succeeds
        res_ok = fresh_client.post('/api/site/verify-pin', json={'pin': '5473'})
        self.assertEqual(res_ok.status_code, 200)
        self.assertTrue(res_ok.get_json()['success'])

        # 4. Now accessing '/' renders dashboard
        res_dash = fresh_client.get('/')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'AJ Attendance Dashboard', res_dash.data)
        self.assertIn(b'Workers', res_dash.data)

        # 5. Lock website
        res_lock = fresh_client.get('/lock', follow_redirects=True)
        self.assertEqual(res_lock.status_code, 200)
        self.assertIn(b'4-Digit Access PIN', res_lock.data)

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
        # Use a fixed weekday (Wednesday) to avoid Sunday attendance blocking
        today = "2026-10-14"

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

    def test_direct_database_consistency(self):
        """Database operations seamlessly write to SQLite and return exact records."""
        # 1. Add employee
        res = self.client.post('/api/employees', json={'name': 'Direct DB Test', 'emp_type': 'Full Day'})
        self.assertEqual(res.status_code, 200)
        emp_id = res.get_json()['employee']['id']

        # 2. Check in database
        with get_db() as conn:
            row = conn.execute("SELECT name FROM employees WHERE id = ?", (emp_id,)).fetchone()
            self.assertEqual(row['name'], 'Direct DB Test')

        # 3. Mark attendance
        res_att = self.client.post('/api/attendance', json={
            'employee_id': emp_id,
            'date': '2026-10-28',
            'status': 'Full Day'
        })
        self.assertEqual(res_att.status_code, 200)

        # 4. Check attendance in database
        with get_db() as conn:
            att = conn.execute("SELECT status FROM attendance_records WHERE employee_id = ? AND date = ?", (emp_id, '2026-10-28')).fetchone()
            self.assertEqual(att['status'], 'Full Day')

    def test_init_db_no_fake_seeding(self):
        """Calling init_db initializes the database without seeding fake dummy employees."""
        init_db()
        with get_db() as conn:
            fake_emp = conn.execute("SELECT * FROM employees WHERE name IN ('Sarah Miller', 'James Wilson', 'Elena Rostova')").fetchone()
            self.assertIsNone(fake_emp)
            fake_wrk = conn.execute("SELECT * FROM workers WHERE name IN ('Robert Taylor', 'Maya Patel')").fetchone()
            self.assertIsNone(fake_wrk)

    def test_firebase_endpoints(self):
        """Firebase configuration and export endpoints return correct database URL."""
        res_cfg = self.client.get('/api/firebase/config')
        self.assertEqual(res_cfg.status_code, 200)
        self.assertIn('attendance-90920-default-rtdb', res_cfg.get_json()['config']['databaseURL'])

        res_exp = self.client.get('/api/firebase/export')
        self.assertEqual(res_exp.status_code, 200)
        exp_data = res_exp.get_json()
        self.assertTrue(exp_data['success'])
        self.assertIn('employees', exp_data['data'])
        self.assertIn('workers', exp_data['data'])

    def test_no_auth_db_file_created(self):
        """Verifies that no auth.db file exists or is created on disk."""
        workspace_dir = os.path.dirname(os.path.abspath(__file__))
        auth_db_path = os.path.join(workspace_dir, 'auth.db')
        self.assertFalse(os.path.exists(auth_db_path), "auth.db file must not exist on disk!")

    def test_salary_isolation_and_no_auto_salary(self):
        """Verify salary is strictly recorded without auto-defaults and editing one field does not alter another."""
        # 1. Add employee without salary -> salary is strictly 0.0 (no auto 30000 or 1000)
        res1 = self.client.post('/api/employees', json={'name': 'Dev NoSalary', 'emp_type': 'Full Day'})
        emp1_id = res1.get_json()['employee']['id']
        with get_db() as conn:
            row1 = conn.execute("SELECT salary FROM employees WHERE id = ?", (emp1_id,)).fetchone()
            self.assertEqual(row1['salary'], 0.0)

        # 2. Add employee with specific salary (45500.0)
        res2 = self.client.post('/api/employees', json={'name': 'Kavya Rao', 'salary': 45500.0, 'emp_type': 'Full Day', 'narration': 'Lead'})
        emp2_id = res2.get_json()['employee']['id']
        with get_db() as conn:
            row2 = conn.execute("SELECT salary, narration FROM employees WHERE id = ?", (emp2_id,)).fetchone()
            self.assertEqual(row2['salary'], 45500.0)
            self.assertEqual(row2['narration'], 'Lead')

        # 3. Edit name and narration only -> salary must strictly remain 45500.0
        self.client.post('/api/admin/login', json={'password': 'attendance'})
        upd = self.client.post('/api/admin/employees/update', json={
            'employee_id': emp2_id,
            'name': 'Kavya Rao Updated',
            'emp_type': 'Full Day',
            'narration': 'Senior Lead'
        })
        self.assertTrue(upd.get_json()['success'])
        with get_db() as conn:
            row_upd = conn.execute("SELECT name, salary, narration FROM employees WHERE id = ?", (emp2_id,)).fetchone()
            self.assertEqual(row_upd['name'], 'Kavya Rao Updated')
            self.assertEqual(row_upd['salary'], 45500.0, "Salary must not be altered when updating employee name/narration!")
            self.assertEqual(row_upd['narration'], 'Senior Lead')

        # 4. Edit salary directly via /api/admin/salary -> name, type, and narration must remain unchanged
        sal_upd = self.client.post('/api/admin/salary', json={
            'employee_id': emp2_id,
            'salary': 52000.0
        })
        self.assertTrue(sal_upd.get_json()['success'])
        with get_db() as conn:
            row_sal = conn.execute("SELECT name, salary, narration, emp_type FROM employees WHERE id = ?", (emp2_id,)).fetchone()
            self.assertEqual(row_sal['salary'], 52000.0)
            self.assertEqual(row_sal['name'], 'Kavya Rao Updated', "Name must not be altered when updating salary!")
            self.assertEqual(row_sal['narration'], 'Senior Lead', "Narration must not be altered when updating salary!")

        # 5. Add worker without salary -> salary is strictly 0.0 (no auto 20000 or 25000)
        res_w = self.client.post('/api/workers', json={'name': 'Worker NoSalary', 'role': 'Maintenance'})
        w_id = res_w.get_json()['worker']['id']
        with get_db() as conn:
            w_row = conn.execute("SELECT salary FROM workers WHERE id = ?", (w_id,)).fetchone()
            self.assertEqual(w_row['salary'], 0.0, "Worker salary must default to 0.0, not an automatic amount!")

        # 6. Update worker details without salary -> salary remains preserved
        with get_db() as conn:
            conn.execute("UPDATE workers SET salary = 18500.0 WHERE id = ?", (w_id,))
            conn.commit()
        upd_w = self.client.post('/api/admin/workers/update', json={
            'worker_id': w_id,
            'name': 'Worker Renamed',
            'role': 'Supervisor'
        })
        self.assertTrue(upd_w.get_json()['success'])
        with get_db() as conn:
            w_upd = conn.execute("SELECT name, salary, role FROM workers WHERE id = ?", (w_id,)).fetchone()
            self.assertEqual(w_upd['name'], 'Worker Renamed')
            self.assertEqual(w_upd['salary'], 18500.0, "Worker salary must not be altered when updating name/role!")

    def test_admin_login_password_only_and_pin_rejected(self):
        """Verify Admin Portal ONLY allows password attendance and rejects PIN."""
        # 1. Login with password 'attendance' succeeds
        res_pw = self.client.post('/api/admin/login', json={'password': 'attendance'})
        self.assertEqual(res_pw.status_code, 200)
        self.assertTrue(res_pw.get_json()['success'])

        # 2. Login with PIN 5473 is rejected for admin portal (PIN is website-only)
        res_pin = self.client.post('/api/admin/login', json={'pin': '5473'})
        self.assertEqual(res_pin.status_code, 401)
        self.assertFalse(res_pin.get_json()['success'])

        # 3. Login with password '5473' is rejected for admin portal
        res_pin_pw = self.client.post('/api/admin/login', json={'password': '5473'})
        self.assertEqual(res_pin_pw.status_code, 401)
        self.assertFalse(res_pin_pw.get_json()['success'])

        # 4. Incorrect password rejected
        res_bad_pw = self.client.post('/api/admin/login', json={'password': 'wrongpassword'})
        self.assertEqual(res_bad_pw.status_code, 401)
        self.assertFalse(res_bad_pw.get_json()['success'])

if __name__ == '__main__':
    unittest.main()
