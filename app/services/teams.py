"""Microsoft Graph API client for Teams integration.

Requires TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET in .env.
If not configured, all methods fall back gracefully (return None/empty).
"""

import logging
from datetime import datetime, timedelta

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(
        settings.TEAMS_TENANT_ID
        and settings.TEAMS_CLIENT_ID
        and settings.TEAMS_CLIENT_SECRET
        and settings.TEAMS_ORGANIZER_EMAIL
    )


async def _get_access_token() -> str | None:
    if not _is_configured():
        return None
    url = f"https://login.microsoftonline.com/{settings.TEAMS_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": settings.TEAMS_CLIENT_ID,
        "client_secret": settings.TEAMS_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data)
        if resp.is_error:
            return None
        return resp.json().get("access_token")


async def criar_reuniao(titulo: str, data_hora: datetime, duracao_minutos: int = 60) -> dict | None:
    """Cria uma reunião Teams e retorna { join_url, meeting_id }"""
    token = await _get_access_token()
    if not token:
        return None

    url = f"https://graph.microsoft.com/v1.0/users/{settings.TEAMS_ORGANIZER_EMAIL}/onlineMeetings"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    inicio = data_hora.isoformat()
    fim = (data_hora + timedelta(minutes=duracao_minutos)).isoformat()

    payload = {
        "subject": titulo,
        "startDateTime": inicio,
        "endDateTime": fim,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.is_error:
            return None
        data = resp.json()
        return {
            "join_url": data.get("joinWebUrl"),
            "meeting_id": data.get("id"),
        }


async def buscar_gravacao(meeting_id: str) -> str | None:
    """Busca URL da gravação de uma reunião Teams"""
    token = await _get_access_token()
    if not token:
        return None

    url = f"https://graph.microsoft.com/v1.0/users/{settings.TEAMS_ORGANIZER_EMAIL}/onlineMeetings/{meeting_id}/recordings"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.is_error:
            return None
        data = resp.json()
        recordings = data.get("value", [])
        if recordings:
            return recordings[0].get("downloadUrl")
        return None


async def listar_presenca(meeting_id: str) -> list[dict]:
    """Retorna lista de presença da reunião"""
    token = await _get_access_token()
    if not token:
        return []

    url = f"https://graph.microsoft.com/v1.0/users/{settings.TEAMS_ORGANIZER_EMAIL}/onlineMeetings/{meeting_id}/attendanceReports"
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.is_error:
            return []
        data = resp.json()
        reports = data.get("value", [])
        if not reports:
            return []
        report_id = reports[0].get("id")
        if not report_id:
            return []

        att_url = f"https://graph.microsoft.com/v1.0/users/{settings.TEAMS_ORGANIZER_EMAIL}/onlineMeetings/{meeting_id}/attendanceReports/{report_id}/attendanceRecords"
        resp2 = await client.get(att_url, headers=headers)
        if resp2.is_error:
            return []
        return resp2.json().get("value", [])


async def processar_gravacao(
    meeting_id: str,
    titulo_aula: str,
    db_session,
) -> dict:
    """Baixa gravacao do Teams, faz upload pro S3 e cria registro Conteudo."""
    from app.models.conteudo import Conteudo
    from app.services import storage as storage_service

    recording_url = await buscar_gravacao(meeting_id)
    if not recording_url:
        logger.warning("processar_gravacao: gravacao nao disponivel para %s", meeting_id)
        return {"success": False, "error": "Gravacao nao disponivel no Teams"}

    token = await _get_access_token()
    if not token:
        return {"success": False, "error": "Token Teams invalido"}

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(recording_url, headers=headers, follow_redirects=True)
        if resp.is_error:
            logger.error("processar_gravacao: falha ao baixar %s - %d", recording_url, resp.status_code)
            return {"success": False, "error": f"Falha ao baixar gravacao: HTTP {resp.status_code}"}
        content = resp.content
        mime_type = resp.headers.get("content-type", "video/mp4")

    file_url = await storage_service.upload_bytes(
        content=content,
        filename=f"gravacao_{meeting_id}.mp4",
        folder="gravacoes",
        content_type=mime_type,
    )

    conteudo = Conteudo(
        tipo_midia="video",
        titulo=f"Gravacao - {titulo_aula}",
        mime_type=mime_type,
        url_arquivo=file_url,
        tamanho_bytes=len(content),
    )
    db_session.add(conteudo)
    await db_session.flush()

    logger.info("processar_gravacao: gravacao salva como Conteudo %d", conteudo.id)
    return {
        "success": True,
        "conteudo_id": conteudo.id,
        "url": file_url,
    }


async def sincronizar_presenca(meeting_id: str, aula_id: int | None = None) -> list[dict]:
    """Retorna lista de presenca da reuniao Teams."""
    registros = await listar_presenca(meeting_id)
    result = []
    for r in registros:
        email = r.get("emailAddress") or ""
        identity = r.get("identity", {}).get("user", {}).get("displayName", "")
        segundos = r.get("totalAttendanceInSeconds", 0)
        result.append(
            {
                "email": email,
                "nome": identity or email,
                "tempo_segundos": segundos,
                "tempo_formatado": f"{segundos // 60}m{segundos % 60}s" if segundos else "0s",
            }
        )
    return result
