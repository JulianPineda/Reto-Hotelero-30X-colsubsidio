import base64
from uuid import UUID

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, WebSocketException, status

from app.agents.voice.gemini_live import GeminiLiveSTTProvider
from app.agents.voice.schemas import OperatorClaims, SessionConfig
from app.agents.voice.session import VoicePTTSession
from app.config import settings

router = APIRouter(tags=["voice"])


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
    voice_session = VoicePTTSession(stt_provider=GeminiLiveSTTProvider(), session_config=session_config)

    try:
        while True:
            message = await websocket.receive_json()
            response = await _dispatch(voice_session, message)
            if response is not None:
                await websocket.send_json(response)
    except WebSocketDisconnect:
        pass
    finally:
        await voice_session.close()


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
