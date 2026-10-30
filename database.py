import sqlite3
import os
import json
import datetime
from contextlib import contextmanager

# IN-MEMORY DATABASE: Completely eliminates auth.db file on disk!
# Uses SQLite URI shared cache so all Flask threads and requests share the same in-memory store.
_ROOT_CONN = sqlite3.connect('file:auth_memory_db?mode=memory&cache=shared', uri=True, check_same_thread=False)
_ROOT_CONN.row_factory = sqlite3.Row

DATA_BACKUP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'firebase_initial_data.json')

def get_db_path():
    return ':memory:'

@contextmanager
def get_db():
    conn = sqlite3.connect('file:auth_memory_db?mode=memory&cache=shared', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()

def persist_to_json():
    """Silently saves the current database state to firebase_initial_data.json."""
    try:
        from firebase_db import export_full_database
        data = export_full_database(get_db)
        with open(DATA_BACKUP_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def init_db():
    """Initializes in-memory database schema and seeds from JSON backup if empty."""
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

        # Create payroll_payments table for payment status tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payroll_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                is_paid INTEGER DEFAULT 0,
                paid_at TIMESTAMP,
                notes TEXT DEFAULT '',
                UNIQUE(recipient_type, target_id, month)
            )
        ''')

        conn.commit()

        # Seed from firebase_initial_data.json if in-memory database is empty
        e_count = cursor.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        if e_count == 0 and os.path.exists(DATA_BACKUP_FILE):
            try:
                with open(DATA_BACKUP_FILE, 'r') as f:
                    fb_data = json.load(f)

                for ek, ev in fb_data.get('employees', {}).items():
                    p = ev.get('profile', {})
                    cursor.execute(
                        'INSERT OR REPLACE INTO employees (id, name, salary, emp_type, narration, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                        (p.get('id'), p.get('name'), p.get('salary', 30000.0), p.get('emp_type', 'Full Day'), p.get('narration', ''), p.get('created_at'))
                    )
                    for date_str, att in ev.get('attendance', {}).items():
                        slots = att.get('slots', [])
                        slots_str = ','.join(slots) if isinstance(slots, list) else str(slots)
                        cursor.execute(
                            'INSERT OR REPLACE INTO attendance_records (employee_id, date, status, notes, slots, updated_at) VALUES (?, ?, ?, ?, ?, ?)',
                            (p.get('id'), date_str, att.get('status', 'Full Day'), att.get('notes', ''), slots_str, att.get('updated_at'))
                        )
                    for m, pay in ev.get('payroll', {}).items():
                        cursor.execute(
                            'INSERT OR REPLACE INTO payroll_payments (recipient_type, target_id, month, is_paid, paid_at) VALUES (?, ?, ?, ?, ?)',
                            ('employee', p.get('id'), m, 1 if pay.get('is_paid') else 0, pay.get('paid_at', ''))
                        )

                for wk, wv in fb_data.get('workers', {}).items():
                    p = wv.get('profile', {})
                    cursor.execute(
                        'INSERT OR REPLACE INTO workers (id, name, role, salary, narration, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                        (p.get('id'), p.get('name'), p.get('role', 'Worker'), p.get('salary', 20000.0), p.get('narration', ''), p.get('created_at'))
                    )
                    for m, pay in wv.get('payroll', {}).items():
                        cursor.execute(
                            'INSERT OR REPLACE INTO payroll_payments (recipient_type, target_id, month, is_paid, paid_at) VALUES (?, ?, ?, ?, ?)',
                            ('worker', p.get('id'), m, 1 if pay.get('is_paid') else 0, pay.get('paid_at', ''))
                        )

                conn.commit()
            except Exception as e:
                print(f"Error seeding in-memory database: {e}")

        # Sundays remain unselected: purge any records on Sunday (strftime %w = 0)
        cursor.execute("DELETE FROM attendance_records WHERE strftime('%w', date) = '0'")
        conn.commit()

# Automatically initialize in-memory schema upon import
init_db()

if __name__ == '__main__':
    with get_db() as c:
        ec = c.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        wc = c.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
        print(f"In-memory database ready: {ec} employees, {wc} workers. Zero auth.db files on disk.")
