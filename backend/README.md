# Backend: desarrollo local

Este README explica cómo ejecutar, probar y conectar el backend. Los comandos
comunes son los mismos en todas las plataformas; solo la instalación de las
herramientas, la red y el almacén de certificados cambian entre sistemas
operativos.

Si es tu primera vez en el proyecto, sigue este orden:

1. prepara el computador con la guía de tu plataforma;
2. levanta la API con la sección [Inicio rápido](#inicio-rápido);
3. ejecuta las [pruebas](#pruebas); y
4. si usarás un teléfono, continúa con
   [HTTPS en la red local](#acceso-desde-un-teléfono-https-en-la-red-local).

Guías para preparar el computador:

- [Linux](docs/platforms/linux.md)
- [macOS](docs/platforms/macos.md)
- [Windows y WSL](docs/platforms/windows.md)

Guías para instalar la autoridad certificadora local en un dispositivo móvil:

- [Android](docs/platforms/android.md)
- [iOS y iPadOS](docs/platforms/ios.md)

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
Compose de desarrollo, crea el usuario de prueba si no existe: correo
`demo@example.com`, contraseña `demo-password`.

El login es `POST /api/v1/auth/login`; devuelve 204 y establece una cookie
`session` `HttpOnly`. El seed usa un UUID generado por la aplicación, no una
contraseña ni identificador de producción. No incluyan secretos ni contraseñas
de producción en Git.

El seed está desactivado por defecto. Para activarlo fuera de Docker Compose,
establece `SEED_DEMO_USER=true`; ejecutarlo nuevamente no duplica al usuario,
porque primero verifica el email.

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
docker compose --profile test down -v --remove-orphans
```

El perfil `test` crea `test-db` sin volumen persistente y el servicio
`backend-tests` aplica las migraciones, ejecuta el seed y corre Pytest. Cubre
la existencia de la tabla `users`, el usuario seed y un login real contra la
base migrada; no usa la base `db` de desarrollo.

## Acceso desde un teléfono: HTTPS en la red local

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

### 1. Obtén la dirección y prepara el certificado

Sigue la guía de [Linux](docs/platforms/linux.md),
[macOS](docs/platforms/macos.md) o
[Windows](docs/platforms/windows.md) para:

1. obtener la dirección LAN;
2. instalar `mkcert` y confiar su CA local;
3. generar `certs/local.pem` y `certs/local-key.pem`; y
4. revisar el firewall de la plataforma.

El certificado debe incluir exactamente la dirección o nombre que abrirás
desde el teléfono. El helper agrega ese valor a la extensión
`subjectAltName` del certificado.

### 2. Configura Docker Compose

Copia `.env.local.example` como `.env.local` en la raíz del repositorio. El
archivo resultante está ignorado por Git y contiene esta configuración:

```dotenv
LOCAL_TLS=true
COOKIE_SECURE=true
```

Las variables tienen estos efectos:

- `LOCAL_TLS` indica al gateway nginx que termine TLS con el certificado local;
  FastAPI y Vite siguen usando HTTP dentro de la red privada de Compose; y
- `COOKIE_SECURE` impide que la cookie de sesión viaje por HTTP.

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

### 3. Confía la CA en el teléfono y verifica

`mkcert -CAROOT` muestra el directorio de la CA. Instala **solo**
`rootCA.pem` en tu dispositivo de desarrollo; nunca copies ni compartas
`rootCA-key.pem`. Sigue la guía de tu dispositivo:

- [Instalar la CA local en Android](docs/platforms/android.md)
- [Instalar la CA local en iOS o iPadOS](docs/platforms/ios.md)

Desde el teléfono abre:

```text
https://192.168.1.40:8443/
https://192.168.1.40:8443/healthz
https://192.168.1.40:8443/docs
```

El primer path viene de Vite; los otros dos pasan por nginx hacia FastAPI. El
frontend usa URLs relativas como `/api/v1/auth/login`, por lo que la IP o nombre
mDNS no queda escrito en su código.

El login debe responder con una cookie `Secure; HttpOnly; SameSite=Lax`.
`Secure` indica que el navegador solo debe enviarla por HTTPS; `HttpOnly`
impide que JavaScript acceda a ella y `SameSite` limita su envío en contextos
entre sitios. Estas propiedades forman parte del mecanismo de
[cookies HTTP](https://www.rfc-editor.org/rfc/rfc6265.html).

### Diagnóstico común

- Abre primero `/healthz` desde el computador usando la misma dirección LAN.
- `curl -k https://192.168.1.40:8443/healthz` desactiva deliberadamente la
  validación del certificado. Úsalo solo para separar un problema de red de uno
  de confianza; no demuestra que HTTPS esté configurado correctamente.
- Si funciona en el computador pero no en el teléfono, revisa firewall,
  aislamiento Wi-Fi y que ambos dispositivos estén en la misma subred.
- Si el navegador rechaza el certificado, confirma que este incluya la
  dirección exacta y que el teléfono confíe `rootCA.pem`.
- Si la API responde pero el navegador no conserva la sesión, verifica HTTPS,
  `COOKIE_SECURE=true` y que el frontend envíe credenciales con Fetch.

## Migraciones y Lambda

Aquí una **migración** no significa copiar la base de datos a otro servidor,
sino guardar como código un cambio versionado de su esquema: crear una tabla,
agregar una columna o modificar un índice. El proyecto usa
[Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html) para que todos
los entornos apliquen esos cambios en el mismo orden.

Las revisiones están en `migrations/versions` y se aplican desde `backend/` con
`alembic upgrade head`. El esquema se declara con
[SQLAlchemy Core](https://docs.sqlalchemy.org/en/20/core/), sin usar el ORM, y
`app.main.handler` expone la app con Mangum para Lambda/API Gateway. La guía
[Despliegue en AWS Lambda y migración a Aurora DSQL](docs/aws-lambda.md) fija
las decisiones de empaquetado, configuración, IAM, pooling, migraciones y
observabilidad.

### Flujo de migraciones

Los cambios al esquema se definen primero en `backend/app/db/schema.py` y se
guardan luego en una nueva revisión de Alembic. No se edita una migración que ya
ha sido aplicada en un entorno compartido. Una revisión autogenerada es un
punto de partida: siempre hay que leerla antes de aplicarla.

Con los contenedores iniciados, ejecuta estos comandos desde la raíz:

```console
docker compose run --rm --entrypoint alembic backend current
docker compose run --rm --entrypoint alembic backend check
docker compose run --rm --entrypoint alembic backend revision --autogenerate -m "describe el cambio"
docker compose run --rm --entrypoint alembic backend upgrade head
docker compose run --rm --entrypoint alembic backend downgrade -1
```

- `current` muestra la revisión aplicada actualmente;
- `check` detecta si el esquema declarado requiere una nueva revisión;
- `revision --autogenerate` propone el archivo de migración;
- `upgrade head` aplica todas las revisiones pendientes; y
- `downgrade -1` revierte una revisión cuando esta admite una reversión segura.

Cada pull request que cambie tablas, columnas, índices o restricciones debe
incluir su migración y explicar si hay impacto sobre datos existentes. Con
PostgreSQL, la conexión se obtiene de `DATABASE_URL`. Con DSQL, Alembic usa el
mismo adaptador IAM que la aplicación. La tarea de migración abre un pool de una
sola conexión, lo descarta al terminar y nunca se ejecuta al iniciar Lambda.
