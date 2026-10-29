import sqlite3
import os
import datetime
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'auth.db')

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initializes database schema, salary columns, employee types, narration, workers table, and payment status."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create employees table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                salary REAL DEFAULT 30000.0,
                emp_type TEXT DEFAULT 'Full Day',
                narration TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Check and migrate columns in employees
        cursor.execute("PRAGMA table_info(employees)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'salary' not in columns:
            cursor.execute("ALTER TABLE employees ADD COLUMN salary REAL DEFAULT 30000.0")
        if 'emp_type' not in columns:
            cursor.execute("ALTER TABLE employees ADD COLUMN emp_type TEXT DEFAULT 'Full Day'")
        if 'narration' not in columns:
            cursor.execute("ALTER TABLE employees ADD COLUMN narration TEXT DEFAULT ''")

        # Create workers table (fixed salary, no attendance required)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT DEFAULT 'Worker',
                salary REAL DEFAULT 20000.0,
                narration TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Check and migrate columns in workers
        cursor.execute("PRAGMA table_info(workers)")
        w_columns = [row['name'] for row in cursor.fetchall()]
        if 'narration' not in w_columns:
            cursor.execute("ALTER TABLE workers ADD COLUMN narration TEXT DEFAULT ''")

        # Create attendance_records table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT DEFAULT '',
                slots TEXT DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE,
                UNIQUE(employee_id, date)
            )
        ''')

        # Check and migrate columns in attendance_records
        cursor.execute("PRAGMA table_info(attendance_records)")
        att_columns = [row['name'] for row in cursor.fetchall()]
        if 'notes' not in att_columns:
            cursor.execute("ALTER TABLE attendance_records ADD COLUMN notes TEXT DEFAULT ''")
        if 'slots' not in att_columns:
            cursor.execute("ALTER TABLE attendance_records ADD COLUMN slots TEXT DEFAULT ''")

        # Create payroll_payments table for payment status tracking (ticked/unticked)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payroll_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_type TEXT NOT NULL, -- 'employee' or 'worker'
                target_id INTEGER NOT NULL,
                month TEXT NOT NULL, -- 'YYYY-MM'
                is_paid INTEGER DEFAULT 0,
                paid_at TIMESTAMP,
                notes TEXT DEFAULT '',
                UNIQUE(recipient_type, target_id, month)
            )
        ''')

        # Check existing employees
        cursor.execute("SELECT COUNT(*) as count FROM employees")
        emp_count = cursor.fetchone()['count']
        if emp_count == 0:
            cursor.execute('''
                INSERT INTO employees (name, salary, emp_type, narration)
                VALUES 
                    ('Sarah Miller', 60000.0, 'Full Day', 'Senior full-stack engineer'),
                    ('James Wilson', 30000.0, 'Half Day', 'Works afternoon half-day shift (1pm - 5pm)'),
                    ('Elena Rostova', 1500.0, 'Part Time', 'Part-time operations specialist - paid per day wage')
            ''')

        # Check existing workers
        cursor.execute("SELECT COUNT(*) as count FROM workers")
        worker_count = cursor.fetchone()['count']
        if worker_count == 0:
            cursor.execute('''
                INSERT INTO workers (name, role, salary, narration)
                VALUES 
                    ('Robert Taylor', 'Maintenance & Facilities', 22000.0, 'Facilities maintenance and repairs'),
                    ('Maya Patel', 'Logistics Support', 25000.0, 'Warehouse logistics and supply')
            ''')

        # Normalize statuses
        cursor.execute("UPDATE attendance_records SET status = 'Full Day' WHERE status IN ('Present')")
        cursor.execute("UPDATE attendance_records SET status = 'Leave' WHERE status IN ('Absent', 'On Leave')")

        # Sundays remain unselected: purge any records on Sunday (strftime %w = 0)
        cursor.execute("DELETE FROM attendance_records WHERE strftime('%w', date) = '0'")

        conn.commit()

if __name__ == '__main__':
    init_db()
    print("Database updated and initialized successfully with payment status and attendance narration.")
