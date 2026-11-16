-- Tabla principal: una fila por cada PQRS procesada
CREATE TABLE IF NOT EXISTS pqrs_casos (
    id              SERIAL PRIMARY KEY,
    archivo_origen  TEXT UNIQUE NOT NULL,   -- ruta del archivo en MinIO (ej. pqrs-raw/audios/caso_001.mp3)
    canal           TEXT NOT NULL CHECK (canal IN ('texto', 'audio', 'foto', 'mixto')),
    texto_extraido  TEXT,                   -- texto original, transcripción u OCR
    tipo            TEXT CHECK (tipo IN ('peticion', 'queja', 'reclamo', 'sugerencia')),
    tema            TEXT,                   -- notas, finanzas, infraestructura, bienestar, etc.
    urgencia        TEXT CHECK (urgencia IN ('baja', 'media', 'alta')),
    area_destino    TEXT,                   -- area responsable (Tesoreria, Registro, etc.)
    clasificador    TEXT,                   -- 'ollama' o 'claude'
    fecha_recepcion DATE,                   -- fecha en que llego la PQRS
    segundos_clasificacion REAL,            -- lo que tardo el modelo (PQRS de la web)
    creado_en       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pqrs_tipo ON pqrs_casos (tipo);
CREATE INDEX IF NOT EXISTS idx_pqrs_tema ON pqrs_casos (tema);
CREATE INDEX IF NOT EXISTS idx_pqrs_urgencia ON pqrs_casos (urgencia);

-- Partes de una PQRS radicada desde la web (texto, audio y/o foto juntos).
-- Cada parte guarda su texto extraido y cuanto tardo la extraccion.
CREATE TABLE IF NOT EXISTS pqrs_partes (
    id              SERIAL PRIMARY KEY,
    archivo_origen  TEXT NOT NULL REFERENCES pqrs_casos (archivo_origen) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('texto', 'audio', 'foto')),
    archivo         TEXT NOT NULL,
    texto_extraido  TEXT,
    segundos        REAL,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_partes_caso ON pqrs_partes (archivo_origen);
