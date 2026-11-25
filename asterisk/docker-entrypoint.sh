#!/bin/sh
# Renders the configuration templates into /etc/asterisk, then starts Asterisk.
#
# Asterisk configuration files cannot read environment variables, so the values that differ per
# deployment (addresses, ports, secrets) are placeholders in the templates.
set -eu

: "${EXTERNAL_IP:?EXTERNAL_IP is required}"
: "${ASTERISK_SIP_PORT:?ASTERISK_SIP_PORT is required}"
: "${SIP_PASSWORD:?SIP_PASSWORD is required}"
: "${BOT_TOKEN:?BOT_TOKEN is required}"
: "${ASTERISK_BOT_WS_URL:?ASTERISK_BOT_WS_URL is required}"

# Only these are substituted: the dialplan has its own ${VARIABLES}, which must stay as they are.
PLACEHOLDERS='${EXTERNAL_IP} ${ASTERISK_SIP_PORT} ${SIP_PASSWORD} ${BOT_TOKEN} ${ASTERISK_BOT_WS_URL}'

umask 077  # the rendered files hold secrets
for template in /etc/asterisk/templates/*.conf; do
    envsubst "$PLACEHOLDERS" < "$template" > "/etc/asterisk/$(basename "$template")"
done

exec "$@"
