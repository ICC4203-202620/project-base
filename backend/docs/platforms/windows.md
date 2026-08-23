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

## 3. Elige el host de acceso

Antes de generar el certificado, elige la dirección que escribirás desde el
teléfono. La IPv4 LAN del host Windows es el camino recomendado.

### IPv4 LAN recomendada

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

### mDNS opcional

mDNS permite que equipos del mismo enlace local resuelvan nombres `.local` por
multicast, sin un DNS central. Su disponibilidad varía según la versión de
Windows, el teléfono y la red. Esta guía no supone que exista un nombre mDNS:
usa la IPv4 salvo que hayas comprobado que el mismo nombre `.local` resuelve
tanto desde Windows como desde el teléfono.

Si ya tienes un nombre como `mi-pc.local` funcionando, puedes incluirlo junto
con la IPv4 en el certificado. El
[estándar de mDNS](https://www.rfc-editor.org/rfc/rfc6762) reserva `.local` y
UDP 5353 para este mecanismo.

## 4. Certificado local

Desde la raíz del repositorio, pasa al helper todos los hosts que realmente
usarás. Para trabajar sólo con la IPv4:

```powershell
.\scripts\create-local-certificate.ps1 192.168.1.40
```

Si ya verificaste mDNS, puedes emitir un solo certificado para ambos:

```powershell
.\scripts\create-local-certificate.ps1 192.168.1.40 mi-pc.local
```

Si la política local impide ejecutar scripts, no cambies la política global;
ejecuta solo este helper con una excepción de proceso:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\create-local-certificate.ps1 192.168.1.40
```

Esta excepción dura solo ese proceso. La documentación de PowerShell explica
los [alcances de las políticas de ejecución](https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_execution_policies).

El helper pide a la CA local que firme `certs\local.pem` y guarda su clave
privada en `certs\local-key.pem`. El certificado incluye todos los valores
indicados y, para seguir permitiendo pruebas en el computador, también
`localhost`, `127.0.0.1` y `::1`.

Los hosts pertenecen al certificado y a las URLs de acceso; **no se agregan a
`.env.local`**. Si regeneras el certificado mientras Compose está activo,
reinicia nginx para que vuelva a cargarlo:

```powershell
docker compose --env-file .env.local restart gateway
```

## 5. Compose, red y firewall

Crea el perfil TLS. Compose no lee `.env.local` automáticamente, por lo que
debes indicar `--env-file` cada vez que levantes esta configuración:

```powershell
Copy-Item .env.local.example .env.local
docker compose --env-file .env.local up --build
```

El perfil `.env.local` publica el gateway HTTPS en el puerto 5173 de Windows.
Si el teléfono no puede acceder, abre **Seguridad de Windows → Firewall y
protección de red → Configuración avanzada → Reglas de entrada** y permite TCP
5173 únicamente en redes privadas. No desactives el firewall completo.

## 6. WSL y el almacén de confianza

Si trabajas dentro de WSL, habilita la integración de tu distribución en
Docker Desktop. Los contenedores siguen publicando el puerto en el host
Windows; desde el teléfono usa la dirección IPv4 del adaptador Windows, no la
dirección interna de WSL.

La guía oficial de Docker explica la
[integración con WSL](https://docs.docker.com/desktop/features/wsl/).

La integración de Docker con WSL no comparte automáticamente autoridades
certificadoras. Si Chrome o Firefox se ejecutan en Windows, instala y usa
`mkcert` desde PowerShell, como indica esta guía. Ejecutar `mkcert -install`
dentro de WSL instalaría otra CA en el almacén Linux; esa CA no sería confiable
automáticamente para los navegadores de Windows.

## 7. Verificación

PowerShell define `curl` como alias en algunas versiones; usa explícitamente
`curl.exe`:

Prueba con validación TLS completa usando un host incluido en el certificado:

```powershell
curl.exe https://192.168.1.40:5173/healthz
# Alternativa, sólo si incluiste y validaste mDNS:
curl.exe https://mi-pc.local:5173/healthz
```

Debes obtener `{"status":"ok"}`. Si Windows responde pero el teléfono no,
revisa la regla de firewall, el perfil privado de la red Wi-Fi y la confianza
de `rootCA.pem` en el dispositivo. Si `curl.exe` rechaza el certificado,
`curl.exe -k` puede servir como diagnóstico de conectividad, pero `-k`
deshabilita la verificación TLS y no debe considerarse una solución.

Continúa con la explicación común de
[HTTPS local y acceso desde un teléfono](../../README.md#https-local-y-acceso-desde-un-teléfono).
