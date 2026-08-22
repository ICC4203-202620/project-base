# Backend: desarrollo local

## Inicio rápido

Necesitas Docker Desktop (o Docker Engine con Compose).

```sh
docker compose up --build
```

La API queda en `http://localhost:8000`, con OpenAPI en `/docs`. El contenedor
aplica las migraciones y, solo en la configuración de Docker Compose de
desarrollo, crea el usuario de prueba si no existe: correo `demo@example.com`,
contraseña `demo-password`. El login es
`POST /api/v1/auth/login`; devuelve 204 y establece una cookie `session`
`HttpOnly`. El seed usa un UUID generado por la aplicación, no una contraseña
ni identificador de producción. No incluyan secretos ni contraseñas de
producción en Git.

El seed está desactivado por defecto. Para activarlo fuera de Docker Compose,
establece `SEED_DEMO_USER=true`; ejecutarlo nuevamente no duplica al usuario,
porque primero verifica el email.

Para pruebas locales con Python 3.13 y uv:

```sh
cd backend
uv sync --group dev
uv run pytest
```

### Pruebas de integración

Las pruebas normales no requieren una base de datos; las que llevan la marca
`integration` se omiten si `TEST_DATABASE_URL` no está configurada. Para
ejecutar la suite completa contra un PostgreSQL aislado, desde la raíz:

```sh
docker compose --profile test up --build --abort-on-container-exit --exit-code-from backend-tests backend-tests
docker compose --profile test down -v --remove-orphans
```

El perfil `test` crea `test-db` sin volumen persistente y el servicio
`backend-tests` aplica las migraciones, ejecuta el seed y corre Pytest. Cubre
la existencia de la tabla `users`, el usuario seed y un login real contra la
base migrada; no usa la base `db` de desarrollo.

## Teléfono: HTTPS y mDNS

Las cookies con `Secure` requieren HTTPS. En macOS (Bonjour) y Linux con
Avahi, el hostname mDNS del equipo suele estar disponible como
`nombre-del-equipo.local`. El teléfono y computador deben estar en la misma
red y la red Wi-Fi no debe tener aislamiento de clientes.

1. Comprueba el hostname mDNS. En macOS, ejecuta:

   ```sh
   scutil --get LocalHostName
   ```

   Si devuelve `mi-mac`, usa `mi-mac.local` en los pasos siguientes.

   En Debian, Ubuntu y derivados, instala y activa Avahi si aún no está
   disponible. Estos comandos piden la contraseña de administrador:

   ```sh
   sudo apt update
   sudo apt install avahi-daemon avahi-utils
   sudo systemctl enable --now avahi-daemon
   hostnamectl --static
   systemctl status avahi-daemon --no-pager
   ```

   Si el nombre devuelto por `hostnamectl --static` es `mi-pc`, prueba que
   Avahi lo publique con `avahi-resolve -n mi-pc.local`. La salida debe mostrar
   una dirección IP de la red local. Si el servicio no queda activo, revisa el
   mensaje de `systemctl status`; en redes corporativas también puede ser
   necesario permitir mDNS (UDP 5353) en el firewall local.
2. Instala mkcert y confía su CA local. En macOS:

   ```sh
   brew install mkcert
   mkcert -install
   ```

   En Linux instala mkcert con el gestor de paquetes y ejecuta también
   `mkcert -install`. Para que iOS o Android confíen el certificado, instala
   la CA de mkcert en el dispositivo solo para desarrollo.
3. Desde la raíz, genera el certificado. El helper guarda la clave y el
   certificado bajo `certs/`, directorio ignorado por Git:

   ```sh
   ./scripts/create-local-certificate.sh mi-equipo.local
   ```

4. Inicia la API con TLS y cookie segura. Declara el origen exacto del frontend
   si se sirve desde otro puerto:

   ```sh
   LOCAL_TLS=true COOKIE_SECURE=true \
   CORS_ORIGINS=https://mi-equipo.local:5173 \
   docker compose up --build
   ```

5. Desde el teléfono abre `https://mi-equipo.local:8000/healthz` y luego
   `https://mi-equipo.local:8000/docs`. El login debe responder con una cookie
   `Secure; HttpOnly; SameSite=Lax`.

Si el hostname no resuelve, prueba primero la IP LAN para diagnosticar red y
firewall, pero genera un nuevo certificado que incluya esa IP antes de usar
HTTPS. `localhost` desde el teléfono siempre significa el propio teléfono.

### Windows + WSL

WSL2 no siempre publica mDNS ni puertos hacia el teléfono. Usa Docker Desktop
con integración WSL y el nombre o IP LAN del host Windows; el certificado debe
incluir exactamente el nombre o IP que abre el teléfono.

En Windows 11, el modo de red reflejado puede simplificar esta conexión. El
archivo `.wslconfig` no está dentro de Linux ni en `/home`: está en el perfil
del usuario de **Windows**, por ejemplo
`C:\Users\ana\.wslconfig` (también se puede abrir desde PowerShell con
`notepad $env:USERPROFILE\.wslconfig`). Crea o edita ese archivo para incluir:

```ini
[wsl2]
networkingMode=mirrored
```

Guarda el archivo, abre PowerShell y ejecuta `wsl --shutdown`. Luego vuelve a
abrir la distribución WSL y Docker Desktop. Si esa opción no está disponible en
tu versión de Windows/WSL, omítela y usa la IP LAN o nombre del host Windows.

Si el teléfono no logra conectar, comprueba que Docker publica el puerto en el
host Windows y permite conexiones TCP entrantes al puerto 8000 en el Firewall
de Windows. La ruta gráfica es **Seguridad de Windows → Firewall y protección
de red → Configuración avanzada → Reglas de entrada**; crea una regla de puerto
TCP 8000 solo para redes privadas si tu configuración lo requiere.

### Diagnóstico rápido

* `curl -k https://mi-equipo.local:8000/healthz` desde el computador descarta
  errores de certificado y verifica que Uvicorn está sirviendo TLS.
* Si funciona en el computador pero no en el teléfono, revisa mDNS, la CA
  instalada en el teléfono, firewall y aislamiento Wi-Fi.
* Si la API responde pero el navegador no conserva la sesión, verifica que el
  frontend use HTTPS, que `COOKIE_SECURE=true` y que `CORS_ORIGINS` sea el
  origen exacto; las solicitudes cross-origin deben enviar credenciales.

## Migraciones y Lambda

Las migraciones están en `backend/migrations/versions` y se aplican con
`alembic upgrade head`. El esquema usa SQLAlchemy Core, no ORM, y
`app.main.handler` expone la app con Mangum para Lambda/API Gateway. La guía
[Despliegue en AWS Lambda y migración a Aurora DSQL](aws-lambda.md) fija las
decisiones de empaquetado, configuración, IAM, pooling, migraciones y
observabilidad.

### Flujo de migraciones

Los cambios al esquema se definen primero en `backend/app/db/schema.py` y se
guardan luego en una nueva revisión de Alembic. No se edita una migración que ya
ha sido aplicada en un entorno compartido.

Con los contenedores iniciados, ejecuta estos comandos desde la raíz:

```sh
# Revisar la revisión aplicada y validar que esquema y metadata coinciden
docker compose run --rm --entrypoint alembic backend current
docker compose run --rm --entrypoint alembic backend check

# Crear una revisión a partir del cambio de schema.py; revisar el SQL generado
docker compose run --rm --entrypoint alembic backend revision --autogenerate -m "describe el cambio"

# Aplicar o revertir una revisión localmente
docker compose run --rm --entrypoint alembic backend upgrade head
docker compose run --rm --entrypoint alembic backend downgrade -1
```

Cada pull request que cambie tablas, columnas, índices o restricciones debe
incluir su migración y explicar si hay impacto sobre datos existentes. Con
PostgreSQL, la conexión se obtiene de `DATABASE_URL`. Con DSQL, Alembic usa el
mismo adaptador IAM que la aplicación. La tarea de migración abre un pool de una
sola conexión, lo descarta al terminar y nunca se ejecuta al iniciar Lambda.
