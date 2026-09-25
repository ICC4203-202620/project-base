# Desarrollo y arquitectura del backend

Esta guía explica cómo está construido el backend y cómo extenderlo sin romper
sus contratos de ejecución local ni su futura migración a AWS. Para instalar
herramientas, iniciar Compose, ejecutar pruebas o configurar HTTPS, comienza en
el [README del backend](README.md).

## Objetivos arquitectónicos

El backend parte como un **monolito modular**: una sola aplicación y un solo
artefacto de despliegue, con responsabilidades separadas en módulos Python. No
es un conjunto de microservicios. Esta elección reduce complejidad accidental
durante las primeras entregas y conserva un camino directo hacia una función
Lambda que contiene la aplicación completa.

Las decisiones centrales son:

- mantener las rutas HTTP independientes del servidor que ejecuta la app;
- concentrar la configuración en variables de entorno validadas;
- acceder a datos mediante SQLAlchemy Core, sin acoplar la API a un ORM;
- versionar cada cambio del esquema con Alembic;
- ocultar la elección PostgreSQL/Aurora DSQL detrás de la creación del engine;
- ejecutar migraciones fuera del runtime de Lambda; y
- probar la misma aplicación tanto como ASGI local como handler de Lambda.

## Mapa de la arquitectura

```text
                         app/main.py
                    crea y compone FastAPI
                              |
                              v
cliente -> nginx -> FastAPI / APIRouter -> Pydantic -> caso de uso
                                               |             |
                                               |             +-> MediaStorage
                                               |             |      +-> volumen local
                                               |             |      \-> bucket S3 privado
                                               |             v
                                               |      SQLAlchemy Core
                                               |             |
                                               |             v
                                               +----- PostgreSQL / DSQL

desarrollo: Uvicorn -----------------> app.main:app
AWS: API Gateway -> Lambda -> Mangum -> app.main:app

Alembic -> metadata de SQLAlchemy -> migraciones versionadas -> base de datos
```

nginx, Vite y TLS pertenecen al entorno que rodea la API, no a su lógica. nginx
presenta frontend y backend bajo un mismo origen; internamente envía `/api/*`,
`/healthz`, `/docs` y `/openapi.json` a FastAPI.

## Stack y función de cada componente

| Tecnología | Responsabilidad en el proyecto | Ubicación principal |
| --- | --- | --- |
| [Python 3.13](https://docs.python.org/3/) | Lenguaje y runtime | Todo `backend/` |
| [FastAPI](https://fastapi.tiangolo.com/) | Aplicación ASGI, routing, validación integrada y OpenAPI | `app/main.py`, `app/api/` |
| [Pydantic](https://docs.pydantic.dev/latest/concepts/models/) | Modelos de entrada, salida y validación de datos | `app/schemas/`, `app/api/` |
| [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | Configuración tipada desde variables de entorno | `app/core/config.py` |
| [Uvicorn](https://www.uvicorn.org/) | Servidor ASGI del contenedor local | `entrypoint.sh` |
| [SQLAlchemy Core](https://docs.sqlalchemy.org/en/20/tutorial/) | Tablas, expresiones SQL, conexiones y transacciones; no se usa el ORM | `app/db/`, `app/services/` |
| [Psycopg 3](https://www.psycopg.org/psycopg3/docs/) | Driver PostgreSQL usado por SQLAlchemy | Configuración del engine |
| [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html) | Historial ejecutable y versionado del esquema | `migrations/` |
| [argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/api.html) | Hash y verificación de contraseñas con Argon2 | `app/core/security.py` |
| [PyJWT](https://pyjwt.readthedocs.io/en/stable/) | Firma de tokens JWT para la sesión | `app/core/security.py` |
| [Mangum](https://mangum.fastapiexpert.com/) | Adaptación de eventos API Gateway/Lambda a ASGI | `app/main.py` |
| [Pillow](https://pillow.readthedocs.io/) | Verificación del contenido real de JPEG, PNG y WebP | `app/services/reviews.py` |
| [Boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) | Adaptador de objetos S3 y URLs prefirmadas | `app/media/storage.py` |
| [Pytest](https://docs.pytest.org/) | Pruebas unitarias, de integración y del handler Lambda | `tests/` |
| [Docker Compose](https://docs.docker.com/compose/) | Entorno reproducible de desarrollo y pruebas | `../docker-compose.yml` |

FastAPI no reemplaza a Uvicorn: FastAPI implementa la aplicación ASGI y
Uvicorn es el servidor que recibe HTTP y la ejecuta localmente. En AWS tampoco
se inicia Uvicorn; Mangum traduce el evento de API Gateway al protocolo ASGI
que entiende la misma aplicación.

## Organización del código

```text
backend/
├── app/
│   ├── main.py             composición de FastAPI y entrypoints ASGI/Lambda
│   ├── api/
│   │   ├── auth.py         contratos HTTP, respuestas y cookies
│   │   ├── dependencies.py sesión actual y protección de origen
│   │   ├── restaurants.py  contrato HTTP del CRUD protegido
│   │   └── reviews.py      creación multipart y entrega de fotografías
│   ├── schemas/
│   │   ├── restaurants.py  modelos Pydantic del CRUD
│   │   └── reviews.py      respuesta pública de reseña y fotografía
│   ├── media/
│   │   └── storage.py      contrato y adaptadores local/S3
│   ├── core/
│   │   ├── config.py       configuración y validaciones por ambiente
│   │   └── security.py     passwords, creación y validación de JWT
│   ├── services/
│   │   ├── auth.py         caso de uso y sesiones persistentes
│   │   ├── restaurants.py  reglas, consultas y transacciones del recurso
│   │   └── reviews.py      validación, persistencia y compensación de medios
│   └── db/
│       ├── engine.py       engines PostgreSQL/DSQL y políticas de pool
│       ├── fixtures.py     datos docentes deterministas, sin inserciones
│       ├── retry.py        reintentos acotados de transacciones idempotentes
│       ├── session.py      engine compartido por el proceso
│       ├── schema.py       metadata y tablas SQLAlchemy Core
│       └── seed.py         datos de demostración optativos
├── migrations/             configuración y revisiones de Alembic
├── tests/                  suite automatizada
├── entrypoint.sh           migración, seed y Uvicorn en el contenedor local
└── pyproject.toml          paquete, dependencias y herramientas
```

### Límites entre módulos

- `app/main.py` **compone** la aplicación. Incluye routers y middleware, pero no
  implementa casos de uso.
- `app/api/` contiene el contrato de transporte: paths, métodos, modelos
  asociados al request, status codes, cookies y traducción de errores a HTTP.
- `app/schemas/` contiene contratos Pydantic reutilizables, separados de las
  tablas y de su representación interna.
- `app/core/` contiene capacidades transversales que no dependen de HTTP ni de
  una tabla concreta.
- `app/services/` coordina casos de uso con varias reglas o pasos de
  persistencia, sin depender de objetos HTTP.
- `app/db/` contiene la definición y construcción de la infraestructura de
  persistencia.
- `migrations/` registra cómo llevar una base desde una revisión de esquema a
  la siguiente. No es código que atienda solicitudes.

El ciclo de autenticación justifica la primera capa de servicio: consultar al
usuario, verificar Argon2, crear o revocar una fila y emitir o validar un JWT
son pasos relacionados que `app/services/auth.py` coordina. El router conserva
las decisiones de HTTP y la dependencia convierte una sesión de aplicación en
autorización reutilizable para otros recursos.

## Dos entrypoints, una sola aplicación

`app/main.py` exporta dos objetos:

- `app`: la aplicación FastAPI que Uvicorn sirve como `app.main:app`; y
- `handler`: `Mangum(app)`, invocado por Lambda como `app.main.handler`.

Los routers y casos de uso no deben saber cuál entrypoint recibió la solicitud.
La [guía de aplicaciones FastAPI en varios
archivos](https://fastapi.tiangolo.com/tutorial/bigger-applications/) explica el
patrón de composición con `APIRouter`.

El endpoint `/healthz` y una prueba con un evento HTTP API v2 aseguran que ambos
caminos mantengan el mismo comportamiento. La arquitectura AWS completa está
en [Despliegue en AWS Lambda y Aurora DSQL](docs/aws-lambda.md).

## Ciclo de autenticación

`POST /api/v1/auth/login` sigue este recorrido:

1. nginx conserva el path y entrega la solicitud a FastAPI;
2. `app.main` selecciona el router incluido bajo `/api/v1`;
3. Pydantic valida JSON como `LoginRequest`, incluido el formato del email;
4. la protección de origen rechaza solicitudes mutables de otro sitio;
5. el servicio consulta `users` y Argon2 compara `password_hash`;
6. una transacción inserta una fila en `auth_sessions`;
7. PyJWT firma un token HS256 con `sub`, `jti`, `iat` y `exp`; y
8. FastAPI responde 204 y entrega el JWT en la cookie `session`.

La cookie usa `HttpOnly`, `SameSite=Lax` y, bajo HTTPS, `Secure`. `HttpOnly`
impide que JavaScript lea el JWT, pero el navegador puede adjuntarlo a futuras
solicitudes. Un JWT firmado permite detectar modificaciones; su payload no está
cifrado y no debe contener secretos.

El JWT y la tabla cumplen tareas distintas. La firma y `exp` permiten rechazar
localmente un token alterado o vencido. `jti` identifica una fila compartida
que debe existir, pertenecer a `sub`, no estar revocada y no haber caducado. La
tabla es una **allowlist**: borrar la cookie no basta, porque una copia del JWT
seguiría existiendo; `POST /auth/logout` marca `revoked_at` y luego elimina la
cookie.

`get_current_session` aplica esas verificaciones y entrega un
`AuthenticatedSession` a cualquier ruta protegida. `GET /auth/session` usa la
misma dependencia para que el frontend reconstruya su estado. Una credencial
inválida responde 401; una falla de la base impide autorizar y responde 503, sin
confundir indisponibilidad con credenciales incorrectas.

La caducación es absoluta y se representa en tres lugares coordinados:

- `exp` dentro del JWT;
- `auth_sessions.expires_at` como límite del servidor; y
- `Max-Age`/`Expires` como comportamiento del navegador.

La configuración inicial no renueva sesiones ni usa refresh tokens. Varias
sesiones por usuario son válidas y logout revoca sólo la actual.

### Registro de cuentas

`POST /api/v1/auth/register` es la única escritura pública del API. Conserva
`require_trusted_origin`, porque lo que la protección evita —que otro sitio
provoque una escritura con las credenciales del navegador— no depende de que
exista una sesión.

`register_user` normaliza, hashea y crea la cuenta junto con su sesión en una
sola transacción. El orden importa: el hash Argon2 se calcula **antes** de
abrir la transacción, para no sostenerla durante la operación más lenta del
recorrido y para que un registro rechazado cueste aproximadamente lo mismo que
uno aceptado.

La normalización vive en el servicio, no en el schema, y el modelo Pydantic la
invoca desde sus validadores. Así la regla se prueba sin HTTP y la comparten
las épicas que después buscan por handle:

- `normalize_handle` retira una arroba inicial y baja a minúsculas. La arroba
  es presentación; almacenarla obligaría a limpiarla en cada comparación.
- `is_valid_handle` aplica `^[a-z0-9_]{3,30}$` sobre la forma normalizada.
- `normalize_email` baja a minúsculas.

La unicidad se resuelve normalizando al escribir, sin índice funcional, porque
Aurora DSQL no los admite. Es la misma estrategia de `normalized_name` en
restaurantes.

El conflicto se clasifica antes de insertar, con una consulta que busca el
correo o el handle. Cuando ambos colisionan con filas distintas gana el correo,
que es la identidad de inicio de sesión y por tanto lo primero que la persona
tiene que cambiar. Si una inscripción simultánea gana la carrera, la violación
de unicidad no dice cuál índice falló, de modo que el servicio vuelve a
preguntar y traduce el resultado; si esa segunda consulta no encuentra
conflicto, la falla era de otra naturaleza y se traduce a 503.

`app/core/countries.py` declara las nacionalidades como dato del código base y
no como tabla. Los países cambian poco, una tabla que nadie edita agrega una
migración y un seed sin agregar una capacidad, y tenerlo en el módulo permite
que el schema valide un código sin consultar la base. El módulo documenta cómo
se regeneró la lista y qué códigos de ICU quedaron fuera por no ser
asignaciones oficiales de ISO 3166-1.

No hay endpoint de disponibilidad de handle. Sería público, porque el registro
lo es, y daría un oráculo para enumerar los handles de la aplicación sin tener
cuenta; el `409` del registro entrega la misma información en el momento en que
el formulario la necesita.

### Cookies y CSRF

`HttpOnly` evita que JavaScript lea el JWT; `Secure` restringe su transporte a
HTTPS y `SameSite=Lax` reduce el envío entre sitios. Como las cookies se
adjuntan automáticamente, login y logout además validan `Origin`. Se acepta el
origen del request —incluido IP o mDNS bajo el gateway— y los valores explícitos
de `CORS_ORIGINS`; un navegador que declare una solicitud cross-site se rechaza
con 403. Clientes no navegador pueden omitir `Origin`.

## Recurso de restaurantes

`app/api/restaurants.py` mantiene las decisiones HTTP y delega el caso de uso a
`app/services/restaurants.py`. Los modelos Pydantic de `app/schemas/` validan
longitudes, coordenadas, slugs y la diferencia entre un campo omitido y uno
nulo en `PATCH`. Los modelos de respuesta no son tablas: convierten los tipos
de persistencia y exponen los estilos como una colección de objetos.

El listado primero pagina restaurantes con un orden estable y después obtiene
sus estilos en una segunda consulta. Así evita tanto una colección ilimitada
como el patrón N+1. `limit` está acotado a 100 y `offset` nunca es negativo. La
[documentación de parámetros de consulta de
FastAPI](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/)
explica cómo estas restricciones pasan además al esquema OpenAPI.

Las dos formas normalizadas del nombre no son redundantes. `normalized_name`
conserva los diacríticos, porque la detección de duplicados tiene que seguir
distinguiendo «Café Perú» de «Cafe Peru» como dos nombres que dos personas
escribieron distinto. `search_name` los pliega, porque quien escribe «cafe»
espera encontrar «Café». Una sola columna obligaría a elegir cuál de las dos
cosas se rompe.

La búsqueda usa `LIKE` sobre `search_name` y escapa los comodines que el
usuario haya escrito; un `%` sin escapar devolvería la colección completa. No
se usan trigramas ni búsqueda de texto completo: atan el proyecto a PostgreSQL
y la entrega 4 migra a Aurora DSQL.

El orden de la colección es alfabético sobre `search_name`, que es la columna
que el índice sirve, y no por relevancia: un cursor reanuda desde una posición
que no puede depender del término buscado.

La consulta del mapa se resuelve con comparaciones sobre `latitude` y
`longitude` y el índice compuesto `ix_restaurants_location`. No se usa
PostGIS: la entrega 4 migra a Aurora DSQL, que no lo ofrece. Las comparaciones
quedan sin funciones que envuelvan las columnas, que es la condición para que
el índice pueda servirlas.

La búsqueda por cercanía usa el mismo índice. El rectángulo que circunscribe
el círculo acota el escaneo, y recién sobre esos candidatos se mide la
distancia exacta, que es la que decide pertenencia y orden. `circumscribing_bounds`
es una función aparte justamente para poder probar sin base de datos sus dos
bordes: un círculo que alcanza un polo no tiene cota de meridiano, y uno
cercano al antimeridiano devuelve una arista oeste al este de la arista este,
que es como la condición reconoce el cruce.

La distancia se calcula en Python y no en SQL. Así la consulta queda con
comparaciones simples que PostgreSQL, Aurora DSQL y el SQLite de las pruebas
sirven igual, sin depender de funciones trigonométricas cuya disponibilidad
difiere entre motores. Lo que eso cuesta es traer las filas del rectángulo, y
el radio máximo es lo que acota ese conjunto.

El límite de área se valida en el servicio y no sólo en el schema, para que la
regla sea comprobable sin HTTP. La medida está en grados cuadrados y es
deliberadamente burda: es una barrera contra quien se alejó hasta ver un
continente, no una medición de superficie.

`truncated` se determina pidiendo un resultado más que el límite, sin contar
la tabla. El orden es por coordenada, que es el que el índice ya produce, de
modo que una respuesta truncada es la parte sur del rectángulo y no una
muestra representativa. Esa es precisamente la razón de anunciarla.

La migración `0100` copia la normalización en lugar de importarla del
servicio. Una migración registra lo que se calculó cuando corrió; importar
código de aplicación dejaría que un cambio posterior a esa función redefina el
historial en silencio.

Para detectar duplicados, la aplicación normaliza nombre y dirección mediante
Unicode NFKC, colapsa whitespace y aplica `casefold`. Luego calcula una clave
SHA-256 sobre ambas partes. El índice único de `identity_key` hace que dos
requests concurrentes no puedan crear la misma identidad, sin indexar textos
largos ni requerir una extensión PostgreSQL. Las columnas normalizadas quedan
explícitas para ordenamiento y diagnóstico, pero nunca se aceptan desde el
cliente.

Crear, actualizar y eliminar usan transacciones cortas. Un UUID y timestamp se
calculan antes de un posible reintento; reemplazar estilos elimina e inserta las
asociaciones dentro de la misma transacción. Si un slug no existe, toda la
operación revierte. Las tablas no declaran foreign keys ni cascadas porque el
adaptador de Aurora DSQL no las soporta: el servicio valida estilos y elimina
asociaciones antes que el restaurante. Esta decisión exige conservar esas
invariantes en todos los futuros casos de uso.

Las escrituras con cookie validan también el origen para reducir CSRF. Por
ahora cualquier sesión válida puede crear, editar o eliminar restaurantes;
esto es una simplificación docente deliberada, no una política para producción.
Una evolución con roles u ownership debe introducir una autorización explícita
antes de reutilizar el CRUD en un despliegue real.

### Fixtures y seed

`app/db/fixtures.py` declara tres usuarios docentes, ocho estilos y diez
restaurantes ficticios con UUID estables. Los usuarios se declaran en la misma
forma que escribe el registro: handle sin arroba y en minúsculas, nacionalidad
como código ISO 3166-1 alfa-2. Como el seed nunca actualiza una fila existente,
una base poblada con el formato anterior conserva sus handles con arroba; el
enunciado de la entrega 3 indica recrear la base de desarrollo al mezclar, y
eso los repone. `app/db/seed.py` contiene la
inserción. Separar datos y mecanismo hace visible qué contenido es docente y
permite probar la idempotencia sin mezclarlo con el runtime del API.

`SEED_DEMO_DATA=true` habilita usuarios, estilos y restaurantes. Para los
usuarios, el seed busca tanto UUID como correo; para estilos y restaurantes,
UUID, slug e identidad antes de insertar. Nunca actualiza una fila ya existente
ni reemplaza asociaciones: reiniciar Compose conserva cambios de los
estudiantes. La opción sigue disponible con `ENVIRONMENT=production`, porque el
despliegue del curso publica contenido de demostración para que el ayudante
recorra la aplicación sin registrarse; véase [DEPLOY.md](../DEPLOY.md). Lambda
no ejecuta el entrypoint local, por lo que las fixtures no forman parte del
bootstrap AWS.

Cuando una fixture coincide por correo o identidad con una fila que usa otro
UUID, el seed conserva esa fila y mapea hacia su UUID persistido las relaciones
de seguimiento, reseña y fotografía. Si UUID e identidad natural apuntan a dos
filas distintas, aborta la transacción en vez de crear referencias ambiguas o
huérfanas.

Los seguimientos usuario→usuario usan una clave primaria compuesta para impedir
duplicados y el `CHECK ck_user_follows_not_self` para impedir auto-seguimientos.
La misma restricción está declarada en la metadata SQLAlchemy y en Alembic; el
seed también rechaza el auto-seguimiento antes de intentar escribirlo.

Las fixtures de feed añaden seguimientos, reseñas y fotografías con UUID y
fechas estables. Los WebP viven en `app/db/assets/reviews/`, pero el seed los
abre como streams y llama a `MediaStorage.store`; `photos.storage_key` siempre
recibe la clave opaca que entregue el proveedor. Si la transacción SQL falla,
el seed elimina los objetos que alcanzó a crear. Reejecutarlo no sobrescribe
filas ni vuelve a cargar las fotografías ya asociadas a una reseña fixture.

## Reseñas y almacenamiento de fotografías

La creación separa tres representaciones que no deben confundirse:

- `reviews` conserva autor, restaurante, plato, texto, visibilidad y fechas;
- `photos` conserva identidad, relaciones, MIME, tamaño y una `storage_key`
  opaca; y
- el proveedor de objetos conserva los bytes en el volumen local o en S3.

La base no conoce paths físicos ni URLs prefirmadas. `Photo.content_url` deriva
siempre de su UUID como `/api/v1/photos/{id}/content`. Esa ruta vuelve a
autorizar la solicitud y luego responde con `FileResponse` en local o con una
redirección 307 de corta duración en S3. Por eso las respuestas del feed
pueden ser estables aunque cambie el proveedor.

### Feed de reseñas

`app/services/feed.py` contiene consultas sin dependencia de FastAPI. Una sola
consulta une reseñas, autor, restaurante y foto, y filtra la actividad pública
por seguimiento de autor o restaurante. La condición es una unión lógica, no
dos listas concatenadas, por lo que una coincidencia doble no se duplica.
Antes de limitar, ordena por `(created_at, id)` descendente; el cursor opaco
codifica esa misma pareja y evita los problemas de offset si se agregan nuevas
reseñas entre páginas.

El detalle usa la misma representación, permite cualquier reseña pública y
permite una privada sólo a su autor. La ausencia y la falta de permiso se
traducen ambas a `404`; los errores SQL se traducen a `503` en el router.

`app/media/storage.py` declara el protocolo `MediaStorage`: `store`, `resolve`
y `delete`. Los casos de uso y routers reciben ese contrato mediante una
dependencia; elegir `local` o `s3` sólo cambia configuración e inyección. El
adaptador local genera una clave a partir del UUID y escribe primero un archivo
temporal, hace `fsync` y lo reemplaza atómicamente. El adaptador S3 usa
`upload_fileobj`, conserva el bucket privado y resuelve lecturas mediante una
URL prefirmada breve. Ninguno utiliza el filename enviado por el cliente.

FastAPI y `python-multipart` entregan la fotografía como `UploadFile`. El
servicio mide el stream, impone `MEDIA_MAX_UPLOAD_BYTES` y usa Pillow para
verificar que sea un JPEG, PNG o WebP íntegro cuyo contenido coincida con el
MIME declarado. nginx tiene un límite algo mayor para admitir el overhead del
multipart. La validación ocurre antes de crear filas.

El filesystem/S3 y SQL no comparten una transacción distribuida. El caso de uso
aplica esta secuencia deliberada:

```text
validar -> almacenar objeto -> transacción photos + reviews
                    |                    |
                    |                    \-> si falla, borrar objeto
                    \-> si falla, no abrir transacción SQL
```

UUID y timestamp se calculan una sola vez antes de la escritura. La transacción
comprueba que el restaurante exista y persiste ambas filas, preservando las
relaciones que DSQL no puede imponer con foreign keys. Si SQL falla, una
compensación _best effort_ elimina el objeto; si también falla la compensación,
se registra el incidente sin ocultar la falla original. Una reconciliación
periódica de huérfanos sería la evolución apropiada para producción.

El contrato de creación usa `multipart/form-data` y responde una reseña con
exactamente una fotografía pública. Rating y comentarios pertenecen a
evoluciones posteriores. El header `Location` apunta a
`/api/v1/reviews/{id}`, implementado por el router de feed como recurso de
detalle.

## Ficha del restaurante y visibilidad de las fotografías

La visibilidad de una fotografía es una columna de `photos` desde la migración
`0102`, y no una deducción a partir de la reseña que la acompañe. Deducirla
deja de funcionar apenas exista una fotografía sin reseña —que es lo que
introduce la épica 8—, y un join interno contra `reviews` en la galería habría
tenido que deshacerse entonces, ocultando mientras tanto fotografías
legítimas. `resolve_photo` autoriza contra esa columna, de modo que la galería
y `/content` no puedan discrepar.

La reseña conserva su propia `visibility`. Cada columna gobierna lo suyo: la
de la reseña decide si el item de actividad aparece en el feed y en el perfil,
la de la fotografía decide la galería y el contenido. Mientras la creación de
reseñas fuerce visibilidad pública, la fotografía copia la de su reseña; la
épica 10 decide si las colapsa cuando la elección llegue al formulario.

La ficha resuelve cuatro consultas acotadas: la fila con sus estilos, los
contadores con las dos direcciones del seguimiento como subconsultas
correlacionadas, el resumen de evaluaciones y las personas conocidas que
estuvieron ahí. Ninguna depende del tamaño del historial del restaurante, y
por eso la galería quedó fuera. `_evaluation_summary` existe como punto único
identificado: cuando la épica 11 tenga evaluaciones, sólo esa función cambia,
y ni el router ni la forma de la respuesta lo hacen.

### Personas conocidas, en una sola pasada

`_known_visitors_statement` agrupa por persona las visitas públicas del
restaurante cuyo autor está entre los seguidos del observador, y proyecta el
máximo de `occurred_at` de cada grupo. Agrupar y no recorrer seguidos es la
decisión: una consulta por persona seguida haría la ficha más lenta
justamente para quien sigue a más gente, que es para quien el bloque existe.

El total sale de la misma pasada, con `count()` como función de ventana sobre
el resultado agrupado. La ventana se evalúa antes del `LIMIT`, así que el
número cuenta a todas las personas aunque la lista se corte en
`MAXIMUM_KNOWN_VISITORS`. La alternativa —una subconsulta de conteo— vuelve a
recorrer las visitas del restaurante para responder lo que la primera pasada
ya sabía.

El observador no se sigue a sí mismo, de modo que sus propias visitas quedan
fuera sin una condición que lo diga. Es la misma propiedad en la que se apoyan
las notificaciones.

El índice de la épica 10 —`ix_visits_restaurant_occurred_id`— encabeza por
restaurante y sigue por instante, que sirve a la lista cronológica pero no a
esta agrupación: obliga a leer todas las visitas que el lugar recibió alguna
vez. La migración `0108` agrega
`ix_visits_restaurant_public_author (restaurant_id, visibility, author_id,
occurred_at)`, que responde el bloque desde el índice: el prefijo fija
restaurante y visibilidad, y lo que queda ya viene ordenado por persona.

Sobre PostgreSQL 17, con cuatrocientas mil visitas repartidas en trescientos
restaurantes y un observador que sigue a trescientas personas, el plan pasa de
un *bitmap heap scan* de 1334 bloques —todas las visitas del restaurante, más
un *sort* para agrupar— a un *index only scan* de 81 filas que alimenta
directamente el *group aggregate*. Es la comprobación que pedía la épica, y el
motivo por el que la migración existe en vez de reutilizar el índice anterior.

### Fotografías: un solo camino de subida

`app/services/photos.py` es el único lugar por donde una imagen entra al
sistema, y el orden de siempre —validar, almacenar el objeto, abrir la
transacción— está escrito una sola vez.

La reseña ya no sube nada: se escribe sobre una fotografía que existe, y
`create_review` sigue siendo el único punto donde se persiste una reseña, que
es donde los grupos enganchan su emisor de Web Push. **Su firma cambió** con la
épica 10: recibe `photo_id`, `rating`, `text` y `visibility` en vez del archivo
y el nombre del plato, y ya no recibe el proveedor de medios. Un emisor
enganchado ahí tiene que leer el restaurante de la reseña devuelta y no de sus
argumentos.

Quién puede reseñar y con qué visibilidad se valida dentro de la misma
transacción que escribe la fila: la reseña la escribe quien tomó la
fotografía, sólo sobre una de plato, y nunca más visible que ella. La segunda
reseña sobre una misma fotografía se rechaza con la que ya existe, de modo que
la interfaz pueda llevar hasta ella.

El plato es una propiedad de la fotografía y no de la reseña. Mantenerlo en
dos tablas garantizaría que en algún momento discrepen, y la fotografía es lo
que se publica: la reseña es una opinión que se agrega encima. La migración
`0104` lo traslada y retira la columna de `reviews`; la respuesta de una
reseña lo conserva, derivado, de modo que el cambio no se note desde el
cliente.

El grupo de subida lo aporta el cliente y no lo infiere el backend. Agrupar
por una ventana de tiempo produce resultados que el usuario no puede explicar:
dos publicaciones deliberadamente distintas terminan juntas, o una carga lenta
termina partida en dos. La coherencia del grupo se comprueba dentro de la
misma transacción que escribe la fila, de modo que dos solicitudes simultáneas
del mismo acto no puedan dejarlo inconsistente.

Un origen de actividad que agrupa —hoy sólo el de fotografías— cambia tres
cosas respecto de uno que no lo hace, y las tres viven en `ActivitySource`:
sus claves salen de un `GROUP BY` con `MIN` sobre los dos instantes, su
contador cuenta actos distintos y no filas, y el cursor se aplica como
`HAVING` y no como `WHERE`. Lo último no es un detalle: un `WHERE` se
evaluaría sobre las filas antes de que formen un acto y cortaría el acto por
la mitad.

Una fotografía que ya tiene reseña no es actividad por derecho propio. El
origen de actividad de fotografías lo expresa con una condición extra —`NOT
EXISTS` sobre la reseña—, que el contador del perfil aplica también, para que
nunca prometa filas que la lista no va a producir.

### La conversación de una fotografía, que no es actividad

`app/services/comments.py` es el único lugar donde alguien escribe sobre el
contenido de otro. Todo lo demás que la aplicación publica —visitas,
fotografías, reseñas, evaluaciones— es el registro propio de una experiencia
en un restaurante.

**Un comentario no es actividad**, y por eso no tiene `ActivitySource`, no
entra en `ACTIVITY_SOURCES`, no aparece en el feed ni en el perfil de su autor
y no llama a `notify`. La clasificación es la del enunciado general, que
enumera cuatro clases de actividad y define la conversación aparte, y se
sostiene por sí sola: el feed cuenta lo que las personas registran de su
experiencia, y un thread de veinte mensajes inundaría el feed de todos los que
siguen a cualquiera de los que hablan. Avisar a quien publicó la fotografía
sería una clase de aviso distinta de la que define el enunciado —«quien te
sigue publicó algo», «alguien publicó en un restaurante que sigues»— y hay
que decidirla aparte, no deducirla.

**El thread tiene dos niveles.** `parent_id` es nulo en un comentario y
apunta a un comentario de primer nivel en una respuesta; nunca a otra
respuesta. Al crear, el servicio resuelve el padre real: responder a una
respuesta se acepta y queda colgado del comentario al que esa respuesta
pertenece. Un anidamiento sin límite obliga a una consulta recursiva, cuyo
soporte en Aurora DSQL no se da por sentado, y a una interfaz que sobre un
teléfono se queda sin ancho al tercer nivel.

El comentario tampoco tiene visibilidad propia: vive sobre una fotografía
pública y es público. Una tercera columna de visibilidad crearía un objeto
capaz de contradecir aquello de lo que habla, que es el problema que el orden
entre reseña y fotografía ya había evitado.

`_replies_of_page` resuelve las respuestas y los totales de una página
completa en **una sola consulta**: una ventana numera las respuestas de cada
padre y las cuenta a la vez, y el select exterior conserva las primeras
`REPLY_PREVIEW` de cada uno. Una consulta por comentario es el N+1 que el
resto de la API evita, y aquí sería el caso peor, porque una pantalla de
conversación los muestra todos. Una página cuesta tres consultas —autorizar
la fotografía, los comentarios, las respuestas— sea cual sea el número de
comentarios, y hay una prueba que lo afirma con ese número.

`comment_count_column` es una subconsulta correlacionada que las dos
sentencias de `photos.py` incluyen, de modo que el total viaje dentro de la
consulta que ya se estaba ejecutando. Cuenta la conversación completa,
respuestas incluidas, que es el número que una pantalla muestra al lado de la
fotografía.

La lista de primer nivel baja de lo más reciente a lo más antiguo, como el
resto de las colecciones; las respuestas dentro de un comentario suben. No es
una inconsistencia: una pantalla abre por lo último que se dijo, y una
conversación se lee hacia adelante.

### Evaluaciones y la excepción del resumen

Los criterios son dato del código base y no una tabla, por la misma razón que
el catálogo de países: una fila que nadie edita agrega una migración y un seed
sin agregar una capacidad, y un criterio que aparece o desaparece invalida los
promedios ya calculados. La calificación, en cambio, es una fila por criterio
y no una columna por criterio: agregar uno es una entrada más en el catálogo
en vez de una migración de esquema.

**El resumen de la ficha es la única excepción a la regla del observador.**
Todo lo demás en este backend responde según quién pregunta; el promedio de un
restaurante, no. Agrega sólo evaluaciones públicas para todos, porque un
promedio que cambiara con el observador no sería comparable entre
restaurantes, y su autor vería un número que nadie más ve. La consecuencia
está tomada en serio: el contador de evaluaciones de la ficha y la lista de
`/restaurants/{id}/evaluations` describen ese mismo conjunto, de modo que los
tres números coincidan en la misma pantalla.

`_evaluation_summary` era desde #39 el punto único identificado para esto.
Cuando llegaron las evaluaciones, sólo esa función cambió: ni el router ni la
forma de la respuesta lo hicieron.

## Perfil de usuario y regla de visibilidad

`app/services/users.py` es donde vive la regla de visibilidad del proyecto, y
las épicas que agreguen clases de actividad deben respetarla sin volver a
discutirla: **el observador llega desde la sesión y el servicio devuelve sólo
lo que esa persona puede ver**. El cliente no filtra. Un cliente que filtra ya
recibió lo que debía ocultarse.

La regla se aplica antes de paginar y antes de contar. Filtrar después de
limitar devuelve páginas cortas que el cliente no puede distinguir del final
de la colección; contar sin filtrar delata la existencia de lo que no se
muestra. Por eso el contador de actividad de un perfil coincide siempre con lo
que el mismo observador puede listar.

Una persona tiene **una sola forma** en toda la API: identificador, handle,
nombre y nacionalidad. El autor de una actividad, la cabecera de un perfil y
un resultado de la búsqueda son la misma tarjeta, y tres formas distintas
obligarían al cliente a normalizarlas antes de dibujarlas. `user_summary` la
construye desde cualquier consulta que la haya seleccionado.

El estado de seguimiento no forma parte de ese resumen. Lo acompaña donde la
pantalla lo necesita —la búsqueda y el perfil— y no donde no: resolverlo para
el autor de cada item de una página de feed sería una consulta por fila.

La búsqueda de personas no necesita una columna normalizada adicional, a
diferencia de la de restaurantes: el handle ya se almacena en su forma de
comparación, que es justamente el beneficio de la decisión de la épica 1.

El perfil se resuelve en una sola consulta. Los tres contadores y las dos
direcciones del seguimiento son subconsultas correlacionadas sobre `users`, no
una consulta por dato. El handle se normaliza con la función de la épica 1, de
modo que `@Demo`, `demo` y `DEMO` resuelven al mismo perfil.

La actividad resuelve primero el handle y después consulta. Son dos viajes
deliberados: filtrar por el handle dentro del join devolvería una página vacía
para un handle inexistente, que no es la misma respuesta que `404`.

### El envelope de actividad y cómo se agrega una clase

`app/services/activity.py` describe cada clase de actividad como un
`ActivitySource`: qué columnas llevan su autor, su restaurante, su visibilidad
y sus dos instantes, y cómo convertir un conjunto de identificadores en
envelopes. **No guarda una consulta**: el feed y el perfil arman las suyas a
partir de esa descripción, de modo que una clase nueva es una entrada más en
`ACTIVITY_SOURCES` y nada más.

La lectura ocurre en dos pasos a propósito. Primero se unen en SQL las claves
de orden de todos los orígenes, se ordenan y se cortan, que es lo que hace que
una página cueste una consulta acotada por muchas clases que existan. Recién
entonces se leen las filas de las clases que compusieron esa página, una
consulta por clase. Traer páginas completas de cada origen para ordenarlas en
Python multiplicaría el trabajo de cada página por el número de clases.

La deduplicación por doble seguimiento sobrevive al cambio porque la condición
sigue siendo una unión lógica dentro de cada origen, y no dos listas
concatenadas.

El feed excluye además la actividad del propio observador. No es una
optimización: es la misma regla que aplican las notificaciones, donde el autor
siempre queda fuera, y responder de dos maneras a «quién se entera de esto»
sería una incoherencia que el usuario notaría. Lo propio se lee en el perfil.

El costo de una página no depende de cuántos items tenga: una consulta une las
claves de todos los orígenes, y después se leen las clases presentes, una
consulta por clase —la evaluación agrega dos más, agrupadas, para sus
calificaciones y sus fotografías—. Hay una prueba que lo fija comparando el
número de consultas con el número de items.

### Los dos instantes del envelope

`app/services/activity.py` construye el envelope que comparten el feed y el
perfil: `type`, `occurred_at`, `published_at` y el objeto bajo una clave
llamada como su tipo. Una pantalla recorre actividad sin saber qué clases
existen, y una clase nueva no reinterpreta los campos anteriores.

Los dos instantes no son redundantes. Coinciden para una reseña, que se
publica cuando se escribe, pero la visita de la épica 7 trae un momento que el
usuario informa y que puede estar en el pasado. El perfil ordena por
`occurred_at` porque es la cronología de esa persona; el feed ordena por
`published_at` porque registrar hoy una visita de hace un mes no debe dejarla
enterrada un mes atrás en el feed de quienes siguen a su autor.

`review_activity_statement` incorpora la condición de visibilidad, y no la
deja al llamador: ninguna consulta puede olvidarla. Los llamadores sólo
restringen más —por autor, por seguimiento—. Cada épica que agregue una clase
de actividad agrega aquí su fuente.

### Cursores

`app/services/cursors.py` codifica la clave de orden de la última fila que el
cliente recibió. El valor es opaco a propósito: su contenido pertenece a la
consulta que lo emitió, y un cliente que lo interprete queda atado a ella.
Base64url lo hace utilizable dentro de un query string.

El códec vive fuera del feed porque el perfil lo usa con otra clave de orden,
y las colecciones de restaurantes lo usarán con una clave que no es temporal.

## Notificaciones dirigidas

`app/services/notifications.py` responde una sola pregunta —a quién
corresponde avisar de una actividad— y se detiene ahí. Enviar es el emisor de
Web Push de cada grupo, que vive en el mismo proceso, y **por eso esto es una
función y no un endpoint**: uno que respondiera «quiénes deben enterarse de
esto» publicaría el grafo de seguidores a cualquiera con sesión.

`resolve_recipients` recibe autor, restaurante y visibilidad, que es lo que
toda clase de actividad tiene, de modo que agregar una clase no cambia nada
aquí. La deduplicación ocurre en la consulta, como una unión lógica de ambas
condiciones de seguimiento y no como dos listas concatenadas después: quien
sigue al autor y al restaurante es un destinatario, no dos. Devuelve
identificadores de usuario y no suscripciones, porque la tabla de
suscripciones es de cada grupo y este módulo no debe conocerla.

El enganche es único. Antes de la épica 14 vivía dentro de la creación de una
reseña, lo que era razonable mientras la reseña era la única clase de
actividad; con cinco habría obligado a cada grupo a repetir su llamada cinco
veces y a descubrir por su cuenta las cuatro nuevas. Ahora los cinco servicios
invocan `notify` **después** de que su transacción se confirma, nunca dentro:
avisar sobre una escritura que después revierte produce avisos de contenido
que no existe, y el reintento de una transacción bajo Aurora DSQL puede
ejecutar su cuerpo más de una vez. Un emisor que falla se registra y no
propaga: no puede deshacer una actividad que ya está escrita.

El aviso de un grupo de fotografías lo dispara la primera del grupo, y el
identificador que viaja es el del grupo. Con una solicitud por archivo el
backend no puede saber que el acto está completo, y esperar a que lo esté
introduciría trabajo diferido que este backend no tiene.

**La reseña no avisa.** Es la única clase de actividad que no lo hace, y la
razón es la misma que ordena el feed: la fotografía de la que habla ya avisó
cuando se publicó, y el feed muestra a ambas como una sola entrada, porque una
fotografía reseñada deja de ser actividad propia. Un segundo aviso
contradiría lo que el seguidor va a ver al abrirlo. La regla, entonces, no es
«una actividad, un aviso» sino **una entrada del feed, un aviso**, que es la
misma deduplicación que el enunciado pide.

## Configuración

`app/core/config.py` define `Settings`, que hereda de `BaseSettings`. Pydantic
Settings lee las variables de entorno, convierte tipos y ejecuta validaciones
al importar `settings`. La
[documentación oficial de Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
describe esa resolución.

Las variables se agrupan conceptualmente así:

- ambiente: `ENVIRONMENT`;
- base: `DATABASE_BACKEND`, `DATABASE_URL`, `AURORA_DSQL_*` y opciones del pool;
- sesión: `JWT_SECRET`, `JWT_EXPIRATION_MINUTES` y `COOKIE_SECURE`;
- navegador: `CORS_ORIGINS`;
- datos locales: `SEED_DEMO_DATA`; y
- medios: `MEDIA_STORAGE_BACKEND`, `MEDIA_LOCAL_PATH`,
  `MEDIA_MAX_UPLOAD_BYTES`, `MEDIA_S3_BUCKET`, `MEDIA_S3_REGION`,
  `MEDIA_S3_PREFIX` y `MEDIA_PRESIGNED_URL_EXPIRATION_SECONDS`.

En producción, la configuración rechaza el secreto de desarrollo, exige
cookies `Secure` e impide habilitar las fixtures. Los secretos se inyectan desde
la plataforma: no se agregan a archivos versionados ni a valores `VITE_*`,
porque estos últimos terminan en el bundle público del frontend.

Aunque el gateway evita CORS en el camino normal, la configuración CORS se
conserva para el modo en que Vite se ejecuta directamente y la API se abre en
otro origen. Los mismos valores son orígenes explícitamente confiables para las
operaciones mutables de autenticación; CORS y la validación CSRF son controles
distintos.

## Persistencia con SQLAlchemy Core

El proyecto usa la API **Core**, no el ORM. Las tablas son objetos `Table`
registrados en `metadata`; las consultas se construyen con expresiones como
`select(users)` y se ejecutan mediante `Connection`. SQLAlchemy describe Core
como su toolkit base para conectividad, expresiones SQL y resultados en el
[tutorial unificado](https://docs.sqlalchemy.org/en/20/tutorial/).

Esta elección mantiene explícitos SQL, transacciones y restricciones, y reduce
la superficie que habrá que comprobar al migrar a un servicio compatible con
PostgreSQL pero no idéntico como Aurora DSQL.

### Engine, conexiones y transacciones

`app/db/engine.py` es la frontera entre la aplicación y el proveedor de datos:

- para PostgreSQL crea `postgresql+psycopg`;
- para DSQL carga opcionalmente el adaptador oficial y autenticación IAM;
- configura un pool acotado, `pool_pre_ping` y reciclaje de conexiones; y
- permite que Alembic use un pool de una conexión.

`app/db/session.py` crea el engine una sola vez en scope de módulo. Uvicorn lo
reutiliza durante la vida del proceso y Lambda puede reutilizarlo durante warm
starts. Cada entorno concurrente de Lambda posee su propio engine y pool.

Usa el contexto según la intención:

```python
with engine.connect() as connection:
    result = connection.execute(select(users))

with engine.begin() as connection:
    connection.execute(users.insert().values(...))
```

`connect()` es adecuado para lecturas o cuando el código controla la
transacción. `begin()` confirma al salir si no hubo error y revierte ante una
excepción. No mantengas una conexión global: el objeto global es el `Engine`,
que administra el pool. La documentación de
[Engine](https://docs.sqlalchemy.org/en/20/core/engines.html) desarrolla esta
separación.

`app/db/retry.py` reintenta únicamente `SQLSTATE 40001`, que representa un
conflicto de serialización/concurrencia. La operación se ejecuta nuevamente en
una transacción nueva, con backoff acotado. Esto sólo es correcto si el caso de
uso es idempotente: login conserva el mismo UUID de sesión durante sus
reintentos, logout actualiza condicionalmente una fila aún no revocada y el
CRUD de restaurantes fija UUID/timestamp y repite el conjunto completo de
cambios.

## Esquema y migraciones con Alembic

`app/db/schema.py` representa el esquema deseado actualmente. Los archivos de
`migrations/versions/` representan el historial para alcanzarlo desde una base
vacía o antigua. Son responsabilidades relacionadas, pero no intercambiables:
crear una columna solo en `schema.py` no modifica ninguna base existente.

Flujo para un cambio de esquema:

1. modifica la metadata en `app/db/schema.py`;
2. genera una revisión candidata con Alembic;
3. lee y corrige `upgrade()` y `downgrade()`;
4. prueba la revisión sobre PostgreSQL aislado; y
5. incluye metadata, migración y pruebas en el mismo pull request.

Con los servicios iniciados, desde la raíz del repositorio:

```console
docker compose run --rm --entrypoint alembic backend current
docker compose run --rm --entrypoint alembic backend check
docker compose run --rm --entrypoint alembic backend revision --autogenerate -m "describe el cambio"
docker compose run --rm --entrypoint alembic backend upgrade head
docker compose run --rm --entrypoint alembic backend downgrade -1
```

- `current` muestra la revisión aplicada;
- `check` detecta diferencias que requerirían una revisión;
- `revision --autogenerate` compara la base con `metadata` y propone código;
- `upgrade head` aplica todas las revisiones pendientes; y
- `downgrade -1` intenta revertir la última revisión.

Autogenerate produce una **migración candidata**, no una migración garantizada.
Alembic exige revisarla porque no todos los cambios pueden inferirse de forma
segura. Consulta sus [capacidades y límites de
autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html).

No edites una migración que ya se aplicó en un entorno compartido. Crea una
nueva revisión. Si el cambio transforma o elimina datos, el PR debe documentar
compatibilidad, estrategia de transición y reversibilidad.

El contenedor local ejecuta `alembic upgrade head` antes de Uvicorn. Lambda no
lo hace: en AWS las migraciones son un job separado del despliegue y la función
no recibe permisos DDL.

## Cómo agregar un endpoint

1. Crea o amplía un módulo en `app/api/` y declara su `APIRouter`.
2. Define modelos Pydantic explícitos para entrada y salida en `app/schemas/`.
3. Mantén en el router las decisiones HTTP y mueve reglas de varios pasos a
   `app/services/` cuando aparezcan.
4. Construye consultas con SQLAlchemy Core y delimita la transacción.
5. Si cambia el esquema, agrega la revisión Alembic correspondiente.
6. Incluye el router en `app/main.py` bajo `/api/v1`.
7. Agrega pruebas de éxito, validación, autorización y errores relevantes.
8. Comprueba el contrato generado en `/docs` y `/openapi.json`.

Usa rutas relativas `/api/v1/...` desde el frontend. No incorpores hosts,
puertos ni nombres de ambiente en los módulos de la API.

## Estrategia de pruebas

La suite combina niveles distintos:

- `test_health.py`, `test_auth.py` y `test_restaurants.py`: contrato HTTP rápido
  con `TestClient` y colaboradores reemplazados cuando corresponde;
- `test_security.py` y `test_retry.py`: claims obligatorios, expiración y
  política de reintentos;
- `test_config.py`: invariantes de configuración;
- `test_database.py`: construcción de engines PostgreSQL/DSQL;
- `test_seed.py`: idempotencia del seed;
- `test_media_storage.py`: contrato local/S3 sin una cuenta AWS;
- `test_reviews.py` y `test_reviews_service.py`: multipart, autorización,
  imágenes, fallas parciales y compensación;
- `test_integration.py`: ciclo completo de migraciones, seed, autenticación y
  persistencia de restaurantes/reseñas contra PostgreSQL real; y
- `test_lambda.py`: eventos API Gateway HTTP API v2, cookies y un upload
  multipart binario procesados por Mangum.

Para desarrollo rápido:

```console
cd backend
uv sync --group dev
uv run pytest
```

Para la suite completa con PostgreSQL aislado:

```console
docker compose --profile test up --build --abort-on-container-exit --exit-code-from backend-tests backend-tests
docker compose --profile test down --remove-orphans
```

No uses `-v` para limpiar este perfil: la opción elimina también los volúmenes
de los servicios fuera del perfil, incluido `postgres-data`. La base `test-db`
es efímera y desaparece al retirar su contenedor.

Una prueba unitaria no reemplaza la prueba de migración. Todo cambio de tablas,
restricciones o comportamiento dependiente de PostgreSQL requiere cobertura de
integración.

## Portabilidad hacia Lambda y Aurora DSQL

Estas reglas mantienen abierta la migración futura:

- la lógica depende de FastAPI/ASGI, no de objetos propios de Uvicorn;
- `app.main.handler` adapta la aplicación completa mediante Mangum;
- el código de API recibe un engine ya configurado y no genera tokens IAM;
- las dependencias DSQL viven en el extra opcional `.[aws]`;
- las conexiones se administran mediante pools pequeños y reciclables;
- las migraciones no se ejecutan durante una invocación Lambda;
- las transacciones de escritura deben ser pequeñas y reintentables;
- las relaciones se mantienen en la aplicación, sin foreign keys ni cascadas;
- los bytes viven en storage externo y la base conserva sólo una clave opaca; y
- cada uso de una característica PostgreSQL debe comprobarse contra las
  capacidades de DSQL.

La guía [AWS Lambda y Aurora DSQL](docs/aws-lambda.md) detalla IAM, packaging,
observabilidad y las diferencias de compatibilidad que deben verificarse.

## Convenciones que deben preservarse

- No guardar secretos, tokens, passwords ni claves privadas en Git.
- No devolver hashes de contraseña ni incluir datos sensibles en JWT o logs.
- No aceptar el secreto de desarrollo ni cookies sin `Secure` en producción.
- No editar migraciones que ya hayan sido compartidas.
- No ejecutar DDL desde la función Lambda.
- No introducir el ORM o acceso SQL directo fuera de SQLAlchemy sin una
  decisión arquitectónica explícita.
- No depender de memoria local entre solicitudes: Lambda puede descartar el
  entorno después de cualquier invocación.
- No dividir el monolito en servicios solo por organización de carpetas; los
  módulos son límites de código dentro de una aplicación.

## Referencias oficiales

- [FastAPI](https://fastapi.tiangolo.com/)
- [FastAPI: aplicaciones en varios archivos](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [Pydantic: modelos](https://docs.pydantic.dev/latest/concepts/models/)
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Uvicorn](https://www.uvicorn.org/)
- [SQLAlchemy: tutorial Core y ORM](https://docs.sqlalchemy.org/en/20/tutorial/)
- [SQLAlchemy: configuración del Engine](https://docs.sqlalchemy.org/en/20/core/engines.html)
- [Alembic](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Alembic: autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [Psycopg 3](https://www.psycopg.org/psycopg3/docs/)
- [argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/api.html)
- [PyJWT](https://pyjwt.readthedocs.io/en/stable/)
- [Mangum](https://mangum.fastapiexpert.com/)
- [FastAPI: archivos y `UploadFile`](https://fastapi.tiangolo.com/tutorial/request-files/)
- [Pillow](https://pillow.readthedocs.io/)
- [Boto3: `upload_fileobj`](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/upload_fileobj.html)
- [Amazon S3: URLs prefirmadas](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [Pytest](https://docs.pytest.org/)
