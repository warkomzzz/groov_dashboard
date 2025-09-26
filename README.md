# Groov Dashboard

Aplicacion full stack para monitorear sensores provenientes de un controlador Opto 22 Groov EPIC. El backend (FastAPI + MongoDB) administra autenticacion JWT, lectura de datos historicos, exportaciones y opcionalmente un poller Modbus TCP. El frontend (React + Vite + TypeScript) entrega un dashboard responsivo con graficos, tabla de mediciones y flujos diferenciados por rol.

## Estructura del repositorio
- `backend/`: API FastAPI, utilidades de exportacion y configuracion del poller Modbus.
- `frontend/`: aplicacion React cliente, estilos y configuraciones de build con Vite.
- `frontend/dist/`: build estatico generado por `npm run build`.

## Backend (FastAPI + MongoDB)
### Caracteristicas clave
- Autenticacion JWT con hashing PBKDF2 (`/auth/login`, `/auth/me`).
- Endpoints para sensores, mediciones historicas, valores recientes y tiempo real (via `POST /realtime`).
- Generacion de reportes en XLSX (`/export/excel`) y PDF con graficos (`/export/pdf`).
- Poller Modbus TCP opcional que inserta lecturas de una bascula directamente en MongoDB.
- Seed opcional de usuarios por defecto (`admin` y `produccion`).

### Requisitos
- Python 3.11 o superior.
- MongoDB accesible (por defecto `mongodb://127.0.0.1:27017`).
- Dependencias definidas en `backend/requirements.txt`.
- (Opcional) Libreria `pymodbus` para el poller Modbus.

### Variables de entorno relevantes
Define estas claves en un archivo `.env` bajo `backend/` o en el entorno de ejecucion:
- `MONGO_URI`, `DB_NAME`, `COLL_NAME`: conexion y colecciones objetivo (por defecto `groov/measurements`).
- `JWT_SECRET`: secreto para firmar tokens.
- `TIMEZONE`: zona horaria usada para interpretar filtros (default `America/Santiago`).
- `ALLOWED_ORIGINS`, `ALLOW_CREDENTIALS`: configuracion CORS.
- `INIT_DEFAULT_USERS`: `true/false` para crear usuarios `admin` y `produccion` al iniciar.
- `MODBUS_*`: parametros del poller (`ENABLED`, `HOST`, `PORT`, `UNIT_ID`, `ADDR`, `NAME`, `ENDPOINT`, `WORD_ORDER`, `BYTE_ORDER`, `INTERVAL_MS`, `DEBUG`).

Ejemplo minimo:
```env
MONGO_URI=mongodb://localhost:27017
DB_NAME=groov
COLL_NAME=measurements
JWT_SECRET=cambia_este_valor
TIMEZONE=America/Santiago
ALLOWED_ORIGINS=http://localhost:5173
INIT_DEFAULT_USERS=true
```

### Puesta en marcha local
```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # En Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
La API queda expuesta en `http://localhost:8000`. Puedes verificar con `GET /health`.

### Datos y colecciones
Las mediciones se guardan en la coleccion `measurements` con la forma:
```json
{
  "ts": "2024-02-19T15:48:00Z",
  "device_ip": "192.168.1.10",
  "endpoint": "analogInputs",
  "name": "PESO_BASCULA",
  "value": 123.45,
  "type": "analog",
  "raw_value": 123.45,
  "is_nan": false
}
```
El poller Modbus inserta documentos identicos desde la lectura en tiempo real.

## Frontend (React + Vite + TypeScript)
### Caracteristicas destacadas
- Formulario de login con persistencia del token en `localStorage`.
- Dashboard admin con seleccion multiple de sensores, agrupamiento por prefijo o IP, graficos con Recharts y tabla de mediciones.
- Vista limitada para rol `user` enfocada en descargas de reportes.
- Polling inteligente de tiempo real (prioriza sensores seleccionados y rota el resto para evitar sobrecarga).
- Alternador de tema claro/oscuro y verificacion opcional de desfase horario con `worldtimeapi.org`.

### Variables Vite disponibles
Configura un archivo `frontend/.env` (o `.env.local`) con:
- `VITE_API_BASE`: URL base absoluta de la API (ej. `http://localhost:8000`).
- `VITE_API_PORT`: Puerto a usar cuando no se define `VITE_API_BASE` (default `8000`).
- `VITE_TZ`: Zona horaria esperada por el cliente (default `America/Santiago`).
- `VITE_TZ_CHECK`: `true/false` para habilitar la verificacion de desfase.
- `VITE_TZ_CHECK_URL`: endpoint alternativo para validar offset horario.

### Scripts de npm
```bash
cd frontend
npm install
npm run dev      # Servidor Vite (http://localhost:5173)
npm run build    # Genera produccion en frontend/dist
npm run preview  # Sirve la build estatico
npm run lint     # ESLint
```
El servidor de desarrollo Vite ya incluye proxy a la API (`/api` y `/auth`) configurable via `VITE_API_TARGET`.

## Autenticacion y roles
- Los tokens expiran a las 8 horas (`JWT_EXP_MIN`).
- Usuarios por defecto: `admin/admin` (rol admin) y `produccion/produccion` (rol user). Cambia las credenciales en produccion.
- `admin` accede a todas las vistas, tiempo real y endpoints protegidos (`/realtime`, `/modbus/*`).
- `user` puede consultar sensores, descargar reportes y ver listas sin tiempo real.

## Endpoints principales
- `GET /health`: ping de estado.
- `POST /auth/login`: autentica, devuelve token JWT y rol.
- `GET /auth/me`: valida token actual.
- `POST /check-user`: verifica si existe un usuario y si la contraseña matchea (uso diagnostico).
- `GET /sensors`: lista sensores registrados en `measurements`.
- `GET /latest?limit=n`: obtiene las ultimas `n` mediciones.
- `GET /measurements?name=...`: historico por sensor con filtros `start`, `end`, `endpoint`, `device_ip`, `tz`, `limit`.
- `GET /export/excel`: genera XLSX (requiere autenticacion).
- `GET /export/pdf`: genera PDF con graficos (requiere autenticacion).
- `POST /realtime`: entrega el ultimo valor por sensor (solo admin).
- `GET /modbus/status`: estado del poller Modbus (solo admin).
- `POST /modbus/once`: lee un valor puntual del dispositivo y opcionalmente lo inserta (solo admin).

## Poller Modbus
Al habilitar `MODBUS_ENABLED=true` el backend crea un thread que consulta registros holding (`unit`, `addr`) via `pymodbus`, interpreta el valor como entero con configuracion de orden de palabra y byte, y persiste el resultado. Ajusta `MODBUS_INTERVAL_MS` para controlar la frecuencia.

## Exportaciones
- `export_excel`: usa pandas + openpyxl/xlsxwriter para generar planillas con columnas comunes y el sensor como columna adicional.
- `export_pdf`: construye un PDF por sensor con graficos generados en matplotlib incrustados en ReportLab.

## Desarrollo y despliegue
- Construye el frontend con `npm run build` y sirve la carpeta `frontend/dist` tras un servidor web estatico.
- Para produccion del backend puedes usar `uvicorn backend.main:app --host 0.0.0.0 --port 8000` detras de un process manager (ej. systemd, supervisor o gunicorn + uvicorn workers).
- Considera configurar HTTPS, rotar `JWT_SECRET` y deshabilitar `INIT_DEFAULT_USERS` en ambientes productivos.

## Notas utiles
- Los filtros de fecha aceptan formatos ISO o locales; el backend los normaliza usando `python-dateutil` y la zona configurada.
- Si el desfase horario del equipo cliente es grande, el frontend mostrara una alerta (puede desactivarse con `VITE_TZ_CHECK=false`).
- El proyecto conserva archivos originales de la plantilla Vite (`App.css`, `index.css`); se pueden depurar en el futuro si no se usan.
