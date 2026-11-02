# Base serverless para la Entrega 4

Esta carpeta contiene la base para desplegar en AWS la aplicación desarrollada hasta la entrega 3. El frontend React se publica como archivos estáticos y el backend se distribuye en cuatro funciones Lambda, con persistencia relacional en Aurora DSQL y almacenamiento de fotografías en S3.

La migración traslada la aplicación monolítica a servicios administrados de AWS orientados a la alta escalabilidad y disponibilidad. La adaptación debe conservar la funcionalidad de la aplicación.

La base conserva las funcionalidades del backend docente y proporciona la infraestructura de despliegue. Se deben incorporar las extensiones propias, la gestión de suscripciones y el código de envío Web Push, junto con el frontend y las capacidades de PWA de las entregas anteriores.

Este README describe la organización de la base, la adaptación del proyecto y su operación en AWS. Los requisitos, las evidencias y los criterios de evaluación se encuentran en el [enunciado de la entrega 4](../docs/entrega4.md).

## Base provista y organización del proyecto

El equipo docente proporciona:

* El backend de dominio adaptado a Lambda y Aurora DSQL, conservando el contrato de las diecisiete épicas de la entrega 3.
* La autenticación y las sesiones compartidas entre las funciones que atienden operaciones protegidas.
* El almacenamiento de fotografías en S3, con control de acceso según su visibilidad.
* La preparación del esquema docente y de los datos de demostración.
* La resolución de destinatarios y la integración que permite solicitar el envío de mensajes Web Push después de guardar una actividad.
* Las plantillas de CloudFormation y los scripts Python para preparar el código y sus bibliotecas, desplegar, publicar el frontend, actualizar la aplicación y eliminar sus recursos.

Se deben adaptar las tablas y endpoints de suscripciones, la configuración VAPID, el código de envío, las demás extensiones propias y el frontend React. La base no sustituye esos componentes por una implementación docente ni exige adoptar un nuevo esquema de suscripciones.

La organización separa ambos despliegues:

* **`backend/`, `gateway/` y los archivos Docker Compose de la raíz:** mantienen la aplicación monolítica.
* **`frontend/`:** contiene la aplicación React del grupo, cuyo build se publica en el nuevo despliegue.
* **`serverless/backend/`:** contiene la adaptación del backend y las extensiones que el grupo traslada a Lambda.
* **`serverless/template.yaml`:** define la infraestructura de CloudFormation.
* **`serverless/scripts/`:** contiene las herramientas de preparación, despliegue, publicación, actualización y eliminación de recursos.

Los puntos de entrada del procedimiento son [scripts/deploy.py](scripts/deploy.py), que administra el despliegue completo, y [scripts/package.py](scripts/package.py), que permite preparar los cuatro ZIP sin conectarse a AWS. La infraestructura se define en [template.yaml](template.yaml).

El despliegue monolítico debe permanecer disponible en paralelo. Su workflow de GitHub Actions continúa publicando esa variante y no debe utilizarse para desplegar la versión serverless en la cuenta AWS del grupo.

La adaptación no requiere trasladar usuarios, sesiones, actividades, fotografías ni suscripciones desde el monolito. El sistema serverless comienza con sus propios datos de demostración y utiliza un origen público diferente. Esta independencia inicial no implica que las actualizaciones posteriores puedan eliminar la información creada en el nuevo sistema.

## Arquitectura

Los servicios cumplen funciones diferentes:

* **Amazon S3:** almacena el build estático del frontend y las fotografías de la aplicación en buckets privados.
* **Amazon CloudFront:** distribuye el frontend mediante HTTPS y dirige las solicitudes de la API a su origen correspondiente.
* **Amazon API Gateway:** recibe las solicitudes HTTP de la API y selecciona la función Lambda según la ruta y el método.
* **AWS Lambda:** ejecuta el código del backend, incluyendo las operaciones de la aplicación y el envío de mensajes Web Push.
* **Amazon Aurora DSQL:** es un servicio de base de datos relacional serverless compatible con PostgreSQL. Permite trabajar con tablas y SQL, mientras AWS administra la infraestructura y ajusta su capacidad según la demanda. En este despliegue almacena usuarios, sesiones, actividades y las tablas de suscripciones del grupo. Su funcionamiento se describe en la [documentación de Aurora DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/what-is-aurora-dsql.html).

Se debe utilizar el dominio asignado por CloudFront. No se requiere un dominio propio, configuración DNS ni un certificado personalizado. Los recursos regionales deben desplegarse en **South America (São Paulo), `sa-east-1`**, con un clúster DSQL de una sola región.

### Frontend y API bajo un mismo origen

CloudFront obtiene el frontend desde S3 mediante Origin Access Control (OAC). No se debe publicar el bucket mediante un website endpoint ni habilitar el acceso público directo a sus objetos.

Las solicitudes de `/api/*` se dirigen a API Gateway. El cliente debe conservar las URLs relativas `/api/v1/...`, de modo que no necesite conocer la dirección directa de API Gateway ni la de las funciones. La configuración reenvía los datos necesarios para la sesión y mantiene deshabilitado el caché para las respuestas de la API.

La navegación de React, la recarga de una ruta interna, el manifest, el service worker y los enlaces de las notificaciones deben funcionar bajo la dirección de CloudFront. La resolución de rutas del frontend no debe reemplazar una respuesta de error de la API por el HTML de la aplicación.

### Cuatro funciones Lambda

El backend monolítico reúne las operaciones de la aplicación y el envío de mensajes Web Push en un mismo despliegue. En esta base, esas responsabilidades se distribuyen en cuatro funciones Lambda.

El código de envío Web Push se ejecuta en una Lambda dedicada. Cuando una operación requiere notificar a otros usuarios, la Lambda que la procesa guarda los cambios y luego invoca a esta otra función con los datos de la actividad y los identificadores de sus destinatarios. Esta consulta las suscripciones activas y envía los mensajes correspondientes. Por esa responsabilidad, se denomina **función emisora de notificaciones**.

Las otras tres funciones atienden solicitudes HTTP mediante API Gateway. La distribución es la siguiente:

| Función | Responsabilidad |
| --- | --- |
| **Cuentas y autenticación** | Registro, inicio y cierre de sesión, operaciones de cuenta y endpoints autenticados de administración de suscripciones Push |
| **Operaciones de dominio** | Restaurantes, actividades, reseñas, evaluaciones, seguimientos, feed y demás operaciones que no corresponden al manejo de archivos |
| **Fotografías** | Recepción, procesamiento y acceso a fotografías persistidas en S3, respetando su visibilidad |
| **Emisor de notificaciones** | Consulta de suscripciones y envío de mensajes Web Push a los destinatarios indicados por el backend |

Las tres funciones que atienden la API conservan FastAPI y utilizan [Mangum](https://mangum.fastapiexpert.com/), una biblioteca Python que adapta su ejecución al modelo de Lambda. API Gateway entrega un evento que describe la solicitud HTTP; Mangum lo transforma para que FastAPI lo procese y convierte la respuesta al formato esperado por API Gateway. Esto permite reutilizar las rutas y validaciones sin mantener un servidor HTTP ejecutándose permanentemente.

Cada función registra solo las rutas que le corresponden. La función emisora no recibe solicitudes HTTP desde API Gateway: las otras Lambdas la invocan directamente. Por ello, utiliza un handler de Python sin FastAPI ni Mangum y no dispone de un endpoint público.

Las funciones pueden compartir módulos de configuración, autenticación, modelos y acceso a datos, así como el mismo esquema DSQL. Cada función debe incluir únicamente el código y las bibliotecas necesarios para cumplir su responsabilidad. La separación no exige crear una Lambda por endpoint ni bases de datos independientes.

Las sesiones se validan utilizando la información persistida y la configuración común de autenticación, no mediante el estado de una función particular. Un usuario debe poder realizar operaciones protegidas en distintas funciones y cerrar sesión de manera consistente.

## Preparación del despliegue

Se debe utilizar **un despliegue por grupo**, en la cuenta AWS de uno de sus integrantes.

El procedimiento debe ejecutarse desde un terminal local con **Python 3.14**. Las funciones Lambda utilizan esa misma versión, con arquitectura **x86_64**. Para generar el build del frontend se requiere Node.js y su gestor de paquetes; el frontend docente requiere Node.js **22.12 o superior** y npm. Se admite npm, pnpm o yarn, conservando el archivo de bloqueo de dependencias correspondiente. El procedimiento no requiere AWS CLI, SAM, Docker ni CloudShell.

CloudFormation define y administra la infraestructura. Los scripts utilizan Boto3, la biblioteca Python para acceder a los servicios de AWS, para cargar el código, ejecutar las operaciones de CloudFormation y publicar los archivos del frontend. La configuración reproducible debe quedar en el repositorio; los secretos y las credenciales deben mantenerse fuera de él.

Cada función se publica mediante un **paquete de despliegue**: un archivo ZIP que contiene su código y las bibliotecas necesarias para ejecutarlo. Las herramientas de preparación reúnen esos archivos según la versión de Python y la arquitectura configuradas para Lambda. No se debe copiar directamente el entorno virtual del computador personal.

### Entorno local y archivo de configuración

Los comandos deben ejecutarse desde la carpeta `serverless` del repositorio del proyecto. Se debe crear y activar un entorno virtual antes de instalar las dependencias.

En Linux o macOS:

```sh
python3.14 -m venv .venv
source .venv/bin/activate
```

En Windows, desde PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea la activación por su política de ejecución, se puede ejecutar `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` y repetir el comando de activación. Este ajuste se aplica únicamente a la sesión actual del terminal.

Con el entorno activo, se deben instalar las dependencias de las herramientas y del mantenimiento local de la base de datos:

```sh
python -m pip install -r requirements.txt
```

Los comandos siguientes presuponen que el entorno virtual está activo. Al abrir otro terminal, se debe volver a la carpeta `serverless` y repetir el comando de activación correspondiente al sistema operativo; no es necesario crear nuevamente el entorno.

Se debe copiar [config.example.json](config.example.json) como `config.local.json` y ajustar los siguientes valores:

| Campo | Configuración |
| --- | --- |
| `deployment_name` | Nombre de 3 a 24 caracteres, con letras minúsculas, números y guiones; debe comenzar con una letra y terminar con letra o número. Debe conservarse en las actualizaciones |
| `region` | `sa-east-1` |
| `expected_account_id` | Identificador de doce dígitos de la cuenta AWS de destino. Puede dejarse vacío únicamente para ejecutar `check` y comprobar la identidad disponible |
| `profile` | Se debe mantener en `null` para utilizar la configuración habitual de Boto3, incluido el perfil `default`. No se requiere un perfil nombrado |
| `frontend_dir` | Ruta del frontend, relativa al archivo de configuración; `../frontend` utiliza el frontend del repositorio |
| `frontend_build_dir` | Subcarpeta generada por el build, normalmente `dist` |
| `package_manager` | `npm`, `pnpm` o `yarn`, según el frontend |
| `frontend_environment` | Variables públicas `VITE_` necesarias para generar el build, por ejemplo la configuración de mapas |
| `service_worker_files` | Rutas de los archivos de entrada del service worker dentro del build. Por omisión incluye `sw.js` y `service-worker.js`; se debe ajustar si la PWA utiliza otro nombre |
| `notifications_enabled` | `false` en el primer despliegue; `true` después de incorporar el emisor |
| `vapid_public_key` y `vapid_subject` | Vacíos en el primer despliegue. Al integrar Web Push, corresponden a la clave pública del grupo y su URI de contacto |

`config.local.json` está excluido de Git. No debe contener claves privadas, secretos de autenticación ni credenciales AWS. Las carpetas `.venv`, `.build` y `.deployment` también están excluidas. El script guarda en `.deployment` los identificadores y salidas del despliegue, no sus secretos.

### Cuenta y credenciales AWS

Las herramientas locales utilizan las credenciales disponibles para el SDK de AWS, mediante su [mecanismo de configuración de credenciales](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html). Estas credenciales corresponden a la identidad que realiza el despliegue, no a la identidad con que se ejecuta la aplicación.

Se debe configurar el acceso de Boto3 mediante un perfil local o variables de entorno. Un perfil reúne las credenciales bajo un nombre en el archivo local de credenciales de AWS y puede seleccionarse mediante `AWS_PROFILE`. Si se utilizan variables de entorno, corresponden a `AWS_ACCESS_KEY_ID` y `AWS_SECRET_ACCESS_KEY`; las credenciales temporales requieren además `AWS_SESSION_TOKEN`. Estos valores no deben incorporarse a archivos versionados ni confundirse con las credenciales de los usuarios de la aplicación.

Antes de modificar recursos, se debe comprobar la cuenta, la región y el nombre del despliegue. No deben utilizarse credenciales de la cuenta root ni incorporarse claves de acceso a los scripts, al repositorio o al frontend.

Para utilizar la configuración por omisión, se deben guardar las credenciales de acceso programático bajo el perfil `default` en el archivo `credentials` del directorio `.aws` del usuario: `~/.aws/credentials` en Linux o macOS, o `%USERPROFILE%\.aws\credentials` en Windows. El archivo debe tener esta estructura, reemplazando los marcadores únicamente en ese archivo local:

```ini
[default]
aws_access_key_id = <identificador de la clave de acceso>
aws_secret_access_key = <clave secreta de acceso>
```

Si las credenciales son temporales, debe agregarse `aws_session_token`. En `config.local.json`, se debe mantener `profile` en `null`. Boto3 utiliza `default` cuando no se ha seleccionado otro perfil ni se han definido credenciales mediante variables de entorno. No se requiere ejecutar `aws configure` ni instalar AWS CLI. La identidad utilizada debe tener permisos para crear los recursos de la plantilla, gestionar sus roles IAM y preparar el esquema DSQL; esos permisos de despliegue no se trasladan a los roles de ejecución de las Lambdas.

Se debe verificar el acceso antes de crear recursos:

```sh
python scripts/deploy.py check
```

Este comando consulta la identidad, muestra la cuenta y la región y no modifica recursos. Si `expected_account_id` estaba vacío, se debe completar con la cuenta verificada antes de continuar. El script rechaza credenciales root o una cuenta diferente de la indicada.

Cada función utiliza un rol de ejecución con permisos acotados. Las credenciales del computador que despliega no se copian a las Lambdas. El permiso para invocar al emisor se limita a las funciones que producen actividades y necesitan solicitar un envío.

### Configuración de la aplicación

La configuración debe distinguir los siguientes elementos:

* **Identificación del despliegue:** cuenta de destino, región y nombre que identifica sus recursos.
* **Autenticación:** secreto de la aplicación y configuración de sesión compartida entre las funciones HTTP. Las cookies deben conservar los atributos `HttpOnly` y `Secure`.
* **Persistencia:** acceso al clúster DSQL y ubicación de las fotografías en S3.
* **Web Push:** clave pública VAPID disponible para el cliente, clave privada configurada exclusivamente en el emisor y datos de contacto utilizados por la biblioteca de envío.
* **Servicios del frontend:** configuración de mapas y de los demás servicios externos utilizados por el grupo, con restricciones que admitan el nuevo origen.
* **Datos de demostración:** contenido y cuentas de prueba suficientes para revisar la aplicación, sin reutilizar contraseñas personales.

Los secretos de autenticación y las claves VAPID deben conservarse entre actualizaciones. No deben generarse nuevamente cada vez que una función comienza a ejecutarse o se publica una versión.

Los valores públicos que necesita el cliente pueden formar parte del build. Esto incluye la clave pública VAPID y la clave de mapas restringida al origen; no incluye la clave privada VAPID, credenciales AWS ni secretos de autenticación.

### Primer despliegue de la base docente

Antes de adaptar la aplicación, se debe desplegar y comprobar la base provista sin modificar su código ni incorporar componentes propios. Solo se debe ajustar la configuración necesaria para utilizar la cuenta AWS elegida.

Se debe ejecutar:

```sh
python scripts/deploy.py deploy
```

El script ejecuta la preparación y publicación completas. Primero genera el build del frontend y los ZIP de las cuatro funciones. Luego crea un bucket privado para almacenar esos ZIP, separado de los buckets de frontend y fotografías, y ejecuta la plantilla de CloudFormation. Finalmente prepara el esquema y los datos docentes, publica el frontend e invalida el caché de CloudFront. No es necesario ejecutar manualmente cada etapa de la siguiente lista.

El procedimiento comprende las siguientes etapas:

1. Obtener una copia de la base docente, preparar las dependencias locales y configurar el acceso a AWS.
2. Comprobar la identidad utilizada, la cuenta, la región y el nombre del despliegue.
3. Preparar los paquetes de despliegue de las funciones provistas y los archivos estáticos de la base.
4. Crear la infraestructura mediante CloudFormation y publicar el código y los archivos correspondientes.
5. Preparar el esquema docente y sus datos de demostración mediante las herramientas provistas.
6. Comprobar el acceso HTTPS desde CloudFront y verificar los endpoints provistos de autenticación, consulta y escritura de contenido, junto con la persistencia y el acceso autorizado a fotografías.

Al terminar, la base debe funcionar en la cuenta del grupo y deben poder identificarse la dirección de CloudFront y los recursos creados. La comprobación del backend puede realizarse mediante sus endpoints; no requiere integrar todavía la interfaz React del grupo.

La salida final indica la URL HTTPS de la aplicación. Se debe abrir esa dirección y consultar `/api/healthz` bajo el mismo origen; la respuesta debe indicar `status: ok`. El acceso a la API y las operaciones de dominio se describen en el [contrato de la API](../backend/docs/api.md). La preparación de datos utiliza las cuentas y el contenido definidos en [backend/app/db/fixtures.py](backend/app/db/fixtures.py).

Los identificadores de los recursos y el estado de CloudFormation pueden consultarse mediante:

```sh
python scripts/deploy.py status
```

`deploy` rechaza un stack existente para evitar reemplazarlo accidentalmente. Las publicaciones posteriores deben utilizar `update`. La creación de la distribución y la preparación inicial de los índices de DSQL pueden tardar varios minutos; el script informa el avance de los índices. Si ocurre un error o se agota la espera, se debe revisar el estado en la consola antes de reintentar. El script no elimina automáticamente una infraestructura que haya quedado parcialmente creada.

En esta etapa no se deben incorporar las tablas de suscripciones, las claves VAPID, el código de envío Web Push ni las capacidades de PWA desarrolladas por el grupo. No se envían notificaciones, y esa ausencia no debe impedir las operaciones de dominio. Las pruebas de instalación, consulta offline y recepción de mensajes corresponden a la etapa posterior.

## Adaptación del proyecto

Una vez comprobada, la base debe incorporarse al repositorio del proyecto siguiendo el procedimiento del [enunciado general](../README.md#uso-del-repositorio). Luego se deben identificar las extensiones propias y trasladarlas a la estructura serverless.

### Identificación de las contribuciones propias

Antes de trasladar archivos, se debe identificar qué se agregó o modificó sobre el backend docente. La revisión debe incluir las tablas de suscripciones, sus endpoints, el emisor, la configuración, las dependencias y cualquier otra extensión desarrollada.

La adaptación debe realizarse en `serverless/backend/`. Se debe conservar el backend monolítico; reemplazar sus archivos por la variante serverless puede afectar el despliegue que debe seguir funcionando en paralelo.

El contrato funcional de referencia es el de la entrega 3, descrito en el [contrato de la API por épica](../backend/docs/api.md). La migración no vuelve a la versión reducida de la prueba de concepto de la entrega 2.

Los componentes propios deben incorporarse de la siguiente manera:

| Componente | Lugar de integración |
| --- | --- |
| Tablas y acceso a datos | Módulos de persistencia de `serverless/backend/` y procedimiento de preparación o actualización del esquema |
| Endpoints de suscripciones | Aplicación FastAPI de cuentas y autenticación, con sus rutas correspondientes en API Gateway |
| Otras extensiones de la API | Aplicación FastAPI de dominio o de fotografías, según su responsabilidad |
| Código de envío Web Push | Handler de la función emisora, reutilizando las tablas de suscripciones del grupo |
| Bibliotecas adicionales | Declaración de dependencias de cada función que las utilice |
| Interfaz y capacidades de PWA | Frontend del grupo, publicado desde su build de producción |

Los archivos concretos que se deben revisar son:

* **[backend/accounts.py](backend/accounts.py), [backend/domain.py](backend/domain.py) y [backend/photos.py](backend/photos.py):** registran los routers de cada aplicación FastAPI.
* **[backend/app/extensions.py](backend/app/extensions.py):** proporciona `register_tables(metadata)` para agregar los modelos propios y `migrate_schema(engine)` para ejecutar cambios explícitos e idempotentes del esquema durante el mantenimiento local.
* **[backend/notifications.py](backend/notifications.py):** contiene el handler que se debe completar con el código de envío del grupo. Inicialmente no realiza envíos.
* **`backend/manifests/`:** contiene un JSON por función, con su handler, archivos y archivo de dependencias. Los archivos propios deben agregarse al manifiesto de cada función que los necesite.
* **`backend/requirements/`:** contiene las bibliotecas de cada función y las del mantenimiento local. Se deben agregar aquí las dependencias propias, no en el backend monolítico.
* **[template.yaml](template.yaml):** contiene las rutas de API Gateway y la configuración de recursos, permisos y variables de las funciones.

### Tablas y operaciones de persistencia

Las tablas y consultas del grupo deben adaptarse a Aurora DSQL. La compatibilidad con PostgreSQL facilita la migración, aunque pueden ser necesarios ajustes en las tablas, consultas y transacciones. Las diferencias se consultan en la [documentación de compatibilidad de DSQL](https://docs.aws.amazon.com/aurora-dsql/latest/userguide/working-with-postgresql-compatibility.html).

La preparación del esquema y de los datos iniciales debe realizarse como una operación explícita del despliegue. No se deben crear tablas ni volver a cargar datos de demostración durante la inicialización de cada Lambda o en cada solicitud.

Las operaciones propias deben utilizar el soporte de transacciones y reintentos de la base cuando corresponda. El envío de una notificación debe quedar fuera de la transacción que guarda la actividad, para que un reintento de la escritura no repita también los envíos.

Las fotografías se conservan en S3 y sus metadatos en DSQL. Los archivos temporales de una función no son almacenamiento permanente. La adaptación debe conservar la autorización sobre las fotografías privadas y no hacer público el bucket para resolver su visualización.

El límite de recepción está configurado en **4.000.000 bytes por fotografía**, para dejar espacio al contenido multipart y a su codificación en el evento enviado a Lambda. No se debe aumentar este valor sin revisar los límites de la integración HTTP.

### Rutas, dependencias e inicialización

Se deben registrar los endpoints propios en la aplicación FastAPI de la función correspondiente y ajustar las rutas de API Gateway en `serverless/template.yaml`. Los de suscripciones corresponden a cuentas y autenticación; las extensiones de dominio y de fotografías deben mantener la separación de responsabilidades indicada anteriormente.

Los nombres y métodos de los endpoints de suscripciones pueden conservarse. Su integración con API Gateway debe respetar ese contrato, incluyendo las rutas anidadas, para que el frontend continúe utilizando la API de su grupo.

Se deben declarar las dependencias adicionales en cada función que las necesite. Las bibliotecas de procesamiento de imágenes o de emisión Web Push no deben cargarse desde funciones que no las utilizan. También deben revisarse las importaciones indirectas: un módulo compartido puede terminar incorporando dependencias de otra responsabilidad.

Las bibliotecas incluidas en los paquetes de despliegue deben ser compatibles con Linux, con la arquitectura de la función y con su versión de Python. Las bibliotecas que contienen componentes compilados requieren distribuciones para ese entorno, aunque los scripts se ejecuten desde Windows o macOS. Se deben utilizar las herramientas de preparación provistas y comprobar que las dependencias adicionales dispongan de una distribución compatible. No se debe resolver esta preparación copiando bibliotecas instaladas para el sistema operativo del computador local. La [documentación de AWS sobre dependencias nativas](https://docs.aws.amazon.com/lambda/latest/dg/python-package.html#python-package-native-libraries) describe esta distinción.

La inicialización registra los componentes necesarios para atender una invocación. No debe depender de que otra función haya ejecutado previamente un paso, ni de que el proceso que atendió una solicitud anterior siga disponible.

### Integración del emisor Web Push

La base determina los destinatarios y proporciona la invocación interna. Se debe adaptar el código de envío al handler de la función emisora, para consultar las suscripciones de esos usuarios y enviar los mensajes. No se debe volver a implementar la consulta de seguidores ni construir otro mecanismo para invocar a la Lambda.

La información recibida identifica el tipo y el identificador de la actividad, su autor, el restaurante y los identificadores de los destinatarios. Estos últimos son usuarios, no endpoints Push: el emisor debe relacionarlos con las suscripciones que administra el grupo. La base determina esos usuarios sin repeticiones y excluye al autor de la actividad.

El contrato está definido en [backend/app/notification_event.py](backend/app/notification_event.py). El evento contiene `type`, `id`, `author_id`, `restaurant_id` y `recipients`; los identificadores son UUID serializados como texto y `recipients` es una lista. El handler debe devolver un objeto JSON con `status: "ok"` cuando haya terminado los intentos de envío, aunque alguna suscripción haya fallado y ese error se haya tratado individualmente. Puede agregar cantidades de envíos aceptados o fallidos, pero no claves ni suscripciones completas. Este resultado no confirma la recepción en el dispositivo.

Después de implementar el emisor y los endpoints de suscripciones, se debe configurar `notifications_enabled` en `true`, completar `vapid_public_key` y `vapid_subject`, y proporcionar la clave privada mediante la variable de entorno local `VAPID_PRIVATE_KEY`. No se debe escribir esa clave en `config.local.json`, el código ni el frontend. La clave pública está disponible en la función de cuentas mediante `VAPID_PUBLIC_KEY` y, durante el build, mediante `VITE_VAPID_PUBLIC_KEY`; el frontend puede utilizar la alternativa que corresponda a su implementación.

El script incorpora las claves al habilitar Web Push por primera vez. Después las conserva mediante los parámetros existentes de CloudFormation; no es necesario volver a proporcionar la clave privada en cada actualización. Un cambio de clave pública se rechaza para evitar invalidar las suscripciones por una rotación accidental. Activar la opción sin completar el handler no implementa el envío: el código provisto devuelve `not_implemented` y registra esa condición.

El flujo es el siguiente:

1. La función que procesa una actividad confirma su escritura en DSQL.
2. El punto de integración determina los destinatarios e invoca de manera síncrona al emisor, con los datos de la actividad y los identificadores de los usuarios que deben recibir el aviso.
3. El emisor obtiene las suscripciones activas, realiza los envíos y devuelve su resultado, sin incluir claves ni suscripciones completas.
4. El emisor retorna y la función que lo invocó completa la respuesta de la operación original.

La [invocación síncrona de Lambda](https://docs.aws.amazon.com/lambda/latest/dg/invocation-sync.html) espera a que termine la función invocada. En esta aplicación se espera que el emisor complete sus solicitudes a los servicios push, no que el dispositivo reciba o muestre la notificación.

La base registra el punto de integración en cada función que produce actividades notificables, incluyendo las publicaciones de fotografías. Se debe adaptar el código de envío en la función emisora; no se debe registrarlo ni copiarlo en cada función que produce actividades.

Se mantienen las reglas de la entrega 3: una actividad pública notifica a quienes siguen a su autor o al restaurante, excluyendo al autor; una actividad privada no produce avisos. La coincidencia de ambos seguimientos no duplica una notificación por instalación. Varias fotografías publicadas como una sola actividad producen un aviso, y reseñar una fotografía ya publicada no genera un segundo aviso por esa entrada del feed.

Los errores deben tratarse por suscripción para permitir los restantes envíos. Los endpoints que el servicio push informa como expirados o permanentemente inválidos deben eliminarse o desactivarse. Los errores controlados de invocación o envío deben registrarse sin revertir una actividad ya guardada.

El emisor debe completar su trabajo antes de retornar. No debe dejar envíos en tareas de fondo que dependan de continuar ejecutándose después de su respuesta. No se utilizan colas ni invocaciones asíncronas.

La espera del emisor aumenta el tiempo de la solicitud original. Además, guardar una actividad e invocar a otra función son operaciones diferentes: si la segunda falla, la actividad puede quedar guardada sin que se envíe su aviso. Esta base no constituye un sistema de distribución masiva ni garantiza la entrega de notificaciones.

### Frontend y nueva instalación de la PWA

Se debe conservar el frontend React y publicarlo desde su build de producción. Sus llamadas deben continuar utilizando rutas relativas, sin referencias a `localhost`, al monolito ni a la dirección directa de API Gateway.

El nuevo dominio corresponde a un origen diferente. Se debe instalar la PWA desde CloudFront y crear nuevas suscripciones mediante la acción explícita de la interfaz. No se deben copiar las suscripciones anteriores ni el almacenamiento local del navegador.

Los enlaces de las notificaciones deben abrir la actividad correspondiente en este despliegue. Las restricciones de los servicios de mapas deben incluir el nuevo origen sin eliminar el acceso que necesita la versión monolítica.

La adaptación debe conservar la instalación, las actualizaciones del service worker, la consulta offline del contenido persistido y su separación por usuario. Estas capacidades deben verificarse desde la PWA instalada en la plataforma utilizada.

## Actualización y verificación de la aplicación

La incorporación de los componentes propios debe publicarse como una actualización de la base ya comprobada. No requiere crear otro despliegue ni eliminar los datos existentes.

Se debe ejecutar:

```sh
python scripts/deploy.py update
```

El script vuelve a preparar el código y el frontend, propone un cambio en CloudFormation y verifica que no elimine ni reemplace los buckets, el clúster DSQL o la distribución de CloudFront. También ejecuta el mantenimiento del esquema, pero no vuelve a cargar los datos docentes. El secreto de autenticación se conserva mediante el parámetro existente de CloudFormation.

Para publicar la integración, se debe:

1. Incorporar las extensiones propias, configurar las claves VAPID y revisar las dependencias y rutas de cada función.
2. Preparar los paquetes de despliegue de las funciones y el build de producción del frontend.
3. Actualizar la infraestructura y publicar el código mediante las herramientas provistas, aplicando los cambios necesarios al esquema sin reinicializarlo.
4. Preparar el contenido de demostración adicional que requieran las pruebas, sin sobrescribir los registros existentes.
5. Comprobar las operaciones de la aplicación, instalar la PWA desde CloudFront y crear nuevas suscripciones mediante la acción explícita de la interfaz.
6. Verificar las notificaciones con dos usuarios distintos y comprobar la navegación al seleccionar el aviso.

### Conservación entre actualizaciones

En las actualizaciones posteriores se deben preparar y publicar las nuevas versiones del código y aplicar los cambios necesarios al esquema, sin eliminar ni volver a crear el sistema. No se debe exigir reinstalar la PWA ni crear nuevamente las suscripciones. Se deben conservar:

* La distribución de CloudFront y su dirección pública.
* Los usuarios, sesiones, actividades y suscripciones almacenados en DSQL.
* Las fotografías almacenadas en S3.
* Los secretos de autenticación y las claves VAPID.

Si se modifica el esquema, el cambio debe aplicarse mediante el procedimiento de actualización correspondiente, sin reinicializar los datos. La publicación de nuevos archivos del frontend debe mantener coherentes el build, el service worker y su estrategia de actualización.

La publicación carga primero los recursos del build, luego `index.html` y finalmente los archivos de entrada del service worker declarados en `service_worker_files`. No elimina los recursos antiguos que una instalación todavía puede necesitar. Este orden no sustituye la gestión de versiones y actualización del service worker desarrollada en la PWA.

### Verificación después de la integración

Una vez incorporados los componentes propios, se debe comprobar:

1. El acceso HTTPS mediante CloudFront y el carácter privado de los buckets.
2. El recorrido de las solicitudes de la API hacia las funciones correspondientes, sin depender del monolito.
3. El inicio y cierre de sesión, y el uso de operaciones protegidas en las distintas funciones.
4. La persistencia de datos en DSQL y de fotografías en S3, con respeto de la visibilidad.
5. La apertura y recarga de rutas internas, la instalación de la PWA y la consulta offline.
6. La recepción de una notificación dirigida con la PWA receptora cerrada y la navegación al seleccionar el aviso.
7. La conservación de datos, archivos, suscripciones y dirección pública después de actualizar.

La verificación académica completa y sus evidencias se especifican en el [enunciado de la entrega 4](../docs/entrega4.md#verificación-mínima).

## Diagnóstico

Si la creación de infraestructura finalizó, pero falló la preparación de datos, se puede repetir únicamente esa operación:

```sh
python scripts/deploy.py database --seed
```

`--seed` inserta únicamente los datos docentes que falten, sin sobrescribir los existentes. Para aplicar solo la preparación y los cambios explícitos del esquema, se debe omitir esa opción. Después de resolver el error, `update` permite completar la publicación. No se debe eliminar y recrear el despliegue para resolver un error de datos o de código.

Para comprobar únicamente el empaquetado, sin modificar recursos AWS:

```sh
python scripts/package.py
```

Los cuatro ZIP quedan en `.build/packages/`. Si falta una biblioteca compatible con Linux y Python 3.14 o un archivo del manifiesto, la preparación se detiene antes de publicar una versión parcial.

Para diagnosticar un error, se debe identificar primero en qué componente ocurre:

* **CloudFormation:** creación o actualización de recursos, parámetros y permisos de despliegue. Sus eventos permiten localizar el recurso cuya operación falló.
* **CloudFront y API Gateway:** publicación del frontend, selección de origen, rutas, métodos HTTP y datos reenviados al backend.
* **Funciones Lambda:** errores de ejecución, configuración o dependencias. Los registros de CloudWatch permiten revisar la función que atendió la operación.
* **Aurora DSQL y S3:** permisos de acceso, preparación del esquema, consultas y disponibilidad de los archivos.
* **Emisor y cliente receptor:** suscripciones, resultados de envío, recepción del evento push y apertura de la vista desde la notificación.

Los registros no deben incluir contraseñas, cookies de sesión, claves privadas VAPID ni suscripciones completas. Deben permitir diagnosticar las operaciones sin exponer la información necesaria para autenticar o enviar mensajes a una instalación.

## Costos y eliminación

Los servicios pueden generar cobros. Se debe revisar el consumo y la cobertura de la cuenta desde la preparación del primer despliegue, sin asumir que su uso será gratuito. Cerrar la consola no detiene la aplicación ni elimina sus recursos.

La eliminación es una operación distinta de actualizar. Antes de ejecutarla, se debe comprobar la cuenta, la región y el nombre del despliegue, y considerar la pérdida de sus datos y archivos. Se deben utilizar las herramientas de eliminación provistas, sin afectar la aplicación monolítica ni recursos ajenos a la entrega.

Se deben eliminar los despliegues de prueba cuando dejen de utilizarse. El presentado para evaluación debe mantenerse disponible hasta que el equipo docente comunique el cierre de la revisión. Después de la limpieza se debe comprobar qué recursos fueron eliminados y si permanece alguno que pueda generar cobros.

Para eliminar el despliegue, se debe ejecutar:

```sh
python scripts/deploy.py delete
```

El script solicita escribir `numero-de-cuenta/nombre-del-despliegue` como confirmación. Después vacía los buckets de la pila, elimina los recursos mediante CloudFormation y retira el bucket de archivos ZIP. La eliminación incluye los datos y fotografías y no puede deshacerse mediante estos scripts. Si una operación falla, se debe revisar `status` y los eventos de CloudFormation antes de reintentar; no se deben borrar recursos de otras aplicaciones para completar la limpieza.
