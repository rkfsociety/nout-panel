# Nout Panel

Лёгкая веб-панель для домашнего ноута на Linux: CPU, RAM, диски, температура. Обновление ~1 с в браузере. Без Docker, только Python 3 из коробки.

## Возможности

- Мониторинг загрузки CPU, памяти, load average
- **Графики истории** (~10 мин) — Chart.js, тёмная тема
- Состояние смонтированных дисков
- Температуры (если доступны в `/sys/class/thermal`)
- Удобно с телефона в той же Wi‑Fi сети
- JSON API: `/api/status`, `/api/metrics` (в metrics есть поле `history`)
- **Удалённое управление** (`/remote`): терминал, файлы в `~/` и `/mnt/`, питание, скриншот — **без пароля**, только для доверенной LAN

## Требования

- Linux с systemd
- Python 3.10+
- `curl` (для проверки при установке)

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

## Управление

```bash
sudo systemctl status nout-panel
sudo systemctl restart nout-panel
# Логи (файл, не journal; путь — PANEL_LOG_FILE в config.local.env):
tail -f ~/.nout-panel/log.txt
```

После обновления кода переустановите юнит: `sudo ./install.sh` (создаёт каталог логов, `Restart=on-failure`).

## Надёжность

- **systemd**: `Restart=on-failure` — сервис поднимается после сбоя
- **Логи**: `~/.nout-panel/log.txt` (ротация 1–5 МБ, по умолчанию 2 МБ × 3 архива)
- **Датчики**: нет батареи/температуры на ПК — в UI показывается **N/A**, панель не падает

## Управление системой (`/remote`)

| Функция | Описание |
|---------|----------|
| Терминал | xterm.js + shell на ноуте |
| Файлы | Просмотр, загрузка, удаление в `PANEL_FILE_ROOTS` |
| Питание | Сон / перезагрузка / выключение (подтверждение) |
| Экран | Скриншот по кнопке (`grim`, `scrot`, …) |

Пароль не используется — **не открывайте порт в интернет**. Скриншот: `sudo apt install grim scrot` при необходимости.

## Чат с агентом (`/chat`)

С телефона можно писать задачи — на ноуте их выполняет **Cursor Agent** (CLI), в той же папке, что и ваши репозитории.

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
