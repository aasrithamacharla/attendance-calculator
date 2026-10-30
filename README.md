# Employee Attendance & Payroll Portal

A full-stack web application featuring direct access to a daily attendance roster, monthly color-coded attendance calendar for every employee, fixed-salary worker management, payment tracking, and a protected Admin Portal with automated category-specific payroll calculations, shift slots, daily notes logs, and leave rules.

---

## 🌟 Key Features

### 1. Direct Dashboard (No Login Barrier)
- **Direct Access**: Navigating to `http://127.0.0.1:5001/` opens the clean, modern Dashboard directly without any authentication barrier.
- **Top Calendar Date Picker**:
  - Quickly select any day from the calendar input.
  - Navigate effortlessly with `‹ Previous Day`, `Today`, and `› Next Day`.
- **Add Employee with Categories**:
  - 🟢 **Full Day Employee**: Standard full-day shift with 2 free leaves/month.
  - 🟠 **Half Day Employee**: Half-day regular shift (half days are NOT counted as 0.5 leaves). Full day worked doubles day pay.
  - 🔵 **Part Time Employee**: Paid strictly per day wage with multi-shift slot options.
- **Attendance Deselect**:
  - Clicking an already active status (`Full Day`, `Half Day`, or `Leave`) deselects it back to unmarked.
  - Alternatively, click the dedicated ✖ deselect button.
- **Daily Narration Dropdown Arrow (▼)**:
  - Beside every attendance button group, click the small dropdown arrow `▼` to open the day note drawer.
  - Record site notes, overtime remarks, or special shift conditions.
  - All dropdown notes are automatically consolidated and displayed in a dedicated table in the Admin Portal.
- **Sunday Handling (Weekly Off)**:
  - 🛑 **Sundays remain strictly unselected**: Sundays are flagged as non-working weekly off days.
  - Attempting to mark attendance on Sunday is blocked on both dashboard and backend API.
  - Attendance counts (`Full Days`, `Half Days`, `Leaves`, `Total Leaves`) strictly exclude Sundays.
  - Sunday is never counted toward present or leave days, and is completely ignored in salary calculations.
  - Whole-month attendance calculation strictly uses non-Sunday working days (e.g. 26 working days in a 30-day month with 4 Sundays).
- **Part-Time Shift Multi-Selection & Mandatory Slot**:
  - Half Day is counted as **1 day**.
  - Opting Full Day provides 3 shift buttons: `☀️ Morning`, `⛅ Afternoon`, `🌙 Evening` with multi-selection enabled.
  - **Mandatory Selection**: When opting Full Day, selecting at least one slot is required (defaults to Morning; deselecting all is blocked).
  - 1 slot selected (Morning OR Afternoon OR Evening) = **1 day**.
  - Any 2 slots selected = **2 days**.
  - All 3 slots selected = **3 days**.
  - Total salary = `Total Calculated Days × Per Day Wage`.
- **Month Calendar Option Beside Every Employee Row**:
  - Color-coded monthly view for every employee:
    - 🟢 **Full Day**: Vibrant Green
    - 🟠 **Half Day**: Vibrant Orange
    - 🔴 **Leave**: Vibrant Red
    - ⚪ **Unmarked**: Slate
    - 🚫 **Sunday Off**: Highlighted with "Sun Off" label and excluded from counts

---

### 2. Admin Portal (Password: `attendance`)
- **Payment Status Checkbox Column**:
  - Added dedicated checkbox column for both **Employees** and **Workers**.
  - Ticking instantly toggles payment status (`Paid` / `Unpaid`) with real-time database persistence.
- **Whole-Month Attendance Salary Locking**:
  - Total salary calculation is finalized **only after updating whole month attendance** for all days in the month.
  - When in progress, shows `Pending Attendance (X/Y days marked)` and displays estimated provisional salary.
  - Admin Portal provides full salary management, leave deduction rules, payment ticking, and worker logs.
- **Workers Fixed Payroll, Narration & Edit Worker**:
  - Fixed-salary workers who are exempt from attendance tracking.
  - Worker narration / description column.
  - Edit modal to update worker name, role, fixed salary, and narration remarks.
- **Daily Notes & Special Narrations Log**:
  - Dedicated section displaying all daily notes and shift slot records entered via the dashboard dropdown arrow.
- **Half-Day Employee Full Day Double Pay**:
  - Half days are **not** counted as 0.5 leaves (only actual leaves count).
  - When marked as **Full Day**, their day salary is **doubled** ($+1 \times \text{day salary bonus}$).
- **Individual Employee Management**:
  - Edit employee names, work types, and narrations directly from the Admin Portal.
  - Delete individual employee records with confirmation.

---

## 📁 Project Architecture

```
auth-website/
├── app.py              # Flask server, dashboard, calendar API, payroll calculation & payments
├── database.py         # SQLite schema & migrations (employees, workers, records, payments)
├── requirements.txt    # Flask dependency
├── test_app.py         # Comprehensive automated unit test suite (13 passing tests)
├── static/
│   └── css/style.css   # Dark glassmorphic styling
└── templates/
    ├── base.html       # Base layout with Tailwind CSS & toast alerts
    ├── dashboard.html  # Daily roster with Month Calendar, dropdown notes, shift slots & deselect
    └── admin.html      # Admin portal with payment ticks, locked month payroll, edit workers & notes log
```

---

## 🚀 Running the Server

Start the application with:
```bash
python3 app.py
```
- **Dashboard**: [http://127.0.0.1:5001](http://127.0.0.1:5001)
- **Admin Password**: `attendance`

---

## 🧪 Automated Tests

Run the test suite with:
```bash
python3 test_app.py
```
All 13 unit tests verify Sunday exclusion from counts and payroll, part-time mandatory shift slots, payment ticks, worker edits & narrations, attendance deselect, daily dropdown notes, half-day double pay, and month completion locking.
