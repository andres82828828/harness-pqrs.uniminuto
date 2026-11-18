# Guion de sustentación: Sistema Inteligente de PQRS

Guion para decir en voz alta, basado en [`guia_unica.md`](guia_unica.md). Cada parte trae **qué mostrar
en pantalla**, **qué decir** y cuánto dura. Total: unos **15 minutos**. Al final hay una versión de
5 minutos, las preguntas probables y qué hacer si algo falla.

---

## 0. Antes de empezar (20 minutos antes)

1. Conecta el portátil al **hotspot de tu celular**. Cierra todo menos el navegador (Opera) y VS Code.
2. Enciende todo: `python scripts/sistema.py encender`.
3. Radica una **PQRS de calentamiento** para que el modelo y Whisper ya estén cargados.
4. Deja abiertas estas pestañas, en este orden:
   1. `docs/arquitectura_pqrs.png` (diagrama)
   2. http://localhost:8000 (app) y otra con el **Panel** como `admin.demo@uniminuto.edu.co`
   3. http://localhost:8025 (buzón local)
   4. http://localhost:9001/rustfs/console/ (data lake, ya con sesión iniciada)
   5. VS Code con `harness/main.py`, `harness/clasificador.py`, `web/app.py` y `web/comun.py`
   6. Una terminal con `docker logs -f pqrs-worker`
5. Ten listo el **QR** (`docs/qr_acceso.png`) y el **video de respaldo**.

---

## 1. Apertura y problema (1 minuto)

**Pantalla:** nada, o una diapositiva con el título.

> "Buenas noches. Nuestro proyecto es un **Sistema Inteligente de Análisis de PQRS** para la universidad.
>
> Hoy la universidad recibe peticiones, quejas, reclamos y sugerencias por muchos canales: correos,
> formularios, llamadas y papel. Se revisan a mano, y eso causa tres problemas: las respuestas tardan,
> los casos urgentes se pierden entre los demás y las directivas no ven qué se repite. Además, la
> **Ley 1755 de 2015** obliga a responder en máximo **quince días hábiles**."

---

## 2. La idea en una frase (30 segundos)

> "Nuestra solución: las PQRS llegan en **texto, audio o foto**, y el sistema las guarda tal cual en un
> **data lake**. Un **harness** las convierte en texto con **Whisper** y **Tesseract**, un **modelo de
> lenguaje local** las clasifica por tipo, tema y urgencia, y un **panel web** las envía al área
> responsable con su plazo. Todo corre en un solo equipo con **Docker**, sin servicios de pago y sin
> que los datos personales salgan de la institución."

---

## 3. Arquitectura (2 minutos y medio)

**Pantalla:** `docs/arquitectura_pqrs.png`. Señala cada caja mientras hablas.

**Los componentes:**
> "La arquitectura tiene cinco componentes, y cada uno corre en su propio **contenedor**:
> - La **aplicación web**, hecha con **FastAPI**: es lo que ve el usuario y el funcionario.
> - El **data lake**, con **RustFS**, compatible con el protocolo S3: guarda los **originales sin
>   transformar**.
> - La **base de datos PostgreSQL**: guarda lo **estructurado**, como la clasificación, los estados y
>   los tiempos.
> - El **harness**: el proceso que convierte cada PQRS en texto y la clasifica.
> - Y el **modelo de IA local**: **Ollama** con **Llama 3.2 de 3.000 millones de parámetros**."

**El flujo (señalando los números del diagrama):**
> "Un caso recorre ocho pasos:
> 1. El usuario radica en la web, y los archivos se guardan en el data lake.
> 2. La web registra la radicación en la base y le da un número.
> 3. El **worker**, que es el harness corriendo en ciclo, revisa el data lake cada tres segundos y
>    encuentra el caso nuevo.
> 4. Descarga el original y extrae el texto: si es audio, con Whisper; si es foto, con Tesseract.
> 5. Le envía el texto al modelo, que responde tipo, tema y urgencia.
> 6. Se aplican las reglas y se guarda el resultado con los tiempos.
> 7. La web se actualiza sola y le muestra al usuario su clasificación y su plazo.
> 8. Y cada mes se genera un reporte PDF para las directivas."

**Las decisiones de diseño:**
> "Tres decisiones importantes:
> - **Data lake y base de datos a la vez:** el data lake guarda datos no estructurados, como audio e
>   imagen, sin transformarlos; la base guarda lo estructurado, que se consulta con SQL.
> - **Desacoplamiento:** la web no clasifica; solo guarda. El worker procesa. Es un patrón
>   **productor-consumidor**, y cada pieza se puede cambiar sin tocar la otra.
> - **La IA decide poco:** el modelo solo elige tipo, tema y urgencia de **catálogos cerrados**. El área
>   la decide una tabla fija, y las urgencias críticas tienen una regla de respaldo."

**Transición:**
> "Esas decisiones se traducen en reglas de negocio."

---

## 4. Reglas de negocio (1 minuto)

**Pantalla:** sección 3 de la guía, o solo hablar.

> "Definimos veintidós reglas. Las más importantes:
> - Solo entran correos **@uniminuto.edu.co**, con un **código de un solo uso** que vence en diez minutos.
> - Hay tres **roles**: el usuario ve sus casos, el funcionario solo los de su área y el administrador todo.
> - Cada PQRS recibe un **radicado único**, y el original **nunca se modifica**.
> - El **área** la asigna una tabla según el tema, no la IA.
> - Si aparecen palabras como *acoso*, *amenaza* o *riesgo*, la urgencia **sube a alta**; ninguna regla la baja.
> - Si la IA se equivoca, el funcionario **corrige**, y se conserva lo que dijo el modelo para auditar.
> - El plazo depende de la urgencia: **uno, cinco o quince días hábiles**, con un **semáforo**.
> - Y por la **Ley 1581**, los reportes no muestran nombres ni correos."

**Transición:**
> "Ahora lo vemos funcionando."

---

## 5. Demo en vivo (3 minutos)

**Paso 1. Acceso.** Muestra el QR.
> "Profesor, puede escanear este código o entrar a esta dirección. Es una página fija en GitHub Pages
> que lo lleva al sistema, que está corriendo en este portátil a través de un túnel HTTPS."

**Paso 2. Ingreso.**
> "Escriba su correo institucional. El código le llega a su correo por Gmail."
(Si no llega: abre http://localhost:8025 → "este es el buzón de respaldo".)

**Paso 3. Radicar.**
> "Ahora puede escribir su PQRS, adjuntar una foto con el más o grabar un audio con el micrófono.
> Puede enviar las tres cosas juntas."

**Paso 4. Mientras clasifica.** Muestra la terminal `docker logs -f pqrs-worker`.
> "Mientras tanto, miren el harness trabajando: encontró la PQRS, está transcribiendo el audio, leyendo
> la foto y ahora consulta al modelo. Con el modelo cargado tarda unos veinte segundos en este portátil,
> que no tiene tarjeta gráfica."

**Paso 5. El data lake.** Abre la consola de RustFS → `pqrs-raw` → `radicaciones` → el radicado.
> "Así quedó en el data lake: una carpeta por radicado, como un expediente, con el texto, el audio, la
> foto y un **manifiesto**. El manifiesto se escribe **de último** y le dice al harness que el paquete
> está completo, así nunca procesa una PQRS a medio subir."

**Paso 6. El seguimiento.** En el celular del profesor.
> "Ya está clasificada: tipo, tema, urgencia, el área a la que se envió, el plazo con su semáforo y
> cuánto tardó cada etapa."

**Paso 7. El panel.** En la pestaña del administrador.
> "Del lado de la universidad, el funcionario ve la bandeja ordenada por urgencia y plazo. Abre el caso,
> ve el original, puede corregir la clasificación y responder. Al responder, al usuario le llega un
> correo y su caso aparece como *Respondida*."

---

## 6. El código (3 minutos)

**Pantalla:** VS Code. Usa **Ctrl + Shift + O** para saltar a cada función.

**El worker** (`harness/main.py`, función `procesar`):
> "El corazón es este ciclo: compara lo que hay en el data lake con lo que ya está en la base y procesa
> solo lo pendiente. Cada caso va en su propia **transacción**: si uno falla, se hace **rollback** y sigue
> con el siguiente. Y gracias a `ON CONFLICT DO NOTHING`, el harness es **idempotente**: correrlo dos
> veces no duplica nada."

**La extracción** (`EXTRACTORES`):
> "Este diccionario asocia cada tipo con su función: texto se lee directo, audio va a Whisper y foto a
> Tesseract. Agregar un canal nuevo sería agregar una función y una línea."

**Las PQRS de varias partes** (`procesar_paquete`):
> "Si llegan texto, audio y foto juntos, extrae cada uno, los une con etiquetas y clasifica **una sola
> vez**. Si una parte falla, por ejemplo una foto borrosa, clasifica con las demás y anota el error."

**La llamada al modelo** (`harness/clasificador.py`, `_llamar_ollama`):
> "Le hablamos a Ollama por HTTP. El **prompt** trae los criterios de cada categoría y seis ejemplos
> resueltos, lo que se llama **few-shot**. Le pedimos **formato JSON** y **temperatura cero**, para que
> responda siempre igual. Y mantenemos el modelo cargado en memoria para que no tarde en cada caso."

**Lo que no decide la IA** (`AREA_POR_TEMA` y `PALABRAS_ALERTA`):
> "El área sale de esta tabla, no del modelo. Y si aparece una palabra de alerta, la urgencia sube a
> alta. Es una **red de seguridad**: preferimos revisar un caso de más que perder uno urgente."

**El correo** (`web/comun.py`, `enviar_correo`):
> "El código de acceso se genera aleatorio y se guarda solo su **hash**. Esta función lo envía por
> **SMTP a Gmail**, con conexión cifrada y una contraseña de aplicación. Si Gmail falla, queda en un
> **buzón local de respaldo** y la pantalla lo avisa."

---

## 7. La base de datos (1 minuto)

**Pantalla:** sección 5 de la guía, y si da el tiempo, una consulta en `psql`.

> "La base tiene siete tablas. Dos las escribe el harness: `pqrs_casos`, con la clasificación, y
> `pqrs_partes`, con el texto y el tiempo de cada parte. Las otras las escribe la web: `usuarios`,
> `codigos_acceso`, `radicaciones`, `gestion` para las correcciones y respuestas, e `historial`.
>
> La base protege las reglas por sí misma: `archivo_origen` es **único**, así que no se procesa dos
> veces lo mismo, y los **CHECK** impiden valores fuera de catálogo. La corrección de un funcionario se
> guarda **aparte**, para no perder lo que dijo el modelo."

Consulta para mostrar (opcional):
```sql
SELECT r.radicado, r.canal, c.tipo, c.tema, c.urgencia, c.area_destino
FROM radicaciones r
LEFT JOIN pqrs_casos c ON c.archivo_origen = 'pqrs-raw/' || r.archivo_origen
ORDER BY r.radicado;
```

---

## 8. Docker (1 minuto)

**Pantalla:** `docker-compose.yml` y `docker-compose.web.yml`.

> "Todo se levanta con **Docker Compose**: nueve servicios, cada uno en su contenedor. Se comunican por
> una **red interna** usando sus nombres, como `postgres` o `ollama`. Los datos viven en **volúmenes**,
> así que sobreviven aunque se borre un contenedor.
>
> Tenemos dos archivos: el núcleo, con el data lake, la base y la IA, y la capa web, con la aplicación,
> el worker, el correo y el túnel. Así el núcleo funciona solo para evaluar y hacer reportes.
>
> Fijamos versiones, como la de Ollama, para que el sistema sea **reproducible**: lo probamos clonando
> el repositorio desde cero en otra carpeta, y funcionó siguiendo solo el README."

---

## 9. Resultados (1 minuto)

**Pantalla:** tabla de la sección 8 de la guía.

> "Medimos el clasificador con **treinta casos sintéticos**, diez de texto, diez de audio y diez de foto,
> con su respuesta correcta conocida. Lo mejoramos en tres versiones:
> - La versión básica acertaba el 80 % en tipo y el 57 % en urgencia.
> - Agregando criterios y ejemplos subió el tipo, pero se escapaban casos urgentes.
> - Con las palabras de alerta, la versión final llegó a **86,7 % en tipo y tema, 73,3 % en urgencia**
>   y detecta **7 de 8 casos urgentes**.
>
> En otro equipo un caso salió distinto con el mismo prompt: la causa era la versión de Ollama. Por eso
> la fijamos: es un hallazgo de **reproducibilidad**."

---

## 10. Limitaciones y lecciones (45 segundos)

> "Somos honestos con las limitaciones: los casos son **sintéticos** y ajustamos el prompt mirando esos
> mismos casos, así que los números son **optimistas**; faltó un conjunto de prueba independiente. En un
> portátil sin GPU, la clasificación tarda decenas de segundos.
>
> Y aprendimos lecciones reales: MinIO retiró sus imágenes durante el proyecto y lo cambiamos por RustFS
> sin tocar el código, gracias al protocolo S3; y descubrimos que hay que mantener el modelo cargado en
> memoria para que responda rápido."

---

## 11. Cierre (20 segundos)

> "En resumen: demostramos que se pueden clasificar PQRS de formatos mezclados con herramientas libres,
> en un solo equipo y sin enviar datos a terceros. Nuestro principio de diseño fue: **el modelo
> clasifica, las reglas protegen y el funcionario decide**. Para producción haría falta un servidor
> institucional y un conjunto de prueba independiente. Muchas gracias; quedamos atentos a sus preguntas."

---

## Versión de 5 minutos (si piden ir rápido)

1. **Problema (30 s):** PQRS por muchos canales, revisión manual, urgencias perdidas, Ley 1755.
2. **Idea (20 s):** la frase de la parte 2.
3. **Arquitectura (1 min):** cinco componentes y el flujo en una frase: "la web guarda en el data lake,
   el worker extrae el texto, el modelo clasifica, las reglas protegen y la web muestra el resultado".
4. **Demo (2 min):** radicar con foto, ver la clasificación y responder desde el panel.
5. **Resultados (40 s):** 86,7 / 86,7 / 73,3, y 7 de 8 urgentes, con la limitación de los datos sintéticos.
6. **Cierre (20 s):** "el modelo clasifica, las reglas protegen y el funcionario decide".

---

## Frases de transición

- Problema → solución: *"Para eso construimos…"*
- Arquitectura → reglas: *"Esas decisiones se traducen en reglas de negocio."*
- Reglas → demo: *"Ahora lo vemos funcionando."*
- Demo → código: *"Veamos qué pasó por dentro."*
- Código → resultados: *"¿Y qué tan bien clasifica? Lo medimos."*
- Resultados → cierre: *"Con sus limitaciones, el sistema demuestra que…"*

---

## Preguntas probables

| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué un modelo local y no ChatGPT o Claude? | Sin costo, sin internet y los datos personales no salen del equipo (Ley 1581). Es intercambiable con una variable |
| ¿Qué es exactamente el harness? | El entorno controlado donde trabaja la IA: lee del data lake sin modificarlo, procesa en orden y guarda en la base |
| ¿Qué hace Ollama? | Es el servidor que ejecuta el modelo en el equipo; recibe el texto por HTTP y responde un JSON |
| ¿Por qué RustFS? | MinIO retiró sus imágenes; RustFS usa el mismo protocolo S3 y solo cambió una línea |
| ¿Por qué data lake y base de datos? | El data lake guarda originales no estructurados; la base, lo estructurado que se consulta con SQL |
| ¿Qué es el manifiesto? | La lista de partes de una PQRS; se escribe de último para marcar que el paquete está completo |
| ¿Qué pasa si la IA se equivoca? | El funcionario corrige; se guarda sin borrar lo del modelo; reglas para lo crítico |
| ¿Cómo saben que funciona? | 30 casos con respuesta conocida; números optimistas, lo reconocemos |
| ¿Por qué falla más la urgencia? | Es subjetiva y el modelo es pequeño; por eso reglas y revisión humana |
| ¿Cómo evitan duplicados? | `archivo_origen` único y `ON CONFLICT DO NOTHING`: el harness es idempotente |
| ¿Es seguro el ingreso? | Dominio exacto, código de un uso, diez minutos, cinco intentos, guardado como hash |
| ¿Y si se cae Gmail? | El código queda en el buzón local y la pantalla lo avisa |
| ¿Por qué tarda la clasificación? | Corre en CPU, sin GPU; la primera vez carga el modelo en memoria |
| ¿Qué cambiarían para producción? | Servidor institucional, conjunto de prueba independiente y completar la regla de revisión manual |

---

## Si algo falla en vivo

| Problema | Qué hacer y qué decir |
|---|---|
| No hay internet | Demo en el portátil con `localhost:8000`: *"el sistema funciona sin internet; el túnel solo es para entrar desde el celular"* |
| La clasificación tarda | Explica los pasos 3 a 6 del diagrama mientras tanto: *"es el modelo trabajando en CPU"* |
| No llega el código | Abre `localhost:8025`: *"este es el respaldo funcionando"* |
| Docker no arranca | Pasa al video de respaldo |
| El profesor borra código | Método de la sección 10 de la guía: ver qué falla, leer el log, `git diff`, arreglar, reconstruir, probar |
