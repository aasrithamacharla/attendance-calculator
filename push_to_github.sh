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
    echo "[!] Running: xcode-select --install"
    xcode-select --install
    echo "Please click 'Install' on the popup window, wait for it to finish, and run this script again."
    exit 1
fi

# 2. Ensure git branch is main
git branch -M main 2>/dev/null || true

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

# 5. Commit changes if any
if git diff --cached --quiet; then
    echo "[-] No new uncommitted changes (commit already exists)."
else
    echo "[-] Committing files..."
    git commit -m "Update dashboard to AJ Attendance Dashboard, connect attendance-90920 Firebase RTDB, and configure Gunicorn for Render"
fi

# 6. Push to GitHub
echo "[-] Pushing to GitHub (origin/main)..."
if git push -u origin main; then
    echo ""
    echo "================================================================"
    echo " [✓] SUCCESS! Your code is now live on GitHub:"
    echo "     https://github.com/aasrithamacharla/attendance-calculator"
    echo "================================================================"
    exit 0
fi

# If standard push failed, test if pull/rebase is needed (e.g. remote has initial README)
echo ""
echo "[!] Standard push did not succeed. Checking if remote has existing commits..."
if git pull origin main --rebase --allow-unrelated-histories 2>/dev/null; then
    echo "[-] Rebase successful. Pushing merged commits..."
    if git push -u origin main; then
        echo ""
        echo "================================================================"
        echo " [✓] SUCCESS! Your code is now live on GitHub:"
        echo "     https://github.com/aasrithamacharla/attendance-calculator"
        echo "================================================================"
        exit 0
    fi
fi

echo ""
echo "================================================================"
echo " [!] Push did not complete."
echo " Common reasons:"
echo " 1. GitHub Authentication: GitHub requires a Personal Access Token (PAT)"
echo "    instead of your account password."
echo "    Create one at: https://github.com/settings/tokens (select 'repo' scope)"
echo "    When prompted for Password in terminal, paste your token."
echo ""
echo " 2. If the remote repo has unrelated files and you want your local code to override:"
echo "    git push -u origin main --force"
echo "================================================================"
exit 1
