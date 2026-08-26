# Backend: instalación y ejecución local

Este README explica cómo ejecutar, probar y conectar el backend. Los comandos
comunes son los mismos en todas las plataformas; solo la instalación de las
herramientas, la red y el almacén de certificados cambian entre sistemas
operativos. Para entender la estructura del código o implementar funcionalidad,
continúa con la [guía de desarrollo y arquitectura](DEVELOPER.md).

Si es tu primera vez en el proyecto, sigue este orden:

1. prepara el computador con la guía de tu plataforma;
2. levanta la API con la sección [Inicio rápido](#inicio-rápido);
3. ejecuta las [pruebas](#pruebas); y
4. si usarás HTTPS o un teléfono, continúa con
   [HTTPS en la red local](#https-local-y-acceso-desde-un-teléfono).

Guías para preparar el computador:

- [Linux](docs/platforms/linux.md)
- [macOS](docs/platforms/macos.md)
- [Windows y WSL](docs/platforms/windows.md)

Guías para instalar la autoridad certificadora local en un dispositivo móvil:

- [Android](docs/platforms/android.md)
- [iOS y iPadOS](docs/platforms/ios.md)

Guía para confiar la CA en un navegador del computador:

- [Google Chrome y Mozilla Firefox](docs/platforms/browsers.md)

Los comandos comunes se ejecutan desde la raíz del repositorio. El entorno usa
[Docker Compose](https://docs.docker.com/compose/) para describir y ejecutar
cuatro servicios: [PostgreSQL](https://www.postgresql.org/docs/17/) en `db`, la
API en `backend`, Vite en `frontend` y nginx en `gateway`. Compose también crea
la red privada que los conecta y los volúmenes de desarrollo.

Antes de comenzar, comprueba que Docker y Compose estén disponibles:

```console
docker version
docker compose version
```

## Inicio rápido

```console
docker compose up --build
```

La primera ejecución puede tardar porque Compose debe descargar o construir las
imágenes. Cuando los servicios estén listos, abre el frontend a través del
gateway en <http://localhost:5173>. nginx sirve la aplicación desde Vite y
envía los paths `/api/*`, `/healthz` y `/docs` a FastAPI.

La API también queda expuesta directamente en <http://localhost:8000> para
diagnóstico. La interfaz interactiva de
[OpenAPI](https://spec.openapis.org/oas/latest.html), generada por
[FastAPI](https://fastapi.tiangolo.com/features/#automatic-docs), se puede abrir
mediante el gateway en <http://localhost:5173/docs>.

El contenedor aplica las migraciones y, solo en la configuración de Docker
Compose de desarrollo, carga datos docentes si no existen: dos usuarios, ocho
estilos de comida y diez restaurantes ficticios de Santiago. Sirven para
explorar el API sin tener que ingresar datos manualmente; no representan
locales comerciales reales.

| Correo | Contraseña | Handle | Uso sugerido |
| --- | --- | --- | --- |
| `demo@example.com` | `demo-password` | `@demo` | Emisor o receptor de prueba |
| `demo2@example.com` | `demo-password` | `@demo2` | Emisor o receptor de prueba |

Estas credenciales son exclusivamente locales y docentes; no son secretos y no
deben reutilizarse en despliegues reales. Para probar notificaciones, inicia
sesión con cada cuenta en un perfil, navegador o dispositivo independiente y
habilita las notificaciones en cada instalación manualmente.

El backend ofrece el ciclo de sesión completo:

| Método y path | Resultado |
| --- | --- |
| `POST /api/v1/auth/login` | Valida credenciales, persiste una sesión y entrega la cookie. |
| `GET /api/v1/auth/session` | Devuelve la identidad y caducación de la sesión vigente. |
| `POST /api/v1/auth/logout` | Revoca la sesión actual y elimina la cookie. |

La cookie `session` contiene un JWT firmado y usa `HttpOnly`, por lo que el
frontend no puede ni debe leerla. El navegador la envía con `credentials:
"include"`. Login y logout devuelven `204 No Content`; una consulta sin sesión,
con un token vencido o con una sesión revocada devuelve `401`.

### API de restaurantes

Todas las rutas de restaurantes requieren esa sesión:

| Método y path | Resultado |
| --- | --- |
| `GET /api/v1/restaurants?limit=20&offset=0` | Lista una página ordenada de forma estable. |
| `POST /api/v1/restaurants` | Crea un restaurante; responde `201` y publica `Location`. |
| `GET /api/v1/restaurants/{id}` | Consulta un restaurante o responde `404`. |
| `PATCH /api/v1/restaurants/{id}` | Modifica únicamente los campos presentes. |
| `DELETE /api/v1/restaurants/{id}` | Elimina el recurso y responde `204`. |

`limit` tiene el valor predeterminado 20, acepta de 1 a 100 y evita descargar
una colección sin límite. `offset` comienza en 0. Cada respuesta contiene
`id`, `name`, `address`, `latitude`, `longitude`, `cuisine_styles`,
`created_at` y `updated_at`.

Al crear o editar, `cuisine_styles` recibe uno o más slugs existentes. Los datos
iniciales ofrecen `chilena`, `peruana`, `italiana`, `japonesa`, `india`,
`vegana`, `cafeteria` y `sandwicheria`. La respuesta expande cada slug a un
objeto con `id`, `slug` y nombre visible. FastAPI describe todos los modelos y
permite probarlos en [`/docs`](http://localhost:5173/docs).

Nombre y dirección se comparan sin distinguir mayúsculas ni espacios
repetidos. Intentar crear la misma combinación responde `409 Conflict`; una
coordenada fuera de rango, una lista vacía o un slug desconocido responde
`422`. En esta base docente cualquier usuario autenticado puede modificar
restaurantes. Esa simplificación permite practicar el CRUD, pero **no es un
modelo de autorización apropiado para producción**: roles, ownership y
moderación quedan para una evolución posterior.

### Creación de reseñas con fotografía

`POST /api/v1/reviews` crea la reseña pública de la sesión vigente. Recibe
`multipart/form-data` con exactamente estos campos:

| Campo | Tipo y límite |
| --- | --- |
| `restaurant_id` | UUID de un restaurante existente. |
| `dish_name` | Texto entre 1 y 120 caracteres, sin contar espacios exteriores. |
| `text` | Texto entre 1 y 2000 caracteres, sin contar espacios exteriores. |
| `photo` | Una imagen JPEG, PNG o WebP válida; 10 MiB como máximo por defecto. |

El backend comprueba el contenido real de la imagen, no solamente el nombre o
el MIME informado por el cliente. Una creación exitosa responde `201 Created`,
incluye el path futuro de detalle en `Location` y entrega una URL estable como
`/api/v1/photos/{photo_id}/content`. Esta última requiere sesión: nunca expone
la ruta del disco, la clave S3 ni guarda una URL prefirmada en la base.

Por ejemplo, después del login del siguiente bloque, reemplaza
`foto-del-plato.jpg` por una imagen propia:

```console
curl -i -b foodie-cookie.txt \
  -H 'Origin: http://localhost:5173' \
  -F 'restaurant_id=20000000-0000-4000-8000-000000000001' \
  -F 'dish_name=Pastel de choclo' \
  -F 'text=Muy sabroso y bien presentado.' \
  -F 'photo=@foto-del-plato.jpg;type=image/jpeg' \
  http://localhost:5173/api/v1/reviews
```

No agregues manualmente `Content-Type: multipart/form-data`: `curl` y
`FormData` en el navegador generan el boundary que separa las partes. La
[guía de archivos de FastAPI](https://fastapi.tiangolo.com/tutorial/request-files/)
explica por qué `UploadFile` permite procesar la carga sin copiar un archivo
arbitrariamente grande completo a memoria.

En Docker Compose, `MEDIA_STORAGE_BACKEND=local` guarda las fotografías en el
volumen nombrado `media-data`, montado en `/data/media`. `docker compose down`
y la recreación del contenedor conservan tanto ese volumen como
`postgres-data`. Para borrar deliberadamente **todos** los datos locales del
proyecto, incluidos base y fotografías, usa `docker compose down --volumes`.
Si sólo necesitas retirar las fotografías, detén primero el stack con
`docker compose down` y elimina `project-base_media-data` con
`docker volume rm project-base_media-data`; el prefijo cambia si usaste otro
nombre de proyecto Compose.

Para probar un bucket privado S3, configura las variables documentadas en
`.env.local.example` y cambia `MEDIA_STORAGE_BACKEND=s3`. Boto3 usa su
[cadena normal de credenciales](https://docs.aws.amazon.com/sdkref/latest/guide/standardized-credentials.html):
en desarrollo puede recibir un perfil o variables desde un override local, y
en Lambda usa el rol de ejecución. Nunca agregues access keys al repositorio.
La API devuelve una redirección temporal a una
[URL prefirmada](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
después de autorizar la ruta estable.

### Feed y detalle de reseñas

`GET /api/v1/feed` devuelve la actividad pública reciente relacionada con los
usuarios o restaurantes que sigue la sesión. La respuesta usa un envelope
extensible y paginación por cursor:

```json
{
  "items": [{"type":"review","occurred_at":"...","review": {"...":"..."}}],
  "next_cursor": "cursor-opaco-o-null"
}
```

`limit` tiene valor predeterminado 20 y máximo 50. Cuando exista
`next_cursor`, inclúyelo como `cursor` en la siguiente llamada; no lo modifiques
ni intentes interpretarlo. El orden es descendente por fecha e identificador,
y una reseña que coincide por ambos tipos de seguimiento aparece una sola vez.

`GET /api/v1/reviews/{review_id}` entrega la misma reseña estructurada. Las
reseñas públicas están disponibles para sesiones autenticadas; una privada sólo
puede verla su autor y para las demás sesiones responde `404`.

El seed local incorpora tres cuentas: `demo@example.com` (`@demo`),
`demo2@example.com` (`@demo2`) y `empty@example.com` (`@empty`), todas con
contraseña `demo-password`. `@demo` demuestra feed, deduplicación y detalle;
`@empty` demuestra una página sin actividad. Las fotos docentes se cargan al
proveedor local o S3 a través del mismo contrato `MediaStorage` usado por las
reseñas normales.

Para probar el contrato conservando la cookie entre comandos:

```console
curl -i -c foodie-cookie.txt \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"demo-password"}' \
  http://localhost:5173/api/v1/auth/login

curl -i -b foodie-cookie.txt \
  http://localhost:5173/api/v1/auth/session

curl -i -b foodie-cookie.txt \
  'http://localhost:5173/api/v1/feed?limit=2'

curl -i -b foodie-cookie.txt \
  http://localhost:5173/api/v1/reviews/30000000-0000-4000-8000-000000000001

curl -i -b foodie-cookie.txt \
  'http://localhost:5173/api/v1/restaurants?limit=3&offset=0'

curl -i -b foodie-cookie.txt \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Restaurante del curso","address":"Monjitas 550, Santiago","latitude":-33.4369,"longitude":-70.6448,"cuisine_styles":["chilena","vegana"]}' \
  http://localhost:5173/api/v1/restaurants

curl -i -b foodie-cookie.txt \
  -H 'Origin: http://localhost:5173' \
  -X POST http://localhost:5173/api/v1/auth/logout
```

Usa un archivo temporal propio si compartes el computador y elimínalo al
terminar: contiene una credencial válida. El seed usa UUID estables docentes,
no contraseñas ni identificadores de producción. No incluyan secretos, cookies
ni contraseñas de producción en Git.

El seed está desactivado por defecto. Para activarlo fuera de Docker Compose,
establece `SEED_DEMO_DATA=true`. Los UUID de los usuarios, estilos y
restaurantes son estables: ejecutarlo nuevamente no duplica filas ni reemplaza
cambios hechos por un estudiante. La configuración rechaza explícitamente el
seed en `ENVIRONMENT=production`.

Para detener los servicios conservando los datos locales:

```console
docker compose down
```

## Pruebas

Para ejecutar pruebas directamente en el computador necesitas Python 3.13 y
[`uv`](https://docs.astral.sh/uv/), que crea el entorno virtual e instala las
dependencias declaradas por el backend:

```console
cd backend
uv sync --group dev
uv run pytest
```

Las pruebas normales no requieren una base de datos; las que llevan la marca
`integration` se omiten si `TEST_DATABASE_URL` no está configurada.

Para ejecutar la suite completa contra un PostgreSQL aislado, desde la raíz:

```console
docker compose --profile test up --build --abort-on-container-exit --exit-code-from backend-tests backend-tests
docker compose --profile test down --remove-orphans
```

El perfil `test` crea `test-db` sin volumen persistente y el servicio
`backend-tests` prueba un ciclo completo de upgrade/downgrade, ejecuta el seed
y corre Pytest. Cubre autenticación, CRUD, asociaciones, duplicados,
idempotencia, cargas multipart, compensación de storage y validación contra la
base migrada; no usa la base `db` de desarrollo.

No agregues `-v` al comando de limpieza: Compose lo aplicaría a todo el
proyecto y eliminaría también `postgres-data`, el volumen de la base de
desarrollo. `test-db` no usa un volumen nombrado, por lo que eliminar su
contenedor ya descarta la base de pruebas.

## HTTPS local y acceso desde un teléfono

HTTPS también se puede usar en el mismo computador. Los helpers del proyecto
emiten el certificado para `localhost`, `127.0.0.1`, `::1` y una o más
direcciones LAN o nombres mDNS proporcionados. Después de instalar la CA local,
Chrome o Firefox pueden abrir <https://localhost:5173> sin una advertencia de
certificado. Sigue
la guía de [Chrome y Firefox](docs/platforms/browsers.md) para entender y
verificar sus almacenes de confianza.

El navegador del teléfono no puede conectarse a `localhost` para alcanzar los
servicios del computador: en cada dispositivo, `localhost` designa a ese mismo
dispositivo. Para probar la aplicación desde un teléfono hay que publicar el
gateway en la red local y acceder mediante HTTPS.

### Conceptos que conviene recordar

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

### IP local, DNS y mDNS

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

### 1. Obtén la dirección y prepara el certificado

Sigue la guía de [Linux](docs/platforms/linux.md),
[macOS](docs/platforms/macos.md) o
[Windows](docs/platforms/windows.md) para:

1. elegir y verificar la dirección LAN o nombre mDNS que usarás;
2. instalar `mkcert` y confiar su CA local;
3. generar `certs/local.pem` y `certs/local-key.pem`; y
4. revisar el firewall de la plataforma.

El certificado debe incluir exactamente cada dirección o nombre que abrirás
desde el teléfono. Los helpers aceptan uno o más valores y los agregan a la
extensión `subjectAltName` del certificado, además de los nombres de loopback.
Por ejemplo, puedes incluir simultáneamente `192.168.1.40` y `mi-pc.local`.

### 2. Configura Docker Compose

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

### 3. Confía la CA en el teléfono y verifica

`mkcert -CAROOT` muestra el directorio de la CA. Instala **solo**
`rootCA.pem` en tu dispositivo de desarrollo; nunca copies ni compartas
`rootCA-key.pem`. Sigue la guía de tu dispositivo:

- [Instalar la CA local en Android](docs/platforms/android.md)
- [Instalar la CA local en iOS o iPadOS](docs/platforms/ios.md)

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

### Diagnóstico común

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

## Desarrollo, migraciones y despliegue

La [guía de desarrollo y arquitectura](DEVELOPER.md) explica el stack, la
organización de `app/`, el ciclo de una solicitud, las convenciones para crear
endpoints y el flujo completo de migraciones con SQLAlchemy Core y Alembic.

La guía de [despliegue en AWS Lambda y migración a Aurora
DSQL](docs/aws-lambda.md) documenta el empaquetado, API Gateway, IAM, pooling,
migraciones y observabilidad de la etapa serverless.
