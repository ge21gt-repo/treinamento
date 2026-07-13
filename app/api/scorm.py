import zipfile
import io
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.config import settings
from app.database import get_db
from app.models.scorm import PacoteScorm, TrackingScorm
from app.models.usuario import Usuario
from app.schemas.scorm import (
    PacoteScormRead,
    ScormLaunchResponse,
    ScormRelatorioItem,
    TrackingScormCreate,
    TrackingScormRead,
)
from app.services.auth import create_access_token
from app.services.rbac import Permissoes
from app.services.storage import upload_file

router = APIRouter(prefix="/scorm", tags=["SCORM"])


def parse_imsmanifest(xml_content: bytes) -> dict:
    root = ET.fromstring(xml_content)
    ns = {
        "imscp": "http://www.imsglobal.org/xsd/imscp_v1p1",
        "adlcp": "http://www.adlnet.org/xsd/adlcp_v1p3",
        "imsss": "http://www.imsglobal.org/xsd/imsss_v1p0",
    }
    manifest: dict = {"organizations": [], "resources": []}
    orgs = root.find(".//imscp:organizations", ns)
    if orgs is not None:
        for org in orgs.findall("imscp:organization", ns):
            org_data = {"title": org.get("title", ""), "items": []}
            for item in org.findall(".//imscp:item", ns):
                org_data["items"].append({
                    "identifier": item.get("identifier"),
                    "identifierref": item.get("identifierref"),
                    "title": item.find("imscp:title", ns).text if item.find("imscp:title", ns) is not None else "",
                })
            manifest["organizations"].append(org_data)
    res = root.find(".//imscp:resources", ns)
    if res is not None:
        for r in res.findall("imscp:resource", ns):
            manifest["resources"].append({
                "identifier": r.get("identifier"),
                "type": r.get("type"),
                "href": r.get("href"),
                "scorm_type": r.get("adlcp:scormType", ns),
            })
    version_el = root.find(".//imscp:schema", ns)
    manifest["scorm_version"] = version_el.text if version_el is not None else "1.2"
    return manifest


@router.post("/upload", response_model=PacoteScormRead, status_code=status.HTTP_201_CREATED)
async def upload_scorm(
    curso_id: int = Query(...),
    titulo: str = Query(...),
    arquivo: UploadFile = ...,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.SCORM_GERENCIAR)),
):
    if arquivo.content_type != "application/zip":
        raise HTTPException(status_code=400, detail="SCORM deve ser um arquivo ZIP")

    content = await arquivo.read()
    await arquivo.seek(0)

    manifest_json = None
    scorm_version = "1.2"
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            if "imsmanifest.xml" in zf.namelist():
                manifest_xml = zf.read("imsmanifest.xml")
                manifest_json = parse_imsmanifest(manifest_xml)
                scorm_version = manifest_json.get("scorm_version", "1.2")
    except Exception:
        pass

    url = await upload_file(arquivo, "scorm")
    pacote = PacoteScorm(
        curso_id=curso_id,
        titulo=titulo,
        arquivo_url=url,
        manifest_json=manifest_json,
        scorm_version=scorm_version,
        criado_por=current_user.id,
    )
    db.add(pacote)
    await db.commit()
    await db.refresh(pacote)
    return pacote


@router.get("/{pacote_id}/launch", response_model=ScormLaunchResponse)
async def launch_scorm(
    pacote_id: int,
    sco_id: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.SCORM_VISUALIZAR)),
):
    result = await db.execute(select(PacoteScorm).where(PacoteScorm.id == pacote_id))
    pacote = result.scalar_one_or_none()
    if not pacote:
        raise HTTPException(status_code=404, detail="Pacote SCORM nao encontrado")

    token = create_access_token(
        data={"sub": str(current_user.id), "pacote_id": pacote_id, "sco_id": sco_id},
        expires_delta=3600,
    )
    return ScormLaunchResponse(url=pacote.arquivo_url, token=token, sco_id=sco_id)


@router.post("/{pacote_id}/tracking", response_model=TrackingScormRead)
async def tracking_scorm(
    pacote_id: int,
    payload: TrackingScormCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.SCORM_VISUALIZAR)),
):
    result = await db.execute(
        select(TrackingScorm).where(
            TrackingScorm.usuario_id == current_user.id,
            TrackingScorm.pacote_id == pacote_id,
            TrackingScorm.sco_id == payload.sco_id,
        )
    )
    tracking = result.scalar_one_or_none()

    if tracking:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(tracking, field, value)
    else:
        tracking = TrackingScorm(
            usuario_id=current_user.id,
            pacote_id=pacote_id,
            **payload.model_dump(),
        )
        db.add(tracking)

    await db.commit()
    await db.refresh(tracking)
    return tracking


@router.get("/{pacote_id}/tracking", response_model=list[TrackingScormRead])
async def listar_tracking(
    pacote_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.SCORM_VISUALIZAR)),
):
    result = await db.execute(
        select(TrackingScorm)
        .where(TrackingScorm.pacote_id == pacote_id)
        .order_by(TrackingScorm.usuario_id, TrackingScorm.sco_id)
    )
    return result.scalars().all()


@router.get("/cursos/{curso_id}/relatorio", response_model=list[ScormRelatorioItem])
async def relatorio_scorm(
    curso_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.SCORM_VISUALIZAR)),
):
    pacotes = await db.execute(select(PacoteScorm.id).where(PacoteScorm.curso_id == curso_id))
    pacote_ids = [r[0] for r in pacotes.all()]
    if not pacote_ids:
        return []

    result = await db.execute(
        select(TrackingScorm)
        .where(TrackingScorm.pacote_id.in_(pacote_ids))
        .order_by(TrackingScorm.usuario_id, TrackingScorm.sco_id)
    )
    trackings = result.scalars().all()
    return [
        ScormRelatorioItem(
            usuario_id=t.usuario_id,
            sco_id=t.sco_id,
            status=t.status,
            score_raw=t.score_raw,
            progresso_pct=t.progresso_pct,
            lesson_status=t.lesson_status,
        )
        for t in trackings
    ]
