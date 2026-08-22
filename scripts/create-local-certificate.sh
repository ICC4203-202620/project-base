#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Uso: $0 <hostname-o-ip-lan>" >&2
  exit 1
fi

host_or_ip="$1"

if ! command -v mkcert >/dev/null 2>&1; then
  echo "No se encontró mkcert. Instálalo y ejecuta 'mkcert -install' primero." >&2
  exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(dirname -- "$script_dir")
certificate_dir="$repository_root/certs"

mkdir -p "$certificate_dir"
mkcert \
  -cert-file "$certificate_dir/local.pem" \
  -key-file "$certificate_dir/local-key.pem" \
  "$host_or_ip" localhost 127.0.0.1 ::1

echo "Certificado creado para https://$host_or_ip:8000"
