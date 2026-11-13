#!/bin/sh
# Builds /etc/nginx/conf.d/default.conf for TLS_MODE=off|selfsigned|provided.
set -eu

SRC=/opt/redshadow/nginx
DEST=/etc/nginx/conf.d/default.conf
MODE="${TLS_MODE:-selfsigned}"

case "$MODE" in
    off)
        cat "$SRC/base.inc" "$SRC/off.conf" > "$DEST"
        echo "tls-mode: off (plain HTTP, no HSTS)"
        exit 0
        ;;
    selfsigned) CERT=/run/secrets/tls/tls.crt; KEY=/run/secrets/tls/tls.key ;;
    provided)   CERT=/etc/nginx/tls/tls.crt;   KEY=/etc/nginx/tls/tls.key ;;
    *) echo "tls-mode: invalid TLS_MODE '$MODE' (use off|selfsigned|provided)" >&2; exit 1 ;;
esac

if [ ! -s "$CERT" ] || [ ! -s "$KEY" ]; then
    echo "tls-mode: $MODE needs $CERT and $KEY" >&2
    exit 1
fi

SUFFIX=""
[ "${HTTPS_PORT:-443}" != "443" ] && SUFFIX=":${HTTPS_PORT}"

{
    cat "$SRC/base.inc"
    sed -e "s|__CERT__|$CERT|g" -e "s|__KEY__|$KEY|g" -e "s|__PORT_SUFFIX__|$SUFFIX|g" "$SRC/tls.conf"
} > "$DEST"
echo "tls-mode: $MODE"
