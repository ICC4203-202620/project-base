# Desarrollo local en Linux

Esta guía llega al mismo resultado que las guías de
[macOS](macos.md) y [Windows](windows.md). Los comandos del backend, pruebas y
migraciones están en el [README principal](../../README.md).

El objetivo es preparar cuatro piezas: Docker Compose para ejecutar los
servicios, una CA local de `mkcert`, una dirección que el teléfono pueda
alcanzar y un certificado emitido para esa dirección. Antes de continuar,
revisa el [modelo de CA, X.509 y confianza](../../README.md#conceptos-que-conviene-recordar).

## 1. Docker y Compose

Puedes usar Docker Desktop o Docker Engine con el plugin de Compose. Docker
ejecuta cada servicio en un contenedor; Compose lee `docker-compose.yml` y
coordina la API, PostgreSQL, su red y sus volúmenes. Sigue la guía oficial
correspondiente a tu distribución:

- [Instalar Docker Engine](https://docs.docker.com/engine/install/)
- [Instalar el plugin de Docker Compose](https://docs.docker.com/compose/install/linux/)

Comprueba la instalación sin anteponer `sudo`. Si tu instalación requiere
`sudo`, completa primero los pasos de postinstalación de Docker para administrar
el daemon como usuario no privilegiado.

```console
docker version
docker compose version
```

## 2. mkcert y la CA local

`mkcert` automatiza una infraestructura de clave pública pequeña para
desarrollo. Instala primero las herramientas NSS que le permiten registrar la
CA en almacenes de confianza usados por navegadores. El paquete cambia según
la distribución:

```console
# Debian y Ubuntu
sudo apt install libnss3-tools

# Fedora y derivados
sudo dnf install nss-tools

# Arch Linux y derivados
sudo pacman -S nss mkcert
```

En las distribuciones donde `mkcert` no venga empaquetado, usa el binario
publicado o las instrucciones del
[proyecto oficial](https://github.com/FiloSottile/mkcert#linux). Luego instala
la CA solo en tu computador de desarrollo:

```console
mkcert -install
```

Este comando crea la CA si todavía no existe e instala su certificado público
en los almacenes compatibles del computador. Aún no genera el certificado del
backend. Consulta los almacenes soportados y las alternativas de instalación
en la [documentación oficial de `mkcert`](https://github.com/FiloSottile/mkcert#supported-root-stores).

## 3. Elige el host de acceso

Antes de generar el certificado, elige la dirección que escribirás desde el
teléfono. La IPv4 LAN es el camino recomendado. mDNS es una alternativa
opcional; puedes incluir ambos valores en el mismo certificado.

### IPv4 LAN recomendada

Muestra las interfaces activas:

```console
ip -brief address
```

Usa la dirección IPv4 de la interfaz Wi-Fi o Ethernet conectada a la misma red
que el teléfono. Las redes privadas suelen usar los bloques `10.0.0.0/8`,
`172.16.0.0/12` o `192.168.0.0/16`, reservados por el
[RFC 1918](https://www.rfc-editor.org/rfc/rfc1918). No uses `127.0.0.1`, que es
la interfaz de retorno del propio computador, ni direcciones internas de
Docker o de una VPN: el teléfono normalmente no puede alcanzarlas.

### mDNS opcional

mDNS permite que los equipos del mismo enlace local resuelvan nombres
terminados en `.local` mediante multicast, sin un servidor DNS central. Avahi
es la implementación habitual en Linux; Debian y Ubuntu pueden publicar el
hostname así:

```console
sudo apt install avahi-daemon avahi-utils
sudo systemctl enable --now avahi-daemon
hostnamectl --static
```

Si el hostname es `mi-pc`, valida el nombre antes de usarlo:

```console
avahi-resolve -n mi-pc.local
```

Confirma también que `mi-pc.local` resuelva desde el teléfono. Algunas redes
institucionales bloquean multicast o aíslan a sus clientes; en ese caso usa la
IPv4. El [estándar de mDNS](https://www.rfc-editor.org/rfc/rfc6762) reserva
`.local` y UDP 5353 para este mecanismo.

## 4. Certificado local

Desde la raíz del repositorio, pasa al helper todos los hosts que realmente
usarás. Para trabajar sólo con la IPv4:

```console
./scripts/create-local-certificate.sh 192.168.1.40
```

Para aceptar tanto la IPv4 como mDNS:

```console
./scripts/create-local-certificate.sh 192.168.1.40 mi-pc.local
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

El perfil `.env.local` publica el gateway HTTPS en el puerto 5173 del host. Si
tu firewall o la red institucional filtran conexiones, permite TCP 5173 solo
desde la red local.
Ten presente que Docker administra reglas propias de iptables; consulta la
[documentación de firewall de Docker](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
antes de asumir que una regla de UFW controla un puerto publicado.

## 6. Verificación

Prueba con validación TLS completa usando un host incluido en el certificado:

```console
curl https://192.168.1.40:5173/healthz
# Alternativa, sólo si incluiste y validaste mDNS:
curl https://mi-pc.local:5173/healthz
```

Debes obtener `{"status":"ok"}`. Si el computador responde pero el teléfono
no, revisa el firewall, la red Wi-Fi y la confianza de `rootCA.pem` en el
dispositivo. Si `curl` rechaza el certificado, `curl -k` puede servir como
diagnóstico de conectividad, pero `-k` deshabilita la verificación TLS y no debe
considerarse una solución.

Continúa con la explicación común de
[HTTPS local y acceso desde un teléfono](../../README.md#https-local-y-acceso-desde-un-teléfono).
