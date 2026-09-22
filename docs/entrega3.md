# Entrega 3 — Frontend completo con React

## Fecha de entrega: 23 de octubre a las 23:59 hrs., por Git y con despliegue bajo `4203.iccuandes.org`

En esta entrega cada grupo construye el frontend completo de la aplicación descrita en el [enunciado general del proyecto](../README.md), usando React sobre el diseño elaborado en la [entrega 1](entrega1.md) y conservando las capacidades de PWA desarrolladas en la [entrega 2](entrega2.md).

Las dos entregas anteriores dejan cada una su aporte. De la entrega 1 viene el diseño: las pantallas, la navegación global, la paleta y la escala tipográfica que ahora se traducen a un theme de MUI. De la entrega 2 vienen el service worker, el manifest, la estrategia de caché, el almacén de IndexedDB y el ciclo completo de Web Push, que deben seguir funcionando después de reemplazar la interfaz. El código base aporta el backend: a partir de esta entrega expone las diecisiete épicas del enunciado general, de modo que el esfuerzo del grupo se concentre en el cliente.

La entrega se evalúa como producto. Una persona ajena al grupo debe poder instalar la PWA desde el subdominio del grupo, crear una cuenta, descubrir restaurantes, registrar su experiencia y seguir a otras personas, sin que se le expliquen las pantallas.

## Código provisto

El equipo docente provee y mantiene el backend monolítico completo. Con el lanzamiento del código base de esta entrega, la API cubre:

* Registro de usuarios, autenticación por cookie `HttpOnly`, sesión y cierre de sesión.
* Perfil propio y perfil ajeno, con la separación entre actividad pública y actividad privada aplicada en el servidor.
* Búsqueda de restaurantes por nombre, creación con prevención de duplicados, ficha completa y edición.
* Consulta de restaurantes por área geográfica y búsqueda por estilo de comida dentro de una distancia dada, con la distancia calculada en el backend.
* Visitas (check-in), fotografías de platos, menús e instalaciones, reseñas de plato, evaluaciones multicriterio de un restaurante y comentarios en threads sobre una fotografía, todos con visibilidad pública o privada.
* Búsqueda de usuarios por handle, seguimiento de usuarios y de restaurantes, y feed cronológico deduplicado.
* Resolución de destinatarios de una notificación a partir de las relaciones de seguimiento, con la garantía de que una misma actividad produce un solo destinatario por usuario.

El contrato vigente es el que expone `/docs` en la instalación que el grupo está ejecutando, junto con las pruebas automatizadas del backend. Cuando un ejemplo de este enunciado o de un README difiera del backend en ejecución, la referencia es `/docs`.

El backend no incluye Web Push: esa parte la construyó cada grupo en la entrega 2 y sigue siendo suya. Lo que el código base agrega es la consulta que determina a quién corresponde notificar; conectarla con el emisor propio es trabajo del grupo, y se describe más adelante.

El código base tampoco incluye React. Migrar el frontend es el objeto de esta entrega.

## Actualización del código base

El código base llega al repositorio del grupo por la vía habitual, descrita en la sección «Uso del repositorio» del enunciado general:

```sh
git fetch upstream
git merge upstream/main
```

La mezcla ocurre sobre un repositorio que ya contiene el trabajo de la entrega 2, de modo que habrá conflictos. Son pocos y están acotados. Resuélvanlos en una rama, con el stack corriendo, antes de escribir una línea de React.

### Numeración de las migraciones

El código base reserva la banda `0100` en adelante para sus revisiones de Alembic y no modifica las anteriores. La primera de ellas encadena sobre `0005_create_follows`, que era la última revisión publicada cuando comenzó la entrega 2. Las revisiones que cada grupo escribió en esa entrega ocupan `0006` y siguientes, y encadenan sobre `0005_create_follows` también.

Después de mezclar, el historial tiene dos ramas que salen del mismo punto, y el contenedor del backend deja de arrancar: `entrypoint.sh` ejecuta `alembic upgrade head` y Alembic responde `Multiple head revisions are present`. Para linealizar la cadena:

**1. Identifiquen las dos cabezas.**

```console
docker compose run --rm --entrypoint alembic backend heads
```

La salida nombra dos revisiones. Una es la más reciente del grupo, por ejemplo `0006_create_push_subscriptions`. La otra es la más reciente del código base, con prefijo `0100` o superior. Copien el identificador completo de esta segunda; es el valor que aparece en la asignación `revision = "..."` de su archivo.

**2. Modifiquen una sola migración propia.**

De las migraciones que escribió el grupo, abran aquella cuyo `down_revision` sea `"0005_create_follows"`. Es la más antigua de las suyas y es la única que cambia. Reemplacen ese valor por el identificador que copiaron:

```python
revision = "0006_create_push_subscriptions"
down_revision = "0103_create_activity"  # el identificador real de la cabeza del código base
branch_labels = None
depends_on = None
```

El identificador se copia literalmente, con su prefijo numérico, entre comillas. Si el grupo escribió más de una migración, las demás conservan su `down_revision`, porque ya encadenan entre ellas.

**3. Comprueben que queda una sola cabeza.**

```console
docker compose run --rm --entrypoint alembic backend heads
docker compose run --rm --entrypoint alembic backend history
```

`heads` debe imprimir una única revisión, la más reciente del grupo. `history` debe mostrar una cadena continua desde `0001_create_users` hasta esa revisión, pasando por todas las del código base.

**4. Recreen la base de datos de desarrollo.**

```console
docker compose down -v
docker compose up --build
```

Esto descarta los datos locales, lo que en desarrollo no tiene costo porque el seed los repuebla. Es necesario porque la tabla `alembic_version` de la base existente registra una revisión que acaba de cambiar de posición en el historial.

Tres advertencias sobre este procedimiento:

* El identificador de una revisión propia no se renumera ni se renombra. Ese valor queda registrado en la tabla `alembic_version` de toda base que ya lo haya aplicado, incluida la de cualquier integrante del grupo.
* La banda `0100` en adelante queda reservada para el código base. Una revisión propia que use un identificador de esa banda puede colisionar con una futura del código base y romper la mezcla siguiente.
* Un grupo que mezcló una versión anterior del código base puede tener su primera migración encadenada a una revisión distinta de `0005_create_follows`. La regla general es la misma: la migración propia que apunta a una revisión del código base es la que se vuelve a apuntar hacia la cabeza actual del código base.

### Puntos de conflicto conocidos

| Archivo | Qué ocurre |
| --- | --- |
| `backend/app/db/schema.py` | El código base agrega sus tablas al final del módulo. Si su tabla de suscripciones quedó antes de ese punto, la mezcla es automática. |
| `backend/app/main.py` | Ambos agregan un `include_router`. Conserven los dos. |
| `backend/app/core/config.py` | Ambos agregan campos de configuración. Conserven los dos bloques. |
| `backend/pyproject.toml` | Ambos agregan dependencias. Conserven las dos listas. |
| `docker-compose.yml` | Ambos agregan variables de entorno al servicio `backend`. Conserven las dos. |
| `backend/app/services/reviews.py` | El código base amplía la creación de reseñas. Para no perder el enganche del emisor de push, el servicio expone un punto de extensión documentado en [DEVELOPER.md](../backend/DEVELOPER.md); trasladen ahí su llamada en lugar de conservar la línea original. |

El código base no modifica `frontend/public/`, el service worker, el manifest, los iconos ni los módulos de push y de almacenamiento offline. Ese código es del grupo y llega intacto a esta entrega.

## Continuidad con la entrega 2

La interfaz se reescribe; la infraestructura de PWA, no. Al terminar la migración a React deben seguir funcionando, sin excepción:

* La instalación en la plataforma declarada y el manifest con su identidad estable.
* El ciclo de vida del service worker: instalación del app shell, limpieza de cachés obsoletos y actualización sin mezclar recursos de dos versiones.
* La copia offline del contenido en IndexedDB, asociada al usuario cuya sesión fue verificada, y su eliminación al cerrar sesión.
* El indicador de modo online u offline y la advertencia de contenido desactualizado.
* El permiso y la suscripción Push gestionados por una acción explícita del usuario, y el manejo de `push` y `notificationclick` en el service worker.

El cambio a React modifica las condiciones de dos de estos puntos, y conviene anticiparlo:

El app shell deja de ser un `index.html` con su hoja de estilos. Ahora es el resultado del build de Vite, con nombres de archivo que incluyen un hash de contenido. La lista de recursos que el service worker precachea tiene que generarse desde el build, y no escribirse a mano.

El `notificationclick` ya no abre una URL que el servidor resuelve. La aplicación es de una sola página, y la ventana enfocada tiene que navegar por el router hacia la vista del contenido notificado. Esto requiere comunicar el service worker con el cliente, por ejemplo mediante `postMessage`.

## Por dónde comenzar

| Si necesitas... | Comienza en... |
| --- | --- |
| Recuperar las decisiones de diseño, la paleta y la tipografía | el archivo de Figma del grupo y `docs/entrega1/README.md` |
| Conocer el contrato completo de la API | `/docs` en la instalación local, y el [README del backend](../backend/README.md) |
| Entender cómo se separan actividad pública y privada, y cómo se resuelven los destinatarios de una notificación | [Arquitectura y desarrollo del backend](../backend/DEVELOPER.md) |
| Conservar el contrato de paths y el origen único | [README del frontend](../frontend/README.md#arquitectura-local-un-solo-origen) |
| Levantar el stack y explorar la API | [Inicio rápido del backend](../backend/README.md#inicio-rápido) |
| Probar desde un dispositivo con HTTPS | [HTTPS local y acceso desde un teléfono](../backend/README.md#https-local-y-acceso-desde-un-teléfono) |

El orden de trabajo recomendado es:

1. Mezclen `upstream/main`, resuelvan los conflictos y comprueben que las pruebas del backend y el flujo de la entrega 2 siguen pasando. Esa es la línea base.
2. Definan el theme de MUI a partir de la paleta y la tipografía del diseño, y fijen la navegación global. Son las dos decisiones que afectan a todas las pantallas.
3. Construyan el shell de la aplicación: router, cliente HTTP, contexto de sesión y las pantallas de autenticación. Comprueben ahí que el service worker sigue controlando la aplicación.
4. Implementen las épicas por familias, empezando por descubrimiento y registro de la experiencia, que alimentan de contenido a todas las demás.
5. Dejen las notificaciones dirigidas y el feed para cuando existan seguimientos y actividad real que mostrar.
6. Desplieguen bajo el subdominio del grupo durante las primeras semanas de trabajo. El build de producción expone problemas de rutas, de manifest y de service worker que el servidor de desarrollo oculta.

## Alcance funcional

El frontend debe resolver las diecisiete épicas del enunciado general. Lo que sigue precisa el alcance exigible de cada una en esta entrega; la descripción completa está en el enunciado general y no se repite aquí.

### Cuenta y perfil

1. **Registro e inicio de sesión.** Formulario de registro con nombre, correo, handle y nacionalidad, con validación del handle contra los ya existentes. Inicio y cierre de sesión con el flujo provisto. El registro y el inicio de sesión requieren conexión.
2. **Perfil de usuario.** El perfil propio muestra la actividad pública y la privada, distinguiéndolas visualmente. El perfil de otra persona muestra solo sus datos públicos y la actividad que decidió compartir. Ambas vistas ofrecen visitas, fotografías, reseñas y evaluaciones. El perfil ajeno incluye la acción de seguir o dejar de seguir.

### Descubrimiento de restaurantes

3. **Buscar o crear un restaurante.** Búsqueda por nombre con resultados incrementales. Cuando no existe, el formulario de creación pide nombre, dirección y estilos de comida. El backend rechaza el duplicado; la interfaz debe explicar el rechazo y llevar a la ficha existente.
4. **Explorar restaurantes en el mapa.** Mapa interactivo con desplazamiento y zoom, que carga los restaurantes del área visible. La interfaz debe evitar una solicitud por cada movimiento del mapa.
5. **Buscar por estilo de comida y cercanía.** Selección de un estilo y de una distancia máxima desde la posición del usuario, con resultados sobre el mapa y en una lista ordenada por distancia. La interfaz debe manejar el permiso de geolocalización denegado.
6. **Ver un restaurante.** Ficha con información básica, estilos de comida, fotografías publicadas por la comunidad, resumen de las evaluaciones recibidas, acciones de registro de la experiencia y la acción de seguir o dejar de seguir.

### Registro de la experiencia

Toda actividad se registra eligiendo su visibilidad. La elección debe estar presente en el formulario, con un valor por omisión coherente y una explicación de su efecto.

7. **Hacer check-in.** Registro de la visita desde la ficha del restaurante, con su momento y su visibilidad.
8. **Publicar la foto de un plato.** Carga de una fotografía identificando el plato. La interfaz debe mostrar una previsualización y el progreso de la carga, y validar tipo y tamaño antes de enviar.
9. **Publicar fotos del menú o de las instalaciones.** Carga de una o más fotografías, indicando de qué tipo se trata.
10. **Reseñar un plato.** Reseña asociada a una única fotografía de plato, con calificación y texto.
11. **Evaluar un restaurante.** Calificación en los criterios definidos por el backend, comentario general y asociación opcional de una o más fotografías de menú o instalaciones. La ficha del restaurante muestra el resumen de las evaluaciones.

### Interacción social

12. **Buscar usuarios por handle.** Búsqueda con resultados incrementales que lleva al perfil.
13. **Seguir y dejar de seguir usuarios.** Acción reversible, visible desde el perfil y desde los resultados de búsqueda, con el estado reflejado de inmediato en la interfaz.
14. **Seguir y dejar de seguir restaurantes.** Acción reversible desde la ficha. La actividad relevante de un restaurante seguido produce una notificación.
15. **Ver el feed.** Actividad reciente de las personas y los restaurantes que el usuario sigue, en orden cronológico, paginada por cursor, sin repetir una actividad que coincide con más de un criterio. El feed debe distinguir sus estados vacío, de carga y de error, y debe poder consultarse desde la copia offline.
16. **Ver visitas de personas conocidas.** La ficha del restaurante indica si alguna persona seguida por el usuario estuvo ahí, y cuándo, considerando solo visitas públicas.
17. **Comentar fotografías.** Conversación en threads sobre una fotografía pública, con respuestas anidadas, publicación de un comentario nuevo y los estados que corresponden.

### Notificaciones dirigidas

La entrega 2 usó una regla deliberadamente simple: una reseña nueva notificaba a todos los usuarios con suscripción activa. Esa regla se reemplaza.

A partir de esta entrega, una actividad pública notifica a quienes siguen a su autor y a quienes siguen al restaurante en que ocurrió, excluyendo al autor. Una actividad privada no notifica a nadie. Cuando una persona sigue tanto al autor como al restaurante, recibe una sola notificación por cada instalación suscrita.

El código base provee la consulta que resuelve esos destinatarios. El grupo adapta su emisor de la entrega 2 para usarla, en lugar de recorrer todas las suscripciones activas.

## Requisitos del frontend

### React

La aplicación se construye con React sobre Vite. El grupo escoge sus bibliotecas de enrutamiento, formularios y obtención de datos, y debe poder justificar cada elección.

Se exige:

* Enrutamiento por URL. Cada vista direccionable tiene su propia ruta, el botón de retroceso del navegador funciona, y una URL compartida abre la vista correspondiente. Esto es condición para que `notificationclick` lleve a la vista del contenido notificado.
* Protección de rutas según el estado de la sesión, con la autorización efectiva siempre en el backend.
* Estado de sesión compartido por la aplicación, actualizado cuando el backend responde `401` a cualquier solicitud.
* Composición en componentes reutilizables. Una pantalla no reimplementa la tarjeta de actividad, el selector de visibilidad ni el cargador de fotografías que ya existen.
* Manejo de la cancelación de solicitudes al desmontar un componente o al cambiar de ruta, para que una respuesta tardía no reescriba una vista que ya cambió.

Se conserva el contrato de paths de las entregas anteriores: URLs relativas `/api/v1/...`, `credentials: "include"`, ninguna referencia a `localhost`, a una IP, a un nombre mDNS ni a un puerto dentro del código del frontend.

### Theme y componentes de MUI

La interfaz se construye con MUI, con la misma exigencia de consistencia que se evaluó en la entrega 1.

* El theme se define una vez, con la paleta y la escala tipográfica del diseño de la entrega 1. Basta con un modo, claro u oscuro, a elección del grupo. Si el grupo usó Material Theme Builder, puede partir de esos tokens; el camino por el que llegó al theme no se evalúa.
* Los colores, espaciados y tipografías provienen del theme. Un valor hexadecimal escrito dentro de un componente es una inconsistencia.
* Los controles son componentes de MUI usados según su propósito. Un control construido a mano teniendo su equivalente en la biblioteca se evalúa como inconsistencia.
* Los iconos provienen de `@mui/icons-material`.

La correspondencia entre el prototipo de Figma y la aplicación implementada se evalúa. Una decisión de diseño puede cambiar durante la implementación, y esos cambios deben quedar documentados en el informe con su razón.

### Estados de la interfaz

Cada vista que obtiene datos del backend distingue sus estados de carga, contenido, vacío y error, con un mensaje que permita al usuario entender qué ocurrió y qué puede hacer. Un estado vacío se distingue de un error. Un error de red se distingue de una respuesta del servidor.

Los formularios validan antes de enviar, informan el resultado y evitan el envío duplicado mientras la solicitud está en curso.

### Contexto móvil y accesibilidad

La aplicación se diseña para teléfono. Las áreas táctiles, la densidad de información y la navegación corresponden a ese contexto, tal como se evaluó en la entrega 1.

Se exige un mínimo de accesibilidad: navegación por teclado en los formularios, etiquetas asociadas a los campos, texto alternativo en las fotografías publicadas, contraste suficiente entre texto y fondo, y anuncio de los cambios de estado mediante regiones `aria-live`.

## Mapas y cercanía

Las épicas 4 y 5 se resuelven con Google Maps Platform. Cada grupo gestiona su propia clave de API.

* La clave del cliente se restringe por referente HTTP al subdominio del grupo y a `localhost`, y se limita a las API que la aplicación usa.
* La clave se inyecta en el build mediante una variable de entorno con prefijo `VITE_`. Todo valor incluido en el build queda a la vista de quien descargue la aplicación: la restricción por referente es la protección, y no el secreto de la clave.
* Ninguna clave se versiona. El archivo `.env.local.example` documenta el nombre de la variable con un valor de ejemplo.
* La cuota del nivel gratuito es acotada. Eviten solicitudes por cada movimiento del mapa y por cada pulsación en un campo de búsqueda.

La posición del usuario se obtiene con la API de geolocalización del navegador, que requiere contexto seguro y permiso explícito. La interfaz debe funcionar cuando el permiso se deniega, ofreciendo al menos la búsqueda por nombre y la exploración libre del mapa.

## Despliegue

Cada grupo despliega su aplicación bajo el subdominio que se le asigne en `4203.iccuandes.org`. El despliegue es parte de la entrega y se evalúa.

El código base provee el mecanismo completo, y la guía [DEPLOY.md](../DEPLOY.md) lo explica en detalle: un workflow de GitHub Actions que publica en cada `push` a `main` sobre un runner del curso, el stack `docker-compose.deploy.yml` y una imagen de nginx que sirve el build estático del frontend y hace proxy de la API. El equipo docente comunicará a cada grupo su subdominio, su puerto y la cadena de conexión a su base de datos.

La topología es la misma de la arquitectura local, descrita en el [README del frontend](../frontend/README.md#arquitectura-local-un-solo-origen). TLS termina en el nginx del servidor, que tiene el certificado comodín del dominio, y Postgres sale del stack porque la base de datos vive en el servidor del curso. El navegador sigue viendo un solo origen, de modo que la cookie de sesión, el service worker y la instalación de la PWA funcionan sin cambios respecto del entorno local.

El trabajo del grupo en esta parte consiste en:

* Definir en su repositorio las variables y los secretos que documenta DEPLOY.md, entre ellos su `JWT_SECRET`, sus claves VAPID y su clave de Google Maps.
* Comprobar que el nombre de su service worker calce con lo que sirve `gateway/production.conf`, y ajustarlo si publicaron otro.
* Mantener el despliegue en funcionamiento, con contenido de demostración y credenciales que el ayudante pueda usar.

El despliegue debe cumplir:

* HTTPS con un certificado válido para el subdominio. La instalación de una PWA y el permiso de notificaciones lo requieren.
* La cookie de sesión con `Secure`, que el stack de despliegue fija mediante `COOKIE_SECURE`.
* El build de producción de Vite, servido como archivos estáticos.
* El manifest, los iconos y el service worker servidos con sus rutas correctas bajo el scope de la aplicación.
* Ningún secreto versionado en el repositorio, y ninguna clave privada dentro del bundle del frontend.

## Verificación mínima

Antes de entregar, comprueben al menos lo siguiente sobre el despliegue, usando la PWA instalada y dos cuentas distintas:

1. Una persona se registra, inicia sesión, cierra sesión y vuelve a iniciar sesión.
2. Se recorre cada una de las diecisiete épicas de extremo a extremo desde la aplicación instalada.
3. Una actividad registrada como privada aparece en el perfil propio y no aparece en el perfil visto por la otra cuenta, ni en su feed, ni en la ficha del restaurante.
4. El feed muestra una sola vez una actividad cuyo autor y cuyo restaurante son ambos seguidos por el usuario.
5. Se recarga una URL profunda, por ejemplo la de una reseña, y la aplicación abre esa vista.
6. La aplicación se cierra, se pierde la conexión y se vuelve a abrir: el feed persistido se consulta en modo de solo lectura, identificado como copia desactualizada.
7. Al iniciar sesión con la segunda cuenta, el contenido persistido de la primera deja de estar disponible.
8. Una publicación de una cuenta seguida produce una notificación en la otra instalación con la aplicación cerrada, y seleccionarla abre la vista correspondiente.
9. Una publicación de una cuenta que no se sigue, y en un restaurante que no se sigue, no produce notificación.
10. Una versión nueva del frontend reemplaza la anterior sin dejar recursos mezclados de dos builds.
11. El mapa carga, responde al desplazamiento y produce resultados por estilo y distancia; con el permiso de geolocalización denegado, la aplicación sigue siendo utilizable.
12. Las pruebas del backend y del frontend pasan sobre el repositorio entregado.

## Formato de la entrega

Todo el código queda versionado en el repositorio del grupo. En `docs/entrega3/README.md` incluyan:

* Nombre de la aplicación e integrantes del grupo.
* URL del despliegue y URL del prototipo de Figma de la entrega 1.
* Credenciales de dos cuentas de demostración con contenido, para que el ayudante pueda recorrer la aplicación sin registrarse.
* Instrucciones reproducibles para ejecutar la aplicación localmente y para desplegarla, con los nombres de las variables de entorno requeridas.
* Mapa de las diecisiete épicas: en qué ruta de la aplicación se resuelve cada una.
* Decisiones de diseño que cambiaron respecto del prototipo de Figma, con su razón.
* Descripción del theme: qué valores de paleta y tipografía se definieron y cómo se derivaron del diseño de la entrega 1.
* Descripción de la arquitectura del frontend: enrutamiento, manejo del estado de sesión, obtención de datos y organización de los componentes.
* Qué cambió en el service worker y en el almacén offline al migrar a React.
* Cómo se conectó el emisor de Web Push del grupo con la resolución de destinatarios provista por el backend.
* Evidencia de la aplicación instalada desde el despliegue, de la operación offline y de una notificación dirigida recibida con la aplicación cerrada.
* Resultado de los comandos de prueba utilizados.
* Problemas conocidos y restricciones de la plataforma escogida.
* Declaración del uso de herramientas de inteligencia artificial generativa.

Las evidencias pueden ser capturas de pantalla o un video breve enlazado desde el documento. Si optan por un video, debe ser accesible públicamente, aunque no es necesario que esté listado.

Antes de la fecha límite, creen un pull request titulado **Revisión Entrega 3** e incluyan al ayudante de proyecto asignado. Se evaluará el estado del pull request y del despliegue al momento del cierre.

## Uso de inteligencia artificial generativa

Está permitido el uso de asistentes de programación basados en modelos de lenguaje. Deben declararlo en `docs/entrega3/README.md`, enumerando las herramientas utilizadas y la finalidad de cada uso.

La condición es la misma que rige en el resto del curso: el grupo responde por el código que entrega. Durante la revisión, el ayudante puede pedir a cualquier integrante que explique una decisión de arquitectura, una consulta al backend o el comportamiento de un componente. Una respuesta insuficiente afecta la evaluación del grupo, con independencia de que el código funcione.

También está permitido generar contenido de ejemplo para el seed del grupo: nombres de restaurantes, platos, reseñas y fotografías.

## Criterios de evaluación

La entrega se evalúa en cinco dimensiones. Cada dimensión recibe un puntaje entero de 1 a 7.

### 1. Cobertura funcional de las épicas — 35%

Se evalúa cada una de las diecisiete épicas por separado, en la escala general que aparece más abajo, y el puntaje de la dimensión es el promedio redondeado de esos diecisiete valores. Se considera si el flujo se recorre de extremo a extremo desde la aplicación instalada, si la información y las acciones exigidas están presentes, y si la visibilidad pública o privada se respeta en todas las vistas.

### 2. Fidelidad al diseño y consistencia con MUI — 20%

Se evalúa la correspondencia entre la aplicación implementada y el prototipo de la entrega 1, la definición y el uso efectivo del theme, la consistencia en el empleo de los componentes de la biblioteca, el tratamiento de los estados vacíos, de carga y de error, y la adecuación al contexto móvil.

### 3. Arquitectura y calidad del frontend — 15%

Se evalúan el enrutamiento y las URL direccionables, el manejo del estado de sesión y su invalidación, la composición y reutilización de componentes, la cancelación de solicitudes, la accesibilidad mínima exigida y la claridad del código.

### 4. Continuidad de la PWA y notificaciones dirigidas — 15%

Se evalúan la instalación desde el despliegue, el ciclo de vida del service worker sobre el build de React, la persistencia offline y su separación por usuario, la selección de destinatarios a partir de los seguimientos, la ausencia de notificaciones duplicadas y la navegación desde `notificationclick` hacia la vista correspondiente.

### 5. Despliegue, reproducibilidad y verificación — 15%

Se evalúan el despliegue accesible bajo el subdominio del grupo con HTTPS y build de producción, la reproducibilidad del procedimiento documentado, el manejo de claves y secretos, las pruebas que acompañan al código y la calidad de las evidencias del informe.

### Escala general

| Puntaje | Descripción |
| --- | --- |
| **1** | El requisito no está implementado o no puede ejecutarse |
| **2** | Existen componentes aislados o un intento reconocible, pero el flujo principal no puede completarse |
| **3** | El flujo principal funciona parcialmente, con omisiones relevantes, estados incorrectos o pasos manuales no documentados |
| **4** | El flujo esencial puede completarse, pero presenta limitaciones que afectan su confiabilidad, su usabilidad o su seguridad |
| **5** | El requisito funciona de extremo a extremo, aunque el manejo de estados o errores relevantes todavía presenta omisiones |
| **6** | El requisito está implementado de forma completa y robusta; solo presenta deficiencias menores |
| **7** | El requisito está implementado de forma completa, robusta y consistente, sin deficiencias relevantes para la dimensión evaluada |

La nota es la suma ponderada de los puntajes de cada dimensión, redondeada a un decimal. La escala resultante va de 1,0 a 7,0.

Una aplicación que no esté desplegada y accesible al momento del cierre se evalúa sobre lo que pueda ejecutarse localmente desde el repositorio, y la dimensión 5 recibe el puntaje que corresponda a esa situación.

## Fuera de alcance

Para mantener el foco de la entrega, no se solicita implementar:

* Modificaciones al backend provisto, salvo la integración del emisor de Web Push propio del grupo y el seed de contenido de demostración.
* Renderizado en el servidor, generación estática o cualquier variante que aparte a la aplicación del modelo de página única servida como archivos estáticos.
* Escrituras offline, Background Sync o resolución de conflictos.
* Mensajería en tiempo real, chat o presencia.
* Migración del backend a una arquitectura serverless, que es el objeto de la entrega 4.
* Compatibilidad simultánea con Android e iOS. Se mantiene la plataforma declarada en la entrega 2; si el grupo la cambia, debe declararlo en el informe.
