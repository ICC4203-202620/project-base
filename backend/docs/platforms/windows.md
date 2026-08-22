# Desarrollo local en Windows

Esta guía llega al mismo resultado que las guías de
[Linux](linux.md) y [macOS](macos.md). Los comandos del backend, pruebas y
migraciones están en el [README principal](../../README.md).

La ruta principal usa PowerShell y Docker Desktop. WSL es compatible, pero no
es obligatorio para ejecutar el backend.

El objetivo es preparar cuatro piezas: Docker Compose para ejecutar los
servicios, una CA local de `mkcert`, una dirección que el teléfono pueda
alcanzar y un certificado emitido para esa dirección. Antes de continuar,
revisa el [modelo de CA, X.509 y confianza](../../README.md#conceptos-que-conviene-recordar).

## 1. Docker y Compose

Instala [Docker Desktop para Windows](https://docs.docker.com/desktop/setup/install/windows-install/)
con el backend WSL 2 recomendado por Docker. Abre Docker Desktop y comprueba la
instalación desde PowerShell. Docker ejecuta cada servicio en un contenedor;
Compose lee `docker-compose.yml` y coordina la API, PostgreSQL, su red y sus
volúmenes:

```powershell
docker version
docker compose version
```

## 2. mkcert y la CA local

Instala `mkcert` usando Chocolatey o Scoop:

```powershell
# Una de estas dos alternativas
choco install mkcert

scoop bucket add extras
scoop install mkcert
```

Las alternativas se mantienen en el
[proyecto oficial](https://github.com/FiloSottile/mkcert#windows). Instala la CA
en el almacén de certificados de tu usuario:

```powershell
mkcert -install
```

Windows puede solicitar confirmación para confiar la nueva CA.

`mkcert -install` crea la CA si todavía no existe e instala su certificado
público en el almacén de confianza del usuario. Aún no genera el certificado
del backend. La CA es solo para desarrollo local.

## 3. Dirección IPv4 LAN

Desde PowerShell:

```powershell
ipconfig
```

Busca **Dirección IPv4** en el adaptador Wi-Fi o Ethernet conectado a la misma
red que el teléfono. Las redes privadas suelen usar los bloques `10.0.0.0/8`,
`172.16.0.0/12` o `192.168.0.0/16`, reservados por el
[RFC 1918](https://www.rfc-editor.org/rfc/rfc1918). No uses una dirección de
WSL, Docker o VPN, ni `127.0.0.1`, que es la interfaz de retorno del propio
computador: el teléfono normalmente no puede alcanzarlas.

## 4. Certificado local

Desde la raíz del repositorio, reemplaza la dirección del ejemplo:

```powershell
.\scripts\create-local-certificate.ps1 192.168.1.40
```

Si la política local impide ejecutar scripts, no cambies la política global;
ejecuta solo este helper con una excepción de proceso:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\create-local-certificate.ps1 192.168.1.40
```

Esta excepción dura solo ese proceso. La documentación de PowerShell explica
los [alcances de las políticas de ejecución](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_execution_policies).

El helper pide a la CA local que firme `certs\local.pem` y guarda su clave
privada en `certs\local-key.pem`. El certificado incluye la IP indicada y,
para seguir permitiendo pruebas en el computador, también `localhost`,
`127.0.0.1` y `::1`.

## 5. Red y firewall

Docker Desktop publica el puerto 8000 en el host Windows. Si el teléfono no
puede acceder, abre **Seguridad de Windows → Firewall y protección de red →
Configuración avanzada → Reglas de entrada** y permite TCP 8000 únicamente en
redes privadas. No desactives el firewall completo.

Continúa con la configuración común de
[HTTPS desde el teléfono](../../README.md#acceso-desde-un-teléfono-https-en-la-red-local).

## 6. WSL y mDNS opcionales

Si trabajas dentro de WSL, habilita la integración de tu distribución en
Docker Desktop. Los contenedores siguen publicando el puerto en el host
Windows; desde el teléfono usa la dirección IPv4 del adaptador Windows, no la
dirección interna de WSL.

La guía oficial de Docker explica la
[integración con WSL](https://docs.docker.com/desktop/features/wsl/).

mDNS permite que equipos del mismo enlace local resuelvan nombres `.local` por
multicast, sin un DNS central. No es un requisito y su disponibilidad puede
variar según la versión de Windows y la configuración de la red. Consulta el
[estándar de mDNS](https://www.rfc-editor.org/rfc/rfc6762) y usa la dirección
IPv4 como camino inicial y alternativa estable.

## 7. Verificación

PowerShell define `curl` como alias en algunas versiones; usa explícitamente
`curl.exe`:

Después de iniciar Compose con la configuración HTTPS del README, prueba primero
con validación completa:

```powershell
curl.exe https://192.168.1.40:8000/healthz
```

Debes obtener `{"status":"ok"}`. Si Windows responde pero el teléfono no,
revisa la regla de firewall, el perfil privado de la red Wi-Fi y la confianza
de `rootCA.pem` en el dispositivo. Si `curl.exe` rechaza el certificado,
`curl.exe -k` puede servir como diagnóstico de conectividad, pero `-k`
deshabilita la verificación TLS y no debe considerarse una solución.
