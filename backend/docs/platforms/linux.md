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

## 3. Dirección IPv4 LAN

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

Docker Compose publica el gateway HTTPS en el puerto 8443 del host. Si tu
firewall o la red institucional filtran conexiones, permite TCP 8443 solo
desde la red local.
Ten presente que Docker administra reglas propias de iptables; consulta la
[documentación de firewall de Docker](https://docs.docker.com/engine/network/packet-filtering-firewalls/)
antes de asumir que una regla de UFW controla un puerto publicado.

Continúa con la configuración común de
[HTTPS desde el teléfono](../../README.md#acceso-desde-un-teléfono-https-en-la-red-local).

## 6. mDNS opcional

La dirección IP funciona sin mDNS. mDNS permite que los equipos del mismo
enlace local resuelvan nombres terminados en `.local` mediante mensajes
multicast, sin un servidor DNS central. Avahi es la implementación habitual en
Linux; Debian y Ubuntu pueden publicar el hostname así:

```console
sudo apt install avahi-daemon avahi-utils
sudo systemctl enable --now avahi-daemon
hostnamectl --static
```

Si el hostname es `mi-pc`, valida `mi-pc.local`:

```console
avahi-resolve -n mi-pc.local
```

Genera nuevamente el certificado usando ese nombre y úsalo también en
`.env.local`. El [estándar de mDNS](https://www.rfc-editor.org/rfc/rfc6762)
reserva `.local` y UDP 5353 para este mecanismo. Algunas redes bloquean ese
tráfico multicast; en ese caso vuelve a la dirección IPv4.

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
