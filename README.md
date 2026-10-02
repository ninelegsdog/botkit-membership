# BotKit Membership

Бот подписок и членства: оформление, оплата, контроль доступа.

Живой бот: @MembershipKitBot · часть портфолио из 9 Telegram-ботов на Python.

## Возможности

- Оформление и продление подписки
- Оплата через ЮKassa (`BOTKIT__YOOKASSA_SHOP_ID` / `_SECRET_KEY`)
- Пробный период `BOTKIT__TRIAL_DAYS` и льготный период `BOTKIT__GRACE_DAYS`
- Управление доступом к закрытому контенту
- Модули напоминаний о продлении
- Миграции БД встроены в код (`src/core/migrations.py`)
- Троттлинг с настраиваемыми лимитами, часовой пояс, `/metrics`, Sentry

## Стек

- Python 3.12+
- aiogram 3.x
- SQLAlchemy 2 (async) + SQLite (WAL) / PostgreSQL
- Redis
- Prometheus `/metrics`
- Sentry
- Docker, webhook (prod) / polling (dev)

## Быстрый старт

```bash
cp .env.example .env      # заполнить BOT_TOKEN и ADMIN_IDS
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python -m bot
```

## Переменные окружения

BOTKIT__BOT_TOKEN, BOTKIT__ADMIN_PASSWORD, BOTKIT__ADMIN_IDS, BOTKIT__DATABASE_URL, BOTKIT__REDIS_URL, BOTKIT__YOOKASSA_SHOP_ID, BOTKIT__YOOKASSA_SECRET_KEY, BOTKIT__WEBHOOK_SECRET_TOKEN, BOTKIT__WEBHOOK_URL, BOTKIT__SENTRY_DSN, BOTKIT__METRICS_PORT, BOTKIT__TIMEZONE, BOTKIT__TRIAL_DAYS, BOTKIT__GRACE_DAYS, BOTKIT__THROTTLE_RATE_LIMIT, BOTKIT__THROTTLE_MAX_IDLE

Секреты не хранятся в git: `.env` в `.gitignore`, для переноса используется
шифрование age, в CI включён gitleaks-гейт.

## Тесты

```bash
pytest
```

163 теста в 24 файлах.

## Бэкапы

Крон на VPS (ежедневно 04:00, retention 14 дней):

```
0 4 * * * AGE_RECIPIENT=age1... OFFSITE_TARGET=user@backup-host:/srv/backups /usr/local/bin/botkit-backup.sh <BOTNAME>
```

Восстановление:

```
botkit-restore.sh <BOTNAME> <db-name>.db ~/.secrets/keys/backup.txt [target-dir]
```

## Development process

Проект создан в AI-native процессе разработки: код производили AI coding-агенты
в настроенном мной agent harness — то есть по слотам требований, инструкций, ограничений
и критериев приёмки, которые я задал заранее.

Моя роль в проекте:

- продуктовая постановка и пользовательские сценарии;
- декомпозиция задачи на самостоятельные инженерные этапы;
- context engineering: инструкции, ограничения и рабочие правила для агентов;
- управление контекстным окном между итерациями;
- цикл «спецификация → генерация → запуск → проверка → исправление»;
- валидация результата, тестирование, ревью;
- контроль структуры репозитория, конфигурации, документации и воспроизводимости запуска.

Implementation code was generated with AI coding agents under human-led engineering control.

Полное описание процесса, шаблон `AGENTS.md` и чек-листы ревью AI-кода и секретов —
в репозитории [agentic-development-playbook](https://github.com/ninelegsdog).

## Лицензия

MIT — см. [LICENSE](LICENSE).

## Статус

Проект работает в продакшене (webhook, TLS, health-check). Состояние: **production**.
