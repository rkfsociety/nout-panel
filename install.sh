#!/bin/bash
# Установка веб-панели: генерирует systemd-юнит из шаблона (без личных данных в Git)
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
	echo "Запустите: sudo ./install.sh" >&2
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_LOCAL="${SCRIPT_DIR}/config.local.env"
CONFIG_EXAMPLE="${SCRIPT_DIR}/config.example.env"

# Локальный конфиг не коммитится — создаём при первой установке
if [[ ! -f "${CONFIG_LOCAL}" ]]; then
	INSTALL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "")}"
	if [[ -z "${INSTALL_USER}" ]]; then
		echo "Не удалось определить пользователя. Создайте config.local.env вручную из config.example.env" >&2
		exit 1
	fi
	cat >"${CONFIG_LOCAL}" <<EOF
# Локальная конфигурация (не для Git)
PANEL_USER=${INSTALL_USER}
INSTALL_DIR=${SCRIPT_DIR}
PANEL_PORT=8765
EOF
	chown "${INSTALL_USER}:${INSTALL_USER}" "${CONFIG_LOCAL}"
	chmod 600 "${CONFIG_LOCAL}"
	echo "Создан ${CONFIG_LOCAL}"
fi

# shellcheck source=/dev/null
source "${CONFIG_LOCAL}"

chmod +x "${INSTALL_DIR}/app.py"

# Лог-файл для отладки (доступ только пользователю панели)
LOG_FILE="/var/log/nout-panel.log"
touch "${LOG_FILE}"
chown "${PANEL_USER}:${PANEL_USER}" "${LOG_FILE}"
chmod 640 "${LOG_FILE}"

# Копия настроек для systemd (без секретов)
install -d -m 0755 /etc/nout-panel
install -m 0644 "${CONFIG_LOCAL}" /etc/nout-panel/env

TEMPLATE="${SCRIPT_DIR}/systemd/nout-panel.service.template"
UNIT="/etc/systemd/system/nout-panel.service"
sed -e "s|@PANEL_USER@|${PANEL_USER}|g" \
	-e "s|@INSTALL_DIR@|${INSTALL_DIR}|g" \
	"${TEMPLATE}" >"${UNIT}"
chmod 0644 "${UNIT}"

systemctl daemon-reload
systemctl enable nout-panel.service
systemctl restart nout-panel.service

sleep 0.5
PORT="${PANEL_PORT:-8765}"
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
echo ""
echo "Логи: tail -f ${LOG_FILE}"
