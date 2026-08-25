# Despliegue en AWS Lambda y migración a Aurora DSQL

Esta guía registra las decisiones de arquitectura del issue #8. No hace falta
cambiar rutas ni casos de uso al migrar: Uvicorn sirve `app.main:app` y Lambda
invoca `app.main.handler` mediante Mangum.

## Modelo mental de la migración

**Serverless** no significa que no existan servidores. Significa que AWS
administra su aprovisionamiento y ejecuta el código de la función cuando recibe
un evento. La aplicación no mantiene un proceso Uvicorn permanentemente
encendido ni administra una máquina virtual. La
[introducción oficial a Lambda](https://docs.aws.amazon.com/lambda/latest/dg/concepts-basics.html)
describe este modelo de ejecución.

FastAPI es una aplicación [ASGI](https://asgi.readthedocs.io/en/latest/), una
interfaz estándar entre aplicaciones web Python y sus servidores. En desarrollo,
Uvicorn traduce HTTP a ASGI. En AWS, API Gateway traduce HTTP a un evento de
Lambda y [Mangum](https://mangum.fastapiexpert.com/) adapta ese evento a ASGI.
La misma aplicación FastAPI queda al final de ambos caminos:

```text
Desarrollo: cliente -> Uvicorn --------------------> FastAPI -> SQLAlchemy -> PostgreSQL
AWS:        cliente -> API Gateway -> Lambda/Mangum -> FastAPI -> SQLAlchemy -> Aurora DSQL
```

Lambda puede crear un entorno nuevo para una invocación (**cold start**) o
reutilizar uno ya inicializado (**warm start**). La aplicación puede aprovechar
la reutilización para mejorar el rendimiento, pero no debe asumir que ocurrirá.

API Gateway usa el formato de evento HTTP API v2, que representa la ruta, los
encabezados, las cookies y el cuerpo de la solicitud. AWS documenta tanto ese
[formato como la respuesta de la integración Lambda](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html).

En esta guía aparecen dos usos de la palabra **migración**:

- migrar la arquitectura es cambiar dónde se ejecutan la API y la base de
  datos; y
- una migración de Alembic es un cambio versionado del esquema de la base de
  datos.

Aurora DSQL es una base relacional distribuida y serverless para cargas
transaccionales. Es compatible con herramientas y parte de la semántica de
PostgreSQL, pero no implementa todas sus funciones. La documentación de AWS
explica su [relación con PostgreSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with.html).

## Decisiones

- **API:** una función Lambda para la aplicación FastAPI completa, detrás de
  API Gateway HTTP API con payload v2. Así se conserva el monolito y su
  enrutamiento; dividir por endpoint queda fuera de esta migración y se
  evaluará solo si aparecen necesidades de escalado distintas.
- **Empaquetado:** archivo ZIP construido en Linux con AWS SAM
  (`sam build --use-container`). Psycopg contiene binarios nativos, por lo que
  no se debe construir el artefacto directamente en macOS o Windows.
- **Base de datos:** PostgreSQL local usa el dialecto `postgresql+psycopg` y
  `DATABASE_URL`. Un dialecto traduce las operaciones de SQLAlchemy a las
  particularidades de una base. Aurora DSQL usa el adaptador oficial
  `aurora-dsql-sqlalchemy`, que genera credenciales IAM por conexión, valida TLS
  y resuelve las diferencias del dialecto.
- **Migraciones:** Alembic corre como un paso separado y único del despliegue;
  nunca durante un cold start. La aplicación Lambda no necesita permisos DDL.
- **Sesiones:** el JWT identifica mediante `jti` una fila de `auth_sessions` en
  la base compartida. Logout y caducación no dependen de la memoria de Lambda.
- **Fotografías:** producción usa un bucket S3 privado. `photos.storage_key`
  conserva una clave opaca y la ruta estable de la API autoriza antes de emitir
  una URL prefirmada breve. El filesystem sólo es un adaptador de desarrollo;
  no se usa el almacenamiento efímero de Lambda como persistencia.
- **Secretos:** los valores de producción se inyectan en el despliegue y no se
  guardan en Git. `JWT_SECRET` se obtiene de AWS Secrets Manager o del almacén
  de secretos del pipeline y se entrega como variable cifrada de Lambda. Si el
  secreto se resuelve mediante una referencia dinámica de CloudFormation, su
  rotación requiere actualizar la función para volver a resolverlo.
- **Observabilidad:** CloudWatch recibe logs de Lambda y access logs JSON de API
  Gateway. Los logs registran eventos; las métricas resumen valores en el
  tiempo; y las trazas siguen una solicitud entre componentes. En producción
  se habilita AWS X-Ray (`Tracing: Active`), retención explícita del log group,
  alarmas de errores/throttling y una alarma de 5xx del API. Los logs no deben
  contener cookies, JWT ni credenciales.

## Configuración

La aplicación solo lee variables de entorno; no necesita archivos locales en
runtime. Para PostgreSQL:

```text
ENVIRONMENT=production
DATABASE_BACKEND=postgresql
DATABASE_URL=postgresql+psycopg://...
DATABASE_POOL_SIZE=1
DATABASE_MAX_OVERFLOW=0
DATABASE_POOL_RECYCLE_SECONDS=3300
JWT_SECRET=<inyectado por la plataforma>
COOKIE_SECURE=true
CORS_ORIGINS=https://app.example.com
SEED_DEMO_DATA=false
MEDIA_STORAGE_BACKEND=s3
MEDIA_S3_BUCKET=<bucket-privado>
MEDIA_S3_REGION=<region>
MEDIA_S3_PREFIX=foodie
MEDIA_PRESIGNED_URL_EXPIRATION_SECONDS=300
```

Para DSQL se reemplaza la configuración de conexión:

```text
DATABASE_BACKEND=aurora-dsql
AURORA_DSQL_ENDPOINT=<cluster-id>.dsql.<region>.on.aws
AURORA_DSQL_USER=foodie_app
AURORA_DSQL_DATABASE=postgres
```

`DATABASE_URL` no contiene un token DSQL. El adaptador obtiene credenciales
temporales de la execution role de Lambda. El endpoint permite descubrir la
región, por lo que no se requiere una variable de región propia.

El engine y su pool se crean en scope de módulo. Los objetos creados fuera del
handler pueden sobrevivir en un warm start, aunque la aplicación nunca debe
depender de que eso ocurra. Este comportamiento está descrito en el
[ciclo de vida del entorno de Lambda](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html).

Una instancia warm reutiliza el engine y su pool; instancias concurrentes
tienen pools independientes. El tamaño recomendado inicial es una conexión y
cero overflow por instancia. Se puede aumentar después de medir concurrencia y
latencia. `pool_pre_ping` descarta conexiones cerradas y `pool_recycle=3300`
evita reutilizarlas después de 55 minutos, antes del máximo de una hora de DSQL.

## Sesiones y revocación en Lambda

Cada request autenticado valida primero la firma y `exp` del JWT y después
consulta `auth_sessions` en Aurora DSQL. Una sesión sólo es válida si la fila
existe, corresponde a `sub`, no está revocada y tampoco venció en la base. Esta
consulta deliberada permite que un logout confirmado sea visible para todas
las instancias concurrentes.

El engine puede reutilizarse durante un warm start, pero ninguna allowlist o
denylist se guarda en variables del módulo. Un cold start y dos instancias en
paralelo observan el mismo estado durable. Las escrituras de login y logout son
cortas y `app/db/retry.py` reintenta conflictos `SQLSTATE 40001`; los UUID se
conservan durante el reintento y el update de revocación es idempotente.

API Gateway HTTP API v2 representa `Set-Cookie` como la colección `cookies` de
la respuesta; Mangum realiza esa traducción. Cuando CloudFront se incorpore,
el comportamiento `/api/*` debe reenviar cookies, permitir los métodos HTTP y
mantener el caché deshabilitado. Nunca se debe incluir JWT, `Cookie` o
`Set-Cookie` en logs.

## Fotografías, payload binario y S3

Mangum decodifica el cuerpo base64 del evento HTTP API v2 y entrega el multipart
a la misma ruta FastAPI; `tests/test_lambda.py` verifica ese recorrido. API
Gateway mantiene límites de payload que incluyen el cuerpo codificado y el
overhead multipart. Por eso `MEDIA_MAX_UPLOAD_BYTES` debe configurarse por
debajo del límite efectivo del API, no igualarlo mecánicamente. AWS documenta
el manejo de [contenido binario con API Gateway y
Lambda](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-payload-encodings.html).

La entrega 2 conserva el upload a través del backend para ofrecer un contrato
sencillo. Si las mediciones o límites de la entrega 4 lo requieren, el flujo
puede evolucionar a: solicitar autorización, subir directamente a S3 con una
URL prefirmada y confirmar la reseña. `reviews`, `photos`, `storage_key` y la
ruta estable de lectura no tienen que cambiar; sólo se agrega el protocolo de
carga directa y su compensación de objetos no confirmados.

El rol de ejecución de Lambda necesita únicamente operaciones de objeto sobre
el prefix configurado (`s3:PutObject`, `s3:GetObject` y `s3:DeleteObject`), no
administración del bucket. Boto3 usa automáticamente las credenciales de ese
rol. Las URLs prefirmadas heredan sus permisos y caducan según
`MEDIA_PRESIGNED_URL_EXPIRATION_SECONDS`; no se persisten ni se registran.

## IAM y roles de base de datos

Un **rol de ejecución** (_execution role_) es la identidad IAM que Lambda asume
al ejecutar la función. No es lo mismo que un rol interno de PostgreSQL/DSQL:
IAM autoriza la conexión al cluster y DSQL usa el rol de base de datos para
decidir qué tablas y operaciones permite. La aplicación obtiene credenciales
temporales a partir del rol de ejecución; no guarda una contraseña permanente de
base de datos.

No se usa `admin` desde la API:

1. Un operador se conecta una vez como `admin` y crea el rol de base de datos
   `foodie_app` con los privilegios DML mínimos sobre el esquema de la app.
2. Se asocia ese rol de base de datos a la execution role de Lambda mediante
   `AWS IAM GRANT`.
3. La execution role recibe `dsql:DbConnect` únicamente sobre el ARN del
   cluster. `dsql:DbConnectAdmin` no se asigna a Lambda.
4. Como las migraciones existentes crean objetos en el esquema `public`, el job
   separado de Alembic se conecta como `admin` con una IAM role de despliegue
   que sí tiene `dsql:DbConnectAdmin`. Esa role no se comparte con la función y
   solo se asume durante el despliegue.

Los detalles oficiales están en
[autenticación y roles de Aurora DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/authentication-authorization.html).

## Build y despliegue

El artefacto de Lambda debe instalar el extra `aws` del backend:

```console
cd backend
python -m pip install '.[aws]' --target build/package
```

En el flujo definitivo se recomienda que AWS SAM haga esa instalación dentro
de su contenedor Linux. La definición SAM debe usar:

```yaml
Runtime: python3.13
Handler: app.main.handler
Architectures: [x86_64]
Tracing: Active
Events:
  Api:
    Type: HttpApi
```

Las variables anteriores se declaran en `Environment.Variables`, recibiendo
endpoints y secretos como parámetros del stack o del pipeline. El ZIP contiene
`app/` y todas las dependencias en su raíz. Docker Compose continúa siendo solo
una herramienta de desarrollo y pruebas.

Después de crear o actualizar el cluster, el pipeline ejecuta desde un job
efímero con la identidad de migraciones:

```console
cd backend
DATABASE_BACKEND=aurora-dsql \
AURORA_DSQL_ENDPOINT="$AURORA_DSQL_ENDPOINT" \
AURORA_DSQL_USER=admin \
alembic upgrade head
```

DSQL no implementa todo PostgreSQL. "Compatible" permite reutilizar muchas
consultas y herramientas, pero no promete equivalencia completa. Cada nueva
migración debe compilarse y probarse contra un cluster de integración. En
particular, el adaptador traduce índices a creación asíncrona y omite foreign
keys; si el dominio incorpora foreign keys, la integridad referencial también
debe protegerse en la aplicación. Las transacciones de escritura deben ser
pequeñas, idempotentes y reintentables ante conflictos de control de
concurrencia optimista.

## Validación mínima

`tests/test_lambda.py` entrega a Mangum eventos HTTP API v2 realistas y exige
que `GET /healthz`, las cookies de autenticación, el listado protegido y una
carga multipart binaria se comporten igual que bajo Uvicorn. Antes de
desplegar:

```console
cd backend
pytest tests/test_lambda.py tests/test_database.py tests/test_config.py
```

Después del despliegue:

```console
curl --fail-with-body https://<api-id>.execute-api.<region>.amazonaws.com/healthz
```

La respuesta esperada es `{"status":"ok"}`. Luego se prueba un login contra la
base migrada, se confirma el access log correlacionado con el request ID y se
verifica que no exista seed de demostración.

## Referencias oficiales

- [Cómo funciona AWS Lambda](https://docs.aws.amazon.com/lambda/latest/dg/concepts-basics.html)
- [Integración de API Gateway HTTP API con Lambda](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html)
- [Documentación de Mangum](https://mangum.fastapiexpert.com/)
- [Introducción a Aurora DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/getting-started.html)
- [Adaptadores y conectores de Aurora DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/aws-sdks.html)
- [Adaptador oficial de SQLAlchemy](https://github.com/awslabs/aurora-dsql-orms/tree/main/python/sqlalchemy)
- [Cuotas y límites de DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/CHAP_quotas.html)
- [Buenas prácticas de Lambda](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Empaquetado ZIP de Python](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html)
- [Boto3: carga administrada desde un objeto de archivo](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/upload_fileobj.html)
- [Amazon S3: URLs prefirmadas](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
