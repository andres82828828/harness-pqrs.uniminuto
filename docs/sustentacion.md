# Sustentación: Sistema Inteligente de PQRS

Hoja de estudio para la sustentación: qué decir, en qué orden, con qué palabras, qué mostrar del
código y cómo responder. Todo en frases cortas para decir en voz alta.

---

## 1. La idea en 20 segundos (apréndela de memoria)

> "Las PQRS de la universidad llegan en texto, audio o foto. Nuestro sistema las guarda tal cual en
> un **data lake**, un **harness** las convierte en texto con **Whisper** y **Tesseract**, un
> **modelo de lenguaje local** las clasifica por tipo, tema y urgencia, y un **panel web** las
> enruta al área responsable con un plazo de respuesta. Todo corre en un solo equipo con
> **Docker**, sin servicios de pago y sin que los datos personales salgan de la institución."

---

## 2. Estructura de la presentación (unos 12 minutos)

| # | Parte | Tiempo | Qué mostrar |
|---|---|---|---|
| 1 | El problema | 1 min | Nada, solo hablar |
| 2 | La solución en una frase | 30 s | Sección 1 |
| 3 | Arquitectura y flujo | 3 min | `docs/arquitectura_pqrs.png` (pasos 1 a 8) |
| 4 | Demo en vivo | 4 min | Celular del profesor + panel |
| 5 | Código clave | 2 min | VS Code: `harness/main.py` y `harness/clasificador.py` |
| 6 | Resultados y limitaciones | 1 min | Tabla v1, v2, v3 |
| 7 | Cierre | 30 s | Qué cambiaría para producción |

---

## 3. Guion por partes

### 3.1 El problema
> "La universidad recibe PQRS por correo, formularios, llamadas y papel. Se revisan a mano, así que
> las respuestas tardan, los casos urgentes se pierden y las directivas no ven los patrones. Además,
> la Ley 1755 obliga a responder en máximo 15 días hábiles."

### 3.2 La arquitectura (señalando el diagrama)
> "Son cinco componentes, cada uno en su propio **contenedor**:"
1. **Aplicación web (FastAPI):** el usuario radica y consulta; el funcionario gestiona.
2. **Data lake (RustFS, compatible con S3):** guarda los **originales sin transformar**.
3. **Base de datos (PostgreSQL):** guarda lo **estructurado**: clasificación, estados, tiempos.
4. **Harness (Python):** el **worker** que procesa cada PQRS.
5. **Modelo de IA local (Ollama con Llama 3.2 de 3B):** clasifica.

> "El flujo es: (1) la web guarda el original en el data lake, (2) registra la radicación en la base,
> (3) el harness detecta el caso nuevo, (4) descarga el original y extrae el texto, (5) el modelo
> clasifica, (6) se aplican las reglas y se guarda, (7) la web muestra el resultado y los tiempos, y
> (8) cada mes se genera un reporte PDF."

**Por qué data lake y base de datos a la vez:**
> "El data lake guarda datos **no estructurados** (audio, imagen) en su formato original. La base
> guarda datos **estructurados** que se consultan con SQL. Cada uno hace lo que mejor sabe."

**Por qué un harness:**
> "El harness es el **entorno controlado** donde trabaja la IA: un contenedor con las herramientas
> instaladas, que lee del data lake **en modo lectura**, ejecuta los pasos en orden y deja el
> resultado en la base. Así el proceso es **reproducible** en cualquier equipo."

### 3.3 La demo (ver sección 6)

### 3.4 Resultados
> "Medimos con 30 casos **sintéticos** con respuesta conocida. La versión final acierta el 86,7 % en
> tipo y tema, el 73,3 % en urgencia y detecta 7 de 8 casos de urgencia alta. Los ajustamos sobre
> los mismos casos, así que son números **optimistas**: lo decimos como limitación."

### 3.5 Cierre
> "Demostramos que se puede clasificar PQRS de formatos mezclados con herramientas libres, en un solo
> equipo y sin enviar datos a terceros. Para producción haría falta un servidor institucional, un
> conjunto de prueba independiente y un modelo más grande o revisión humana obligatoria en urgencias."

---

## 4. Vocabulario técnico (lo que debes poder explicar con tus palabras)

### Arquitectura y despliegue
| Término | Qué significa en el proyecto |
|---|---|
| **Arquitectura por componentes** | El sistema se divide en piezas con una sola responsabilidad (web, datos, procesamiento, IA) |
| **Desacoplamiento** | La web no clasifica; solo guarda. El harness no conoce la web. Se comunican por el data lake y la base |
| **Patrón productor-consumidor** | La web *produce* PQRS en el data lake; el worker las *consume* y procesa |
| **Worker** | Proceso que corre en segundo plano y revisa cada 3 s si hay trabajo nuevo (*polling*) |
| **Contenedor** | Un programa aislado con todo lo que necesita; corre igual en cualquier equipo |
| **Imagen** | La plantilla del contenedor (por ejemplo `postgres:16`) |
| **Docker Compose** | Archivo YAML que describe y levanta todos los contenedores juntos |
| **Volumen** | Disco persistente: los datos sobreviven aunque se borre el contenedor |
| **Red interna** | Los contenedores se llaman por su nombre (`postgres`, `rustfs`, `ollama`) |
| **Healthcheck** | Prueba que dice cuándo la base está lista; los demás servicios la esperan |
| **Túnel (reverse tunnel)** | Cloudflare crea un enlace HTTPS público hacia el portátil sin abrir puertos |
| **Despliegue** | Dónde corre cada pieza: un portátil con Docker; el código en GitHub; acceso por GitHub Pages |

### Datos
| Término | Qué significa en el proyecto |
|---|---|
| **Data lake** | Repositorio de datos en formato original, sin esquema previo |
| **Almacenamiento de objetos / S3** | Se guardan *objetos* (archivos) dentro de *buckets*, con una API estándar (S3) |
| **Bucket** | "Carpeta raíz" del data lake: `pqrs-raw` (originales) y `pqrs-reportes` |
| **Inmutabilidad de los originales** | El harness solo lee (`get_object`); nunca modifica lo que llegó (RN-06) |
| **Manifiesto** | `manifiesto.json` se escribe de último y marca el paquete como completo |
| **Llave primaria / foránea** | Identifican filas y relacionan tablas (por ejemplo `radicaciones.usuario_id → usuarios.id`) |
| **Restricción UNIQUE** | `archivo_origen UNIQUE`: impide procesar dos veces el mismo archivo |
| **Restricción CHECK** | Catálogos cerrados en la base: `tipo IN ('peticion','queja','reclamo','sugerencia')` |
| **Idempotencia** | Ejecutar el harness varias veces no duplica nada (`ON CONFLICT DO NOTHING`) |
| **Transacción, commit, rollback** | Cada archivo se guarda completo o no se guarda; si falla, se deshace |
| **JSONB** | Columna que guarda JSON en PostgreSQL (la lista de partes de una PQRS) |
| **Datos sintéticos** | Casos inventados con respuesta conocida, para no usar datos reales (Ley 1581) |
| **Semilla (seed)** | Hace que el generador produzca siempre los mismos 30 casos |

### Inteligencia artificial
| Término | Qué significa en el proyecto |
|---|---|
| **LLM (modelo de lenguaje grande)** | Llama 3.2 con 3.000 millones de parámetros (3B) |
| **Inferencia local** | El modelo corre en el portátil (Ollama), no en la nube |
| **Prompt** | La instrucción que recibe el modelo: criterios, ejemplos y el mensaje |
| **Few-shot** | El prompt trae 6 ejemplos resueltos para guiar al modelo |
| **Temperatura 0** | El modelo responde siempre lo mismo ante el mismo texto (determinista) |
| **Salida estructurada (JSON)** | Se obliga al modelo a responder `{"tipo", "tema", "razon", "urgencia"}` |
| **Validación contra catálogo** | Si el modelo inventa un valor, el código lo detecta |
| **Reglas determinísticas** | Lo que no decide la IA: el área (tabla fija) y la urgencia por palabras de alerta |
| **ASR (reconocimiento de voz)** | Whisper convierte audio en texto |
| **OCR (reconocimiento óptico de caracteres)** | Tesseract lee el texto de una foto |
| **Arranque en frío (cold start)** | La primera clasificación tarda más porque el modelo se carga en memoria |

### Evaluación
| Término | Qué significa en el proyecto |
|---|---|
| **Precisión (accuracy)** | Porcentaje de casos donde el campo coincide con la etiqueta correcta |
| **Recall de urgencia alta** | De los casos realmente urgentes, cuántos detectó (7 de 8) |
| **Etiquetas (ground truth)** | `etiquetas.csv`: la respuesta correcta de cada caso |
| **Sobreajuste** | Ajustamos el prompt mirando los mismos 30 casos: los números son optimistas |
| **Conjunto de prueba independiente** | Casos nuevos nunca vistos al ajustar; es lo que faltó |
| **Reproducibilidad** | Mismo resultado en otro equipo: por eso fijamos la versión de Ollama (0.40.16) |

### Seguridad y acceso
| Término | Qué significa en el proyecto |
|---|---|
| **Autenticación sin contraseña (OTP)** | Código de 6 dígitos de un solo uso, enviado al correo |
| **Hash SHA-256** | El código no se guarda en claro, solo su huella |
| **Sesión firmada** | La cookie de sesión va firmada con `SECRET_KEY`; no se puede falsificar |
| **Control de acceso por roles** | Usuario, funcionario (solo su área) y administrador |
| **SMTP y contraseña de aplicación** | Envío por Gmail con una clave limitada y revocable |
| **Fallback (respaldo)** | Si Gmail falla, el código queda en el buzón local y la página lo avisa |
| **Variables de entorno (.env)** | Las contraseñas viven fuera del código y no se suben al repositorio |

---

## 5. Código para mostrar (y qué decir de cada uno)

Abre VS Code con **Ctrl + P** y escribe el nombre del archivo.

### 5.1 El ciclo del worker (`harness/main.py`, función `procesar`)
```python
ya_procesados = {fila[0] for fila in cur.fetchall()}          # lo que ya está en la base
pendientes = [(k, c) for k, c in listar_objetos(s3)
              if f"{BUCKET_RAW}/{k}" not in ya_procesados]    # lo que falta
for clave, canal in pendientes:
    try:
        ...extraer texto, clasificar, guardar...
        conn.commit()
    except Exception as e:
        conn.rollback()                                       # un error no detiene a los demás
```
> "El worker compara lo que hay en el data lake con lo que ya está en la base y procesa solo lo
> pendiente. Cada archivo va en su propia transacción: si uno falla, se deshace y sigue con el
> siguiente."

### 5.2 Extraer texto según el tipo (`harness/main.py`)
```python
EXTRACTORES = {"texto": leer_texto, "audio": transcribir_audio, "foto": leer_foto}
```
> "Es un diccionario que asocia cada canal con su función. Agregar un canal nuevo, por ejemplo PDF,
> sería agregar una función y una línea aquí."

### 5.3 PQRS con varias partes (`procesar_paquete`)
```python
texto_total = "\n\n".join(f"[{ETIQUETA_PARTE[p['tipo']]}] {p['texto']}" for p in utiles)
caso["resultado"] = clasificar(texto_total)          # una sola clasificación por PQRS
```
> "Si llegan texto, audio y foto juntos, se extrae cada uno, se unen con etiquetas y se clasifica
> una sola vez. Si una parte falla, se clasifica con las demás."

### 5.4 La llamada al modelo (`harness/clasificador.py`)
```python
requests.post(f"{url}/api/chat", json={
    "model": "llama3.2:3b", "format": "json",
    "options": {"temperature": 0}, "messages": [...]})
```
> "Llamamos a Ollama por HTTP. `format: json` obliga a responder en JSON y `temperature: 0` hace que
> la respuesta sea siempre la misma."

### 5.5 Lo que NO decide la IA (`harness/clasificador.py`)
```python
AREA_POR_TEMA = {"finanzas": "Tesorería", "notas": "Registro Académico", ...}
PALABRAS_ALERTA = ["acoso", "amenaza", "riesgo", "urgente", "me siento muy mal", ...]
```
> "El área sale de una tabla fija, no del modelo. Y si aparece una palabra de alerta, la urgencia
> sube a alta aunque el modelo diga otra cosa. Es una **red de seguridad**: es mejor revisar un caso
> de más que perder uno urgente."

### 5.6 Guardar sin duplicar (`harness/main.py`)
```sql
INSERT INTO pqrs_casos (...) VALUES (...) ON CONFLICT (archivo_origen) DO NOTHING
```
> "Si el caso ya existe, no hace nada. Eso hace al harness **idempotente**."

### 5.7 El ingreso (`web/app.py` y `web/reglas.py`)
```python
if not reglas.correo_permitido(correo): ...           # dominio exacto @uniminuto.edu.co
codigo = f"{secrets.randbelow(1_000_000):06d}"         # aleatorio criptográficamente seguro
guardar(huella(codigo), vence_en=10 minutos)           # solo el hash SHA-256
```
> "Solo entra el dominio institucional exacto; un dominio trampa como `uniminuto.edu.co.evil.com` se
> rechaza. El código es aleatorio, vence en 10 minutos, permite 5 intentos y solo se guarda su hash."

---

## 6. La demo paso a paso

**Antes de entrar al salón (20 minutos antes):**
1. Conecta el portátil al **hotspot de tu celular**.
2. En PowerShell, en la carpeta del proyecto:
   ```
   python scripts/sistema.py encender
   ```
   Esto abre Docker, levanta los servicios, actualiza la página fija de GitHub Pages, calienta el
   modelo y abre la app.
3. Radica una PQRS de **calentamiento** (para que Whisper y el modelo ya estén cargados).
4. Abre en pestañas: la app (`localhost:8000`), el panel como administrador, el buzón
   (`localhost:8025`) y el diagrama de arquitectura.
5. Ten listo el **video de respaldo**.

**En vivo:**
1. Muestra el **QR** (`docs/qr_acceso.png`) o la dirección
   https://andres82828828.github.io/harness-pqrs.uniminuto/
2. El profesor entra con **su correo institucional**. El código le llega a su correo (Gmail ya está
   configurado). Si tarda, revisa spam; si falla, el código queda en el buzón local y la página lo dice.
3. Radica una PQRS: texto + foto o grabación de voz.
4. Mientras clasifica, explica qué está pasando (pasos 3 a 6 del diagrama). Puedes mostrar en una
   terminal: `docker logs -f pqrs-worker`.
5. Muestra el **seguimiento**: tipo, tema, urgencia, área, plazo y tiempo de cada etapa.
6. Entra al **panel** como administrador (`admin.demo@uniminuto.edu.co`, su código va al buzón
   local): abre el caso, muestra el original (foto o audio), corrige si hace falta y **responde**.
7. Vuelve al celular del profesor: **Mis casos** → "Respondida".

**Al terminar:**
```
python scripts/sistema.py apagar
```
Nunca cierres Docker a la fuerza: en este equipo eso impide que vuelva a arrancar.

---

## 7. Preguntas probables y respuestas cortas

**¿Por qué un modelo local y no ChatGPT o Claude?**
Sin costo, sin cuentas, funciona sin internet y los datos personales no salen del equipo (Ley 1581).
El clasificador es intercambiable: una variable cambia a un modelo en la nube.

**¿Qué es exactamente el harness?**
El entorno controlado donde trabaja la IA: un contenedor con Python, Whisper y Tesseract que lee del
data lake sin modificarlo, ejecuta los pasos en orden y guarda el resultado en la base.

**¿Por qué RustFS y no MinIO?**
MinIO retiró sus imágenes públicas durante el proyecto. RustFS usa el mismo protocolo S3, así que el
código no cambió: solo la imagen en el `docker-compose`.

**¿Qué pasa si la IA se equivoca?**
El funcionario corrige desde el panel; se guarda la corrección **sin borrar** lo que dijo el modelo,
para auditar. Las urgencias críticas tienen una regla de respaldo.

**¿Cómo saben que funciona?**
30 casos con respuesta conocida: 86,7 % en tipo y tema, 73,3 % en urgencia, 7 de 8 urgencias altas.
Son optimistas porque ajustamos sobre los mismos casos.

**¿Por qué falla más la urgencia?**
Es la más subjetiva (media frente a alta) y el modelo es pequeño. Por eso pusimos reglas y revisión humana.

**¿Qué pasa si llega audio y foto en la misma PQRS?**
Se extrae cada parte, se unen con etiquetas y se clasifica una vez. Si una parte falla, se usa el resto.

**¿Cómo evitan procesar dos veces lo mismo?**
`archivo_origen` es `UNIQUE` y se inserta con `ON CONFLICT DO NOTHING`: el harness es idempotente.

**¿Cómo evitan tomar una PQRS a medio subir?**
La web escribe el `manifiesto.json` de último; el harness solo procesa carpetas con manifiesto.

**¿Por qué Docker?**
Para que corra igual en cualquier equipo con un comando. Lo probamos clonando el repositorio desde cero.

**¿Qué tan rápido es?**
Extraer el texto tarda segundos; clasificar, unos 20 s en CPU (80 s la primera vez, por el arranque en
frío). Con una GPU o un servidor sería mucho más rápido.

**¿Es seguro el ingreso?**
Solo el dominio institucional exacto, código de un solo uso, 10 minutos, 5 intentos, guardado como hash.
Las contraseñas del sistema están en el `.env`, que no se sube a GitHub.

**¿Qué cambiarían para producción?**
Servidor institucional en vez del portátil, correo institucional, conjunto de prueba independiente,
evaluar casos mixtos y mandar a revisión manual las respuestas del modelo fuera de catálogo (RN-12).

**¿Por qué no un solo modelo que lo haga todo?**
Separamos responsabilidades: Whisper para audio, Tesseract para imágenes, el LLM solo para clasificar
y reglas para lo crítico. Cada pieza se puede medir y cambiar por separado.

**¿Dónde está el código?**
https://github.com/andres82828828/harness-pqrs.uniminuto (con README, guía paso a paso y artículo).

---

## 8. Si algo falla en vivo

| Problema | Qué hacer y qué decir |
|---|---|
| No hay internet | Demo en el portátil con `localhost:8000`. "El sistema funciona sin internet; el túnel solo es para el celular." |
| La clasificación tarda | "Es el arranque en frío del modelo en CPU." Mientras, explica el diagrama |
| El código no llega al correo | Abre `localhost:8025`. "Por diseño hay respaldo al buzón local" |
| Docker no arranca | Usa el video. Luego: `wsl --shutdown`, apartar `%LOCALAPPDATA%\Docker\run` y abrir Docker una vez |
| Te piden cambiar algo del código | Ver `docs/reparacion.md` |

---

## 9. Últimos consejos

- Di siempre **"el modelo clasifica, las reglas protegen y el funcionario decide"**: resume el diseño.
- Si no sabes algo, di qué archivo lo hace y que lo puedes mostrar.
- Habla de las limitaciones antes de que te pregunten: demuestra criterio.
- No digas "la IA lo hace todo": la IA hace una parte pequeña y medida.
