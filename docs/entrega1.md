# Entrega 1 — Diseño de la Aplicación en Figma

En esta primera entrega, cada grupo debe producir el **diseño completo de la aplicación** descrita en el [enunciado general del proyecto](../README.md), en forma de un prototipo interactivo construido en Figma.

El énfasis de la entrega está en el diseño de la experiencia y de la interfaz, no en la programación: el resultado es un prototipo navegable que permita recorrer la aplicación completa y entender cómo se resuelve cada una de las épicas. Este prototipo será el insumo directo del desarrollo del frontend en las entregas siguientes, en particular de la entrega 3, en que la aplicación se implementa con React.

## Antes de comenzar: obtener una cuenta de Figma

**Este es el primer paso y no debe dejarse para el final.** Figma ofrece acceso gratuito a estudiantes y docentes a través de su programa educativo, que habilita funcionalidades necesarias para el trabajo en equipo y el prototipado.

* Postulen a la cuenta educativa en https://www.figma.com/education/, usando su correo institucional.
* La verificación de la cuenta puede tardar algunos días y en ocasiones requiere adjuntar un comprobante de alumno regular. Háganlo apenas comience la entrega, para no perder tiempo de trabajo.
* Todos los integrantes del grupo deben tener su cuenta, de modo que puedan trabajar sobre el mismo archivo de diseño.

## Herramientas y biblioteca de componentes

El diseño debe construirse utilizando la **biblioteca de componentes de MUI para Figma, basada en Material Design**, que se presentará en la clase 2 y en el laboratorio 1.

El uso de esta biblioteca no es una formalidad: los componentes de MUI en Figma tienen una correspondencia directa con los componentes de React que ustedes utilizarán al implementar el frontend en la entrega 3. Diseñar con estos componentes reduce la distancia entre el diseño y el código, y evita que el prototipo proponga interfaces que después resulten costosas o imposibles de construir.

Por lo mismo, se espera que:

* Usen los componentes de la biblioteca en lugar de dibujar controles a mano (botones, campos de texto, listas, _app bars_, _bottom navigation_, _cards_, diálogos, etc.).
* Respeten las convenciones de Material Design en tipografía, espaciado, iconografía y jerarquía visual.
* Definan y usen consistentemente estilos propios del proyecto (paleta de colores y tipografías) sobre la base del sistema, en lugar de improvisar valores pantalla por pantalla.

## Alcance del diseño

El prototipo debe cubrir **todas las épicas** listadas en la sección "Funcionalidad de la Aplicación" del enunciado general, agrupadas en:

* Cuenta y perfil: registro, inicio de sesión y perfil de usuario.
* Descubrimiento de restaurantes: búsqueda por nombre, exploración en el mapa, búsqueda por estilo de comida y cercanía, y ficha del restaurante.
* Registro de la experiencia: _check-in_, publicación de fotos de platos y de menú, reseña de un plato y evaluación de un restaurante.
* Interacción social: búsqueda de usuarios por _handle_, seguir y dejar de seguir, _feed_, visitas de personas conocidas en un restaurante, comentarios en fotografías y etiquetado de usuarios.

El diseño debe ser **móvil**: las pantallas se diseñan para el tamaño de un teléfono, con la navegación, los tamaños de área táctil y las convenciones propias de una aplicación móvil. Recuerden que la aplicación se implementará primero como una PWA y luego con React, siempre en el contexto de un dispositivo móvil.

Además de las pantallas principales, el diseño debe hacerse cargo de los estados que hacen usable una aplicación real: estados vacíos (por ejemplo, un _feed_ sin actividad o una búsqueda sin resultados), estados de carga, y mensajes de error o de confirmación.

## Interactividad esperada

El prototipo debe ofrecer **interactividad básica**, entendida como:

1. **Navegación completa**: debe ser posible recorrer la aplicación de extremo a extremo desde el prototipo, sin callejones sin salida. Toda pantalla debe ser alcanzable desde algún flujo, y debe permitir volver.
2. **Interacción con elementos de formulario**: los campos de texto, selectores, controles de calificación y botones de los formularios deben responder a la interacción, mostrando por ejemplo el estado de un campo enfocado, una opción seleccionada o una calificación asignada.
3. **Flujos completos**: las acciones principales deben poder ejecutarse de principio a fin en el prototipo. Por ejemplo, buscar un restaurante, entrar a su ficha, hacer _check-in_, subir la foto de un plato y publicar su reseña.

No se espera lógica de negocio, datos reales ni animaciones sofisticadas. Sí se espera que una persona ajena al grupo pueda tomar el prototipo y usar la aplicación sin explicaciones adicionales.

## Formato de la entrega

* El trabajo se realiza en un único archivo de Figma compartido por el grupo.
* El archivo debe estar organizado de manera comprensible: páginas o secciones por grupo de épicas, _frames_ con nombres significativos, y una pantalla inicial que sirva de punto de partida del prototipo.
* En el repositorio del grupo, agreguen un documento `docs/entrega1-diseno.md` que contenga:
  * El nombre de la aplicación definido por el grupo.
  * El enlace al archivo de Figma y al prototipo, con permisos de visualización habilitados para el equipo docente.
  * Los nombres de los integrantes del grupo.
  * Un breve mapa que indique, para cada épica del enunciado general, en qué pantallas del prototipo se resuelve.
* Antes de la fecha límite, creen un _pull request_ titulado "Revisión Entrega 1", incluyendo al ayudante de proyecto asignado, según lo indicado en la sección "Uso del repositorio" del enunciado general.

**Verifiquen los permisos del enlace de Figma antes de entregar.** Un prototipo al que el ayudante no puede acceder no puede ser evaluado.

## Criterios de Evaluación

La entrega se evaluará según los siguientes criterios:

| Criterio | Ponderación | Qué se evalúa |
| --- | --- | --- |
| **Cobertura de requisitos** | 40% | Que el prototipo aborde todas las épicas del enunciado general, que los flujos estén completos y sean navegables de principio a fin, y que las pantallas contemplen la información y las acciones que cada épica requiere. |
| **Consistencia en el uso de componentes de Material Design con Figma** | 30% | Uso efectivo de la biblioteca de MUI en lugar de elementos dibujados a mano; aplicación coherente de tipografía, color, espaciado e iconografía; reutilización de componentes y estilos definidos por el grupo, en vez de soluciones improvisadas pantalla a pantalla. |
| **Calidad de la interfaz móvil resultante** | 30% | Que la aplicación se entienda y se pueda usar: claridad de la navegación, jerarquía visual, legibilidad, adecuación al contexto móvil, tratamiento de estados vacíos y de error, y calidad general del resultado como producto. |

## Recomendaciones

* Comiencen por los flujos, no por las pantallas: identifiquen qué secuencia de pasos sigue el usuario para cumplir cada épica, y recién entonces diseñen las pantallas que esos pasos requieren.
* Definan temprano la navegación global de la aplicación (por ejemplo, qué secciones viven en una barra de navegación inferior). Es una decisión que afecta a todas las pantallas y es cara de cambiar después.
* Diseñen con contenido realista: nombres de restaurantes, platos y reseñas verosímiles. El texto de relleno oculta problemas de diseño que aparecerán al implementar.
* Distribuyan el trabajo por flujos entre los integrantes, pero acuerden antes los estilos y componentes comunes. La consistencia es un criterio de evaluación y es lo primero que se pierde cuando cada integrante diseña por su cuenta.
