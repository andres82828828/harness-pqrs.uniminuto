# Guía paso a paso: cómo se construyó el harness de PQRS

Esta guía explica cómo se armó el sistema, en el orden en que se hizo, con el código clave
explicado. La idea es que puedas rehacerlo o defenderlo sin ayuda. Cada paso termina con
**cómo comprobar que funciona** antes de seguir al siguiente.

**Anexos** (al final): A. el harness función por función · B. la base de datos tabla por tabla ·
C. la estructura de Docker · D. cómo estudiar el código en VS Code.

Archivos que se mencionan: todos están en este repositorio. Arquitectura y reglas de negocio:
[`arquitectura_y_reglas.md`](arquitectura_y_reglas.md).

---

## 0. La idea en una frase

Las PQRS llegan como **texto, audio o foto**. Se guardan **tal cual** en un *data lake*, un
**harness** (un contenedor de Python) las convierte en texto, un **modelo de IA local** las
clasifica (tipo, tema, urgencia) y el resultado queda en una **base de datos**, desde donde la
**web** lo muestra al usuario y a los funcionarios.

¿Por qué un data lake y no solo la base de datos? Porque los originales son de formatos mezclados
(audio, imagen, texto). El data lake guarda cualquier archivo sin transformarlo; la base de datos
guarda lo estructurado (la clasificación, los estados, los tiempos).

¿Qué es el harness? El "taller" donde trabaja la IA: un entorno controlado (Docker) con las
herramientas instaladas (Python, Whisper, Tesseract), que lee del data lake sin modificar los
originales, ejecuta las tareas en orden y deja el resultado en la base.

---

## 1. Preparar el equipo

| Herramienta | Para qué |
|---|---|
| Docker Desktop (con WSL 2 en Windows) | Correr todos los servicios con un comando |
| Git y una cuenta de GitHub | Versionar y compartir el código |
| Python 3.10 o superior | Generar los datos sintéticos fuera de Docker |
| Un editor (VS Code) | Escribir el código |

Estructura inicial del repositorio:

```
harness-pqrs.uniminuto/
├── docker-compose.yml
├── .env.example        ← variables SIN contraseñas reales (sí se sube)
├── .gitignore          ← debe contener la línea .env
├── db/init.sql
├── harness/
├── synthetic_data/
└── web/
```

**Regla de oro de seguridad:** las contraseñas van en `.env` (no se sube) y en el repo solo va
`.env.example` con valores de ejemplo. Antes de cada commit, revisa con `git status` que `.env`
no aparezca.

> Error que cometimos: el primer `.env.example` tenía espacios al inicio de cada línea y por eso
> Docker no leía bien las variables (el login del data lake fallaba). Las líneas deben ser
> `CLAVE=valor`, sin espacios.

---

## 2. Data lake, base de datos e IA con Docker Compose

`docker-compose.yml` describe cada servicio. Lo esencial (resumido; el archivo completo está en el repo):

```yaml
services:
  rustfs:                          # data lake compatible con S3
    image: rustfs/rustfs:1.0.0
    environment:
      RUSTFS_ACCESS_KEY: ${MINIO_ROOT_USER}       # salen del .env
      RUSTFS_SECRET_KEY: ${MINIO_ROOT_PASSWORD}
    ports: ["9000:9000", "9001:9001"]             # API S3 y consola web
    volumes: [datalake_data:/data]                # los archivos sobreviven a reinicios

  postgres:
    image: postgres:16
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql   # crea las tablas la 1.a vez
    healthcheck: ...                              # los demás esperan a que esté lista

  ollama:                                         # servidor del modelo de IA
    image: ollama/ollama:0.40.16                  # versión fija (ver sección 13)
  ollama-init:                                    # descarga el modelo una vez y termina
    entrypoint: ... ollama pull llama3.2:3b
```

Conceptos que debes poder explicar:
- **Imagen:** la plantilla (por ejemplo `postgres:16`). **Contenedor:** una imagen corriendo.
- **Volumen:** disco que guarda los datos aunque borres el contenedor.
- **Red interna:** dentro de Docker, los servicios se llaman por su nombre (`postgres`,
  `rustfs`, `ollama`), no por `localhost`.

> Por qué RustFS y no MinIO: el plan era MinIO, pero en 2026 retiró sus imágenes públicas de
> Docker Hub y Quay (los `docker pull` daban "access denied" y 401). RustFS habla el mismo
> protocolo S3, así que el código (que usa la librería `boto3`) no cambió: solo la imagen.

**La tabla principal** (`db/init.sql`):

```sql
CREATE TABLE IF NOT EXISTS pqrs_casos (
    id              SERIAL PRIMARY KEY,
    archivo_origen  TEXT UNIQUE NOT NULL,   -- dónde está el original en el data lake
    canal           TEXT NOT NULL CHECK (canal IN ('texto', 'audio', 'foto', 'mixto')),
    texto_extraido  TEXT,
    tipo            TEXT CHECK (tipo IN ('peticion', 'queja', 'reclamo', 'sugerencia')),
    tema            TEXT,
    urgencia        TEXT CHECK (urgencia IN ('baja', 'media', 'alta')),
    area_destino    TEXT,
    clasificador    TEXT,                   -- qué modelo clasificó
    fecha_recepcion DATE,
    creado_en       TIMESTAMP DEFAULT NOW()
);
```

`archivo_origen UNIQUE` es lo que impide procesar dos veces el mismo archivo. Los `CHECK`
garantizan los catálogos cerrados (regla RN-09) desde la propia base.

**Comprobar:**
```
docker compose up -d
docker compose ps                                              # todo en "running"
docker compose exec postgres psql -U pqrs -d pqrs -c "\dt"     # aparece pqrs_casos
docker compose exec ollama ollama run llama3.2:3b "Hola"       # el modelo responde
```
Consola del data lake: http://localhost:9001/rustfs/console/

---

## 3. Datos sintéticos

No hay PQRS reales (y no se deben usar por la Ley 1581), así que se generan: `synthetic_data/generar_datos.py`.

1. Una lista de casos base con su **clasificación correcta** (tipo, tema, urgencia, área).
2. Cada caso se convierte en uno de tres formatos:
   - **texto:** un `.txt` tipo correo;
   - **audio:** voz sintética con `gTTS` (necesita internet);
   - **foto:** un formulario dibujado con `Pillow` (para probar el OCR).
3. Se suben al bucket `pqrs-raw` (carpetas `textos/`, `audios/`, `fotos/`) con `boto3`:

```python
s3.put_object(Bucket="pqrs-raw", Key=f"{carpeta}/{archivo}", Body=contenido,
              Metadata={"fecha": fecha, "caso-id": caso_id})
```

4. Se escribe `etiquetas.csv` con la respuesta correcta de cada archivo: es la "hoja de
   respuestas" para medir la precisión del modelo.

El generador usa una **semilla fija** (`random.Random(SEMILLA)`): en cualquier equipo produce
exactamente los mismos 30 casos. Así las mediciones son comparables.

**Comprobar:** en la consola de RustFS, `pqrs-raw` tiene `textos/`, `audios/` y `fotos/` con 10
archivos cada una.

---

## 4. El harness: de archivo a texto

`harness/Dockerfile` instala lo necesario para leer audio y fotos:

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt   # boto3, psycopg2, faster-whisper...
COPY . .
CMD ["python", "main.py"]
```

`harness/main.py` sigue siempre el mismo ciclo:

1. **Listar** los archivos del data lake.
2. **Descartar** los que ya están en `pqrs_casos` (por `archivo_origen`). Por eso se puede correr
   muchas veces sin duplicar nada.
3. **Extraer el texto** según el tipo (resumido; en el código real Whisper se carga una sola vez y se reutiliza):

```python
def leer_texto(datos):
    return datos.decode("utf-8", errors="replace")

def transcribir_audio(datos):            # Whisper "small", en CPU
    modelo = WhisperModel("small", device="cpu", compute_type="int8")
    segmentos, _ = modelo.transcribe(ruta_temporal, language="es")
    return " ".join(s.text.strip() for s in segmentos)

def leer_foto(datos):                    # Tesseract en español
    return pytesseract.image_to_string(Image.open(io.BytesIO(datos)), lang="spa").strip()

EXTRACTORES = {"texto": leer_texto, "audio": transcribir_audio, "foto": leer_foto}
```

4. **Clasificar** (sección 5) y **guardar**:

```python
cur.execute("""INSERT INTO pqrs_casos (archivo_origen, canal, texto_extraido, tipo, tema,
               urgencia, area_destino, clasificador, fecha_recepcion)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (archivo_origen) DO NOTHING""", (...))
conn.commit()
```

5. Si un archivo falla, se hace `rollback`, se imprime el error y se sigue con el siguiente: un
   archivo dañado no detiene a los demás.

Los originales **nunca se modifican**: el harness solo hace `get_object` (lectura).

**Comprobar:**
```
docker compose run --rm harness python main.py --limite 3     # prueba con 3 archivos
docker compose exec postgres psql -U pqrs -d pqrs -c "SELECT canal, tipo, tema, urgencia FROM pqrs_casos;"
```

---

## 5. El clasificador: cómo se le pregunta a la IA

`harness/clasificador.py`. Cuatro piezas:

**a) El prompt.** Le pide al modelo responder **solo un JSON** y le da criterios claros y ejemplos:

```
Responde SOLO con un JSON de la forma {"tipo": "...", "tema": "...", "razon": "...", "urgencia": "..."}.
TIPO: "reclamo" = algo falló o se cobró mal; "queja" = inconformidad con el trato; ...
TEMA: "finanzas" = pagos, matrícula...; "notas" = calificaciones...; ...
URGENCIA: "alta" SOLO si hay riesgo, acoso o un plazo que vence; "media" es muy frecuente...
Ejemplos: Mensaje: "..." -> {"tipo": "reclamo", ...}
Ahora clasifica este mensaje: """ <texto> """
```

Los ejemplos del prompt son **distintos** a los casos de prueba, para que la medición sea justa.
El campo `razon` obliga al modelo a justificar la urgencia antes de decidirla (eso mejoró el uso
de "media").

**b) La llamada a Ollama** (API HTTP local):

```python
r = requests.post(f"{OLLAMA_URL}/api/chat", json={
        "model": "llama3.2:3b", "stream": False, "format": "json",
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0}})          # temperatura 0: misma respuesta cada vez
respuesta = r.json()["message"]["content"]
```

**c) Validación.** Se extrae el JSON, se quitan tildes y mayúsculas, y cada campo se compara
con su catálogo. Si el JSON viene roto, se reintenta una vez. Hoy, si un valor no está en el
catálogo, se usa uno por defecto y se imprime un `aviso` (ver RN-12: lo ideal es revisión manual).

**d) Reglas que no dependen del modelo:**
- **Área por tema** (RN-10): una tabla fija `AREA_POR_TEMA` (`finanzas → Tesorería`, …). El
  modelo nunca decide el área.
- **Red de seguridad de urgencia** (RN-11): si el texto contiene palabras de alerta (`acoso`,
  `amenaza`, `riesgo`, `me siento muy mal`, `inundad`…), la urgencia sube a "alta". Así un caso
  grave no se escapa aunque el modelo de 3B se equivoque.

El clasificador es **intercambiable**: `CLASSIFIER=ollama` (local, por defecto) o
`CLASSIFIER=claude` (API de pago, opcional). El resto del sistema no cambia.

---

## 6. Medir la precisión (y ser honesto con los números)

`harness/evaluar.py` compara lo que guardó el modelo con `etiquetas.csv` y calcula: precisión de
tipo, tema y urgencia, porcentaje con los tres bien y **urgencias altas detectadas** (la más
importante: dejar pasar un caso urgente es el peor error).

```
docker compose run --rm harness python evaluar.py
```

Cómo evolucionó (30 casos):

| Versión | Cambio | Tipo | Tema | Urgencia | Altas detectadas |
|---|---|---|---|---|---|
| v1 | prompt básico | 80,0 % | 86,7 % | 56,7 % | 87,5 % |
| v2 | criterios, ejemplos y "razón" | 86,7 % | 86,7 % | 66,7 % | 62,5 % |
| v3 | v2 + palabras de alerta | 86,7 % | 86,7 % | 73,3 % | 87,5 % |

Lo que hay que decir en la sustentación o el artículo:
- El prompt y las reglas se ajustaron **mirando estos mismos 30 casos**; no hay un conjunto de
  prueba separado, así que los números son optimistas.
- Antes de culpar al modelo, se revisó la entrada: el OCR de las fotos salía exacto, así que el
  error de urgencia era del modelo, no del OCR.
- Son 30 casos sintéticos: los porcentajes son indicativos, no concluyentes.

---

## 7. Reporte mensual

`harness/reporte.py` lee `pqrs_casos` de un mes, arma gráficos con `matplotlib` (por tipo,
urgencia, canal y tema), una tabla de casos urgentes y recomendaciones simples, y genera el PDF
con `reportlab`. Lo guarda en `reports/` y lo sube al bucket `pqrs-reportes`. No incluye nombres
ni correos (RN-20).

```
docker compose run --rm harness python reporte.py --mes 2026-10
```

---

## 8. La aplicación web

Carpeta `web/`, con **FastAPI** (Python) y plantillas HTML (**Jinja2**), sin frameworks de
JavaScript. Se eligió así para no aprender otro lenguaje y porque se ve bien en celular con CSS.

| Archivo | Qué hace |
|---|---|
| `app.py` | Rutas del usuario: ingreso, código, nueva PQRS, seguimiento, mis casos, acceso con QR |
| `panel.py` | Rutas del panel: bandeja, detalle, corregir, responder, tablero, reportes, usuarios |
| `comun.py` | Conexiones (base, data lake, correo), esquema de las tablas propias y armado de cada caso |
| `reglas.py` | Reglas de negocio: dominios, límites, radicado, plazos, semáforo, catálogos |
| `templates/` + `static/estilos.css` | Pantallas con el estilo del diseño en Figma (colores UNIMINUTO) |

Piezas importantes:

**Ingreso con código (RN-01).** Se valida el dominio, se genera un código de 6 dígitos, se guarda
**solo su huella** (SHA-256) con vencimiento de 10 minutos y se envía por correo. Al escribirlo se
compara la huella y se cuentan los intentos.

```python
if not reglas.correo_permitido(correo):          # dominio exacto: @uniminuto.edu.co
    return error("Solo se permite el ingreso con correo institucional")
codigo = f"{secrets.randbelow(1_000_000):06d}"
guardar(correo, sha256(codigo), vence=ahora + 10 min)
```

**Radicar.** La web **no clasifica**: guarda los originales en el data lake y registra la
radicación (sección 9). **Seguimiento:** la página pregunta cada 2 s a `/api/caso/<radicado>` y
se recarga sola cuando el harness termina.

**Panel.** El funcionario solo ve los casos de su área; el administrador ve todo. Corregir la
clasificación **no borra** lo que dijo el modelo: la corrección se guarda en la tabla `gestion`
(RN-13). Los estados siguen RN-14 y cada acción queda en `historial`.

**Comprobar:**
```
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build
```
Abrir http://localhost:8000. El código de acceso llega a http://localhost:8025 (buzón de prueba).

---

## 9. Worker y PQRS con varias partes

Al principio el harness se corría a mano. Para la web se necesita que **clasifique solo**: el
servicio `worker` corre `python main.py --ciclo 3`, que revisa el data lake cada 3 segundos.

Una PQRS de la web puede traer **texto, foto y audio juntos**. Se guarda como un **paquete**:

```
pqrs-raw/radicaciones/PQRS-2026-000001/
├── texto.txt
├── audio.webm
├── foto.png
└── manifiesto.json      ← se escribe DE ÚLTIMO
```

El manifiesto escrito al final es un patrón importante: el harness solo procesa una carpeta cuando
ve su manifiesto, así **nunca toma un paquete a medio subir**.

El harness extrae cada parte, une los textos con etiquetas y **clasifica una sola vez**:

```
[Texto escrito] No me han actualizado el pago de la matrícula...
[Transcripción del audio] Hola, llamo porque pagué la matrícula...
[Texto de la foto] UNIVERSIDAD - FORMULARIO PQRS ... Referencia de pago 99812.
```

Guarda el caso (canal `mixto`) en `pqrs_casos` y cada parte, con su texto y su tiempo, en
`pqrs_partes` (RN-17). Si una parte falla, clasifica con las demás; si fallan todas, el caso queda
en revisión manual. Para un solo canal el texto va sin etiquetas, con el mismo prompt que se evaluó.

---

## 10. Acceso desde el celular

- **Túnel** (`cloudflared`): crea un enlace `https://…trycloudflare.com` hacia el portátil. La
  web lo muestra con un QR en `/acceso`. Cambia en cada reinicio.
- **Página fija** (GitHub Pages): `acceso/index.html` se publica en la rama `gh-pages` y redirige
  al enlace vigente, que se actualiza con:
  ```
  python scripts/publicar_enlace.py --repo https://github.com/andres82828828/harness-pqrs.uniminuto.git
  ```
- **Micrófono:** los navegadores solo dejan grabar en HTTPS o `localhost`; por eso funciona por el
  túnel y no por la IP del portátil.

---

## 11. Correo con respaldo

`comun.enviar_correo` intenta el correo real (Gmail con **contraseña de aplicación**, nunca la
contraseña de la cuenta). Si no está configurado o falla, deja el mensaje en el buzón local
(Mailpit) y la página lo avisa (RN-19). Así una caída del correo no bloquea a nadie en la demo.

---

## 12. Lista de pruebas que se hicieron

| Prueba | Resultado |
|---|---|
| Ingreso con correo de otro dominio y con dominio trampa (`uniminuto.edu.co.evil.com`) | Rechazados |
| Código incorrecto, texto corto, sin aceptar datos, contenido repetido, formato no permitido | Rechazados con mensaje claro |
| PQRS con texto + foto + audio | Transcripción y OCR exactos; clasificada una vez |
| Funcionario de otra área abre un caso | "No pertenece a tu área" |
| Cerrar sin responder / respuesta muy corta | Rechazados |
| 30 casos sintéticos | Ver sección 6 |
| Reportes de octubre y noviembre | Se descargan bien desde el panel |
| Clonar el repo en una carpeta nueva y seguir solo el README | Funcionó de punta a punta |

Comandos útiles para depurar:
```
docker compose ps                         # qué está corriendo
docker logs pqrs-worker --tail 30         # qué hizo el harness
docker logs pqrs-web --tail 30            # errores de la web
docker compose exec postgres psql -U pqrs -d pqrs     # consultar la base a mano
```

---

## 13. Problemas reales que aparecieron y cómo se resolvieron

| Problema | Causa | Solución |
|---|---|---|
| `pull access denied` con MinIO | MinIO retiró sus imágenes | Cambiar a RustFS (mismo protocolo S3) |
| No dejaba entrar a la consola del data lake | `.env` con espacios / credenciales viejas en el volumen | `.env` limpio y borrar el volumen de prueba |
| El modelo ponía "petición/servicios" de más | Valores por defecto ocultaban respuestas inválidas | Avisos visibles, mejor prompt con criterios y ejemplos |
| Se escapaban urgencias altas | Modelo pequeño (3B) | Red de seguridad por palabras de alerta |
| El reporte fallaba con PQRS de varias partes | No conocía el canal `mixto` | Agregar la etiqueta |
| El PDF del repo salía dañado al clonar | Git cambiaba los finales de línea | `.gitattributes` con `*.pdf binary` |
| Docker no arrancaba ("rename … .sock") | Cierre forzado de Docker | `wsl --shutdown`, apartar la carpeta `run` y abrir Docker una vez |
| Un caso cambió entre dos equipos | Versión distinta de Ollama | Fijar `ollama/ollama:0.40.16` |

---

## 14. Si lo hicieras solo: orden recomendado

1. Repo, `.gitignore`, `.env.example` (sección 1).
2. `docker-compose.yml` con data lake, base y Ollama; comprobar los tres (sección 2).
3. Generador de datos y subirlos (sección 3).
4. Harness solo con texto; luego Tesseract; luego Whisper (sección 4). Probar siempre con `--limite 3`.
5. Clasificador simple → medir → mejorar el prompt → reglas (secciones 5 y 6). Guardar cada medición.
6. Reporte (sección 7).
7. Web: primero ingreso y radicar, luego seguimiento, luego panel (sección 8).
8. Worker en ciclo y paquetes (sección 9).
9. Túnel, página fija y correo (secciones 10 y 11).
10. README y la prueba de clonar desde cero.

Principios que sirvieron todo el tiempo:
- **Probar cada pieza sola antes de unirla** (un archivo, tres archivos, treinta).
- **Mirar la entrada antes de culpar al modelo** (el OCR, la transcripción).
- **Nunca ocultar errores**: si algo se reemplaza o falla, que se vea en el log o en pantalla.
- **Separar lo que decide la IA de lo que decide una regla** (área, plazos, urgencias críticas).
- **Reproducibilidad**: versiones fijas, semilla fija y un README que alguien más pueda seguir.

---

## 15. Preguntas probables en la sustentación

- **¿Por qué un modelo local y no ChatGPT o Claude?** Funciona sin cuentas, sin costo y sin
  internet, y las PQRS (con datos personales) no salen del equipo. El módulo es intercambiable.
- **¿Qué pasa si la IA se equivoca?** El funcionario corrige desde el panel y se conserva lo que
  dijo el modelo; las urgencias críticas tienen una regla de respaldo.
- **¿Por qué RustFS?** Es compatible con S3; MinIO retiró sus imágenes. Cambiar de proveedor solo
  tocó una línea, porque el código usa el protocolo S3.
- **¿Cómo sabes que funciona?** 30 casos con respuesta conocida y la tabla de la sección 6, con
  sus limitaciones.
- **¿Qué cambiaría para producción?** Correo institucional real, un servidor en vez del portátil,
  un conjunto de prueba independiente, casos mixtos evaluados y RN-12 completa (revisión manual
  cuando el modelo responde algo fuera del catálogo).

---

# Anexo A. El harness, archivo por archivo y función por función

El harness está en `harness/` y tiene cuatro programas. Todos corren dentro del mismo contenedor
(`harness/Dockerfile`: Python 3.11 + Tesseract en español + las librerías de `requirements.txt`).

| Archivo | Qué es | Cómo se ejecuta |
|---|---|---|
| `main.py` | El procesador: lee del data lake, extrae texto, clasifica y guarda | `python main.py` (una vez) o `python main.py --ciclo 3` (worker) |
| `clasificador.py` | El módulo de IA: prompt, llamada al modelo, validación y reglas | No se ejecuta solo; `main.py` llama a `clasificar(texto)` |
| `evaluar.py` | Mide la precisión contra `etiquetas.csv` | `python evaluar.py` |
| `reporte.py` | Genera el reporte mensual en PDF | `python reporte.py --mes 2026-10` |

Librerías (`harness/requirements.txt` y el `Dockerfile`):

| Librería | Para qué |
|---|---|
| `boto3` | Hablar con el data lake por el protocolo S3 (listar, leer y subir archivos) |
| `psycopg2-binary` | Conectarse a PostgreSQL |
| `requests` | Llamar a la API de Ollama (y, opcionalmente, a la de Claude) |
| `Pillow` | Abrir imágenes |
| `pytesseract` | Leer el texto de las fotos (OCR) con Tesseract |
| `faster-whisper` | Transcribir audios (Whisper, versión optimizada para CPU) |
| `matplotlib`, `reportlab` | Gráficos y PDF del reporte |

## A.1 `main.py`: el procesador

### Constantes

| Nombre | Valor | Para qué |
|---|---|---|
| `BUCKET_RAW` | `"pqrs-raw"` | Bucket donde están los originales |
| `PREFIJOS` | `textos/ → texto`, `audios/ → audio`, `fotos/ → foto` | Carpetas de los datos sintéticos y su canal |
| `PREFIJO_PAQUETES` | `"radicaciones/"` | Carpeta de las PQRS que llegan desde la web |
| `MANIFIESTO` | `"manifiesto.json"` | Archivo que marca un paquete como completo |
| `EXTRACTORES` | `{texto: leer_texto, audio: transcribir_audio, foto: leer_foto}` | Qué función usar según el canal |
| `ORDEN_PARTES` | `texto, audio, foto` | Orden en que se unen las partes de un paquete |
| `ETIQUETA_PARTE` | "Texto escrito", "Transcripción del audio", "Texto de la foto" | Etiquetas que ve el modelo |

### Funciones

**`conectar_s3()`**: crea el cliente de `boto3` apuntando al data lake (`S3_ENDPOINT`, que en
Docker es `http://rustfs:9000`) con las credenciales del `.env`. Usa `addressing_style="path"`
porque RustFS, como MinIO, espera la ruta `http://servidor/bucket/archivo`.

**`conectar_db(intentos=20)`**: se conecta a PostgreSQL. Si la base todavía está arrancando,
reintenta cada 3 segundos hasta 20 veces; si no lo logra, termina con un mensaje claro.

**`preparar_esquema(conn)`**: pone al día una base creada con una versión anterior: agrega
`fecha_recepcion` y `segundos_clasificacion`, permite el canal `mixto` y crea `pqrs_partes`. Todo
usa `IF NOT EXISTS`, así que correrla varias veces no rompe nada (es *idempotente*).

**`leer_texto(datos)`**: convierte los bytes a texto UTF-8. `errors="replace"` evita que un
carácter raro detenga el proceso.

**`transcribir_audio(datos)`**: carga Whisper una sola vez (variable global `_whisper`) y lo
reutiliza; cargarlo en cada audio sería muy lento. `faster-whisper` necesita un archivo, por eso
guarda los bytes en un temporal, transcribe con `language="es"`, une los segmentos y borra el
temporal en el `finally` (se borra aunque haya error). Si recibe `None`, solo carga el modelo:
así el worker lo precarga al arrancar (`PRECARGAR_WHISPER=1`).

**`leer_foto(datos)`**: abre la imagen desde memoria (`io.BytesIO`) y le pasa Tesseract en
español (`lang="spa"`).

**`listar_objetos(s3)`**: es un *generador* (`yield`): va entregando `(clave, canal)` de cada
archivo en `textos/`, `audios/` y `fotos/`, y luego `(clave_manifiesto, "paquete")` por cada
`manifiesto.json` en `radicaciones/`. Usa un *paginador* porque S3 entrega máximo 1.000 objetos
por consulta.

**`procesar_paquete(s3, clave_manifiesto)`**: procesa una PQRS de la web.
1. Lee el manifiesto (JSON con el radicado, la fecha y la lista de partes).
2. Ordena las partes (texto, audio, foto).
3. Para cada parte: descarga, extrae el texto y mide el tiempo con `time.perf_counter()`. Si falla,
   guarda el error y sigue con la siguiente.
4. Si solo una parte dejó texto, lo usa tal cual; si son varias, las une con etiquetas
   (`[Texto escrito] …`).
5. Canal: el de la parte si es una sola; `mixto` si son varias.
6. Si hay texto, llama a `clasificar` y mide cuánto tardó. Si no hay texto, no clasifica (el caso
   quedará en revisión manual).
7. Devuelve `(caso, partes)`.

**`guardar_paquete(conn, clave_manifiesto, caso, partes)`**: inserta el caso en `pqrs_casos` con
`ON CONFLICT (archivo_origen) DO NOTHING` (si ya existía, no hace nada) y, solo si se insertó
(`cur.rowcount`), inserta cada parte en `pqrs_partes`. Luego `commit`.

**`main()`**: lee los argumentos `--limite` y `--ciclo`, se conecta y prepara el esquema.
- Sin `--ciclo`: llama una vez a `procesar` y termina.
- Con `--ciclo N`: modo *worker*. Repite `procesar` cada N segundos para siempre. Si algo falla
  (por ejemplo, la base se reinició), imprime el error, se reconecta y sigue.

**`procesar(s3, conn, limite=0, silencioso=False)`**: una vuelta completa.
1. Consulta qué `archivo_origen` ya están en `pqrs_casos`.
2. Arma la lista de pendientes (lo que está en el data lake y no en la base).
3. Si es un paquete, usa `procesar_paquete` y `guardar_paquete`.
4. Si es un archivo suelto: descarga, toma la fecha de los metadatos, extrae el texto (si queda
   vacío, es un error), clasifica e inserta en `pqrs_casos`.
5. Cada archivo va en su propio `try`: si uno falla, `rollback` y sigue con el siguiente.
6. Al final imprime cuántos procesó por canal y cuántos errores hubo.

`silencioso=True` (modo worker) evita imprimir cada 3 segundos cuando no hay nada nuevo.

## A.2 `clasificador.py`: el módulo de IA

### Constantes

| Nombre | Para qué |
|---|---|
| `TIPOS`, `URGENCIAS` | Catálogos cerrados (RN-09) |
| `AREA_POR_TEMA` | Tabla fija tema → área (RN-10). `TEMAS` son sus claves |
| `PALABRAS_ALERTA` | Vocabulario de riesgo que sube la urgencia a alta (RN-11) |
| `POR_DEFECTO` | Valores que se usan si el modelo responde algo inválido |
| `ETIQUETAS_PARTES` | Etiquetas que identifican una PQRS de varias partes |

### Funciones

**`clasificar(texto)`**: la única función que usa el resto del sistema.
1. Elige el modelo según `CLASSIFIER` (`ollama` por defecto, o `claude`).
2. Arma el prompt con `_prompt(texto)`.
3. Hasta dos intentos: llama al modelo → `_extraer_json` → `_normalizar` → `_finalizar`.
   Con `CLASSIFIER_DEBUG=1` imprime la respuesta cruda del modelo.
4. Si los dos intentos fallan, usa `POR_DEFECTO` y lo avisa en el log.
5. Devuelve `{tipo, tema, urgencia, area, clasificador, nota}`.

**`_prompt(texto)`**: el texto que recibe el modelo: formato JSON obligatorio, definición de cada
tipo, tema y urgencia, seis ejemplos y el mensaje a clasificar (máximo 6.000 caracteres).

**`_nota_partes(texto)`**: si el mensaje trae etiquetas de varias partes, agrega al prompt una
frase que dice que todas son el mismo caso. Si no, no agrega nada; así el prompt de los casos de un
solo canal es idéntico al que se evaluó.

**`_llamar_ollama(prompt)`**: `POST /api/chat` a Ollama con `format: "json"` (obliga a responder
JSON) y `temperature: 0` (misma respuesta cada vez). Espera hasta 300 segundos, porque en CPU
puede tardar.

**`_llamar_claude(prompt)`**: lo mismo con la API de Anthropic. Solo se usa con
`CLASSIFIER=claude` y una clave en el `.env`; si falta la clave, da un error claro.

**`_extraer_json(texto)`**: toma lo que hay entre la primera `{` y la última `}` y lo convierte con
`json.loads`. Así funciona aunque el modelo agregue texto alrededor del JSON.

**`_sin_tildes(valor)`**: quita tildes y pasa a minúsculas (`"Petición"` → `"peticion"`), para
comparar con los catálogos.

**`_normalizar(datos)`**: valida tipo, tema y urgencia contra los catálogos. Si alguno no está,
imprime un `aviso` y usa el valor por defecto. Calcula el área con `AREA_POR_TEMA`.

**`_escalar_urgencia(texto, urgencia)`**: si `URGENCIA_REGLAS=1` y la urgencia no es ya alta,
busca las palabras de alerta en el texto (sin tildes) y, si encuentra una, devuelve `"alta"` y una
nota que dice qué palabra la activó.

**`_finalizar(resultado, texto, modo)`**: aplica `_escalar_urgencia` y marca el clasificador como
`ollama+reglas` (o `ollama` si las reglas están apagadas). Así cada fila de la base dice con qué
configuración se clasificó.

## A.3 `evaluar.py`: la medición

**`cargar_etiquetas(ruta)`**: lee `etiquetas.csv` en un diccionario `{nombre_archivo: fila}`.

**`calcular(etiquetas, filas)`**: compara cada caso de la base con su etiqueta correcta. Ignora
los casos que no tienen etiqueta (por ejemplo, las PQRS de la web). Cuenta aciertos de tipo,
tema y urgencia, el porcentaje con los tres bien (`exacto`), los resultados por canal, la lista de
errores y el *recall* de urgencia alta (de los casos realmente urgentes, cuántos detectó).

**`imprimir(res, nombre)`**: muestra la tabla en pantalla.

**`main()`**: lee `pqrs_casos`, toma el nombre del clasificador más usado, calcula, imprime y guarda
`reports/evaluacion_<clasificador>.json`.

## A.4 `reporte.py`: el informe mensual

**`main()`**: toma el mes de `--mes` (o el más reciente con datos), lee los casos de ese mes, llama a
`construir_pdf` y sube el PDF al bucket `pqrs-reportes` (salvo con `--sin-subir`).

**`grafico_resumen(filas)`**: cuatro gráficos de barras con `matplotlib` (tipo, urgencia, canal y
tema) en una sola imagen.

**`hallazgos(filas)`**: frases automáticas (total por canal, tema y tipo más frecuentes, casos
urgentes y áreas con más urgencias) y recomendaciones simples.

**`extracto(texto, n=150)`**: resume cada caso urgente quitando saludos, nombres, encabezados y
firmas, para no mostrar datos personales en el reporte (RN-20). Es "mejor esfuerzo": está pensado
para el formato de los datos sintéticos.

**`construir_pdf(filas, mes, ruta, clasificador)`**: arma el PDF con `reportlab`: título, resumen,
gráficos, recomendaciones, tabla por área, tabla de casos urgentes y una nota de que la
clasificación es automática.

---

# Anexo B. La base de datos, tabla por tabla

Hay siete tablas. Las crean tres lugares distintos, todos con `IF NOT EXISTS` para que puedan
correr en cualquier orden:
- `db/init.sql`: lo ejecuta PostgreSQL la primera vez que arranca (`pqrs_casos`, `pqrs_partes`).
- `harness/main.py` → `preparar_esquema`: pone al día bases viejas.
- `web/comun.py` → `ESQUEMA`: las tablas de la web, que se crean cuando arranca la web.

## B.1 Cómo se relacionan

```
usuarios ──< radicaciones ──< historial
   │              │
   │              ├── gestion            (0 o 1 por radicado)
   │              │
   │              └ ─ ─ pqrs_casos ──< pqrs_partes
   │                 (se unen por archivo_origen)
   └── codigos_acceso  (por correo, temporal)
```

`──<` significa "uno a muchos". La línea punteada entre `radicaciones` y `pqrs_casos` no es una
llave foránea: las escriben programas distintos (la web y el harness) y se unen por la ruta del
archivo. `pqrs_casos.archivo_origen` es `pqrs-raw/` + `radicaciones.archivo_origen`.

¿Por qué dos tablas y no una? `pqrs_casos` es el resultado del **harness**, y también tiene los
30 casos sintéticos, que no vienen de la web. `radicaciones` es lo que registra la **web** cuando
alguien radica. Separarlas permite que el harness funcione igual con o sin la web.

## B.2 Las tablas

### `pqrs_casos` (la escribe el harness)
Una fila por PQRS procesada. Es el resultado del modelo, tal como respondió.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | SERIAL, PK | Número interno |
| `archivo_origen` | TEXT, UNIQUE | Ruta en el data lake. El `UNIQUE` impide procesar dos veces lo mismo |
| `canal` | TEXT, CHECK | `texto`, `audio`, `foto` o `mixto` |
| `texto_extraido` | TEXT | Lo que leyó el sistema (unido con etiquetas si hay varias partes) |
| `tipo`, `tema`, `urgencia` | TEXT, CHECK | Clasificación del modelo (vacíos si no se pudo clasificar) |
| `area_destino` | TEXT | Área calculada a partir del tema |
| `clasificador` | TEXT | `ollama+reglas`, `ollama`, `claude…` o `sin texto` |
| `fecha_recepcion` | DATE | Fecha de la PQRS; el reporte mensual agrupa por ella |
| `segundos_clasificacion` | REAL | Lo que tardó el modelo (solo PQRS de la web) |
| `creado_en` | TIMESTAMP | Cuándo la guardó el harness |

### `pqrs_partes` (la escribe el harness)
Una fila por cada parte de una PQRS de la web.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | SERIAL, PK | |
| `archivo_origen` | TEXT, FK → `pqrs_casos` | A qué caso pertenece. `ON DELETE CASCADE`: si se borra el caso, se borran sus partes |
| `tipo` | TEXT, CHECK | `texto`, `audio` o `foto` |
| `archivo` | TEXT | Ruta del archivo de esa parte |
| `texto_extraido` | TEXT | Lo que se leyó de esa parte |
| `segundos` | REAL | Cuánto tardó la extracción (RN-17) |
| `error` | TEXT | Por qué falló, si falló |

### `usuarios` (la escribe la web)
| Columna | Tipo | Significado |
|---|---|---|
| `id` | SERIAL, PK | |
| `correo` | TEXT, UNIQUE | Correo institucional |
| `rol` | TEXT, CHECK | `usuario`, `funcionario` o `admin` (RN-02) |
| `area` | TEXT | Área del funcionario (vacía para los demás) |
| `creado_en` | TIMESTAMP | Primer ingreso |

### `codigos_acceso` (la escribe la web)
Un código vigente por correo; se borra al ingresar.

| Columna | Tipo | Significado |
|---|---|---|
| `correo` | TEXT, PK | Para quién es el código |
| `codigo_hash` | TEXT | Huella SHA-256 del código. **El código nunca se guarda en claro** |
| `expira_en` | TIMESTAMP | Vence a los 10 minutos |
| `intentos` | INT | Intentos fallidos (máximo 5) |

### `radicaciones` (la escribe la web)
Una fila por PQRS radicada desde la web.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | SERIAL, PK | |
| `radicado` | TEXT, UNIQUE | `PQRS-AAAA-NNNNNN`. El número sale de la secuencia `radicado_seq` (RN-05) |
| `usuario_id` | INT, FK → `usuarios` | Quién la radicó (RN-03: no hay anónimas) |
| `canal` | TEXT, CHECK | `texto`, `audio`, `foto` o `mixto` |
| `archivo_origen` | TEXT, UNIQUE | Ruta del manifiesto en el data lake |
| `partes` | JSONB | Lista de partes, para mostrarlas antes de que el harness termine |
| `sha256` | TEXT | Huella del contenido, para no aceptar dos veces lo mismo (RN-08) |
| `acepta_datos` | BOOLEAN | Aceptó el tratamiento de datos (RN-04) |
| `recibido_en` | TIMESTAMP | Cuándo se radicó; de aquí salen el plazo y el semáforo |

### `gestion` (la escribe el panel)
El trabajo humano sobre un caso. Cero o una fila por radicado.

| Columna | Tipo | Significado |
|---|---|---|
| `radicado` | TEXT, PK y FK → `radicaciones` | |
| `tipo`, `tema`, `urgencia` | TEXT | Clasificación corregida por un funcionario. Si están vacías, vale la del modelo (RN-13) |
| `estado` | TEXT, CHECK | `en_gestion`, `respondida` o `cerrada`. Vacío = "clasificada" |
| `respuesta`, `respondida_en` | TEXT, TIMESTAMP | La respuesta al usuario y cuándo se envió |
| `actualizado_por`, `actualizado_en` | INT FK → `usuarios`, TIMESTAMP | Quién y cuándo tocó el caso por última vez |

### `historial` (la escriben la web y el panel)
Bitácora de todo lo que pasó con un caso: radicada, clasificación corregida, cambios de estado.

| Columna | Tipo | Significado |
|---|---|---|
| `id` | SERIAL, PK | |
| `radicado` | TEXT, FK → `radicaciones` | |
| `usuario_id` | INT, FK → `usuarios` | Quién hizo la acción |
| `accion`, `detalle` | TEXT | Qué se hizo y el detalle (por ejemplo, "antes → después") |
| `creado_en` | TIMESTAMP | Cuándo |

## B.3 Cómo se calcula lo que ve la pantalla

El **estado** que ve el usuario no está guardado en una sola columna; la web lo deduce
(`web/comun.py` → `armar_caso`):

| Situación | Estado |
|---|---|
| Hay radicación pero el harness aún no crea la fila en `pqrs_casos` | En proceso |
| Ya está en `pqrs_casos` pero falta tipo, tema o urgencia | Revisión manual |
| Clasificada y sin fila en `gestion` (o con `estado` vacío) | Clasificada |
| `gestion.estado` tiene valor | En gestión, Respondida o Cerrada |

El **valor que se muestra** de tipo, tema y urgencia es el corregido (`gestion`) si existe; si no,
el del modelo (`pqrs_casos`). El **plazo** se calcula desde `radicaciones.recibido_en` sumando
días hábiles según la urgencia, y el **semáforo** compara el tiempo que queda con el plazo total.

## B.4 Consultas útiles para la sustentación

Abrir la consola de la base:
```
docker compose exec postgres psql -U pqrs -d pqrs
```

```sql
-- Cuántos casos hay por canal y por urgencia
SELECT canal, urgencia, COUNT(*) FROM pqrs_casos GROUP BY canal, urgencia ORDER BY 1, 2;

-- Una PQRS de la web completa: radicación, clasificación del modelo y gestión
SELECT r.radicado, r.canal, c.tipo, c.tema, c.urgencia, c.area_destino,
       g.estado, g.respuesta
FROM radicaciones r
LEFT JOIN pqrs_casos c ON c.archivo_origen = 'pqrs-raw/' || r.archivo_origen
LEFT JOIN gestion g     ON g.radicado = r.radicado
ORDER BY r.recibido_en DESC;

-- Lo que tardó cada parte de las PQRS de la web
SELECT archivo_origen, tipo, segundos, error FROM pqrs_partes ORDER BY id;

-- Casos que un funcionario corrigió (cuánto se equivoca el modelo en la práctica)
SELECT r.radicado, c.tipo AS modelo_tipo, g.tipo AS corregido_tipo,
       c.urgencia AS modelo_urgencia, g.urgencia AS corregida_urgencia
FROM gestion g
JOIN radicaciones r ON r.radicado = g.radicado
JOIN pqrs_casos c   ON c.archivo_origen = 'pqrs-raw/' || r.archivo_origen
WHERE g.tipo IS NOT NULL;
```

---

# Anexo C. La estructura de Docker

## C.1 Las piezas

| Concepto | Qué es | En este proyecto |
|---|---|---|
| **Imagen** | Plantilla de solo lectura con un programa y todo lo que necesita | `postgres:16`, `rustfs/rustfs:1.0.0`, `ollama/ollama:0.40.16`, y las que construimos: web y harness |
| **Dockerfile** | Receta para construir una imagen propia | `web/Dockerfile` y `harness/Dockerfile` |
| **Contenedor** | Una imagen corriendo | `pqrs-web`, `pqrs-worker`, `pqrs-postgres`… |
| **Volumen** | Disco que sobrevive aunque se borre el contenedor | Los datos de la base, del data lake, el modelo y Whisper |
| **Red** | Red privada donde los contenedores se ven por su nombre | `pqrs-inteligente_default` (la crea Compose) |
| **Puerto publicado** | Abre un puerto del contenedor en el PC | `8000:8000` = el puerto 8000 del PC lleva al 8000 del contenedor |
| **Docker Compose** | Archivo YAML que describe y levanta todos los servicios juntos | `docker-compose.yml` + `docker-compose.web.yml` |

## C.2 Por qué hay dos archivos de Compose

- `docker-compose.yml` (del equipo, núcleo de datos): data lake, base de datos, Ollama y el
  harness a demanda.
- `docker-compose.web.yml` (capa de usuario): web, worker, correo de prueba y túnel.

Se usan juntos con `-f` y Compose los combina en uno solo:
```
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build
```
Así el núcleo funciona sin la web (para evaluar y hacer reportes) y la web se agrega encima.

## C.3 Los servicios

| Servicio | Contenedor | Imagen | Puertos en el PC | Volúmenes | Depende de |
|---|---|---|---|---|---|
| `rustfs` | `pqrs-datalake` | `rustfs/rustfs:1.0.0` | 9000 (API S3), 9001 (consola) | `datalake_data:/data` | — |
| `postgres` | `pqrs-postgres` | `postgres:16` | 5432 | `pg_data`, y `db/init.sql` montado | — |
| `ollama` | `pqrs-ollama` | `ollama/ollama:0.40.16` | 11434 | `ollama_data:/root/.ollama` | — |
| `ollama-init` | `pqrs-ollama-init` | igual que ollama | — | — | `ollama` |
| `harness` | `pqrs-harness` | construida desde `./harness` | — | `whisper_cache`, `./reports`, `etiquetas.csv` | `postgres` (sana), `rustfs`, `ollama` |
| `web` | `pqrs-web` | construida desde `./web` | 8000 | — | `postgres` (sana), `rustfs`, `mailpit` |
| `worker` | `pqrs-worker` | construida desde `./harness` | — | `whisper_cache` | `postgres` (sana), `rustfs`, `ollama` |
| `mailpit` | `pqrs-correo` | `axllent/mailpit` | 8025 | — | — |
| `tunnel` | `pqrs-tunel` | `cloudflare/cloudflared` | — | — | `web` |

Detalles que conviene saber explicar:
- **`ollama-init`** es un contenedor de un solo uso: espera a que Ollama responda
  (`until ollama list`), descarga el modelo (`ollama pull llama3.2:3b`) y termina
  (`restart: "no"`). El modelo queda en el volumen `ollama_data`, así que solo se descarga la primera vez.
- **`harness`** tiene `profiles: ["harness"]`: no arranca con `up -d`, solo cuando lo pides con
  `docker compose run --rm harness …` (evaluar, reporte, procesar a mano). `--rm` borra el
  contenedor al terminar.
- **`worker`** usa la **misma imagen** que el harness, pero con otro comando
  (`python main.py --ciclo 3`) y `restart: unless-stopped`: si se cae, Docker lo levanta de nuevo.
- **`postgres`** tiene un `healthcheck` (`pg_isready`). Los servicios que dicen
  `condition: service_healthy` esperan a que la base de verdad acepte conexiones, no solo a que el
  contenedor exista.
- **`tunnel`** no publica puertos: sale a internet hacia Cloudflare y de ahí trae el tráfico hasta
  `http://web:8000`. Por eso funciona aunque la red no permita conexiones entrantes.

## C.4 La red interna

Dentro de Docker cada servicio se llama por su nombre:

```
web     → postgres:5432   (base de datos)
web     → rustfs:9000     (data lake)
web     → mailpit:1025    (correo de prueba)
web     → tunnel:2000     (pregunta el enlace público)
worker  → rustfs:9000, postgres:5432, ollama:11434
tunnel  → web:8000
```

Por eso en el código las direcciones son `http://rustfs:9000` o `host=postgres` y no `localhost`:
dentro de un contenedor, `localhost` es el propio contenedor. Los puertos publicados (8000, 8025,
9001…) son solo para que **tú** entres desde el navegador del PC.

## C.5 Los volúmenes (dónde viven los datos)

| Volumen | Qué guarda | Si lo borras |
|---|---|---|
| `datalake_data` | Todos los archivos del data lake | Se pierden los originales y los reportes |
| `pg_data` | La base de datos | Se pierden casos, usuarios y gestión |
| `ollama_data` | El modelo `llama3.2:3b` (2 GB) | Se vuelve a descargar |
| `whisper_cache` | El modelo de Whisper (~500 MB) | Se vuelve a descargar |

`docker compose down` borra contenedores y red, **pero no los volúmenes**. `docker compose down -v`
sí los borra (todo empieza de cero). Úsalo solo si de verdad quieres borrar los datos.

## C.6 Las dos imágenes propias

`harness/Dockerfile`:
```dockerfile
FROM python:3.11-slim                         # Python liviano
RUN apt-get install tesseract-ocr tesseract-ocr-spa   # OCR en español (programa del sistema)
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt           # librerías de Python
RUN pip install matplotlib reportlab          # capa aparte: cambiar el reporte no reinstala todo
COPY . .                                      # el código va de último
CMD ["python", "main.py"]
```

`web/Dockerfile`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt   # FastAPI, uvicorn, boto3, psycopg...
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", ...]
```

¿Por qué el código se copia **al final**? Docker construye por **capas** y reutiliza las que no
cambiaron. Si el código va de último, al editar un `.py` solo se rehace esa capa y la construcción
tarda segundos; las librerías (lo lento) quedan en caché.

`--host 0.0.0.0` hace que la web escuche fuera del contenedor (si no, solo se vería por dentro), y
`--proxy-headers` hace que entienda que llega por HTTPS a través del túnel.

## C.7 Las variables de entorno

Compose lee el `.env` y reemplaza `${VARIABLE}` en los YAML. `${VARIABLE:-valor}` significa "usa
el `.env` y, si no está, este valor por defecto". El código las lee con `os.getenv(...)`. Así las
contraseñas nunca están en el código ni en el repositorio.

## C.8 Comandos del día a día

```
# Levantar todo (construye lo que cambió)
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build

# Ver qué está corriendo
docker compose -f docker-compose.yml -f docker-compose.web.yml ps

# Ver qué hace un servicio (Ctrl + C para salir)
docker logs -f pqrs-worker
docker logs -f pqrs-web

# Ejecutar el harness a demanda
docker compose -f docker-compose.yml -f docker-compose.web.yml run --rm harness python evaluar.py
docker compose -f docker-compose.yml -f docker-compose.web.yml run --rm harness python reporte.py --mes 2026-11

# Entrar a la base de datos
docker compose exec postgres psql -U pqrs -d pqrs

# Apagar sin perder datos
docker compose -f docker-compose.yml -f docker-compose.web.yml stop
```

Al terminar, cierra Docker Desktop desde su ícono (*Quit Docker Desktop*), nunca forzándolo: en
este PC un cierre forzado deja archivos bloqueados y Docker no vuelve a arrancar (sección 13).

---

# Anexo D. Cómo estudiar el código en Visual Studio Code

Abre la carpeta del proyecto en VS Code y sigue este orden. Junto a cada archivo está la sección
de esta guía que lo explica.

| # | Archivo | Sección |
|---|---|---|
| 1 | `docker-compose.yml` y `docker-compose.web.yml` | 2 y Anexo C |
| 2 | `db/init.sql` | 2 y Anexo B |
| 3 | `synthetic_data/generar_datos.py` | 3 |
| 4 | `harness/main.py`: empieza por `procesar` y `procesar_paquete` | 4, 9 y Anexo A.1 |
| 5 | `harness/clasificador.py`: empieza por `clasificar` | 5 y Anexo A.2 |
| 6 | `harness/evaluar.py` y `harness/reporte.py` | 6, 7, A.3 y A.4 |
| 7 | `web/reglas.py` | 8 y `arquitectura_y_reglas.md` |
| 8 | `web/app.py`, `web/panel.py`, `web/comun.py` | 8 y Anexo B.3 |

Atajos útiles:
- **Ctrl + clic** sobre una función: va a donde está definida.
- **Shift + F12**: muestra todos los lugares donde se usa.
- **Ctrl + P**: abre un archivo por su nombre.
- **Ctrl + Shift + F**: busca un texto en todo el proyecto (por ejemplo `pqrs_partes`).
- **Ctrl + Shift + V** sobre un `.md`: lo muestra con formato.

Para entender una función, mírala funcionando: deja corriendo `docker logs -f pqrs-worker` en una
terminal, radica una PQRS en la web y lee en el log, línea por línea, lo que hace `procesar`.
