# HTTPS en la red local y acceso desde un teléfono

Este procedimiento emite una autoridad certificadora local, la instala en el
computador y en el teléfono, y publica el gateway sobre HTTPS en la red del
laboratorio o de la casa. Se hace **una vez**; después basta con levantar
Compose.

Hace falta cuando la entrega exige probar desde un dispositivo real: el
service worker, la instalación de la PWA y el permiso de notificaciones Push
requieren un contexto seguro, y `localhost` no lo es para el teléfono.

Para levantar el backend sin esto, ver el [README](../README.md).

## Índice

- [Conceptos que conviene recordar](#conceptos-que-conviene-recordar)
- [IP local, DNS y mDNS](#ip-local-dns-y-mdns)
- [1. Obtén la dirección y prepara el certificado](#1-obtén-la-dirección-y-prepara-el-certificado)
- [2. Configura Docker Compose](#2-configura-docker-compose)
- [3. Confía la CA en el teléfono y verifica](#3-confía-la-ca-en-el-teléfono-y-verifica)
- [Diagnóstico común](#diagnóstico-común)

Guías por plataforma: [Android](platforms/android.md) ·
[iOS y iPadOS](platforms/ios.md) ·
[Chrome y Firefox](platforms/browsers.md) ·
[Linux](platforms/linux.md) · [macOS](platforms/macos.md) ·
[Windows y WSL](platforms/windows.md)

---

HTTPS también se puede usar en el mismo computador. Los helpers del proyecto
emiten el certificado para `localhost`, `127.0.0.1`, `::1` y una o más
direcciones LAN o nombres mDNS proporcionados. Después de instalar la CA local,
Chrome o Firefox pueden abrir <https://localhost:5173> sin una advertencia de
certificado. Sigue
la guía de [Chrome y Firefox](platforms/browsers.md) para entender y
verificar sus almacenes de confianza.

El navegador del teléfono no puede conectarse a `localhost` para alcanzar los
servicios del computador: en cada dispositivo, `localhost` designa a ese mismo
dispositivo. Para probar la aplicación desde un teléfono hay que publicar el
gateway en la red local y acceder mediante HTTPS.

## Conceptos que conviene recordar

**HTTPS** es HTTP protegido por [TLS](https://www.rfc-editor.org/rfc/rfc8446).
TLS cifra la conexión y permite que el cliente compruebe la identidad del
servidor. Para identificarse, el gateway presenta un **certificado X.509** que
contiene su clave pública, su vigencia y los nombres o direcciones IP para los
que es válido. El formato y la validación de estos certificados se definen en
el [perfil X.509 de Internet](https://www.rfc-editor.org/rfc/rfc5280).

Una **autoridad certificadora** o **CA** firma certificados. Un navegador
confía en un certificado del servidor cuando puede construir una cadena de
firmas hasta una CA presente en su almacén de confianza. En producción se usa
una CA pública. En desarrollo, [`mkcert`](https://github.com/FiloSottile/mkcert)
crea una CA privada local y emite con ella un certificado para este gateway.
Por eso hay que instalar el certificado público de esa CA tanto en el
computador como en el teléfono.

```text
rootCA-key.pem --firma--> certs/local.pem --nginx lo presenta a--> navegador
rootCA.pem     --se instala en--> almacén de confianza --lo consulta--> navegador
```

Los archivos cumplen funciones distintas:

| Archivo | Función | Tratamiento |
| --- | --- | --- |
| `rootCA.pem` | Certificado público de la CA local | Se instala en los dispositivos de desarrollo. |
| `rootCA-key.pem` | Clave privada de la CA local | No se copia ni se comparte: permite firmar otros certificados confiables. |
| `certs/local.pem` | Certificado X.509 que presenta nginx | Se monta en el gateway local. |
| `certs/local-key.pem` | Clave privada del gateway | Permanece en el computador y no se publica. |

El navegador valida también que la IP o el nombre escrito en la URL aparezca
en el certificado. Una IP debe coincidir exactamente, como explica la
[verificación de identidad en TLS](https://www.rfc-editor.org/rfc/rfc9525).
Confiar en la CA no corrige un certificado emitido para otra dirección.

[↑ Índice](#índice)

## IP local, DNS y mDNS

El camino recomendado es usar la dirección IPv4 LAN del computador, por
ejemplo `192.168.1.40`. Es la dirección que el router asigna al computador
dentro de esa red y puede cambiar al conectarse a otra red.

Como alternativa, **mDNS** (_Multicast DNS_) permite resolver un nombre como
`mi-pc.local` sin configurar un servidor DNS. En vez de preguntar a un DNS
central, los dispositivos consultan por multicast a los otros equipos del
mismo enlace local. El sufijo `.local` está reservado para este mecanismo por
el [RFC 6762](https://www.rfc-editor.org/rfc/rfc6762). mDNS solo resuelve un
nombre a una dirección: no cifra la conexión ni reemplaza TLS.

mDNS es opcional porque algunas redes institucionales bloquean multicast o
separan a sus clientes. Si no sabes si está disponible, usa primero la IPv4
LAN. En ambos casos, el teléfono y el computador deben estar en la misma red y
la red Wi-Fi no debe tener aislamiento entre clientes.

Llamaremos **host de acceso** al valor exacto que escribirás en la URL: por
ejemplo, `192.168.1.40` o `mi-pc.local`. Ese valor aparece en dos lugares y no
en `.env.local`:

| Dato | Dónde se configura |
| --- | --- |
| Host de acceso | Argumento del helper del certificado y host de la URL. |
| Activación de TLS y puertos | `.env.local`. |
| Rutas del backend | URLs relativas del frontend; no incluyen host. |

[↑ Índice](#índice)

## 1. Obtén la dirección y prepara el certificado

Sigue la guía de [Linux](platforms/linux.md),
[macOS](platforms/macos.md) o
[Windows](platforms/windows.md) para:

1. elegir y verificar la dirección LAN o nombre mDNS que usarás;
2. instalar `mkcert` y confiar su CA local;
3. generar `certs/local.pem` y `certs/local-key.pem`; y
4. revisar el firewall de la plataforma.

El certificado debe incluir exactamente cada dirección o nombre que abrirás
desde el teléfono. Los helpers aceptan uno o más valores y los agregan a la
extensión `subjectAltName` del certificado, además de los nombres de loopback.
Por ejemplo, puedes incluir simultáneamente `192.168.1.40` y `mi-pc.local`.

[↑ Índice](#índice)

## 2. Configura Docker Compose

Copia `.env.local.example` como `.env.local` en la raíz del repositorio. El
archivo resultante está ignorado por Git y contiene esta configuración:

```dotenv
LOCAL_TLS=true
COOKIE_SECURE=true
GATEWAY_HTTP_PORT=5174
GATEWAY_HTTPS_PORT=5173
```

Las variables tienen estos efectos:

- `LOCAL_TLS` indica al gateway nginx que termine TLS con el certificado local;
  FastAPI y Vite siguen usando HTTP dentro de la red privada de Compose;
- `COOKIE_SECURE` impide que la cookie de sesión viaje por HTTP;
- `GATEWAY_HTTPS_PORT=5173` conserva el puerto habitual para la entrada HTTPS;
  y
- `GATEWAY_HTTP_PORT=5174` evita que los dos mapeos de Compose intenten usar el
  mismo puerto. Es una reserva técnica: nginx no escucha HTTP en ese puerto
  cuando `LOCAL_TLS=true`; el gateway sirve sólo HTTPS.

`.env.local` no es uno de los nombres que Compose carga automáticamente. Debes
pasarlo explícitamente con `--env-file` en cada comando que cree o recree los
servicios de este perfil.

En la Web, un **origen** es la combinación de esquema, host y puerto. Por eso
`http://192.168.1.40:5173` y `https://192.168.1.40:5173` son orígenes distintos.
Con el gateway, el navegador recibe el frontend y llama a `/api/*` usando el
mismo origen. No se necesita CORS para ese camino. La configuración CORS del
backend se conserva para quienes ejecuten Vite directamente en el puerto 5173;
la [guía de CORS de FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)
desarrolla esta diferencia.

Inicia los servicios con el mismo comando en Linux, macOS y PowerShell:

```console
docker compose --env-file .env.local up --build
```

Si vuelves a generar `certs/local.pem` mientras el stack está activo, reinicia
el gateway para que nginx cargue el certificado nuevo:

```console
docker compose --env-file .env.local restart gateway
```

Verifica primero desde el computador:

```text
https://localhost:5173/
https://localhost:5173/healthz
https://localhost:5173/docs
```

[↑ Índice](#índice)

## 3. Confía la CA en el teléfono y verifica

`mkcert -CAROOT` muestra el directorio de la CA. Instala **solo**
`rootCA.pem` en tu dispositivo de desarrollo; nunca copies ni compartas
`rootCA-key.pem`. Sigue la guía de tu dispositivo:

- [Instalar la CA local en Android](platforms/android.md)
- [Instalar la CA local en iOS o iPadOS](platforms/ios.md)

Desde el teléfono abre el mismo host que incluiste en el certificado. Por
ejemplo, para IPv4:

```text
https://192.168.1.40:5173/
https://192.168.1.40:5173/healthz
https://192.168.1.40:5173/docs
```

O bien, si verificaste e incluiste mDNS:

```text
https://mi-pc.local:5173/
https://mi-pc.local:5173/healthz
https://mi-pc.local:5173/docs
```

> No omitas `:5173`: forma parte de la dirección de este entorno local. Si
> escribes solo `https://mi-pc.local/`, el navegador usa el puerto HTTPS
> predeterminado `443`, donde este stack no publica el gateway.

El primer path viene de Vite; los otros dos pasan por nginx hacia FastAPI. El
frontend usa URLs relativas como `/api/v1/auth/login`, por lo que la IP o nombre
mDNS no queda escrito en su código.

El login debe responder con una cookie `Secure; HttpOnly; SameSite=Lax`.
`Secure` indica que el navegador solo debe enviarla por HTTPS; `HttpOnly`
impide que JavaScript acceda a ella y `SameSite` limita su envío en contextos
entre sitios. Estas propiedades forman parte del mecanismo de
[cookies HTTP](https://www.rfc-editor.org/rfc/rfc6265.html).

[↑ Índice](#índice)

## Diagnóstico común

- Abre primero `/healthz` desde el computador usando el mismo host de acceso
  que probarás en el teléfono.
- `curl -k https://192.168.1.40:5173/healthz` —sustituyendo la IP por tu host
  de acceso— desactiva deliberadamente la validación del certificado. Úsalo
  solo para separar un problema de red de uno de confianza; no demuestra que
  HTTPS esté configurado correctamente.
- Si funciona en el computador pero no en el teléfono, revisa firewall,
  aislamiento Wi-Fi y que ambos dispositivos estén en la misma subred.
- Si el navegador rechaza el certificado, confirma que este incluya la
  dirección exacta y que el teléfono confíe `rootCA.pem`.
- Si la API responde pero el navegador no conserva la sesión, verifica HTTPS,
  `COOKIE_SECURE=true` y que el frontend envíe credenciales con Fetch.

[↑ Índice](#índice)
