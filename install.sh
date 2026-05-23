#!/bin/bash
# Установка веб-панели: генерирует systemd-юнит из шаблона (без личных данных в Git)
set -euo pipefail

# Флаг: только установить юнит и конфиг, без запуска сервиса
NO_START=0

usage() {
	echo "Использование: sudo ./install.sh [--no-start]" >&2
	echo "  --no-start  настроить config/local.env и не запускать сервис" >&2
}

for arg in "$@"; do
	case "${arg}" in
	--no-start) NO_START=1 ;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		echo "Неизвестный аргумент: ${arg}" >&2
		usage
		exit 1
		;;
	esac
done

if [[ "${EUID}" -ne 0 ]]; then
	echo "Запустите: sudo ./install.sh" >&2
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/config"
CONFIG_LOCAL="${CONFIG_DIR}/local.env"
CONFIG_EXAMPLE="${CONFIG_DIR}/example.env"
LEGACY_CONFIG="${SCRIPT_DIR}/config.local.env"

mkdir -p "${CONFIG_DIR}"
# Миграция со старого пути в корне
if [[ -f "${LEGACY_CONFIG}" && ! -f "${CONFIG_LOCAL}" ]]; then
	mv "${LEGACY_CONFIG}" "${CONFIG_LOCAL}"
	echo "Перенесён ${LEGACY_CONFIG} → ${CONFIG_LOCAL}"
fi

# Локальный конфиг не коммитится — создаём при первой установке
if [[ ! -f "${CONFIG_LOCAL}" ]]; then
	INSTALL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "")}"
	if [[ -z "${INSTALL_USER}" ]]; then
		echo "Не удалось определить пользователя. Создайте config/local.env из config/example.env" >&2
		exit 1
	fi
	INSTALL_HOME="$(getent passwd "${INSTALL_USER}" | cut -d: -f6)"
	INSTALL_HOME="${INSTALL_HOME:-/home/${INSTALL_USER}}"
	cat >"${CONFIG_LOCAL}" <<EOF
# Локальная конфигурация (не для Git)
PANEL_USER=${INSTALL_USER}
INSTALL_DIR=${SCRIPT_DIR}
PANEL_PORT=8765
PANEL_METRICS_INTERVAL=0.5
PANEL_LOG_FILE=${INSTALL_HOME}/.nout-panel/log.txt
PANEL_LOG_MAX_MB=2
PANEL_FILE_ROOTS=${INSTALL_HOME}:/mnt
PANEL_AGENT_WORKSPACE=$(dirname "${SCRIPT_DIR}")
EOF
	chown "${INSTALL_USER}:${INSTALL_USER}" "${CONFIG_LOCAL}"
	chmod 600 "${CONFIG_LOCAL}"
	echo "Создан ${CONFIG_LOCAL}"
fi

# shellcheck source=/dev/null
source "${CONFIG_LOCAL}"

chmod +x "${INSTALL_DIR}/app.py"

# Лог-файл с ротацией (путь и размер — в config/local.env)
if [[ -z "${PANEL_LOG_FILE:-}" ]]; then
	PANEL_HOME="$(getent passwd "${PANEL_USER}" | cut -d: -f6)"
	LOG_FILE="${PANEL_HOME:-/home/${PANEL_USER}}/.nout-panel/log.txt"
else
	LOG_FILE="${PANEL_LOG_FILE}"
fi
LOG_DIR="$(dirname "${LOG_FILE}")"
mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"
chown -R "${PANEL_USER}:${PANEL_USER}" "${LOG_DIR}"
chmod 750 "${LOG_DIR}"
chmod 640 "${LOG_FILE}"

# Копия настроек для systemd (без секретов)
install -d -m 0755 /etc/nout-panel
install -m 0644 "${CONFIG_LOCAL}" /etc/nout-panel/env

# Перезапуск панели из веб-UI (sudo без пароля)
SUDOERS_FILE="/etc/sudoers.d/nout-panel-${PANEL_USER}"
cat >"${SUDOERS_FILE}" <<EOF
# nout-panel: перезапуск сервиса из веб-UI (${PANEL_USER})
${PANEL_USER} ALL=(root) NOPASSWD: /usr/bin/systemctl restart nout-panel.service, /usr/bin/systemctl restart nout-panel
${PANEL_USER} ALL=(root) NOPASSWD: /usr/bin/cp ${INSTALL_DIR}/config/local.env /etc/nout-panel/env
EOF
chmod 0440 "${SUDOERS_FILE}"
if ! visudo -cf "${SUDOERS_FILE}" >/dev/null 2>&1; then
	echo "Ошибка: неверный ${SUDOERS_FILE}" >&2
	rm -f "${SUDOERS_FILE}"
	exit 1
fi

TEMPLATE="${SCRIPT_DIR}/systemd/nout-panel.service.template"
UNIT="/etc/systemd/system/nout-panel.service"
sed -e "s|@PANEL_USER@|${PANEL_USER}|g" \
	-e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
	"${TEMPLATE}" >"${UNIT}"
chmod 0644 "${UNIT}"

systemctl daemon-reload
systemctl enable nout-panel.service

# Авто-перезапуск при изменении /etc/nout-panel/env
install -m 0644 "${SCRIPT_DIR}/systemd/nout-panel-config.path" /etc/systemd/system/nout-panel-config.path
install -m 0644 "${SCRIPT_DIR}/systemd/nout-panel-config.service" /etc/systemd/system/nout-panel-config.service
systemctl enable nout-panel-config.path
systemctl start nout-panel-config.path 2>/dev/null || true

PORT="${PANEL_PORT:-8765}"

# Подсказка: как применить правки config/local.env
config_hint() {
	echo ""
	echo "Конфиг: ${CONFIG_LOCAL}  →  /etc/nout-panel/env"
	echo "После правки:"
	echo "  sudo cp ${CONFIG_LOCAL} /etc/nout-panel/env"
	echo "  (сервис перезапустится автоматически)"
	echo "Или одной командой: sudo ./install.sh"
}

if [[ "${NO_START}" -eq 1 ]]; then
	echo ""
	echo "Установка завершена (--no-start). Сервис не запущен."
	echo "Отредактируйте ${CONFIG_LOCAL}, затем:"
	echo "  sudo cp ${CONFIG_LOCAL} /etc/nout-panel/env"
	echo "  sudo systemctl start nout-panel"
	config_hint
	echo "Логи после запуска: tail -f ${LOG_FILE}"
	exit 0
fi

systemctl restart nout-panel.service

sleep 0.5
if curl -fsS "http://127.0.0.1:${PORT}/api/status" >/dev/null; then
	echo "Панель отвечает локально."
else
	echo "Предупреждение: проверка не прошла — tail -f ${LOG_FILE}" >&2
	exit 1
fi

IP="$(hostname -I | awk '{print $1}')"
echo ""
echo "Откройте в браузере (LAN):"
echo "  http://${IP}:${PORT}/"
echo "  http://${IP}:${PORT}/remote  — терминал, файлы, питание"
echo "  http://${IP}:${PORT}/chat     — чат с Cursor Agent"
echo ""
echo "Чат: один раз на ноуте выполните: cursor agent login"
echo "Логи: tail -f ${LOG_FILE}"
config_hint
