#!/bin/sh
set -eu

if [ "$#" -lt 1 ]; then
  echo "Uso: $0 <hostname-o-ip-lan> [hostname-o-ip-lan ...]" >&2
  exit 1
fi

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
  "$@" localhost 127.0.0.1 ::1

printf "Certificado creado para"
for host_or_ip in "$@"; do
  printf " https://%s:5173" "$host_or_ip"
done
printf " https://localhost:5173\n"
