#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Uso: $0 <hostname-mDNS.local>" >&2
  exit 1
fi

host_name="$1"
case "$host_name" in
  *.local) ;;
  *)
    echo "El hostname debe terminar en .local (por ejemplo, mi-equipo.local)." >&2
    exit 1
    ;;
esac

if ! command -v mkcert >/dev/null 2>&1; then
  echo "No se encontró mkcert. Instálalo y ejecuta 'mkcert -install' primero." >&2
  exit 1
fi

mkdir -p certs
mkcert +  -cert-file certs/local.pem +  -key-file certs/local-key.pem +  "$host_name" +  localhost +  127.0.0.1 +  ::1

echo "Certificado creado para https://$host_name:8000"
