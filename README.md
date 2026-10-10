# BotKit Membership

Бот подписок и членства: оформление, оплата, контроль доступа.

Живой бот: @MembershipKitBot · часть портфолио из 9 Telegram-ботов на Python.

## Возможности

- Оформление и продление подписки
- Оплата через ЮKassa (`YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY`)
- Пробный период `TRIAL_DAYS` и льготный период `GRACE_DAYS`
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
cp .env.example .env      # заполнить TELEGRAM_BOT_TOKEN и ADMIN_IDS
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python -m bot
```

## Переменные окружения

Ключи задаются без префикса: `TELEGRAM_BOT_TOKEN` (токен бота), `ADMIN_PASSWORD`,
`ADMIN_IDS`, `DATABASE_URL`, `REDIS_URL`, `YOOKASSA_SHOP_ID`,
`YOOKASSA_SECRET_KEY`, `WEBHOOK_SECRET_TOKEN`, `WEBHOOK_URL`, `SENTRY_DSN`,
`METRICS_PORT`, `TIMEZONE`, `TRIAL_DAYS`, `GRACE_DAYS`, `THROTTLE_RATE_LIMIT`,
`THROTTLE_MAX_IDLE`.

Секреты не хранятся в git: `.env` в `.gitignore`, для переноса используется
шифрование age, в CI включён gitleaks-гейт.

## Тесты

```bash
pytest
```

163 теста в 24 файлах.

## Бэкапы

Бэкапы и восстановление — общий контур на проде (systemd-таймеры, offsite restic,
один общий Redis на все боты), а не отдельный скрипт внутри репозитория.
Актуальная процедура и оговорки — в
[`botkit-monitoring/ops/backup/RESTORE.md`](https://github.com/ninelegsdog/botkit-monitoring/blob/main/ops/backup/RESTORE.md).

```bash
# проверка бэкапа этого бота (ничего не меняет)
/root/restore_test.sh botkit-membership
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
в репозитории [agentic-development-playbook](https://github.com/ninelegsdog/agentic-development-playbook).

## Лицензия

MIT — см. [LICENSE](LICENSE).

## Статус

Проект работает в продакшене (webhook, TLS, health-check). Состояние: **production**.
