import asyncio
import base64
from uuid import UUID

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, WebSocketException, status
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.catalog.router import run_homologation
from app.agents.voice.gemini_live import GeminiLiveSTTProvider
from app.agents.voice.schemas import OperatorClaims, SessionConfig
from app.agents.voice.session import AudioChunkFn, HomologateFn, PendingItem, PersistItemFn, VoicePTTSession
from app.config import settings
from app.database import AsyncSessionLocal
from app.services.catalog_sync import get_qdrant_client
from app.services.orchestrator import SessionNotFoundError, UnknownOracleCodeError, persist_count_item
from app.services.perishables import PerishableItemMissingExpiryError

router = APIRouter(tags=["voice"])


def _build_on_audio_chunk(websocket: WebSocket, send_lock: asyncio.Lock) -> AudioChunkFn:
    """Wraps the WS connection into the `AudioChunkFn` shape
    `VoicePTTSession` expects, relaying TTS audio from `speak()` calls
    (see session.py) back to the browser as it arrives. Guarded by
    `send_lock` because this fires from a background task
    (`_relay_audio_out`) running concurrently with the main dispatch loop
    below — both write to the same WebSocket, which Starlette doesn't
    guarantee is safe without external serialization."""

    async def on_audio_chunk(chunk_b64: str) -> None:
        async with send_lock:
            await websocket.send_json({"type": "audio_out", "data": chunk_b64})

    return on_audio_chunk


def _build_homologate(session: AsyncSession, qdrant_client: AsyncQdrantClient) -> HomologateFn:
    """Wraps the Catalog Agent (`catalog/router.py::run_homologation`) into
    the `HomologateFn` shape `VoicePTTSession` expects. The DB session and
    Qdrant client are opened once per WS connection and reused across every
    ptt_stop in that session — cheaper than reconnecting per utterance."""

    async def homologate(article: str) -> dict:
        result = await run_homologation(session, qdrant_client, article)
        return {
            "oracle_code": result.oracle_code,
            "name": result.name,
            "is_perishable": result.is_perishable,
            "sin_homologar": result.sin_homologar,
        }

    return homologate


def _build_persist_item(session: AsyncSession, session_id: UUID, operator_id: str) -> PersistItemFn:
    """Wraps the Orchestrator (`services/orchestrator.py::persist_count_item`)
    into the `PersistItemFn` shape `VoicePTTSession` expects — the real
    counterpart to `_default_persist_item`'s stub."""

    async def persist_item(item: PendingItem) -> dict:
        try:
            result = await persist_count_item(
                session,
                session_id=session_id,
                oracle_code=item.oracle_code,
                article_name=item.article,
                raw_transcript=None,
                quantity=item.quantity,
                unit=item.unit,
                homologation_score=None,
                sin_homologar=item.oracle_code is None,
                expiry_date=item.expiry_date,
                is_offline=False,
                confidence_stt=None,
                created_by=operator_id,
            )
        except SessionNotFoundError:
            return {"ok": False, "code": "SESSION_NOT_FOUND", "message": "La sesión de conteo no existe."}
        except UnknownOracleCodeError:
            return {"ok": False, "code": "UNKNOWN_ORACLE_CODE", "message": "Código de catálogo inválido."}
        except PerishableItemMissingExpiryError:
            # The perishables state machine already forces an expiry date
            # before reaching confirmation — this would mean that guard was
            # bypassed somehow, not a normal user-facing path.
            return {
                "ok": False,
                "code": "EXPIRY_DATE_REQUIRED",
                "message": "Este artículo requiere fecha de vencimiento.",
            }

        await session.commit()
        return {
            "ok": True,
            "item_id": str(result.item_id),
            "is_flagged": result.is_flagged,
            "flag_type": result.flag_type,
            "traffic_light": result.traffic_light,
            "sequence": result.sequence_in_session,
        }

    return persist_item


async def verify_ws_token(token: str) -> OperatorClaims:
    """Verifica JWT antes de aceptar la conexión WS (CWE-1390)."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return OperatorClaims(**payload)
    except jwt.InvalidTokenError as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION) from exc


@router.websocket("/ws/voice/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: UUID, token: str = Query(...)) -> None:
    try:
        claims = await verify_ws_token(token)
    except WebSocketException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    session_config = SessionConfig(session_id=session_id, operator_id=claims.operator_id)
    qdrant_client = get_qdrant_client()
    send_lock = asyncio.Lock()

    async with AsyncSessionLocal() as db_session:
        homologate = _build_homologate(db_session, qdrant_client)
        persist_item = _build_persist_item(db_session, session_id, claims.operator_id)
        on_audio_chunk = _build_on_audio_chunk(websocket, send_lock)
        voice_session = VoicePTTSession(
            stt_provider=GeminiLiveSTTProvider(),
            session_config=session_config,
            homologate=homologate,
            persist_item=persist_item,
            on_audio_chunk=on_audio_chunk,
        )

        try:
            while True:
                message = await websocket.receive_json()
                response = await _dispatch(voice_session, message)
                if response is not None:
                    async with send_lock:
                        await websocket.send_json(response)
        except WebSocketDisconnect:
            pass
        finally:
            await voice_session.close()
            await qdrant_client.close()


async def _dispatch(session: VoicePTTSession, message: dict) -> dict | None:
    msg_type = message.get("type")

    if msg_type == "ptt_start":
        return await session.handle_ptt_start()
    if msg_type == "audio_chunk":
        await session.handle_audio_chunk(base64.b64decode(message["data"]))
        return None
    if msg_type == "ptt_stop":
        return await session.handle_ptt_stop()
    if msg_type == "confirm":
        return await session.handle_confirm(bool(message.get("value")))
    if msg_type == "barge_in":
        return await session.handle_barge_in()

    return {
        "type": "error",
        "code": "UNKNOWN_MESSAGE_TYPE",
        "message": f"Tipo de mensaje no soportado: {msg_type}",
    }
