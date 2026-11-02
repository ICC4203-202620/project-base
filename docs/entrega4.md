# Entrega 4 — Backend serverless en AWS

## Fecha de entrega: viernes 13 de noviembre a las 23:59 hrs., en la rama `entrega-4` y con despliegue en AWS

En esta entrega cada grupo migra la aplicación desarrollada en la [entrega 3](entrega3.md) desde su arquitectura monolítica a una arquitectura serverless en AWS. Se conservan el frontend React, las funcionalidades del [enunciado general del proyecto](../README.md) y las capacidades de PWA de las entregas anteriores.

La migración tiene un propósito formativo: practicar una alternativa para desarrollar aplicaciones de alta escalabilidad y disponibilidad. El trabajo se concentra en adaptar la ejecución del backend y la persistencia de sus datos y fotografías a los servicios de AWS, y en comprender cómo se integran para mantener funcionando la aplicación.

El resultado debe ser la misma aplicación, publicada sobre una infraestructura diferente. Una persona debe poder instalarla desde su nueva dirección, autenticarse, consultar y publicar contenido, y recibir las notificaciones que correspondan. No se solicita desarrollar una aplicación nueva ni rediseñar la interfaz.

## Código provisto

El equipo docente provee la base serverless en la carpeta `serverless` del repositorio. Esta base incluye:

* El backend docente de la entrega 3 adaptado a Lambda y Aurora DSQL, con el contrato necesario para sus diecisiete épicas.
* La separación en cuatro funciones Lambda y las rutas de API Gateway que atiende cada una.
* La autenticación, las sesiones y el acceso a los datos compartidos entre las funciones.
* La preparación del esquema docente y de los datos de demostración.
* El almacenamiento de fotografías en S3, respetando su visibilidad.
* La resolución de destinatarios y la integración que permite solicitar el envío de mensajes Web Push después de guardar una actividad.
* Las plantillas de CloudFormation y los scripts Python para preparar los paquetes, desplegar, publicar el frontend, actualizar la aplicación y eliminar sus recursos.

La [guía de la base serverless](../serverless/README.md) describe su organización y procedimiento de uso. La infraestructura se entrega como punto de partida; no corresponde reconstruirla desde cero ni reimplementar las funcionalidades de dominio provistas.

La gestión de suscripciones y el código de envío Web Push siguen siendo trabajo del grupo. Cada grupo traslada sus tablas, endpoints, configuración VAPID y código de envío, junto con las demás extensiones propias del backend. La base no impone un nuevo esquema de suscripciones ni reemplaza el frontend React o las capacidades de PWA ya desarrolladas.

## Continuidad con la entrega 3

La entrega 3 se centró en construir el frontend completo con React, integrando las capacidades de PWA desarrolladas en la entrega 2 con el backend monolítico provisto. Esa aplicación constituye el punto de partida de esta entrega: el trabajo ya desarrollado se adapta a la infraestructura serverless.

El cambio de infraestructura no modifica su alcance funcional. Deben seguir funcionando las diecisiete épicas de la entrega 3, con las mismas reglas de visibilidad, seguimiento, feed y notificaciones dirigidas. La separación del backend no debe alterar las operaciones disponibles ni permitir el acceso a información protegida.

También se conservan las capacidades de PWA:

* Instalación y apertura en modo independiente, con manifest, iconos y alcance del service worker coherentes con las rutas del despliegue.
* Actualización del service worker y del frontend sin mezclar recursos incompatibles de dos versiones.
* Consulta del feed persistido después de cerrar y volver a abrir la aplicación sin conexión, en modo de solo lectura e identificado como una copia que puede estar desactualizada.
* Separación del contenido persistido por usuario y eliminación de la copia correspondiente al cerrar sesión.
* Permiso y suscripción Push mediante una acción explícita del usuario, sin volver a solicitar un permiso ya concedido.
* Recepción de notificaciones con la PWA cerrada y navegación hacia la actividad correspondiente al seleccionarlas.

Se mantiene la plataforma declarada en la entrega 3. No se exige compatibilidad simultánea con Android e iOS; si el grupo cambia de plataforma, debe declararlo y documentar sus verificaciones.

El despliegue monolítico permanece disponible en paralelo, sin modificar sus datos, su dominio ni su mecanismo de publicación. La adaptación se realiza dentro de `serverless`, sin reemplazar los archivos que mantienen funcionando la versión anterior.

El nuevo sistema comienza con sus propios datos de demostración. No se requiere trasladar usuarios, sesiones, actividades, fotografías ni suscripciones desde el monolito. La PWA se instala desde la dirección de CloudFront y las suscripciones se crean nuevamente para ese origen; tampoco se traslada el contenido que el navegador conserva para la aplicación anterior.

## Por dónde comenzar

La documentación técnica se mantiene junto a los componentes que describe. El directorio `docs` contiene los enunciados y el informe de cada entrega.

| Para... | Documento de referencia |
| --- | --- |
| Conocer la organización, configuración y despliegue de la nueva base | [Guía de la base serverless](../serverless/README.md) |
| Revisar los flujos que deben conservarse | [Entrega 3](entrega3.md) y el informe del grupo en `docs/entrega3/README.md` |
| Consultar el contrato de las diecisiete épicas | [Contrato de la API por épica](../backend/docs/api.md) |
| Identificar los componentes que el grupo extendió en el backend | [Arquitectura y desarrollo del backend](../backend/DEVELOPER.md) |

El orden de trabajo recomendado es:

1. Obtener una copia de la base serverless provista y revisar su guía de configuración y despliegue.
2. Desplegar esa base, sin modificar su código ni integrar componentes del grupo, en la cuenta AWS de uno de sus integrantes. Solo se ajusta la configuración necesaria para el despliegue. Se debe comprobar el funcionamiento de los servicios y de las operaciones provistas antes de continuar, para distinguir problemas de configuración de aquellos que puedan introducirse durante la adaptación.
3. Comprobar el funcionamiento de la entrega 3 e identificar las tablas, endpoints, dependencias y configuraciones que agregó el grupo.
4. Incorporar la base serverless al repositorio del grupo mediante el procedimiento de actualización descrito en el enunciado general, conservando el despliegue monolítico.
5. Adaptar las tablas y operaciones propias a Aurora DSQL, ubicar los endpoints en la función correspondiente y trasladar el código de envío Web Push a la Lambda destinada a esa tarea.
6. Publicar el frontend React, preparar contenido de demostración e instalar la PWA desde CloudFront.
7. Verificar los flujos completos y actualizar el despliegue para comprobar que conserva sus datos, archivos, suscripciones y dirección pública.

## Requisitos del backend

### Funciones Lambda y API Gateway

En el backend monolítico, las operaciones de la aplicación y el envío de mensajes Web Push forman parte de un mismo despliegue. En esta entrega, esas responsabilidades se distribuyen en cuatro funciones Lambda.

El código de envío Web Push desarrollado por el grupo se traslada a una Lambda dedicada. Cuando una operación requiere notificar a otros usuarios, la Lambda que la procesa guarda los cambios y luego invoca a esta otra función, entregándole los datos de la actividad y los identificadores de sus destinatarios. Esta consulta las suscripciones activas y envía los mensajes Web Push correspondientes. Por esa responsabilidad, se denomina **función emisora de notificaciones**.

Las otras tres funciones atienden las solicitudes HTTP de la aplicación mediante API Gateway. La distribución de responsabilidades es la siguiente:

| Función | Responsabilidad |
| --- | --- |
| **Cuentas y autenticación** | Registro, inicio y cierre de sesión, operaciones de cuenta y endpoints autenticados de administración de suscripciones Push |
| **Operaciones de dominio** | Restaurantes, actividades, reseñas, evaluaciones, seguimientos, feed y demás operaciones que no corresponden al manejo de archivos |
| **Fotografías** | Recepción, procesamiento y acceso a fotografías almacenadas en S3, respetando su visibilidad |
| **Emisor de notificaciones** | Consulta de las suscripciones de los destinatarios y envío de mensajes Web Push, sin un endpoint público |

Las funciones que atienden la API conservan FastAPI y utilizan [Mangum](https://mangum.fastapiexpert.com/), una biblioteca Python que adapta su ejecución al modelo de AWS Lambda. API Gateway invoca la función con un evento que describe la solicitud HTTP; Mangum transforma ese evento para que FastAPI lo procese y convierte la respuesta al formato que espera API Gateway.

Este adaptador permite reutilizar las rutas, validaciones y dependencias del backend existente, sin reescribir cada endpoint como un handler de Lambda ni mantener un servidor HTTP ejecutándose permanentemente. Cada función conserva solo las rutas que le corresponden.

La función emisora no atiende solicitudes HTTP desde API Gateway, sino invocaciones directas desde las otras Lambdas. Por ello, utiliza un handler de Python sin FastAPI ni Mangum.

El grupo debe incorporar sus extensiones respetando esta separación. Se permite compartir módulos de configuración, autenticación, modelos y acceso a datos, así como el mismo esquema DSQL. No se exige una Lambda por endpoint ni una base de datos diferente por función. Cada función Lambda debe incluir únicamente el código y las bibliotecas necesarios para cumplir su responsabilidad.

La sesión se reconoce de manera consistente en las funciones que atienden operaciones protegidas. Se conserva la cookie `HttpOnly` y `Secure`, y la autorización efectiva siempre se realiza en el backend.

Las funciones no deben depender de usuarios, sesiones, suscripciones o datos de negocio conservados exclusivamente en memoria. Una solicitud debe poder atenderse desde la información persistida y la configuración del despliegue, aunque esa función no haya ejecutado solicitudes anteriores.

### Persistencia en Aurora DSQL

[Amazon Aurora DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/what-is-aurora-dsql.html) es un servicio de base de datos relacional serverless de AWS, compatible con PostgreSQL. Permite organizar los datos en tablas y operar sobre ellos mediante SQL. AWS administra la infraestructura y ajusta su capacidad según la demanda, sin que sea necesario desplegar ni mantener un servidor de base de datos.

En esta entrega, Aurora DSQL reemplaza al servidor PostgreSQL del despliegue monolítico para almacenar los datos relacionales de la aplicación, incluyendo las tablas de suscripciones y las extensiones propias. La base docente resuelve la adaptación de las operaciones que proporciona; el grupo debe comprobar y adaptar sus tablas, consultas y transacciones.

La compatibilidad con PostgreSQL facilita la migración, aunque pueden ser necesarios ajustes en las tablas, consultas y transacciones para utilizar Aurora DSQL. Los cambios necesarios en los componentes propios deben quedar documentados.

La preparación y actualización del esquema tienen un procedimiento reproducible. No se deben crear tablas ni cargar datos de demostración en cada solicitud o durante la inicialización de cada Lambda. Las operaciones propias utilizan el soporte de transacciones y reintentos de la base cuando corresponde.

### Fotografías en S3

Las fotografías se almacenan en S3, no en el sistema de archivos temporal de una Lambda. La aplicación debe conservar su acceso después de publicar una nueva versión del backend.

El acceso respeta la visibilidad de cada fotografía. La entrega de una fotografía privada requiere autorización del backend. El bucket no debe habilitar acceso público directo a los archivos para resolver su visualización.

### Emisor de Web Push

Se conserva la regla de notificaciones de la entrega 3: una actividad pública notifica a quienes siguen a su autor o al restaurante, excluyendo al autor. Una actividad privada no notifica a nadie. Cuando coinciden ambos seguimientos, el usuario recibe un solo aviso por instalación suscrita.

La regla sigue siendo **una entrada del feed, un aviso**. Varias fotografías publicadas como una sola actividad producen un aviso; agregar una reseña a una fotografía ya publicada no produce una segunda notificación por esa entrada.

La base proporciona la resolución de destinatarios y la invocación de la Lambda emisora. El grupo adapta su emisor para completar este flujo:

1. La función que procesa la actividad confirma su escritura en DSQL.
2. El punto de integración provisto determina los destinatarios e invoca al emisor de manera síncrona, con los datos de la actividad y los identificadores de esos usuarios.
3. El emisor consulta sus suscripciones activas, realiza los envíos Web Push y devuelve el resultado.
4. La función que lo invocó completa la respuesta de la operación original.

La espera corresponde al término del emisor, no a que el dispositivo reciba o muestre la notificación. Los envíos deben completarse antes de que el emisor retorne, sin dejar hilos o tareas pendientes que dependan de continuar ejecutándose después de la respuesta.

Los errores se tratan por suscripción, de modo que uno no impida intentar los restantes envíos. Los endpoints expirados o permanentemente inválidos se eliminan o desactivan. Los errores controlados de invocación o envío se registran sin revertir una actividad ya guardada ni presentarla como si no se hubiera guardado.

El envío queda fuera de la transacción de la actividad, para que un reintento de la escritura no repita también los mensajes. La escritura y la invocación no son atómicas: puede guardarse la actividad y fallar el aviso. No se solicita implementar colas, invocaciones asíncronas ni garantías de entrega.

Los endpoints de suscripciones obtienen la identidad desde la sesión autenticada. El navegador no puede registrar una suscripción a nombre de otro usuario ni invocar directamente al emisor para escoger los destinatarios.

La clave privada VAPID se configura exclusivamente en la función emisora. La clave pública queda disponible para el cliente; ambas se conservan entre actualizaciones.

## Despliegue

Cada grupo presenta **un despliegue en la cuenta AWS de uno de sus integrantes**, si bien todos los integrantes deben comprender y poder reproducir el procedimiento.

La base proporciona las plantillas CloudFormation y los scripts Python para desplegar desde un terminal local. No se utiliza el workflow de GitHub Actions del monolito ni la infraestructura compartida del curso. El procedimiento no requiere CloudShell, SAM, AWS CLI ni Docker.

Los recursos regionales se crean en **South America (São Paulo), `sa-east-1`**, con un clúster Aurora DSQL de una sola región. El procedimiento de configuración y publicación se describe en la [guía de la base serverless](../serverless/README.md).

### Publicación del frontend y de la API

El build de producción de React se almacena en un bucket S3 privado y se distribuye mediante CloudFront, con acceso al bucket mediante Origin Access Control (OAC). No se habilita el bucket como un sitio web público.

La dirección de la aplicación es el dominio HTTPS asignado por CloudFront. No se requiere dominio propio, configuración DNS ni certificado personalizado.

CloudFront dirige `/api/*` hacia API Gateway, que selecciona la función según la ruta y el método HTTP. El frontend conserva las llamadas relativas a `/api/v1/...`; el navegador accede a la aplicación y a su API mediante un mismo origen.

El despliegue debe permitir:

* Abrir y recargar una ruta interna de React, incluyendo la vista a la que dirige una notificación.
* Obtener el manifest, los iconos, el service worker y los recursos del build desde sus rutas correctas.
* Consultar la API sin depender de `localhost`, del dominio del monolito ni de la dirección directa de API Gateway.
* Utilizar los mapas y demás servicios externos, con las restricciones de acceso ajustadas al nuevo origen sin eliminar las necesarias para el monolito.

### Actualización, permisos y operación

La infraestructura debe poder reconstruirse a partir del repositorio y de la configuración documentada, sin depender de cambios manuales no registrados. La creación inicial, la actualización y la eliminación son operaciones diferentes.

Una actualización debe conservar la distribución y su dirección pública, los datos, las fotografías, las suscripciones, los secretos de autenticación y las claves VAPID. No debe volver a cargar los datos de demostración sobre los registros existentes ni exigir reinstalar la PWA. El frontend y el service worker deben actualizarse sin mezclar archivos incompatibles de dos builds.

Se exige:

* Roles de ejecución con permisos acotados a los recursos y operaciones de cada función, sin `AdministratorAccess` en las Lambdas.
* Invocación del emisor permitida a las funciones que producen actividades, sin exponerlo como un endpoint público.
* Credenciales AWS, secretos de autenticación y claves privadas VAPID fuera del repositorio y del build del frontend. La configuración pública necesaria para el cliente sí puede incluirse en el build, con las restricciones que correspondan.
* Registros de CloudWatch que permitan diagnosticar errores de la API, de persistencia y de emisión, sin publicar contraseñas, cookies ni suscripciones completas.

Los recursos pueden generar cobros. El grupo debe revisar su consumo y la cobertura de su cuenta, sin asumir que la actividad será gratuita. Cerrar la consola no elimina recursos. El informe debe documentar la limpieza: los despliegues de prueba se eliminan cuando dejan de utilizarse, y el evaluado se mantiene hasta que el equipo docente comunique el cierre de la revisión.

## Verificación mínima

Las verificaciones deben realizarse sobre el despliegue en AWS y, cuando involucren capacidades móviles, desde la PWA instalada. Deben utilizarse al menos dos cuentas de la aplicación y dos instalaciones o perfiles independientes para las pruebas de privacidad y notificaciones.

Antes de entregar, el grupo debe comprobar al menos lo siguiente:

1. El frontend se obtiene mediante CloudFront con HTTPS y los archivos del bucket privado no quedan disponibles mediante acceso público directo.
2. La API utiliza el mismo origen del frontend, sus rutas llegan a las funciones correspondientes y no dependen del backend monolítico.
3. Se puede registrar una cuenta, iniciar sesión, utilizar operaciones protegidas en las distintas funciones y cerrar sesión.
4. Las diecisiete épicas conservan su funcionamiento desde el nuevo despliegue; el informe identifica el resultado de su revisión.
5. Las actividades privadas no quedan disponibles para otra cuenta. Las fotografías declaradas privadas tampoco pueden obtenerse mediante la API ni mediante acceso directo a sus archivos.
6. La PWA se instala desde CloudFront, permite abrir y recargar una ruta interna y puede consultar el feed persistido al reabrirse sin conexión.
7. El contenido offline no se mezcla entre usuarios y el cierre de sesión elimina la copia correspondiente.
8. Una publicación pública relevante para la segunda cuenta produce una notificación con su PWA cerrada. Al seleccionarla se abre la actividad en el nuevo despliegue.
9. Una publicación privada, una actividad propia o una actividad sin relación de seguimiento no produce una notificación para esa cuenta. Seguir al autor y al restaurante no produce dos avisos por la misma instalación.
10. Una suscripción inválida no impide intentar los envíos a las demás suscripciones ni revierte la actividad publicada. El resultado puede diagnosticarse en los registros.
11. Una actualización del frontend y del backend conserva la dirección de CloudFront, los datos, las fotografías y las suscripciones, y permite seguir recibiendo notificaciones sin reinstalar la PWA.
12. El despliegue monolítico continúa disponible de manera independiente.
13. Las pruebas aplicables al código adaptado pasan, y la documentación permite reproducir el despliegue y sus verificaciones.

## Formato de la entrega

Cada grupo debe crear y publicar una rama con el nombre `entrega-4` en su repositorio, con todo el código, las definiciones de infraestructura y la documentación de esta entrega. En `docs/entrega4/README.md` se debe incluir:

* Nombre de la aplicación e integrantes del grupo.
* URL del despliegue serverless que se presenta para evaluación y URL del despliegue monolítico que permanece disponible.
* Plataforma, dispositivo, sistema operativo y navegador utilizados para verificar la PWA instalada.
* Instrucciones de acceso a dos cuentas de demostración de la aplicación, con contenido suficiente para realizar la revisión, sin compartir credenciales AWS ni reutilizar contraseñas personales.
* Descripción de los servicios utilizados, la responsabilidad de cada Lambda y el recorrido de una solicitud y de una notificación.
* Identificación de los componentes propios trasladados desde las entregas anteriores y de los cambios necesarios para adaptarlos.
* Instrucciones reproducibles para configurar, desplegar, preparar los datos iniciales, actualizar y eliminar el despliegue, con los nombres de las variables requeridas y sin valores secretos.
* Descripción de los ajustes al esquema y a las operaciones propias en Aurora DSQL.
* Descripción de la integración del emisor, de la administración de suscripciones y del tratamiento de errores de envío.
* Resultado de la revisión de las diecisiete épicas y de las verificaciones de esta entrega.
* Evidencia de la aplicación instalada desde CloudFront, de la consulta offline, de una notificación dirigida y de una actualización que conserva datos, fotografías y suscripciones.
* Resultado de las pruebas ejecutadas, problemas conocidos y restricciones de la solución.
* Declaración del uso de herramientas de inteligencia artificial generativa.

Las evidencias pueden consistir en capturas de pantalla o en un video breve enlazado desde el informe. El material debe ser accesible para el equipo docente y no debe exponer secretos, cookies ni endpoints reales de suscripciones Push.

Se evaluará el último commit publicado en la rama `entrega-4` dentro del plazo anunciado. No se requiere crear un pull request. El despliegue en AWS debe estar disponible al cierre del plazo y corresponder a la versión de ese commit.

## Uso de inteligencia artificial generativa

Se permite utilizar asistentes de programación basados en modelos de lenguaje. El grupo debe declarar las herramientas utilizadas y la finalidad de cada uso en su informe.

Independiente de lo anterior, cada integrante debe poder explicar los componentes entregados, la configuración de los servicios, los permisos utilizados y los cambios realizados al código. La utilización de estas herramientas no reemplaza esa responsabilidad ni la verificación del resultado.

## Criterios de evaluación

La entrega se evalúa en cinco dimensiones. Cada dimensión recibe un puntaje entero de 1 a 7.

### 1. Publicación e integración de servicios — 25%

Evalúa la publicación del build React en S3 mediante CloudFront, el acceso HTTPS, el origen único para frontend y API, las rutas de API Gateway y el funcionamiento de las URL de la aplicación. Incluye la correcta distinción entre contenido estático y respuestas autenticadas.

### 2. Adaptación y organización del backend — 25%

Evalúa la incorporación de las extensiones propias respetando la separación provista en cuatro funciones, las dependencias de cada una y la conservación de la autenticación y autorización entre componentes. Considera que el funcionamiento no dependa de un proceso permanente ni de la versión monolítica.

### 3. Persistencia y conservación de información — 20%

Evalúa la adaptación de las tablas y operaciones propias a Aurora DSQL, el almacenamiento de fotografías en S3, el respeto de la visibilidad y la preparación reproducible del esquema. Incluye la conservación de datos y archivos durante las actualizaciones.

### 4. Continuidad funcional, PWA y notificaciones — 15%

Evalúa el funcionamiento de la aplicación de la entrega 3 en el nuevo despliegue, su instalación, consulta offline y actualización. Incluye la administración de nuevas suscripciones, la invocación síncrona del emisor, los destinatarios correctos, el manejo de resultados y la navegación desde una notificación.

### 5. Despliegue reproducible, seguridad y verificación — 15%

Evalúa el uso de la infraestructura provista, la configuración de permisos y secretos, los registros para diagnóstico, las pruebas, las evidencias y la claridad del procedimiento de despliegue, actualización y limpieza. La configuración debe poder reconstruirse a partir del repositorio y de la documentación entregada.

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

La nota grupal es la suma ponderada de los puntajes de las dimensiones, redondeada a un decimal. La escala resultante va de 1,0 a 7,0. Se mantiene la Prueba de Evaluación Teórica del Proyecto individual correspondiente a esta entrega, según las reglas de evaluación de la asignatura.

## Fuera de alcance

Para mantener el foco de la entrega, no se solicita implementar:

* Nuevas épicas ni un rediseño del frontend desarrollado en la entrega 3.
* Migración de datos, fotografías, sesiones o suscripciones desde el despliegue monolítico.
* Dominio propio, administración DNS o certificados personalizados.
* Una Lambda por endpoint, bases de datos independientes por función o una arquitectura de microservicios con comunicación general entre sus componentes.
* Colas de mensajería, invocaciones asíncronas del emisor, procesamiento masivo de notificaciones o garantías de entrega exactamente una vez.
* Escrituras offline, Background Sync, sincronización entre ambos despliegues o resolución de conflictos entre ellos.
* Compatibilidad simultánea con Android e iOS.
