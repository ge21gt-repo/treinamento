import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class ModeloCertificadoBase(BaseModel):
    nome: str
    template_html: str
    logo_url: str | None = None
    assinatura_digital: bool = False
    ativo: bool = True


class ModeloCertificadoCreate(ModeloCertificadoBase):
    pass


class ModeloCertificadoRead(ModeloCertificadoBase):
    id: int
    criado_em: datetime

    model_config = {"from_attributes": True}


class CertificadoBase(BaseModel):
    usuario_id: uuid.UUID
    curso_id: int
    modelo_id: int | None = None
    nota_final: Decimal | None = None
    carga_horaria: int
    valido_ate: date | None = None


class CertificadoCreate(CertificadoBase):
    pass


class CertificadoRead(CertificadoBase):
    id: uuid.UUID
    url_pdf: str | None = None
    qr_code_url: str | None = None
    hash_validacao: str | None = None
    emitido_em: datetime

    model_config = {"from_attributes": True}
