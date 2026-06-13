# 🏋️ Kolodii OS Dashboard

Візуальний дашборд прогресу всіх проєктів Kolodii Fitness.

## Оновлення

Дашборд оновлюється автоматично щодня о 08:00 (Київ) з локального мака через `deploy.sh`.

## Структура

- `index.html` — головна сторінка дашборду
- `data.json` — сирі дані (проєкти, cron jobs, сесії)
- `generate_dashboard.py` — скрипт генерації
- `deploy.sh` — скрипт деплою

## Дані

- **Проєкти** — з `~/KolodiiOS/project_ledger.md`
- **Cron Jobs** — з `hermes cron list`
- **Сесії** — з `~/.hermes/state.db`

---

*Всім фітнес. Бач, як добре. 💪*
