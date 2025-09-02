# main.py
import os, hmac, json, time, base64, hashlib
from datetime import datetime
from typing import List, Optional, Dict

from fastapi import FastAPI, HTTPException, Query, Depends, Header, status, Body
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, ASCENDING, DESCENDING
from dateutil import parser as dateparser
import pandas as pd

from export_utils import build_dataframe, to_excel_bytes, make_pdf_with_charts

# ==========================
# Configuración / Mongo
# ==========================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
DB_NAME   = os.getenv("DB_NAME", "groov")
COLL_NAME = os.getenv("COLL_NAME", "measurements")

client = MongoClient(MONGO_URI, appname="groov-dashboard")
coll   = client[DB_NAME][COLL_NAME]
users  = client[DB_NAME]["users"]

app = FastAPI(title="Groov Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://100.120.139.122:5173",
        "http://192.168.100.250:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================
# Seguridad (hash + JWT)
# ==========================
JWT_SECRET  = "ingelsa$2025$groov#dashboard#secret#b7e1c5a9a51f4e32a56b97b1a98f37f0"
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

def time_filter(start: Optional[str], end: Optional[str]) -> dict:
    sdt = parse_dt(start); edt = parse_dt(end)
    tf: dict = {}
    if sdt or edt:
        tf["ts"] = {}
        if sdt: tf["ts"]["$gte"] = sdt
        if edt: tf["ts"]["$lte"] = edt
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
    return list(cur)

@app.get("/measurements")
def measurements(
    name: str = Query(..., description="Nombre del sensor"),
    start: Optional[str] = Query(None), end: Optional[str] = Query(None),
    endpoint: Optional[str] = Query(None), device_ip: Optional[str] = None,
    limit: int = 20, _user=ReadRole,
):
    q = {"name": name}
    if endpoint: q["endpoint"] = endpoint
    if device_ip: q["device_ip"] = device_ip
    if start or end:
        q["ts"] = {}
        if start: q["ts"]["$gte"] = parse_dt(start)
        if end:   q["ts"]["$lte"] = parse_dt(end)
    cur  = coll.find(q, {"_id": 0}).sort("ts", -1).limit(limit)
    docs = list(cur); docs.reverse()
    return docs

@app.get("/export/excel")
def export_excel(
    names: Optional[List[str]] = Query(default=None, description="Lista de sensores"),
    start: Optional[str] = None, end: Optional[str] = None,
    _user=AdminRole,
):
    if not names:
        recent = list(coll.aggregate([{"$sort": {"ts": -1}}, {"$group": {"_id": "$name"}}, {"$limit": 10}]))
        names = [d["_id"] for d in recent if d.get("_id")]
    frames = []
    tf = time_filter(start, end)
    for nm in names:
        q = {"name": nm, **tf}
        rows = list(coll.find(q, {"_id": 0}).sort("ts", 1))
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
    _user=AdminRole,
):
    if not names:
        recent = list(coll.aggregate([{"$sort": {"ts": -1}}, {"$group": {"_id": "$name"}}, {"$limit": 10}]))
        names = [d["_id"] for d in recent if d.get("_id")]
    datasets = []
    tf = time_filter(start, end)
    for nm in names:
        q = {"name": nm, **tf}
        rows = list(coll.find(q, {"_id": 0}).sort("ts", 1))
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
    _user=ReadRole,
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

    pipeline = [
        {"$match": q},
        {"$sort": {"ts": -1}},
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
            "ts": d.get("ts"), "value": d.get("value"),
            "type": d.get("type"), "device_ip": d.get("device_ip"),
            "endpoint": d.get("endpoint"),
        } for d in docs if d.get("_id")
    }
