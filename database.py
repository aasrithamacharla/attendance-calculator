import sqlite3
import os
import json
import datetime
from contextlib import contextmanager

# IN-MEMORY DATABASE: Temporary runtime cache only.
# Firebase Realtime Database is the ONLY database and single source of truth.
_ROOT_CONN = sqlite3.connect('file:auth_memory_db?mode=memory&cache=shared', uri=True, check_same_thread=False)
_ROOT_CONN.row_factory = sqlite3.Row

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
    """No-op: Local JSON backup is removed. Firebase is the ONLY database."""
    pass

def init_db():
    """Initializes runtime schema only. Never auto-seeds or restores fake data."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                salary REAL DEFAULT 0.0,
                emp_type TEXT DEFAULT 'Full Day',
                narration TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT DEFAULT 'Worker',
                salary REAL DEFAULT 0.0,
                narration TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

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

# Initialize schema upon module import
init_db()

def clear_all_local_data():
    """Clears all local tables so they strictly mirror Firebase."""
    with get_db() as conn:
        conn.execute("DELETE FROM employees")
        conn.execute("DELETE FROM workers")
        conn.execute("DELETE FROM attendance_records")
        conn.execute("DELETE FROM payroll_payments")
        conn.commit()

if __name__ == '__main__':
    with get_db() as c:
        ec = c.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
        wc = c.execute("SELECT COUNT(*) FROM workers").fetchone()[0]
        print(f"Database schema initialized. Employee count: {ec}, Worker count: {wc}.")
