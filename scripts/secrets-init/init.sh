#!/bin/sh
# Generates missing secrets into the `secrets` volume. Idempotent: never overwrites.
set -eu

DIR=/secrets
umask 022

gen() {
    f="$DIR/$1"
    if [ ! -s "$f" ]; then
        openssl rand -hex 32 > "$f"
        chmod 0444 "$f"
        echo "generated $1"
    fi
}

# Fernet key for MFA secrets at rest: urlsafe base64 of 32 random bytes.
if [ ! -s "$DIR/mfa_key" ]; then
    openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n' > "$DIR/mfa_key"
    chmod 0444 "$DIR/mfa_key"
    echo "generated mfa_key"
fi

for name in secret_key db_admin_password db_owner_password db_app_password redis_password; do
    gen "$name"
done

if [ "${TLS_MODE:-selfsigned}" = "selfsigned" ]; then
    mkdir -p "$DIR/tls"
    if [ ! -s "$DIR/tls/tls.crt" ] || [ ! -s "$DIR/tls/tls.key" ]; then
        HOST="${TLS_HOSTNAME:-localhost}"
        SAN="DNS:localhost,DNS:${HOST},IP:127.0.0.1"
        [ -n "${TLS_EXTRA_SAN:-}" ] && SAN="${SAN},${TLS_EXTRA_SAN}"
        openssl req -x509 -newkey rsa:3072 -sha256 -days 825 -nodes \
            -keyout "$DIR/tls/tls.key" -out "$DIR/tls/tls.crt" \
            -subj "/CN=${HOST}/O=RedShadow" -addext "subjectAltName=${SAN}" 2>/dev/null
        # Readable by the unprivileged nginx user; the volume is internal-only.
        chmod 0444 "$DIR/tls/tls.key" "$DIR/tls/tls.crt"
        echo "generated self-signed certificate for ${SAN}"
    fi
fi
echo "secrets ready"
