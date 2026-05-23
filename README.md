# Nout Panel

Лёгкая веб-панель для домашнего ноута на Linux: CPU, RAM, диски, температура. Обновление ~1 с в браузере. Без Docker, только Python 3 из коробки.

## Возможности

- Мониторинг загрузки CPU, памяти, load average
- **Графики истории** (~10 мин) — Chart.js, тёмная тема
- Состояние смонтированных дисков
- Температуры (если доступны в `/sys/class/thermal`)
- Удобно с телефона в той же Wi‑Fi сети
- JSON API: `/api/status`, `/api/metrics` (в metrics есть `history` и `panel` — PID, RAM, uptime процесса панели)
- **Отдельные страницы** (без вкладок): `/` — мониторинг, `/remote` — управление, `/chat` — агент, `/settings` — конфиг и логи

## Требования

- Linux с systemd
- Python 3.10+
- `curl` (для проверки при установке)

## Smoke-тест

Проверка, что запущенная панель отвечает (после `systemctl start` или `./install.sh`):

```bash
python3 tests/smoke_test.py
# другой порт: PANEL_PORT=9000 python3 tests/smoke_test.py
# удалённый хост: PANEL_URL=http://192.168.0.10:8765 python3 tests/smoke_test.py
```

Код выхода `0` — всё ок, `1` — есть ошибки.

## Установка

```bash
git clone https://github.com/rkfsociety/nout-panel.git
cd nout-panel
chmod +x install.sh app.py
sudo ./install.sh
# Сначала настроить порт и интервал без запуска:
sudo ./install.sh --no-start
```

Скрипт создаст **локальный** `config.local.env` (не в Git) и зарегистрирует сервис `nout-panel`. Порт (`PANEL_PORT`), интервал метрик (`PANEL_METRICS_INTERVAL`) и путь к логам (`PANEL_LOG_FILE`) меняются в этом файле без правки кода.

Откройте в браузере с другого ПК в той же сети:

```text
http://<IP-ноута>:8765/
```

IP покажет вывод `install.sh` или `hostname -I` на ноуте.

## Страницы

| URL | Содержимое |
|-----|------------|
| `/` | CPU, RAM, диски, графики |
| `/remote` | Терминал, файлы, питание, скриншот |
| `/chat` | Чат с Cursor Agent |
| `/settings` | Конфиг, логи, перезапуск панели |

Сверху на каждой странице — простые ссылки (не вкладки).

## Надёжность

- **systemd**: `Restart=on-failure` — сервис поднимается после сбоя
- **Логи**: `~/.nout-panel/log.txt` (ротация 1–5 МБ, по умолчанию 2 МБ × 3 архива)
- **Датчики**: нет батареи/температуры на ПК — в UI показывается **N/A**, панель не падает

## Управление и чат

Пароль не используется — **не открывайте порт в интернет**. Скриншот: `sudo apt install grim scrot` при необходимости.

С телефона: раздел **Чат** (`/chat`) — на ноуте задачи выполняет **Cursor Agent** (CLI).

**Один раз на ноуте** (SSH или локально):

```bash
cursor agent login
```

Проверка: `cursor agent status` → logged in.

Откройте `http://<IP-ноута>:8765/chat`, напишите, например: «обнови nout-panel и перезапусти сервис».

Это **не тот же текстовый чат**, что в окне Cursor на ПК, но тот же агент с инструментами на ноуте. Папка задаётся `PANEL_AGENT_WORKSPACE` (по умолчанию каталог над `nout-panel`, обычно `~/github-pc`).

## Приватность

Личные данные (IP, пользователь, пути) **не хранятся в репозитории**. См. [SECURITY.md](SECURITY.md).

| В Git | Только локально |
|-------|-----------------|
| Код панели | `config.local.env` |
| `config.example.env` | `/etc/nout-panel/env` |

Перед `git push` проверьте:

```bash
git status
git diff
```

## Лицензия

MIT — см. [LICENSE](LICENSE).
