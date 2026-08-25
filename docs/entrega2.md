# Entrega 2 — Prueba de Concepto de una PWA

## Fecha de entrega: 25 de septiembre a las 23:59 hrs., en repositorio en GitHub

En esta entrega se debe desarrollar una Progressive Web Application (PWA) mínima, instalable y funcional. El propósito no es implementar todavía la interfaz diseñada en Figma, sino construir y comprobar las capacidades técnicas que se requerirán en una PWA.

La prueba de concepto se desarrolla con HTML, CSS y JavaScript, sin React ni otro framework que administre la construcción y actualización de la interfaz. La aplicación debe consumir el backend provisto, permitir consultar contenido, crear una reseña de un plato mediante el envío de una fotografía y un texto, y recibir notificaciones. La creación de una reseña debe producir un mensaje Web Push para los demás usuarios que tengan una suscripción activa, el cual debe mostrarse como una notificación del sistema aunque la aplicación receptora se encuentre cerrada.

La calidad visual no es el foco de esta entrega. Se espera una interfaz mínima que permita ejecutar y comprender los flujos, distinguir sus estados y diagnosticar errores.

## Código provisto

El repositorio contiene una aplicación base ejecutable mediante Docker Compose. El equipo docente provee y mantiene:

* El backend monolítico construido con FastAPI y PostgreSQL
* Los usuarios de demostración, la autenticación y las sesiones mediante una cookie `HttpOnly`
* El formulario de inicio de sesión, la restauración de la sesión, el cierre de sesión y el manejo de una sesión perdida en el frontend
* El cliente HTTP común y una vista protegida de ejemplo
* Los modelos y endpoints necesarios para obtener el feed, consultar una reseña específica y acceder a los demás datos utilizados por la prueba de concepto
* El endpoint y la persistencia necesarios para crear una reseña con una fotografía y un texto
* El gateway nginx y la configuración local de HTTP y HTTPS

Este código es parte del punto de partida y no debe reimplementarse sin una razón justificada. Los grupos deben adaptar la interfaz provista para mostrar el feed, el formulario de reseña y la vista de una reseña específica, pero el trabajo a evaluar se concentra en el ciclo de vida de la PWA, la persistencia offline y el flujo Web Push, no en el resultado visual de la aplicación.

## Por dónde comenzar

Antes de implementar el manifest, el service worker o Web Push, cada integrante debe poder ejecutar y explicar el código provisto. La documentación técnica se encuentra junto al componente que describe; el directorio `docs` se reserva para los enunciados y para el informe que prepare cada grupo.

| Si necesitas... | Comienza en... |
| --- | --- |
| Entender el esqueleto HTML/JavaScript, el cliente HTTP y los estados de autenticación | [README del frontend](../frontend/README.md) |
| Levantar el stack, conocer las credenciales de demostración y explorar la API | [Inicio rápido del backend](../backend/README.md#inicio-rápido) |
| Preparar Docker, red y certificados en tu computador | [Linux](../backend/docs/platforms/linux.md), [macOS](../backend/docs/platforms/macos.md) o [Windows y WSL](../backend/docs/platforms/windows.md) |
| Probar la aplicación mediante HTTPS desde un dispositivo | [HTTPS local y acceso desde un teléfono](../backend/README.md#https-local-y-acceso-desde-un-teléfono) y la guía de [Android](../backend/docs/platforms/android.md) o [iOS/iPadOS](../backend/docs/platforms/ios.md) |
| Comprender o extender FastAPI, SQLAlchemy y Alembic | [Arquitectura y desarrollo del backend](../backend/DEVELOPER.md) |
| Agregar tablas, configuración, endpoints y pruebas para Web Push | [Configuración](../backend/DEVELOPER.md#configuración), [migraciones](../backend/DEVELOPER.md#esquema-y-migraciones-con-alembic), [cómo agregar un endpoint](../backend/DEVELOPER.md#cómo-agregar-un-endpoint) y [estrategia de pruebas](../backend/DEVELOPER.md#estrategia-de-pruebas) |

Se recomienda comenzar el desarrollo en este orden:

1. Desde la raíz del repositorio, ejecuta `docker compose up --build`. Abre <http://localhost:5173> y comprueba el login, la restauración de sesión, el índice protegido y el logout descritos en la [verificación del frontend](../frontend/README.md#verificación-del-flujo).
2. Abre <http://localhost:5173/docs> y revisa el contrato OpenAPI de los endpoints provistos. Esta interfaz muestra los métodos, paths, cuerpos, respuestas y códigos de error que el frontend debe respetar.
3. Ejecuta las pruebas existentes antes de modificar el código. Los comandos del frontend están en su sección de [pruebas y build](../frontend/README.md#comandos); las alternativas para el backend están en la sección de [pruebas](../backend/README.md#pruebas). Ese resultado constituye la línea base con la cual distinguir una falla preexistente de una regresión introducida por el grupo.
4. Revisa la [arquitectura de un solo origen](../frontend/README.md#arquitectura-local-un-solo-origen) y conserva URLs relativas `/api/...`. No escribas `localhost`, una IP, un nombre mDNS ni el puerto del backend dentro del código del frontend.
5. Configura HTTPS y comprueba `/healthz` desde el dispositivo escogido al inicio del trabajo, no al final. La instalación, el service worker y Web Push dependen del navegador y de un contexto seguro; descubrir tarde una restricción de la plataforma pone en riesgo el flujo completo.
6. Una vez verificada la base, divide el trabajo en incrementos observables: manifest e instalación; app shell y actualización; persistencia offline por usuario; suscripción Push; backend Web Push; y recepción y navegación desde la notificación. Conserva funcionando autenticación y contenido después de cada incremento.

Para verificar Web Push, el seed local dispone de dos cuentas docentes con la
misma contraseña `demo-password`: `demo@example.com` (`@demo`) y
`demo2@example.com` (`@demo2`). Úsalas en perfiles, navegadores o dispositivos
independientes: habilita las notificaciones explícitamente en ambas
instalaciones, crea una reseña con una y confirma la notificación en la otra.
Estas credenciales sólo sirven para desarrollo local y no deben reutilizarse en
un despliegue real.

Los README explican cómo ejecutar y usar el código; `backend/DEVELOPER.md` explica cómo extenderlo. Cuando exista una diferencia entre un ejemplo escrito y el backend que se está ejecutando, el contrato expuesto en `/docs` y sus pruebas automatizadas son la referencia técnica que el grupo debe verificar.

## Alcance funcional

La prueba de concepto debe permitir completar flujos básicos de autenticación y contenido, así como el ciclo completo de Web Push.

### Autenticación y contenido

1. Un usuario inicia sesión mediante el flujo provisto. Si no hay conexión, la aplicación informa que no puede iniciar sesión
2. Después de que el backend confirma la sesión, la aplicación obtiene y muestra el feed
3. La interfaz debe incluir un indicador que señale si se está en modo online u offline. En modo offline debe informar que el contenido podría estar desactualizado
4. El usuario puede crear una versión acotada de la reseña definida en el enunciado general del proyecto. Para esta prueba de concepto, la reseña debe asociarse a una fotografía de un plato enviada mediante el formulario e incluir un texto; no se exige una calificación ni la implementación de comentarios. La creación se realiza mediante el endpoint provisto. Si no hay conexión, el acceso al formulario debe estar deshabilitado. Si la conexión se pierde durante el envío, la aplicación debe informar que no puede completar la operación. No es necesario implementar una cola de escritura ni reintentos
5. Después de que su sesión haya sido verificada, el usuario puede cerrar y volver a abrir la aplicación y consultar la copia persistida del feed aunque no exista conexión
6. El cierre de sesión requiere conexión. Una vez completado correctamente, la aplicación debe eliminar la información persistida asociada con el usuario

No se exige reproducir todavía el diseño de Figma ni implementar las demás épicas del proyecto. La vista del feed y el formulario de reseña pueden ser deliberadamente simples.

### Flujo Web Push

El flujo completo que debe funcionar es el siguiente:

1. Una vez autenticado, el usuario debe poder encontrar una acción explícita para habilitar las notificaciones
2. Al presionar el botón correspondiente, la aplicación debe revisar el estado del permiso. Solo debe solicitarlo si todavía no ha sido concedido ni rechazado; si ya fue concedido, debe continuar sin invocar nuevamente la solicitud ni mostrar el diálogo del navegador
3. Después de confirmar el permiso, la misma acción debe crear una suscripción Push y registrarla en el backend
4. Cuando un usuario crea una reseña, el backend debe enviar un mensaje Web Push a todos los demás usuarios que tengan una suscripción activa, excepto al autor de la reseña
5. El service worker del receptor debe atender el evento `push` y mostrar una notificación a nivel de dispositivo con un título y un texto que identifiquen la nueva reseña. La notificación debe aparecer aunque la aplicación receptora se encuentre cerrada
6. Cuando el usuario selecciona la notificación, la aplicación debe abrir la vista específica de la reseña correspondiente
7. Al cerrar sesión, la aplicación debe eliminar la suscripción del backend y desuscribir esa instalación. Si el usuario vuelve a iniciar sesión, debe habilitar nuevamente las notificaciones mediante la acción explícita de la interfaz

Para esta entrega se utiliza una regla deliberadamente simple: una reseña nueva notifica a todos los demás usuarios que tengan una suscripción Push activa; es decir, aún no se implementan relaciones de seguimiento de restaurantes u otros usuarios. Estas reglas forman parte del producto completo y se abordarán en etapas posteriores.

De forma deliberada, el backend entregado no implementa el sistema de Web Push. El grupo deberá diseñar y agregar la o las tablas, endpoints y configuraciones necesarias para que el flujo completo funcione. La implementación debe ser compatible con la especificación de Web Push y con la plataforma y el navegador escogidos, incluyendo VAPID y cifrado de mensajes. No se exige una cola de mensajes ni infraestructura asincrónica; el envío puede ocurrir inmediatamente después de persistir la reseña.

Se puede asumir que las notificaciones serán revisadas siempre en un dispositivo que tenga conexión; por lo tanto, no es necesario realizar cargas automatizadas de contenido en el caché cuando la notificación llega.

## Requisitos de la PWA

### Web App Manifest e instalación

La aplicación debe publicar y vincular un Web App Manifest válido. Como mínimo, debe definir:

* Una identidad estable mediante `id`
* `name` y `short_name`
* `start_url` y `scope` coherentes con las rutas reales de la aplicación
* Un modo de presentación apropiado para una aplicación instalada
* Colores de tema y fondo
* Iconos adecuados para la plataforma escogida

Las rutas del manifest y de los iconos deben funcionar en el build de producción, no solamente en el servidor de desarrollo. La aplicación debe servirse mediante HTTPS cuando se acceda desde un dispositivo; `localhost` puede utilizarse como contexto confiable durante el desarrollo en el mismo computador.

La entrega debe conservar un procedimiento reproducible basado en Docker Compose. La versión utilizada en la demostración debe corresponder al build de producción y debe poder levantarse mediante `docker compose up --build`, junto con las variables de entorno documentadas por el grupo.

### Service worker y ciclo de vida

El service worker debe:

* Registrarse con un alcance que permita controlar la aplicación completa
* Preparar el app shell durante su instalación
* Eliminar cachés pertenecientes a versiones anteriores durante la activación
* Controlar las solicitudes necesarias para proporcionar la experiencia offline definida en este enunciado
* Aplicar una estrategia de actualización que evite mezclar recursos incompatibles de dos versiones, ya sea esperando el término de los clientes anteriores o coordinando la actualización y recarga de la interfaz
* Atender los eventos `push` y `notificationclick`

### Persistencia y operación offline

La aplicación debe poder cerrarse y volver a abrirse sin conexión, conservando una experiencia útil de solo lectura. Para ello se utilizan mecanismos con responsabilidades diferentes:

* **Cache Storage** para el app shell: HTML, CSS, JavaScript, iconos y demás recursos estáticos indispensables
* **IndexedDB** para el último contenido estructurado del feed obtenido correctamente y los metadatos necesarios para asociarlo con el usuario correspondiente

Las respuestas JSON autenticadas de `/api/*` no deben almacenarse directamente en Cache Storage. Las fotografías necesarias para representar la copia offline del feed pueden persistirse como datos binarios en IndexedDB o en un caché de contenido separado por usuario. Cualquiera sea la estrategia escogida, estos recursos deben eliminarse al cerrar sesión y no deben quedar disponibles para otro usuario.

La sesión autenticada y el contexto offline son estados diferentes. La sesión solo se considera vigente después de que el backend la confirma. El contexto offline corresponde a una copia local asociada con el último usuario cuya sesión fue verificada y permite consultar su feed persistido cuando no es posible contactar al backend; no constituye una validación de que la sesión del servidor continúe vigente.

El comportamiento mínimo es el siguiente:

* Después de verificar una sesión y cargar correctamente el feed, la aplicación persiste el identificador del usuario, el contenido necesario y la fecha de actualización
* Si no es posible contactar al backend y existe un contexto offline, la aplicación muestra exclusivamente la copia asociada con ese usuario en modo de solo lectura
* La interfaz identifica el contenido persistido como una copia que puede estar desactualizada
* Si el backend responde que no existe una sesión vigente, la aplicación invalida el contexto offline y deja de mostrar su contenido protegido
* Los datos de usuarios diferentes no se mezclan. Cuando se verifica una sesión correspondiente a otro usuario, la copia anterior deja de estar disponible
* Un cierre de sesión completado correctamente elimina el contenido local asociado con ese usuario
* Si no existe una sesión confirmada ni un contexto offline, la aplicación muestra el app shell e informa que necesita conexión para iniciar sesión
* Al recuperar conectividad, la aplicación vuelve a verificar la sesión antes de habilitar operaciones protegidas
* El inicio y cierre de sesión, la creación de reseñas y cualquier otra escritura requieren conexión. Las solicitudes `POST`, `PATCH` y `DELETE` no se encolan ni se simulan como exitosas

No se exige Background Sync, una cola de escrituras, reintentos persistentes ni resolución de conflictos.

## Permiso y suscripción Push

Una vez que el usuario se encuentre autenticado, la aplicación debe presentar una acción explícita para habilitar las notificaciones, por ejemplo un botón. Esa acción debe revisar el estado actual del permiso, solicitarlo solamente si aún no existe una decisión, crear la suscripción Push cuando el permiso esté concedido y registrarla en el backend.

El permiso no debe solicitarse automáticamente al instalar o abrir la aplicación, al iniciar sesión ni al activar el service worker. La llamada que muestra el diálogo del navegador debe ser consecuencia directa de la interacción con el botón. Si el permiso ya fue concedido, la aplicación no debe invocar nuevamente la solicitud: el mismo botón debe continuar directamente con la creación o el registro de la suscripción pendiente.

La interfaz debe distinguir al menos estos estados:

* La capacidad no está disponible en el navegador o modo de ejecución actual
* El permiso todavía no ha sido solicitado
* El permiso fue concedido, pero aún no existe una suscripción Push
* La suscripción Push fue creada, pero su registro en el backend aún no ha sido confirmado
* La suscripción está activa y confirmada por el backend
* El permiso fue rechazado
* La suscripción o su registro fallaron y es posible volver a intentar

Rechazar el permiso no debe impedir consultar el contenido de la aplicación. No se debe solicitar nuevamente el permiso de manera automática en cada carga.

El cierre de sesión requiere conexión. Como parte de este flujo, la aplicación debe eliminar el registro de la suscripción en el backend mientras la sesión aún pueda autenticar esa operación y desuscribir la instalación mediante la API Push. Un inicio de sesión posterior no debe reactivar las notificaciones automáticamente: el usuario debe habilitarlas nuevamente desde la interfaz.

Una persona puede utilizar la misma cuenta desde más de una instalación, dispositivo o perfil. Por lo tanto, el backend debe admitir más de una suscripción activa por usuario. El endpoint de una `PushSubscription` identifica una suscripción y no un dispositivo: debe ser único en el backend, y registrar nuevamente el mismo endpoint para el mismo usuario debe ser una operación idempotente.

## Backend de Web Push

Cada grupo debe implementar en el backend la parte correspondiente a Web Push. Esta implementación incluye:

1. Una estructura persistente para asociar una suscripción con el usuario autenticado, junto con un mecanismo reproducible para crearla al levantar una instalación nueva del proyecto
2. Un endpoint autenticado para registrar o actualizar una suscripción
3. Un endpoint autenticado para eliminar o desactivar una suscripción
4. Un mecanismo para obtener la clave pública VAPID desde el cliente
5. Un emisor que reciba una reseña creada, determine sus destinatarios y envíe el mensaje a cada suscripción activa
6. La integración del emisor en el flujo provisto para crear una reseña, de modo que el envío se inicie después de persistirla
7. Manejo independiente del resultado de cada envío
8. Eliminación o desactivación de endpoints que el push service informe como expirados o permanentemente inválidos

La identidad del usuario debe obtenerse desde la sesión autenticada. El cliente no debe poder registrar una suscripción a nombre de otro usuario enviando un `user_id` arbitrario.

Los endpoints que modifican suscripciones deben conservar las mismas protecciones utilizadas por las demás operaciones autenticadas del backend, incluyendo la validación del origen de la solicitud.

El endpoint y el material criptográfico `p256dh` y `auth` entregados por una `PushSubscription` deben tratarse como datos sensibles: no deben aparecer innecesariamente en logs, respuestas de error ni documentación pública.

Para esta prueba de concepto, el envío puede iniciarse inmediatamente después de persistir la reseña. No se exige una cola de mensajes ni infraestructura asincrónica. Una vez persistida la reseña, su endpoint debe responder exitosamente aunque falle el envío a una o más suscripciones. Estos fallos no deben revertir la reseña ni impedir los envíos a los demás destinatarios.

Si el endpoint de una suscripción expira o es considerado permanentemente inválido, no es necesario revisar proactivamente para informar al usuario ni forzar el restablecimiento de la suscripción. Para esta entrega, basta con eliminarla o desactivarla en el backend cuando el push service comunique un error permanente, como una respuesta `404` o `410`.

## Claves VAPID y configuración

Cada grupo debe generar su propio par de claves VAPID. No se compartirán claves entre grupos.

* La clave privada permanece exclusivamente en el backend y se debe configurar mediante una variable de entorno
* La clave pública puede enviarse al frontend y utilizarse al crear la suscripción
* El mismo par de claves debe conservarse entre ejecuciones y despliegues del grupo; no debe generarse nuevamente al iniciar la aplicación
* Ninguna clave privada, archivo `.env` real ni otro secreto debe incorporarse al repositorio
* Los nombres de las variables requeridas deben documentarse y agregarse, con valores de ejemplo no secretos, a un archivo `.env.local.example` o equivalente

El grupo puede seleccionar una biblioteca compatible con Web Push para el backend Python. Debe declarar la dependencia, fijar una versión compatible con el proyecto y poder explicar cómo utiliza VAPID y cifra el mensaje para el push service.

## Recepción y presentación de la notificación

El evento `push` debe ser atendido por el service worker y producir una notificación visible. El payload debe contener solamente la información necesaria para presentarla y localizar el contenido relacionado.

Como mínimo, la notificación debe incluir:

* Un título comprensible
* Un texto que identifique la actividad nueva
* Una URL o identificador que permita llegar a la vista específica de la reseña

El evento `notificationclick` debe cerrar la notificación y abrir la URL de la vista específica de la reseña. Si ya existe una ventana dentro del alcance de la aplicación, debe enfocarla y hacer que navegue o actualice su interfaz para mostrar esa reseña; si no existe, debe abrir una nueva ventana.

Como se indicó anteriormente, se puede asumir que el acceso a las notificaciones se realiza desde un dispositivo con conexión. No es necesario implementar cargas automáticas de contenido en el caché cuando la notificación llega.

## Plataforma objetivo

Cada grupo debe escoger una de las siguientes plataformas para esta entrega:

* Android
* iOS

En ambos casos, la demostración y las evidencias deben obtenerse utilizando la PWA instalada, no una pestaña normal del navegador.

El grupo debe declarar:

* Marca y modelo del dispositivo utilizado
* Versión del sistema operativo
* Navegador y versión utilizados para instalar la PWA
* Procedimiento seguido para instalarla
* Diferencias, restricciones o problemas encontrados en esa combinación

En iOS la prueba debe realizarse desde la aplicación agregada a la pantalla de inicio. En Android, debe realizarse desde la PWA instalada mediante el navegador escogido.

La notificación debe recibirse incluso cuando la aplicación instalada se encuentre cerrada. No es necesario demostrar compatibilidad simultánea con Android e iOS en esta entrega.

## Verificación mínima

Antes de entregar, los grupos deben comprobar al menos los siguientes escenarios:

1. La aplicación se instala y se abre en modo independiente
2. El manifest, los iconos y el service worker se cargan sin errores
3. Una versión nueva del service worker reemplaza correctamente a la anterior, elimina cachés obsoletos y actualiza la interfaz sin mezclar recursos incompatibles
4. Después de verificar una sesión y cargar el feed, la aplicación puede cerrarse y volver a abrirse sin conexión para consultar la copia asociada con ese usuario
5. Una instalación sin sesión previa no expone contenido protegido al abrirse sin conexión
6. El contenido de un usuario no aparece después de iniciar sesión con una cuenta diferente
7. El inicio y cierre de sesión y la creación de reseñas informan que requieren conexión y no aparentan completarse offline
8. El permiso para notificaciones solo se solicita después de presionar el botón dispuesto para habilitar las notificaciones y únicamente si todavía no existe una decisión; si ya fue concedido, no se solicita nuevamente, y si fue rechazado, las demás funciones continúan disponibles
9. La acción explícita de activar notificaciones permite crear y registrar una suscripción, y repetir el registro no produce duplicados
10. Al cerrar sesión se eliminan la suscripción local, su registro en el backend y el contenido persistido del usuario; un nuevo inicio de sesión no reactiva las notificaciones automáticamente
11. Un usuario crea una reseña y otro usuario suscrito recibe la notificación con la PWA cerrada. El usuario que crea la reseña no recibe la notificación
12. Seleccionar la notificación abre la vista específica de la reseña o enfoca una ventana existente y la dirige hacia esa vista
13. Un endpoint inválido no impide enviar notificaciones a las demás suscripciones

Las verificaciones deben utilizar al menos dos usuarios y dos instalaciones o perfiles independientes: uno crea la reseña y el otro recibe la notificación. La instalación receptora debe corresponder a la PWA instalada en la plataforma declarada.

## Formato de la entrega

Todo el código debe quedar versionado en el repositorio del grupo. En `docs/entrega2/README.md` deben incluir:

* Nombre de la aplicación e integrantes del grupo
* Plataforma, dispositivo, sistema operativo y navegador evaluados
* Instrucciones reproducibles para configurar las variables de entorno, ejecutar la aplicación e instalarla
* Descripción breve de la estrategia de caché y del esquema utilizado en IndexedDB
* Descripción del ciclo de la suscripción Push y de las responsabilidades del frontend, service worker y backend
* Nombres de los endpoints implementados y ejemplos de sus contratos, sin incluir secretos ni endpoints reales de suscripciones
* Evidencia de la aplicación instalada
* Evidencia de la ejecución offline después de cerrar y volver a abrir la PWA
* Evidencia de una notificación recibida con la aplicación receptora cerrada
* Resultado de los comandos de prueba y verificación utilizados
* Problemas conocidos o restricciones de la plataforma escogida
* Declaración del uso de herramientas de inteligencia artificial generativa

Las evidencias pueden consistir en capturas de pantalla o en un video breve enlazado desde el documento. Si el grupo opta por incluir un video, este debe ser accesible públicamente, aunque no es necesario que se encuentre listado.

Antes de la fecha límite, cada grupo debe crear un pull request titulado **"Revisión Entrega 2"** e incluir al ayudante de proyecto asignado. Se evaluará el estado del pull request al momento del cierre de la entrega.

## Criterios de evaluación

La entrega se evalúa en cinco dimensiones. Cada dimensión recibe un puntaje entero de 1 a 7.

### 1. Integración funcional — 15%

Evalúa el uso correcto del código base, la carga del feed, la creación y consulta de una reseña mediante los endpoints provistos y el manejo de estados de sesión, carga y error. No se evalúa la calidad visual de la interfaz, aunque se espera una usabilidad suficientemente intuitiva.

### 2. Instalación y ciclo de vida — 20%

Evalúa el manifest, los iconos, la instalación en la plataforma declarada, el alcance del service worker y el manejo de instalación, activación, actualización y limpieza de cachés.

### 3. Persistencia y operación offline — 25%

Evalúa el app shell, la persistencia del contenido, la separación por usuario, la reapertura sin conexión, la identificación de datos desactualizados y el bloqueo correcto de operaciones que requieren el backend.

### 4. Web Push de extremo a extremo — 30%

Evalúa permiso, suscripción, persistencia en el backend, configuración VAPID, selección de destinatarios, emisión, recepción, presentación de la notificación y manejo de `notificationclick`.

### 5. Calidad técnica y verificación — 10%

Evalúa seguridad de credenciales y suscripciones, manejo de errores, pruebas, claridad del código, documentación reproducible y calidad de las evidencias en la plataforma escogida.

Para cada dimensión se utiliza la siguiente escala general:

| Puntaje | Descripción |
| --- | --- |
| **1** | El requisito no está implementado o no puede ejecutarse |
| **2** | Existen componentes aislados o un intento reconocible, pero el flujo principal no puede completarse |
| **3** | El flujo principal funciona parcialmente, con omisiones relevantes, estados incorrectos o pasos manuales no documentados |
| **4** | El flujo esencial puede completarse, pero presenta limitaciones que afectan su confiabilidad o seguridad |
| **5** | El requisito funciona de extremo a extremo, aunque el manejo de estados o errores relevantes todavía presenta omisiones |
| **6** | El requisito está implementado de forma completa y robusta; solo presenta deficiencias menores |
| **7** | El requisito está implementado de forma completa, robusta y consistente, sin deficiencias relevantes para la dimensión evaluada |

La nota se calcula como la suma ponderada de los puntajes obtenidos en cada dimensión y se redondea a un decimal. Por lo tanto, la escala de notas resultante va de 1,0 a 7,0.

## Fuera de alcance

Para mantener el foco de la prueba de concepto, no se solicita implementar ninguno de los siguientes elementos:

* React u otros frameworks o bibliotecas que administren la construcción, el estado y la actualización de la interfaz
* Reproducir el diseño de Figma
* Geolocalización o mapas
* Compatibilidad simultánea con Android e iOS
* Escrituras offline, Background Sync o resolución de conflictos
* Seguimientos, preferencias de notificación o deduplicación de mensajes
* Colas de mensajería, workers de backend o infraestructura serverless

Se permite utilizar bibliotecas de estilos, iconografía, validación, formato o manipulación del DOM que faciliten el desarrollo, siempre que no introduzcan un modelo de componentes, renderizado o gestión de estado que reemplace el trabajo explícito con HTML, CSS y JavaScript que se busca realizar en esta entrega.
