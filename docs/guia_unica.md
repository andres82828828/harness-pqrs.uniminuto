# Guía única del Sistema Inteligente de PQRS

Todo lo necesario en un solo documento: qué es, cómo funciona, el código, la base de datos, Docker,
cómo operarlo, cómo sustentarlo y cómo arreglarlo. Resume y reemplaza la lectura de las demás guías
([`guia_construccion.md`](../docs/guia_construccion.md), [`arquitectura_y_reglas.md`](../docs/arquitectura_y_reglas.md), [`sustentacion.md`](../docs/sustentacion.md), [`reparacion.md`](../docs/reparacion.md),
[`comandos_powershell.md`](../docs/comandos_powershell.md)), que siguen en `docs/` por si necesitas el detalle.

Repositorio: https://github.com/andres82828828/harness-pqrs.uniminuto
Acceso fijo: https://andres82828828.github.io/harness-pqrs.uniminuto/

**Contenido:** 1. Qué es · 2. Arquitectura · 3. Reglas de negocio · 4. El código · 5. Base de datos ·
6. Docker · 7. Operación · 8. Resultados · 9. Sustentación · 10. Si algo se rompe · 11. Lecciones

---

## 1. Qué es (dilo en 20 segundos)

> "Las PQRS llegan en texto, audio o foto. El sistema las guarda tal cual en un **data lake**, un
> **harness** las convierte en texto con **Whisper** y **Tesseract**, un **modelo de lenguaje local**
> las clasifica por tipo, tema y urgencia, y un **panel web** las enruta al área responsable con un
> plazo. Todo corre en un equipo con **Docker**, sin servicios de pago y sin sacar datos personales."

| Pieza | Tecnología |
|---|---|
| Web y panel | FastAPI + HTML (Jinja2), adaptable a celular, estilo del Figma (colores UNIMINUTO) |
| Data lake | RustFS 1.0.0, compatible con S3 (buckets `pqrs-raw`, `pqrs-reportes`) |
| Base de datos | PostgreSQL 16 |
| Harness | Python 3.11: extracción, clasificación, reporte y evaluación |
| Audio → texto | faster-whisper `small` |
| Foto → texto | Tesseract en español |
| IA | Ollama 0.40.16 con `llama3.2:3b` (local) |
| Correo | Gmail con contraseña de aplicación, con respaldo en Mailpit (buzón local) |
| Acceso externo | Túnel HTTPS de Cloudflare + página fija en GitHub Pages |

---

## 2. Arquitectura

Diagramas: [`docs/arquitectura_pqrs.png`](../docs/arquitectura_pqrs.png) (lógica) y [`docs/despliegue_pqrs.png`](../docs/despliegue_pqrs.png) (despliegue).

**Flujo de un caso (pasos del diagrama):**
1. El usuario radica en la web: texto, una foto y/o un audio. Cada parte va a
   `pqrs-raw/radicaciones/<radicado>/` y al final se escribe `manifiesto.json`.
2. La web registra la radicación en la base (tabla `radicaciones`) y entrega el número.
3. El **worker** (harness en ciclo) revisa el data lake cada 3 s y encuentra el manifiesto.
4. Descarga cada parte y extrae el texto (lectura, Whisper u OCR), midiendo el tiempo de cada una.
5. Une los textos con etiquetas y el modelo local clasifica **una sola vez**.
6. Aplica las reglas (área por tema, palabras de alerta) y guarda en `pqrs_casos` y `pqrs_partes`.
7. La web se actualiza sola y muestra clasificación, plazo y tiempos.
8. Cada mes se genera el reporte PDF y se sube a `pqrs-reportes`.

**Decisiones de diseño (y por qué):**
- **Data lake + base de datos:** el data lake guarda lo no estructurado sin transformar (audio,
  imagen); la base guarda lo estructurado que se consulta con SQL.
- **Desacoplamiento (productor-consumidor):** la web solo guarda; el worker procesa. Se comunican
  por el data lake y la base. El harness funciona igual con o sin la web.
- **La IA decide poco:** el modelo solo elige tipo, tema y urgencia de catálogos cerrados. El área
  sale de una tabla fija y las urgencias críticas tienen una regla de respaldo.
- **Manifiesto escrito de último:** el harness nunca toma un paquete a medio subir.
- **Protocolo S3:** cambiar de MinIO a RustFS solo tocó una línea del compose.
- **Modelo local:** sin costo, sin internet, datos dentro de la institución (Ley 1581).
- **Despliegue:** un portátil con Docker; el túnel solo transporta la conexión cifrada.

---

## 3. Reglas de negocio (RN)

| RN | Regla |
|---|---|
| 01 | Solo correos `@uniminuto.edu.co` (dominio exacto); código de 6 dígitos, 10 min, 5 intentos |
| 02 | Roles: usuario, funcionario (solo su área), administrador |
| 03 | No hay PQRS anónimas |
| 04 | Se acepta el tratamiento de datos (Ley 1581) antes de radicar |
| 05 | Radicado único `PQRS-AAAA-NNNNNN` |
| 06 | El original va al data lake antes de procesar y nunca se modifica |
| 07 | Texto (≤ 2.000; ≥ 20 si va solo), audio (≤ 2 min, 10 MB) y foto PNG/JPG (≤ 5 MB), juntos o separados |
| 08 | Máximo 5 PQRS por día y sin contenido repetido |
| 09 | Tipo, tema y urgencia solo de catálogos cerrados |
| 10 | El área la asigna una tabla fija según el tema, no la IA |
| 11 | Palabras de alerta suben la urgencia a alta; nada la baja |
| 12 | Sin texto legible → revisión manual (pendiente: respuestas fuera de catálogo usan un valor por defecto) |
| 13 | El funcionario corrige; se conserva lo que dijo el modelo |
| 14 | En proceso → clasificada → en gestión → respondida → cerrada (+ revisión manual) |
| 15 | Plazo: alta 1, media 5, baja 15 días hábiles (Ley 1755) |
| 16 | Semáforo: verde, amarillo (< 25 % del plazo), rojo (vencido) |
| 17 | Se muestran los tiempos de cada etapa |
| 18 | La respuesta llega por correo y queda en "Mis casos" |
| 19 | Si el correo falla, queda en el buzón local y la página lo avisa |
| 20 | Los reportes no muestran nombres ni correos |
| 21 | Datos y modelo locales; el túnel solo transporta HTTPS |
| 22 | Las claves viven en `.env`, que no se sube al repositorio |

---

## 4. El código

### 4.1 Mapa de archivos

| Archivo | Qué hace |
|---|---|
| [`docker-compose.yml`](../docker-compose.yml) | Núcleo: data lake, base, Ollama y harness a demanda |
| [`docker-compose.web.yml`](../docker-compose.web.yml) | Web, worker, correo de prueba y túnel |
| [`db/init.sql`](../db/init.sql) | Tablas `pqrs_casos` y `pqrs_partes` |
| [`synthetic_data/generar_datos.py`](../synthetic_data/generar_datos.py) | 30 casos (10 textos, 10 audios, 10 fotos) con semilla fija + `etiquetas.csv` |
| [`harness/main.py`](../harness/main.py) | El procesador (ver 4.2) |
| [`harness/clasificador.py`](../harness/clasificador.py) | El módulo de IA (ver 4.3) |
| [`harness/evaluar.py`](../harness/evaluar.py) | Precisión contra `etiquetas.csv` |
| [`harness/reporte.py`](../harness/reporte.py) | Reporte mensual en PDF (matplotlib + reportlab) |
| [`web/app.py`](../web/app.py) | Ingreso, radicar, seguimiento, mis casos, acceso con QR |
| [`web/panel.py`](../web/panel.py) | Bandeja, detalle, corregir, responder, tablero, reportes, usuarios |
| [`web/comun.py`](../web/comun.py) | Conexiones, correo con respaldo, tablas de la web, armado de cada caso |
| [`web/reglas.py`](../web/reglas.py) | Reglas: dominios, límites, radicado, plazos, semáforo, catálogos |
| [`scripts/sistema.py`](../scripts/sistema.py) | Encender y apagar todo con un comando |
| [`scripts/publicar_enlace.py`](../scripts/publicar_enlace.py) | Actualiza la página fija con el enlace del túnel |

### 4.2 [`harness/main.py`](../harness/main.py)

| Función | Qué hace |
|---|---|
| `conectar_s3()` | Cliente `boto3` al data lake (`http://rustfs:9000`, estilo de ruta) |
| `conectar_db()` | Conecta a PostgreSQL; reintenta 20 veces cada 3 s |
| `preparar_esquema()` | Pone al día bases viejas (canal `mixto`, `pqrs_partes`); idempotente |
| `leer_texto()` | Bytes → texto UTF-8 |
| `transcribir_audio()` | Whisper cargado **una sola vez** y reutilizado; transcribe en español |
| `leer_foto()` | Tesseract en español sobre la imagen |
| `EXTRACTORES` | `{texto: leer_texto, audio: transcribir_audio, foto: leer_foto}` |
| `listar_objetos()` | Generador: archivos de `textos/ audios/ fotos/` y manifiestos de `radicaciones/` |
| `procesar_paquete()` | Lee el manifiesto, extrae cada parte (midiendo), une con etiquetas, clasifica una vez |
| `guardar_paquete()` | Inserta caso y partes (`ON CONFLICT DO NOTHING`) y hace `commit` |
| `procesar()` | Una vuelta: pendientes = data lake − base; cada archivo en su `try` con `rollback` |
| `main()` | `--limite N` para probar; `--ciclo 3` = modo worker que no termina |

```python
pendientes = [(k, c) for k, c in listar_objetos(s3) if f"{BUCKET_RAW}/{k}" not in ya_procesados]
texto_total = "\n\n".join(f"[{ETIQUETA_PARTE[p['tipo']]}] {p['texto']}" for p in utiles)
```

### 4.3 [`harness/clasificador.py`](../harness/clasificador.py)

**`clasificar(texto)`** es lo único que usa el resto: arma el prompt → llama al modelo → extrae el
JSON → valida contra catálogos → aplica reglas. Reintenta una vez si el JSON viene roto.

| Pieza | Qué hace |
|---|---|
| `_prompt()` | JSON obligatorio, criterios de cada tipo, tema y urgencia, 6 ejemplos (*few-shot*), campo `razon` |
| `_nota_partes()` | Solo en PQRS de varias partes: "todas son el mismo caso" (el prompt de un canal no cambia) |
| `_llamar_ollama()` | `POST /api/chat` con `format: "json"` y `temperature: 0` |
| `_llamar_claude()` | Alternativa en la nube, solo con `CLASSIFIER=claude` |
| `_extraer_json()` | Toma lo que hay entre la primera `{` y la última `}` |
| `_normalizar()` | Quita tildes, valida catálogos, calcula el área con `AREA_POR_TEMA` |
| `_escalar_urgencia()` | Palabras de alerta (acoso, amenaza, riesgo, urgente, "me siento muy mal"…) → alta |
| `_finalizar()` | Marca el clasificador como `ollama+reglas` |

```python
requests.post(f"{url}/api/chat", json={"model": "llama3.2:3b", "stream": False,
    "format": "json", "messages": [...], "options": {"temperature": 0}})
```

### 4.4 La web

- **Ingreso:** valida el dominio exacto, genera el código con `secrets.randbelow`, guarda solo su
  hash SHA-256, vence en 10 min, cuenta intentos. La sesión va firmada con `SECRET_KEY`.
- **Radicar:** valida cada parte, sube las partes y luego el manifiesto, registra la radicación.
  **La web no clasifica.**
- **Seguimiento:** la página consulta `/api/caso/<radicado>` cada 2 s y se recarga al terminar.
- **Panel:** el funcionario solo ve su área; corregir guarda en `gestion` sin borrar lo del modelo;
  responder envía correo; cada acción queda en `historial`.
- **Correo:** `enviar_correo()` usa Gmail si hay `SMTP_USER` y `SMTP_PASSWORD`; si falla, Mailpit.
  Las cuentas de `CORREOS_DEMO` (por defecto `admin.demo@uniminuto.edu.co`) siempre van a Mailpit.

---

## 5. Base de datos (7 tablas)

```
usuarios ──< radicaciones ──< historial
   │              ├── gestion            (0 o 1 por radicado)
   │              └ ─ ─ pqrs_casos ──< pqrs_partes   (se unen por archivo_origen)
   └── codigos_acceso (temporal, por correo)
```

| Tabla | Quién escribe | Contenido clave |
|---|---|---|
| `pqrs_casos` | Harness | `archivo_origen` **UNIQUE**, `canal` (texto/audio/foto/mixto), `texto_extraido`, `tipo`, `tema`, `urgencia` (CHECK), `area_destino`, `clasificador`, `fecha_recepcion`, `segundos_clasificacion` |
| `pqrs_partes` | Harness | Por parte: `tipo`, `archivo`, `texto_extraido`, `segundos`, `error`; FK a `pqrs_casos` con `ON DELETE CASCADE` |
| `usuarios` | Web | `correo` UNIQUE, `rol` (usuario/funcionario/admin), `area` |
| `codigos_acceso` | Web | `codigo_hash` (SHA-256), `expira_en`, `intentos` |
| `radicaciones` | Web | `radicado` UNIQUE (secuencia), `usuario_id` FK, `canal`, `archivo_origen` (manifiesto), `partes` JSONB, `sha256`, `acepta_datos`, `recibido_en` |
| `gestion` | Panel | Corrección (`tipo`, `tema`, `urgencia`), `estado`, `respuesta`, `respondida_en`, quién y cuándo |
| `historial` | Web y panel | `accion`, `detalle`, quién y cuándo |

- **Por qué dos tablas (`radicaciones` y `pqrs_casos`):** una es lo que registra la web y la otra el
  resultado del harness, que también procesa los 30 casos sintéticos que no vienen de la web.
  Se unen por `pqrs_casos.archivo_origen = 'pqrs-raw/' || radicaciones.archivo_origen`.
- **El estado no está en una columna:** la web lo deduce. Sin fila en `pqrs_casos` → en proceso;
  sin tipo/tema/urgencia → revisión manual; `gestion.estado` vacío → clasificada; si no, su valor.
- **Valor mostrado:** el de `gestion` si existe; si no, el del modelo.

Consulta útil:
```sql
SELECT r.radicado, r.canal, c.tipo, c.tema, c.urgencia, c.area_destino, g.estado
FROM radicaciones r
LEFT JOIN pqrs_casos c ON c.archivo_origen = 'pqrs-raw/' || r.archivo_origen
LEFT JOIN gestion g     ON g.radicado = r.radicado
ORDER BY r.recibido_en DESC;
```

---

## 6. Docker

| Concepto | En el proyecto |
|---|---|
| Imagen / contenedor | Plantilla / programa corriendo (`postgres:16` → `pqrs-postgres`) |
| Docker Compose | [`docker-compose.yml`](../docker-compose.yml) (núcleo) + [`docker-compose.web.yml`](../docker-compose.web.yml) (capa web), combinados con `-f` |
| Volumen | Datos persistentes: `datalake_data`, `pg_data`, `ollama_data` (2 GB), `whisper_cache` |
| Red interna | Los servicios se llaman por nombre: `rustfs:9000`, `postgres:5432`, `ollama:11434`, `web:8000` |

| Servicio | Contenedor | Puerto en el PC | Nota |
|---|---|---|---|
| `rustfs` | `pqrs-datalake` | 9000 (S3), 9001 (consola) | |
| `postgres` | `pqrs-postgres` | 5432 | `healthcheck` con `pg_isready`; monta [`db/init.sql`](../db/init.sql) |
| `ollama` | `pqrs-ollama` | 11434 | Versión fija 0.40.16 |
| `ollama-init` | `pqrs-ollama-init` | — | Descarga el modelo una vez y termina |
| `harness` | `pqrs-harness` | — | `profiles: ["harness"]`: solo con `run --rm` |
| `worker` | `pqrs-worker` | — | Misma imagen que harness, `--ciclo 3`, `restart: unless-stopped` |
| `web` | `pqrs-web` | 8000 | |
| `mailpit` | `pqrs-correo` | 8025 | Buzón de prueba |
| `tunnel` | `pqrs-tunel` | — | Sale a Cloudflare; no abre puertos |

- `localhost` dentro de un contenedor es el propio contenedor: por eso el código usa los nombres.
- Los Dockerfile copian el código **de último**: cambiar un `.py` solo rehace esa capa (segundos).
- **Un cambio en el código no aplica hasta reconstruir** (`up -d --build worker` o `web`).
- `down` borra contenedores pero **no** volúmenes; `down -v` borra los datos.
- `${VAR:-valor}` en los YAML: toma la variable del `.env` o usa ese valor por defecto.

---

## 7. Operación

### Encender y apagar
```
cd "C:\andrés\Uniminuto\SEMESTRE VI\ARQUITECTURA\pqrs-inteligente"
python scripts/sistema.py encender     # Docker → servicios → página fija → calienta el modelo → abre la app
python scripts/sistema.py apagar       # detiene servicios y cierra Docker de forma segura
```
**Nunca cierres Docker a la fuerza** (Administrador de tareas o apagar el PC con Docker abierto).

### Direcciones
| Qué | Dirección | ¿Desde otro equipo? |
|---|---|---|
| App y panel | http://localhost:8000 | Sí, por el túnel o la página fija |
| Página fija | https://andres82828828.github.io/harness-pqrs.uniminuto/ | Sí |
| Enlace del túnel y QR | http://localhost:8000/acceso | Sí |
| Buzón de prueba | http://localhost:8025 | No |
| Consola del data lake | http://localhost:9001/rustfs/console/ | No |

### Tareas frecuentes
| Tarea | Cómo |
|---|---|
| Hacer administrador a alguien | `CORREOS_ADMIN=correo@uniminuto.edu.co` en `.env` y `up -d web`; o *Panel → Usuarios* |
| Correo real | Gmail: verificación en dos pasos + contraseña de aplicación (16 letras) en `SMTP_PASSWORD` |
| Ver qué hace el harness | `docker logs -f pqrs-worker` |
| Evaluar | `docker compose -f docker-compose.yml -f docker-compose.web.yml run --rm harness python evaluar.py` |
| Reporte | `… run --rm harness python reporte.py --mes 2026-11` |
| Actualizar la página fija | `python scripts/publicar_enlace.py --repo https://github.com/andres82828828/harness-pqrs.uniminuto.git` |
| Entrar a la base | `docker compose exec postgres psql -U pqrs -d pqrs` |

---

## 8. Resultados

30 casos sintéticos con respuesta conocida:

| Medida | v1 (básico) | v2 (criterios + ejemplos) | v3 (+ palabras de alerta) |
|---|---|---|---|
| Tipo | 80,0 % | 86,7 % | 86,7 % |
| Tema | 86,7 % | 86,7 % | 86,7 % |
| Urgencia | 56,7 % | 66,7 % | 73,3 % |
| Urgencias altas detectadas | 87,5 % | 62,5 % | 87,5 % |

- En otro equipo, v3 dio 83,3 % en tema (un caso): mismo prompt, distinta versión de Ollama. Por eso
  se fijó la versión 0.40.16 (**reproducibilidad**).
- Caso con texto + audio + foto: transcripción y OCR exactos; audio 7,5 s, foto 0,5 s;
  clasificación ~80 s la primera vez (arranque en frío) y ~19 s después.
- **Limitaciones:** casos sintéticos; prompt ajustado sobre esos mismos casos (números optimistas);
  sin conjunto de prueba independiente; casos mixtos sin evaluar; RN-12 incompleta.

---

## 9. Sustentación

### Estructura (unos 12 minutos)
Problema (1 min) → la idea en una frase (30 s) → arquitectura con el diagrama (3 min) → demo
(4 min) → código clave (2 min) → resultados y limitaciones (1 min) → cierre (30 s).

### Demo
**Antes:** hotspot del celular, `sistema.py encender`, una PQRS de calentamiento, pestañas abiertas
(app, panel, buzón, diagrama) y video de respaldo.

**En vivo:**
1. El profesor escanea el QR ([`docs/qr_acceso.png`](../docs/qr_acceso.png)) y entra con su correo; el código le llega a su
   correo (o al buzón local si falla).
2. Radica texto + foto o graba un audio.
3. Mientras clasifica, explica los pasos 3 a 6 (puedes mostrar `docker logs -f pqrs-worker`).
4. Muestra el seguimiento: clasificación, plazo y tiempos.
5. Entra al panel con `admin.demo@uniminuto.edu.co` (código en el buzón local), abre el caso,
   muestra el original, corrige si hace falta y responde.
6. El profesor ve "Respondida" en *Mis casos*.

### Vocabulario clave
| Término | Frase corta |
|---|---|
| Data lake | Guarda los originales en su formato, sin esquema previo |
| Bucket / objeto / S3 | Contenedores de archivos con una API estándar |
| Harness | Entorno controlado donde trabaja la IA, en solo lectura sobre los originales |
| Worker / polling | Proceso en segundo plano que revisa cada 3 s si hay trabajo |
| Productor-consumidor | La web produce casos; el worker los consume |
| Desacoplamiento | Las piezas no dependen unas de otras directamente |
| Idempotencia | Ejecutar varias veces no duplica (`ON CONFLICT DO NOTHING`) |
| Transacción / rollback | Cada caso se guarda completo o no se guarda |
| Restricción UNIQUE / CHECK | La base impide duplicados y valores fuera de catálogo |
| LLM / inferencia local | Modelo de lenguaje corriendo en el propio equipo |
| Prompt / few-shot | Instrucción con ejemplos resueltos |
| Temperatura 0 | Respuesta determinista |
| ASR / OCR | Voz a texto (Whisper) / imagen a texto (Tesseract) |
| Arranque en frío | La primera inferencia tarda porque carga el modelo |
| Precisión / recall | Aciertos sobre el total / urgentes detectados sobre los urgentes reales |
| Sobreajuste | Ajustar mirando los mismos datos con que se mide |
| Reproducibilidad | Mismo resultado en otro equipo (versiones fijas, semilla) |
| OTP / hash | Código de un solo uso / guardar solo su huella |
| Fallback | Respaldo automático cuando algo falla |
| Túnel inverso | Enlace público HTTPS hacia el portátil sin abrir puertos |

### Preguntas probables
| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué modelo local? | Sin costo, sin internet, datos dentro (Ley 1581); intercambiable con una variable |
| ¿Qué es el harness? | El entorno controlado que lee del data lake, procesa en orden y guarda en la base |
| ¿Por qué RustFS? | MinIO retiró sus imágenes; mismo protocolo S3, solo cambió una línea |
| ¿Y si la IA se equivoca? | El funcionario corrige; se guarda sin borrar lo del modelo; reglas para lo crítico |
| ¿Cómo saben que funciona? | 30 casos con respuesta conocida; números optimistas, lo reconocemos |
| ¿Por qué falla la urgencia? | Es subjetiva y el modelo es pequeño; por eso reglas y revisión humana |
| ¿Audio y foto juntos? | Se extrae cada parte, se unen con etiquetas y se clasifica una vez |
| ¿Cómo no duplican? | `archivo_origen UNIQUE` + `ON CONFLICT DO NOTHING` |
| ¿Cómo no toman paquetes incompletos? | El manifiesto se escribe de último |
| ¿Es seguro el ingreso? | Dominio exacto, código de un uso, 10 min, 5 intentos, hash; claves en `.env` |
| ¿Qué cambiaría en producción? | Servidor institucional, conjunto de prueba independiente, completar RN-12 |

**Frase de cierre para repetir:** *"el modelo clasifica, las reglas protegen y el funcionario decide"*.

---

## 10. Si algo se rompe (o el profesor borra código)

### Método en 5 pasos
1. **¿Qué falla?** (no abre, queda "En proceso", no llega el código…).
2. **¿Qué está corriendo?** `docker compose -f docker-compose.yml -f docker-compose.web.yml ps`
3. **Leer el error:** `docker logs pqrs-worker --tail 40` / `pqrs-web` / `pqrs-postgres`. La última
   línea del `Traceback` es el error; la anterior, el archivo y la línea.
4. **Ver qué cambió:** `git status` y `git diff` (rojo = borrado).
5. **Arreglar y reconstruir:** `git restore <archivo>` o reescribir; luego `up -d --build worker`
   (o `web`) y probar.

### Síntomas frecuentes
| Si borran… | Síntoma | Arreglo |
|---|---|---|
| Una función (`leer_foto`…) | Worker reiniciándose: `NameError` en la línea de `EXTRACTORES` | Reescribirla |
| Una entrada de `EXTRACTORES` | Solo ese canal falla: `ERROR: 'foto'` | Restaurar la entrada |
| `conn.commit()` | Con `run --rm`, no queda nada guardado | Volver a ponerlo tras el `INSERT` |
| `"format": "json"` | Avisos de respuesta inválida y valores por defecto | Restaurarlo |
| `"temperature": 0` | Sin error; resultados cambian entre corridas | Restaurarlo |
| Línea de `AREA_POR_TEMA` | `KeyError` con ese tema | Restaurarla |
| Revisión del manifiesto | PQRS de la web quedan "En proceso" | Restaurar el bloque de `radicaciones/` |
| Servicio `ollama` del compose | `depends on undefined service "ollama"` | Restaurar el bloque |
| Puerto `8000:8000` | No abre en localhost (el túnel sí funciona) | Restaurar el puerto |
| Tesseract en el Dockerfile | "tesseract is not installed" | Restaurar el `apt-get` y reconstruir |
| Una librería | `ModuleNotFoundError` | Agregarla y reconstruir |
| `correo_permitido` | **Sin error**: entra cualquier dominio | Restaurar; probar con `@gmail.com` |
| `personal(...)` en el panel | **Sin error**: un usuario entra al panel | Restaurar; probar con un usuario normal |
| Una plantilla | `TemplateNotFound` | Restaurar el archivo |

### Prueba rápida (2 minutos)
1. `ps`: todo en `running`.
2. Ingreso con `@uniminuto.edu.co` → llega el código.
3. Con `@gmail.com` → rechazado.
4. PQRS "un profesor me acosa" → urgencia alta.
5. PQRS con foto → aparece el texto leído.
6. `/panel` con un usuario normal → "Sin permiso".
7. `docker logs pqrs-worker --tail 10` → sin `ERROR`.

**Mientras arreglas, narra el método:** "veo qué servicio falla, leo el log, confirmo con `git diff`
qué se borró, lo reescribo, reconstruyo porque el código vive en la imagen, y pruebo".

---

## 11. Lecciones (problemas reales y cómo se resolvieron)

| Problema | Causa | Solución |
|---|---|---|
| `pull access denied` con MinIO | Retiró sus imágenes | RustFS, mismo protocolo S3 |
| No entraba a la consola del data lake | [`.env.example`](../.env.example) con espacios al inicio | Líneas `CLAVE=valor` sin espacios |
| Muchos "petición/servicios" | Valores por defecto ocultaban respuestas inválidas | Avisos visibles y mejor prompt |
| Se escapaban urgencias altas | Modelo pequeño | Palabras de alerta |
| Reporte fallaba con PQRS mixtas | No conocía el canal `mixto` | Etiqueta agregada |
| PDF dañado al clonar | Git cambiaba finales de línea | `.gitattributes` con `*.pdf binary` |
| Docker no arrancaba ("rename … .sock") | Cierre forzado | `wsl --shutdown`, apartar `%LOCALAPPDATA%\Docker\run`, abrir Docker una vez |
| Un caso cambió entre equipos | Versión distinta de Ollama | Versión fija 0.40.16 |
| Gmail rechazaba el login | Se usó la contraseña de la cuenta | Contraseña de aplicación de 16 letras |

**Principios:** probar cada pieza sola antes de unirla · mirar la entrada antes de culpar al modelo ·
nunca ocultar errores · separar lo que decide la IA de lo que decide una regla · versiones fijas y
semilla para poder repetir los resultados.
