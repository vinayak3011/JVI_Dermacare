"""DermCare web application: authentication, scan history, and model inference."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DATABASE = DATA_DIR / "dermcare.sqlite3"
STATIC_DIR = ROOT / "static"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DEFAULT_MODEL = ROOT / "final_model_kaggle_version1" / "model.json"
SESSION_SECRET = secrets.token_bytes(32)
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MODEL = None
PREDICT_IMAGE = None

app = FastAPI(title="DermCare")
FRONTEND_DIST.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets") if (FRONTEND_DIST / "assets").exists() else None


def connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    database = sqlite3.connect(DATABASE)
    database.row_factory = sqlite3.Row
    return database


def initialise_database() -> None:
    with connection() as database:
        database.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                location TEXT NOT NULL,
                phone TEXT NOT NULL,
                age INTEGER NOT NULL,
                date_of_birth TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subject_name TEXT NOT NULL,
                image_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                predictions TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


initialise_database()


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return base64.urlsafe_b64encode(salt + digest).decode()


def password_matches(password: str, encoded: str) -> bool:
    raw = base64.urlsafe_b64decode(encoded.encode())
    return hmac.compare_digest(password_hash(password, raw[:16]), encoded)


def make_session(user_id: int) -> str:
    payload = f"{user_id}:{int(time.time()) + 60 * 60 * 24 * 7}"
    signature = hmac.new(SESSION_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()


def current_user(session: Annotated[str | None, Cookie()] = None) -> sqlite3.Row:
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in")
    try:
        user_id, expires, signature = base64.urlsafe_b64decode(session.encode()).decode().split(":")
        signed = f"{user_id}:{expires}"
        valid = hmac.compare_digest(hmac.new(SESSION_SECRET, signed.encode(), hashlib.sha256).hexdigest(), signature)
        if not valid or int(expires) < time.time():
            raise ValueError
    except (ValueError, IndexError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    with connection() as database:
        user = database.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def public_user(user: sqlite3.Row) -> dict[str, object]:
    return {key: user[key] for key in ("id", "name", "email", "location", "phone", "age", "date_of_birth")}


def public_scan(scan: sqlite3.Row) -> dict[str, object]:
    return {
        "id": scan["id"],
        "subject_name": scan["subject_name"],
        "original_filename": scan["original_filename"],
        "predictions": json.loads(scan["predictions"]),
        "created_at": scan["created_at"],
        "image_url": f"/uploads/{scan['image_path']}",
    }


@app.get("/")
def home() -> FileResponse:
    built_index = FRONTEND_DIST / "index.html"
    if built_index.exists():
        return FileResponse(built_index)
    return FileResponse(ROOT / "frontend" / "index.html")


@app.post("/api/auth/register")
def register(
    name: Annotated[str, Form()], email: Annotated[str, Form()], location: Annotated[str, Form()],
    phone: Annotated[str, Form()], age: Annotated[int, Form()], date_of_birth: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> dict[str, object]:
    if len(password) < 8 or not name.strip() or age < 1 or age > 120:
        raise HTTPException(status_code=400, detail="Enter valid details and an 8+ character password")
    try:
        with connection() as database:
            cursor = database.execute(
                "INSERT INTO users (name,email,location,phone,age,date_of_birth,password_hash) VALUES (?,?,?,?,?,?,?)",
                (name.strip(), email.strip().lower(), location.strip(), phone.strip(), age, date_of_birth, password_hash(password)),
            )
            user = database.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    return {"user": public_user(user)}


@app.post("/api/auth/login")
def login(email: Annotated[str, Form()], password: Annotated[str, Form()]) -> dict[str, object]:
    with connection() as database:
        user = database.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if not user or not password_matches(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {"user": public_user(user), "session": make_session(user["id"])}


@app.get("/api/auth/me")
def me(user: sqlite3.Row = Depends(current_user)) -> dict[str, object]:
    return {"user": public_user(user)}


@app.get("/api/scans")
def scans(user: sqlite3.Row = Depends(current_user)) -> list[dict[str, object]]:
    with connection() as database:
        records = database.execute("SELECT * FROM scans WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)).fetchall()
    return [public_scan(scan) for scan in records]


@app.post("/api/scans")
async def create_scan(
    image: Annotated[UploadFile, File()], subject_name: Annotated[str, Form()] = "My skin scan",
    user: sqlite3.Row = Depends(current_user),
) -> dict[str, object]:
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Please upload a JPG, PNG, or WebP image")
    contents = await image.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Images must be smaller than 10 MB")
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[image.content_type]
    filename = f"{secrets.token_hex(16)}{suffix}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_path = UPLOAD_DIR / filename
    image_path.write_bytes(contents)
    try:
        global MODEL, PREDICT_IMAGE
        if MODEL is None:
            if not DEFAULT_MODEL.is_file():
                raise RuntimeError("The bundled model is missing")
            from predict import load_tfjs_model, predict_image

            MODEL = load_tfjs_model(DEFAULT_MODEL)
            PREDICT_IMAGE = predict_image
        if PREDICT_IMAGE is None:
            raise RuntimeError("The prediction function is unavailable")
        predictions = PREDICT_IMAGE(MODEL, image_path)
    except Exception as error:
        image_path.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=f"The scan model is unavailable: {error}")
    with connection() as database:
        cursor = database.execute(
            "INSERT INTO scans (user_id,subject_name,image_path,original_filename,predictions) VALUES (?,?,?,?,?)",
            (user["id"], subject_name.strip() or "My skin scan", filename, image.filename or filename, json.dumps(predictions)),
        )
        scan = database.execute("SELECT * FROM scans WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return public_scan(scan)


@app.patch("/api/scans/{scan_id}")
def rename_scan(scan_id: int, subject_name: Annotated[str, Form()], user: sqlite3.Row = Depends(current_user)) -> dict[str, object]:
    with connection() as database:
        database.execute("UPDATE scans SET subject_name = ? WHERE id = ? AND user_id = ?", (subject_name.strip() or "My skin scan", scan_id, user["id"]))
        scan = database.execute("SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, user["id"])).fetchone()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return public_scan(scan)


@app.delete("/api/scans/{scan_id}")
def delete_scan(scan_id: int, user: sqlite3.Row = Depends(current_user)) -> dict[str, bool]:
    with connection() as database:
        scan = database.execute("SELECT * FROM scans WHERE id = ? AND user_id = ?", (scan_id, user["id"])).fetchone()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        database.execute("DELETE FROM scans WHERE id = ?", (scan_id,))
    (UPLOAD_DIR / scan["image_path"]).unlink(missing_ok=True)
    return {"deleted": True}


@app.get("/uploads/{filename}")
def uploaded_image(filename: str, user: sqlite3.Row = Depends(current_user)) -> FileResponse:
    with connection() as database:
        exists = database.execute("SELECT 1 FROM scans WHERE image_path = ? AND user_id = ?", (filename, user["id"])).fetchone()
    path = UPLOAD_DIR / filename
    if not exists or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)