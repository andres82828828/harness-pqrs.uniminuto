# Comandos de PowerShell para encender y apagar el sistema

Ejecuta los comandos **uno por uno**, en orden. En Windows PowerShell no se usa `&&`.

## Encender

```powershell
# 1. Ir a la carpeta del proyecto
cd "C:\andrés\Uniminuto\SEMESTRE VI\ARQUITECTURA\pqrs-inteligente"

# 2. Encender Docker Desktop (una sola vez) y esperar a que esté listo
docker desktop start
docker desktop status            # repetir hasta que diga "running"

# 3. Levantar todos los servicios (web, worker, base de datos, data lake, Ollama, correo, túnel)
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d

# 4. Revisar que todo esté corriendo
docker compose -f docker-compose.yml -f docker-compose.web.yml ps

# 5. Actualizar la página fija con el enlace nuevo del túnel (para entrar desde el celular)
python scripts/publicar_enlace.py --repo https://github.com/andres82828828/harness-pqrs.uniminuto.git

# 6. Calentar el modelo de IA (la primera respuesta tarda 1 a 2 minutos)
docker exec pqrs-ollama ollama run llama3.2:3b "Responde solo: listo"

# 7. Abrir la app y el buzón de prueba
Start-Process "http://localhost:8000"
Start-Process "http://localhost:8025"
```

## Apagar

```powershell
# 1. Ir a la carpeta del proyecto
cd "C:\andrés\Uniminuto\SEMESTRE VI\ARQUITECTURA\pqrs-inteligente"

# 2. Detener los servicios (no borra datos)
docker compose -f docker-compose.yml -f docker-compose.web.yml stop

# 3. Cerrar Docker Desktop de forma segura
docker desktop stop
```

Nunca cierres Docker desde el Administrador de tareas ni apagues el PC con Docker abierto: en este
equipo, un cierre forzado deja archivos bloqueados y Docker no vuelve a arrancar.

## Útiles

```powershell
# Ver qué hace el harness (Ctrl + C para salir)
docker logs -f pqrs-worker

# Ver errores de la web
docker logs pqrs-web --tail 40

# Ver el enlace actual del túnel
Start-Process "http://localhost:8000/acceso"

# Entrar a la base de datos por consola
docker compose -f docker-compose.yml -f docker-compose.web.yml exec postgres psql -U pqrs -d pqrs

# Evaluar el clasificador contra los 30 casos
docker compose -f docker-compose.yml -f docker-compose.web.yml run --rm harness python evaluar.py

# Generar el reporte de un mes
docker compose -f docker-compose.yml -f docker-compose.web.yml run --rm harness python reporte.py --mes 2026-11

# Reconstruir después de cambiar código del harness o de la web
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build worker
docker compose -f docker-compose.yml -f docker-compose.web.yml up -d --build web
```

## Si Docker no arranca ("An unexpected error occurred ... rename ... .sock")

Primero presiona **Quit** en la ventana del error. Luego:

```powershell
wsl --shutdown
$sello = Get-Date -Format yyyyMMddHHmmss
Rename-Item "$env:LOCALAPPDATA\Docker\run" "run.bloqueado-$sello"
Rename-Item "$env:LOCALAPPDATA\docker-secrets-engine" "docker-secrets-engine.bloqueado-$sello"
docker desktop start
```

Si `Rename-Item` dice que la carpeta no existe, sigue con el siguiente comando. Nunca uses
"Reset to factory defaults": borra los datos.
