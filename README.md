# Proyecto de Aplicaciones Móviles — Enunciado General del Proyecto

Durante este semestre, el proyecto del curso consistirá en el desarrollo de una aplicación móvil para _foodies_ y sibaritas viajeros: una red social gastronómica en la que las personas descubren restaurantes donde quiera que estén, registran sus visitas, publican fotografías de los platos que probaron, escriben reseñas y evalúan los restaurantes que conocen.

La aplicación se articula en torno a tres ideas:

* **Descubrir**: encontrar dónde comer, sea buscando un restaurante por su nombre, explorando un mapa, o preguntando qué hay cerca de mí de un cierto estilo de comida.
* **Registrar**: dejar constancia de las visitas y de lo que se comió, con fotografías de los platos, del menú y de las instalaciones, reseñas y evaluaciones.
* **Compartir**: seguir a otras personas cuyo criterio gastronómico interesa y a restaurantes de interés, ver su actividad, conversar en torno a las fotografías y saber si alguien de confianza ya estuvo en el restaurante que estoy mirando.

El valor de la aplicación está en la combinación de las tres: el descubrimiento se enriquece con lo que ha registrado la comunidad, y en particular con lo que han registrado las personas que cada usuario decidió seguir.

Cada grupo deberá definir un nombre para su aplicación, el cual ciertamente deberá respetar la moral y las buenas costumbres.

## Conceptos del Dominio

Para entender la funcionalidad descrita más adelante, conviene fijar el significado de los conceptos centrales de la aplicación. Este es un modelo conceptual: no prescribe cómo se almacenará la información.

* **Usuario**: Una persona registrada en la aplicación. Se identifica públicamente por un _handle_ único, a la usanza de las redes sociales (p. ej., `@sibarita`), y tiene un perfil con su nombre y nacionalidad.
* **Restaurante**: Un establecimiento gastronómico, con nombre, dirección, ubicación geográfica y uno o más estilos de comida. Es el objeto en torno al cual gira toda la actividad de la aplicación.
* **Estilo de comida**: La categoría gastronómica que caracteriza a un restaurante (peruana, japonesa, italiana, vegetariana, etc.). Un restaurante puede tener más de una.
* **Visita** (_check-in_): El registro de que un usuario estuvo en un restaurante en un momento determinado.
* **Plato**: Una preparación ofrecida por un restaurante. Es aquello sobre lo que los usuarios publican fotografías y opinan.
* **Fotografía**: Una imagen publicada por un usuario en un restaurante. Puede mostrar un plato, el menú o las instalaciones del establecimiento. Las fotografías pueden recibir comentarios. Cada reseña de un plato se asocia a una sola fotografía; una evaluación de un restaurante puede asociarse a una o más fotografías de su menú o sus instalaciones.
* **Reseña**: La opinión de un usuario sobre un plato, expresada con una calificación y un texto, a propósito de una única fotografía publicada.
* **Comentario**: La conversación que se produce en torno a una fotografía. Los comentarios pueden responder a otros comentarios, formando un _thread_.
* **Evaluación**: La valoración que un usuario hace de un restaurante como un todo. Considera varios criterios (por ejemplo, comida, servicio, ambiente y relación precio/calidad) y un comentario general. Puede asociarse a una o más fotografías del menú o de las instalaciones.
* **Seguimiento**: La decisión de un usuario de seguir a otra persona o a un restaurante para enterarse de la actividad que publica. Seguir a una persona es una relación dirigida: seguirla no implica ser seguido de vuelta.
* **Feed**: La vista cronológica de la actividad reciente de las personas que un usuario sigue y de la actividad publicada en torno a los restaurantes que sigue.
* **Actividad pública**: Una visita, fotografía, reseña o evaluación que el usuario decide compartir con la comunidad. Puede aparecer en su perfil público, en el _feed_ y en las fichas de los restaurantes correspondientes.
* **Actividad privada**: Una visita, fotografía, reseña o evaluación que el usuario decide conservar solo para sí. Puede consultarla desde su propio perfil, pero no es visible para otros usuarios ni se incorpora al _feed_ o a la actividad pública de un restaurante.
* **Notificación**: Un aviso de actividad nueva relacionada con una persona o un restaurante que el usuario sigue. Una misma actividad debe producir un único aviso, aunque sea relevante por más de una relación de seguimiento.

## Funcionalidad de la Aplicación

La funcionalidad a desarrollar se organiza en las siguientes épicas. En las entregas sucesivas se irá solicitando implementar funcionalidades relativas a estas épicas, con mayor detalle sobre las funciones específicas y su alcance en cada una.

### Cuenta y perfil

1. **Registro e inicio de sesión**: Una persona puede crear una cuenta indicando su nombre, correo electrónico, _handle_ y nacionalidad, y luego autenticarse para usar la aplicación.
2. **Perfil de usuario**: Cada usuario tiene un perfil con su _handle_, nombre y nacionalidad. Al consultar su propio perfil, ve tanto su actividad pública como su actividad privada —visitas, fotografías, reseñas y evaluaciones—; cuando otro usuario consulta ese mismo perfil, solo ve sus datos públicos y la actividad que decidió compartir.

### Descubrimiento de restaurantes

3. **Buscar o crear un restaurante**: El usuario busca un restaurante escribiendo su nombre y accede a su ficha desde los resultados. Si no existe, puede crearlo indicando su nombre, dirección y estilos de comida. Antes de crear el registro, la aplicación debe prevenir duplicados mediante comprobaciones mínimas, como verificar que no exista otro restaurante con el mismo nombre y dirección, para que la información aportada por distintos usuarios se agrupe en una única ficha.
4. **Explorar restaurantes en el mapa**: El usuario recorre libremente un mapa interactivo, desplazándose y acercándose sobre la zona que le interesa, y ve los restaurantes disponibles en ella.
5. **Buscar por estilo de comida y cercanía**: El usuario busca restaurantes de un cierto estilo de comida a menos de una distancia dada desde donde se encuentra, y ve los resultados sobre el mapa y en una lista ordenada por distancia.
6. **Ver un restaurante**: El usuario consulta la ficha de un restaurante: su información básica, sus estilos de comida, las fotografías de platos, menús e instalaciones publicadas por la comunidad, y el resumen de sus evaluaciones.

### Registro de la experiencia

Al registrar una actividad, el usuario decide si será pública o privada. La visibilidad elegida determina quién podrá verla y si se incorporará al _feed_, a las notificaciones y a la actividad pública del restaurante correspondiente.

7. **Hacer check-in en un restaurante**: El usuario registra que está o estuvo en un restaurante.
8. **Publicar la foto de un plato**: El usuario sube la fotografía de un plato que probó, identificando de qué plato se trata.
9. **Publicar fotos del menú o de las instalaciones**: El usuario sube una o más fotografías del menú o de los espacios de un restaurante, de modo que la comunidad conozca su oferta, sus precios y sus instalaciones.
10. **Reseñar un plato**: El usuario añade una reseña a la fotografía de un plato, con una calificación y un texto que describe su experiencia. Cada reseña se asocia exactamente a una fotografía del plato.
11. **Evaluar un restaurante**: El usuario califica un restaurante en varios criterios de evaluación y agrega un comentario general. Puede asociar a la evaluación una o más fotografías del menú o de las instalaciones. La aplicación muestra el resumen de las evaluaciones recibidas por cada restaurante.

### Interacción social

12. **Buscar usuarios por handle**: El usuario encuentra a otras personas por su _handle_ y llega a su perfil.
13. **Seguir y dejar de seguir usuarios**: El usuario decide de quiénes quiere enterarse mediante su _feed_ y sus notificaciones, y puede revertir esa decisión.
14. **Seguir y dejar de seguir restaurantes**: El usuario decide de qué restaurantes quiere enterarse, y puede revertir esa decisión. Recibe notificaciones cuando se publica actividad relevante en torno a ellos. Si una misma actividad está relacionada tanto con una persona como con un restaurante que sigue, recibe una sola notificación.
15. **Ver el feed**: El usuario ve, en orden cronológico, la actividad reciente de las personas que sigue y la actividad publicada en torno a los restaurantes que sigue. Una misma actividad aparece una sola vez, aunque coincida con más de un criterio de seguimiento.
16. **Ver visitas de personas conocidas en un restaurante**: Al mirar la ficha de un restaurante, el usuario ve si alguna de las personas que sigue estuvo ahí alguna vez, y cuándo, siempre que esas visitas sean públicas.
17. **Comentar fotografías**: Los usuarios conversan en torno a una fotografía pública, respondiéndose entre sí en un _thread_ de comentarios.

## Alcances del Desarrollo

* El proyecto se desarrolla por etapas, en entregas sucesivas. **No se espera implementar toda la funcionalidad anterior de una vez**: cada entrega tendrá su propio enunciado, en el directorio `docs`, que precisará qué se debe construir, con qué nivel de detalle y bajo qué criterios será evaluado.
* La evolución del proyecto a lo largo del semestre es la siguiente:

  1. **Diseño (entrega 1)**: diseño completo de la aplicación en Figma. El enunciado general que están leyendo es el insumo para ese diseño: define qué hace la aplicación, no cómo se ve ni cómo se implementa.
  2. **Prueba de concepto (entrega 2)**: desarrollo de una PWA (_Progressive Web Application_) que consume los _endpoints_ de un backend monolítico. Las vistas se construyen con HTML simple, para concentrar el esfuerzo en el consumo de la API y en las capacidades propias de una PWA: _manifest_, _service worker_ y notificaciones.
  3. **Frontend completo (entrega 3)**: desarrollo completo del frontend de la aplicación usando React, sobre el diseño elaborado en la entrega 1 y las capacidades de PWA desarrolladas en la entrega 2.
  4. **Backend serverless (entrega 4)**: migración del backend monolítico a una arquitectura _serverless_ sobre AWS Lambda, con foco en la escalabilidad de la aplicación.
* La información se persiste en **PostgreSQL**. Esta elección permitirá migrar con mayor facilidad la capa de datos a **Aurora DSQL**, un servicio distribuido y _serverless_ compatible con consultas PostgreSQL, durante la entrega 4.
* Las épicas de **mapa y cercanía** (4 y 5) se apoyan en servicios externos de mapas y lugares, como Google Maps Platform, para desplegar el mapa, buscar establecimientos y obtener la posición del usuario. Estos servicios requieren claves de API y están sujetos a cuotas, por lo que el alcance final de estas épicas se precisará según su factibilidad. En caso de restricciones, se acordará una alternativa acotada a los restaurantes ya registrados en la aplicación.
* El **contenido multimedia** se limita a fotografías. No se contempla video.

## Estructura del repositorio

```text
docs/        Enunciados de las entregas.
frontend/    Aplicación cliente: la PWA de la entrega 2 y el frontend React de la entrega 3.
backend/     API REST, backend serverless y su documentación técnica.
gateway/     Proxy nginx para servir frontend y API bajo un mismo origen local.
```

La documentación técnica para ejecutar, probar y desplegar la API comienza en
[backend/README.md](backend/README.md). El punto de partida del cliente y su
contrato de paths están en [frontend/README.md](frontend/README.md). La
arquitectura interna y las convenciones para extender la API se explican en
[backend/DEVELOPER.md](backend/DEVELOPER.md).

## Uso del repositorio

Cada grupo de proyecto trabaja en su propio repositorio de GitHub, creado por el equipo docente. Para obtenerlo, cada grupo debe registrarse en un formulario que será anunciado por Canvas, indicando los nombres de usuario de GitHub de todos sus integrantes. Con esa información, el equipo docente creará los repositorios y enviará las invitaciones correspondientes, de modo que cada integrante recibirá una invitación en la cuenta de GitHub que haya declarado. Es importante que los nombres de usuario informados sean correctos, ya que las invitaciones se generan automáticamente a partir del formulario.

Una vez aceptada la invitación, los grupos podrán crear libremente ramas locales y remotas para avanzar en el desarrollo de su aplicación. Sin embargo,

* Se considerará que la rama `main` contiene el último código estable que será revisado y evaluado por el ayudante.
* Pueden usar _issues_ de GitHub en su repositorio para mantener registro de bugs, o _features_ que requieran implementar.
* Para las entregas, antes de la fecha límite, deben crear un _pull request_ e incluir al ayudante de proyecto que tengan asignado. El _pull request_ puede ser creado sin requerir una mezcla de código. Más bien, su fin es que el ayudante pueda revisar el trabajo y dejar su evaluación de cada aspecto en la entrega. El título del _pull request_ debe decir "Revisión Entrega X", en donde X es el número de la entrega.

Los profesores del curso continuarán trabajando sobre el repositorio con el código base durante el semestre, tanto para remediar posibles bugs como para proveer nuevas funciones relevantes para alguna de las entregas. Para que los grupos puedan actualizar su repositorio con nuevos lanzamientos del código base, deben agregar el repositorio de los profesores como origen remoto adicional:

```sh
git remote add upstream https://github.com/ICC4203-202620/project-base.git
```

Luego, para aplicar en el repositorio local los cambios que se encuentren en dicho repositorio:

```sh
git fetch upstream
git merge upstream/main --allow-unrelated-histories
```
