# Proyecto de Aplicaciones Móviles — Enunciado General del Proyecto

Durante este semestre, el proyecto del curso consistirá en el desarrollo de una aplicación móvil para _foodies_ y sibaritas viajeros: una red social gastronómica en la que las personas descubren restaurantes donde quiera que estén, registran sus visitas, publican fotografías de los platos que probaron, escriben reseñas y evalúan los restaurantes que conocen.

La aplicación se articula en torno a tres ideas:

* **Descubrir**: encontrar dónde comer, sea buscando un restaurante por su nombre, explorando un mapa, o preguntando qué hay cerca de mí de un cierto estilo de comida.
* **Registrar**: dejar constancia de las visitas y de lo que se comió, con fotografías de los platos y del menú, reseñas y evaluaciones.
* **Compartir**: seguir a otras personas cuyo criterio gastronómico interesa, ver su actividad, conversar en torno a las fotografías y saber si alguien de confianza ya estuvo en el restaurante que estoy mirando.

El valor de la aplicación está en la combinación de las tres: el descubrimiento se enriquece con lo que ha registrado la comunidad, y en particular con lo que han registrado las personas que cada usuario decidió seguir.

Cada grupo deberá definir un nombre para su aplicación, el cual ciertamente deberá respetar la moral y las buenas costumbres.

## Conceptos del Dominio

Para entender la funcionalidad descrita más adelante, conviene fijar el significado de los conceptos centrales de la aplicación. Este es un modelo conceptual: no prescribe cómo se almacenará la información.

* **Usuario**: Una persona registrada en la aplicación. Se identifica públicamente por un _handle_ único, a la usanza de las redes sociales (p. ej., `@sibarita`), y tiene un perfil con su nombre y nacionalidad.
* **Restaurante**: Un establecimiento gastronómico, con nombre, dirección, ubicación geográfica y uno o más estilos de comida. Es el objeto en torno al cual gira toda la actividad de la aplicación.
* **Estilo de comida**: La categoría gastronómica que caracteriza a un restaurante (peruana, japonesa, italiana, vegetariana, etc.). Un restaurante puede tener más de una.
* **Visita** (_check-in_): El registro de que un usuario estuvo en un restaurante en un momento determinado.
* **Plato**: Una preparación ofrecida por un restaurante. Es aquello sobre lo que los usuarios publican fotografías y opinan.
* **Fotografía**: Una imagen publicada por un usuario en un restaurante. Puede ser la foto de un plato o la foto del menú del establecimiento.
* **Reseña**: La opinión de un usuario sobre un plato, expresada con una calificación y un texto, a propósito de una fotografía publicada.
* **Comentario**: La conversación que se produce en torno a una fotografía. Los comentarios pueden responder a otros comentarios, formando un _thread_.
* **Etiqueta**: La mención de un usuario en una fotografía, para indicar que estuvo ahí o que la publicación le concierne.
* **Evaluación**: La valoración que un usuario hace de un restaurante como un todo. Considera varios criterios (por ejemplo, comida, servicio, ambiente y relación precio/calidad) y un comentario general.
* **Seguimiento**: La decisión de un usuario de seguir a otro para enterarse de su actividad. Es una relación dirigida: seguir a alguien no implica ser seguido de vuelta.
* **Feed**: La vista cronológica de la actividad reciente de las personas que un usuario sigue.

## Funcionalidad de la Aplicación

La funcionalidad a desarrollar se organiza en las siguientes épicas. En las entregas sucesivas se irá solicitando implementar funcionalidad relativa a estas épicas, con mayor detalle sobre las funciones específicas y su alcance en cada una.

### Cuenta y perfil

1. **Registro e inicio de sesión**: Una persona puede crear una cuenta indicando su nombre, correo electrónico, _handle_ y nacionalidad, y luego autenticarse para usar la aplicación.
2. **Perfil de usuario**: Cada usuario tiene un perfil que reúne su actividad pública —visitas, fotografías, reseñas y evaluaciones— y que otros usuarios pueden consultar.

### Descubrimiento de restaurantes

3. **Buscar restaurante por nombre**: El usuario busca un restaurante escribiendo su nombre y accede a su ficha desde los resultados.
4. **Explorar restaurantes en el mapa**: El usuario recorre libremente un mapa interactivo, desplazándose y acercándose sobre la zona que le interesa, y ve los restaurantes disponibles en ella.
5. **Buscar por estilo de comida y cercanía**: El usuario busca restaurantes de un cierto estilo de comida a menos de una distancia dada desde donde se encuentra, y ve los resultados sobre el mapa y en una lista ordenada por distancia.
6. **Ver un restaurante**: El usuario consulta la ficha de un restaurante: su información básica, sus estilos de comida, las fotografías de platos y de menú publicadas por la comunidad, y el resumen de sus evaluaciones.

### Registro de la experiencia

7. **Hacer check-in en un restaurante**: El usuario registra que está o estuvo en un restaurante.
8. **Publicar la foto de un plato**: El usuario sube la fotografía de un plato que probó, identificando de qué plato se trata.
9. **Publicar la foto del menú**: El usuario sube la fotografía del menú de un restaurante, de modo que la comunidad conozca su oferta y sus precios.
10. **Reseñar un plato**: El usuario añade una reseña a la fotografía de un plato, con una calificación y un texto que describe su experiencia.
11. **Evaluar un restaurante**: El usuario califica un restaurante en varios criterios de evaluación y agrega un comentario general. La aplicación muestra el resumen de las evaluaciones recibidas por cada restaurante.

### Interacción social

12. **Buscar usuarios por handle**: El usuario encuentra a otras personas por su _handle_ y llega a su perfil.
13. **Seguir y dejar de seguir usuarios**: El usuario decide de quiénes quiere enterarse, y puede revertir esa decisión.
14. **Ver el feed**: El usuario ve, en orden cronológico, la actividad reciente de las personas que sigue.
15. **Ver visitas de personas conocidas en un restaurante**: Al mirar la ficha de un restaurante, el usuario ve si alguna de las personas que sigue estuvo ahí alguna vez, y cuándo.
16. **Comentar fotografías**: Los usuarios conversan en torno a una fotografía, respondiéndose entre sí en un _thread_ de comentarios.
17. **Etiquetar usuarios en fotografías**: El usuario menciona a otras personas en las fotografías de platos o de menús que publica.

## Alcances del Desarrollo

* El proyecto se desarrolla por etapas, en entregas sucesivas. **No se espera implementar toda la funcionalidad anterior de una vez**: cada entrega tendrá su propio enunciado, en el directorio `docs`, que precisará qué se debe construir, con qué nivel de detalle y bajo qué criterios será evaluado.
* La evolución del proyecto a lo largo del semestre es la siguiente:

  1. **Diseño (entrega 1)**: diseño completo de la aplicación en Figma. El enunciado general que están leyendo es el insumo para ese diseño: define qué hace la aplicación, no cómo se ve ni cómo se implementa.
  2. **Primera aplicación funcional (entrega 2)**: desarrollo de una PWA (_Progressive Web Application_) que consume los _endpoints_ de un backend. El backend, con persistencia en DynamoDB, les será entregado; el trabajo del grupo está en el lado del cliente. Las vistas de esta entrega se construyen con HTML simple, para concentrar el esfuerzo en el consumo de la API y en las capacidades de una PWA.
  3. **Frontend completo (entrega 3)**: desarrollo completo del frontend de la aplicación usando React, sobre el diseño elaborado en la entrega 1.
  4. **Backend serverless (entrega 4)**: migración del backend monolítico a una arquitectura _serverless_ sobre AWS Lambda, con foco en la escalabilidad de la aplicación.
* La información se persiste en **DynamoDB**, una base de datos NoSQL. Esto tiene consecuencias importantes sobre cómo se modela la información: el diseño de los datos se hace en función de los patrones de acceso de la aplicación, y no siguiendo la normalización propia de las bases de datos relacionales. La mayor parte del trabajo de implementación del backend, incluyendo la capa de datos, será proporcionado en el código base próximamente.
* Las épicas de **mapa y cercanía** (4 y 5) se apoyan en servicios externos de mapas y lugares, como Google Maps Platform, para desplegar el mapa, buscar establecimientos y obtener la posición del usuario. Estos servicios requieren claves de API y están sujetos a cuotas, por lo que el alcance final de estas épicas se precisará según su factibilidad. En caso de restricciones, se acordará una alternativa acotada a los restaurantes ya registrados en la aplicación.
* El **contenido multimedia** se limita a fotografías. No se contempla video.

## Estructura del repositorio

```
docs/        Enunciados de las entregas y documentación del proyecto.
frontend/    Aplicación cliente: la PWA de la entrega 2 y el frontend React de la entrega 3.
backend/     Aplicación de backend, que será provista por el equipo docente.
```

El directorio `backend` se incorporará al código base cuando comience la entrega 2.

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
