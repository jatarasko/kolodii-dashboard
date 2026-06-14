#!/usr/bin/env python3
"""
Kolodii OS Telegram Dashboard
Генерує коротке текстове повідомлення з прогресом для Telegram
"""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOME = Path.home()
KOLIIOS = HOME / "KolodiiOS"
LEDGER = KOLIIOS / "project_ledger.md"

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.stdout.strip()
    except Exception:
        return ""

def parse_ledger():
    """Parse project_ledger.md — reads project tables, skips legend/meta sections"""
    projects = []
    if not LEDGER.exists():
        return projects

    content = LEDGER.read_text(encoding="utf-8")
    lines = content.split('\n')

    skip_sections = {"legend", "business impact ranking", "recommended focus", "change log",
                     "completed projects", "cancelled projects"}
    current_section = ""
    in_table = False

    for line in lines:
        if line.startswith('## '):
            current_section = line[3:].strip().lower()
            in_table = False
            continue

        if any(s in current_section for s in skip_sections):
            continue

        if '|' in line and ('Project Name' in line or 'Project' in line and 'Status' in line):
            in_table = True
            continue

        if in_table and line.strip().startswith('|---'):
            continue

        if in_table and line.strip().startswith('|'):
            parts = [p.strip() for p in line.strip().strip('|').split('|')]
            if len(parts) >= 5:
                name = parts[1].strip()
                status = parts[2].strip().lower()
                impact = parts[3].strip().lower()
                completion = parts[4].strip()

                if not name or name == '_(none)_' or name == '--':
                    continue
                if not status or status == '--':
                    continue

                progress = 0
                prog_match = re.search(r'(\d+)', completion)
                if prog_match:
                    progress = int(prog_match.group(1))
                elif status == "completed":
                    progress = 100

                projects.append({
                    "name": name,
                    "status": status if status in ("active", "paused", "completed", "cancelled") else "active",
                    "impact": impact if impact in ("high", "medium", "low") else "medium",
                    "progress": progress,
                })

        if in_table and (not line.strip() or line.startswith('#')):
            in_table = False

    return projects

def get_cron_summary():
    text = run("hermes cron list 2>/dev/null")
    if not text:
        return 0, 0
    active = text.count("[active]")
    paused = text.count("[paused]")
    return active, paused

def generate_telegram_message(projects, cron_active, cron_paused):
    now = datetime.now().strftime("%d.%m.%Y")
    active_projects = [p for p in projects if p["status"] == "active"]
    paused_projects = [p for p in projects if p["status"] == "paused"]
    completed_projects = [p for p in projects if p["status"] == "completed"]

    avg = 0
    if projects:
        avg = sum(p["progress"] for p in projects) // len(projects)

    msg = f"📊 Kolodii OS Dashboard — {now}\n\n"
    msg += f"🎯 Проєктів: {len(projects)} | Активних: {len(active_projects)} | Завершено: {len(completed_projects)}\n"
    msg += f"📈 Середній прогрес: {avg}%\n"
    msg += f"⏰ Cron: {cron_active} активних / {cron_paused} на паузі\n\n"

    if active_projects:
        msg += "🟢 Активні проєкти:\n"
        for p in active_projects:
            bar_len = 10
            filled = int(p["progress"] / 100 * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)
            impact = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(p["impact"], "⚪")
            msg += f"  {impact} {p['name']}: {bar} {p['progress']}%\n"
        msg += "\n"

    if paused_projects:
        msg += "🟡 На паузі:\n"
        for p in paused_projects:
            msg += f"  • {p['name']} ({p['progress']}%)\n"
        msg += "\n"

    if completed_projects:
        msg += "✅ Завершено:\n"
        for p in completed_projects:
            msg += f"  • {p['name']}\n"
        msg += "\n"

    msg += "Всім фітнес. Бач, як добре. 💪"
    return msg

def main():
    projects = parse_ledger()
    cron_active, cron_paused = get_cron_summary()
    msg = generate_telegram_message(projects, cron_active, cron_paused)
    print(msg)
    return 0

if __name__ == "__main__":
    sys.exit(main())
