from __future__ import annotations

import asyncio
import base64
import binascii
import copy
import io
import json
import logging
import os
import re
import os
import secrets
import shutil
import socket
import sqlite3
import string
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


FROZEN = bool(getattr(sys, "frozen", False))
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if FROZEN:
    _appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    DATA_DIR = _appdata / "MudengTRPG"
    _legacy_dir = _appdata / "MingDengTRPG"
    if not DATA_DIR.exists() and _legacy_dir.exists():
        shutil.copytree(_legacy_dir, DATA_DIR)
else:
    DATA_DIR = BASE_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "trpg.sqlite3"
MAP_ASSETS_DIR = DATA_DIR / "map-assets"
MAP_ASSETS_DIR.mkdir(exist_ok=True)
RULES_DIR = BASE_DIR / "rules"
RULES_DIR.mkdir(exist_ok=True)
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
TRANSCRIPTS_DIR.mkdir(exist_ok=True)
AI_CONFIG_PATH = DATA_DIR / "ai_config.json"

DEFAULT_AI_ENDPOINT = "https://api.deepseek.com"
DEFAULT_AI_MODEL = "deepseek-flash"

app = FastAPI(title="跑团主持台 API", version="0.2.0")
app.mount("/rules", StaticFiles(directory=str(RULES_DIR)), name="rules")

ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
logger = logging.getLogger("trpg.ai")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_handler)
    logger.propagate = False


class CreateRoomRequest(BaseModel):
    name: str = Field(default="未命名战役", max_length=100)
    host_name: str = Field(default="主持人", max_length=60)
    device_id: str = Field(default="", max_length=200)
    state: dict[str, Any] = Field(default_factory=dict)


class JoinRoomRequest(BaseModel):
    name: str = Field(default="玩家", max_length=60)
    player_id: str = Field(default="", max_length=100)
    character_id: str = Field(default="", max_length=100)
    character_snapshot: dict[str, Any] = Field(default_factory=dict)
    device_id: str = Field(default="", max_length=200)


class MapAssetRequest(BaseModel):
    name: str = Field(default="map", max_length=200)
    data: str = Field(default="")


class SnapshotRestoreRequest(BaseModel):
    participant_id: str


class SwitchCharacterRequest(BaseModel):
    participant_id: str
    character_id: str = Field(default="", max_length=100)
    character_snapshot: dict[str, Any] = Field(default_factory=dict)


class DeviceBootstrapRequest(BaseModel):
    device_id: str = Field(default="", max_length=200)
    name: str = Field(default="未命名设备", max_length=60)


class StateRequest(BaseModel):
    participant_id: str
    state: dict[str, Any]
    revision: int = 0


class EventRequest(BaseModel):
    participant_id: str
    event_type: str
    state: dict[str, Any] = Field(default_factory=dict)


class CampaignSaveRequest(BaseModel):
    id: str | None = Field(default=None, max_length=40)
    name: str = Field(default="未命名存档", max_length=120)
    summary: str = Field(default="", max_length=300)
    state: dict[str, Any] = Field(default_factory=dict)
    auto: bool = False


class ModuleLibraryRequest(BaseModel):
    title: str = Field(default="未命名模组", max_length=200)
    module: dict[str, Any] = Field(default_factory=dict)


class ParticipantUpdateRequest(BaseModel):
    participant_id: str
    name: str | None = Field(default=None, max_length=60)
    player_id: str | None = Field(default=None, max_length=100)


class ParticipantRemoveRequest(BaseModel):
    participant_id: str


class ActionRequestCreate(BaseModel):
    participant_id: str
    action_type: str = Field(default="skill-check", max_length=60)
    payload: dict[str, Any] = Field(default_factory=dict)


class ActionRequestUpdate(BaseModel):
    participant_id: str
    status: str = Field(default="resolved", max_length=40)
    response: str = Field(default="", max_length=2000)


class AiChatMessage(BaseModel):
    role: str = Field(default="user", max_length=20)
    content: str = Field(default="", max_length=60000)


class AiChatRequest(BaseModel):
    messages: list[AiChatMessage] = Field(default_factory=list)
    model: str = Field(default="", max_length=120)
    temperature: float | None = None
    jsonMode: bool = False
    disableThinking: bool = False
    maxTokens: int | None = Field(default=None, ge=64, le=8192)


class AiConfigUpdate(BaseModel):
    endpoint: str | None = Field(default=None, max_length=300)
    model: str | None = Field(default=None, max_length=120)
    apiKey: str | None = Field(default=None, max_length=300)
    temperature: float | None = None


class RoomSocketManager:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = {}

    async def connect(self, room_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.rooms.setdefault(room_id.upper(), set()).add(websocket)

    def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        sockets = self.rooms.get(room_id.upper())
        if not sockets:
            return
        sockets.discard(websocket)
        if not sockets:
            self.rooms.pop(room_id.upper(), None)

    async def broadcast(self, room_id: str, message: dict[str, Any]) -> None:
        sockets = list(self.rooms.get(room_id.upper(), set()))
        for socket in sockets:
            try:
                await socket.send_json(message)
            except Exception:
                self.disconnect(room_id, socket)


socket_manager = RoomSocketManager()

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_ai_config() -> dict[str, Any]:
    """Provider settings live on the server so the browser never needs the key."""
    config: dict[str, Any] = {
        "endpoint": DEFAULT_AI_ENDPOINT,
        "model": DEFAULT_AI_MODEL,
        "apiKey": "",
        "temperature": 0.7,
    }
    try:
        if AI_CONFIG_PATH.exists():
            saved = json.loads(AI_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                config.update({key: saved[key] for key in config if key in saved})
    except (OSError, ValueError):
        pass
    for env_key, field in (
        ("TRPG_AI_ENDPOINT", "endpoint"),
        ("TRPG_AI_MODEL", "model"),
        ("TRPG_AI_API_KEY", "apiKey"),
    ):
        value = os.environ.get(env_key)
        if value:
            config[field] = value
    try:
        env_temperature = os.environ.get("TRPG_AI_TEMPERATURE")
        if env_temperature:
            config["temperature"] = float(env_temperature)
    except ValueError:
        pass
    config["endpoint"] = str(config.get("endpoint") or DEFAULT_AI_ENDPOINT).strip().rstrip("/")
    config["model"] = str(config.get("model") or DEFAULT_AI_MODEL).strip()
    config["apiKey"] = str(config.get("apiKey") or "").strip()
    try:
        config["temperature"] = max(0.0, min(2.0, float(config.get("temperature", 0.7))))
    except (TypeError, ValueError):
        config["temperature"] = 0.7
    return config


def save_ai_config(config: dict[str, Any]) -> None:
    payload = {
        "endpoint": config.get("endpoint", DEFAULT_AI_ENDPOINT),
        "model": config.get("model", DEFAULT_AI_MODEL),
        "apiKey": config.get("apiKey", ""),
        "temperature": config.get("temperature", 0.7),
    }
    AI_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ai_public_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_ai_config()
    key = config.get("apiKey", "")
    return {
        "endpoint": config.get("endpoint", DEFAULT_AI_ENDPOINT),
        "model": config.get("model", DEFAULT_AI_MODEL),
        "temperature": config.get("temperature", 0.7),
        "hasKey": bool(key),
        "keyHint": f"…{key[-4:]}" if len(key) >= 8 else "",
    }


def ai_provider_url(endpoint: str) -> str:
    clean = str(endpoint or "").strip().rstrip("/")
    if not clean:
        clean = DEFAULT_AI_ENDPOINT
    if clean.endswith("/chat/completions"):
        return clean
    return f"{clean}/chat/completions"


def is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


def connect_db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with connect_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                account_no INTEGER UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                avatar TEXT NOT NULL DEFAULT '',
                session_token TEXT UNIQUE NOT NULL,
                recovery_code TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS characters (
                id TEXT PRIMARY KEY,
                account_id TEXT NOT NULL,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                state_json TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS participants (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                player_id TEXT NOT NULL DEFAULT '',
                device_id TEXT NOT NULL DEFAULT '',
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            );
            CREATE INDEX IF NOT EXISTS participants_room_idx
                ON participants(room_id);
            CREATE TABLE IF NOT EXISTS room_events (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            );
            CREATE INDEX IF NOT EXISTS room_events_room_idx
                ON room_events(room_id, created_at);
            CREATE TABLE IF NOT EXISTS room_snapshots (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                reason TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            );
            CREATE INDEX IF NOT EXISTS room_snapshots_room_idx
                ON room_snapshots(room_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS action_requests (
                id TEXT PRIMARY KEY,
                room_id TEXT NOT NULL,
                participant_id TEXT NOT NULL,
                player_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                response TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            );
            CREATE INDEX IF NOT EXISTS action_requests_room_idx
                ON action_requests(room_id, status, created_at);
            CREATE TABLE IF NOT EXISTS campaign_saves (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                state_json TEXT NOT NULL,
                auto INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS campaign_saves_updated_idx
                ON campaign_saves(auto, updated_at DESC);
            CREATE TABLE IF NOT EXISTS module_library (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                module_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS module_library_updated_idx
                ON module_library(updated_at DESC);
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(participants)").fetchall()}
        if "device_id" not in columns:
            connection.execute("ALTER TABLE participants ADD COLUMN device_id TEXT NOT NULL DEFAULT ''")
        if "last_seen_at" not in columns:
            connection.execute("ALTER TABLE participants ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT ''")
            connection.execute("UPDATE participants SET last_seen_at = created_at WHERE last_seen_at = ''")
        if "account_id" not in columns:
            connection.execute("ALTER TABLE participants ADD COLUMN account_id TEXT NOT NULL DEFAULT ''")
        connection.execute("CREATE INDEX IF NOT EXISTS participants_device_idx ON participants(device_id)")
        device_columns = {row["name"] for row in connection.execute("PRAGMA table_info(devices)").fetchall()}
        if "account_id" not in device_columns:
            connection.execute("ALTER TABLE devices ADD COLUMN account_id TEXT NOT NULL DEFAULT ''")
        save_columns = {row["name"] for row in connection.execute("PRAGMA table_info(campaign_saves)").fetchall()}
        if "account_id" not in save_columns:
            connection.execute("ALTER TABLE campaign_saves ADD COLUMN account_id TEXT NOT NULL DEFAULT ''")
        connection.execute("CREATE INDEX IF NOT EXISTS campaign_saves_account_idx ON campaign_saves(account_id, updated_at DESC)")


def random_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def random_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


def create_unique_room_code() -> str:
    with connect_db() as connection:
        while True:
            code = random_code()
            if connection.execute("SELECT 1 FROM rooms WHERE id = ?", (code,)).fetchone() is None:
                return code


def get_room(room_id: str) -> sqlite3.Row:
    with connect_db() as connection:
        room = connection.execute("SELECT * FROM rooms WHERE id = ?", (room_id.upper(),)).fetchone()
    if room is None:
        raise HTTPException(status_code=404, detail="房间不存在")
    return room


def get_participant(room_id: str, participant_id: str) -> sqlite3.Row:
    with connect_db() as connection:
        participant = connection.execute(
            "SELECT * FROM participants WHERE id = ? AND room_id = ?",
            (participant_id, room_id.upper()),
        ).fetchone()
        if participant is not None:
            connection.execute(
                "UPDATE participants SET last_seen_at = ? WHERE id = ?",
                (utc_now(), participant_id),
            )
            participant = connection.execute(
                "SELECT * FROM participants WHERE id = ? AND room_id = ?",
                (participant_id, room_id.upper()),
            ).fetchone()
    if participant is None:
        raise HTTPException(status_code=403, detail="参与者身份无效")
    return participant


def authorize_participant(room_id: str, participant_id: str, http_request: Request) -> sqlite3.Row:
    participant = get_participant(room_id, participant_id)
    token = http_request.headers.get("x-participant-token", "")
    if not token or not secrets.compare_digest(token, str(participant["token"])):
        raise HTTPException(status_code=403, detail="参与者令牌无效，请重新加入房间")
    return participant


def get_room_members(room_id: str) -> list[sqlite3.Row]:
    with connect_db() as connection:
        return connection.execute(
            "SELECT * FROM participants WHERE room_id = ? ORDER BY role DESC, created_at ASC",
            (room_id.upper(),),
        ).fetchall()


def participant_is_online(last_seen_at: str) -> bool:
    try:
        last_seen = datetime.fromisoformat(last_seen_at)
        return (datetime.now(timezone.utc) - last_seen).total_seconds() <= 12
    except (TypeError, ValueError):
        return False


def member_payload(member: sqlite3.Row, current_id: str) -> dict[str, Any]:
    return {
        "id": member["id"],
        "name": member["name"],
        "role": member["role"],
        "playerId": member["player_id"],
        "deviceId": member["device_id"],
        "online": participant_is_online(member["last_seen_at"]),
        "lastSeenAt": member["last_seen_at"],
        "isSelf": member["id"] == current_id,
    }


def touch_room(room_id: str) -> None:
    with connect_db() as connection:
        connection.execute(
            "UPDATE rooms SET revision = revision + 1, updated_at = ? WHERE id = ?",
            (utc_now(), room_id.upper()),
        )


def record_room_event(room_id: str, participant_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "id": random_id("event"),
        "roomId": room_id.upper(),
        "participantId": participant_id,
        "eventType": event_type,
        "payload": payload,
        "createdAt": utc_now(),
    }
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO room_events (id, room_id, participant_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event["id"],
                event["roomId"],
                event["participantId"],
                event["eventType"],
                json.dumps(event["payload"], ensure_ascii=False),
                event["createdAt"],
            ),
        )
    return event


def row_to_action_request(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "roomId": row["room_id"],
        "participantId": row["participant_id"],
        "playerId": row["player_id"],
        "actionType": row["action_type"],
        "payload": json.loads(row["payload_json"]),
        "status": row["status"],
        "response": row["response"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def get_action_requests(room_id: str, include_done: bool = False) -> list[dict[str, Any]]:
    where = "room_id = ?"
    params: list[Any] = [room_id.upper()]
    if not include_done:
        where += " AND status = 'pending'"
    with connect_db() as connection:
        rows = connection.execute(
            f"SELECT * FROM action_requests WHERE {where} ORDER BY created_at ASC",
            tuple(params),
        ).fetchall()
    return [row_to_action_request(row) for row in rows]


async def broadcast_room(room_id: str, message_type: str, payload: dict[str, Any] | None = None) -> None:
    await socket_manager.broadcast(room_id, {
        "type": message_type,
        "roomId": room_id.upper(),
        "payload": payload or {},
        "time": utc_now(),
    })


ACCOUNT_COOKIE = "trpg_account"


def account_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "accountNo": int(row["account_no"]),
        "displayName": row["display_name"],
        "avatar": row["avatar"] or "",
        "recoveryCode": row["recovery_code"],
    }


def get_account_from_cookie(request: Request) -> sqlite3.Row | None:
    token = request.cookies.get(ACCOUNT_COOKIE, "")
    if not token:
        return None
    with connect_db() as connection:
        return connection.execute(
            "SELECT * FROM accounts WHERE session_token = ?",
            (token,),
        ).fetchone()


def create_guest_account(display_name: str = "") -> sqlite3.Row:
    now = utc_now()
    last_error: Exception | None = None
    # 并发下 MAX(account_no)+1 可能撞号，重试几次即可
    for _ in range(6):
        with connect_db() as connection:
            max_no = connection.execute("SELECT COALESCE(MAX(account_no), 1000) AS n FROM accounts").fetchone()["n"]
            account_no = int(max_no) + 1
            account_id = random_id("account")
            name = display_name.strip() or f"调查员 {account_no}"
            recovery = secrets.token_urlsafe(18)
            session_token = secrets.token_urlsafe(32)
            try:
                connection.execute(
                    """
                    INSERT INTO accounts (id, account_no, display_name, avatar, session_token, recovery_code, created_at, last_seen_at)
                    VALUES (?, ?, ?, '', ?, ?, ?, ?)
                    """,
                    (account_id, account_no, name, session_token, recovery, now, now),
                )
            except sqlite3.IntegrityError as error:
                last_error = error
                continue
            return connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if last_error is not None:
        raise last_error
    raise RuntimeError("guest account creation failed")


def ensure_account(request: Request, response: Response | None = None) -> sqlite3.Row:
    account = get_account_from_cookie(request)
    if account is None:
        account = create_guest_account()
        if response is not None:
            response.set_cookie(
                ACCOUNT_COOKIE,
                account["session_token"],
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 3650,
                path="/",
            )
    return account


def ensure_device(device_id: str, name: str = "未命名设备", account_id: str = "") -> sqlite3.Row:
    safe_id = device_id.strip() or random_id("device")
    now = utc_now()
    with connect_db() as connection:
        existing = connection.execute("SELECT * FROM devices WHERE id = ?", (safe_id,)).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO devices (id, name, created_at, last_seen_at, account_id) VALUES (?, ?, ?, ?, ?)",
                (safe_id, name.strip() or "未命名设备", now, now, account_id),
            )
        else:
            connection.execute(
                "UPDATE devices SET name = ?, last_seen_at = ?, account_id = COALESCE(NULLIF(?, ''), account_id) WHERE id = ?",
                (name.strip() or existing["name"], now, account_id, safe_id),
            )
        return connection.execute("SELECT * FROM devices WHERE id = ?", (safe_id,)).fetchone()


def get_device(device_id: str) -> sqlite3.Row:
    with connect_db() as connection:
        device = connection.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if device is None:
        raise HTTPException(status_code=403, detail="设备身份不存在，请重新注册")
    return device


def choose_player_id(state: dict[str, Any], requested: str) -> str:
    players = state.get("players") if isinstance(state.get("players"), list) else []
    ids = {str(player.get("id")) for player in players if isinstance(player, dict) and player.get("id")}
    if requested and requested in ids:
        return requested
    return next(iter(ids), "")


def merge_duplicate_players(state: dict[str, Any], keep_id: str, origin_id: str, name: str) -> None:
    players = state.get("players", [])
    if not isinstance(players, list):
        return
    keep = next((item for item in players if isinstance(item, dict) and item.get("id") == keep_id), None)
    if keep is None:
        return
    keep_name = str(keep.get("name") or name or "玩家")
    duplicates = [
        item for item in players
        if isinstance(item, dict)
        and item.get("id") != keep_id
        and (
            (origin_id and str(item.get("originCharacterId") or "") == origin_id)
            or (name and str(item.get("name") or "") == name)
        )
    ]
    if not duplicates:
        return
    duplicate_ids = {str(item.get("id")) for item in duplicates if item.get("id")}
    state["players"] = [item for item in players if str(item.get("id")) not in duplicate_ids]
    for message in state.get("chatMessages", []):
        if isinstance(message, dict) and str(message.get("speakerId") or "") in duplicate_ids:
            message["speakerId"] = keep_id
            message["speakerName"] = keep_name
    game_map = state.get("map") if isinstance(state.get("map"), dict) else {}
    seen_tokens = set()
    clean_tokens = []
    for token in game_map.get("tokens", []):
        if not isinstance(token, dict):
            continue
        if str(token.get("id") or "") in duplicate_ids:
            token["id"] = keep_id
            token["name"] = keep_name
        token_id = str(token.get("id") or "")
        if token_id in seen_tokens:
            continue
        seen_tokens.add(token_id)
        clean_tokens.append(token)
    game_map["tokens"] = clean_tokens
    combat = state.get("combat") if isinstance(state.get("combat"), dict) else {}
    combat["turnOrder"] = [
        keep_id if str(actor_id) in duplicate_ids else actor_id
        for actor_id in combat.get("turnOrder", [])
    ]
    action_points = combat.get("actionPoints")
    if isinstance(action_points, dict):
        for duplicate_id in duplicate_ids:
            if duplicate_id in action_points and keep_id not in action_points:
                action_points[keep_id] = action_points.pop(duplicate_id)
            else:
                action_points.pop(duplicate_id, None)
    selections = state.get("selections")
    if isinstance(selections, dict) and str(selections.get("playerId") or "") in duplicate_ids:
        selections["playerId"] = keep_id


def merge_character_snapshot(state: dict[str, Any], snapshot: dict[str, Any], requested: str) -> str:
    """Copy a device-owned character into the room as a host-owned play copy."""
    if not isinstance(snapshot, dict) or not snapshot.get("name"):
        return choose_player_id(state, requested)
    players = state.setdefault("players", [])
    safe_id = requested if requested else f"p_{secrets.token_urlsafe(8)}"
    player = copy.deepcopy(snapshot)
    player["id"] = safe_id
    player["originCharacterId"] = str(snapshot.get("originCharacterId") or snapshot.get("id") or "")
    player.pop("ownerDeviceId", None)
    origin_id = str(player["originCharacterId"] or "")
    name = str(player.get("name") or "")
    existing = None
    if requested:
        candidate = next((item for item in players if isinstance(item, dict) and item.get("id") == requested), None)
        if candidate is not None:
            same_origin = origin_id and str(candidate.get("originCharacterId") or "") == origin_id
            same_name = name and str(candidate.get("name") or "") == name
            if same_origin or same_name:
                existing = candidate
    if existing is None and origin_id:
        existing = next(
            (item for item in reversed(players) if isinstance(item, dict) and str(item.get("originCharacterId") or "") == origin_id),
            None,
        )
    if existing is None and name and not origin_id:
        existing = next(
            (item for item in reversed(players) if isinstance(item, dict) and str(item.get("name") or "") == name),
            None,
        )
    if existing is not None:
        keep_id = str(existing.get("id"))
        player["id"] = keep_id
        for key, value in player.items():
            if key not in {"id", "protectFromGmSnapshot", "joinedByParticipant"}:
                existing[key] = value
        merge_duplicate_players(state, keep_id, origin_id, name)
        return keep_id
    players.append(player)
    return safe_id


PLAYER_SCENE_META_PATTERNS = (
    "本段涵盖",
    "章节摘要",
    "剧情梗概",
    "模组尾声",
    "真相揭示",
    "后续剧情",
    "后续调查",
    "故事将从",
)


def clean_player_scene_text(value: Any) -> str:
    text = str(value or "")
    sentences = re.split(r"(?<=[。！？!?])", text)
    kept = [
        sentence.strip()
        for sentence in sentences
        if sentence.strip() and not any(pattern in sentence for pattern in PLAYER_SCENE_META_PATTERNS)
    ]
    return "".join(kept).strip()


def dedupe_chat_messages(messages: Any) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    seen_signatures: set[tuple[str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict):
            continue
        message_id = str(message.get("id") or "")
        signature = (
            str(message.get("speakerId") or ""),
            str(message.get("text") or ""),
            str(message.get("time") or ""),
            str(message.get("role") or ""),
        )
        if message_id and message_id in seen_ids:
            continue
        if signature in seen_signatures:
            continue
        if message_id:
            seen_ids.add(message_id)
        seen_signatures.add(signature)
        result.append(message)
    return result


def merge_chat_messages(existing: Any, incoming: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index_by_id: dict[str, int] = {}
    for message in list(existing if isinstance(existing, list) else []) + list(incoming if isinstance(incoming, list) else []):
        if not isinstance(message, dict):
            continue
        message_id = str(message.get("id") or "")
        if message_id and message_id in index_by_id:
            merged[index_by_id[message_id]] = message
            continue
        if message_id:
            index_by_id[message_id] = len(merged)
        merged.append(message)
    return dedupe_chat_messages(merged)


def strip_player_state(source: dict[str, Any], player_id: str) -> dict[str, Any]:
    """Return the public projection sent to a player client."""
    state = copy.deepcopy(source)
    state["viewMode"] = "player"
    state["aiPlan"] = None
    state["aiTurnPreview"] = None
    state["mapLibrary"] = []
    state["storyEvents"] = []
    state["aiMemory"] = {"facts": [], "summaries": []}
    state["aiControl"] = {
        "enabled": False,
        "paused": True,
        "busy": False,
        "mode": "assist",
        "lastError": "",
        "queue": [],
        "activeQueueId": "",
    }
    state["aiPlayer"] = {
        "enabled": False,
        "playerId": "",
        "playerIds": [],
        "activeIndex": 0,
        "maxTurns": 0,
        "turn": 0,
        "running": False,
        "paused": True,
        "followHuman": True,
        "pendingReaction": False,
        "lastAction": "",
        "lastReason": "",
        "lastError": "",
        "persona": "",
        "goals": "",
        "profiles": {},
        "history": [],
    }
    state["ai"] = {
        "endpoint": "",
        "model": "",
        "apiKey": "",
        "temperature": 0.7,
    }
    state["world"] = {
        **(state.get("world") if isinstance(state.get("world"), dict) else {}),
        "gmNotes": "",
    }
    state["scene"] = {
        **(state.get("scene") if isinstance(state.get("scene"), dict) else {}),
        "canon": "",
    }
    state["scene"]["plot"] = clean_player_scene_text(state["scene"].get("plot", ""))
    state["scene"]["publicText"] = clean_player_scene_text(state["scene"].get("publicText", ""))
    if isinstance(state.get("session"), dict):
        state["session"]["focus"] = clean_player_scene_text(state["session"].get("focus", ""))
    state["scenarioNodes"] = [
        {
            **node,
            "publicText": clean_player_scene_text(node.get("publicText", "")),
        }
        for node in state.get("scenarioNodes", [])
        if isinstance(node, dict)
    ]

    state["npcs"] = [
        {
            key: value
            for key, value in npc.items()
            if key not in {"secret", "notes", "goal", "relationship", "voice", "knowledge", "ignorance", "memory", "currentFacts"}
        }
        for npc in state.get("npcs", [])
        if isinstance(npc, dict)
    ]

    visible_clues = []
    for clue in state.get("clues", []):
        if not isinstance(clue, dict):
            continue
        mode = clue.get("publishMode", "hidden")
        targets = [str(value) for value in clue.get("publishTargets", [])]
        if not clue.get("published") or mode == "hidden":
            continue
        if mode == "targets" and player_id not in targets:
            continue
        visible_clues.append(clue)
    state["clues"] = visible_clues

    visible_nodes = []
    for node in state.get("scenarioNodes", []):
        if not isinstance(node, dict):
            continue
        mode = node.get("visibility", "hidden")
        targets = [str(value) for value in node.get("visibleTo", [])]
        if not node.get("published") or mode == "hidden":
            continue
        if mode == "targets" and player_id not in targets:
            continue
        public_node = {
            key: value
            for key, value in node.items()
            if key not in {"gmText", "triggers", "visibleTo"}
        }
        visible_nodes.append(public_node)
    state["scenarioNodes"] = visible_nodes

    state["chatMessages"] = [
        message
        for message in state.get("chatMessages", [])
        if isinstance(message, dict) and message.get("visibility", "public") == "public"
    ]
    state["logs"] = [
        log
        for log in state.get("logs", [])
        if isinstance(log, dict) and log.get("visibility", "public") == "public"
    ]

    game_map = state.get("map")
    if isinstance(game_map, dict):
        if not game_map.get("published"):
            state["map"] = {
                **game_map,
                "enabled": False,
                "published": False,
                "tiles": {},
                "tokens": [],
            }
        else:
            safe_map = copy.deepcopy(game_map)
            safe_tiles = {}
            for key, tile in (safe_map.get("tiles") or {}).items():
                if not isinstance(tile, dict):
                    continue
                safe_tile = dict(tile)
                if safe_tile.get("trap") == "hidden":
                    safe_tile["trap"] = "none"
                safe_tiles[key] = safe_tile
            safe_map["tiles"] = safe_tiles
            state["map"] = safe_map

    state["selections"] = {
        **(state.get("selections") if isinstance(state.get("selections"), dict) else {}),
        "playerId": player_id,
    }
    projected_players = []
    for player in state.get("players", []):
        if not isinstance(player, dict):
            continue
        if str(player.get("id")) == str(player_id):
            projected_players.append(player)
            continue
        public_player = copy.deepcopy(player)
        for key in (
            "inventory", "notes", "background", "backstory", "equipment", "gold",
            "spells", "dndState", "cocState", "cocSkillMarks", "lastCheck",
        ):
            public_player.pop(key, None)
        if isinstance(public_player.get("dnd"), dict):
            for key in ("notes", "backgroundFields", "equipment", "gold", "spells"):
                public_player["dnd"].pop(key, None)
        if isinstance(public_player.get("coc"), dict):
            for key in ("notes", "backstory", "equipment", "ideology", "significantPeople", "meaning", "injuries", "scars", "phobias"):
                public_player["coc"].pop(key, None)
        projected_players.append(public_player)
    state["players"] = projected_players
    return state


def strip_ai_credentials(source: dict[str, Any]) -> dict[str, Any]:
    """Keep provider settings while ensuring API credentials never enter room storage."""
    state = copy.deepcopy(source)
    ai = state.get("ai")
    if isinstance(ai, dict):
        ai["apiKey"] = ""
    return state


def room_payload(room: sqlite3.Row, participant: sqlite3.Row) -> dict[str, Any]:
    full_state = strip_ai_credentials(json.loads(room["state_json"]))
    visible_state = (
        full_state
        if participant["role"] == "gm"
        else strip_player_state(full_state, participant["player_id"])
    )
    members = get_room_members(room["id"])
    return {
        "room": {
            "id": room["id"],
            "name": room["name"],
            "revision": room["revision"],
            "updatedAt": room["updated_at"],
        },
        "participant": {
            "id": participant["id"],
            "name": participant["name"],
            "role": participant["role"],
            "playerId": participant["player_id"],
            "token": participant["token"],
            "deviceId": participant["device_id"],
        },
        "members": [
            member_payload(member, participant["id"])
            for member in members
            if participant["role"] == "gm" or member["id"] == participant["id"] or member["role"] != "gm"
        ],
        "actionRequests": get_action_requests(room["id"], participant["role"] == "gm")
        if participant["role"] == "gm"
        else [
            item
            for item in get_action_requests(room["id"], False)
            if item["participantId"] == participant["id"]
        ],
        "state": visible_state,
    }


def append_player_delta(room: sqlite3.Row, participant: sqlite3.Row, incoming: dict[str, Any]) -> None:
    current = strip_ai_credentials(json.loads(room["state_json"]))
    player_id = participant["player_id"]
    current["chatMessages"] = dedupe_chat_messages(current.get("chatMessages", []))

    known_messages = {
        str(message.get("id"))
        for message in current.get("chatMessages", [])
        if isinstance(message, dict) and message.get("id")
    }
    speaker = next(
        (item for item in current.get("players", []) if isinstance(item, dict) and item.get("id") == player_id),
        None,
    )
    speaker_name = str(speaker.get("name") if speaker else participant["name"])
    for message in incoming.get("chatMessages", [])[-30:]:
        if not isinstance(message, dict):
            continue
        if message.get("visibility", "public") != "public":
            continue
        if not player_id:
            continue
        clean = copy.deepcopy(message)
        clean["speakerId"] = player_id
        clean["speakerName"] = speaker_name
        clean["userName"] = str(clean.get("userName") or participant["name"] or speaker_name)
        clean["role"] = "player"
        clean["visibility"] = "public"
        message_id = str(clean.get("id") or "")
        if message_id and message_id in known_messages:
            # savePlayerDelta sends the whole chat history. Existing messages
            # must be skipped, not appended with a new id.
            continue
        if not message_id:
            clean["id"] = random_id("m")
        known_messages.add(str(clean["id"]))
        current.setdefault("chatMessages", []).append(clean)

    incoming_player = next(
        (item for item in incoming.get("players", []) if isinstance(item, dict) and item.get("id") == player_id),
        None,
    )
    if incoming_player:
        current_player = next(
            (item for item in current.get("players", []) if isinstance(item, dict) and item.get("id") == player_id),
            None,
        )
        if current_player is not None:
            for key in ("hp", "san", "maxSan", "mp", "maxMp", "conditions", "skillPoints", "pressure", "luck", "dndDeathSaves", "dndState", "cocState", "cocSkillMarks", "avatar", "avatarImage", "userName"):
                if key in incoming_player:
                    current_player[key] = incoming_player[key]

    incoming_map = incoming.get("map") if isinstance(incoming.get("map"), dict) else {}
    current_map = current.get("map") if isinstance(current.get("map"), dict) else {}
    incoming_tokens = {
        str(token.get("id")): token
        for token in incoming_map.get("tokens", [])
        if isinstance(token, dict) and token.get("id")
    }
    for token in current_map.get("tokens", []):
        if token.get("id") == player_id and player_id in incoming_tokens:
            source = incoming_tokens[player_id]
            token["row"] = source.get("row", token.get("row"))
            token["col"] = source.get("col", token.get("col"))

    save_room_state(room["id"], current, int(room["revision"]), "玩家增量")


def record_room_snapshot(room_id: str, state: dict[str, Any], revision: int, reason: str) -> None:
    serialized = json.dumps(state, ensure_ascii=False)
    with connect_db() as connection:
        latest = connection.execute(
            "SELECT state_json, created_at FROM room_snapshots WHERE room_id = ? ORDER BY created_at DESC LIMIT 1",
            (room_id.upper(),),
        ).fetchone()
        if latest and latest["state_json"] == serialized:
            return
        if latest and "回滚" not in reason:
            try:
                last_at = datetime.fromisoformat(str(latest["created_at"]).replace("Z", "+00:00"))
                if last_at.tzinfo is None:
                    last_at = last_at.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - last_at).total_seconds() < 60:
                    return
            except (TypeError, ValueError):
                pass
        connection.execute(
            "INSERT INTO room_snapshots (id, room_id, revision, reason, state_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (random_id("snapshot"), room_id.upper(), revision, reason or "state-updated", serialized, utc_now()),
        )
        connection.execute(
            """
            DELETE FROM room_snapshots
            WHERE room_id = ? AND id NOT IN (
                SELECT id FROM room_snapshots WHERE room_id = ? ORDER BY created_at DESC LIMIT 120
            )
            """,
            (room_id.upper(), room_id.upper()),
        )


def sanitize_stale_ai_queue(state: dict[str, Any], max_age_seconds: int = 120) -> None:
    control = state.get("aiControl")
    if not isinstance(control, dict):
        return
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    for item in control.get("queue", []):
        if not isinstance(item, dict) or item.get("status") not in {"pending", "processing", "error"}:
            continue
        created = str(item.get("createdAt") or "")
        try:
            created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at.timestamp() >= cutoff:
                continue
        except (TypeError, ValueError):
            pass
        item["status"] = "cancelled"
        item["error"] = "主机恢复或保存时跳过过期队列"


def build_room_transcript(room_id: str, state: dict[str, Any], include_private: bool = True) -> str:
    module_title = str((state.get("module") or {}).get("title") or (state.get("session") or {}).get("campaign") or "未命名模组")
    lines = [
        f"《{module_title}》聊天记录",
        f"房间：{room_id}",
        f"导出时间：{datetime.now(timezone.utc).isoformat()}",
        "=" * 60,
        "",
    ]
    for message in state.get("chatMessages", []):
        if not isinstance(message, dict):
            continue
        if not include_private and message.get("visibility") != "public":
            continue
        lines.append(
            f"[{message.get('time') or ''}] {message.get('speakerName') or '未知'}："
            f"{str(message.get('text') or '').strip()}"
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_room_transcript(room_id: str, state: dict[str, Any]) -> None:
    try:
        module_title = str((state.get("module") or {}).get("title") or (state.get("session") or {}).get("campaign") or "未命名模组")
        safe_title = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", module_title).strip("_")[:48] or "模组"
        text = build_room_transcript(room_id, state, include_private=True)
        target = TRANSCRIPTS_DIR / f"{room_id.upper()}-{safe_title}.txt"
        temp = target.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(target)
    except Exception as exc:
        logger.warning("transcript write failed room=%s error=%s", room_id, exc)


def merge_room_players(existing_players: Any, incoming_players: Any, removed_ids: Any = None) -> list[dict[str, Any]]:
    existing_list = [item for item in existing_players if isinstance(item, dict)] if isinstance(existing_players, list) else []
    incoming_list = [item for item in incoming_players if isinstance(item, dict)] if isinstance(incoming_players, list) else []
    removed = {str(item) for item in removed_ids} if isinstance(removed_ids, list) else set()
    incoming_by_id = {str(item.get("id") or ""): item for item in incoming_list if item.get("id")}
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in existing_list:
        player_id = str(item.get("id") or "")
        if not player_id or player_id in removed:
            continue
        result.append(incoming_by_id.get(player_id, item))
        seen.add(player_id)
    for item in incoming_list:
        player_id = str(item.get("id") or "")
        if not player_id or player_id in seen or player_id in removed:
            continue
        result.append(item)
        seen.add(player_id)
    return result


def save_room_state(room_id: str, state: dict[str, Any], revision: int, reason: str = "state-updated", preserve_chat: bool = True) -> int:
    sanitize_stale_ai_queue(state)
    now = utc_now()
    with connect_db() as connection:
        if preserve_chat:
            existing_row = connection.execute(
                "SELECT state_json FROM rooms WHERE id = ?",
                (room_id.upper(),),
            ).fetchone()
            if existing_row is not None:
                try:
                    existing = json.loads(existing_row["state_json"])
                except (TypeError, ValueError):
                    existing = {}
                state["chatMessages"] = merge_chat_messages(
                    existing.get("chatMessages", []),
                    state.get("chatMessages", []),
                )
                state["players"] = merge_room_players(
                    existing.get("players", []),
                    state.get("players", []),
                    state.get("removedPlayerIds", []),
                )
                existing_context_at = int(existing.get("aiContextStartedAt") or 0)
                incoming_context_at = int(state.get("aiContextStartedAt") or 0)
                if existing_context_at > incoming_context_at:
                    state["aiContextStartedAt"] = existing_context_at
                    state["aiContextStartMessageId"] = existing.get("aiContextStartMessageId", "")
                    state["aiMemory"] = existing.get("aiMemory", {"facts": [], "summaries": []})
        result = connection.execute(
            """
            UPDATE rooms
            SET state_json = ?, revision = revision + 1, updated_at = ?
            WHERE id = ? AND revision = ?
            """,
            (json.dumps(state, ensure_ascii=False), now, room_id.upper(), revision),
        )
        if result.rowcount == 0:
            current = connection.execute("SELECT revision FROM rooms WHERE id = ?", (room_id.upper(),)).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="房间不存在")
            raise HTTPException(status_code=409, detail="房间状态已更新，请重新同步")
        updated = connection.execute("SELECT revision FROM rooms WHERE id = ?", (room_id.upper(),)).fetchone()
        new_revision = int(updated["revision"])
    write_room_transcript(room_id, state)
    record_room_snapshot(room_id, state, new_revision, reason)
    return new_revision


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/account/session")
def account_session(http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    with connect_db() as connection:
        connection.execute("UPDATE accounts SET last_seen_at = ? WHERE id = ?", (utc_now(), account["id"]))
    return {"account": account_payload(account)}


@app.patch("/api/account/profile")
def update_account_profile(http_request: Request, response: Response, payload: dict[str, Any]) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    display_name = str(payload.get("displayName") or "").strip()[:60]
    avatar = str(payload.get("avatar") or "").strip()[:500]
    with connect_db() as connection:
        connection.execute(
            "UPDATE accounts SET display_name = ?, avatar = ?, last_seen_at = ? WHERE id = ?",
            (display_name or account["display_name"], avatar, utc_now(), account["id"]),
        )
        updated = connection.execute("SELECT * FROM accounts WHERE id = ?", (account["id"],)).fetchone()
    return {"account": account_payload(updated)}


@app.post("/api/account/recover")
def recover_account(payload: dict[str, Any], response: Response) -> dict[str, Any]:
    code = str(payload.get("recoveryCode") or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="恢复码为空")
    with connect_db() as connection:
        account = connection.execute(
            "SELECT * FROM accounts WHERE recovery_code = ?",
            (code,),
        ).fetchone()
        if account is None:
            raise HTTPException(status_code=404, detail="恢复码无效")
        connection.execute("UPDATE accounts SET last_seen_at = ? WHERE id = ?", (utc_now(), account["id"]))
    response.set_cookie(
        ACCOUNT_COOKIE,
        account["session_token"],
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 3650,
        path="/",
    )
    return {"account": account_payload(account)}


@app.post("/api/account/claim-legacy-saves")
def claim_legacy_saves(http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    with connect_db() as connection:
        result = connection.execute(
            "UPDATE campaign_saves SET account_id = ? WHERE account_id = ''",
            (account["id"],),
        )
        count = result.rowcount
    return {"ok": True, "claimed": count}


def account_from_request(request: Request) -> sqlite3.Row | None:
    return get_account_from_cookie(request)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "trpg-host-console", "time": utc_now()}


def system_network_addresses() -> set[str]:
    """Read all IPv4 interfaces, including virtual adapters such as Tailscale."""
    commands = [["ipconfig"]] if os.name == "nt" else [["hostname", "-I"], ["ifconfig"]]
    addresses: set[str] = set()
    for command in commands:
        try:
            output = subprocess.check_output(command, stderr=subprocess.DEVNULL, timeout=2, text=True, errors="ignore")
        except (OSError, subprocess.SubprocessError):
            continue
        if os.name == "nt":
            lines = [
                line for line in output.splitlines()
                if "IPv4" in line and not any(word in line for word in ("Subnet", "Mask", "Gateway"))
            ]
        else:
            lines = output.splitlines()
        for line in lines:
            for match in re.findall(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", line):
                if match.startswith(("127.", "169.254.", "0.", "255.")):
                    continue
                addresses.add(match)
        if addresses:
            break
    return addresses


def local_network_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        _, _, host_ips = socket.gethostbyname_ex(socket.gethostname())
        addresses.update(ip for ip in host_ips if ip and not ip.startswith("127."))
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(0.2)
        probe.connect(("8.8.8.8", 80))
        addresses.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    addresses.update(system_network_addresses())
    return sorted(address for address in addresses if address and not address.startswith(("127.", "169.254.", "0.")))


@app.get("/api/network")
def network_info(request: Request) -> dict[str, Any]:
    host = request.headers.get("host", "")
    port = request.url.port or (443 if request.url.scheme == "https" else 8000)
    addresses = local_network_addresses()
    request_host = host.split(":")[0].strip("[]")
    if request_host and request_host not in {"localhost", "127.0.0.1", "::1"} and request_host not in addresses:
        addresses.append(request_host)
    reachable: list[str] = []
    for address in addresses:
        try:
            probe = socket.create_connection((address, port), timeout=0.2)
            probe.close()
            reachable.append(address)
        except OSError:
            continue
    suffix = "" if port in {80, 443} else f":{port}"
    urls = [f"http://{address}{suffix}/" for address in reachable]
    loopback = request_host in {"localhost", "127.0.0.1", "::1"}
    return {
        "host": host,
        "port": port,
        "addresses": addresses,
        "urls": urls,
        "loopback": loopback,
        "lanEnabled": bool(reachable),
    }


@app.get("/api/ai/config")
def read_ai_config() -> dict[str, Any]:
    return ai_public_config()


@app.put("/api/ai/config")
def write_ai_config(request: Request, update: AiConfigUpdate) -> dict[str, Any]:
    if not is_loopback(request):
        raise HTTPException(status_code=403, detail="AI 配置只允许在本机修改")
    config = load_ai_config()
    if update.endpoint is not None:
        config["endpoint"] = update.endpoint.strip().rstrip("/") or DEFAULT_AI_ENDPOINT
    if update.model is not None:
        config["model"] = update.model.strip() or DEFAULT_AI_MODEL
    if update.temperature is not None:
        config["temperature"] = max(0.0, min(2.0, float(update.temperature)))
    if update.apiKey:
        config["apiKey"] = update.apiKey.strip()
    save_ai_config(config)
    return ai_public_config(config)


def build_ai_call(payload: AiChatRequest) -> tuple[dict[str, Any], dict[str, str], str, dict[str, Any], dict[str, Any]]:
    config = load_ai_config()
    if not config["apiKey"]:
        raise HTTPException(
            status_code=503,
            detail="服务端还没有配置 AI Key。请在“设置 > AI 接口设置”里填写并保存，或设置环境变量 TRPG_AI_API_KEY。",
        )
    if not payload.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")
    allowed_roles = {"system", "user", "assistant"}
    messages = []
    total_chars = 0
    for message in payload.messages:
        role = message.role if message.role in allowed_roles else "user"
        content = message.content
        total_chars += len(content)
        messages.append({"role": role, "content": content})
    if total_chars > 180000:
        raise HTTPException(status_code=413, detail=f"上下文过长（{total_chars} 字符），请先精简模组或记忆。")

    body: dict[str, Any] = {
        "model": (payload.model or config["model"]).strip(),
        "messages": messages,
        "temperature": config["temperature"] if payload.temperature is None else max(0.0, min(2.0, payload.temperature)),
        "stream": False,
    }
    if payload.maxTokens:
        body["max_tokens"] = payload.maxTokens
    if payload.jsonMode:
        body["response_format"] = {"type": "json_object"}

    url = ai_provider_url(config["endpoint"])
    headers = {
        "Authorization": f"Bearer {config['apiKey']}",
        "Content-Type": "application/json",
    }
    proxy_url = os.environ.get("TRPG_AI_PROXY", "").strip()
    client_options: dict[str, Any] = {
        "timeout": httpx.Timeout(60.0, connect=15.0),
        "trust_env": False,
    }
    if proxy_url:
        client_options["proxy"] = proxy_url
    if payload.disableThinking and "deepseek" in url.lower():
        body["thinking"] = {"type": "disabled"}
    return config, headers, url, body, client_options


@app.post("/api/ai/chat")
async def ai_chat(payload: AiChatRequest) -> dict[str, Any]:
    config, headers, url, body, client_options = build_ai_call(payload)
    started = datetime.now(timezone.utc)
    last_error = ""
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(**client_options) as client:
                response = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            last_error = "AI 接口超时（60 秒）"
            logger.warning("ai timeout model=%s attempt=%s", body["model"], attempt + 1)
        except httpx.RequestError as error:
            last_error = f"无法连接 AI 接口：{error.__class__.__name__}"
            logger.warning("ai request error model=%s attempt=%s error=%s", body["model"], attempt + 1, error.__class__.__name__)
        else:
            if response.status_code in {429, 500, 502, 503, 504} and attempt < max_attempts - 1:
                last_error = f"AI 接口返回 {response.status_code}"
                logger.warning("ai retry status=%s model=%s attempt=%s", response.status_code, body["model"], attempt + 1)
                await asyncio.sleep(0.8 * (attempt + 1))
                continue
            if response.status_code >= 400:
                detail = response.text[:400].replace(config["apiKey"], "***")
                try:
                    error_payload = response.json()
                    error_message = ""
                    if isinstance(error_payload, dict):
                        error_value = error_payload.get("error")
                        if isinstance(error_value, dict):
                            error_message = str(error_value.get("message") or "")
                        elif error_value:
                            error_message = str(error_value)
                    if error_message:
                        detail = error_message[:300]
                except ValueError:
                    pass
                logger.warning("ai failed status=%s model=%s body=%s", response.status_code, body["model"], detail[:200])
                raise HTTPException(status_code=502, detail=f"AI 接口返回 {response.status_code}：{detail}")
            try:
                data = response.json()
            except ValueError:
                raise HTTPException(status_code=502, detail="AI 接口返回的不是 JSON")
            choices = data.get("choices") if isinstance(data, dict) else None
            content = ""
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") if isinstance(choices[0], dict) else None
                if isinstance(message, dict):
                    content = str(message.get("content") or "")
            if not content.strip():
                finish = (choices[0].get("finish_reason") if isinstance(choices[0], dict) else "") or ""
                logger.warning("ai empty model=%s finish=%s", body["model"], finish)
                hint = "（输出达到 max_tokens，思考 tokens 可能占满了额度；请调大 maxTokens）" if finish == "length" else ""
                raise HTTPException(status_code=502, detail=f"AI 接口返回了空内容{hint}")
            elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            usage = data.get("usage") or {}
            cache_hit = usage.get("prompt_cache_hit_tokens")
            cache_miss = usage.get("prompt_cache_miss_tokens")
            cache_note = ""
            if isinstance(cache_hit, int) and isinstance(cache_miss, int) and (cache_hit + cache_miss) > 0:
                cache_note = f" cache={cache_hit}/{cache_hit + cache_miss}({cache_hit * 100 // (cache_hit + cache_miss)}%)"
            logger.info(
                "ai ok model=%s elapsed=%sms prompt=%s completion=%s%s",
                data.get("model") or body["model"],
                elapsed,
                usage.get("prompt_tokens", "?"),
                usage.get("completion_tokens", "?"),
                cache_note,
            )
            return {
                "content": content.strip(),
                "model": data.get("model") or body["model"],
                "usage": data.get("usage") or {},
                "elapsedMs": elapsed,
                "finishReason": (choices[0].get("finish_reason") if isinstance(choices[0], dict) else "") or "",
            }
    raise HTTPException(status_code=502, detail=last_error or "AI 接口调用失败")


@app.post("/api/ai/chat/stream")
async def ai_chat_stream(payload: AiChatRequest) -> StreamingResponse:
    config, headers, url, body, client_options = build_ai_call(payload)
    body["stream"] = True
    body["stream_options"] = {"include_usage": True}

    async def event_generator():
        started = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(**client_options) as client:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    if response.status_code >= 400:
                        raw = await response.aread()
                        detail = raw.decode("utf-8", "replace")[:400].replace(config["apiKey"], "***")
                        try:
                            error_payload = json.loads(raw)
                            error_value = error_payload.get("error") if isinstance(error_payload, dict) else None
                            if isinstance(error_value, dict) and error_value.get("message"):
                                detail = str(error_value["message"])[:300]
                        except ValueError:
                            pass
                        logger.warning("ai stream failed status=%s model=%s body=%s", response.status_code, body["model"], detail[:200])
                        yield f"event: error\ndata: {json.dumps({'detail': f'AI 接口返回 {response.status_code}：{detail}'}, ensure_ascii=False)}\n\n"
                        return
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
            elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            logger.info("ai stream done model=%s elapsed=%sms", body["model"], elapsed)
        except httpx.TimeoutException:
            yield f"event: error\ndata: {json.dumps({'detail': 'AI 流式接口超时'}, ensure_ascii=False)}\n\n"
        except httpx.RequestError as error:
            yield f"event: error\ndata: {json.dumps({'detail': f'无法连接 AI 接口：{error.__class__.__name__}'}, ensure_ascii=False)}\n\n"
        except Exception as error:  # pragma: no cover - defensive stream guard
            logger.warning("ai stream error model=%s error=%s", body["model"], error.__class__.__name__)
            yield f"event: error\ndata: {json.dumps({'detail': f'AI 流式输出中断：{error.__class__.__name__}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 文档解析（模组 / 规则书 / 扫描件）
#
# 走 DeepSeek 的 /v1/tools/ocr：PDF、Word、PowerPoint 和图片都能直接读，扫描版
# 也行，返回逐页文本。相比前端 pdf.js 只能拿到文字层，这里能保住表格和图注，
# 也不再让模型去"读"整份文件，按页计费（1.5 元 / 1000 页）。
# ---------------------------------------------------------------------------

DOC_EXTRACT_MAX_BYTES = 25 * 1024 * 1024
DOC_PURPOSES = {"text_recognition", "rich_layout_recognition"}
OCR_MARKUP_RE = re.compile(r"<｜[^｜]{0,40}｜>")
OCR_BOX_RE = re.compile(r"\[\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]\]")
DOC_SUFFIX_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class DocExtractRequest(BaseModel):
    filename: str = Field(default="document", max_length=255)
    data: str = Field(default="", description="文件内容的 base64（不含 data: 前缀）")
    purpose: str = Field(default="text_recognition")


def safe_doc_filename(raw: str) -> str:
    name = Path(str(raw or "document")).name
    name = re.sub(r"[\x00-\x1f\x7f]+", "", name).strip()
    return name or "document"


def clean_ocr_text(page_texts: list[str]) -> str:
    """去掉 OCR 逐页输出里的 <｜ref｜>/<｜box｜> 标记与归一化坐标框。"""
    cleaned: list[str] = []
    for page in page_texts:
        text = OCR_MARKUP_RE.sub("", str(page or ""))
        text = OCR_BOX_RE.sub("", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            cleaned.append(text)
    return "\n\n".join(cleaned)


PDF_OCR_CHUNK_PAGES = 20


def split_pdf_bytes(raw: bytes, pages_per_chunk: int = PDF_OCR_CHUNK_PAGES) -> list[tuple[int, bytes]]:
    """大 PDF 切段再送 OCR。

    /v1/tools/ocr 单次解析有总时长上限（约 180 秒），整本 400 页规则书会 504。
    切成 20 页一段后，一次性导入整本模组/规则书才跑得通。
    """
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(raw))
        total = len(reader.pages)
    except Exception:
        return [(0, raw)]
    if total <= pages_per_chunk:
        return [(0, raw)]
    chunks: list[tuple[int, bytes]] = []
    for start in range(0, total, pages_per_chunk):
        writer = PdfWriter()
        for index in range(start, min(start + pages_per_chunk, total)):
            writer.add_page(reader.pages[index])
        buffer = io.BytesIO()
        writer.write(buffer)
        chunks.append((start, buffer.getvalue()))
    return chunks


async def ocr_request(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    raw: bytes,
    filename: str,
    mime: str,
    purpose: str,
    api_key: str,
) -> dict[str, Any]:
    response = await client.post(
        url,
        headers=headers,
        data={"purpose": purpose},
        files={"file": (filename, raw, mime)},
    )
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        detail = ""
        if isinstance(data, dict):
            error_value = data.get("error")
            if isinstance(error_value, dict):
                detail = str(error_value.get("message") or "")
            elif error_value:
                detail = str(error_value)
        if not detail:
            detail = response.text[:300].replace(api_key, "***")
        logger.warning("doc extract failed status=%s file=%s body=%s", response.status_code, filename, detail[:200])
        raise HTTPException(
            status_code=502,
            detail=f"文档解析接口返回 {response.status_code}：{detail}（若当前 endpoint 是中转站，可能不支持 /v1/tools/ocr）",
        )
    return data if isinstance(data, dict) else {}


@app.post("/api/doc/extract")
async def doc_extract(request: Request, payload: DocExtractRequest) -> dict[str, Any]:
    if not is_loopback(request):
        raise HTTPException(status_code=403, detail="文档解析只允许在本机调用")
    purpose = (payload.purpose or "text_recognition").strip()
    if purpose not in DOC_PURPOSES:
        raise HTTPException(status_code=400, detail="purpose 只能是 text_recognition 或 rich_layout_recognition")
    encoded = re.sub(r"^data:[^,]*,", "", (payload.data or "").strip())
    if not encoded:
        raise HTTPException(status_code=400, detail="没有收到文件内容")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="文件内容不是合法的 base64")
    if not raw:
        raise HTTPException(status_code=400, detail="文件是空的")
    if len(raw) > DOC_EXTRACT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 25 MB，请拆分后再解析")

    config = load_ai_config()
    if not config["apiKey"]:
        raise HTTPException(
            status_code=503,
            detail="服务端还没有配置 AI Key，无法调用文档解析。",
        )
    endpoint = str(config["endpoint"] or DEFAULT_AI_ENDPOINT).strip().rstrip("/")
    if endpoint.endswith("/chat/completions"):
        endpoint = endpoint[: -len("/chat/completions")]
    url = f"{endpoint}/v1/tools/ocr"

    filename = safe_doc_filename(payload.filename)
    mime = DOC_SUFFIX_MIME.get(Path(filename).suffix.lower(), "application/octet-stream")
    headers = {"Authorization": f"Bearer {config['apiKey']}"}
    client_options: dict[str, Any] = {
        "timeout": httpx.Timeout(240.0, connect=20.0),
        "trust_env": False,
    }
    proxy_url = os.environ.get("TRPG_AI_PROXY", "").strip()
    if proxy_url:
        client_options["proxy"] = proxy_url

    started = datetime.now(timezone.utc)
    page_texts: list[str] = []
    page_count = 0
    chunks = split_pdf_bytes(raw) if filename.lower().endswith(".pdf") else [(0, raw)]
    try:
        async with httpx.AsyncClient(**client_options) as client:
            for chunk_index, (start_page, chunk_bytes) in enumerate(chunks):
                if len(chunks) > 1:
                    logger.info(
                        "doc extract chunk %s/%s from_page=%s file=%s",
                        chunk_index + 1,
                        len(chunks),
                        start_page + 1,
                        filename,
                    )
                data = await ocr_request(
                    client, url, headers, chunk_bytes, filename, mime, purpose, config["apiKey"]
                )
                chunk_pages: list[str] = []
                pages = data.get("pages")
                if isinstance(pages, list):
                    for page in pages:
                        if isinstance(page, dict):
                            chunk_pages.append(str(page.get("text") or ""))
                page_texts.extend(chunk_pages)
                reported = data.get("page_count")
                page_count += reported if isinstance(reported, int) and reported > 0 else len(chunk_pages)
    except httpx.TimeoutException:
        logger.warning("doc extract timeout file=%s bytes=%s chunks=%s", filename, len(raw), len(chunks))
        raise HTTPException(status_code=504, detail="文档解析超时，请稍后重试，或把文件拆成几份")
    except httpx.RequestError as error:
        logger.warning("doc extract request error file=%s error=%s", filename, error.__class__.__name__)
        raise HTTPException(status_code=502, detail=f"无法连接文档解析服务：{error.__class__.__name__}")

    elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    text = clean_ocr_text(page_texts)
    if not text.strip():
        logger.warning("doc extract empty file=%s chunks=%s", filename, len(chunks))
        raise HTTPException(status_code=502, detail="文档解析没有识别到文字，可能文件损坏或格式不受支持")

    if page_count <= 0:
        page_count = len(page_texts)
    logger.info(
        "doc extract ok file=%s pages=%s chars=%s elapsed=%sms purpose=%s chunks=%s",
        filename,
        page_count,
        len(text),
        elapsed,
        purpose,
        len(chunks),
    )
    return {
        "text": text,
        "pageCount": page_count,
        "chars": len(text),
        "purpose": purpose,
        "engine": "deepseek-ocr",
        "elapsedMs": elapsed,
        "chunks": len(chunks),
    }


@app.get("/api/modules")
def list_module_library() -> dict[str, Any]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT id, title, module_json, updated_at FROM module_library ORDER BY updated_at DESC",
        ).fetchall()
    modules = []
    for row in rows:
        try:
            module = json.loads(row["module_json"])
        except json.JSONDecodeError:
            continue
        modules.append({
            "id": row["id"],
            "title": row["title"],
            "updatedAt": row["updated_at"],
            "module": module,
        })
    return {"modules": modules}


@app.put("/api/modules/{module_id}")
def upsert_module(module_id: str, payload: ModuleLibraryRequest) -> dict[str, Any]:
    module_id = module_id.strip()
    if not module_id:
        raise HTTPException(status_code=400, detail="模组 ID 为空")
    module_json = json.dumps(payload.module, ensure_ascii=False, separators=(",", ":"))
    if len(module_json.encode("utf-8")) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="模组过大（超过 25 MB）。")
    now = datetime.now(timezone.utc).isoformat()
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO module_library (id, title, module_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                module_json = excluded.module_json,
                updated_at = excluded.updated_at
            """,
            (module_id, payload.title.strip() or module_id, module_json, now),
        )
    return {"ok": True, "id": module_id, "updatedAt": now}


@app.delete("/api/modules/{module_id}")
def delete_module(module_id: str) -> dict[str, Any]:
    with connect_db() as connection:
        connection.execute("DELETE FROM module_library WHERE id = ?", (module_id,))
    return {"ok": True}


@app.get("/api/characters")
def list_account_characters(http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT id, data_json, updated_at FROM characters WHERE account_id = ? ORDER BY updated_at DESC",
            (account["id"],),
        ).fetchall()
    characters = []
    for row in rows:
        try:
            characters.append(json.loads(row["data_json"]))
        except ValueError:
            continue
    return {"characters": characters}


@app.put("/api/characters/{character_id}")
def save_account_character(character_id: str, payload: dict[str, Any], http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    character = dict(payload or {})
    character["id"] = character_id
    if not str(character.get("name") or "").strip():
        raise HTTPException(status_code=400, detail="角色名称为空")
    now = utc_now()
    data_json = json.dumps(character, ensure_ascii=False, separators=(",", ":"))
    if len(data_json.encode("utf-8")) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="角色数据过大")
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO characters (id, account_id, data_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                account_id = excluded.account_id,
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (character_id, account["id"], data_json, now),
        )
    return {"ok": True, "id": character_id, "updatedAt": now}


@app.delete("/api/characters/{character_id}")
def delete_account_character(character_id: str, http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    with connect_db() as connection:
        connection.execute(
            "DELETE FROM characters WHERE id = ? AND account_id = ?",
            (character_id, account["id"]),
        )
    return {"ok": True}


@app.get("/api/saves")
def list_campaign_saves(http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT id, name, summary, auto, created_at, updated_at, length(state_json) AS size "
            "FROM campaign_saves WHERE account_id = ? "
            "ORDER BY auto DESC, updated_at DESC",
            (account["id"],),
        ).fetchall()
    return {
        "saves": [
            {
                "id": row["id"],
                "name": row["name"],
                "summary": row["summary"],
                "auto": bool(row["auto"]),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "size": row["size"],
            }
            for row in rows
        ]
    }


@app.post("/api/saves")
def create_campaign_save(payload: CampaignSaveRequest, http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    if not payload.state:
        raise HTTPException(status_code=400, detail="存档状态为空")
    state_json = json.dumps(payload.state, ensure_ascii=False, separators=(",", ":"))
    if len(state_json.encode("utf-8")) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="存档过大（超过 12 MB），请先导出清理。")
    now = datetime.now(timezone.utc).isoformat()
    name = payload.name.strip() or "未命名存档"
    summary = payload.summary.strip()[:300]
    with connect_db() as connection:
        if payload.auto:
            save_id = f"auto_{account['account_no']}"
            connection.execute(
                """
                INSERT INTO campaign_saves (id, name, summary, state_json, auto, created_at, updated_at, account_id)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    summary = excluded.summary,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at,
                    account_id = excluded.account_id
                """,
                (save_id, name, summary, state_json, now, now, account["id"]),
            )
        elif payload.id and payload.id.startswith("quick-") and payload.id[6:].isdigit():
            save_id = payload.id
            connection.execute(
                """
                INSERT INTO campaign_saves (id, name, summary, state_json, auto, created_at, updated_at, account_id)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    summary = excluded.summary,
                    state_json = excluded.state_json,
                    auto = 0,
                    updated_at = excluded.updated_at,
                    account_id = excluded.account_id
                """,
                (save_id, name, summary, state_json, now, now, account["id"]),
            )
        else:
            save_id = random_id("save")
            connection.execute(
                "INSERT INTO campaign_saves (id, name, summary, state_json, auto, created_at, updated_at, account_id) "
                "VALUES (?, ?, ?, ?, 0, ?, ?, ?)",
                (save_id, name, summary, state_json, now, now, account["id"]),
            )
            connection.execute(
                "DELETE FROM campaign_saves WHERE account_id = ? AND id IN ("
                "SELECT id FROM campaign_saves WHERE account_id = ? AND auto = 0 ORDER BY updated_at DESC LIMIT -1 OFFSET 50"
                ")",
                (account["id"], account["id"]),
            )
    return {"id": save_id, "name": name, "auto": payload.auto, "updatedAt": now}


@app.get("/api/saves/{save_id}")
def get_campaign_save(save_id: str, http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    with connect_db() as connection:
        row = connection.execute(
            "SELECT * FROM campaign_saves WHERE id = ? AND account_id = ?",
            (save_id, account["id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="找不到这个存档")
    try:
        state = json.loads(row["state_json"])
    except ValueError:
        raise HTTPException(status_code=500, detail="存档内容损坏，无法读取")
    return {
        "id": row["id"],
        "name": row["name"],
        "summary": row["summary"],
        "auto": bool(row["auto"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "state": state,
    }


@app.delete("/api/saves/{save_id}")
def delete_campaign_save(save_id: str, http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    with connect_db() as connection:
        result = connection.execute(
            "DELETE FROM campaign_saves WHERE id = ? AND account_id = ?",
            (save_id, account["id"]),
        )
        deleted = result.rowcount
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到这个存档")
    return {"ok": True}


@app.post("/api/devices/bootstrap")
def bootstrap_device(request: DeviceBootstrapRequest, http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    device = ensure_device(request.device_id, request.name, account["id"])
    with connect_db() as connection:
        participants = connection.execute(
            """
            SELECT p.*, r.name AS room_name, r.revision AS room_revision, r.updated_at AS room_updated_at
            FROM participants p
            JOIN rooms r ON r.id = p.room_id
            WHERE p.device_id = ? OR p.account_id = ?
            ORDER BY r.updated_at DESC
            """,
            (device["id"], account["id"]),
        ).fetchall()
    return {
        "account": account_payload(account),
        "device": {
            "id": device["id"],
            "name": device["name"],
            "createdAt": device["created_at"],
            "lastSeenAt": device["last_seen_at"],
        },
        "rooms": [
            {
                "roomId": item["room_id"],
                "roomName": item["room_name"],
                "revision": item["room_revision"],
                "updatedAt": item["room_updated_at"],
                "participantId": item["id"],
                "participantName": item["name"],
                "role": item["role"],
                "playerId": item["player_id"],
                "token": item["token"],
            }
            for item in participants
        ],
    }


@app.post("/api/rooms")
def create_room(request: CreateRoomRequest, http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    device = ensure_device(request.device_id, request.host_name, account["id"])
    room_id = create_unique_room_code()
    participant_id = random_id("participant")
    token = secrets.token_urlsafe(24)
    now = utc_now()
    state = strip_ai_credentials(request.state)
    with connect_db() as connection:
        connection.execute(
            "INSERT INTO rooms (id, name, state_json, revision, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (room_id, request.name.strip() or "未命名战役", json.dumps(state, ensure_ascii=False), 1, now, now),
        )
        connection.execute(
            """
            INSERT INTO participants (id, room_id, name, role, player_id, device_id, account_id, token, created_at, last_seen_at)
            VALUES (?, ?, ?, 'gm', '', ?, ?, ?, ?, ?)
            """,
            (participant_id, room_id, request.host_name.strip() or "主持人", device["id"], account["id"], token, now, now),
        )
        room = connection.execute("SELECT * FROM rooms WHERE id = ?", (room_id,)).fetchone()
        participant = connection.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
    return room_payload(room, participant)


@app.post("/api/rooms/{room_id}/recover-gm")
def recover_gm_participant(room_id: str, http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    room = get_room(room_id)
    with connect_db() as connection:
        participant = connection.execute(
            "SELECT * FROM participants WHERE room_id = ? AND role = 'gm' ORDER BY created_at LIMIT 1",
            (room["id"],),
        ).fetchone()
        if participant is None:
            raise HTTPException(status_code=404, detail="这个房间没有可恢复的主持身份")
        connection.execute(
            "UPDATE participants SET account_id = ?, last_seen_at = ? WHERE id = ?",
            (account["id"], utc_now(), participant["id"]),
        )
    participant = get_participant(room["id"], participant["id"])
    return room_payload(room, participant)


@app.post("/api/rooms/{room_id}/join")
def join_room(room_id: str, request: JoinRoomRequest, http_request: Request, response: Response) -> dict[str, Any]:
    account = ensure_account(http_request, response)
    room = get_room(room_id)
    device = ensure_device(request.device_id, request.name, account["id"])
    state = json.loads(room["state_json"])
    participant_id = random_id("participant")
    token = secrets.token_urlsafe(24)
    snapshot = request.character_snapshot if isinstance(request.character_snapshot, dict) else {}
    origin_id = str(snapshot.get("originCharacterId") or snapshot.get("id") or "")
    bindings = state.get("deviceCharacterBindings")
    if not isinstance(bindings, dict):
        bindings = {}
    binding_key = f"{account['id']}:{origin_id}" if origin_id else ""
    bound_player_id = str(bindings.get(binding_key) or "") if binding_key else ""
    player_id = merge_character_snapshot(state, snapshot, bound_player_id or request.player_id)
    for player in state.get("players", []):
        if isinstance(player, dict) and str(player.get("id")) == str(player_id):
            player["userName"] = request.name.strip() or "玩家"
            player["accountId"] = account["id"]
            player["accountNo"] = int(account["account_no"])
            break
    if binding_key:
        bindings[binding_key] = player_id
        state["deviceCharacterBindings"] = bindings
    now = utc_now()
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO participants (id, room_id, name, role, player_id, device_id, account_id, token, created_at, last_seen_at)
            VALUES (?, ?, ?, 'player', ?, ?, ?, ?, ?, ?)
            """,
            (participant_id, room["id"], request.name.strip() or "玩家", player_id, device["id"], account["id"], token, now, now),
        )
        participant = connection.execute("SELECT * FROM participants WHERE id = ?", (participant_id,)).fetchone()
    if request.character_snapshot:
        try:
            save_room_state(room["id"], strip_ai_credentials(state), int(room["revision"]), "加入房间")
            room = get_room(room["id"])
            participant = get_participant(room["id"], participant_id)
        except HTTPException:
            pass
    return room_payload(room, participant)


@app.post("/api/rooms/{room_id}/character")
async def switch_room_character(room_id: str, request: SwitchCharacterRequest, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, request.participant_id, http_request)
    if participant["role"] != "player":
        raise HTTPException(status_code=403, detail="只有玩家可以更换自己的角色")
    snapshot = request.character_snapshot
    if not isinstance(snapshot, dict) or not snapshot.get("name"):
        raise HTTPException(status_code=400, detail="角色数据为空")
    state = json.loads(room["state_json"])
    old_player_id = str(participant["player_id"] or "")
    new_player_id = merge_character_snapshot(state, snapshot, "")
    if not new_player_id:
        raise HTTPException(status_code=400, detail="无法创建房间角色副本")
    for player in state.get("players", []):
        if isinstance(player, dict) and player.get("id") == new_player_id:
            player["protectFromGmSnapshot"] = True
            player["joinedByParticipant"] = participant["id"]
            player["userName"] = str(participant["name"] or "玩家")
            break
    # Switching a participant's active character must not delete the old room
    # character. The host may still need it for the party, map and chat history.
    origin_id = str(snapshot.get("originCharacterId") or snapshot.get("id") or "")
    device_id = str(participant["device_id"] or "")
    account_id = str(participant["account_id"] or "")
    if origin_id and (account_id or device_id):
        bindings = state.get("deviceCharacterBindings")
        if not isinstance(bindings, dict):
            bindings = {}
        bindings[f"{account_id or device_id}:{origin_id}"] = new_player_id
        state["deviceCharacterBindings"] = bindings
    with connect_db() as connection:
        connection.execute(
            "UPDATE participants SET player_id = ?, last_seen_at = ? WHERE id = ?",
            (new_player_id, utc_now(), participant["id"]),
        )
    revision = save_room_state(room["id"], strip_ai_credentials(state), int(room["revision"]), "角色切换")
    event = record_room_event(room["id"], participant["id"], "character-switched", {
        "playerId": new_player_id,
        "characterId": request.character_id,
        "revision": revision,
    })
    await broadcast_room(room["id"], "state-updated", {"revision": revision, "event": event})
    room = get_room(room["id"])
    participant = get_participant(room["id"], participant["id"])
    return room_payload(room, participant)


@app.get("/api/rooms/{room_id}/snapshots")
def read_room_snapshots(room_id: str, participant_id: str, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, participant_id, http_request)
    if participant["role"] != "gm":
        raise HTTPException(status_code=403, detail="只有主持人可以查看房间快照")
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT id, revision, reason, created_at, length(state_json) AS bytes FROM room_snapshots WHERE room_id = ? ORDER BY created_at DESC LIMIT 120",
            (room["id"],),
        ).fetchall()
    return {
        "roomId": room["id"],
        "snapshots": [
            {
                "id": row["id"],
                "revision": row["revision"],
                "reason": row["reason"],
                "bytes": row["bytes"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ],
    }


@app.post("/api/rooms/{room_id}/snapshots/{snapshot_id}/restore")
async def restore_room_snapshot(room_id: str, snapshot_id: str, request: SnapshotRestoreRequest, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, request.participant_id, http_request)
    if participant["role"] != "gm":
        raise HTTPException(status_code=403, detail="只有主持人可以回滚房间快照")
    with connect_db() as connection:
        snapshot = connection.execute(
            "SELECT * FROM room_snapshots WHERE id = ? AND room_id = ?",
            (snapshot_id, room["id"]),
        ).fetchone()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="快照不存在")
    state = json.loads(snapshot["state_json"])
    revision = save_room_state(room["id"], state, int(room["revision"]), f"回滚到快照 {snapshot['revision']}", preserve_chat=False)
    event = record_room_event(room["id"], participant["id"], "snapshot-restored", {
        "snapshotId": snapshot_id,
        "snapshotRevision": snapshot["revision"],
        "revision": revision,
    })
    await broadcast_room(room["id"], "state-updated", {"revision": revision, "event": event})
    room = get_room(room["id"])
    return room_payload(room, participant)


@app.get("/api/rooms/{room_id}/state")
def read_room_state(room_id: str, participant_id: str, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, participant_id, http_request)
    return room_payload(room, participant)


@app.get("/api/rooms/{room_id}/transcript")
def download_room_transcript(room_id: str, participant_id: str, http_request: Request) -> PlainTextResponse:
    room = get_room(room_id)
    participant = authorize_participant(room_id, participant_id, http_request)
    state = json.loads(room["state_json"])
    is_gm = participant["role"] == "gm"
    if is_gm:
        write_room_transcript(room["id"], state)
    text = build_room_transcript(room["id"], state, include_private=is_gm)
    return PlainTextResponse(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{room["id"]}-chat.txt"'},
    )


@app.get("/api/rooms/{room_id}/members")
def read_room_members(room_id: str, participant_id: str, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, participant_id, http_request)
    if participant["role"] != "gm":
        raise HTTPException(status_code=403, detail="只有主持人可以查看完整成员列表")
    return {
        "roomId": room["id"],
        "members": [member_payload(member, participant["id"]) for member in get_room_members(room["id"])],
    }


@app.patch("/api/rooms/{room_id}/members/{member_id}")
async def update_room_member(room_id: str, member_id: str, request: ParticipantUpdateRequest, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    operator = authorize_participant(room_id, request.participant_id, http_request)
    if operator["role"] != "gm":
        raise HTTPException(status_code=403, detail="只有主持人可以管理成员")
    target = get_participant(room_id, member_id)
    if target["role"] == "gm":
        raise HTTPException(status_code=400, detail="不能修改主持人身份")
    state = json.loads(room["state_json"])
    valid_player_ids = {
        str(player.get("id"))
        for player in state.get("players", [])
        if isinstance(player, dict) and player.get("id")
    }
    if request.player_id is not None and request.player_id not in valid_player_ids:
        raise HTTPException(status_code=400, detail="指定的角色不存在")
    updates: list[str] = []
    values: list[Any] = []
    if request.name is not None:
        updates.append("name = ?")
        values.append(request.name.strip() or target["name"])
    if request.player_id is not None:
        updates.append("player_id = ?")
        values.append(request.player_id)
    if updates:
        values.append(member_id)
        values.append(room["id"])
        with connect_db() as connection:
            connection.execute(
                f"UPDATE participants SET {', '.join(updates)} WHERE id = ? AND room_id = ?",
                tuple(values),
            )
        touch_room(room["id"])
    members = [member_payload(member, operator["id"]) for member in get_room_members(room["id"])]
    event = record_room_event(room["id"], operator["id"], "member-updated", {"memberId": member_id})
    await broadcast_room(room["id"], "members-updated", {"members": members, "event": event})
    return {
        "roomId": room["id"],
        "members": members,
    }


@app.delete("/api/rooms/{room_id}/members/{member_id}")
async def remove_room_member(room_id: str, member_id: str, request: ParticipantRemoveRequest, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    operator = authorize_participant(room_id, request.participant_id, http_request)
    if operator["role"] != "gm":
        raise HTTPException(status_code=403, detail="只有主持人可以移除成员")
    target = get_participant(room_id, member_id)
    if target["role"] == "gm":
        raise HTTPException(status_code=400, detail="不能移除主持人")
    with connect_db() as connection:
        connection.execute(
            "DELETE FROM participants WHERE id = ? AND room_id = ?",
            (member_id, room["id"]),
        )
    touch_room(room["id"])
    members = [member_payload(member, operator["id"]) for member in get_room_members(room["id"])]
    event = record_room_event(room["id"], operator["id"], "member-removed", {"memberId": member_id})
    await broadcast_room(room["id"], "members-updated", {"members": members, "removedParticipantId": member_id, "event": event})
    return {
        "roomId": room["id"],
        "removedParticipantId": member_id,
        "members": members,
    }


@app.get("/api/rooms/{room_id}/events")
def read_room_events(room_id: str, participant_id: str, http_request: Request, after: str = "") -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, participant_id, http_request)
    with connect_db() as connection:
        if after:
            rows = connection.execute(
                """
                SELECT * FROM room_events
                WHERE room_id = ? AND created_at > ?
                ORDER BY created_at ASC
                LIMIT 200
                """,
                (room["id"], after),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM room_events WHERE room_id = ? ORDER BY created_at DESC LIMIT 50",
                (room["id"],),
            ).fetchall()
    events = [
        {
            "id": row["id"],
            "roomId": row["room_id"],
            "participantId": row["participant_id"],
            "eventType": row["event_type"],
            "payload": json.loads(row["payload_json"]),
            "createdAt": row["created_at"],
        }
        for row in reversed(rows)
    ]
    return {
        "roomId": room["id"],
        "viewerRole": participant["role"],
        "events": events,
    }


def visible_action_requests(room_id: str, participant: sqlite3.Row) -> list[dict[str, Any]]:
    requests = get_action_requests(room_id, participant["role"] == "gm")
    if participant["role"] == "gm":
        return requests
    return [item for item in requests if item.get("participantId") == participant["id"]]


@app.get("/api/rooms/{room_id}/action-requests")
def read_action_requests(room_id: str, participant_id: str, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, participant_id, http_request)
    return {
        "roomId": room["id"],
        "requests": visible_action_requests(room["id"], participant),
    }


@app.post("/api/rooms/{room_id}/action-requests")
async def create_action_request(room_id: str, request: ActionRequestCreate, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, request.participant_id, http_request)
    if participant["role"] != "player":
        raise HTTPException(status_code=403, detail="只有玩家可以提交行动请求")
    if not participant["player_id"]:
        raise HTTPException(status_code=400, detail="玩家尚未绑定角色")
    payload = copy.deepcopy(request.payload)
    actor_id = str(payload.get("actorId") or "")
    if actor_id and actor_id != str(participant["player_id"]):
        raise HTTPException(status_code=403, detail="只能以自己的角色提交行动")
    payload["actorId"] = participant["player_id"]
    payload["playerId"] = participant["player_id"]
    now = utc_now()
    request_id = random_id("action")
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO action_requests
            (id, room_id, participant_id, player_id, action_type, payload_json, status, response, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', '', ?, ?)
            """,
            (
                request_id,
                room["id"],
                participant["id"],
                participant["player_id"],
                request.action_type,
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
            ),
        )
    item = {
        "id": request_id,
        "roomId": room["id"],
        "participantId": participant["id"],
        "playerId": participant["player_id"],
        "actionType": request.action_type,
        "payload": payload,
        "status": "pending",
        "response": "",
        "createdAt": now,
        "updatedAt": now,
    }
    event = record_room_event(room["id"], participant["id"], "action-request-created", item)
    await broadcast_room(room["id"], "action-request-created", {"request": item, "event": event})
    return {"request": item, "requests": visible_action_requests(room["id"], participant)}


@app.patch("/api/rooms/{room_id}/action-requests/{request_id}")
async def update_action_request(room_id: str, request_id: str, request: ActionRequestUpdate, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    operator = authorize_participant(room_id, request.participant_id, http_request)
    if operator["role"] != "gm":
        raise HTTPException(status_code=403, detail="只有主持人可以处理行动请求")
    status = request.status if request.status in {"resolved", "rejected", "cancelled"} else "resolved"
    now = utc_now()
    with connect_db() as connection:
        result = connection.execute(
            """
            UPDATE action_requests
            SET status = ?, response = ?, updated_at = ?
            WHERE id = ? AND room_id = ?
            """,
            (status, request.response.strip(), now, request_id, room["id"]),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="行动请求不存在")
        row = connection.execute("SELECT * FROM action_requests WHERE id = ?", (request_id,)).fetchone()
    item = row_to_action_request(row)
    event = record_room_event(room["id"], operator["id"], "action-request-updated", item)
    await broadcast_room(room["id"], "action-request-updated", {"request": item, "event": event})
    return {"request": item, "requests": get_action_requests(room["id"], True)}


def merge_protected_players(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Keep player-created character copies even when a GM submits a stale snapshot."""
    removed_ids = {
        str(player_id)
        for player_id in current.get("removedPlayerIds", [])
        if player_id
    }
    if removed_ids:
        incoming["players"] = [
            player for player in incoming.get("players", [])
            if not (isinstance(player, dict) and str(player.get("id")) in removed_ids)
        ]
        incoming["removedPlayerIds"] = sorted(removed_ids)
    current_players = {
        str(player.get("id")): player
        for player in current.get("players", [])
        if isinstance(player, dict) and player.get("protectFromGmSnapshot")
    }
    if not current_players:
        return incoming
    players = incoming.setdefault("players", [])
    by_id = {
        str(player.get("id")): index
        for index, player in enumerate(players)
        if isinstance(player, dict)
    }
    for player_id, protected in current_players.items():
        if player_id in by_id:
            players[by_id[player_id]] = copy.deepcopy(protected)
        else:
            players.append(copy.deepcopy(protected))
    return incoming


@app.put("/api/rooms/{room_id}/state")
async def write_room_state(room_id: str, request: StateRequest, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, request.participant_id, http_request)
    if participant["role"] != "gm":
        raise HTTPException(status_code=403, detail="只有主持人可以保存完整房间状态")
    current = json.loads(room["state_json"])
    incoming = strip_ai_credentials(request.state)
    incoming = merge_protected_players(current, incoming)
    save_room_state(room_id, incoming, request.revision, "主持人保存")
    room = get_room(room_id)
    payload = room_payload(room, participant)
    event = record_room_event(room_id, participant["id"], "state-updated", {"revision": room["revision"]})
    await broadcast_room(room_id, "state-updated", {"revision": room["revision"], "event": event})
    return payload


@app.post("/api/rooms/{room_id}/events")
async def write_room_event(room_id: str, request: EventRequest, http_request: Request) -> dict[str, Any]:
    room = get_room(room_id)
    participant = authorize_participant(room_id, request.participant_id, http_request)
    if participant["role"] == "gm":
        raise HTTPException(status_code=400, detail="主持人应使用状态保存接口")
    if request.event_type != "player-delta":
        raise HTTPException(status_code=400, detail="不支持的事件类型")
    append_player_delta(room, participant, request.state)
    room = get_room(room_id)
    event = record_room_event(room_id, participant["id"], request.event_type, {"revision": room["revision"]})
    await broadcast_room(room_id, "state-updated", {"revision": room["revision"], "event": event})
    return room_payload(room, participant)


@app.websocket("/ws/rooms/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str, participant_id: str, token: str = "") -> None:
    try:
        room = get_room(room_id)
        participant = get_participant(room_id, participant_id)
        if not token or not secrets.compare_digest(token, str(participant["token"])):
            raise HTTPException(status_code=403, detail="参与者令牌无效")
    except HTTPException:
        await websocket.close(code=4403)
        return

    await socket_manager.connect(room["id"], websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "roomId": room["id"],
            "payload": {
                "revision": room["revision"],
                "role": participant["role"],
                "actionRequests": get_action_requests(room["id"], participant["role"] == "gm"),
            },
            "time": utc_now(),
        })
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "ping":
                get_participant(room_id, participant_id)
                await websocket.send_json({"type": "pong", "time": utc_now()})
            elif message_type == "sync":
                fresh_room = get_room(room_id)
                fresh_participant = get_participant(room_id, participant_id)
                await websocket.send_json({
                    "type": "snapshot-required",
                    "roomId": fresh_room["id"],
                    "payload": {
                        "revision": fresh_room["revision"],
                        "state": room_payload(fresh_room, fresh_participant),
                    },
                    "time": utc_now(),
                })
    except WebSocketDisconnect:
        socket_manager.disconnect(room_id, websocket)
    except Exception:
        socket_manager.disconnect(room_id, websocket)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/index.html")
def index_alias() -> FileResponse:
    return FileResponse(BASE_DIR / "index.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.post("/api/map-assets")
def upload_map_asset(request: MapAssetRequest) -> dict[str, Any]:
    import re
    match = re.match(r"^data:image/(png|jpeg|jpg|webp|gif);base64,(.+)$", request.data, re.DOTALL)
    if not match:
        raise HTTPException(status_code=400, detail="只支持 PNG、JPG、WebP 或 GIF 图片")
    mime = match.group(1)
    encoded = match.group(2)
    if len(encoded) > 11_000_000:
        raise HTTPException(status_code=413, detail="图片不能超过 8MB")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=400, detail="图片数据无效")
    if len(raw) > 8_000_000:
        raise HTTPException(status_code=413, detail="图片不能超过 8MB")
    ext = "jpg" if mime in {"jpeg", "jpg"} else mime
    filename = f"{secrets.token_hex(12)}.{ext}"
    (MAP_ASSETS_DIR / filename).write_bytes(raw)
    return {"ok": True, "url": f"/map-assets/{filename}", "bytes": len(raw)}


@app.get("/map-assets/{filename}")
def map_asset(filename: str) -> FileResponse:
    import re
    if not re.fullmatch(r"[a-f0-9]{24}\.(png|jpg|webp|gif)", filename):
        raise HTTPException(status_code=404, detail="Not found")
    target = MAP_ASSETS_DIR / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.get("/{filename}")
def static_asset(filename: str) -> FileResponse:
    """Whitelist public assets so the database, server code and AI key stay private."""
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=404, detail="Not found")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp", ".woff", ".woff2"}:
        raise HTTPException(status_code=404, detail="Not found")
    target = (BASE_DIR / filename).resolve()
    if target.parent != BASE_DIR or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target, headers={"Cache-Control": "no-store, max-age=0"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
