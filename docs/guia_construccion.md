# Guía paso a paso: cómo se construyó el harness de PQRS

Esta guía explica cómo se armó el sistema, en el orden en que se hizo, con el código clave
explicado. La idea es que puedas rehacerlo o defenderlo sin ayuda. Cada paso termina con
**cómo comprobar que funciona** antes de seguir al siguiente.

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
