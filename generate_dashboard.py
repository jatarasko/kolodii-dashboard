#!/usr/bin/env python3
"""
Kolodii OS Dashboard Generator
Збирає дані з project_ledger.md, cron jobs, session logs
Генерує красивий HTML dashboard (світла тема)
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

HOME = Path.home()
KOLIIOS = HOME / "KolodiiOS"
LEDGER = KOLIIOS / "project_ledger.md"
DASHBOARD_DIR = KOLIIOS / "dashboard"
OUTPUT_HTML = DASHBOARD_DIR / "index.html"
STATE_DB = HOME / ".hermes" / "state.db"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def run(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.stdout.strip()
    except Exception:
        return ""

def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def status_color(status: str) -> str:
    return {
        "active": "#22c55e",
        "paused": "#f59e0b",
        "completed": "#3b82f6",
        "cancelled": "#ef4444",
    }.get(status.lower(), "#9ca3af")

def status_emoji(status: str) -> str:
    return {
        "active": "🟢",
        "paused": "🟡",
        "completed": "🔵",
        "cancelled": "🔴",
    }.get(status.lower(), "⚪")

def impact_color(impact: str) -> str:
    return {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}.get(impact.lower(), "#9ca3af")

def truncate(text: str, max_len: int = 120) -> str:
    text = text.strip()
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text

# ─── Parse project_ledger.md ──────────────────────────────────────────────────

def parse_ledger() -> list[dict]:
    """
    Parse project_ledger.md — reads project tables.
    For active/paused projects extracts: name, status, impact, progress, next_step
    Skips: legend, business impact ranking, recommended focus, change log, completed, cancelled
    """
    projects = []
    if not LEDGER.exists():
        return projects

    content = LEDGER.read_text(encoding="utf-8")
    lines = content.split('\n')

    skip_sections = {
        "legend", "business impact ranking", "recommended focus", "change log",
        "completed projects", "cancelled projects"
    }
    current_section = ""
    in_table = False

    for line in lines:
        if line.startswith('## '):
            current_section = line[3:].strip().lower()
            in_table = False
            continue

        if any(s in current_section for s in skip_sections):
            continue

        if '|' in line and ('Project Name' in line or ('Project' in line and 'Status' in line)):
            in_table = True
            continue

        if in_table and line.strip().startswith('|---'):
            continue

        if in_table and line.strip().startswith('|'):
            parts = [p.strip() for p in line.strip().strip('|').split('|')]
            if len(parts) >= 6:
                name = parts[1].strip()
                status = parts[2].strip().lower()
                impact = parts[3].strip().lower()
                completion = parts[4].strip()
                next_step = parts[5].strip() if len(parts) > 5 else ""

                if not name or name in ('_(none)_', '--'):
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
                    "next_step": next_step,
                })

        if in_table and (not line.strip() or line.startswith('#')):
            in_table = False

    return projects


def get_todays_tasks(projects: list[dict]) -> dict:
    """
    Build today's task list from projects.
    - main_goal: highest priority active project with next_step
    - additional: other active projects with next_step
    """
    active = [p for p in projects if p["status"] == "active" and p.get("next_step")]
    high = [p for p in active if p["impact"] == "high"]
    medium = [p for p in active if p["impact"] == "medium"]
    low = [p for p in active if p["impact"] == "low"]

    main_goal = high[0] if high else (active[0] if active else None)
    additional = [p for p in active if p != main_goal]

    # Limit to top 5 additional
    additional = additional[:5]

    return {
        "main_goal": main_goal,
        "additional": additional,
    }


# ─── Get cron jobs info ───────────────────────────────────────────────────────

def get_cron_jobs() -> list[dict]:
    """Parse hermes cron list text output"""
    text = run("hermes cron list 2>/dev/null")
    if not text:
        return []

    jobs = []
    current = {}
    for line in text.split('\n'):
        stripped = line.strip()
        if re.match(r'^[0-9a-f]{12}\s+\[(active|paused)\]', stripped):
            if current.get('name'):
                jobs.append(current)
            state = 'active' if '[active]' in stripped else 'paused'
            current = {'enabled': state == 'active', 'state': state}
        elif stripped.startswith('Name:'):
            current['name'] = stripped.split(':', 1)[-1].strip()
        elif stripped.startswith('Schedule:'):
            current['schedule'] = stripped.split(':', 1)[-1].strip()
        elif stripped.startswith('Next run:'):
            current['next_run'] = stripped.split(':', 1)[-1].strip()
        elif stripped.startswith('Deliver:'):
            current['deliver'] = stripped.split(':', 1)[-1].strip()

    if current.get('name'):
        jobs.append(current)

    for j in jobs:
        j.setdefault('schedule', '')
        j.setdefault('next_run', '')
        j.setdefault('deliver', '')
        j.setdefault('enabled', True)
    return jobs


# ─── Get recent session activity ──────────────────────────────────────────────

def get_recent_sessions(limit: int = 10) -> list[dict]:
    """
    Get recent sessions with title, date, source, message_count.
    For summary: extract last assistant message as approximation.
    """
    sessions = []
    if not STATE_DB.exists():
        return sessions

    try:
        # Get session list
        output = run(
            f'sqlite3 "{STATE_DB}" "SELECT id, title, source, started_at, message_count '
            f'FROM sessions WHERE archived=0 ORDER BY started_at DESC LIMIT {limit};" 2>/dev/null'
        )
        if not output:
            return sessions

        for line in output.split('\n'):
            parts = line.split('|')
            if len(parts) < 5:
                continue

            sid = parts[0].strip()
            title = parts[1].strip()
            source = parts[2].strip()

            try:
                ts = float(parts[3])
                dt = datetime.fromtimestamp(ts)
                date_str = dt.strftime("%d.%m %H:%M")
            except (ValueError, OSError):
                date_str = parts[3][:10]

            msg_count = parts[4].strip()

            # Fallback title
            if not title:
                # Try to get first user message
                first_msg = run(
                    f'sqlite3 "{STATE_DB}" "SELECT substr(content, 1, 80) FROM messages '
                    f'WHERE session_id=\'{sid}\' AND role=\'user\' ORDER BY timestamp ASC LIMIT 1;" 2>/dev/null'
                )
                title = first_msg.strip()[:60] + "…" if first_msg.strip() else sid[:30]

            # Get last assistant message for summary
            last_assistant = run(
                f'sqlite3 "{STATE_DB}" "SELECT substr(content, 1, 200) FROM messages '
                f'WHERE session_id=\'{sid}\' AND role=\'assistant\' ORDER BY timestamp DESC LIMIT 1;" 2>/dev/null'
            )
            summary = ""
            if last_assistant.strip():
                # Clean up: take first meaningful line
                for aline in last_assistant.strip().split('\n'):
                    aline = aline.strip()
                    if aline and not aline.startswith('#') and len(aline) > 10:
                        summary = truncate(aline, 100)
                        break
                if not summary:
                    summary = truncate(last_assistant.strip(), 100)

            # Get first user message for recommendation context
            first_user = run(
                f'sqlite3 "{STATE_DB}" "SELECT substr(content, 1, 150) FROM messages '
                f'WHERE session_id=\'{sid}\' AND role=\'user\' ORDER BY timestamp ASC LIMIT 1;" 2>/dev/null'
            )
            topic = truncate(first_user.strip(), 80) if first_user.strip() else ""

            sessions.append({
                "title": title,
                "date": date_str,
                "source": source,
                "messages": msg_count,
                "summary": summary,
                "topic": topic,
            })
    except Exception:
        pass

    return sessions


# ─── Calculate stats ──────────────────────────────────────────────────────────

def calc_stats(projects: list[dict], jobs: list[dict]) -> dict:
    total = len(projects)
    active = sum(1 for p in projects if p["status"] == "active")
    paused = sum(1 for p in projects if p["status"] == "paused")
    completed = sum(1 for p in projects if p["status"] == "completed")
    high_impact = sum(1 for p in projects if p["impact"] == "high" and p["status"] == "active")
    active_jobs = sum(1 for j in jobs if j.get("enabled", True))
    total_jobs = len(jobs)
    avg_progress = sum(p["progress"] for p in projects) // max(total, 1)

    return {
        "total_projects": total,
        "active": active,
        "paused": paused,
        "completed": completed,
        "high_impact": high_impact,
        "avg_progress": avg_progress,
        "active_jobs": active_jobs,
        "total_jobs": total_jobs,
    }


# ─── HTML Template ────────────────────────────────────────────────────────────

def generate_html(projects: list[dict], jobs: list[dict], sessions: list[dict],
                  stats: dict, todays_tasks: dict) -> str:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Sort projects: active first, then by impact
    order = {"active": 0, "paused": 1, "completed": 2, "cancelled": 3}
    imp_order = {"high": 0, "medium": 1, "low": 2}
    projects.sort(key=lambda p: (order.get(p["status"], 9), imp_order.get(p["impact"], 9)))

    # ── Project cards ──
    project_cards = ""
    for p in projects:
        sc = status_color(p["status"])
        se = status_emoji(p["status"])
        ic = impact_color(p["impact"])
        impact_label = {"high": "Високий", "medium": "Середній", "low": "Низький"}.get(p["impact"], p["impact"])
        status_label = {
            "active": "Активний", "paused": "На паузі",
            "completed": "Завершено", "cancelled": "Скасовано"
        }.get(p["status"], p["status"])

        next_step_html = ""
        if p.get("next_step"):
            next_step_html = f'<div class="next-step">🎯 Наступний крок: {p["next_step"]}</div>'

        project_cards += f"""
      <div class="project-card status-{p['status']}">
        <div class="project-header">
          <h3>{se} {p['name']}</h3>
          <div class="badges">
            <span class="badge" style="background:{sc}">{status_label}</span>
            <span class="badge" style="background:{ic}">{impact_label}</span>
          </div>
        </div>
        <div class="progress-section">
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" style="width:{p['progress']}%; background:{sc}"></div>
          </div>
          <span class="progress-text">{p['progress']}%</span>
        </div>
        {next_step_html}
      </div>"""

    # ── Compact cron jobs ──
    cron_html = ""
    for j in jobs:
        state_color = "#22c55e" if j.get("enabled") else "#9ca3af"
        state_text = "🟢" if j.get("enabled") else "⚪"
        next_run = j.get("next_run", "")
        if next_run:
            next_run = next_run[:16].replace("T", " ")

        cron_html += f"""
      <div class="cron-compact">
        <span class="cron-dot" style="background:{state_color}"></span>
        <span class="cron-name">{j['name']}</span>
        <span class="cron-schedule">{j.get('schedule', '')}</span>
        <span class="cron-next">→ {next_run}</span>
      </div>"""

    if not cron_html:
        cron_html = '<p class="empty">Немає cron задач</p>'

    # ── Sessions with summary ──
    sessions_html = ""
    source_icons = {"tui": "💻", "telegram": "📱", "cron": "⏰"}
    for s in sessions[:8]:
        icon = source_icons.get(s.get("source", ""), "💬")
        summary_text = s.get("summary", "")
        topic_text = s.get("topic", "")

        # Build subtitle: use topic (first user msg) + summary (last assistant msg)
        subtitle_parts = []
        if topic_text and topic_text != s["title"]:
            subtitle_parts.append(f"Тема: {topic_text}")
        if summary_text:
            subtitle_parts.append(f"Резюме: {summary_text}")

        subtitle = " · ".join(subtitle_parts) if subtitle_parts else ""

        sessions_html += f"""
      <div class="session-card">
        <div class="session-top">
          <span class="session-title">{icon} {s['title']}</span>
          <span class="session-date">{s['date']}</span>
        </div>
        {"<div class='session-summary'>" + subtitle + "</div>" if subtitle else ""}
        <div class="session-meta">
          <span>{s.get('source', '')}</span>
          <span>{s.get('messages', '')} повідомлень</span>
        </div>
      </div>"""

    if not sessions_html:
        sessions_html = '<p class="empty">Немає даних про сесії</p>'

    # ── Today's tasks ──
    main = todays_tasks.get("main_goal")
    additional = todays_tasks.get("additional", [])

    main_html = ""
    if main:
        main_html = f"""
      <div class="task-main">
        <div class="task-label">🎯 Головна мета</div>
        <div class="task-name">{main['name']}</div>
        <div class="task-step">{main.get('next_step', '')}</div>
        <div class="task-progress">
          <div class="progress-bar-bg small">
            <div class="progress-bar-fill" style="width:{main['progress']}%; background:#667eea"></div>
          </div>
          <span>{main['progress']}%</span>
        </div>
      </div>"""
    else:
        main_html = """
      <div class="task-main">
        <div class="task-label">🎯 Головна мета</div>
        <div class="task-name empty">Немає активних задач</div>
      </div>"""

    additional_html = ""
    for t in additional:
        additional_html += f"""
      <div class="task-item">
        <div class="task-item-name">{t['name']}</div>
        <div class="task-item-step">{t.get('next_step', '')}</div>
        <div class="task-item-progress">
          <div class="progress-bar-bg small">
            <div class="progress-bar-fill" style="width:{t['progress']}%; background:#94a3b8"></div>
          </div>
          <span>{t['progress']}%</span>
        </div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="uk">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kolodii OS Dashboard</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #f1f5f9;
      color: #1e293b;
      line-height: 1.5;
    }}

    /* Header */
    .header {{
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 1.75rem 1.5rem;
      text-align: center;
    }}
    .header h1 {{ font-size: 1.75rem; margin-bottom: 0.3rem; }}
    .header .subtitle {{ opacity: 0.85; font-size: 0.9rem; }}
    .header .updated {{ opacity: 0.65; font-size: 0.75rem; margin-top: 0.4rem; }}

    .container {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 1.25rem;
    }

    /* Stats */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }}
    .stat-card {{
      background: white;
      border-radius: 10px;
      padding: 1rem;
      text-align: center;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      border: 1px solid #e2e8f0;
    }}
    .stat-number {{ font-size: 1.75rem; font-weight: 700; color: #667eea; }}
    .stat-label {{ font-size: 0.7rem; color: #64748b; margin-top: 0.2rem; text-transform: uppercase; letter-spacing: 0.05em; }}

    /* Section */
    .section {{ margin-bottom: 1.5rem; }}
    .section-title {{
      font-size: 1rem;
      font-weight: 600;
      margin-bottom: 0.75rem;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      color: #475569;
    }}

    /* Today's Tasks */
    .tasks-container {{
      background: white;
      border-radius: 12px;
      padding: 1.25rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      border: 1px solid #e2e8f0;
    }}
    .task-main {{
      background: linear-gradient(135deg, #667eea10 0%, #764ba210 100%);
      border: 1px solid #667eea30;
      border-radius: 10px;
      padding: 1rem;
      margin-bottom: 0.75rem;
    }}
    .task-label {{ font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: #667eea; font-weight: 600; }}
    .task-name {{ font-size: 1.1rem; font-weight: 600; margin: 0.3rem 0; }}
    .task-name.empty {{ color: #94a3b8; font-weight: 400; }}
    .task-step {{ font-size: 0.85rem; color: #475569; margin-bottom: 0.5rem; }}
    .task-progress, .task-item-progress {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    .task-item-progress span {{ font-size: 0.7rem; color: #94a3b8; min-width: 30px; }}

    .task-divider {{ height: 1px; background: #e2e8f0; margin: 0.75rem 0; }}

    .task-item {{
      padding: 0.6rem 0;
      border-bottom: 1px solid #f1f5f9;
    }}
    .task-item:last-child {{ border-bottom: none; }}
    .task-item-name {{ font-weight: 600; font-size: 0.9rem; }}
    .task-item-step {{ font-size: 0.8rem; color: #64748b; margin: 0.2rem 0 0.4rem; }}

    /* Project Cards */
    .projects-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 0.75rem;
    }}
    .project-card {{
      background: white;
      border-radius: 10px;
      padding: 1rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      border: 1px solid #e2e8f0;
      border-left: 3px solid #94a3b8;
      transition: box-shadow 0.15s;
    }}
    .project-card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.12); }}
    .project-card.status-active {{ border-left-color: #22c55e; }}
    .project-card.status-paused {{ border-left-color: #f59e0b; }}
    .project-card.status-completed {{ border-left-color: #3b82f6; }}
    .project-card.status-cancelled {{ border-left-color: #ef4444; }}

    .project-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 0.5rem;
      gap: 0.5rem;
    }}
    .project-header h3 {{ font-size: 0.9rem; font-weight: 600; flex: 1; }}
    .badges {{ display: flex; gap: 0.3rem; flex-shrink: 0; }}
    .badge {{
      color: white;
      padding: 0.15rem 0.5rem;
      border-radius: 12px;
      font-size: 0.6rem;
      font-weight: 600;
      white-space: nowrap;
    }}

    .progress-section {{
      display: flex;
      align-items: center;
      gap: 0.6rem;
      margin-bottom: 0.4rem;
    }}
    .progress-bar-bg {{
      flex: 1;
      height: 6px;
      background: #e2e8f0;
      border-radius: 3px;
      overflow: hidden;
    }}
    .progress-bar-bg.small {{ height: 4px; }}
    .progress-bar-fill {{
      height: 100%;
      border-radius: 3px;
      transition: width 0.4s ease;
    }}
    .progress-text {{ font-size: 0.7rem; font-weight: 600; color: #475569; min-width: 30px; text-align: right; }}

    .next-step {{
      font-size: 0.75rem;
      color: #64748b;
      margin-top: 0.4rem;
      padding: 0.4rem 0.6rem;
      background: #f8fafc;
      border-radius: 6px;
      border-left: 2px solid #667eea;
    }}

    /* Cron Compact */
    .cron-list {{
      background: white;
      border-radius: 10px;
      padding: 0.75rem 1rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      border: 1px solid #e2e8f0;
    }}
    .cron-compact {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.35rem 0;
      border-bottom: 1px solid #f8fafc;
      font-size: 0.8rem;
    }}
    .cron-compact:last-child {{ border-bottom: none; }}
    .cron-dot {{
      width: 7px; height: 7px;
      border-radius: 50%;
      flex-shrink: 0;
    }}
    .cron-name {{ font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .cron-schedule {{ color: #94a3b8; font-size: 0.7rem; flex-shrink: 0; }}
    .cron-next {{ color: #64748b; font-size: 0.7rem; flex-shrink: 0; }}

    /* Sessions */
    .sessions-list {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}
    .session-card {{
      background: white;
      border-radius: 10px;
      padding: 0.85rem 1rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
      border: 1px solid #e2e8f0;
    }}
    .session-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 0.5rem;
      margin-bottom: 0.25rem;
    }}
    .session-title {{ font-size: 0.85rem; font-weight: 600; flex: 1; }}
    .session-date {{ font-size: 0.7rem; color: #94a3b8; white-space: nowrap; flex-shrink: 0; }}
    .session-summary {{
      font-size: 0.75rem;
      color: #64748b;
      margin-bottom: 0.35rem;
      line-height: 1.4;
    }}
    .session-meta {{
      display: flex;
      gap: 0.75rem;
      font-size: 0.65rem;
      color: #94a3b8;
    }}

    .empty {{ color: #94a3b8; font-style: italic; padding: 0.75rem; font-size: 0.85rem; }}

    /* Footer */
    .footer {{
      text-align: center;
      padding: 1.5rem;
      color: #94a3b8;
      font-size: 0.75rem;
    }}

    @media (max-width: 600px) {{
      .projects-grid {{ grid-template-columns: 1fr; }}
      .stats-grid {{ grid-template-columns: repeat(3, 1fr); }}
      .header h1 {{ font-size: 1.4rem; }}
      .cron-schedule {{ display: none; }}
      .cron-next {{ display: none; }}
    }}
  </style>
</head>
<body>

<div class="header">
  <h1>🏋️ Kolodii OS</h1>
  <div class="subtitle">Операційна система Kolodii Fitness</div>
  <div class="updated">Оновлено: {now}</div>
</div>

<div class="container">

  <!-- Stats -->
  <div class="stats-grid">
    <div class="stat-card"><div class="stat-number">{stats['total_projects']}</div><div class="stat-label">Проєктів</div></div>
    <div class="stat-card"><div class="stat-number" style="color:#22c55e">{stats['active']}</div><div class="stat-label">Активних</div></div>
    <div class="stat-card"><div class="stat-number" style="color:#3b82f6">{stats['completed']}</div><div class="stat-label">Завершено</div></div>
    <div class="stat-card"><div class="stat-number" style="color:#ef4444">{stats['high_impact']}</div><div class="stat-label">Високий вплив</div></div>
    <div class="stat-card"><div class="stat-number">{stats['avg_progress']}%</div><div class="stat-label">Сер. прогрес</div></div>
    <div class="stat-card"><div class="stat-number">{stats['active_jobs']}/{stats['total_jobs']}</div><div class="stat-label">Cron</div></div>
  </div>

  <!-- Today's Tasks -->
  <div class="section">
    <h2 class="section-title">📋 Задачі на сьогодні</h2>
    <div class="tasks-container">
      {main_html}
      {'<div class="task-divider"></div>' if additional else ""}
      {additional_html}
    </div>
  </div>

  <!-- Projects -->
  <div class="section">
    <h2 class="section-title">📊 Проєкти</h2>
    <div class="projects-grid">
      {project_cards if project_cards else '<p class="empty">Немає проєктів</p>'}
    </div>
  </div>

  <!-- Cron Jobs (compact) -->
  <div class="section">
    <h2 class="section-title">⏰ Заплановані задачі</h2>
    <div class="cron-list">
      {cron_html}
    </div>
  </div>

  <!-- Recent Sessions -->
  <div class="section">
    <h2 class="section-title">💬 Останні сесії</h2>
    <div class="sessions-list">
      {sessions_html}
    </div>
  </div>

</div>

<div class="footer">
  <p>Kolodii OS Dashboard · Автоматично згенеровано щодня</p>
  <p style="margin-top:0.3rem">Всім фітнес. Бач, як добре. 💪</p>
</div>

</body>
</html>"""


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"🔧 Kolodii OS Dashboard Generator")
    print(f"   Date: {today()}")

    projects = parse_ledger()
    print(f"   Projects: {len(projects)}")

    jobs = get_cron_jobs()
    print(f"   Cron jobs: {len(jobs)}")

    sessions = get_recent_sessions(limit=8)
    print(f"   Sessions: {len(sessions)}")

    stats = calc_stats(projects, jobs)
    print(f"   Avg progress: {stats['avg_progress']}%")

    todays_tasks = get_todays_tasks(projects)
    print(f"   Main goal: {todays_tasks['main_goal']['name'] if todays_tasks['main_goal'] else '—'}")
    print(f"   Additional: {len(todays_tasks['additional'])}")

    html = generate_html(projects, jobs, sessions, stats, todays_tasks)

    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"   ✅ Dashboard: {OUTPUT_HTML}")

    data = {
        "generated": datetime.now().isoformat(),
        "stats": stats,
        "projects": projects,
        "jobs": jobs,
        "todays_tasks": {
            "main_goal": todays_tasks["main_goal"]["name"] if todays_tasks["main_goal"] else None,
            "additional_count": len(todays_tasks["additional"]),
        },
    }
    json_path = DASHBOARD_DIR / "data.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ✅ Data: {json_path}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
