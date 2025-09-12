# main.py
import os, hmac, json, time, base64, hashlib, asyncio, threading
from datetime import datetime, timezone
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, Query, Depends, Header, status, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, ASCENDING, DESCENDING
from dateutil import parser as dateparser
import pandas as pd

from export_utils import build_dataframe, to_excel_bytes, make_pdf_with_charts
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# ==========================
# Configuración / Mongo
# ==========================
# Cargar variables de entorno desde .env si existe
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
DB_NAME   = os.getenv("DB_NAME", "groov")
COLL_NAME = os.getenv("COLL_NAME", "measurements")

client = MongoClient(MONGO_URI, appname="groov-dashboard")
coll   = client[DB_NAME][COLL_NAME]
users  = client[DB_NAME]["users"]

app = FastAPI(title="Groov Dashboard API")

# Zona horaria objetivo por defecto (Chile)
DEFAULT_TZ = os.getenv("TIMEZONE", "America/Santiago")

# CORS: por defecto permitir cualquier origen (no usamos cookies),
# o restringir vía variables de entorno ALLOWED_ORIGINS (separadas por coma)
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()
if _allowed_origins_env:
    _origins = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
    _allow_credentials = os.getenv("ALLOW_CREDENTIALS", "false").lower() == "true"
else:
    # wildcard para todas las IPs/hosts; desactivamos credentials para que FastAPI acepte "*"
    _origins = ["*"]
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================
# Seguridad (hash + JWT)
# ==========================
JWT_SECRET  = os.getenv("JWT_SECRET", "ingelsa$2025$groov#dashboard#secret#b7e1c5a9a51f4e32a56b97b1a98f37f0")
JWT_ISS     = "groov-dashboard"
JWT_EXP_MIN = 8 * 60

PBKDF2_ITER = 160_000
# IMPORTANTE: en Mongo podrías tener "pbkdf2" o "pbkdf2_sha256".
# Dejamos el valor por defecto en "pbkdf2" y al validar aceptamos ambos.
HASH_ALG_DEFAULT = "pbkdf2"

def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def make_password(password: str, salt: Optional[bytes] = None) -> str:
    """
    Genera hashes estilo: pbkdf2$<iter>$<salt_hex>$<digest_hex>
    """
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITER)
    return f"{HASH_ALG_DEFAULT}${PBKDF2_ITER}${salt.hex()}${dk.hex()}"

def check_password(password: str, stored: str) -> bool:
    """
    Acepta tanto 'pbkdf2$...' como 'pbkdf2_sha256$...'
    """
    try:
        alg, it, salt_hex, dk_hex = stored.split("$", 3)
        if alg not in ("pbkdf2", "pbkdf2_sha256"):
            return False
        it = int(it)
        salt = bytes.fromhex(salt_hex)
        dk2  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, it)
        return hmac.compare_digest(dk2.hex(), dk_hex)
    except Exception:
        return False

def sign_jwt(payload: dict, exp_minutes: int = JWT_EXP_MIN) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    body = {**payload, "iss": JWT_ISS, "iat": now, "exp": now + exp_minutes * 60}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(body,   separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    s = _b64url(sig)
    return f"{h}.{p}.{s}"

def verify_jwt(token: str) -> dict:
    try:
        h, p, s = token.split(".")
        signing_input = f"{h}.{p}".encode()
        sig = _b64url_decode(s)
        mac = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, mac):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(p))
        if payload.get("iss") != JWT_ISS:
            raise ValueError("bad iss")
        if int(time.time()) >= int(payload.get("exp", 0)):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

# ==========================
# Usuarios por defecto
# ==========================
def ensure_default_users():
    users.create_index([("username", ASCENDING)], unique=True, background=True)
    # Permite desactivar la creación de usuarios por defecto en producción
    if os.getenv("INIT_DEFAULT_USERS", "true").lower() not in ("1", "true", "yes", "y"):  # pragma: no cover
        return
    if not users.find_one({"username": "admin"}):
        users.insert_one({"username": "admin", "role": "admin", "password": make_password("admin")})
    if not users.find_one({"username": "produccion"}):
        users.insert_one({"username": "produccion", "role": "user", "password": make_password("produccion")})

@app.on_event("startup")
def _startup():
    ensure_default_users()
    try:
        coll.create_index([("name", ASCENDING), ("ts", DESCENDING)], background=True)
        coll.create_index([("endpoint", ASCENDING), ("name", ASCENDING)], background=True)
        coll.create_index([("ts", DESCENDING)], background=True)
    except Exception:
        pass
    # Lanzar poller Modbus si está habilitado
    try:
        if os.getenv("MODBUS_ENABLED", "false").lower() in ("1", "true", "yes", "y"):  # pragma: no cover
            print(_modbus_config_string(), flush=True)
            _start_modbus_thread()
            print("[MODBUS] Poller habilitado (thread)", flush=True)
    except Exception as e:  # pragma: no cover
        print(f"[MODBUS] No se pudo iniciar poller: {e}", flush=True)

@app.on_event("shutdown")
def _shutdown():  # pragma: no cover
    # Cancelar poller si está corriendo
    try:
        _stop_modbus_thread()
    except Exception:
        pass

# ==========================
# Poller Modbus (báscula)
# ==========================
_modbus_thread = None
_modbus_stop_evt: threading.Event | None = None
_modbus_last_err: Optional[str] = None
_modbus_last_ok: Optional[datetime] = None
_modbus_last_value: Optional[int] = None

def _modbus_config_string() -> str:
    host = os.getenv("MODBUS_HOST", "192.168.100.204").strip()
    port = int(os.getenv("MODBUS_PORT", "502"))
    unit = int(os.getenv("MODBUS_UNIT_ID", "1"))
    addr = int(os.getenv("MODBUS_ADDR", "0"))
    name = os.getenv("MODBUS_NAME", "PESO_BASCULA").strip() or "PESO_BASCULA"
    endpoint = os.getenv("MODBUS_ENDPOINT", "analogInputs").strip() or "analogInputs"
    word_o = (os.getenv("MODBUS_WORD_ORDER", "big") or "big").lower()
    byte_o = (os.getenv("MODBUS_BYTE_ORDER", "big") or "big").lower()
    return f"[MODBUS] Config host={host} port={port} unit={unit} addr={addr} name={name} endpoint={endpoint} word_order={word_o} byte_order={byte_o}"

def _start_modbus_thread():  # pragma: no cover
    global _modbus_thread, _modbus_stop_evt
    if _modbus_thread and _modbus_thread.is_alive():
        return
    _modbus_stop_evt = threading.Event()
    _modbus_thread = threading.Thread(target=_run_modbus_weight_poller_sync, args=(_modbus_stop_evt,), daemon=True)
    _modbus_thread.start()

def _stop_modbus_thread():  # pragma: no cover
    global _modbus_thread, _modbus_stop_evt
    try:
        if _modbus_stop_evt:
            _modbus_stop_evt.set()
        if _modbus_thread and _modbus_thread.is_alive():
            _modbus_thread.join(timeout=2.0)
    finally:
        _modbus_thread = None
        _modbus_stop_evt = None

def _run_modbus_weight_poller_sync(stop_evt: threading.Event):  # pragma: no cover
    global _modbus_last_ok, _modbus_last_value, _modbus_last_err
    try:
        from pymodbus.client import ModbusTcpClient
    except Exception as e:
        print(f"[MODBUS] pymodbus no disponible: {e}. Instala 'pymodbus' y habilita MODBUS_ENABLED.", flush=True)
        return

    host = os.getenv("MODBUS_HOST", "192.168.100.204").strip()
    port = int(os.getenv("MODBUS_PORT", "502"))
    unit = int(os.getenv("MODBUS_UNIT_ID", "1"))
    # NOTA: modpoll usa 1-based en -r; pymodbus usa 0-based. Ajusta aquí segun tu mapeo
    addr = int(os.getenv("MODBUS_ADDR", "0"))
    interval_ms = int(os.getenv("MODBUS_INTERVAL_MS", "1000"))
    interval = max(0.2, interval_ms / 1000.0)
    name = os.getenv("MODBUS_NAME", "PESO_BASCULA").strip() or "PESO_BASCULA"
    endpoint = os.getenv("MODBUS_ENDPOINT", "analogInputs").strip() or "analogInputs"
    word_o = (os.getenv("MODBUS_WORD_ORDER", "big") or "big").lower()
    byte_o = (os.getenv("MODBUS_BYTE_ORDER", "big") or "big").lower()
    debug = (os.getenv("MODBUS_DEBUG", "false") or "false").lower() in ("1","true","yes","y")

    word_big = True if word_o.startswith("b") else False
    byte_big = True if byte_o.startswith("b") else False

    client = ModbusTcpClient(host=host, port=port, timeout=2)
    print(f"[MODBUS] Thread iniciado -> {host}:{port} unit={unit} addr={addr}", flush=True)

    while not stop_evt.is_set():
        try:
            try:
                if not getattr(client, 'connected', False):
                    client.connect()
            except Exception:
                # algunas versiones no exponen .connected, intentamos conectar igual
                try:
                    client.connect()
                except Exception:
                    pass

            # Enviar siempre el unit (ID de esclavo).
            try:
                rr = client.read_holding_registers(address=addr, count=2, unit=unit)
            except TypeError:
                # fallback: algunas versiones usan 'slave'
                try:
                    rr = client.read_holding_registers(address=addr, count=2, slave=unit)
                except TypeError:
                    # último recurso: sin unit
                    rr = client.read_holding_registers(address=addr, count=2)
            if rr is None or getattr(rr, 'isError', lambda: True)():
                raise RuntimeError(f"Lectura fallo: {rr}")
            regs = getattr(rr, 'registers', None)
            if not regs or len(regs) < 2:
                raise RuntimeError(f"Respuesta inválida regs={regs}")

            # Decodificar int32 firmado manualmente para evitar dependencias de payload
            def _i32_from_regs(r0: int, r1: int) -> int:
                r0 &= 0xFFFF; r1 &= 0xFFFF
                if byte_big:
                    b0b1 = [(r0 >> 8) & 0xFF, r0 & 0xFF]
                    b2b3 = [(r1 >> 8) & 0xFF, r1 & 0xFF]
                else:
                    b0b1 = [r0 & 0xFF, (r0 >> 8) & 0xFF]
                    b2b3 = [r1 & 0xFF, (r1 >> 8) & 0xFF]
                if word_big:
                    bs = bytes(b0b1 + b2b3)
                else:
                    bs = bytes(b2b3 + b0b1)
                return int.from_bytes(bs, byteorder='big', signed=True)

            value = _i32_from_regs(regs[0], regs[1])

            if debug:
                print(f"[MODBUS] regs={regs} value={value}", flush=True)

            doc = {
                "ts": datetime.utcnow(),
                "device_ip": host,
                "endpoint": endpoint,
                "name": name,
                "value": value,
                "raw_value": value,
                "is_nan": False,
                "type": "analog",
            }
            coll.insert_one(doc)
            # estado
            try:
                _modbus_last_ok = datetime.utcnow()
                _modbus_last_value = int(value)
                _modbus_last_err = None
            except Exception:
                pass
        except Exception as e:
            print(f"[MODBUS] Error lectura/inserción: {e}", flush=True)
            try:
                _modbus_last_err = str(e)
            except Exception:
                pass
            time.sleep(min(5.0, interval))
        finally:
            # No uses sleep bloqueante si se requiere apagado rápido
            stop_evt.wait(interval)
    try:
        client.close()
    except Exception:
        pass

# (endpoints de modbus se agregan más abajo tras dependencias)

# ==========================
# Dependencias de seguridad
# ==========================
def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Falta token")
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_jwt(token)
    return {"username": payload.get("sub"), "role": payload.get("role")}

def require_role(allowed: List[str]):
    def _dep(user=Depends(get_current_user)):
        if user["role"] not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No autorizado")
        return user
    return _dep

ReadRole  = Depends(require_role(["user", "admin"]))
AdminRole = Depends(require_role(["admin"]))

# ==========================
# Helpers de tiempo
# ==========================
def parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return dateparser.parse(s)
    except Exception:
        return None

def _to_utc_iso_z(dt: Optional[datetime]) -> Optional[str]:
    """Normaliza a UTC y serializa ISO con sufijo Z.
    Si el datetime es naive, se asume UTC (compatibilidad hacia atrás).
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        try:
            dt = dateparser.parse(dt)
        except Exception:
            return str(dt)
    if not isinstance(dt, datetime):
        return str(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

def _to_utc(dt: Optional[datetime], tzname: str) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        # interpreta naive como hora local del tz solicitado
        dt = dt.replace(tzinfo=ZoneInfo(tzname))
    return dt.astimezone(timezone.utc)

def time_filter(start: Optional[str], end: Optional[str], tzname: Optional[str] = None) -> dict:
    tzname = tzname or DEFAULT_TZ
    sdt = parse_dt(start); edt = parse_dt(end)
    tf: dict = {}
    if sdt or edt:
        tf["ts"] = {}
        if sdt: tf["ts"]["$gte"] = _to_utc(sdt, tzname)
        if edt: tf["ts"]["$lte"] = _to_utc(edt, tzname)
    return tf

# ==========================
# Salud / Auth
# ==========================
@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}

@app.post("/auth/login")
def login(data: Dict[str, str]):
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "")

    # --- logs de diagnóstico (se ven en consola uvicorn) ---
    u = users.find_one({"username": username})
    if not u:
        print(f"[AUTH] user not found: {username}", flush=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    if not check_password(password, u.get("password", "")):
        print(f"[AUTH] bad password for: {username}", flush=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")

    token = sign_jwt({"sub": username, "role": u["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": u["role"],
        "username": username,
        "expires_in": 60 * JWT_EXP_MIN,
    }

@app.get("/auth/me")
def auth_me(user=ReadRole):
    return {"username": user["username"], "role": user["role"]}

# ==========================
# Endpoints de datos
# ==========================
@app.get("/sensors")
def list_sensors(endpoint: Optional[str] = None, _user=ReadRole):
    match = {}
    if endpoint:
        match["endpoint"] = endpoint
    names = coll.distinct("name", match)
    return {"count": len(names), "items": sorted([n for n in names if n])}

@app.get("/latest")
def latest_values(limit: int = 100, _user=ReadRole):
    cur = coll.find({}, {"_id": 0}).sort("ts", -1).limit(limit)
    docs = list(cur)
    # Serializa timestamps a UTC-Z para el frontend
    for d in docs:
        if "ts" in d:
            d["ts"] = _to_utc_iso_z(d["ts"])  # type: ignore
    return docs

@app.get("/measurements")
def measurements(
    name: str = Query(..., description="Nombre del sensor"),
    start: Optional[str] = Query(None), end: Optional[str] = Query(None),
    tz: Optional[str] = Query(None, description="Zona horaria (e.g. America/Santiago)"),
    endpoint: Optional[str] = Query(None), device_ip: Optional[str] = None,
    limit: int = 20, _user=ReadRole,
):
    q = {"name": name}
    if endpoint:
        q["endpoint"] = endpoint
    if device_ip:
        q["device_ip"] = device_ip
    # Aplicar filtro de tiempo interpretando start/end en la zona indicada
    tf = time_filter(start, end, tz or DEFAULT_TZ)
    q.update(tf)
    cur  = coll.find(q, {"_id": 0}).sort("ts", -1).limit(limit)
    docs = list(cur); docs.reverse()
    for d in docs:
        if "ts" in d:
            d["ts"] = _to_utc_iso_z(d["ts"])  # type: ignore
    return docs

# ==========================
# Endpoint temporal para verificar usuario
# ==========================
from fastapi import Body

@app.post("/check-user")
def check_user(data: dict = Body(...)):
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    u = users.find_one({"username": username})
    if not u:
        return {"exists": False, "password_ok": False}
    try:
        alg, it, salt_hex, dk_hex = u["password"].split("$", 3)
        dk2 = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(it))
        ok = hmac.compare_digest(dk2.hex(), dk_hex)
    except Exception:
        ok = False
    return {"exists": True, "password_ok": ok}


@app.get("/export/excel")
def export_excel(
    names: Optional[List[str]] = Query(default=None, description="Lista de sensores"),
    start: Optional[str] = None, end: Optional[str] = None,
    tz: Optional[str] = Query(None, description="Zona horaria para exportación"),
    _user=ReadRole,
):
    if not names:
        recent = list(coll.aggregate([{"$sort": {"ts": -1}}, {"$group": {"_id": "$name"}}, {"$limit": 10}]))
        names = [d["_id"] for d in recent if d.get("_id")]
    tzname = tz or DEFAULT_TZ
    frames = []
    tf = time_filter(start, end, tzname)
    for nm in names:
        q = {"name": nm, **tf}
        rows = list(coll.find(q, {"_id": 0}).sort("ts", 1))
        # Convertir timestamps a hora local del timezone solicitado, sin tzinfo
        def to_local_naive(d):
            if d is None:
                return d
            if isinstance(d, str):
                try:
                    d = dateparser.parse(d)
                except Exception:
                    return d
            if not isinstance(d, datetime):
                return d
            if d.tzinfo is None:
                # consideramos que viene en UTC (compatibilidad)
                d = d.replace(tzinfo=timezone.utc)
            d = d.astimezone(ZoneInfo(tzname))
            return d.replace(tzinfo=None)
        for r in rows:
            if "ts" in r:
                r["ts"] = to_local_naive(r["ts"])  # type: ignore
        df = build_dataframe(rows)
        df.insert(0, "sensor", nm)
        frames.append(df)
    df_all = pd.concat(frames, ignore_index=True) if frames else build_dataframe([])
    data = to_excel_bytes(df_all)
    filename = f"export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/export/pdf")
def export_pdf(
    names: Optional[List[str]] = Query(default=None, description="Lista de sensores"),
    start: Optional[str] = None, end: Optional[str] = None,
    tz: Optional[str] = Query(None, description="Zona horaria para exportación"),
    _user=ReadRole,
):
    if not names:
        recent = list(coll.aggregate([{"$sort": {"ts": -1}}, {"$group": {"_id": "$name"}}, {"$limit": 10}]))
        names = [d["_id"] for d in recent if d.get("_id")]
    tzname = tz or DEFAULT_TZ
    datasets = []
    tf = time_filter(start, end, tzname)
    for nm in names:
        q = {"name": nm, **tf}
        rows = list(coll.find(q, {"_id": 0}).sort("ts", 1))
        def to_local_naive(d):
            if d is None:
                return d
            if isinstance(d, str):
                try:
                    d = dateparser.parse(d)
                except Exception:
                    return d
            if not isinstance(d, datetime):
                return d
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            d = d.astimezone(ZoneInfo(tzname))
            return d.replace(tzinfo=None)
        for r in rows:
            if "ts" in r:
                r["ts"] = to_local_naive(r["ts"])  # type: ignore
        df = build_dataframe(rows)
        datasets.append((nm, df))
    pdf_bytes = make_pdf_with_charts(datasets)
    filename = f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# --- Acepta GET y POST en /realtime para evitar 405 ---
@app.api_route("/realtime", methods=["GET", "POST"])
def realtime(
    names: Optional[List[str]] = Query(None),
    endpoint: Optional[str] = None,
    device_ip: Optional[str] = None,
    body: dict = Body(default=None),
    _user=AdminRole,
) -> Dict[str, dict]:
    # Si viene POST con JSON, lo priorizamos
    if body:
        names     = body.get("names") or names
        endpoint  = body.get("endpoint") or endpoint
        device_ip = body.get("device_ip") or device_ip

    q: dict = {}
    if names:    q["name"]      = {"$in": names}
    if endpoint: q["endpoint"]  = endpoint
    if device_ip:q["device_ip"] = device_ip

    # Optimizamos el sort para aprovechar el índice compuesto (name asc, ts desc)
    pipeline = [
        {"$match": q},
        {"$sort": {"name": 1, "ts": -1}},
        {"$group": {
            "_id": "$name",
            "ts":       {"$first": "$ts"},
            "value":    {"$first": "$value"},
            "type":     {"$first": "$type"},
            "device_ip":{"$first": "$device_ip"},
            "endpoint": {"$first": "$endpoint"},
        }},
    ]
    docs = list(coll.aggregate(pipeline))
    return {
        d["_id"]: {
            "ts": _to_utc_iso_z(d.get("ts")),
            "value": d.get("value"),
            "type": d.get("type"),
            "device_ip": d.get("device_ip"),
            "endpoint": d.get("endpoint"),
        } for d in docs if d.get("_id")
    }

# ==========================
# Modbus: estado y prueba (solo admin)
# ==========================
@app.get("/modbus/status")
def modbus_status(_user=AdminRole):
    running = bool(_modbus_thread and _modbus_thread.is_alive())
    enabled = os.getenv("MODBUS_ENABLED", "false").lower() in ("1","true","yes","y")
    return {
        "enabled": enabled,
        "running": running,
        "config": _modbus_config_string(),
        "last_ok": _to_utc_iso_z(_modbus_last_ok),
        "last_value": _modbus_last_value,
        "last_err": _modbus_last_err,
    }

@app.post("/modbus/once")
def modbus_once(
    insert: bool = True,
    addr: Optional[int] = None,
    unit: Optional[int] = None,
    word_order: Optional[str] = None,
    byte_order: Optional[str] = None,
    _user=AdminRole,
):
    try:
        from pymodbus.client import ModbusTcpClient
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pymodbus no disponible: {e}")

    host = os.getenv("MODBUS_HOST", "192.168.100.204").strip()
    port = int(os.getenv("MODBUS_PORT", "502"))
    unit_id = unit if unit is not None else int(os.getenv("MODBUS_UNIT_ID", "1"))
    base_addr = addr if addr is not None else int(os.getenv("MODBUS_ADDR", "0"))
    name = os.getenv("MODBUS_NAME", "PESO_BASCULA").strip() or "PESO_BASCULA"
    endpoint = os.getenv("MODBUS_ENDPOINT", "analogInputs").strip() or "analogInputs"
    word_o = (word_order or os.getenv("MODBUS_WORD_ORDER", "big") or "big").lower()
    byte_o = (byte_order or os.getenv("MODBUS_BYTE_ORDER", "big") or "big").lower()
    word_big = True if word_o.startswith("b") else False
    byte_big = True if byte_o.startswith("b") else False

    cli = ModbusTcpClient(host=host, port=port, timeout=2)
    if not cli.connect():
        raise HTTPException(status_code=502, detail="No se pudo conectar al dispositivo Modbus")
    # Intentar sin kwargs y fijando unit al cliente
    if hasattr(cli, 'unit_id'):
        try:
            setattr(cli, 'unit_id', unit_id)
        except Exception:
            pass
    if hasattr(cli, 'unit'):
        try:
            setattr(cli, 'unit', unit_id)
        except Exception:
            pass
    try:
        rr = cli.read_holding_registers(address=base_addr, count=2, unit=unit_id)
    except TypeError:
        try:
            rr = cli.read_holding_registers(address=base_addr, count=2, slave=unit_id)
        except TypeError:
            rr = cli.read_holding_registers(address=base_addr, count=2)
    if rr is None or getattr(rr, 'isError', lambda: True)():
        raise HTTPException(status_code=502, detail=f"Lectura fallida: {rr}")
    regs = getattr(rr, 'registers', None)
    if not regs or len(regs) < 2:
        raise HTTPException(status_code=502, detail=f"Respuesta inválida regs={regs}")
    # Decodificar manualmente int32 firmado
    r0, r1 = regs[0] & 0xFFFF, regs[1] & 0xFFFF
    if byte_big:
        b0b1 = [(r0 >> 8) & 0xFF, r0 & 0xFF]
        b2b3 = [(r1 >> 8) & 0xFF, r1 & 0xFF]
    else:
        b0b1 = [r0 & 0xFF, (r0 >> 8) & 0xFF]
        b2b3 = [r1 & 0xFF, (r1 >> 8) & 0xFF]
    bs = bytes(b0b1 + b2b3) if word_big else bytes(b2b3 + b0b1)
    value = int.from_bytes(bs, 'big', signed=True)
    resp = {"regs": regs, "value": value, "config": _modbus_config_string()}
    if insert:
        doc = {
            "ts": datetime.utcnow(),
            "device_ip": host,
            "endpoint": endpoint,
            "name": name,
            "value": int(value),
            "raw_value": int(value),
            "is_nan": False,
            "type": "analog",
        }
        coll.insert_one(doc)
        resp["inserted"] = True
    try:
        cli.close()
    except Exception:
        pass
    return resp
