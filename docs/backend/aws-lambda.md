# Despliegue en AWS Lambda y migración a Aurora DSQL

Esta guía registra las decisiones de arquitectura del issue #8. No hace falta
cambiar rutas ni casos de uso al migrar: Uvicorn sirve `app.main:app` y Lambda
invoca `app.main.handler` mediante Mangum.

## Decisiones

- **API:** una función Lambda para la aplicación FastAPI completa, detrás de
  API Gateway HTTP API con payload v2. Dividir por endpoint queda fuera de esta
  migración y se evaluará solo si aparecen necesidades de escalado distintas.
- **Empaquetado:** archivo ZIP construido en Linux con AWS SAM
  (`sam build --use-container`). Psycopg contiene binarios nativos, por lo que
  no se debe construir el artefacto directamente en macOS o Windows.
- **Base de datos:** PostgreSQL local usa el dialecto `postgresql+psycopg` y
  `DATABASE_URL`. Aurora DSQL usa el adaptador oficial
  `aurora-dsql-sqlalchemy`, que genera credenciales IAM por conexión, valida TLS
  y resuelve las diferencias del dialecto.
- **Migraciones:** Alembic corre como un paso separado y único del despliegue;
  nunca durante un cold start. La aplicación Lambda no necesita permisos DDL.
- **Secretos:** los valores de producción se inyectan en el despliegue y no se
  guardan en Git. `JWT_SECRET` se obtiene de AWS Secrets Manager o del almacén
  de secretos del pipeline y se entrega como variable cifrada de Lambda. Si el
  secreto se resuelve mediante una referencia dinámica de CloudFormation, su
  rotación requiere actualizar la función para volver a resolverlo.
- **Observabilidad:** CloudWatch recibe logs de Lambda y access logs JSON de API
  Gateway. En producción se habilita AWS X-Ray (`Tracing: Active`), retención
  explícita del log group, alarmas de errores/throttling y una alarma de 5xx del
  API. Los logs no deben contener cookies, JWT ni credenciales.

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
SEED_DEMO_USER=false
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

El engine y su pool se crean en scope de módulo. Una instancia warm de Lambda
los reutiliza; instancias concurrentes tienen pools independientes. El tamaño
recomendado inicial es una conexión y cero overflow por instancia. Se puede
aumentar después de medir concurrencia y latencia. `pool_pre_ping` descarta
conexiones cerradas y `pool_recycle=3300` evita reutilizarlas después de 55
minutos, antes del máximo de una hora de DSQL.

## IAM y roles de base de datos

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

```sh
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

```sh
cd backend
DATABASE_BACKEND=aurora-dsql \
AURORA_DSQL_ENDPOINT="$AURORA_DSQL_ENDPOINT" \
AURORA_DSQL_USER=admin \
alembic upgrade head
```

DSQL no implementa todo PostgreSQL. Cada nueva migración debe compilarse y
probarse contra un cluster de integración. En particular, el adaptador traduce
índices a creación asíncrona y omite foreign keys; si el dominio incorpora
foreign keys, la integridad referencial también debe protegerse en la
aplicación. Las transacciones de escritura deben ser pequeñas, idempotentes y
reintentables ante conflictos de control de concurrencia optimista.

## Validación mínima

`tests/test_lambda.py` entrega a Mangum un evento HTTP API v2 realista y exige
que `GET /healthz` responda igual que bajo Uvicorn. Antes de desplegar:

```sh
cd backend
pytest tests/test_lambda.py tests/test_database.py tests/test_config.py
```

Después del despliegue:

```sh
curl --fail-with-body https://<api-id>.execute-api.<region>.amazonaws.com/healthz
```

La respuesta esperada es `{"status":"ok"}`. Luego se prueba un login contra la
base migrada, se confirma el access log correlacionado con el request ID y se
verifica que no exista seed de demostración.

## Referencias oficiales

- [Adaptadores y conectores de Aurora DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/aws-sdks.html)
- [Adaptador oficial de SQLAlchemy](https://github.com/awslabs/aurora-dsql-orms/tree/main/python/sqlalchemy)
- [Cuotas y límites de DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/CHAP_quotas.html)
- [Buenas prácticas de Lambda](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [Empaquetado ZIP de Python](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html)
