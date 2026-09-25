# Backend: instalación y ejecución local

Este README explica cómo ejecutar, probar y conectar el backend. Los comandos
comunes son los mismos en todas las plataformas; solo la instalación de las
herramientas, la red y el almacén de certificados cambian entre sistemas
operativos. Para entender la estructura del código o implementar funcionalidad,
continúa con la [guía de desarrollo y arquitectura](DEVELOPER.md).

Si es tu primera vez en el proyecto, sigue este orden:

1. prepara el computador con la guía de tu plataforma;
2. levanta la API con la sección [Inicio rápido](#inicio-rápido);
3. ejecuta las [pruebas](#pruebas); y
4. si usarás HTTPS o un teléfono, continúa con
   [HTTPS en la red local](#https-local-y-acceso-desde-un-teléfono).

Guías para preparar el computador:

- [Linux](docs/platforms/linux.md)
- [macOS](docs/platforms/macos.md)
- [Windows y WSL](docs/platforms/windows.md)

Guías para instalar la autoridad certificadora local en un dispositivo móvil:

- [Android](docs/platforms/android.md)
- [iOS y iPadOS](docs/platforms/ios.md)

Guía para confiar la CA en un navegador del computador:

- [Google Chrome y Mozilla Firefox](docs/platforms/browsers.md)

Los comandos comunes se ejecutan desde la raíz del repositorio. El entorno usa
[Docker Compose](https://docs.docker.com/compose/) para describir y ejecutar
cuatro servicios: [PostgreSQL](https://www.postgresql.org/docs/17/) en `db`, la
API en `backend`, Vite en `frontend` y nginx en `gateway`. Compose también crea
la red privada que los conecta y los volúmenes de desarrollo.

Antes de comenzar, comprueba que Docker y Compose estén disponibles:

```console
docker version
docker compose version
```

## Inicio rápido

```console
docker compose up --build
```

La primera ejecución puede tardar porque Compose debe descargar o construir las
imágenes. Cuando los servicios estén listos, abre el frontend a través del
gateway en <http://localhost:5173>. nginx sirve la aplicación desde Vite y
envía los paths `/api/*`, `/healthz` y `/docs` a FastAPI.

La API también queda expuesta directamente en <http://localhost:8000> para
diagnóstico. La interfaz interactiva de
[OpenAPI](https://spec.openapis.org/oas/latest.html), generada por
[FastAPI](https://fastapi.tiangolo.com/features/#automatic-docs), se puede abrir
mediante el gateway en <http://localhost:5173/docs>.

El contenedor aplica las migraciones y, solo en la configuración de Docker
Compose de desarrollo, carga datos docentes si no existen: dos usuarios, ocho
estilos de comida y diez restaurantes ficticios de Santiago. Sirven para
explorar el API sin tener que ingresar datos manualmente; no representan
locales comerciales reales.

| Correo | Contraseña | Handle | Uso sugerido |
| --- | --- | --- | --- |
| `demo@example.com` | `demo-password` | `demo` | Emisor o receptor de prueba |
| `demo2@example.com` | `demo-password` | `demo2` | Emisor o receptor de prueba |

El handle se almacena sin arroba y en minúsculas. La arroba es presentación y
la agrega la interfaz cuando muestra `@demo`.

Estas credenciales son exclusivamente locales y docentes; no son secretos y no
deben reutilizarse en despliegues reales. Para probar notificaciones, inicia
sesión con cada cuenta en un perfil, navegador o dispositivo independiente y
habilita las notificaciones en cada instalación manualmente.

El backend ofrece el ciclo de sesión completo:

| Método y path | Resultado |
| --- | --- |
| `POST /api/v1/auth/register` | Crea la cuenta, persiste su sesión y entrega la cookie. |
| `POST /api/v1/auth/login` | Valida credenciales, persiste una sesión y entrega la cookie. |
| `GET /api/v1/auth/session` | Devuelve la identidad y caducación de la sesión vigente. |
| `POST /api/v1/auth/logout` | Revoca la sesión actual y elimina la cookie. |

La cookie `session` contiene un JWT firmado y usa `HttpOnly`, por lo que el
frontend no puede ni debe leerla. El navegador la envía con `credentials:
"include"`. Login y logout devuelven `204 No Content`; una consulta sin sesión,
con un token vencido o con una sesión revocada devuelve `401`.

### Registro de una cuenta

`POST /api/v1/auth/register` es la única ruta de escritura que no requiere
sesión, aunque sí valida el origen como el resto. Recibe `name`, `email`,
`handle`, `nationality` y `password`, responde `201` con el mismo cuerpo que
`GET /api/v1/auth/session` y emite la cookie: quien se registra queda
autenticado en la misma operación, sin un segundo viaje que obligue al cliente
a conservar la contraseña.

El servidor normaliza antes de escribir. El handle pierde una arroba inicial y
pasa a minúsculas, de modo que `@Demo`, `demo` y `DEMO` son el mismo handle, y
después tiene que calzar con `^[a-z0-9_]{3,30}$`. El correo pasa a minúsculas.
La nacionalidad es un código ISO 3166-1 alfa-2 y se guarda en mayúsculas.

Un correo o un handle ya tomados responden `409` con el campo en conflicto, de
modo que el formulario pueda marcarlo:

```json
{ "detail": { "field": "handle", "message": "Handle already taken" } }
```

Un formato inválido, una contraseña de menos de doce caracteres o un código de
país desconocido responden `422`. No existe un endpoint que informe si un
handle está disponible: sería público, porque el registro lo es, y permitiría
enumerar los handles de la aplicación sin tener cuenta. El `409` entrega la
misma información en el momento en que hace falta.

`GET /api/v1/countries` publica el catálogo de nacionalidades —código alfa-2 y
nombre en español, ordenado por nombre— para que el formulario construya su
selector sin datos escritos a mano. Es público y cacheable, porque el registro
lo necesita antes de que exista una sesión.

### API de restaurantes

Todas las rutas de restaurantes requieren esa sesión:

| Método y path | Resultado |
| --- | --- |
| `GET /api/v1/restaurants?q=cocina&limit=20` | Busca por nombre y pagina por cursor. |
| `GET /api/v1/restaurants/map?south=…&west=…&north=…&east=…` | Restaurantes dentro del rectángulo visible del mapa. |
| `GET /api/v1/restaurants/nearby?latitude=…&longitude=…&radius=…` | Restaurantes cercanos, ordenados por distancia. |
| `GET /api/v1/cuisine-styles` | Catálogo de estilos de comida para el formulario de creación. |
| `POST /api/v1/restaurants` | Crea un restaurante; responde `201` y publica `Location`. |
| `GET /api/v1/restaurants/{id}` | Ficha del restaurante, tal como la sesión puede verla. |
| `GET /api/v1/restaurants/{id}/photos` | Galería del restaurante, paginada por cursor. |
| `PUT /api/v1/restaurants/{id}/follow` | Sigue el restaurante. |
| `DELETE /api/v1/restaurants/{id}/follow` | Deja de seguirlo. |
| `PATCH /api/v1/restaurants/{id}` | Modifica únicamente los campos presentes. |
| `DELETE /api/v1/restaurants/{id}` | Elimina el recurso y responde `204`. |

La colección responde `{ items, next_cursor }` y se recorre por cursor
opaco, no por `offset`: mientras alguien recorre la lista, otras personas
crean restaurantes, y un desplazamiento numérico repite y salta filas. Cuando
`next_cursor` es `null`, no hay más páginas. `limit` tiene el valor
predeterminado 20 y acepta de 1 a 100.

Cada item es el **resumen de restaurante** que comparten esta colección, el
mapa y la búsqueda por cercanía: `id`, `name`, `address`, `latitude`,
`longitude` y `cuisine_styles`. La ficha de un restaurante agrega `created_at`
y `updated_at`.

`q` acota la colección a un término contenido en el nombre, ignorando
mayúsculas y acentos: `cafe` encuentra «Café Ñielol». El orden es alfabético
sobre esa misma forma y no por relevancia, porque un cursor tiene que
reanudar desde una posición estable. Un término de menos de dos caracteres
responde `422` en vez de devolver la colección completa, y un cursor que esta
API no emitió responde `422` también.

`GET /api/v1/cuisine-styles` entrega el catálogo completo con `id`, `slug` y
nombre visible, para que el formulario de creación construya su selector sin
slugs escritos a mano.

#### Ficha del restaurante

`GET /api/v1/restaurants/{id}` es la pantalla donde converge el resto de la
aplicación. Conserva los campos que ya devolvía y agrega cuatro bloques que
**dependen de quién pregunta**:

* `counters`: fotografías, reseñas, evaluaciones, visitas y seguidores. Cada
  contador informa sólo lo que ese observador podría además listar; uno que
  incluyera actividad privada ajena delataría su existencia sin mostrarla. Los
  de visitas y evaluaciones informan cero hasta que existan sus tablas.
* `ratings`: el resumen de evaluaciones, con el promedio por criterio y el
  total. Viene vacío por ahora, y su forma está fijada para que el cliente que
  lo lea hoy siga funcionando cuando lleguen los números.
* `viewer`: si el observador sigue al restaurante, para que la interfaz decida
  entre «Seguir» y «Siguiendo» sin una segunda solicitud.
* `known_visitors`: quiénes, de las personas que el observador sigue,
  estuvieron ahí y cuándo.

##### Personas conocidas que estuvieron ahí

`known_visitors` responde `{ total, items }`. Cada item es el mismo **resumen
de persona** que devuelven un perfil y la búsqueda —`id`, `handle`, `name` y
`nationality`— más `last_visit_at`, la fecha de su visita pública más
reciente a ese restaurante.

Cuenta **personas, no visitas**: quien fue diez veces aparece una sola vez,
con la última. De otro modo una sola persona llenaría el bloque entero.

Sólo entran **visitas públicas**, y ni siquiera para su autor: el bloque habla
de lo que alguien eligió dar a conocer. Tampoco entran las visitas del propio
observador —nadie se sigue a sí mismo— ni las de quienes no sigue, aunque sean
públicas y en ese mismo restaurante.

**No se pagina.** El orden es por `last_visit_at` descendente y la lista se
corta en diez; `total` cuenta a todas las personas, de modo que una lista
cortada igual dice cuántas hay y la interfaz escribe «y N más». Lo que la
épica pide es saber si alguien conocido estuvo, no auditar quiénes.

Para un observador que no sigue a nadie que haya estado ahí, `total` es cero y
`items` viene vacío: es un estado del bloque y no su ausencia.

Va dentro de la ficha y no en un endpoint aparte porque está acotado de
antemano: su costo no crece con el historial del restaurante ni con el número
de personas que el observador sigue. Es la diferencia con la galería.

**La galería no está en la ficha.** Crece sin límite con la actividad del
restaurante, y la pantalla la recorre por separado con
`GET /api/v1/restaurants/{id}/photos`, que responde `{ items, next_cursor }`
en orden cronológico descendente. Incluye las fotografías públicas y, además,
las privadas del propio observador. Cada item trae su autor, el tipo de
fotografía, la fecha, `content_url` y el identificador de la reseña asociada
cuando la tiene. El parámetro `kind` la acota a platos, menús o instalaciones,
que son tres recorridos distintos sobre la misma galería; un tipo desconocido
responde `422`.

La visibilidad de una fotografía es suya y no se deduce de la reseña que la
acompañe: `GET /api/v1/photos/{id}/content` autoriza contra ella, de modo que
la galería y el contenido concuerdan siempre.

#### Seguir un restaurante

Con la misma forma que seguir a una persona: `PUT` y `DELETE` sobre un
subrecurso, idempotentes, `204` sin cuerpo. La interfaz escribe un botón y no
dos. Seguir un restaurante no notifica a nadie, y el estado aparece en la
ficha bajo `viewer`.

Lo que sí hace es cambiar de qué se entera esa persona: la actividad pública
publicada en ese restaurante pasa a producirle una notificación.

#### Restaurantes del mapa

`GET /api/v1/restaurants/map` responde qué hay dentro del rectángulo que el
mapa informa: `south`, `west`, `north` y `east` en grados decimales, los
cuatro obligatorios. Devuelve `{ items, truncated }` con el mismo resumen de
restaurante de la colección.

**No se pagina.** Un rectángulo es una consulta de mapa, no una lista que se
recorre: si el resultado no cabe, la respuesta es acercar. `truncated` indica
que el rectángulo contenía más restaurantes de los que se devolvieron, y la
interfaz debe pedir un acercamiento en lugar de dibujar un mapa incompleto
como si estuviera completo. Lo que se devuelve en ese caso es la parte sur del
rectángulo y no una muestra representativa; por eso el aviso existe.

Un rectángulo cuya arista oeste queda al este de la arista este cruza el
antimeridiano, y se maneja como dos rangos de longitud. Un rectángulo
invertido en latitud, una coordenada fuera de rango o un área mayor que cien
grados cuadrados responden `422`; el último con un mensaje que la interfaz
puede traducir a «acerca el mapa». Un rectángulo válido sin restaurantes
responde `200` con `items` vacío, que es distinto de un error.

La cuota de Google Maps es acotada y esta consulta es barata pero no gratis:
**la interfaz no debe solicitarla en cada movimiento del mapa**. Conviene
esperar a que el desplazamiento termine y omitir la solicitud cuando el
rectángulo nuevo está contenido en el que ya se consultó.

#### Restaurantes cercanos

`GET /api/v1/restaurants/nearby` responde qué hay a menos de cierta distancia
de una posición. Recibe `latitude`, `longitude` y `radius` en metros, los tres
obligatorios, y `cuisine_style` opcional y repetible: un restaurante califica
si tiene al menos uno de los estilos indicados. Sin ese parámetro devuelve
todos los cercanos, porque el selector de la pantalla se puede limpiar.

Devuelve `{ items, truncated }` ordenado por distancia ascendente, con el
mismo resumen de restaurante y `distance_m` como único campo agregado. **La
distancia la mide el servidor**, con la fórmula de Haversine sobre un radio
terrestre medio de 6 371 008,8 m, y se publica redondeada a metros: más
precisión sugeriría una exactitud que la posición del navegador no tiene. Que
el cliente la recalcule invita a mostrar un número distinto del que se usó
para ordenar.

Tampoco se pagina, por la misma razón que el mapa y una propia: el orden es
una distancia calculada, que no está indexada, y un cursor sobre ella
obligaría a recalcularla en cada página. Si el resultado no cabe, la respuesta
es reducir el radio o afinar el estilo.

El radio máximo son cincuenta kilómetros. Una consulta de cercanía de mil
kilómetros no es una consulta de cercanía: es la colección completa, que ya
tiene su endpoint. Un radio no positivo o mayor que el máximo, una coordenada
fuera de rango o un slug de estilo desconocido responden `422`; un círculo
válido sin restaurantes responde `200` con `items` vacío.

La misma advertencia del mapa vale aquí: **no conviene solicitar en cada
pulsación del selector de estilo ni en cada arrastre del control de
distancia**. Y como el enunciado exige que la aplicación siga siendo utilizable
cuando se deniega el permiso de geolocalización, esta consulta no puede ser el
único camino hacia un restaurante: la búsqueda por nombre y la exploración
libre del mapa tienen que seguir estando.

Al crear o editar, `cuisine_styles` recibe uno o más slugs existentes. Los datos
iniciales ofrecen `chilena`, `peruana`, `italiana`, `japonesa`, `india`,
`vegana`, `cafeteria` y `sandwicheria`. La respuesta expande cada slug a un
objeto con `id`, `slug` y nombre visible. FastAPI describe todos los modelos y
permite probarlos en [`/docs`](http://localhost:5173/docs).

Nombre y dirección se comparan sin distinguir mayúsculas ni espacios
repetidos, pero **sí distinguen acentos**: «Café Perú» y «Cafe Peru» son dos
restaurantes distintos que dos personas pudieron aportar, aunque la búsqueda
los encuentre juntos. Intentar crear la misma combinación responde `409
Conflict` con la ficha que ya existe, para que la interfaz lleve al usuario
hasta ella en lugar de dejarlo en un error:

```json
{
  "detail": {
    "message": "A restaurant with the same name and address already exists",
    "restaurant": { "id": "…", "name": "Cocina del Barrio" }
  }
}
```

Una coordenada fuera de rango, una lista vacía o un slug desconocido responde
`422`. En esta base docente cualquier usuario autenticado puede modificar
restaurantes. Esa simplificación permite practicar el CRUD, pero **no es un
modelo de autorización apropiado para producción**: roles, ownership y
moderación quedan para una evolución posterior.

### Publicar fotografías

| Método y path | Resultado |
| --- | --- |
| `POST /api/v1/photos` | Publica la fotografía de un plato; responde `201` y publica `Location`. |
| `GET /api/v1/photos/{id}` | Metadatos de una fotografía, o `404`. |
| `GET /api/v1/photos/{id}/content` | Los bytes de la fotografía. |

Subir una fotografía es una acción completa en sí misma, y reseñarla es otra.
Recibe `multipart/form-data` con `restaurant_id`, `kind`, `dish_name`,
`visibility`, el archivo, un `caption` opcional que la interfaz puede usar
como texto alternativo de la imagen, y un `upload_group` opcional.

`kind` admite `dish`, `menu` y `venue`. **El nombre del plato es obligatorio
para una fotografía de plato y se rechaza para las otras dos**: una fotografía
del menú no es de ningún plato, y aceptar el campo en silencio produce datos
que después agrupan mal. La visibilidad es obligatoria y sin valor por
omisión, con el mismo criterio del check-in.

#### Publicar varias en un acto

**Cada fotografía viaja en su propia solicitud.** Así la interfaz muestra el
progreso de cada archivo y reintenta sólo el que falló; un multipart con
varias obligaría a rechazar el conjunto completo cuando una sola falla, que
sobre un teléfono significa volver a subir las que ya habían llegado.

Para que ese conjunto siga siendo un solo acto, el cliente genera un UUID y lo
repite como `upload_group` en todas las solicitudes de esa publicación. Las
fotografías que lo comparten forman **una sola entrada en el feed y en el
perfil**, fechada por la primera de ellas para que no se mueva mientras el
resto llega.

Todas las fotografías de un grupo comparten autor, restaurante, tipo,
visibilidad y plato; una solicitud que reutilice un grupo ajeno o incompatible
responde `422`, igual que la que pase del máximo de diez por grupo. El grupo
no es un recurso consultable: es una relación entre fotografías.

**El plato vive en la fotografía**, no en la reseña. Se guarda tal como se
escribió y además en una forma normalizada que ignora acentos y mayúsculas,
de modo que las fotografías del mismo plato se agrupen aunque una diga «Ají de
gallina» y otra «aji de gallina».

Un archivo que no sea un JPEG, PNG o WebP íntegro, o cuyo MIME declarado no
coincida con su contenido, responde `422`; uno sobre `MEDIA_MAX_UPLOAD_BYTES`
responde `413`. La validación ocurre antes de almacenar nada, y si la
transacción falla después, el objeto almacenado se elimina.

Una fotografía pública la ve cualquier sesión; una privada, sólo su autor,
tanto en sus metadatos como en su contenido.

### Reseñar un plato

`POST /api/v1/reviews` agrega una reseña a una **fotografía que ya existe**.
Recibe JSON con `photo_id`, `rating`, `text` y `visibility`; ya no recibe
multipart ni crea la fotografía, porque publicarla es una acción y reseñarla
es otra.

La reseña la escribe **quien tomó la fotografía**. Hay una razón de dominio
—uno reseña el plato que comió y fotografió— y otra estructural: cada
fotografía admite una sola reseña, así que permitir que cualquiera la escriba
dejaría a un tercero ocupando el único espacio que su dueño tiene. Sólo se
reseña una fotografía de plato.

La calificación va de 1 a 5, la misma escala que usarán los criterios de
evaluación de un restaurante, de modo que la interfaz presente un solo tipo de
control.

**Una reseña nunca es más visible que su fotografía.** Privada sobre una
fotografía pública es coherente —comparto la foto y me guardo la opinión—;
pública sobre una privada responde `422`, porque mostraría a todos el texto de
algo que nadie puede ver.

Una segunda reseña sobre la misma fotografía responde `409` con la que ya
existe, para que la interfaz lleve hasta ella. Una fotografía inexistente o no
visible responde `404`; una calificación fuera de rango, un texto en blanco o
una fotografía ajena o que no es de plato responden `422`.

Una fotografía reseñada deja de aparecer como actividad propia: la reseña la
lleva consigo, y contarlas por separado mostraría dos veces la misma
fotografía al mismo seguidor.

### Feed y detalle de reseñas

`GET /api/v1/feed` devuelve la actividad pública reciente relacionada con los
usuarios o restaurantes que sigue la sesión. La respuesta usa un envelope
extensible y paginación por cursor:

```json
{
  "items": [{"type":"review","occurred_at":"...","review": {"...":"..."}}],
  "next_cursor": "cursor-opaco-o-null"
}
```

`limit` tiene valor predeterminado 20 y máximo 50. Cuando exista
`next_cursor`, inclúyelo como `cursor` en la siguiente llamada; no lo modifiques
ni intentes interpretarlo. El orden es descendente por fecha e identificador,
y una reseña que coincide por ambos tipos de seguimiento aparece una sola vez.

`GET /api/v1/reviews/{review_id}` entrega la misma reseña estructurada. Las
reseñas públicas están disponibles para sesiones autenticadas; una privada sólo
puede verla su autor y para las demás sesiones responde `404`.

El seed local incorpora tres cuentas: `demo@example.com` (`demo`),
`demo2@example.com` (`demo2`) y `empty@example.com` (`empty`), todas con
contraseña `demo-password`. `demo` demuestra feed, deduplicación y detalle;
`empty` demuestra una página sin actividad. Las fotos docentes se cargan al
proveedor local o S3 a través del mismo contrato `MediaStorage` usado por las
reseñas normales.

Para probar el contrato conservando la cookie entre comandos:

```console
curl -i -c foodie-cookie.txt \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@example.com","password":"demo-password"}' \
  http://localhost:5173/api/v1/auth/login

curl -i -b foodie-cookie.txt \
  http://localhost:5173/api/v1/auth/session

curl -i -b foodie-cookie.txt \
  'http://localhost:5173/api/v1/feed?limit=2'

curl -i -b foodie-cookie.txt \
  http://localhost:5173/api/v1/reviews/30000000-0000-4000-8000-000000000001

curl -i -b foodie-cookie.txt \
  'http://localhost:5173/api/v1/restaurants?limit=3&offset=0'

curl -i -b foodie-cookie.txt \
  -H 'Origin: http://localhost:5173' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Restaurante del curso","address":"Monjitas 550, Santiago","latitude":-33.4369,"longitude":-70.6448,"cuisine_styles":["chilena","vegana"]}' \
  http://localhost:5173/api/v1/restaurants

curl -i -b foodie-cookie.txt \
  -H 'Origin: http://localhost:5173' \
  -X POST http://localhost:5173/api/v1/auth/logout
```

Usa un archivo temporal propio si compartes el computador y elimínalo al
terminar: contiene una credencial válida. El seed usa UUID estables docentes,
no contraseñas ni identificadores de producción. No incluyan secretos, cookies
ni contraseñas de producción en Git.

El seed está desactivado por defecto. Para activarlo fuera de Docker Compose,
establece `SEED_DEMO_DATA=true`. Los UUID de los usuarios, estilos y
restaurantes son estables: ejecutarlo nuevamente no duplica filas ni reemplaza
cambios hechos por un estudiante. La configuración rechaza explícitamente el
seed en `ENVIRONMENT=production`.

### Evaluar un restaurante

| Método y path | Resultado |
| --- | --- |
| `GET /api/v1/rating-criteria` | Criterios de evaluación que define el backend. |
| `POST /api/v1/evaluations` | Evalúa un restaurante; responde `201` y publica `Location`. |
| `GET /api/v1/evaluations/{id}` | Consulta una evaluación, o responde `404`. |
| `GET /api/v1/restaurants/{id}/evaluations` | Evaluaciones del restaurante, paginadas por cursor. |

La evaluación es del restaurante como un todo, distinta de la reseña de un
plato. Recibe `restaurant_id`, `ratings`, `comment`, `visibility` y una lista
opcional de `photo_ids`.

**Todos los criterios del catálogo son obligatorios, exactamente una vez cada
uno.** Un promedio calculado sobre un criterio que unos respondieron y otros
omitieron mezcla poblaciones distintas y no se puede comparar entre
restaurantes. Es además lo que hace que el promedio general coincida con el
promedio de los promedios por criterio. La escala es de 1 a 5, la misma de la
reseña de un plato.

El comentario general es obligatorio: para quien lee la ficha es lo que
explica los números.

**Cada persona evalúa un restaurante una sola vez.** Un segundo intento
responde `409` con la evaluación que ya existe. Las fotografías asociadas son
opcionales y tienen que ser del mismo restaurante, del mismo autor y de tipo
menú o instalaciones; una evaluación nunca es más visible que la menos visible
de ellas.

#### El resumen de la ficha

`GET /api/v1/restaurants/{id}` devuelve en `ratings` el promedio por criterio,
el promedio general y el total. **Agrega solamente evaluaciones públicas, para
todos los observadores, incluido el autor de una privada.** Un promedio que
cambiara según quién mira no sería comparable entre restaurantes, y su autor
vería en la ficha un número que nadie más ve; su evaluación privada aparece en
su perfil, que es donde el enunciado la ubica. Por lo mismo, el contador de
evaluaciones cuenta lo mismo que el resumen, y la lista de
`/restaurants/{id}/evaluations` contiene exactamente ese conjunto: los tres
números describen lo mismo en la misma pantalla.

Los promedios se publican redondeados a un decimal: más precisión sugeriría
una exactitud que veinte evaluaciones no tienen.

### Check-in en un restaurante

| Método y path | Resultado |
| --- | --- |
| `POST /api/v1/visits` | Registra que la sesión estuvo en un restaurante. |
| `GET /api/v1/visits/{id}` | Consulta una visita, o responde `404`. |

Recibe `restaurant_id`, `visibility` y `occurred_at` opcional. **La visibilidad
es obligatoria y el backend no aplica un valor por omisión**: el enunciado pide
que la elección esté en el formulario, y ese valor pertenece a la interfaz. Un
default en el servidor convertiría un campo olvidado en una publicación
accidental.

`occurred_at` es cuándo la persona estuvo ahí; ausente, es el instante de la
solicitud. El enunciado admite «está o estuvo», así que registrar la visita de
ayer es un caso legítimo. Un momento futuro responde `422` —una visita futura
es una reserva, que no está en el alcance—, con una tolerancia de minutos por
si el reloj del teléfono adelanta. El pasado no se restringe.

No hay restricción de unicidad: una persona visita el mismo restaurante muchas
veces, y ese es el caso normal.

Una visita es direccionable por URL propia, porque `notificationclick` y una
URL profunda recargada tienen que poder abrir su vista. Una visita pública la
ve cualquier sesión; una privada, sólo su autor, y para el resto responde
`404`, igual que el detalle de una reseña.

### Perfil de usuario y actividad

| Método y path | Resultado |
| --- | --- |
| `GET /api/v1/users?q=demo` | Busca personas por handle, paginado por cursor. |
| `GET /api/v1/users/{handle}` | Perfil de una persona, tal como la sesión puede verlo. |
| `PUT /api/v1/users/{handle}/follow` | Sigue a esa persona. |
| `DELETE /api/v1/users/{handle}/follow` | Deja de seguirla. |
| `GET /api/v1/users/{handle}/activity` | Su actividad, paginada por cursor. |

Ambas rutas requieren sesión y aceptan el handle como el usuario lo escribe:
`demo`, `@demo` y `DEMO` resuelven al mismo perfil. Un handle que no existe
responde `404`, y no una página vacía: son respuestas distintas.

`q` busca por handle, no por nombre: es lo que pide la épica, y buscar por
nombre real convertiría la aplicación en un directorio de personas, que es una
decisión de privacidad que nadie tomó. El término se lee como se escribe un
handle —se le retira una arroba inicial y se pasa a minúsculas—, así que
`@Demo`, `demo` y `DEMO` encuentran lo mismo. Un término de menos de dos
caracteres responde `422`, igual que en la búsqueda de restaurantes.

Cada resultado trae el **resumen compartido de una persona** —identificador,
handle, nombre y nacionalidad— acompañado de si el observador ya la sigue, para
que el botón se dibuje sin una solicitud por resultado. El estado de
seguimiento viaja al lado del resumen y no dentro: el autor de cada item de una
página de feed no lo necesita, y resolverlo ahí sería una consulta por fila.

**Ninguna respuesta de usuarios expone el correo.** Es el único dato de la
tabla que no es público.

Esta búsqueda requiere sesión, y eso es lo que la distingue del endpoint de
disponibilidad de handle que el registro no ofrece: aquel sería público,
porque el registro lo es, y daría un oráculo para enumerar los handles de la
aplicación a cualquiera antes de tener cuenta.

**La misma URL devuelve cosas distintas según quién pregunta.** El backend
recibe la identidad del observador desde la cookie y entrega sólo lo que esa
persona puede ver. Una reseña privada aparece en el perfil de su autor y en
ninguna otra vista. El cliente no filtra nada: si filtrara, ya habría recibido
lo que debía ocultarse.

Los contadores siguen la misma regla. El dueño ve contada su actividad
completa; otra persona ve contada sólo la pública, de modo que el contador
coincide siempre con lo que esa persona puede listar. Un contador que
incluyera actividad privada ajena delataría su existencia sin mostrarla.

Seguir es **fijar un estado**, no acumular un evento: el botón de la interfaz
declara «quiero seguir a esta persona», y por eso la acción es `PUT` y no
`POST`. Las dos operaciones son idempotentes y responden `204` sin cuerpo:
seguir a quien ya se sigue no es un conflicto, y dejar de seguir a quien no se
sigue tampoco, porque en ambos casos el estado final es el que se pidió.
Responder `409` obligaría a la interfaz a tratar como error una pulsación
repetida, que sobre un teléfono con conexión intermitente es un caso
frecuente.

Seguirse a uno mismo responde `422`, y un handle inexistente responde `404`.
Seguir a alguien no le notifica: el enunciado define la notificación como un
aviso de actividad nueva, y un seguimiento no es actividad.

El perfil trae además la relación del observador con esa persona —si la sigue,
si es seguido por ella, si es su propio perfil— para que la interfaz decida
entre «Seguir» y «Siguiendo» sin una segunda solicitud. La acción de seguir
llega con la épica 13; aquí sólo se informa el estado.

La actividad usa el mismo envelope del feed y se pagina por cursor opaco:

```json
{
  "items": [
    {
      "type": "review",
      "occurred_at": "2026-08-18T12:00:00Z",
      "published_at": "2026-08-18T12:00:00Z",
      "review": { "...": "..." }
    }
  ],
  "next_cursor": null
}
```

`occurred_at` es cuándo ocurrió la actividad y `published_at` cuándo se
publicó. Para una reseña coinciden, porque se publica cuando se escribe; para
una visita no tienen por qué, ya que su momento lo informa el usuario y puede
estar en el pasado. **El perfil ordena por `occurred_at`**, que es la
cronología de esa persona; **el feed ordena por `published_at`**, de modo que
registrar hoy una visita de hace un mes aparezca arriba en el feed de quienes
siguen a su autor y no enterrada donde nadie la verá. Un cursor que esta API
no emitió responde `422`.

**El feed no incluye la actividad del propio usuario**, ni siquiera la
publicada en un restaurante que sigue. Un feed es aquello de lo que uno se
entera, y nadie se entera de lo que acaba de publicar; su actividad propia la
consulta en su perfil. Es además la misma regla que rige las notificaciones,
donde el autor siempre se excluye, y la aplicación no debería responder de dos
maneras a la misma pregunta.

El feed no ofrece filtros por clase de actividad ni por restaurante: el
enunciado pide una vista cronológica única, y un filtro convierte el cursor en
una familia de cursores que hay que invalidar cuando el filtro cambia. Tampoco
tiene antigüedad máxima: «actividad reciente» es el orden, no un recorte, y
quien sigue a poca gente debe poder llegar al final de su feed. Un feed sin
nada que mostrar responde `200` con lista vacía y sin cursor, que la interfaz
debe distinguir de un error.

Cada clase de actividad viaja bajo una clave llamada como su `type`: una
reseña en `review`, una visita en `visit`, una publicación de fotografías en
`photo`. Un cliente que recorre la lista distingue por `type` y no necesita
saber cuáles clases existen.

El item de tipo `photo` lleva una **colección** de fotografías, aunque hoy
siempre tenga una: la épica 9 publica varias en un mismo acto y las presenta
como una sola actividad. Una fotografía que ya tiene reseña no aparece como
actividad propia: la reseña la lleva consigo, y contarlas por separado
mostraría dos veces la misma fotografía al mismo seguidor.

Para detener los servicios conservando los datos locales:

```console
docker compose down
```

## Pruebas

Para ejecutar pruebas directamente en el computador necesitas Python 3.13 y
[`uv`](https://docs.astral.sh/uv/), que crea el entorno virtual e instala las
dependencias declaradas por el backend:

```console
cd backend
uv sync --group dev
uv run pytest
```

Las pruebas normales no requieren una base de datos; las que llevan la marca
`integration` se omiten si `TEST_DATABASE_URL` no está configurada.

Para ejecutar la suite completa contra un PostgreSQL aislado, desde la raíz:

```console
docker compose --profile test up --build --abort-on-container-exit --exit-code-from backend-tests backend-tests
docker compose --profile test down --remove-orphans
```

El perfil `test` crea `test-db` sin volumen persistente y el servicio
`backend-tests` prueba un ciclo completo de upgrade/downgrade, ejecuta el seed
y corre Pytest. Cubre autenticación, CRUD, asociaciones, duplicados,
idempotencia, cargas multipart, compensación de storage y validación contra la
base migrada; no usa la base `db` de desarrollo.

No agregues `-v` al comando de limpieza: Compose lo aplicaría a todo el
proyecto y eliminaría también `postgres-data`, el volumen de la base de
desarrollo. `test-db` no usa un volumen nombrado, por lo que eliminar su
contenedor ya descarta la base de pruebas.

## HTTPS local y acceso desde un teléfono

HTTPS también se puede usar en el mismo computador. Los helpers del proyecto
emiten el certificado para `localhost`, `127.0.0.1`, `::1` y una o más
direcciones LAN o nombres mDNS proporcionados. Después de instalar la CA local,
Chrome o Firefox pueden abrir <https://localhost:5173> sin una advertencia de
certificado. Sigue
la guía de [Chrome y Firefox](docs/platforms/browsers.md) para entender y
verificar sus almacenes de confianza.

El navegador del teléfono no puede conectarse a `localhost` para alcanzar los
servicios del computador: en cada dispositivo, `localhost` designa a ese mismo
dispositivo. Para probar la aplicación desde un teléfono hay que publicar el
gateway en la red local y acceder mediante HTTPS.

### Conceptos que conviene recordar

**HTTPS** es HTTP protegido por [TLS](https://www.rfc-editor.org/rfc/rfc8446).
TLS cifra la conexión y permite que el cliente compruebe la identidad del
servidor. Para identificarse, el gateway presenta un **certificado X.509** que
contiene su clave pública, su vigencia y los nombres o direcciones IP para los
que es válido. El formato y la validación de estos certificados se definen en
el [perfil X.509 de Internet](https://www.rfc-editor.org/rfc/rfc5280).

Una **autoridad certificadora** o **CA** firma certificados. Un navegador
confía en un certificado del servidor cuando puede construir una cadena de
firmas hasta una CA presente en su almacén de confianza. En producción se usa
una CA pública. En desarrollo, [`mkcert`](https://github.com/FiloSottile/mkcert)
crea una CA privada local y emite con ella un certificado para este gateway.
Por eso hay que instalar el certificado público de esa CA tanto en el
computador como en el teléfono.

```text
rootCA-key.pem --firma--> certs/local.pem --nginx lo presenta a--> navegador
rootCA.pem     --se instala en--> almacén de confianza --lo consulta--> navegador
```

Los archivos cumplen funciones distintas:

| Archivo | Función | Tratamiento |
| --- | --- | --- |
| `rootCA.pem` | Certificado público de la CA local | Se instala en los dispositivos de desarrollo. |
| `rootCA-key.pem` | Clave privada de la CA local | No se copia ni se comparte: permite firmar otros certificados confiables. |
| `certs/local.pem` | Certificado X.509 que presenta nginx | Se monta en el gateway local. |
| `certs/local-key.pem` | Clave privada del gateway | Permanece en el computador y no se publica. |

El navegador valida también que la IP o el nombre escrito en la URL aparezca
en el certificado. Una IP debe coincidir exactamente, como explica la
[verificación de identidad en TLS](https://www.rfc-editor.org/rfc/rfc9525).
Confiar en la CA no corrige un certificado emitido para otra dirección.

### IP local, DNS y mDNS

El camino recomendado es usar la dirección IPv4 LAN del computador, por
ejemplo `192.168.1.40`. Es la dirección que el router asigna al computador
dentro de esa red y puede cambiar al conectarse a otra red.

Como alternativa, **mDNS** (_Multicast DNS_) permite resolver un nombre como
`mi-pc.local` sin configurar un servidor DNS. En vez de preguntar a un DNS
central, los dispositivos consultan por multicast a los otros equipos del
mismo enlace local. El sufijo `.local` está reservado para este mecanismo por
el [RFC 6762](https://www.rfc-editor.org/rfc/rfc6762). mDNS solo resuelve un
nombre a una dirección: no cifra la conexión ni reemplaza TLS.

mDNS es opcional porque algunas redes institucionales bloquean multicast o
separan a sus clientes. Si no sabes si está disponible, usa primero la IPv4
LAN. En ambos casos, el teléfono y el computador deben estar en la misma red y
la red Wi-Fi no debe tener aislamiento entre clientes.

Llamaremos **host de acceso** al valor exacto que escribirás en la URL: por
ejemplo, `192.168.1.40` o `mi-pc.local`. Ese valor aparece en dos lugares y no
en `.env.local`:

| Dato | Dónde se configura |
| --- | --- |
| Host de acceso | Argumento del helper del certificado y host de la URL. |
| Activación de TLS y puertos | `.env.local`. |
| Rutas del backend | URLs relativas del frontend; no incluyen host. |

### 1. Obtén la dirección y prepara el certificado

Sigue la guía de [Linux](docs/platforms/linux.md),
[macOS](docs/platforms/macos.md) o
[Windows](docs/platforms/windows.md) para:

1. elegir y verificar la dirección LAN o nombre mDNS que usarás;
2. instalar `mkcert` y confiar su CA local;
3. generar `certs/local.pem` y `certs/local-key.pem`; y
4. revisar el firewall de la plataforma.

El certificado debe incluir exactamente cada dirección o nombre que abrirás
desde el teléfono. Los helpers aceptan uno o más valores y los agregan a la
extensión `subjectAltName` del certificado, además de los nombres de loopback.
Por ejemplo, puedes incluir simultáneamente `192.168.1.40` y `mi-pc.local`.

### 2. Configura Docker Compose

Copia `.env.local.example` como `.env.local` en la raíz del repositorio. El
archivo resultante está ignorado por Git y contiene esta configuración:

```dotenv
LOCAL_TLS=true
COOKIE_SECURE=true
GATEWAY_HTTP_PORT=5174
GATEWAY_HTTPS_PORT=5173
```

Las variables tienen estos efectos:

- `LOCAL_TLS` indica al gateway nginx que termine TLS con el certificado local;
  FastAPI y Vite siguen usando HTTP dentro de la red privada de Compose;
- `COOKIE_SECURE` impide que la cookie de sesión viaje por HTTP;
- `GATEWAY_HTTPS_PORT=5173` conserva el puerto habitual para la entrada HTTPS;
  y
- `GATEWAY_HTTP_PORT=5174` evita que los dos mapeos de Compose intenten usar el
  mismo puerto. Es una reserva técnica: nginx no escucha HTTP en ese puerto
  cuando `LOCAL_TLS=true`; el gateway sirve sólo HTTPS.

`.env.local` no es uno de los nombres que Compose carga automáticamente. Debes
pasarlo explícitamente con `--env-file` en cada comando que cree o recree los
servicios de este perfil.

En la Web, un **origen** es la combinación de esquema, host y puerto. Por eso
`http://192.168.1.40:5173` y `https://192.168.1.40:5173` son orígenes distintos.
Con el gateway, el navegador recibe el frontend y llama a `/api/*` usando el
mismo origen. No se necesita CORS para ese camino. La configuración CORS del
backend se conserva para quienes ejecuten Vite directamente en el puerto 5173;
la [guía de CORS de FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)
desarrolla esta diferencia.

Inicia los servicios con el mismo comando en Linux, macOS y PowerShell:

```console
docker compose --env-file .env.local up --build
```

Si vuelves a generar `certs/local.pem` mientras el stack está activo, reinicia
el gateway para que nginx cargue el certificado nuevo:

```console
docker compose --env-file .env.local restart gateway
```

Verifica primero desde el computador:

```text
https://localhost:5173/
https://localhost:5173/healthz
https://localhost:5173/docs
```

### 3. Confía la CA en el teléfono y verifica

`mkcert -CAROOT` muestra el directorio de la CA. Instala **solo**
`rootCA.pem` en tu dispositivo de desarrollo; nunca copies ni compartas
`rootCA-key.pem`. Sigue la guía de tu dispositivo:

- [Instalar la CA local en Android](docs/platforms/android.md)
- [Instalar la CA local en iOS o iPadOS](docs/platforms/ios.md)

Desde el teléfono abre el mismo host que incluiste en el certificado. Por
ejemplo, para IPv4:

```text
https://192.168.1.40:5173/
https://192.168.1.40:5173/healthz
https://192.168.1.40:5173/docs
```

O bien, si verificaste e incluiste mDNS:

```text
https://mi-pc.local:5173/
https://mi-pc.local:5173/healthz
https://mi-pc.local:5173/docs
```

> No omitas `:5173`: forma parte de la dirección de este entorno local. Si
> escribes solo `https://mi-pc.local/`, el navegador usa el puerto HTTPS
> predeterminado `443`, donde este stack no publica el gateway.

El primer path viene de Vite; los otros dos pasan por nginx hacia FastAPI. El
frontend usa URLs relativas como `/api/v1/auth/login`, por lo que la IP o nombre
mDNS no queda escrito en su código.

El login debe responder con una cookie `Secure; HttpOnly; SameSite=Lax`.
`Secure` indica que el navegador solo debe enviarla por HTTPS; `HttpOnly`
impide que JavaScript acceda a ella y `SameSite` limita su envío en contextos
entre sitios. Estas propiedades forman parte del mecanismo de
[cookies HTTP](https://www.rfc-editor.org/rfc/rfc6265.html).

### Diagnóstico común

- Abre primero `/healthz` desde el computador usando el mismo host de acceso
  que probarás en el teléfono.
- `curl -k https://192.168.1.40:5173/healthz` —sustituyendo la IP por tu host
  de acceso— desactiva deliberadamente la validación del certificado. Úsalo
  solo para separar un problema de red de uno de confianza; no demuestra que
  HTTPS esté configurado correctamente.
- Si funciona en el computador pero no en el teléfono, revisa firewall,
  aislamiento Wi-Fi y que ambos dispositivos estén en la misma subred.
- Si el navegador rechaza el certificado, confirma que este incluya la
  dirección exacta y que el teléfono confíe `rootCA.pem`.
- Si la API responde pero el navegador no conserva la sesión, verifica HTTPS,
  `COOKIE_SECURE=true` y que el frontend envíe credenciales con Fetch.

## Desarrollo, migraciones y despliegue

La [guía de desarrollo y arquitectura](DEVELOPER.md) explica el stack, la
organización de `app/`, el ciclo de una solicitud, las convenciones para crear
endpoints y el flujo completo de migraciones con SQLAlchemy Core y Alembic.

La guía de [despliegue en AWS Lambda y migración a Aurora
DSQL](docs/aws-lambda.md) documenta el empaquetado, API Gateway, IAM, pooling,
migraciones y observabilidad de la etapa serverless.
