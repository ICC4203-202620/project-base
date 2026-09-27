# Backend: instalación, ejecución y mapa de la API

Este README explica cómo levantar el backend, con qué cuentas explorarlo y
**dónde está el contrato de cada épica**. Tres documentos se reparten el
trabajo:

| Documento | Para qué |
| --- | --- |
| **este README** | Levantar, probar y saber qué endpoint sirve a cada épica. |
| [Contrato de la API, por épica](docs/api.md) | Qué recibe y qué devuelve cada endpoint, y por qué. |
| [Arquitectura y desarrollo](DEVELOPER.md) | Cómo está construido por dentro, y cómo agregar algo. |

El contrato vigente siempre es el que expone [`/docs`](http://localhost:5173/docs)
en la instalación que estés ejecutando.

## Índice

- [Preparar el computador](#preparar-el-computador)
- [Inicio rápido](#inicio-rápido)
- [Cuentas y datos de demostración](#cuentas-y-datos-de-demostración)
- [La API por épica](#la-api-por-épica)
- [Lo que hay que saber antes de escribir el cliente](#lo-que-hay-que-saber-antes-de-escribir-el-cliente)
- [Probar el contrato con curl](#probar-el-contrato-con-curl)
- [Pruebas](#pruebas)
- [HTTPS y acceso desde un teléfono](#https-y-acceso-desde-un-teléfono)
- [Desarrollo, migraciones y despliegue](#desarrollo-migraciones-y-despliegue)

---

## Preparar el computador

Los comandos son los mismos en todas las plataformas; sólo cambian la
instalación de las herramientas, la red y el almacén de certificados.

- [Linux](docs/platforms/linux.md)
- [macOS](docs/platforms/macos.md)
- [Windows y WSL](docs/platforms/windows.md)

Antes de comenzar, comprueba que Docker y Compose estén disponibles:

```console
docker version
docker compose version
```

[↑ Índice](#índice)

---

## Inicio rápido

Desde la raíz del repositorio:

```console
docker compose up --build
```

La primera ejecución puede tardar porque Compose debe descargar o construir las
imágenes. Cuando los servicios estén listos, abre el frontend a través del
gateway en <http://localhost:5173>.

Compose describe y ejecuta cuatro servicios:
[PostgreSQL](https://www.postgresql.org/docs/17/) en `db`, la API en `backend`,
Vite en `frontend` y nginx en `gateway`, más la red privada que los conecta y
los volúmenes de desarrollo. nginx sirve la aplicación desde Vite y envía los
paths `/api/*`, `/healthz` y `/docs` a FastAPI.

| URL | Qué es |
| --- | --- |
| <http://localhost:5173> | La aplicación, a través del gateway. |
| <http://localhost:5173/docs> | La interfaz interactiva de OpenAPI. |
| <http://localhost:8000> | La API directamente, para diagnóstico. |

El contenedor aplica las migraciones y, sólo en la configuración de desarrollo,
carga los datos docentes si no existen.

Para detener los servicios conservando los datos locales:

```console
docker compose down
```

[↑ Índice](#índice)

---

## Cuentas y datos de demostración

El seed carga cinco cuentas, ocho estilos de comida y dieciséis restaurantes
ficticios de Santiago, con actividad suficiente para recorrer las diecisiete
épicas sin ingresar nada a mano. **No representan locales comerciales reales.**

| Correo | Handle | Para qué sirve |
| --- | --- | --- |
| `demo@example.com` | `demo` | La cuenta principal: sigue a tres personas y a un restaurante, tiene actividad pública y privada, y un feed con las cuatro clases. |
| `demo2@example.com` | `demo2` | La persona a la que `demo` sigue: publica casi todo lo que `demo` ve en su feed. |
| `empty@example.com` | `empty` | No sigue a nadie: sirve para ver un feed vacío, que no es un error. |
| `demo_viajera@example.com` | `demo_viajera` | Comparte prefijo de handle con las anteriores, para ejercitar la búsqueda de personas. |
| `sibarita@example.com` | `la_sibarita` | Su handle no empieza con el término, para comprobar que la búsqueda coincide por contenido. |

Todas usan la contraseña `demo-password`.

El seed deja además un thread de comentarios con respuestas, un grupo de tres
fotografías publicadas en un mismo acto, una visita registrada mucho después de
ocurrida, y actividad privada de varias personas. Cada regla de visibilidad es
comprobable desde estos datos.

> Estas credenciales son **exclusivamente locales y docentes**. No son secretos
> y no deben reutilizarse en despliegues reales. Para probar notificaciones,
> inicia sesión con cada cuenta en un perfil, navegador o dispositivo
> independiente.

El seed está desactivado por omisión; fuera de Docker Compose se activa con
`SEED_DEMO_DATA=true`, y la configuración lo rechaza en
`ENVIRONMENT=production`. Los UUID son estables: ejecutarlo de nuevo no duplica
filas ni reemplaza cambios hechos por un estudiante.

[↑ Índice](#índice)

---

## La API por épica

Cada fila enlaza al contrato completo en
[docs/api.md](docs/api.md), donde está qué recibe, qué devuelve y por qué.

### Cuenta y perfil

| # | Épica | Endpoints |
| --- | --- | --- |
| 1 | [Registro e inicio de sesión](docs/api.md#1-registro-e-inicio-de-sesión) | `POST /auth/register` · `POST /auth/login` · `GET /auth/session` · `POST /auth/logout` · `GET /countries` |
| 2 | [Perfil de usuario](docs/api.md#2-perfil-de-usuario) | `GET /users/{handle}` · `GET /users/{handle}/activity` |

### Descubrimiento de restaurantes

| # | Épica | Endpoints |
| --- | --- | --- |
| 3 | [Buscar o crear un restaurante](docs/api.md#3-buscar-o-crear-un-restaurante) | `GET /restaurants?q=…` · `POST /restaurants` · `GET /cuisine-styles` |
| 4 | [Explorar en el mapa](docs/api.md#4-explorar-restaurantes-en-el-mapa) | `GET /restaurants/map` |
| 5 | [Estilo de comida y cercanía](docs/api.md#5-buscar-por-estilo-de-comida-y-cercanía) | `GET /restaurants/nearby` |
| 6 | [Ver un restaurante](docs/api.md#6-ver-un-restaurante) | `GET /restaurants/{id}` · `GET /restaurants/{id}/photos` |

### Registro de la experiencia

| # | Épica | Endpoints |
| --- | --- | --- |
| 7 | [Check-in en un restaurante](docs/api.md#7-hacer-check-in-en-un-restaurante) | `POST /visits` · `GET /visits/{id}` |
| 8 | [Publicar la foto de un plato](docs/api.md#8-publicar-la-foto-de-un-plato) | `POST /photos` · `GET /photos/{id}` · `GET /photos/{id}/content` |
| 9 | [Fotos del menú o instalaciones](docs/api.md#9-publicar-fotos-del-menú-o-de-las-instalaciones) | `POST /photos` con `upload_group` |
| 10 | [Reseñar un plato](docs/api.md#10-reseñar-un-plato) | `POST /reviews` · `GET /reviews/{id}` |
| 11 | [Evaluar un restaurante](docs/api.md#11-evaluar-un-restaurante) | `GET /rating-criteria` · `POST /evaluations` · `GET /evaluations/{id}` · `GET /restaurants/{id}/evaluations` |

### Interacción social

| # | Épica | Endpoints |
| --- | --- | --- |
| 12 | [Buscar usuarios por handle](docs/api.md#12-buscar-usuarios-por-handle) | `GET /users?q=…` |
| 13 | [Seguir usuarios](docs/api.md#13-seguir-y-dejar-de-seguir-usuarios) | `PUT` y `DELETE /users/{handle}/follow` |
| 14 | [Seguir restaurantes](docs/api.md#14-seguir-y-dejar-de-seguir-restaurantes) | `PUT` y `DELETE /restaurants/{id}/follow` |
| 15 | [Ver el feed](docs/api.md#15-ver-el-feed) | `GET /feed` |
| 16 | [Visitas de personas conocidas](docs/api.md#16-ver-visitas-de-personas-conocidas-en-un-restaurante) | dentro de `GET /restaurants/{id}` |
| 17 | [Comentar fotografías](docs/api.md#17-comentar-fotografías) | `POST` y `GET /photos/{id}/comments` · `GET /comments/{id}/replies` |

Todos los paths llevan el prefijo `/api/v1`. Fuera de las épicas quedan el
[CRUD de restaurantes](docs/api.md#crud-de-restaurantes) heredado de la entrega
2 y [`GET /healthz`](docs/api.md#salud-del-servicio).

[↑ Índice](#índice)

---

## Lo que hay que saber antes de escribir el cliente

Cinco cosas atraviesan toda la API. Están explicadas en
[Antes de empezar](docs/api.md#antes-de-empezar); este es el resumen.

**La sesión viaja en una cookie `HttpOnly`.** El frontend no puede leerla ni
necesita hacerlo: basta con enviar cada solicitud con `credentials: "include"`.
Sin sesión, `401`. Todo requiere sesión salvo el registro, el inicio de sesión
y el catálogo de nacionalidades.

**Las colecciones se recorren por cursor opaco**, no por `offset`. Responden
`{ items, next_cursor }`; cuando `next_cursor` es `null` no hay más páginas. No
construyas ni interpretes un cursor: uno que esta API no emitió responde `422`.

**El cliente no filtra por visibilidad.** El backend recibe la identidad del
observador desde la cookie y devuelve sólo lo que esa persona puede ver. La
misma URL devuelve cosas distintas según quién pregunta. Un cliente que filtra
ya recibió lo que debía ocultarse.

**Cuatro formas se repiten en muchas respuestas** —el resumen de persona, el
de restaurante, el restaurante de una actividad y el envelope de actividad—.
Escribe un componente por cada una y reutilízalo.

**`404` y `422` se reparten así:** `404` cuando el recurso de la URL no está
disponible, incluso si es porque esta sesión no puede verlo; `422` cuando está
y lo que se pide sobre él no se puede aceptar.

[↑ Índice](#índice)

---

## Probar el contrato con curl

Conservando la cookie entre comandos:

```console
curl -i -c foodie-cookie.txt \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"demo-password"}' \
  http://localhost:5173/api/v1/auth/login

curl -i -b foodie-cookie.txt http://localhost:5173/api/v1/auth/session

curl -i -b foodie-cookie.txt 'http://localhost:5173/api/v1/feed?limit=2'

curl -i -b foodie-cookie.txt 'http://localhost:5173/api/v1/restaurants?limit=3'

curl -i -b foodie-cookie.txt \
  'http://localhost:5173/api/v1/users/demo2/activity?limit=3'

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
terminar: contiene una credencial válida. **No incluyas secretos, cookies ni
contraseñas de producción en Git.**

[↑ Índice](#índice)

---

## Pruebas

La forma canónica es la del contenedor, contra un PostgreSQL aislado, desde la
raíz del repositorio:

```console
docker compose --profile test up --build --abort-on-container-exit --exit-code-from backend-tests backend-tests
docker compose --profile test down --remove-orphans
```

El perfil `test` crea `test-db` sin volumen persistente, y el servicio
`backend-tests` prueba un ciclo completo de upgrade/downgrade, ejecuta el seed
y corre Pytest. Cubre autenticación, CRUD, asociaciones, duplicados,
idempotencia, cargas multipart, compensación de storage y validación contra la
base migrada; no usa la base `db` de desarrollo.

> **No agregues `-v` al comando de limpieza.** Compose lo aplicaría a todo el
> proyecto y eliminaría también `postgres-data`, el volumen de la base de
> desarrollo. `test-db` no usa un volumen nombrado, así que eliminar su
> contenedor ya descarta la base de pruebas.

Para iterar rápido en el computador hacen falta Python 3.13 y
[`uv`](https://docs.astral.sh/uv/):

```console
cd backend
uv sync --group dev
uv run pytest
```

Las pruebas normales no requieren base de datos; las que llevan la marca
`integration` se omiten si `TEST_DATABASE_URL` no está configurada. **Un
resultado obtenido así no reemplaza al del contenedor**, que es el que corre
sobre las versiones que el proyecto declara.

[↑ Índice](#índice)

---

## HTTPS y acceso desde un teléfono

El service worker, la instalación de la PWA y el permiso de notificaciones Push
requieren un contexto seguro, y `localhost` no lo es para el teléfono: en cada
dispositivo, `localhost` designa a ese mismo dispositivo.

El procedimiento completo —emitir una autoridad certificadora local,
instalarla en el computador y en el teléfono, y publicar el gateway sobre
HTTPS en la red local— está en
[HTTPS en la red local y acceso desde un teléfono](docs/https-local.md). Se
hace una vez.

Guías para confiar la CA en un dispositivo:
[Android](docs/platforms/android.md) · [iOS y iPadOS](docs/platforms/ios.md) ·
[Chrome y Firefox](docs/platforms/browsers.md)

[↑ Índice](#índice)

---

## Desarrollo, migraciones y despliegue

La [guía de desarrollo y arquitectura](DEVELOPER.md) explica el stack, la
organización de `app/`, el ciclo de una solicitud, las convenciones para crear
endpoints y el flujo completo de migraciones con SQLAlchemy Core y Alembic.

La guía de [despliegue en AWS Lambda y migración a Aurora
DSQL](docs/aws-lambda.md) documenta el empaquetado, API Gateway, IAM, pooling,
migraciones y observabilidad de la etapa serverless.

[↑ Índice](#índice)
