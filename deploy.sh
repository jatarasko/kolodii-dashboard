#!/bin/bash
# Kolodii OS Dashboard — collect data and push to GitHub
# Run this daily via cron

set -e

DASHBOARD_DIR="$HOME/KolodiiOS/dashboard"
REPO_DIR="$HOME/KolodiiOS/dashboard-repo"

echo "🔧 Kolodii OS Dashboard — Daily Update"
echo "   $(date '+%d.%m.%Y %H:%M')"

# Step 1: Generate fresh dashboard
cd "$DASHBOARD_DIR"
python3 generate_dashboard.py

# Step 2: Clone or update repo
if [ ! -d "$REPO_DIR/.git" ]; then
    echo "❌ Repo not found at $REPO_DIR"
    echo "   Create a GitHub repo first, then run:"
    echo "   git clone https://github.com/jatarasko/kolodii-dashboard.git $REPO_DIR"
    exit 1
fi

cd "$REPO_DIR"
git pull --rebase origin main 2>/dev/null || git pull --rebase origin master 2>/dev/null

# Step 3: Copy generated files
cp "$DASHBOARD_DIR/index.html" "$REPO_DIR/index.html"
cp "$DASHBOARD_DIR/data.json" "$REPO_DIR/data.json"

# Step 4: Commit and push
cd "$REPO_DIR"
git add index.html data.json
if git diff --cached --quiet; then
    echo "   ℹ️ No changes — skipping push"
else
    git commit -m "📊 Dashboard update: $(date '+%d.%m.%Y %H:%M')"
    git push origin main 2>/dev/null || git push origin master 2>/dev/null
    echo "   ✅ Pushed to GitHub"
fi

echo "   ✅ Done!"
