# Si algo se rompe (o el profesor borra código): cómo encontrarlo y arreglarlo

En la sustentación es probable que el profesor borre o cambie una parte del código y pida
arreglarlo. No hace falta memorizar todo el código: hace falta un **método** para encontrar qué se
rompió y saber **dónde mirar**. Este documento tiene las dos cosas.

---

## 1. El método en 5 pasos

**Paso 1. Ver qué falla.** ¿Qué no funciona? La página no abre, el caso se queda "En proceso", no
llega el código, sale un error en pantalla… Eso dice qué pieza revisar (tabla de la sección 3).

**Paso 2. Ver qué está corriendo.**
```
docker compose -f docker-compose.yml -f docker-compose.web.yml ps
```
Si un servicio no aparece o dice `Exited` o `Restarting`, el problema está ahí.

**Paso 3. Leer el error.** Los registros dicen el archivo, la línea y el motivo:
```
docker logs pqrs-worker --tail 40      # el harness (clasificación)
docker logs pqrs-web --tail 40         # la aplicación web
docker logs pqrs-postgres --tail 20    # la base de datos
```
Busca líneas con `Error`, `Traceback`, `NameError`, `KeyError`, `ModuleNotFoundError`. La última
línea del `Traceback` es el error; la de arriba dice en qué archivo y línea pasó.

**Paso 4. Ver exactamente qué cambió.** El proyecto está en Git, así que Git sabe qué se borró:
```
git status              # qué archivos cambiaron
git diff                # qué líneas: las rojas (-) se borraron, las verdes (+) se agregaron
git diff harness/main.py    # solo un archivo
```
Este es el paso más poderoso: muestra lo borrado línea por línea.

**Paso 5. Arreglar, reconstruir y probar.**
- Restaurar lo borrado (si el profesor lo permite):
  ```
  git restore harness/main.py      # deja el archivo como en el último commit
  ```
- O reescribirlo a mano (si pide que lo hagas tú): mira la sección 4.
- **Reconstruir el contenedor.** El código se copia **dentro** de la imagen al construirla, así que un
  cambio en un `.py` **no aplica** hasta reconstruir:
  ```
  docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build worker   # si fue el harness
  docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build web      # si fue la web
  ```
- Probar de nuevo: radicar una PQRS y ver que se clasifique.

> Dato útil: si el profesor borra algo y **no** reconstruye, el sistema sigue funcionando con la
> versión anterior (la que está dentro de la imagen). El error aparece cuando se reconstruye o se
> reinicia con `--build`.

---

## 2. Mapa rápido: qué archivo hace qué

| Si falla… | Mira | Archivo |
|---|---|---|
| Ningún servicio arranca | `docker compose ps` | `docker-compose.yml`, `docker-compose.web.yml`, `.env` |
| La base de datos o una tabla | `docker logs pqrs-postgres` | `db/init.sql`, `web/comun.py` (`ESQUEMA`) |
| La clasificación (casos "En proceso" para siempre) | `docker logs pqrs-worker` | `harness/main.py`, `harness/clasificador.py` |
| El audio o la foto no se leen | `docker logs pqrs-worker` | `harness/main.py` (`transcribir_audio`, `leer_foto`), `harness/Dockerfile` |
| La página web, el ingreso o el panel | `docker logs pqrs-web` | `web/app.py`, `web/panel.py`, `web/comun.py`, `web/templates/` |
| Las reglas (dominio, límites, plazos) | Probar en la web | `web/reglas.py` |
| El reporte PDF | Correr `reporte.py` | `harness/reporte.py` |

---

## 3. Lo que más probablemente borraría y cómo se ve

### Docker y configuración

| Si borra… | Qué pasa (síntoma) | Cómo lo arreglas |
|---|---|---|
| El servicio `ollama` del compose | **Nada arranca**: `docker compose up` responde `service "worker" depends on undefined service "ollama"` (comprobado). Si además borra el `depends_on`, el worker arranca pero no puede conectarse a `ollama:11434` y los casos quedan "En proceso" | Restaurar el bloque `ollama:` (imagen `ollama/ollama:0.40.16`, puerto `11434`, volumen `ollama_data`) |
| La línea `ports: - "8000:8000"` de la web | La página no abre en `localhost:8000`, aunque el contenedor esté corriendo. El túnel **sí** sigue funcionando, porque entra por la red interna de Docker | Volver a poner el puerto publicado |
| `depends_on` / `condition: service_healthy` | A veces la web o el worker arrancan antes que la base y fallan al conectar | Restaurar; o reiniciar el servicio cuando la base ya esté lista |
| El volumen `./db/init.sql` | En una base **nueva**, no existe `pqrs_casos` (`relation "pqrs_casos" does not exist`) | Restaurar el montaje; luego hay que recrear la base (`down -v` borra los datos) |
| `POSTGRES_PASSWORD` del `.env` | Con una base **nueva**, `pqrs-postgres` no arranca ("superuser password is not specified"). Con la base que ya existe, la base arranca pero la web y el worker no pueden conectarse (sin contraseña) | Volver a poner la variable en el `.env` y recrear los servicios |
| `tesseract-ocr` en `harness/Dockerfile` | Las fotos fallan: "tesseract is not installed" | Restaurar el `apt-get install tesseract-ocr tesseract-ocr-spa` y reconstruir |
| Una librería de `requirements.txt` | El contenedor se cae al arrancar: `ModuleNotFoundError: No module named '...'` | Volver a agregarla y reconstruir |

### Harness (`harness/main.py` y `clasificador.py`)

| Si borra… | Qué pasa | Cómo lo arreglas |
|---|---|---|
| Una función (`leer_foto`, `transcribir_audio`…) | **El worker no arranca** (queda reiniciándose): `NameError: name 'leer_foto' is not defined`, en la línea de `EXTRACTORES`, que la nombra (comprobado). Ninguna PQRS se clasifica | Reescribirla (sección 4) |
| Una entrada de `EXTRACTORES` | Solo falla ese canal: el log muestra `ERROR: 'foto'` (un `KeyError`) y los demás se siguen procesando | `EXTRACTORES = {"texto": leer_texto, "audio": transcribir_audio, "foto": leer_foto}` |
| `conn.commit()` después del `INSERT` | Al correr el harness **una vez** (`run --rm harness`), dice que procesó pero no queda nada guardado. En modo worker casi no se nota, porque la siguiente vuelta empieza con otro `commit()` que guarda lo pendiente | Volver a poner `conn.commit()` después del `INSERT` |
| `ON CONFLICT (archivo_origen) DO NOTHING` | Normalmente no se nota; si algo se procesa dos veces, error de clave duplicada | Restaurar la cláusula |
| La revisión del manifiesto en `listar_objetos` | Las PQRS de la web nunca se procesan (quedan "En proceso"); los datos sintéticos sí | Restaurar el bloque que busca `radicaciones/…/manifiesto.json` |
| `"format": "json"` en `_llamar_ollama` | El modelo responde con texto libre; aparecen `aviso: respuesta invalida` y valores por defecto | Restaurar `"format": "json"` |
| `"temperature": 0` | Funciona, pero la misma PQRS puede clasificarse distinto cada vez | Restaurar `"options": {"temperature": 0}` |
| Una línea de `AREA_POR_TEMA` | `KeyError` cuando llega ese tema | Restaurar la línea (`"finanzas": "Tesorería"`, etc.) |
| `_escalar_urgencia` o su llamada | Funciona, pero los casos graves pueden quedar en urgencia baja (no da error) | Restaurar; se detecta con una PQRS que diga "acoso" o "me siento muy mal" |

### Web (`web/`)

| Si borra… | Qué pasa | Cómo lo arreglas |
|---|---|---|
| Una ruta (`@app.post("/nueva")`, etc.) | Esa página da `404 Not Found` o `405 Method Not Allowed` | Restaurar la función con su decorador |
| `if not reglas.correo_permitido(correo)` | **No da error**: deja entrar correos de cualquier dominio (falla de seguridad, regla RN-01) | Restaurar la validación; probar con un `@gmail.com` |
| La verificación de rol en `panel.py` (`personal(...)`) | **No da error**: un usuario normal entra al panel | Restaurar; probar entrando al `/panel` con un usuario normal |
| Una plantilla (`templates/x.html`) | `TemplateNotFound` en `docker logs pqrs-web` | Restaurar el archivo |
| `estilos.css` | La página funciona pero sin diseño | Restaurar el archivo |

> Los cambios más "tramposos" son los que **no dan error** (seguridad, reglas, temperatura,
> palabras de alerta). Se descubren probando el comportamiento, no leyendo logs. Por eso conviene
> saber qué debería pasar en cada caso (sección 5).

---

## 4. Lo mínimo para reescribir a mano

Si el profesor pide reescribir y no restaurar, estas son las piezas clave en su forma más corta.

**Leer cada tipo de archivo** (`harness/main.py`):
```python
def leer_texto(datos):
    return datos.decode("utf-8", errors="replace")

def leer_foto(datos):
    imagen = Image.open(io.BytesIO(datos))
    return pytesseract.image_to_string(imagen, lang="spa").strip()

EXTRACTORES = {"texto": leer_texto, "audio": transcribir_audio, "foto": leer_foto}
```

**Conectarse al data lake y a la base** (`harness/main.py`):
```python
def conectar_s3():
    return boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT"),
                        aws_access_key_id=os.getenv("MINIO_ROOT_USER"),
                        aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD"),
                        region_name="us-east-1",
                        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}))

conn = psycopg2.connect(host=os.getenv("POSTGRES_HOST"), dbname="pqrs",
                        user=os.getenv("POSTGRES_USER"), password=os.getenv("POSTGRES_PASSWORD"))
```

**Llamar al modelo** (`harness/clasificador.py`):
```python
def _llamar_ollama(prompt):
    r = requests.post(f"{os.getenv('OLLAMA_URL')}/api/chat", json={
        "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"), "stream": False, "format": "json",
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0}}, timeout=300)
    r.raise_for_status()
    return r.json()["message"]["content"]
```

**Guardar el resultado** (`harness/main.py`):
```python
cur.execute("""INSERT INTO pqrs_casos (archivo_origen, canal, texto_extraido, tipo, tema,
               urgencia, area_destino, clasificador, fecha_recepcion)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (archivo_origen) DO NOTHING""", (...))
conn.commit()
```

**Un servicio en Docker Compose** (el patrón de todos):
```yaml
  ollama:
    image: ollama/ollama:0.40.16
    container_name: pqrs-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
```
Y al final del archivo, el volumen declarado: `volumes: ollama_data:`.

---

## 5. Prueba rápida de que todo quedó bien (2 minutos)

1. `docker compose … ps`: todo en `running`.
2. Entrar a http://localhost:8000 con un correo `@uniminuto.edu.co` → llega el código.
3. Probar con un correo `@gmail.com` → debe **rechazarlo**.
4. Radicar una PQRS de texto que diga "un profesor me acosa" → debe quedar **urgencia alta**.
5. Radicar una con foto → en el seguimiento aparece el texto leído de la foto.
6. Entrar al `/panel` con un usuario normal → debe decir **"Sin permiso"**.
7. `docker logs pqrs-worker --tail 10` → sin `ERROR`.

Si estas siete cosas pasan, el sistema está completo.

---

## 6. Qué decir mientras arreglas

El profesor evalúa también cómo razonas. Ir diciendo en voz alta el método ayuda:

> "Primero veo qué servicio está fallando con `docker compose ps`. Luego leo el log del worker: dice
> `NameError` en `leer_foto`, o sea que falta la función que lee las fotos. Con `git diff` confirmo
> qué se borró. La vuelvo a escribir: abre la imagen con Pillow y le pasa Tesseract en español.
> Reconstruyo el worker porque el código vive dentro de la imagen, y pruebo con una foto."
