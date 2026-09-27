# Contrato de la API, por épica

Este documento describe qué expone el backend para cada una de las diecisiete
épicas del [enunciado general](../../README.md#funcionalidad-de-la-aplicación).
Está pensado para leerse con el enunciado al lado: cada sección dice qué pide
la épica, qué endpoints la sirven, y qué decisiones del backend cambian lo que
el cliente tiene que escribir.

**El contrato vigente siempre es el que expone `/docs`** en la instalación que
estés ejecutando. Aquí está lo que ese OpenAPI no alcanza a decir: por qué un
endpoint responde como responde, y qué no hay que intentar.

Para levantar el backend, ver el [README](../README.md). Para entender cómo
está construido por dentro, la [guía de desarrollo](../DEVELOPER.md).

## Índice

**[Antes de empezar](#antes-de-empezar)** — [Sesión y origen](#sesión-y-origen)
· [Paginación por cursor](#paginación-por-cursor)
· [Visibilidad](#visibilidad)
· [Formas compartidas](#formas-compartidas)
· [Errores](#errores)

**Cuenta y perfil**

1. [Registro e inicio de sesión](#1-registro-e-inicio-de-sesión)
2. [Perfil de usuario](#2-perfil-de-usuario)

**Descubrimiento de restaurantes**

3. [Buscar o crear un restaurante](#3-buscar-o-crear-un-restaurante)
4. [Explorar restaurantes en el mapa](#4-explorar-restaurantes-en-el-mapa)
5. [Buscar por estilo de comida y cercanía](#5-buscar-por-estilo-de-comida-y-cercanía)
6. [Ver un restaurante](#6-ver-un-restaurante)

**Registro de la experiencia**

7. [Hacer check-in en un restaurante](#7-hacer-check-in-en-un-restaurante)
8. [Publicar la foto de un plato](#8-publicar-la-foto-de-un-plato)
9. [Publicar fotos del menú o de las instalaciones](#9-publicar-fotos-del-menú-o-de-las-instalaciones)
10. [Reseñar un plato](#10-reseñar-un-plato)
11. [Evaluar un restaurante](#11-evaluar-un-restaurante)

**Interacción social**

12. [Buscar usuarios por handle](#12-buscar-usuarios-por-handle)
13. [Seguir y dejar de seguir usuarios](#13-seguir-y-dejar-de-seguir-usuarios)
14. [Seguir y dejar de seguir restaurantes](#14-seguir-y-dejar-de-seguir-restaurantes)
15. [Ver el feed](#15-ver-el-feed)
16. [Ver visitas de personas conocidas en un restaurante](#16-ver-visitas-de-personas-conocidas-en-un-restaurante)
17. [Comentar fotografías](#17-comentar-fotografías)

**[Fuera de las épicas](#fuera-de-las-épicas)** — [CRUD de restaurantes](#crud-de-restaurantes)
· [Salud del servicio](#salud-del-servicio)

---

## Antes de empezar

Cinco convenciones atraviesan toda la API. Están aquí una vez, y las épicas las
dan por sabidas.

### Sesión y origen

**Todo requiere sesión, salvo tres cosas**: el registro, el inicio de sesión y
el catálogo de nacionalidades. La sesión viaja en una cookie `HttpOnly` llamada
`session`, así que el frontend no puede leerla ni necesita hacerlo; basta con
enviar cada solicitud con `credentials: "include"`.

```js
await fetch("/api/v1/feed", { credentials: "include" });
```

Una solicitud sin sesión, con el token vencido o con la sesión revocada
responde `401`.

**Toda escritura valida el origen.** En `POST`, `PUT`, `PATCH` y `DELETE`, si
la solicitud trae una cabecera `Origin` que el backend no reconoce, responde
`403`. Desde el navegador la cabecera la agrega él mismo y no hay nada que
hacer. Una solicitud que **no** trae `Origin` —como `curl` por omisión— se
acepta, porque los clientes que no son navegadores suelen omitirla; lo que se
rechaza sin `Origin` es una que declare `Sec-Fetch-Site: cross-site`. Aun así,
los ejemplos de este documento la envían: es lo que hará tu frontend.

### Paginación por cursor

Las colecciones responden `{ items, next_cursor }` y se recorren por cursor,
no por `offset`. Mientras alguien recorre una lista, otras personas escriben, y
un desplazamiento numérico repite y salta elementos.

```js
let cursor = null;
do {
  const url = cursor ? `/api/v1/feed?limit=20&cursor=${cursor}` : "/api/v1/feed?limit=20";
  const page = await fetch(url, { credentials: "include" }).then((r) => r.json());
  render(page.items);
  cursor = page.next_cursor;
} while (cursor);
```

**El cursor es opaco.** No lo construyas, no lo interpretes y no lo modifiques:
su contenido pertenece a la consulta que lo emitió. Uno que esta API no emitió
responde `422`. Cuando `next_cursor` es `null` no hay más páginas.

`limit` es opcional; su valor por omisión y su máximo dependen del endpoint y
están en la tabla de cada épica.

Tres endpoints **no** paginan, y cada uno dice por qué: el mapa, la búsqueda
por cercanía y el bloque de personas conocidas de la ficha.

### Visibilidad

Al registrar actividad —una visita, una fotografía, una reseña, una
evaluación— el usuario elige si es pública o privada. **La visibilidad es
obligatoria y el backend nunca aplica un valor por omisión**: el enunciado pide
que la elección esté en el formulario. Un default en el servidor convertiría un
campo olvidado en una publicación accidental.

La regla es una sola y vale en todas partes:

> Una actividad pública la ve cualquier sesión. Una privada la ve sólo su
> autor. Para cualquier otra sesión, una actividad privada **no existe**: no
> aparece en listas, no se cuenta en contadores y su detalle responde `404`.

**El cliente no filtra nunca.** El backend recibe la identidad del observador
desde la cookie y devuelve sólo lo que esa persona puede ver. La misma URL
devuelve cosas distintas según quién pregunta, y eso es deliberado. Un cliente
que filtra ya recibió lo que debía ocultarse.

Los contadores siguen la misma regla: informan exactamente lo que ese
observador podría además listar. Uno que incluyera actividad privada ajena
delataría su existencia sin mostrarla.

### Formas compartidas

Cuatro objetos aparecen en muchas respuestas, siempre con la misma forma.
Escribe un componente por cada uno y reutilízalo.

**Resumen de persona** — autor de una actividad, cabecera de un perfil,
resultado de la búsqueda, visitante conocido, autor de un comentario:

```json
{
  "id": "00000000-0000-4000-8000-000000000001",
  "handle": "demo",
  "name": "Demo Foodie",
  "nationality": { "code": "CL", "name": "Chile" }
}
```

El handle se guarda sin arroba y en minúsculas. **La arroba es presentación**:
la agrega la interfaz al mostrar `@demo`. `nationality.name` puede ser `null`
si el código almacenado no está en el catálogo.

**Resumen de restaurante** — colección, mapa, búsqueda por cercanía:

```json
{
  "id": "…", "name": "…", "address": "…",
  "latitude": -33.4369, "longitude": -70.6448,
  "cuisine_styles": [{ "id": "…", "slug": "chilena", "name": "Chilena" }]
}
```

La ficha agrega `created_at` y `updated_at`. La búsqueda por cercanía agrega
`distance_m`.

**Restaurante de una actividad** — deliberadamente más delgado, porque una
tarjeta de feed no dibuja un marcador:

```json
{ "id": "…", "name": "…", "address": "…" }
```

**Envelope de actividad** — lo usan el feed y el perfil, y está descrito en
[la épica 15](#15-ver-el-feed).

### Errores

| Código | Qué significa |
| --- | --- |
| `401` | Sin sesión, vencida o revocada. |
| `403` | Escritura sin un `Origin` confiable. |
| `404` | No existe, **o** existe y esta sesión no puede verlo. Son la misma respuesta a propósito. |
| `409` | El recurso ya existe. El cuerpo nombra el que existe, para llevar al usuario hasta él en vez de dejarlo en un error. |
| `413` | El archivo excede `MEDIA_MAX_UPLOAD_BYTES`. |
| `422` | La solicitud está mal formada, o pide algo que las reglas del dominio no permiten. |
| `503` | El almacén de medios o la base de datos no respondieron. |

`404` y `422` se reparten así: **`404` cuando el recurso de la URL no está
disponible; `422` cuando está y lo que se pide sobre él no se puede aceptar.**
Comentar una fotografía privada ajena es `404` —esa fotografía no existe para
quien pregunta—; comentar una privada propia es `422`, porque existe y lo que
le falta no es permiso sino audiencia.

[↑ Índice](#índice)

---

## 1. Registro e inicio de sesión

> Una persona puede crear una cuenta indicando su nombre, correo electrónico,
> handle y nacionalidad, y luego autenticarse para usar la aplicación.

| Método y path | Sesión | Resultado |
| --- | --- | --- |
| `POST /api/v1/auth/register` | no | Crea la cuenta, persiste la sesión y emite la cookie. `201`. |
| `POST /api/v1/auth/login` | no | Valida credenciales y emite la cookie. `204`. |
| `GET /api/v1/auth/session` | sí | Identidad y caducidad de la sesión vigente. |
| `POST /api/v1/auth/logout` | sí | Revoca la sesión y elimina la cookie. `204`. |
| `GET /api/v1/countries` | no | Catálogo de nacionalidades para el selector del formulario. |

### Registrar

```http
POST /api/v1/auth/register
Content-Type: application/json
Origin: http://localhost:5173

{ "name": "…", "email": "…", "handle": "…", "nationality": "CL", "password": "…" }
```

Es la única ruta de escritura que no requiere sesión, aunque sí valida el
origen. Responde `201` con el mismo cuerpo que `GET /api/v1/auth/session` y
emite la cookie: **quien se registra queda autenticado en la misma
operación**, sin un segundo viaje que obligue al cliente a conservar la
contraseña.

`name` hasta 120 caracteres, `handle` hasta 64, `password` entre 12 y 128.

**El servidor normaliza antes de escribir.** El handle pierde una arroba
inicial y pasa a minúsculas —`@Demo`, `demo` y `DEMO` son el mismo handle— y
después tiene que calzar con `^[a-z0-9_]{3,30}$`. El correo pasa a minúsculas.
La nacionalidad es un código ISO 3166-1 alfa-2 y se guarda en mayúsculas.

Un correo o un handle ya tomados responden `409` nombrando el campo, para que
el formulario pueda marcarlo:

```json
{ "detail": { "field": "handle", "message": "Handle already taken" } }
```

**No existe un endpoint que informe si un handle está disponible.** Sería
público, porque el registro lo es, y permitiría enumerar los handles de la
aplicación sin tener cuenta. El `409` entrega la misma información en el
momento en que hace falta.

Un formato inválido, una contraseña de menos de doce caracteres o un código de
país desconocido responden `422`.

### Iniciar y cerrar sesión

`POST /api/v1/auth/login` recibe `email` y `password` y responde `204` sin
cuerpo; credenciales incorrectas responden `401`. `POST /api/v1/auth/logout`
revoca la sesión en la base y borra la cookie, también con `204`.

La cookie contiene un JWT firmado y es `HttpOnly`: **el frontend no puede ni
debe leerla**. Para saber quién está conectado, `GET /api/v1/auth/session`.

### Nacionalidades

`GET /api/v1/countries` publica los 249 códigos ISO 3166-1 alfa-2 con su
nombre en español, ordenados por nombre. Es público y cacheable, porque el
formulario de registro lo necesita antes de que exista una sesión.

```json
[{ "code": "CL", "name": "Chile" }, { "code": "PE", "name": "Perú" }]
```

[↑ Índice](#índice)

---

## 2. Perfil de usuario

> Cada usuario tiene un perfil con su handle, nombre y nacionalidad. Al
> consultar su propio perfil, ve tanto su actividad pública como su actividad
> privada; cuando otro usuario consulta ese mismo perfil, sólo ve sus datos
> públicos y la actividad que decidió compartir.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `GET /api/v1/users/{handle}` | — | Perfil, tal como la sesión puede verlo. |
| `GET /api/v1/users/{handle}/activity` | 1–50, def. 20 | Su actividad, paginada por cursor. |

El handle se acepta como el usuario lo escriba: `demo`, `@demo` y `DEMO`
resuelven al mismo perfil. Uno que no existe responde `404`, y no una página
vacía: son respuestas distintas.

### El perfil

```json
{
  "id": "…", "handle": "demo", "name": "Demo Foodie",
  "nationality": { "code": "CL", "name": "Chile" },
  "joined_at": "2026-08-01T12:00:00Z",
  "counters": { "activity": 8, "followers": 1, "following": 3 },
  "viewer": { "is_self": false, "following": true, "followed_by": false }
}
```

Es el [resumen de persona](#formas-compartidas) más `joined_at`, los contadores
y la relación del observador. **`viewer` evita una segunda solicitud** para
decidir entre «Seguir» y «Siguiendo».

`counters.activity` cuenta **actos, no filas**: tres fotografías publicadas en
un mismo acto cuentan una, y una fotografía que ya tiene reseña no se cuenta
aparte, porque la reseña la lleva consigo. El dueño ve contada su actividad
completa; otra persona, sólo la pública.

**Ninguna respuesta de usuarios expone el correo.** Es el único dato de la
tabla que no es público.

### La actividad

Usa el [envelope de actividad](#15-ver-el-feed), el mismo del feed, y se pagina
por cursor opaco.

**El perfil ordena por `occurred_at`** —cuándo ocurrió la actividad—, que es la
cronología de esa persona. El feed ordena por `published_at`. Para una reseña
los dos instantes coinciden; para una visita no tienen por qué, porque su
momento lo informa el usuario y puede estar en el pasado.

Una actividad privada aparece aquí cuando el observador es el dueño del
perfil, y en ninguna otra vista.

[↑ Índice](#índice)

---

## 3. Buscar o crear un restaurante

> El usuario busca un restaurante escribiendo su nombre y accede a su ficha
> desde los resultados. Si no existe, puede crearlo indicando su nombre,
> dirección y estilos de comida, previniendo duplicados.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `GET /api/v1/restaurants?q=…` | 1–100, def. 20 | Colección, paginada por cursor. |
| `GET /api/v1/cuisine-styles` | — | Catálogo de estilos para el formulario. |
| `POST /api/v1/restaurants` | — | Crea uno. `201` y publica `Location`. |

### Buscar

`q` acota la colección a un término contenido en el nombre, **ignorando
mayúsculas y acentos**: `cafe` encuentra «Café Ñielol». El orden es alfabético
sobre esa misma forma y no por relevancia, porque un cursor tiene que reanudar
desde una posición estable. Sin `q`, devuelve la colección completa.

Un término de menos de dos caracteres responde `422` en vez de devolver todo.

Cada item es el [resumen de restaurante](#formas-compartidas).

> **Cambio de contrato.** Esta colección devolvía un arreglo y paginaba con
> `limit` y `offset`. Ahora devuelve `{ items, next_cursor }`. Un cliente
> escrito contra la forma anterior falla al iterar sobre un objeto.

### Crear

```json
{
  "name": "Cocina del Barrio",
  "address": "Monjitas 550, Santiago",
  "latitude": -33.4369, "longitude": -70.6448,
  "cuisine_styles": ["chilena", "vegana"]
}
```

`cuisine_styles` recibe de uno a veinte slugs existentes, sin repetir. El seed
ofrece `chilena`, `peruana`, `italiana`, `japonesa`, `india`, `vegana`,
`cafeteria` y `sandwicheria`; `GET /api/v1/cuisine-styles` entrega el catálogo
con `id`, `slug` y nombre visible, para que el selector no lleve slugs escritos
a mano. La respuesta expande cada slug al objeto completo.

**La prevención de duplicados es la respuesta del `POST`, no una consulta
previa.** No hay endpoint de «¿existe ya?»: entre la comprobación y la
creación pueden pasar cosas, y dos personas creando el mismo restaurante a la
vez es justo el caso que hay que evitar.

Nombre y dirección se comparan sin distinguir mayúsculas ni espacios
repetidos, pero **sí distinguen acentos**: «Café Perú» y «Cafe Peru» son dos
restaurantes distintos que dos personas pudieron aportar, aunque la búsqueda
los encuentre juntos. Repetir la combinación responde `409` con la ficha que ya
existe, para llevar al usuario hasta ella:

```json
{
  "detail": {
    "message": "A restaurant with the same name and address already exists",
    "restaurant": { "id": "…", "name": "Cocina del Barrio" }
  }
}
```

Una coordenada fuera de rango, una lista de estilos vacía o un slug
desconocido responden `422`.

[↑ Índice](#índice)

---

## 4. Explorar restaurantes en el mapa

> El usuario recorre libremente un mapa interactivo, desplazándose y
> acercándose sobre la zona que le interesa, y ve los restaurantes disponibles
> en ella.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `GET /api/v1/restaurants/map` | 1–200, def. 200 | Lo que hay dentro del rectángulo visible. |

Recibe `south`, `west`, `north` y `east` en grados decimales, **los cuatro
obligatorios**. Devuelve `{ items, truncated }` con el
[resumen de restaurante](#formas-compartidas).

**No se pagina.** Un rectángulo es una consulta de mapa, no una lista que se
recorre: si el resultado no cabe, la respuesta es acercar. `truncated` indica
que el rectángulo contenía más de los que se devolvieron, y la interfaz debe
pedir un acercamiento en lugar de dibujar un mapa incompleto como si estuviera
completo. Lo que se devuelve en ese caso es la parte sur del rectángulo y no
una muestra representativa; por eso el aviso existe.

Un rectángulo cuya arista oeste queda al este de la arista este **cruza el
antimeridiano**, y se maneja como dos rangos de longitud. Uno invertido en
latitud, una coordenada fuera de rango o un área mayor que cien grados
cuadrados responden `422`; el último con un mensaje que la interfaz puede
traducir a «acerca el mapa». Un rectángulo válido sin restaurantes responde
`200` con `items` vacío, que es distinto de un error.

> **La cuota de Google Maps es acotada y esta consulta es barata pero no
> gratis.** No la solicites en cada movimiento del mapa: espera a que el
> desplazamiento termine, y omítela cuando el rectángulo nuevo esté contenido
> en el que ya consultaste.

[↑ Índice](#índice)

---

## 5. Buscar por estilo de comida y cercanía

> El usuario busca restaurantes de un cierto estilo de comida a menos de una
> distancia dada desde donde se encuentra, y ve los resultados sobre el mapa y
> en una lista ordenada por distancia.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `GET /api/v1/restaurants/nearby` | 1–200, def. 200 | Cercanos, ordenados por distancia. |

Recibe `latitude`, `longitude` y `radius` en metros, los tres obligatorios, y
`cuisine_style` **opcional y repetible**: un restaurante califica si tiene al
menos uno de los estilos indicados. Sin ese parámetro devuelve todos los
cercanos, porque el selector de la pantalla se puede limpiar.

```
GET /api/v1/restaurants/nearby?latitude=-33.43&longitude=-70.64&radius=2000&cuisine_style=chilena&cuisine_style=peruana
```

Devuelve `{ items, truncated }` ordenado por distancia ascendente, con el
[resumen de restaurante](#formas-compartidas) más `distance_m` como único
campo agregado.

**La distancia la mide el servidor**, con la fórmula de Haversine sobre un
radio terrestre medio de 6 371 008,8 m, y se publica redondeada a metros: más
precisión sugeriría una exactitud que la posición del navegador no tiene. Que
el cliente la recalcule invita a mostrar un número distinto del que se usó
para ordenar.

Tampoco se pagina: el orden es una distancia calculada, que no está indexada,
y un cursor sobre ella obligaría a recalcularla en cada página. Si el resultado
no cabe, la respuesta es reducir el radio o afinar el estilo.

**El radio máximo son cincuenta kilómetros.** Una consulta de cercanía de mil
kilómetros no es una consulta de cercanía: es la colección completa, que ya
tiene su endpoint. Un radio no positivo o mayor que el máximo, una coordenada
fuera de rango o un slug desconocido responden `422`; un círculo válido sin
restaurantes responde `200` con `items` vacío.

> **Dos advertencias.** No solicites en cada pulsación del selector de estilo
> ni en cada arrastre del control de distancia. Y como el enunciado exige que
> la aplicación siga siendo utilizable cuando se deniega el permiso de
> geolocalización, **esta consulta no puede ser el único camino hacia un
> restaurante**: la búsqueda por nombre y la exploración libre del mapa tienen
> que seguir estando.

[↑ Índice](#índice)

---

## 6. Ver un restaurante

> El usuario consulta la ficha de un restaurante: su información básica, sus
> estilos de comida, las fotografías de platos, menús e instalaciones
> publicadas por la comunidad, y el resumen de sus evaluaciones.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `GET /api/v1/restaurants/{id}` | — | La ficha, tal como la sesión puede verla. |
| `GET /api/v1/restaurants/{id}/photos` | 1–50, def. 20 | Galería, paginada por cursor. |

### La ficha

Es la pantalla donde converge el resto de la aplicación. Al
[resumen de restaurante](#formas-compartidas) más `created_at` y `updated_at`
agrega cuatro bloques que **dependen de quién pregunta**:

```json
{
  "id": "…", "name": "…", "address": "…", "latitude": …, "longitude": …,
  "cuisine_styles": [ … ], "created_at": "…", "updated_at": "…",
  "counters": { "photos": 6, "reviews": 3, "evaluations": 2, "visits": 5, "followers": 1 },
  "ratings": { "criteria": [ … ], "average": 3.8, "total": 2 },
  "viewer": { "following": true },
  "known_visitors": { "total": 2, "items": [ … ] }
}
```

* **`counters`** informa sólo lo que ese observador podría además listar.
* **`ratings`** es el resumen de evaluaciones, descrito en
  [la épica 11](#11-evaluar-un-restaurante). Es **la única excepción** a la
  regla del observador: agrega sólo evaluaciones públicas, para todos.
* **`viewer`** dice si el observador sigue el restaurante
  ([épica 14](#14-seguir-y-dejar-de-seguir-restaurantes)).
* **`known_visitors`** nombra a las personas que el observador sigue y
  estuvieron ahí ([épica 16](#16-ver-visitas-de-personas-conocidas-en-un-restaurante)).

Un identificador que no existe responde `404`.

### La galería no está en la ficha

Crece sin límite con la actividad del restaurante, y la ficha no. Tiene su
propio endpoint, `{ items, next_cursor }` en orden cronológico descendente:

```json
{
  "id": "…",
  "author": { "id": "…", "handle": "demo2", "name": "Demo Foodie Dos" },
  "kind": "dish",
  "visibility": "public",
  "created_at": "2026-08-22T13:00:00Z",
  "content_url": "/api/v1/photos/…/content",
  "review_id": "…",
  "comments_count": 7
}
```

Incluye las fotografías públicas y, además, las privadas del propio
observador. `review_id` es `null` si la fotografía no tiene reseña;
`comments_count` es la conversación completa
([épica 17](#17-comentar-fotografías)).

`kind` acota la galería a `dish`, `menu` o `venue`, que son tres recorridos
distintos sobre la misma galería; un tipo desconocido responde `422`.

**La visibilidad de una fotografía es suya** y no se deduce de la reseña que
la acompañe: `GET /api/v1/photos/{id}/content` autoriza contra ella, de modo
que la galería y el contenido concuerdan siempre.

[↑ Índice](#índice)

---

## 7. Hacer check-in en un restaurante

> El usuario registra que está o estuvo en un restaurante.

| Método y path | Resultado |
| --- | --- |
| `POST /api/v1/visits` | Registra la visita. `201` y publica `Location`. |
| `GET /api/v1/visits/{id}` | Una visita, o `404`. |

```json
{ "restaurant_id": "…", "visibility": "public", "occurred_at": "2026-08-17T13:00:00Z" }
```

`visibility` es obligatoria, sin valor por omisión: ver
[Visibilidad](#visibilidad).

**`occurred_at` es cuándo la persona estuvo ahí**; ausente, es el instante de
la solicitud, que es el caso normal de un check-in en el lugar. El enunciado
admite «está o estuvo», así que registrar la visita de ayer es legítimo y el
pasado no se restringe. Un momento futuro responde `422` —una visita futura es
una reserva, que no está en el alcance—, con una tolerancia de cinco minutos
por si el reloj del teléfono adelanta. Un instante sin zona horaria también
responde `422`.

**No hay restricción de unicidad**: una persona visita el mismo restaurante
muchas veces, y ese es el caso normal.

Una visita es direccionable por URL propia, porque `notificationclick` y una
URL profunda recargada tienen que poder abrir su vista. La respuesta es el
objeto `visit` del [envelope de actividad](#15-ver-el-feed).

Un restaurante inexistente responde `404`; una visita privada ajena, también.

[↑ Índice](#índice)

---

## 8. Publicar la foto de un plato

> El usuario sube la fotografía de un plato que probó, identificando de qué
> plato se trata.

| Método y path | Resultado |
| --- | --- |
| `POST /api/v1/photos` | Publica una fotografía. `201` y publica `Location`. |
| `GET /api/v1/photos/{id}` | Metadatos de una fotografía, o `404`. |
| `GET /api/v1/photos/{id}/content` | Los bytes. |

**Subir una fotografía es una acción completa en sí misma, y reseñarla es
otra.** Recibe `multipart/form-data`, que en JavaScript se construye con
`FormData`:

```js
const body = new FormData();
body.append("restaurant_id", restaurantId);
body.append("kind", "dish");
body.append("dish_name", dishName);
body.append("visibility", "public");
body.append("photo", fileInput.files[0]);
// body.append("caption", "…");        opcional, texto alternativo
// body.append("upload_group", uuid);  opcional, ver épica 9

await fetch("/api/v1/photos", { method: "POST", credentials: "include", body });
```

**No definas `Content-Type` a mano**: el navegador tiene que agregar el
`boundary` de ese `FormData`.

`kind` admite `dish`, `menu` y `venue`, y su valor por omisión es `dish`. **El
nombre del plato es obligatorio para una fotografía de plato y se rechaza para
las otras dos**: una fotografía del menú no es de ningún plato, y aceptar el
campo en silencio produce datos que después agrupan mal. `dish_name` admite
hasta 120 caracteres y `caption` hasta 500.

**El plato vive en la fotografía**, no en la reseña. Se guarda tal como se
escribió y además en una forma normalizada que ignora acentos y mayúsculas, de
modo que las fotografías del mismo plato se agrupen aunque una diga «Ají de
gallina» y otra «aji de gallina».

Un archivo que no sea un JPEG, PNG o WebP íntegro, o cuyo MIME declarado no
coincida con su contenido, responde `422`; uno sobre `MEDIA_MAX_UPLOAD_BYTES`
responde `413`. La validación ocurre **antes** de almacenar nada, y si la
transacción falla después, el objeto almacenado se elimina.

`content_url` es relativa, estable y requiere la misma cookie; así funciona con
`localhost`, una IP, mDNS, el subdominio del grupo y CloudFront sin incrustar
hosts en el código. Una fotografía pública la ve cualquier sesión; una privada,
sólo su autor, tanto en sus metadatos como en su contenido.

[↑ Índice](#índice)

---

## 9. Publicar fotos del menú o de las instalaciones

> El usuario sube una o más fotografías del menú o de los espacios de un
> restaurante, de modo que la comunidad conozca su oferta, sus precios y sus
> instalaciones.

Mismo endpoint de la épica 8, con `kind` en `menu` o `venue` y sin
`dish_name`. Lo que esta épica agrega es **publicar varias como un solo acto**.

**Cada fotografía viaja en su propia solicitud.** Así la interfaz muestra el
progreso de cada archivo y reintenta sólo el que falló; un multipart con varias
obligaría a rechazar el conjunto completo cuando una sola falla, que sobre un
teléfono significa volver a subir las que ya habían llegado.

Para que ese conjunto siga siendo un solo acto, **el cliente genera un UUID y
lo repite como `upload_group`** en todas las solicitudes de esa publicación:

```js
const uploadGroup = crypto.randomUUID();
for (const file of files) {
  const body = new FormData();
  body.append("restaurant_id", restaurantId);
  body.append("kind", "menu");
  body.append("visibility", "public");
  body.append("upload_group", uploadGroup);
  body.append("photo", file);
  await fetch("/api/v1/photos", { method: "POST", credentials: "include", body });
}
```

Las fotografías que comparten grupo forman **una sola entrada en el feed y en
el perfil**, fechada por la primera de ellas para que no se mueva mientras el
resto llega.

Todas las de un grupo comparten autor, restaurante, tipo, visibilidad y plato.
Una solicitud que reutilice un grupo ajeno o incompatible responde `422`, igual
que la que pase del **máximo de diez por grupo**. El grupo no es un recurso
consultable: es una relación entre fotografías.

[↑ Índice](#índice)

---

## 10. Reseñar un plato

> El usuario añade una reseña a la fotografía de un plato, con una calificación
> y un texto que describe su experiencia. Cada reseña se asocia exactamente a
> una fotografía del plato.

| Método y path | Resultado |
| --- | --- |
| `POST /api/v1/reviews` | Reseña una fotografía que ya existe. `201` y publica `Location`. |
| `GET /api/v1/reviews/{id}` | Una reseña, o `404`. |

```json
{ "photo_id": "…", "rating": 4, "text": "…", "visibility": "public" }
```

> **Cambio de contrato.** Este endpoint recibía `multipart/form-data` con la
> fotografía, el nombre del plato y el texto, y creaba ambas cosas en una
> operación. Ahora recibe JSON sobre una fotografía que ya existe. Un cliente
> escrito contra el contrato anterior recibe `422` hasta que envíe JSON.

**La reseña la escribe quien tomó la fotografía.** Hay una razón de dominio
—uno reseña el plato que comió y fotografió— y otra estructural: cada
fotografía admite una sola reseña, así que permitir que cualquiera la escriba
dejaría a un tercero ocupando el único espacio que su dueño tiene. Sólo se
reseña una fotografía de plato.

`rating` va de 1 a 5, la misma escala de los criterios de evaluación, de modo
que la interfaz presente un solo tipo de control. `text` admite hasta 2000
caracteres y no puede estar en blanco.

**Una reseña nunca es más visible que su fotografía.** Privada sobre una
fotografía pública es coherente —comparto la foto y me guardo la opinión—;
pública sobre una privada responde `422`, porque mostraría a todos el texto de
algo que nadie puede ver.

Una segunda reseña sobre la misma fotografía responde `409` con la que ya
existe, para que la interfaz lleve hasta ella. Una fotografía inexistente o no
visible responde `404`; una calificación fuera de rango, un texto en blanco o
una fotografía ajena o que no es de plato responden `422`.

**Una fotografía reseñada deja de aparecer como actividad propia**: la reseña
la lleva consigo, y contarlas por separado mostraría dos veces la misma
fotografía al mismo seguidor.

`GET /api/v1/reviews/{id}` devuelve el objeto `review` del
[envelope de actividad](#15-ver-el-feed), con su autor, su restaurante y su
fotografía. Publicar una fotografía **sí** avisa a quien corresponda; reseñarla
no ([épica 14](#14-seguir-y-dejar-de-seguir-restaurantes)).

[↑ Índice](#índice)

---

## 11. Evaluar un restaurante

> El usuario califica un restaurante en varios criterios de evaluación y
> agrega un comentario general. Puede asociar a la evaluación una o más
> fotografías del menú o de las instalaciones. La aplicación muestra el
> resumen de las evaluaciones recibidas por cada restaurante.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `GET /api/v1/rating-criteria` | — | Criterios que define el backend. |
| `POST /api/v1/evaluations` | — | Evalúa un restaurante. `201` y publica `Location`. |
| `GET /api/v1/evaluations/{id}` | — | Una evaluación, o `404`. |
| `GET /api/v1/restaurants/{id}/evaluations` | 1–50, def. 20 | Las del restaurante, por cursor. |

```json
{
  "restaurant_id": "…",
  "ratings": { "comida": 4, "servicio": 3, "ambiente": 5, "precio-calidad": 4 },
  "comment": "…",
  "visibility": "public",
  "photo_ids": ["…"]
}
```

La evaluación es **del restaurante como un todo**, distinta de la reseña de un
plato.

**Todos los criterios del catálogo son obligatorios, exactamente una vez cada
uno.** Un promedio calculado sobre un criterio que unos respondieron y otros
omitieron mezcla poblaciones distintas y no se puede comparar entre
restaurantes. Es además lo que hace que el promedio general coincida con el
promedio de los promedios por criterio. La escala es de 1 a 5, la misma de la
reseña.

Los criterios son dato del backend, no una tabla editable:
`GET /api/v1/rating-criteria` entrega `slug` y nombre visible, y el formulario
se construye desde ahí. Un criterio faltante, repetido o desconocido responde
`422`.

El **comentario general es obligatorio** —hasta 2000 caracteres—: para quien
lee la ficha es lo que explica los números.

**Cada persona evalúa un restaurante una sola vez.** Un segundo intento
responde `409` con la evaluación que ya existe. Las fotografías asociadas son
opcionales y tienen que ser del mismo restaurante, del mismo autor y de tipo
menú o instalaciones; una evaluación nunca es más visible que la menos visible
de ellas.

### El resumen de la ficha

`ratings`, en `GET /api/v1/restaurants/{id}`, trae el promedio por criterio, el
promedio general y el total:

```json
{
  "criteria": [{ "criterion": "comida", "average": 4.0 }, …],
  "average": 3.8,
  "total": 2
}
```

**Agrega solamente evaluaciones públicas, para todos los observadores,
incluido el autor de una privada.** Es la única excepción a la regla del
observador, y es deliberada: un promedio que cambiara según quién mira no sería
comparable entre restaurantes, y su autor vería en la ficha un número que nadie
más ve. Su evaluación privada aparece en su perfil, que es donde el enunciado
la ubica.

Por lo mismo, `counters.evaluations` cuenta lo mismo que el resumen, y
`/restaurants/{id}/evaluations` contiene exactamente ese conjunto: **los tres
números describen lo mismo en la misma pantalla**. `average` es `null` mientras
no haya evaluaciones. Los promedios se publican redondeados a un decimal: más
precisión sugeriría una exactitud que veinte evaluaciones no tienen.

[↑ Índice](#índice)

---

## 12. Buscar usuarios por handle

> El usuario encuentra a otras personas por su handle y llega a su perfil.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `GET /api/v1/users?q=…` | 1–50, def. 20 | Personas, paginadas por cursor. |

**`q` es obligatorio y busca por handle, no por nombre.** Es lo que pide la
épica, y buscar por nombre real convertiría la aplicación en un directorio de
personas, que es una decisión de privacidad que nadie tomó.

El término se lee como se escribe un handle —se le retira una arroba inicial y
se pasa a minúsculas—, así que `@Demo`, `demo` y `DEMO` encuentran lo mismo.
Coincide por contenido, no sólo por prefijo. Menos de dos caracteres responde
`422`, igual que en la búsqueda de restaurantes.

Cada resultado es el [resumen de persona](#formas-compartidas) **acompañado**
de `following`, para que el botón se dibuje sin una solicitud por fila:

```json
{ "id": "…", "handle": "demo2", "name": "…", "nationality": { … }, "following": false }
```

El estado de seguimiento viaja al lado del resumen y no dentro: el autor de
cada item de una página de feed no lo necesita, y resolverlo ahí sería una
consulta por fila.

**Esta búsqueda requiere sesión**, y eso es lo que la distingue del endpoint de
disponibilidad de handle que el registro no ofrece: aquel sería público, y
daría un oráculo para enumerar los handles de la aplicación a cualquiera antes
de tener cuenta.

[↑ Índice](#índice)

---

## 13. Seguir y dejar de seguir usuarios

> El usuario decide de quiénes quiere enterarse mediante su feed y sus
> notificaciones, y puede revertir esa decisión.

| Método y path | Resultado |
| --- | --- |
| `PUT /api/v1/users/{handle}/follow` | Sigue a esa persona. `204`. |
| `DELETE /api/v1/users/{handle}/follow` | Deja de seguirla. `204`. |

**Seguir es fijar un estado, no acumular un evento.** El botón de la interfaz
declara «quiero seguir a esta persona», y por eso la acción es `PUT` y no
`POST`.

Las dos operaciones son **idempotentes** y responden `204` sin cuerpo: seguir a
quien ya se sigue no es un conflicto, y dejar de seguir a quien no se sigue
tampoco, porque en ambos casos el estado final es el que se pidió. Responder
`409` obligaría a la interfaz a tratar como error una pulsación repetida, que
sobre un teléfono con conexión intermitente es un caso frecuente.

Seguirse a uno mismo responde `422`; un handle inexistente, `404`.

**Seguir a alguien no le notifica.** El enunciado define la notificación como
un aviso de actividad nueva, y un seguimiento no es actividad.

El estado aparece en el perfil bajo `viewer`, en las dos direcciones, y en cada
resultado de la búsqueda bajo `following`.

[↑ Índice](#índice)

---

## 14. Seguir y dejar de seguir restaurantes

> El usuario decide de qué restaurantes quiere enterarse, y puede revertir esa
> decisión. Recibe notificaciones cuando se publica actividad relevante en
> torno a ellos. Si una misma actividad está relacionada tanto con una persona
> como con un restaurante que sigue, recibe una sola notificación.

| Método y path | Resultado |
| --- | --- |
| `PUT /api/v1/restaurants/{id}/follow` | Sigue el restaurante. `204`. |
| `DELETE /api/v1/restaurants/{id}/follow` | Deja de seguirlo. `204`. |

Misma forma que seguir a una persona: `PUT` y `DELETE` sobre un subrecurso,
idempotentes, `204` sin cuerpo. **La interfaz escribe un botón y no dos.** Un
identificador inexistente responde `404`. El estado aparece en la ficha bajo
`viewer.following`.

Seguir un restaurante no notifica a nadie. Lo que hace es **cambiar de qué se
entera esa persona**: la actividad pública publicada ahí pasa a producirle un
aviso.

### Las notificaciones no son un endpoint

**El backend resuelve a quién corresponde avisar; enviar es del emisor de Web
Push de cada grupo**, que vive en el mismo proceso. Un endpoint que respondiera
«quiénes deben enterarse de esto» publicaría el grafo de seguidores a
cualquiera con sesión.

El enganche es único y está en `app/services/notifications.py`. Ahí se conecta
el emisor del grupo, y desde ahí llega el aviso de las tres clases que avisan:
visitas, fotografías y evaluaciones.

Cuatro reglas que la interfaz tiene que conocer porque determinan lo que el
usuario verá:

1. **Una entrada del feed, un aviso.** Quien sigue al autor **y** al
   restaurante es un destinatario, no dos: la deduplicación ocurre en la
   consulta, no concatenando listas.
2. **El autor nunca se avisa a sí mismo.**
3. **Sólo la actividad pública avisa.** Una privada no produce destinatarios.
4. **Reseñar no avisa.** Es la única clase de actividad que no lo hace: la
   fotografía de la que habla ya avisó cuando se publicó, y el feed muestra a
   ambas como una sola entrada. Un segundo aviso contradiría lo que el
   seguidor va a ver al abrirlo. Comentar tampoco avisa, porque un comentario
   no es actividad ([épica 17](#17-comentar-fotografías)).

El aviso de un grupo de fotografías lo dispara la primera del grupo, y el
identificador que viaja es el del grupo.

[↑ Índice](#índice)

---

## 15. Ver el feed

> El usuario ve, en orden cronológico, la actividad reciente de las personas
> que sigue y la actividad publicada en torno a los restaurantes que sigue.
> Una misma actividad aparece una sola vez, aunque coincida con más de un
> criterio de seguimiento.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `GET /api/v1/feed` | 1–50, def. 20 | La actividad de lo que la sesión sigue, por cursor. |

### El envelope de actividad

Lo comparten el feed y el perfil. Cada item declara su `type`, sus dos
instantes, y lleva el objeto **bajo una clave llamada como su `type`**:

```json
{
  "items": [
    {
      "type": "review",
      "occurred_at": "2026-08-18T12:00:00Z",
      "published_at": "2026-08-18T12:00:00Z",
      "review": { "id": "…", "dish_name": "…", "rating": 4, "text": "…",
                  "visibility": "public", "author": { … }, "restaurant": { … },
                  "photo": { "id": "…", "content_url": "…", "caption": null },
                  "created_at": "…", "updated_at": "…" }
    }
  ],
  "next_cursor": null
}
```

Hay **cuatro clases**: `review`, `visit`, `photo` y `evaluation`. Un cliente
que recorre la lista distingue por `type` y no necesita saber cuáles existen:

```js
const object = item[item.type];
```

**El item de tipo `photo` lleva una colección de fotografías**, en
`photo.photos`, porque la épica 9 publica varias en un mismo acto y las
presenta como una sola actividad. Trátalo siempre como colección, aunque traiga
una.

**Los dos instantes son distintos y las dos vistas ordenan por uno distinto.**
`occurred_at` es cuándo ocurrió; `published_at`, cuándo se publicó. Para una
reseña coinciden. Para una visita no tienen por qué: **el feed ordena por
`published_at`**, de modo que registrar hoy una visita de hace un mes aparezca
arriba en el feed de quienes siguen a su autor y no enterrada donde nadie la
verá. El perfil ordena por `occurred_at`, que es la cronología de esa persona.

### Qué contiene y qué no

* **Sólo actividad pública.** Ninguna privada, de nadie.
* **Una actividad aparece una sola vez**, aunque coincida por autor y por
  restaurante.
* **Una fotografía reseñada aparece como reseña**, no dos veces; un grupo de
  fotografías aparece una vez.
* **No incluye la actividad del propio usuario**, ni siquiera la publicada en
  un restaurante que sigue. Un feed es aquello de lo que uno se entera, y nadie
  se entera de lo que acaba de publicar; su actividad propia la consulta en su
  perfil. Es la misma regla que rige las notificaciones.
* **No ofrece filtros** por clase de actividad ni por restaurante: el enunciado
  pide una vista cronológica única, y un filtro convierte el cursor en una
  familia de cursores que hay que invalidar cuando el filtro cambia.
* **No tiene antigüedad máxima**: «actividad reciente» es el orden, no un
  recorte, y quien sigue a poca gente debe poder llegar al final de su feed.

Un feed sin nada que mostrar responde `200` con lista vacía y sin cursor, que
la interfaz debe distinguir de un error. Seguir o dejar de seguir cambia el
contenido en la consulta siguiente.

[↑ Índice](#índice)

---

## 16. Ver visitas de personas conocidas en un restaurante

> Al mirar la ficha de un restaurante, el usuario ve si alguna de las personas
> que sigue estuvo ahí alguna vez, y cuándo, siempre que esas visitas sean
> públicas.

No tiene endpoint propio: es el bloque `known_visitors` de
`GET /api/v1/restaurants/{id}`.

```json
{
  "total": 2,
  "items": [
    { "id": "…", "handle": "demo2", "name": "…", "nationality": { … },
      "last_visit_at": "2026-08-19T20:00:00Z" }
  ]
}
```

Cada item es el [resumen de persona](#formas-compartidas) más `last_visit_at`,
la fecha de su visita pública más reciente a ese restaurante.

Va dentro de la ficha y no en un endpoint aparte porque **está acotado de
antemano**: su costo no crece con el historial del restaurante ni con el número
de personas que el observador sigue. Es la diferencia con la galería.

* **Cuenta personas, no visitas.** Quien fue diez veces aparece una vez, con la
  última; de otro modo una sola persona llenaría el bloque.
* **Sólo visitas públicas**, y ni siquiera para su autor: el bloque habla de lo
  que alguien eligió dar a conocer.
* **No incluye las visitas del propio observador** —nadie se sigue a sí mismo—
  ni las de quienes no sigue, aunque sean públicas y en ese mismo restaurante.
* **No se pagina.** Orden por `last_visit_at` descendente, lista cortada en
  diez. **`total` cuenta a todas las personas**, de modo que una lista cortada
  igual dice cuántas hay y la interfaz escriba «y N más».

Para un observador que no sigue a nadie que haya estado ahí, `total` es cero y
`items` viene vacío: es un estado del bloque y no su ausencia. Dejar de seguir
a alguien lo retira en la consulta siguiente.

[↑ Índice](#índice)

---

## 17. Comentar fotografías

> Los usuarios conversan en torno a una fotografía pública, respondiéndose
> entre sí en un thread de comentarios.

| Método y path | `limit` | Resultado |
| --- | --- | --- |
| `POST /api/v1/photos/{id}/comments` | — | Escribe o responde. `201` y publica `Location`. |
| `GET /api/v1/photos/{id}/comments` | 1–50, def. 20 | La conversación, por cursor. |
| `GET /api/v1/comments/{id}/replies` | 1–50, def. 20 | Las respuestas de un comentario, por cursor. |

### Escribir

```json
{ "text": "¿Las sirven todo el día?", "parent_id": null }
```

`text` admite hasta 1000 caracteres y se recorta antes de guardarse; en blanco
o más largo responde `422`. `parent_id` ausente o `null` escribe un comentario
de la conversación; presente, una respuesta.

**El thread tiene dos niveles.** Responder a una respuesta **se acepta**, y el
comentario queda colgado del comentario de primer nivel al que esa respuesta
pertenece; nunca se abre un tercer nivel. Un `parent_id` inexistente o de otra
fotografía responde `422`.

**Sólo se comenta una fotografía pública.** Una privada ajena responde `404`,
indistinguible de una que no existe; una privada propia responde `422`, porque
existe y lo que le falta no es permiso sino audiencia. El autor de la
fotografía puede comentar la suya: es parte de la conversación, no una
excepción.

**El comentario no tiene visibilidad propia**: vive sobre una fotografía
pública y es público.

### Leer

`GET /api/v1/photos/{id}/comments` responde `{ items, next_cursor }` con los
comentarios de primer nivel, **del más reciente al más antiguo**, que es por
donde una pantalla abre:

```json
{
  "comment": { "id": "…", "photo_id": "…", "parent_id": null,
               "author": { … }, "text": "…", "created_at": "…" },
  "reply_count": 4,
  "replies": [ { … }, { … }, { … } ]
}
```

Cada item trae `reply_count` y sus **primeras tres respuestas, de la más
antigua a la más reciente**, porque una conversación se lee hacia adelante. Así
la pantalla dibuja el thread **sin una solicitud por comentario**. Las
restantes se piden en `GET /api/v1/comments/{id}/replies`, que pagina en ese
mismo orden ascendente.

Los dos órdenes son distintos a propósito, y no es una inconsistencia.

Una fotografía sin comentarios responde una lista vacía, que no es un error. Un
comentario que no existe responde `404`; uno que existe y nadie respondió, una
lista vacía.

Los metadatos de una fotografía y cada tarjeta de la galería traen
`comments_count`, **la conversación completa, respuestas incluidas**, para que
la interfaz decida si ofrece la entrada al thread.

### Lo que un comentario no hace

**No es actividad.** No aparece en el feed, no aparece en el perfil de su autor
y **no produce ningún aviso**, ni siquiera a quien publicó la fotografía. El
enunciado enumera como actividad la visita, la fotografía, la reseña y la
evaluación, y define la conversación aparte. Un thread de veinte mensajes
inundaría el feed de todos los que siguen a cualquiera de los que hablan.

**No hay edición, eliminación ni moderación**, en línea con el resto de la API.
Es la evolución evidente para un despliegue real.

[↑ Índice](#índice)

---

## Fuera de las épicas

Dos cosas que el backend expone y que ninguna épica pide.

### CRUD de restaurantes

| Método y path | Resultado |
| --- | --- |
| `PATCH /api/v1/restaurants/{id}` | Modifica únicamente los campos presentes. |
| `DELETE /api/v1/restaurants/{id}` | Elimina el recurso. `204`. |

Existen desde la entrega 2, cuando el recurso de restaurantes era el ejercicio
de CRUD protegido. `PATCH` acepta cualquier subconjunto de `name`, `address`,
`latitude`, `longitude` y `cuisine_styles`, y rechaza un cuerpo vacío o un
campo en `null`; cambiar el nombre o la dirección hacia una combinación que ya
existe responde `409`, igual que al crear.

> **En esta base docente cualquier usuario autenticado puede modificar o
> eliminar cualquier restaurante.** Esa simplificación permite practicar el
> CRUD, pero **no es un modelo de autorización apropiado para producción**:
> roles, ownership y moderación quedan para una evolución posterior.

### Salud del servicio

`GET /healthz` responde `200` sin sesión. Lo usa el contenedor y el
procedimiento de despliegue; no es parte del contrato de la aplicación.

[↑ Índice](#índice)
