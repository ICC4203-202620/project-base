# Frontend: Vite, HTML y JavaScript

Este directorio contiene el punto de partida de la aplicación cliente. En la
entrega 2 se trabaja con HTML, CSS y JavaScript nativos; Vite aporta el servidor
de desarrollo, recarga en caliente y el build de producción, pero no impone un
framework. La [guía oficial de Vite](https://vite.dev/guide/) describe estas dos
responsabilidades.

El esqueleto demuestra la conectividad y el ciclo completo de autenticación:

- `GET /healthz`, para comprobar la conectividad;
- `GET /api/v1/auth/session`, para reconstruir la interfaz al cargar la página;
- `POST /api/v1/auth/login`, para iniciar una sesión; y
- `POST /api/v1/auth/logout`, para revocarla y eliminar la cookie.

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

## Ciclo de autenticación

El frontend no guarda una copia de la sesión en `localStorage` ni intenta leer
`document.cookie`. La cookie `session` usa `HttpOnly`: el navegador la recibe y
la adjunta, pero JavaScript sólo conoce el resultado que entrega el backend. La
[documentación de cookies seguras de
MDN](https://developer.mozilla.org/docs/Web/Security/Practical_implementation_guides/Cookies#httponly)
explica por qué este atributo reduce la exposición de una credencial ante
scripts.

Al cargar o recargar la página, el controlador consulta `/auth/session` con
`credentials: "include"`. La interfaz representa cuatro estados explícitos:

| Estado | Qué significa | Interfaz |
| --- | --- | --- |
| `loading` | Aún no hay una respuesta confiable. | Mensaje transitorio; no muestra prematuramente el formulario. |
| `anonymous` | El backend respondió `401`: no hay sesión vigente. | Formulario de login y explicación de `HttpOnly`. |
| `authenticated` | El backend confirmó usuario y caducación. | Identidad, fecha local de expiración y logout. |
| `unavailable` | Falló la red o el servicio respondió un error de infraestructura. | Mensaje diferente de credenciales inválidas y acción de reintento. |

Login responde `204 No Content`, pero eso no basta para cambiar la interfaz a
autenticada. Inmediatamente después se consulta `/auth/session` y sólo un `200`
confirma el nuevo estado. Logout también responde `204`; el backend lo trata de
forma idempotente aunque la sesión haya caducado mientras la página estaba
abierta.

Los módulos mantienen responsabilidades separadas sin introducir un framework:

```text
src/api.js   -> Fetch, URLs, credentials y formato común de errores
src/auth.js  -> transiciones loading/anonymous/authenticated/unavailable
src/main.js  -> eventos del DOM, renderizado y formato local de la caducación
```

`index.html` contiene desde el inicio el panel `loading` y mantiene ocultos los
demás. Así se evita mostrar por un instante el formulario antes de conocer la
sesión. El estado textual usa `role="status"` y `aria-live="polite"` para que
las tecnologías de asistencia anuncien los cambios sin interrumpir al usuario.

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

Si el puerto está ocupado, define otro en tu archivo `.env` local mediante
`GATEWAY_HTTP_PORT`. El valor predeterminado de Compose para HTTPS es 8443, pero
el perfil `.env.local.example` lo publica en 5173 y desplaza el mapeo HTTP a
5174. Así, la URL habitual cambia de esquema, no de puerto: HTTP para el inicio
rápido y HTTPS para el perfil TLS. Estas variables solo cambian los puertos
publicados por Compose; no entran en el bundle.

La API sigue disponible directamente en <http://localhost:8000> para
diagnóstico, pero el frontend no debe construir URLs con ese puerto.

Para abrir la aplicación desde un teléfono con HTTPS, sigue la guía de
[HTTPS local y acceso desde un teléfono](../backend/README.md#https-local-y-acceso-desde-un-teléfono).
Los puntos de entrada serán `https://localhost:5173` en el computador y, por
ejemplo, `https://192.168.1.40:5173` desde otro dispositivo.

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
npm test          # prueba el cliente HTTP y las transiciones de autenticación
npm run preview   # sirve localmente el contenido de dist/
```

`dist/` no se versiona. En la entrega 3, el pipeline construirá este directorio
y lo incorporará a la imagen del monolito. En la entrega 4, el mismo contenido
podrá publicarse en un origen estático para CloudFront.

### Verificación del flujo

Las pruebas usan el runner incorporado en Node.js, por lo que no añaden un
framework de testing. Comprueban URLs relativas, `credentials: "include"`,
errores HTTP frente a errores de red y todas las transiciones de sesión:

```console
cd frontend
npm test
npm run build
```

Para una comprobación manual con el stack iniciado:

1. abre la página y verifica que el estado inicial transitorio termina en el
   formulario;
2. usa una contraseña incorrecta y comprueba que el mensaje habla de
   credenciales, no de conectividad;
3. inicia sesión con `demo@example.com` y `demo-password`;
4. recarga y confirma que la identidad continúa visible;
5. cierra sesión y recarga para comprobar que vuelve el formulario; y
6. detén temporalmente el backend y usa «Volver a intentar» para observar el
   estado de indisponibilidad.

## Convenciones para el desarrollo

- Usa URLs relativas para la API: `/api/v1/...`.
- Usa `credentials: "include"` en las llamadas autenticadas. Aunque las
  credenciales se incluyen por defecto en same-origin, hacerlo explícito ayuda
  a reconocer el contrato de autenticación de Fetch.
- No intentes leer la cookie `session`: es `HttpOnly` y el navegador la
  administra.
- No deduzcas una sesión a partir del `204` de login: consulta `/auth/session`.
- Trata `401 Unauthorized` como ausencia de sesión, no como una falla de red;
  la semántica del código está definida en
  [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110#name-401-unauthorized).
- No agregues secretos al frontend. Todo valor incluido en el build queda
  disponible para quien descargue la aplicación.
- Conserva `/api` para el backend al definir rutas de la futura aplicación
  React.

Referencias:

- [Fetch API](https://developer.mozilla.org/docs/Web/API/Fetch_API/Using_Fetch)
- [Fetch: opción `credentials`](https://developer.mozilla.org/docs/Web/API/Request/credentials)
- [Opciones del servidor Vite](https://vite.dev/config/server-options)
- [Proxy WebSocket de nginx](https://nginx.org/en/docs/http/websocket.html)
- [Políticas de caché administradas de CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)
