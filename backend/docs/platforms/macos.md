# Desarrollo local en macOS

Esta guía llega al mismo resultado que las guías de
[Linux](linux.md) y [Windows](windows.md). Los comandos del backend, pruebas y
migraciones están en el [README principal](../../README.md).

El objetivo es preparar cuatro piezas: Docker Compose para ejecutar los
servicios, una CA local de `mkcert`, una dirección que el teléfono pueda
alcanzar y un certificado emitido para esa dirección. Antes de continuar,
revisa el [modelo de CA, X.509 y confianza](../../README.md#conceptos-que-conviene-recordar).

## 1. Docker y Compose

Instala [Docker Desktop para Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
y abre la aplicación antes de trabajar con el repositorio. Docker ejecuta cada
servicio en un contenedor; Compose lee `docker-compose.yml` y coordina la API,
PostgreSQL, su red y sus volúmenes.

```console
docker version
docker compose version
```

## 2. mkcert y la CA local

Con Homebrew:

```console
brew install mkcert
brew install nss
mkcert -install
```

`nss` solo es necesario para que Firefox use automáticamente la CA local. Si
no usas Homebrew, sigue las alternativas del
[proyecto oficial](https://github.com/FiloSottile/mkcert#macos).

`mkcert -install` crea la CA si todavía no existe e instala su certificado
público en los almacenes de confianza compatibles del Mac. Aún no genera el
certificado del backend. La CA es solo para desarrollo local.

## 3. Dirección IPv4 LAN

Para una conexión Wi-Fi típica:

```console
ipconfig getifaddr en0
```

Si no entrega una dirección, revisa **Configuración del Sistema → Red** o
identifica primero el nombre de la interfaz activa:

```console
networksetup -listallhardwareports
```

Usa la dirección IPv4 de la interfaz conectada a la misma red que el teléfono.
Las redes privadas suelen usar los bloques `10.0.0.0/8`, `172.16.0.0/12` o
`192.168.0.0/16`, reservados por el
[RFC 1918](https://www.rfc-editor.org/rfc/rfc1918). No uses `127.0.0.1`, que es
la interfaz de retorno del propio Mac, ni una interfaz VPN o una dirección
interna de Docker: el teléfono normalmente no puede alcanzarlas.

## 4. Certificado local

Desde la raíz del repositorio, reemplaza la dirección del ejemplo:

```console
./scripts/create-local-certificate.sh 192.168.1.40
```

El helper pide a la CA local que firme `certs/local.pem` y guarda su clave
privada en `certs/local-key.pem`. El certificado incluye la IP indicada y,
para seguir permitiendo pruebas en el computador, también `localhost`,
`127.0.0.1` y `::1`.

## 5. Red y firewall

Docker Desktop publica el gateway HTTPS en el puerto 8443 de macOS. Si aparece
una solicitud del firewall para permitir conexiones entrantes, autoriza Docker
únicamente en redes de confianza. En redes institucionales puede existir
aislamiento entre clientes aunque el firewall local permita la conexión.

Continúa con la configuración común de
[HTTPS desde el teléfono](../../README.md#acceso-desde-un-teléfono-https-en-la-red-local).

## 6. mDNS opcional

La dirección IP funciona sin mDNS. mDNS permite que los equipos del mismo
enlace local resuelvan nombres terminados en `.local` mediante mensajes
multicast, sin un servidor DNS central. La implementación de Apple se llama
Bonjour y macOS normalmente publica un nombre local. Consúltalo con:

```console
scutil --get LocalHostName
```

Si devuelve `mi-mac`, prueba `mi-mac.local`. Genera nuevamente el certificado
con ese nombre y úsalo también en `.env.local`:

```console
./scripts/create-local-certificate.sh mi-mac.local
```

El [estándar de mDNS](https://www.rfc-editor.org/rfc/rfc6762) reserva `.local`
y UDP 5353 para este mecanismo. Si la red bloquea ese tráfico multicast,
vuelve a la dirección IPv4 LAN.

## 7. Verificación

Después de iniciar Compose con la configuración HTTPS del README, prueba primero
con validación completa:

```console
curl https://192.168.1.40:8443/healthz
```

Debes obtener `{"status":"ok"}`. Si el computador responde pero el teléfono
no, revisa el firewall, la red Wi-Fi y la confianza de `rootCA.pem` en el
dispositivo. Si `curl` rechaza el certificado, `curl -k` puede servir como
diagnóstico de conectividad, pero `-k` deshabilita la verificación TLS y no debe
considerarse una solución.
