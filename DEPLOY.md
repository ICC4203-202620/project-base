# Despliegue bajo 4203.iccuandes.org

Cada grupo publica su aplicación en un subdominio de `4203.iccuandes.org`. El
despliegue ocurre automáticamente en cada `push` a `main` mediante el workflow
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml), que permite
despliegue automático con GitHub Actions.

Esta guía describe qué hace el workflow, qué debe configurar cada grupo en su
repositorio y cómo diagnosticar un despliegue que falla. El servidor, su nginx
y el servidor de base de datos los administra el equipo docente.

## Arquitectura

```text
navegador
   │  https://grupoXX.4203.iccuandes.org
   ▼
nginx del servidor              administrado por el equipo docente
   │  http://127.0.0.1:PUERTO   TLS y un site por grupo
   ▼
gateway del grupo               contenedor nginx
   ├── /          build estático del frontend, con fallback a index.html
   └── /api/*  ─► backend del grupo   contenedor uvicorn
                     │
                     ▼
               servidor PostgreSQL del curso
               una base de datos por grupo
```

Es la misma topología de la [arquitectura local de un solo
origen](frontend/README.md#arquitectura-local-un-solo-origen), con dos
diferencias. TLS termina en el nginx del servidor, que envía el tráfico al
contenedor del grupo por HTTP dentro de la máquina. Y Postgres sale del stack:
la base de datos vive en el servidor del curso y llega por `DATABASE_URL`.

El navegador ve un solo origen, de modo que la cookie de sesión, el service
worker y la instalación de la PWA funcionan igual que en desarrollo.

## Qué hace el workflow

1. Comprueba que estén definidas las variables y los secretos del repositorio.
2. Escribe `.env.deploy` con la configuración del backend y
   `frontend/.env.production` con las variables `VITE_` de compilación.
3. Construye las imágenes y levanta
   [`docker-compose.deploy.yml`](docker-compose.deploy.yml) con el nombre de
   proyecto `foodie-grupoXX`, de modo que los contenedores, imágenes y
   volúmenes del grupo queden separados de los de los demás.
4. Espera a que el backend responda su healthcheck y comprueba `/healthz` y `/`
   por el puerto asignado.
5. Borra del runner los archivos de entorno que escribió.

Las migraciones de Alembic corren solas: `backend/entrypoint.sh` ejecuta
`alembic upgrade head` antes de Uvicorn, y a continuación el seed, que sólo
inserta las filas que faltan. Un despliegue sobre una base ya poblada no
duplica contenido.

El runner del curso es uno solo y atiende un trabajo a la vez. Si varios grupos
despliegan al mismo tiempo, los trabajos hacen fila.

## Variables y secretos

Se definen en el repositorio del grupo, en **Settings → Secrets and variables →
Actions**. Las variables son valores públicos y quedan visibles en los
registros; los secretos se enmascaran.

### Variables (pestaña «Variables»)

| Nombre | Ejemplo | Qué es |
| --- | --- | --- |
| `GROUP_ID` | `07` | Número del grupo, con dos dígitos y cero de relleno. Nombra el proyecto de Compose. |
| `HOST_PORT` | `4007` | Puerto de loopback asignado al grupo en el servidor: `4000` más el número de grupo. |
| `PUBLIC_ORIGIN` | `https://grupo07.4203.iccuandes.org` | Origen público. Alimenta `CORS_ORIGINS`. |
| `SEED_DEMO_DATA` | `true` | Contenido de demostración. Déjala en `true` mientras el ayudante deba recorrer la aplicación. |

El equipo docente comunica a cada grupo su `GROUP_ID`, su `HOST_PORT` y su
subdominio. La convención es `grupoXX` para el subdominio, con el número de
grupo en dos dígitos y cero de relleno, y `4000` más ese número para el puerto:
el grupo 7 recibe `grupo07.4203.iccuandes.org` y el puerto `4007`.

### Secretos (pestaña «Secrets»)

| Nombre | Obligatorio | Qué es |
| --- | --- | --- |
| `DATABASE_URL` | sí | Cadena de conexión a la base del grupo, por ejemplo `postgresql+psycopg://icc4203_grupo07:CLAVE@dbfs-server.tail518971.ts.net:5432/icc4203_grupo07`. |
| `JWT_SECRET` | sí | Secreto de firma de las sesiones. Debe ser propio del grupo y distinto del valor de desarrollo; el backend rechaza arrancar con el valor por omisión cuando `ENVIRONMENT=production`. |
| `VAPID_PUBLIC_KEY` | sí | Clave pública VAPID del grupo, la misma que usó en la entrega 2. |
| `VAPID_PRIVATE_KEY` | sí | Clave privada VAPID. Llega al contenedor del backend y no sale de ahí. |
| `VAPID_SUBJECT` | sí | Sujeto VAPID, por ejemplo `mailto:equipo@example.com`. |
| `VITE_GOOGLE_MAPS_API_KEY` | sí | Clave de Google Maps, restringida por referente HTTP al subdominio del grupo y a `localhost`. |
| `BACKEND_ENV` | no | Salida para cualquier otra variable del backend, una por línea en formato `CLAVE=valor`. Véase más abajo. |
| `FRONTEND_ENV` | no | Salida para cualquier otra variable `VITE_` de compilación, con el mismo formato. |

Genera el secreto de sesiones con un valor aleatorio largo:

```console
openssl rand -base64 48
```

### Backend y build son dos entornos distintos

Las variables del backend llegan al contenedor en tiempo de ejecución y no
salen de ahí. Las variables `VITE_` son otra cosa: Vite las resuelve durante
`npm run build` y **quedan dentro del bundle que descarga cualquier visitante**.
Una clave privada de VAPID definida como `VITE_…` quedaría publicada.

La clave de Google Maps es una excepción conocida: por diseño viaja al
navegador, y su protección es la restricción por referente HTTP configurada en
la consola de Google Cloud, no el secreto de su valor.

El workflow define por su cuenta `ENVIRONMENT`, `COOKIE_SECURE`,
`MEDIA_STORAGE_BACKEND` y `MEDIA_LOCAL_PATH`. Redefinirlas no tiene efecto.

### Cómo llega un secreto al contenedor

Un secreto de GitHub Actions no está disponible como variable de entorno por el
solo hecho de existir. El workflow tiene que nombrarlo, y después escribirlo en
el archivo que Compose entrega al contenedor. El paso «Componer el entorno del
backend» hace las dos cosas: el bloque `env:` trae el secreto al paso, y un
`printf` lo escribe en `.env.deploy`.

Los secretos de la tabla anterior ya están nombrados en el workflow, de modo
que definirlos en el repositorio basta. Si tu grupo usó otros nombres al
implementar Web Push en la entrega 2, tienes dos caminos: renombrar los campos
en la configuración del backend para que calcen con los canónicos, que es lo
recomendable, o dejarlos en `BACKEND_ENV`.

`BACKEND_ENV` y `FRONTEND_ENV` son un solo secreto cuyo valor ocupa varias
líneas, que el workflow vuelca completo al archivo de entorno:

```dotenv
SENTRY_DSN=https://...
FEATURE_COMENTARIOS=true
```

Úsalos sólo para lo que no tenga un secreto propio. GitHub
[desaconseja los datos estructurados como valor de un secreto](https://docs.github.com/en/actions/reference/security/secrets),
porque el enmascaramiento en los registros funciona por coincidencia con el
valor completo: un valor individual extraído del bloque puede aparecer sin
enmascarar. Por eso las claves VAPID y la de Google Maps tienen cada una su
propio secreto.

Si prefieres un secreto suelto para una variable adicional, hay que editar
[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) en dos lugares
del mismo paso:

```yaml
      - name: Componer el entorno del backend
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          SENTRY_DSN: ${{ secrets.SENTRY_DSN }}        # 1. traer el secreto
          ...
        run: |
          ...
          if [ -n "$SENTRY_DSN" ]; then                # 2. escribirlo
            printf 'SENTRY_DSN=%s\n' "$SENTRY_DSN" >> .env.deploy
          fi
```

Olvidar el segundo cambio produce una falla silenciosa: el workflow termina en
verde y el backend arranca con la variable ausente.

Editar el workflow tiene un costo de mantenimiento: cada actualización del
código base que lo toque producirá un conflicto que el grupo deberá resolver.
`BACKEND_ENV` evita ese conflicto.

## Primer despliegue

1. Mezclen `upstream/main` para incorporar el workflow, `docker-compose.deploy.yml`,
   `gateway/Dockerfile.production` y `gateway/production.conf`.
2. Definan las variables y los secretos de las tablas anteriores.
3. Comprueben que el nombre del service worker del grupo calce con lo que sirve
   [`gateway/production.conf`](gateway/production.conf). El archivo contempla
   `sw.js` y `service-worker.js`; si publicaron otro nombre, agréguenlo ahí.
4. Hagan `push` a `main`, o lancen el workflow a mano desde la pestaña
   **Actions** con **Run workflow**.
5. Abran `https://grupoXX.4203.iccuandes.org` e instalen la PWA desde ahí.

## Verificación

Con el despliegue en marcha:

```console
curl -i https://grupoXX.4203.iccuandes.org/healthz
curl -i https://grupoXX.4203.iccuandes.org/manifest.webmanifest
```

Desde el navegador, comprueben que el service worker queda registrado con
scope `/`, que una URL profunda recargada abre su vista, y que el inicio de
sesión deja la cookie `session` con `Secure` y `HttpOnly`.

## Diagnóstico

| Síntoma | Causa habitual |
| --- | --- |
| El workflow falla en «Comprobar la configuración» | Falta una variable o un secreto. El mensaje nombra cuáles. |
| El backend no arranca y el registro menciona `JWT_SECRET` | El secreto es el valor de desarrollo. `ENVIRONMENT=production` lo rechaza. |
| El backend no arranca y el registro menciona `Multiple head revisions` | La cadena de Alembic quedó con dos cabezas después de mezclar. Véase la sección de migraciones del [enunciado de la entrega 3](docs/entrega3.md#numeración-de-las-migraciones). |
| Login y demás escrituras responden `403 Untrusted request origin` | `PUBLIC_ORIGIN` no coincide exactamente con el origen desde el que se abre la aplicación. Si coincide, avisen al equipo docente: el site del grupo puede no estar propagando `Host` y `X-Forwarded-Proto`. |
| Una ruta de React recargada responde `404` | El gateway no está sirviendo el fallback a `index.html`. Revisen que la imagen se construyó con `gateway/Dockerfile.production`. |
| La aplicación queda congelada en una versión anterior | El service worker se está cacheando. Revisen que su nombre calce con la regla de `production.conf`. |
| Una variable propia del grupo llega vacía al backend | Está definida como secreto suelto y el workflow no la nombra. Muévanla a `BACKEND_ENV` o agréguenla en los dos lugares que describe «Cómo llega un secreto al contenedor». |
| El mapa no carga | Falta el secreto `VITE_GOOGLE_MAPS_API_KEY`, o su restricción por referente no incluye el subdominio del grupo. |
| Nadie recibe notificaciones | Faltan los secretos `VAPID_*`, o el código del grupo lee otros nombres de variable. Revisen el aviso del workflow. |

Los registros de los contenedores aparecen en el paso final del workflow
cuando el despliegue falla. El workflow no los publica en un despliegue
exitoso, para no exponer información de la ejecución.
