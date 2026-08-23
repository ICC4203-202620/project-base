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
# Opcional: permite a mkcert instalar también en almacenes NSS
brew install nss
mkcert -install
```

Las versiones actuales de Firefox pueden usar la CA del sistema. `nss` sigue
siendo útil como alternativa porque permite que `mkcert` instale la CA
directamente en los almacenes NSS de perfiles compatibles. Si no usas Homebrew,
sigue las alternativas del
[proyecto oficial](https://github.com/FiloSottile/mkcert#macos).

`mkcert -install` crea la CA si todavía no existe e instala su certificado
público en los almacenes de confianza compatibles del Mac. Aún no genera el
certificado del backend. La CA es solo para desarrollo local.

## 3. Elige el host de acceso

Antes de generar el certificado, elige la dirección que escribirás desde el
teléfono. La IPv4 LAN es el camino recomendado. mDNS es una alternativa
opcional; puedes incluir ambos valores en el mismo certificado.

### IPv4 LAN recomendada

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

### mDNS opcional

mDNS permite que los equipos del mismo enlace local resuelvan nombres
terminados en `.local` mediante multicast, sin un servidor DNS central. La
implementación de Apple se llama Bonjour y macOS normalmente publica un nombre
local. Consúltalo con:

```console
scutil --get LocalHostName
```

Si devuelve `mi-mac`, verifica `mi-mac.local` desde el Mac y el teléfono antes
de usarlo. Algunas redes bloquean multicast o aíslan a sus clientes; en ese
caso usa la IPv4 LAN. El
[estándar de mDNS](https://www.rfc-editor.org/rfc/rfc6762) reserva `.local` y
UDP 5353 para este mecanismo.

## 4. Certificado local

Desde la raíz del repositorio, pasa al helper todos los hosts que realmente
usarás. Para trabajar sólo con la IPv4:

```console
./scripts/create-local-certificate.sh 192.168.1.40
```

Para aceptar tanto la IPv4 como mDNS:

```console
./scripts/create-local-certificate.sh 192.168.1.40 mi-mac.local
```

El helper pide a la CA local que firme `certs/local.pem` y guarda su clave
privada en `certs/local-key.pem`. El certificado incluye todos los valores
indicados y, para seguir permitiendo pruebas en el computador, también
`localhost`, `127.0.0.1` y `::1`.

Los hosts pertenecen al certificado y a las URLs de acceso; **no se agregan a
`.env.local`**. Si regeneras el certificado mientras Compose está activo,
reinicia nginx para que vuelva a cargarlo:

```console
docker compose --env-file .env.local restart gateway
```

## 5. Compose, red y firewall

Crea el perfil TLS. Compose no lee `.env.local` automáticamente, por lo que
debes indicar `--env-file` cada vez que levantes esta configuración:

```console
cp .env.local.example .env.local
docker compose --env-file .env.local up --build
```

El perfil `.env.local` publica el gateway HTTPS en el puerto 5173 de macOS. Si
aparece una solicitud del firewall para conexiones entrantes, autoriza Docker
únicamente en redes de confianza. En redes institucionales puede existir
aislamiento entre clientes aunque el firewall local permita la conexión.

## 6. Verificación

Prueba con validación TLS completa usando un host incluido en el certificado:

```console
curl https://192.168.1.40:5173/healthz
# Alternativa, sólo si incluiste y validaste mDNS:
curl https://mi-mac.local:5173/healthz
```

Debes obtener `{"status":"ok"}`. Si el computador responde pero el teléfono
no, revisa el firewall, la red Wi-Fi y la confianza de `rootCA.pem` en el
dispositivo. Si `curl` rechaza el certificado, `curl -k` puede servir como
diagnóstico de conectividad, pero `-k` deshabilita la verificación TLS y no debe
considerarse una solución.

Continúa con la explicación común de
[HTTPS local y acceso desde un teléfono](../../README.md#https-local-y-acceso-desde-un-teléfono).
