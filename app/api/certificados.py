import hashlib
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.certificado import Certificado, ModeloCertificado
from app.models.usuario import Usuario
from app.services.rbac import Permissoes
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
    _: Usuario = Depends(require_permissao(Permissoes.CERTIFICADO_CRIAR)),
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
    _: Usuario = Depends(require_permissao(Permissoes.CERTIFICADO_CRIAR)),
):
    cert = Certificado(**payload.model_dump())
    db.add(cert)
    await db.flush()
    cert.hash_validacao = hashlib.sha256(str(cert.id).encode()).hexdigest()
    await db.commit()
    await db.refresh(cert)
    return cert


@router.get("/meus", response_model=list[CertificadoRead])
async def meus_certificados(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Certificados do participante logado (T-15.6) — sem exigir permissao admin."""
    result = await db.execute(
        select(Certificado).where(Certificado.usuario_id == current_user.id).order_by(Certificado.emitido_em.desc())
    )
    return result.scalars().all()


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


@router.get("/validar/{hash_validacao}/pagina", response_class=HTMLResponse)
async def pagina_validacao(
    hash_validacao: str,
    db: AsyncSession = Depends(get_db),
):
    """Pagina publica de validacao do certificado (T-15.5) — sem login."""
    from app.models.curso import Curso
    from app.models.usuario import Usuario
    from app.services.certificado_templates import mascarar_cpf, render_pagina_validacao

    result = await db.execute(select(Certificado).where(Certificado.hash_validacao == hash_validacao))
    cert = result.scalar_one_or_none()
    if not cert:
        return HTMLResponse(
            render_pagina_validacao(
                {
                    "SELO": "&#10060;",
                    "CLASSE": "invalido",
                    "STATUS": "Certificado INVALIDO",
                    "NOME": "-",
                    "CPF": "-",
                    "PREFEITURA": "-",
                    "CURSO": "-",
                    "CARGA_HORARIA": "-",
                    "NOTA": "-",
                    "DATA": "-",
                    "QR_CODE_HTML": "",
                    "CODIGO": hash_validacao,
                }
            ),
            status_code=200,
        )

    usuario = await db.get(Usuario, cert.usuario_id)
    curso = await db.get(Curso, cert.curso_id)
    nome = usuario.nome_completo if usuario else "Participante"
    prefeitura = usuario.orgao_instituicao if usuario else "Prefeitura"
    cpf = mascarar_cpf(usuario.cpf) if usuario else "-"
    return HTMLResponse(
        render_pagina_validacao(
            {
                "SELO": "&#9989;",
                "CLASSE": "",
                "STATUS": "Certificado VALIDO",
                "NOME": nome,
                "CPF": cpf,
                "PREFEITURA": prefeitura,
                "CURSO": curso.titulo if curso else "-",
                "CARGA_HORARIA": cert.carga_horaria,
                "NOTA": f"{cert.nota_final:.2f}" if cert.nota_final is not None else "-",
                "DATA": cert.emitido_em.strftime("%d/%m/%Y"),
                "QR_CODE_HTML": f'<img class="qrcode" src="{cert.qr_code_url}" alt="QR Code" width="120">' if cert.qr_code_url else "",
                "CODIGO": cert.hash_validacao,
            }
        )
    )


@router.get("/usuario/{usuario_id}", response_model=list[CertificadoRead])
async def listar_certificados_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.CERTIFICADO_VISUALIZAR)),
):
    result = await db.execute(select(Certificado).where(Certificado.usuario_id == usuario_id))
    return result.scalars().all()
