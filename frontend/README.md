# Frontend: Vite, HTML y JavaScript

Este directorio contiene el punto de partida de la aplicación cliente. En la
entrega 2 se trabaja con HTML, CSS y JavaScript nativos; Vite aporta el servidor
de desarrollo, recarga en caliente y el build de producción, pero no impone un
framework. La [guía oficial de Vite](https://vite.dev/guide/) describe estas dos
responsabilidades.

El esqueleto demuestra dos interacciones con el backend:

- `GET /healthz`, para comprobar la conectividad; y
- `POST /api/v1/auth/login`, para comprobar Fetch, JSON y la cookie de sesión.

No incluye `manifest`, `service worker`, soporte offline ni instalación como
PWA. Esos elementos forman parte del trabajo de los grupos en la entrega 2.

## Arquitectura local: un solo origen

El navegador entra siempre por el gateway nginx. nginx decide el servicio de
destino según el path, sin exponer esa topología al JavaScript:

```text
navegador -> gateway nginx -> /, assets y HMR -> Vite
                          \-> /api/*            -> FastAPI
                          \-> /healthz, /docs   -> FastAPI
```

Por ejemplo, el frontend llama a `fetch("/api/v1/auth/login")`. Como la URL es
relativa, conserva automáticamente el esquema, host y puerto de la página. Esto
produce un solo **origen web** y evita configurar una IP, un nombre mDNS o un
dominio dentro del código fuente.

La misma convención sirve para las siguientes etapas:

- **Entrega 3:** nginx sirve el build estático de React en `/` y mantiene el
  proxy `/api/*` hacia el backend del monolito Docker, bajo el subdominio del
  grupo en `4203.iccuandes.org`.
- **Entrega 4:** CloudFront usa el build estático como origen predeterminado y
  un comportamiento `/api/*` hacia API Gateway y Lambda. CloudFront permite
  [varios orígenes y routing por path](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesCacheBehavior.html).

## Ejecutar con Docker Compose

Desde la raíz del repositorio:

```console
docker compose up --build
```

Abre <http://localhost:5173>. El gateway sirve el frontend y enruta las llamadas
al backend. Vite observa los archivos montados desde `frontend/`, por lo que los
cambios aparecen sin reconstruir la imagen.

Si el puerto está ocupado, define otro en tu archivo `.env` local, por ejemplo
`GATEWAY_HTTP_PORT=5174`. Para HTTPS se puede sobreescribir de la misma forma
`GATEWAY_HTTPS_PORT`, cuyo valor predeterminado es 8443. Estas variables solo
cambian los puertos publicados por Compose; no entran en el bundle.

La API sigue disponible directamente en <http://localhost:8000> para
diagnóstico, pero el frontend no debe construir URLs con ese puerto.

Para abrir la aplicación desde un teléfono con HTTPS, sigue la guía de
[acceso desde la red local](../backend/README.md#acceso-desde-un-teléfono-https-en-la-red-local).
El punto de entrada será, por ejemplo, `https://192.168.1.40:8443`.

## Ejecutar Vite directamente

Esta alternativa es útil para trabajar solo en el frontend. Requiere Node.js
22.12 o posterior:

```console
docker compose up db backend

# En otra terminal
cd frontend
npm install
npm run dev
```

Abre <http://localhost:5173>. Detén primero el gateway de Compose, porque ambos
usan el mismo puerto del host. Durante el desarrollo, Vite también hace proxy
de los paths del backend hacia `http://localhost:8000`; este proxy no forma
parte del build. Para probar desde un teléfono o validar cookies `Secure`, usa
el gateway de Compose en vez de esta alternativa.

## Comandos

```console
npm run dev       # servidor de desarrollo
npm run build     # genera dist/ para un despliegue estático
npm run preview   # sirve localmente el contenido de dist/
```

`dist/` no se versiona. En la entrega 3, el pipeline construirá este directorio
y lo incorporará a la imagen del monolito. En la entrega 4, el mismo contenido
podrá publicarse en un origen estático para CloudFront.

## Convenciones para el desarrollo

- Usa URLs relativas para la API: `/api/v1/...`.
- Usa `credentials: "include"` en las llamadas autenticadas. Aunque las
  credenciales se incluyen por defecto en same-origin, hacerlo explícito ayuda
  a reconocer el contrato de autenticación de Fetch.
- No intentes leer la cookie `session`: es `HttpOnly` y el navegador la
  administra.
- No agregues secretos al frontend. Todo valor incluido en el build queda
  disponible para quien descargue la aplicación.
- Conserva `/api` para el backend al definir rutas de la futura aplicación
  React.

Referencias:

- [Fetch API](https://developer.mozilla.org/docs/Web/API/Fetch_API/Using_Fetch)
- [Opciones del servidor Vite](https://vite.dev/config/server-options)
- [Proxy WebSocket de nginx](https://nginx.org/en/docs/http/websocket.html)
- [Políticas de caché administradas de CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)
