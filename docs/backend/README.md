# Backend: desarrollo local

## Inicio rápido

Necesitas Docker Desktop (o Docker Engine con Compose).

```sh
docker compose up --build
```

La API queda en `http://localhost:8000`, con OpenAPI en `/docs`. El contenedor
aplica las migraciones y crea el usuario de prueba si no existe: correo
`demo@foodie.local`, contraseña `demo-password`. El login es
`POST /api/v1/auth/login`; devuelve 204 y establece una cookie `session`
`HttpOnly`. No incluyan secretos ni contraseñas de producción en Git.

Para pruebas locales con Python 3.13 y uv:

```sh
cd backend
uv sync --group dev
uv run pytest
```

## Teléfono: HTTPS y mDNS

Las cookies `Secure` requieren HTTPS. En macOS y Linux con Avahi/Bonjour, usa el
hostname mDNS del equipo, por ejemplo `mi-equipo.local`, y confirma que el
teléfono está en la misma red sin aislamiento Wi-Fi.

1. Instala mkcert y su CA: en macOS, `brew install mkcert && mkcert -install`.
2. En la raíz, crea certificados (sustituye el nombre):

   ```sh
   mkdir -p certs
   mkcert -cert-file certs/local.pem -key-file certs/local-key.pem mi-equipo.local localhost 127.0.0.1
   ```

3. Inicia con `LOCAL_TLS=true COOKIE_SECURE=true docker compose up --build`.
   Agrega `https://mi-equipo.local:5173` a `CORS_ORIGINS` si corresponde.
   `certs/` está ignorado y se monta de solo lectura.
4. Abre `https://mi-equipo.local:8000/docs` en el teléfono.

### Windows + WSL

WSL2 no siempre publica mDNS ni puertos hacia el teléfono. Usa Docker Desktop
con integración WSL y el nombre o IP LAN del host Windows, generando el
certificado para ese nombre. En Windows 11, `networkingMode=mirrored` en
`.wslconfig` puede ayudar. Si no responde, permite TCP 8000 en el firewall.
`localhost` en un teléfono se refiere al propio teléfono.

## Migraciones y Lambda

Las migraciones están en `backend/migrations/versions` y se aplican con
`alembic upgrade head`. El esquema usa SQLAlchemy Core, no ORM, y
`app.main.handler` expone la app con Mangum para Lambda/API Gateway. Al pasar
a Aurora DSQL hay que validar el dialecto, driver y autenticación del servicio.
