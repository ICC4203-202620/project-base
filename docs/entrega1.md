# Entrega 1 — Diseño de la Aplicación en Figma
## Fecha de Entrega: 26 de agosto a las 23:59 hrs., por Git y Figma

En esta primera entrega, cada grupo debe producir el **diseño completo de la aplicación** descrita en el [enunciado general del proyecto](../README.md), en forma de un prototipo interactivo construido en Figma.

El énfasis de la entrega está en el diseño de la experiencia y de la interfaz, no en la programación: el resultado es un prototipo navegable que permita recorrer la aplicación completa y entender cómo se resuelve cada una de las épicas. Este prototipo será el insumo directo del desarrollo del frontend en las entregas siguientes, en particular de la entrega 3, en que la aplicación se implementa con React.

## Antes de comenzar: obtener una cuenta de Figma

**Este es el primer paso y no debe dejarse para el final.** Figma ofrece acceso gratuito a estudiantes y docentes a través de su programa educativo, que habilita funcionalidades necesarias para el trabajo en equipo y el prototipado.

* Postulen a la cuenta educativa en https://www.figma.com/education/, usando su correo institucional.
* La verificación de la cuenta puede tardar algunos días y en ocasiones requiere adjuntar un comprobante de alumno regular. Háganlo apenas comience la entrega, para no perder tiempo de trabajo.
* Todos los integrantes del grupo deben tener su cuenta, de modo que puedan trabajar sobre el mismo archivo de diseño.

## Herramientas y biblioteca de componentes

El diseño debe construirse utilizando la **biblioteca de componentes de MUI para Figma, basada en Material Design**, que se presentará en la clase 2 y en el laboratorio 1. La biblioteca base obligatoria es:

* **Material UI for Figma and MUI X**: https://www.figma.com/community/file/912837788133317724/material-ui-for-figma-and-mui-x

Deben agregar este archivo a su cuenta desde la comunidad de Figma y usarlo como biblioteca de componentes del proyecto.

El uso de esta biblioteca no es una formalidad: los componentes de MUI en Figma tienen una correspondencia directa con los componentes de React que ustedes utilizarán al implementar el frontend en la entrega 3. Diseñar con estos componentes reduce la distancia entre el diseño y el código, y evita que el prototipo proponga interfaces que después resulten costosas o imposibles de construir.

Por lo mismo, se espera que:

* Usen los componentes de la biblioteca en lugar de dibujar controles a mano (botones, campos de texto, listas, _app bars_, _bottom navigation_, _cards_, diálogos, etc.).
* Respeten las convenciones de Material Design en tipografía, espaciado, iconografía y jerarquía visual.
* Definan y usen consistentemente estilos propios del proyecto (paleta de colores y tipografías) sobre la base del sistema, en lugar de improvisar valores pantalla por pantalla.

### Complementos y recursos útiles

Además de la biblioteca base, recomendamos lo siguiente:

* **[Material Theme Builder](https://www.figma.com/community/plugin/1034969338659738588/material-theme-builder)**, el plugin oficial de Material Design: genera paletas y _tokens_ a partir de un color semilla, permite armonizar colores de marca y definir la escala tipográfica eligiendo fuentes de Google Fonts. Úsenlo para fijar el _theme_ de su aplicación, en modo claro y oscuro, antes de escribir una línea de código. Dos advertencias:
  * Lo que exporta son _tokens_ de Material Design (`md.sys.color.primary`, `surface-container-high`), que no coinciden con la estructura del _theme_ de MUI (`palette.primary.main`, `palette.background.paper`, `typography.h1`). La traducción de un vocabulario al otro les corresponde a ustedes; conviene dejarla documentada, porque será el punto de partida del _theme_ de MUI en la entrega 3.
  * Usen los _surface tokens_ nuevos (`surface-container-lowest` a `surface-container-highest`). Las Surfaces 1 a 5 (los antiguos tokens `surface1` … `surface5`, que representaban los niveles de elevación de una superficie mediante tintes del color primario) siguen disponibles por compatibilidad, pero están descontinuadas y aún aparecen en tutoriales antiguos.
* **Iconografía**: usen los iconos que vienen dentro del kit de MUI para Figma. Si necesitan alguno que no esté ahí, búsquenlo en el [catálogo de iconos de MUI](https://mui.com/material-ui/material-icons/), que muestra el nombre exacto de importación en React, y copien el SVG a Figma desde ahí. **Eviten los plugins de Material Symbols**: Symbols es el set sucesor publicado por Google, pero `@mui/icons-material` implementa el set anterior, Material Icons. Los nombres no siempre calzan, hay iconos de Symbols que no existen en MUI, y sus ejes de fuente variable (_Fill_, _Weight_, _Grade_, _Optical size_) no tienen equivalente en el paquete de React. Diseñar con Symbols produce prototipos que después no se pueden implementar. Si prefieren un plugin, elijan uno de Material Icons, cuyas cinco variantes (_Filled_, _Outlined_, _Rounded_, _Two-tone_, _Sharp_) sí corresponden a los sufijos de `@mui/icons-material`.

En ambos casos aplica el mismo principio: "Material Design" como especificación de Google avanza más rápido que MUI como implementación. **Durante el diseño, su fuente de verdad es la documentación de MUI**, no la de Material Design.

## Alcance del diseño

El prototipo debe cubrir **todas las épicas** listadas en la sección "Funcionalidad de la Aplicación" del enunciado general, agrupadas en:

* Cuenta y perfil: registro, inicio de sesión y las dos vistas del perfil de usuario: la propia, que incluye actividad pública y privada, y la que consultan otras personas, limitada a la actividad pública.
* Descubrimiento de restaurantes: búsqueda por nombre, creación de un restaurante que no existe con prevención de duplicados, exploración en el mapa, búsqueda por estilo de comida y cercanía, y ficha del restaurante.
* Registro de la experiencia: _check-in_, publicación de fotos de platos, menús e instalaciones, reseña de un plato asociada a una única fotografía y evaluación de un restaurante asociada opcionalmente a una o más fotografías.
* Interacción social: búsqueda de usuarios por _handle_, seguimiento de usuarios y restaurantes, _feed_, notificaciones sin duplicados, visitas públicas de personas conocidas en un restaurante y comentarios en fotografías públicas.

El diseño debe ser **móvil**: las pantallas se diseñan para el tamaño de un teléfono, con la navegación, los tamaños de área táctil y las convenciones propias de una aplicación móvil. Recuerden que la aplicación se implementará primero como una PWA y luego con React, siempre en el contexto de un dispositivo móvil.

Además de las pantallas principales, el diseño debe hacerse cargo de los estados que hacen usable una aplicación real: estados vacíos (por ejemplo, un _feed_ sin actividad o una búsqueda sin resultados), estados de carga, y mensajes de error o de confirmación.

## Interactividad esperada

El prototipo debe ofrecer **interactividad básica**, entendida como:

1. **Navegación completa**: debe ser posible recorrer la aplicación de extremo a extremo desde el prototipo, sin callejones sin salida. Toda pantalla debe ser alcanzable desde algún flujo, y debe permitir volver.
2. **Interacción con elementos de formulario**: los campos de texto, selectores, controles de calificación y botones de los formularios deben responder a la interacción, mostrando por ejemplo el estado de un campo enfocado, una opción seleccionada o una calificación asignada.
3. **Flujos completos**: las acciones principales deben poder ejecutarse de principio a fin en el prototipo. Por ejemplo, buscar un restaurante, entrar a su ficha, hacer _check-in_, escoger la visibilidad de la actividad, subir la foto de un plato y publicar su reseña. También debe poder apreciarse el efecto de seguir a un usuario o restaurante tanto en el _feed_ como en las notificaciones, incluida la deduplicación cuando una misma actividad coincide con ambos seguimientos.

No se espera lógica de negocio, datos reales ni animaciones sofisticadas. Sí se espera que una persona ajena al grupo pueda tomar el prototipo y usar la aplicación sin explicaciones adicionales.

## Formato de la entrega

El trabajo se realiza en un único archivo de Figma compartido por el grupo, organizado de manera comprensible: páginas o secciones por grupo de épicas, _frames_ con nombres significativos, y una pantalla inicial que sirva de punto de partida del prototipo.

La entrega se compone de tres piezas, cada una con un propósito distinto. Las tres son obligatorias:

1. **Invitación al ayudante como _viewer_ del archivo en Figma.** Esto le permite dejar comentarios sobre el diseño mismo, que es la forma más útil de retroalimentación en esta etapa. Inviten al ayudante de proyecto asignado con el correo que les indique. La información para invitar al ayudante, esto es, nombre de usuario y/o email, será confirmada por Canvas oportunamente.
2. **Enlace al prototipo en modo presentación.** Es el enlace que permite recorrer la aplicación como lo haría un usuario, y es sobre lo que se evalúa la interactividad y los flujos. Debe encontrarse documentado en docs/entrega1/INFORME.md
3. **Copia del archivo `.fig` en el repositorio del grupo**, dentro de la carpeta `docs/entrega1`. Se obtiene desde Figma exportando o guardando una copia local del archivo. Esta copia congelada, con la fecha del _commit_, es el respaldo formal de lo entregado: el archivo en la nube puede seguir editándose después del plazo, el `.fig` del repositorio no.

Además, en la misma carpeta `docs/entrega1` agreguen un documento `README.md` con:

* El nombre de la aplicación definido por el grupo.
* Los nombres de los integrantes.
* El enlace al archivo de Figma y el enlace al prototipo.
* Un breve mapa que indique, para cada épica del enunciado general, en qué pantallas del prototipo se resuelve.
Antes de la fecha límite, creen un _pull request_ titulado "Revisión Entrega 1", incluyendo al ayudante de proyecto asignado, según lo indicado en la sección "Uso del repositorio" del enunciado general.

**Verifiquen los permisos de los enlaces de Figma antes de entregar.** Un prototipo al que el ayudante no puede acceder no puede ser evaluado.

## Uso de Inteligencia Artificial Generativa

En esta entrega está permitido el uso de IA generativa con fines auxiliares: por ejemplo, generar textos de relleno realistas para sus vistas, obtener ideas sobre nombres de restaurantes, platos, y generación de imágenes y reseñas de ejemplo.

**No está permitido usar herramientas de IA que generen el diseño de Figma completo.** El propósito de esta entrega es que conozcan Figma y tengan una experiencia auténtica de prototipado; delegar eso en una herramienta generativa vacía la entrega de sentido y los deja sin la base que necesitarán en las entregas siguientes.

Si usan modelos de lenguaje con los fines permitidos, deben declararlo en una sección apropiada en `docs/entrega1/INFORME.md`, enumerando los modelos utilizados y la finalidad de cada uso.

## Criterios de Evaluación

La evaluación se realiza en dos niveles. **Épica por épica** se evalúan dos aspectos: la cobertura del requisito y la consistencia en el uso de los componentes de MUI. **Globalmente**, se evalúa la calidad de la interfaz móvil resultante como producto. La nota final se obtiene ponderando estos tres puntajes según la fórmula descrita más adelante.

### Cobertura de requisitos (escala 1 a 5, por épica)

Para cada una de las épicas del enunciado general, se evalúa en qué medida el prototipo la resuelve:

| Puntaje | Descripción |
| --- | --- |
| **1** | La épica no está abordada en el prototipo. |
| **2** | La épica está apenas esbozada: existe alguna pantalla relacionada, pero no hay un flujo que permita cumplirla, o faltan la información y las acciones esenciales. |
| **3** | La épica está abordada parcialmente: el flujo principal se reconoce, pero está incompleto, es difícil de recorrer, o quedan fuera acciones o datos relevantes. |
| **4** | La épica está abordada de manera completa: el flujo se recorre de principio a fin, con la información y las acciones que requiere, salvo omisiones menores. |
| **5** | La épica está resuelta de manera completa y cuidada: flujo íntegro y navegable, decisiones de diseño acertadas, y tratamiento de los estados vacíos, de error y de confirmación que correspondan. |

### Consistencia en el uso de componentes de Material Design (escala 1 a 4, por épica)

Para cada épica, se evalúa el uso que hacen las pantallas involucradas de la biblioteca de componentes de MUI:

| Puntaje | Descripción |
| --- | --- |
| **1** | El diseño no se apoya en la biblioteca: los elementos fueron construidos por cuenta propia y no se reconoce correspondencia con los componentes de Material Design. |
| **2** | El uso de la biblioteca es deficiente: se recurre a algunos componentes, pero alterados o combinados de maneras que se apartan de Material Design. |
| **3** | El uso de la biblioteca es correcto en lo general, aunque se observan algunas inconsistencias: variantes mezcladas sin criterio, estilos definidos ad hoc en ciertas pantallas, o tipografías y espaciados fuera del sistema. |
| **4** | El uso de la biblioteca es altamente consistente: componentes empleados según su propósito y estilos del proyecto aplicados de manera uniforme en todas las pantallas de la épica. |

### Calidad de la interfaz móvil resultante (escala 1 a 10, global)

Este criterio se aplica una sola vez, sobre el prototipo completo. Evalúa el resultado como producto: claridad y coherencia de la navegación global, jerarquía visual, legibilidad, adecuación al contexto móvil (áreas táctiles, densidad de información, uso del espacio disponible), calidad del contenido de ejemplo, y el grado en que una persona ajena al grupo puede usar la aplicación sin explicaciones.

| Puntaje | Descripción |
| --- | --- |
| **1 – 2** | La interfaz resulta confusa: no se entiende cómo usar la aplicación. |
| **3 – 4** | La interfaz es usable con esfuerzo, con problemas notorios de navegación, jerarquía o legibilidad. |
| **5 – 6** | La interfaz es correcta y se comprende, aunque sin mayor cuidado en el detalle. |
| **7 – 8** | La interfaz es clara, coherente y agradable de usar, con buen tratamiento del contexto móvil. |
| **9 – 10** | La interfaz tiene calidad de producto: coherente, cuidada en el detalle y comparable a la de una aplicación real del rubro. |

### Cálculo de la nota

A partir de los puntajes anteriores se calculan tres valores normalizados al rango 0 a 1:

* Cobertura: `nC = (promedio de los puntajes de cobertura − 1) / 4`
* Consistencia: `nM = (promedio de los puntajes de consistencia − 1) / 3`
* Calidad: `nQ = (puntaje de calidad − 1) / 9`

El puntaje global de la entrega es la combinación ponderada de los tres:

```
P = 0,50 · nC + 0,25 · nM + 0,25 · nQ
```

Y la nota final, en escala de 1 a 7, es:

```
Nota = 1 + 6 · P
```

Por ejemplo, un grupo con promedio 4,0 en cobertura, 3,0 en consistencia y 8 en calidad obtiene `nC = 0,75`, `nM = 0,67`, `nQ = 0,78`, de donde `P = 0,74` y una nota de **5,4**.

De este modo, la cobertura de los requisitos pesa la mitad de la evaluación, pero un prototipo que cubra todas las épicas ignorando el sistema de diseño o descuidando la interfaz no alcanza una nota alta. La nota se redondea a un decimal.

## Recomendaciones

* Comiencen por los flujos, no por las pantallas: identifiquen qué secuencia de pasos sigue el usuario para cumplir cada épica, y recién entonces diseñen las pantallas que esos pasos requieren.
* Definan temprano la navegación global de la aplicación (por ejemplo, qué secciones viven en una barra de navegación inferior). Es una decisión que afecta a todas las pantallas y es cara de cambiar después.
* Diseñen con contenido realista: nombres de restaurantes, platos y reseñas verosímiles. El texto de relleno oculta problemas de diseño que aparecerán al implementar.
* Distribuyan el trabajo por flujos entre los integrantes, pero acuerden antes los estilos y componentes comunes. La consistencia es un criterio de evaluación y es lo primero que se pierde cuando cada integrante diseña por su cuenta.
