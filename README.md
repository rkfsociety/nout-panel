# Nout Panel

Лёгкая веб-панель для домашнего ноута на Linux: CPU, RAM, диски, температура. Обновление ~1 с в браузере. Без Docker, только Python 3 из коробки.

## Возможности

- Мониторинг загрузки CPU, памяти, load average
- Состояние смонтированных дисков
- Температуры (если доступны в `/sys/class/thermal`)
- JSON API: `/api/status`, `/api/metrics`

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
```

Скрипт создаст **локальный** `config.local.env` (не в Git) и зарегистрирует сервис `nout-panel`.

Откройте в браузере с другого ПК в той же сети:

```text
http://<IP-ноута>:8765/
```

IP покажет вывод `install.sh` или `hostname -I` на ноуте.

## Управление

```bash
sudo systemctl status nout-panel
sudo systemctl restart nout-panel
journalctl -u nout-panel -f
```

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
