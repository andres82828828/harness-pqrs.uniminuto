# Aplicación web (lo que ve el usuario)

Página para radicar PQRS desde el celular o el PC y ver cómo el sistema las clasifica.

## Cómo levantarla

Con Docker Desktop abierto y el `.env` creado, desde la carpeta del repositorio:

```
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build
```

| Qué | Dónde |
|---|---|
| Aplicación | http://localhost:8000 |
| Enlace público y código QR (para el celular) | http://localhost:8000/acceso |
| Buzón de prueba con los códigos de acceso | http://localhost:8025 |

## Cómo se usa

1. Entra con un correo `@uniminuto.edu.co`. El código de acceso llega al buzón de prueba (Mailpit).
2. Radica una PQRS por texto, audio o foto. El original se guarda en `pqrs-raw/` del data lake.
3. La pantalla de seguimiento espera a que el harness clasifique el caso y muestra tipo, tema,
   urgencia, área, plazo de respuesta y cuánto tardó el sistema.

## Cómo se conecta con el harness

La web no clasifica. Una PQRS puede traer **texto, un audio y una foto, juntos o por separado**,
y se guarda como un paquete en el data lake:

```
pqrs-raw/radicaciones/PQRS-2026-000006/
├── texto.txt
├── audio.webm
├── foto.png
└── manifiesto.json   ← se escribe de último: señal de "paquete completo"
```

El servicio `worker` (el harness con `--ciclo 3`) busca manifiestos nuevos, extrae el texto de cada
parte (lectura directa, Whisper o Tesseract), los une con etiquetas en el orden texto → audio → foto
y clasifica **una sola vez**. Guarda el caso en `pqrs_casos` (canal `mixto` si hay varias partes) y
cada parte, con su texto y el tiempo que tardó, en `pqrs_partes`. Si una parte falla, clasifica con
las demás; si ninguna deja texto, el caso queda en revisión manual.

Los archivos sueltos de `textos/`, `audios/` y `fotos/` (datos sintéticos) se procesan igual que antes.

## Panel para funcionarios y administradores

En `/panel` (enlace "Panel" en la barra superior):

| Sección | Quién | Qué hace |
|---|---|---|
| Bandeja | Funcionario (su área) y administrador (todas) | Casos ordenados por estado y plazo, con filtros |
| Detalle del caso | Igual que la bandeja | Ver el original del data lake, corregir la clasificación (RN-13), pasar a "en gestión", responder y cerrar |
| Tablero | Igual que la bandeja | Cifras y gráficos por estado, urgencia, tipo, canal, tema y área |
| Reportes | Administrador | Descargar los PDF del bucket `pqrs-reportes` |
| Usuarios | Administrador | Asignar rol (usuario, funcionario, administrador) y área |

La respuesta del funcionario le llega al usuario por correo y aparece en "Mis casos".
La corrección no borra lo que dijo el modelo: queda en `pqrs_casos` y la corrección en la tabla `gestion`.

## Variables opcionales del `.env`

| Variable | Para qué | Valor por defecto |
|---|---|---|
| `DOMINIOS_PERMITIDOS` | Dominios de correo aceptados, separados por coma | `uniminuto.edu.co` |
| `CORREOS_ADMIN` | Correos con rol administrador, separados por coma | vacío |
| `MAX_RADICACIONES_DIA` | Máximo de PQRS por usuario al día | `5` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | Servidor de correo real, si se quiere enviar el código al buzón verdadero | Mailpit local |
| `SECRET_KEY` | Clave para firmar las sesiones; si falta, se genera una en cada arranque | vacío |
| `PUBLIC_URL` | Enlace fijo, si no se usa el túnel | vacío |

## Reglas de negocio que aplica la web

RN-01 (dominio del correo), RN-03 (sin anónimos), RN-04 (aceptación de datos), RN-05 (radicado),
RN-06 (original al data lake antes de registrar), RN-07 (límites), RN-08 (máximo diario),
RN-12 (revisión manual si falta clasificación), RN-15 (plazo) y RN-16 (semáforo).
Están en `reglas.py`.

Limitaciones conocidas: el plazo cuenta de lunes a viernes pero no descuenta festivos, y la
duración del audio se controla por tamaño (10 MB), no por minutos.
