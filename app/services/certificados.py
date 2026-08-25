"""Emissao de certificados digitais (US-15, T-15.2/15.3/15.4)."""

import hashlib
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.certificado import Certificado, ModeloCertificado
from app.models.curso import Curso
from app.models.usuario import Usuario
from app.services.certificado_templates import mascarar_cpf
from app.services.storage import upload_bytes


def _gerar_pdf_bytes(dados: dict) -> bytes:
    """Gera o PDF do certificado com reportlab (T-15.3)."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), rightMargin=30*mm, leftMargin=30*mm, topMargin=25*mm, bottomMargin=25*mm)

    styles = getSampleStyleSheet()
    azul = HexColor("#1a3d6d")
    titulo = ParagraphStyle("Titulo", parent=styles["Title"], fontSize=36, textColor=azul, spaceAfter=24, alignment=1)
    normal = ParagraphStyle("Normal", parent=styles["Normal"], fontSize=16, alignment=1, spaceAfter=10)
    nome = ParagraphStyle("Nome", parent=normal, fontSize=26, bold=True, spaceBefore=8, spaceAfter=8)
    pequeno = ParagraphStyle("Pequeno", parent=styles["Normal"], fontSize=11, textColor=HexColor("#888888"), alignment=1, spaceBefore=18)

    conteudo = []
    conteudo.append(Paragraph("CERTIFICADO", titulo))
    conteudo.append(Paragraph("Conferimos a", normal))
    conteudo.append(Paragraph(dados["nome"], nome))
    conteudo.append(Paragraph(f"CPF: {dados['cpf']} · {dados['prefeitura']}", normal))
    conteudo.append(Paragraph("a conclusão com aproveitamento do curso", normal))
    conteudo.append(Paragraph(dados["curso"], nome))
    conteudo.append(Paragraph(f"Carga horária: {dados['carga_horaria']} horas", normal))
    conteudo.append(Paragraph(f"Nota final: {dados['nota']} · Emitido em {dados['data']}", normal))
    conteudo.append(Spacer(1, 20))
    conteudo.append(Paragraph("_____________________________", normal))
    conteudo.append(Paragraph("Coordenação de Capacitação", normal))
    conteudo.append(Paragraph(f"Código de validação: {dados['codigo']}", pequeno))

    doc.build(conteudo)
    return buf.getvalue()


def _gerar_qr_bytes(url: str) -> bytes:
    """Gera o QR Code apontando para a pagina publica de validacao (T-15.4)."""
    import qrcode
    from PIL import Image

    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _url_validacao(hash_validacao: str) -> str:
    base = settings.BASE_URL.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[: -len("/api/v1")]
    return f"{base}/certificados/validar/{hash_validacao}"


async def _modelo_padrao(db: AsyncSession) -> ModeloCertificado:
    """Retorna o modelo ativo; cria o padrao na hora se nao existir (nao depende do seed)."""
    from app.services.certificado_templates import TEMPLATE_CERTIFICADO_PADRAO

    result = await db.execute(
        select(ModeloCertificado).where(ModeloCertificado.ativo).order_by(ModeloCertificado.id).limit(1)
    )
    modelo = result.scalars().first()
    if modelo:
        return modelo
    modelo = ModeloCertificado(
        nome="Padrao GE21",
        template_html=TEMPLATE_CERTIFICADO_PADRAO(),
        assinatura_digital=False,
        ativo=True,
    )
    db.add(modelo)
    await db.flush()
    return modelo


async def emitir_certificado_curso(
    db: AsyncSession,
    usuario: Usuario,
    curso: Curso,
    nota_final: Decimal | None,
) -> Certificado | None:
    """Emite o certificado do curso ao concluir (T-15.2). Retorna None se ja emitido."""
    existente = await db.execute(
        select(Certificado).where(
            Certificado.usuario_id == usuario.id,
            Certificado.curso_id == curso.id,
        )
    )
    if existente.scalar_one_or_none():
        return None

    modelo = await _modelo_padrao(db)

    cert_id = uuid.uuid4()
    hash_validacao = hashlib.sha256(f"{cert_id}:{usuario.id}:{curso.id}".encode()).hexdigest()

    agora = datetime.now(timezone.utc)
    dados = {
        "nome": usuario.nome_completo or "Participante",
        "cpf": mascarar_cpf(usuario.cpf),
        "prefeitura": usuario.orgao_instituicao or "Prefeitura",
        "curso": curso.titulo,
        "carga_horaria": curso.carga_horaria or 0,
        "nota": f"{nota_final:.2f}" if nota_final is not None else "-",
        "data": agora.strftime("%d/%m/%Y"),
        "codigo": hash_validacao,
    }

    url_validacao = _url_validacao(hash_validacao)
    try:
        pdf_bytes = _gerar_pdf_bytes(dados)
        url_pdf = await upload_bytes(pdf_bytes, f"certificado_{cert_id}.pdf", "certificados", "application/pdf")
        qr_bytes = _gerar_qr_bytes(url_validacao)
        url_qr = await upload_bytes(qr_bytes, f"certificado_{cert_id}_qr.png", "certificados", "image/png")
    except Exception:
        url_pdf = None
        url_qr = None

    cert = Certificado(
        id=cert_id,
        usuario_id=usuario.id,
        curso_id=curso.id,
        modelo_id=modelo.id,
        nota_final=nota_final,
        carga_horaria=curso.carga_horaria or 0,
        url_pdf=url_pdf,
        qr_code_url=url_qr,
        hash_validacao=hash_validacao,
    )
    db.add(cert)
    await db.flush()
    return cert