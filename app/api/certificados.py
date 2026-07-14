import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.certificado import Certificado, ModeloCertificado
from app.models.usuario import Usuario
from app.schemas.certificado import (
    CertificadoCreate,
    CertificadoRead,
    ModeloCertificadoCreate,
    ModeloCertificadoRead,
)

router = APIRouter(prefix="/certificados", tags=["Certificados"])


# --- Modelos ---


@router.get("/modelos", response_model=list[ModeloCertificadoRead])
async def listar_modelos(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(ModeloCertificado).where(ModeloCertificado.ativo))
    return result.scalars().all()


@router.post("/modelos", response_model=ModeloCertificadoRead, status_code=status.HTTP_201_CREATED)
async def criar_modelo(
    payload: ModeloCertificadoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    modelo = ModeloCertificado(**payload.model_dump())
    db.add(modelo)
    await db.commit()
    await db.refresh(modelo)
    return modelo


# --- Certificados ---


@router.post("", response_model=CertificadoRead, status_code=status.HTTP_201_CREATED)
async def emitir_certificado(
    payload: CertificadoCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    cert = Certificado(**payload.model_dump())
    db.add(cert)
    await db.flush()
    cert.hash_validacao = hashlib.sha256(str(cert.id).encode()).hexdigest()
    await db.commit()
    await db.refresh(cert)
    return cert


@router.get("/{certificado_id}", response_model=CertificadoRead)
async def obter_certificado(
    certificado_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Certificado).where(Certificado.id == certificado_id))
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificado nao encontrado")
    return cert


@router.get("/validar/{hash_validacao}", response_model=CertificadoRead)
async def validar_certificado(
    hash_validacao: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Certificado).where(Certificado.hash_validacao == hash_validacao))
    cert = result.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificado invalido")
    return cert


@router.get("/usuario/{usuario_id}", response_model=list[CertificadoRead])
async def listar_certificados_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    result = await db.execute(select(Certificado).where(Certificado.usuario_id == usuario_id))
    return result.scalars().all()
