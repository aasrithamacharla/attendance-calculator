#!/bin/bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "=========================================="
echo " Pushing Attendance Calculator to GitHub "
echo "=========================================="

# 1. Check if git is available
if ! git --version >/dev/null 2>&1; then
    echo "[!] Xcode Command Line Tools is required for git on macOS."
    echo "[!] Triggering installation dialog: xcode-select --install"
    xcode-select --install
    echo ""
    echo "Please click 'Install' on the popup window that appears."
    echo "Once finished, rerun this script: ./push_to_github.sh"
    exit 1
fi

# 2. Initialize git if not already initialized
if [ ! -d ".git" ]; then
    echo "[-] Initializing git repository on branch 'main'..."
    git init -b main
else
    git branch -M main 2>/dev/null || true
fi

# 3. Configure remote origin
TARGET_URL="https://github.com/aasrithamacharla/attendance-calculator.git"
if git remote | grep -q "^origin$"; then
    git remote set-url origin "$TARGET_URL"
else
    git remote add origin "$TARGET_URL"
fi
echo "[-] Configured remote origin: $TARGET_URL"

# 4. Stage all files
echo "[-] Staging files..."
git add .

# 5. Commit changes
if git diff --cached --quiet; then
    echo "[-] No new changes to commit."
else
    echo "[-] Committing files..."
    git commit -m "Initial commit: Employee Attendance & Payroll Portal with Firebase integration"
fi

# 6. Push to GitHub
echo "[-] Pushing to GitHub repository..."
git push -u origin main || {
    echo ""
    echo "[!] If the remote repo has existing files (e.g., initial README/license), rebase and push:"
    echo "    git pull origin main --rebase"
    echo "    git push -u origin main"
}

echo ""
echo "[✓] Push complete! Visit: https://github.com/aasrithamacharla/attendance-calculator"
