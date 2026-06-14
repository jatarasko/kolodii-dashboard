# Інструкція налаштування GitHub Pages для дашборду

## Крок 1: Створи репозиторій на GitHub

1. Відди https://github.com/new
2. Назва: `kolodii-dashboard`
3. Тип: Public (або Private — але Pages працює тільки з Public на безкоштовному плані)
4. НЕ додавай README, .gitignore, чи ліцензію
5. Натисни "Create repository"

## Крок 2: Підключи локальну папку

```bash
cd ~/KolodiiOS/dashboard
git init
git remote add origin hhttps://github.com/jatarasko/kolodii-dashboard.git
git add index.html data.json README.md .github/workflows/pages.yml generate_dashboard.py
git commit -m "Initial dashboard"
git branch -M main
git push -u origin main
```

## Крок 3: Увімкни GitHub Pages

1. В репозиторії → Settings → Pages
2. Source: GitHub Actions
3. Збережи

## Крок 4: Налаштуй deploy.sh

Відкрий `~/KolodiiOS/dashboard/deploy.sh` і заміни `YOUR_USER` на свій GitHub username.

## Крок 5: Протестуй

```bash
cd ~/KolodiiOS/dashboard
./deploy.sh
```

Після цього дашборд буде доступний за адресою:
`https://YOUR_USERNAME.github.io/kolodii-dashboard/`

## Щоденне оновлення

- Cron job "Dashboard: Daily Update & Telegram" запускається о 08:00
- Він генерує свіжий HTML і надсилає в Telegram
- Для деплою на GitHub запусти `deploy.sh` вручну або додай його в cron
