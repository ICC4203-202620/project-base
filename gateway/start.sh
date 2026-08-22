#!/bin/sh
set -eu

if [ "${LOCAL_TLS:-false}" = "true" ]; then
  if [ ! -r /certs/local.pem ] || [ ! -r /certs/local-key.pem ]; then
    echo "LOCAL_TLS=true requiere certs/local.pem y certs/local-key.pem" >&2
    exit 1
  fi
  configuration=/etc/nginx/configurations/https.conf
else
  configuration=/etc/nginx/configurations/http.conf
fi

cp "$configuration" /etc/nginx/conf.d/default.conf
exec nginx -g "daemon off;"
