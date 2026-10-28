import uuid
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.credenciamento import AprovacaoHierarquica, SolicitacaoCredenciamento
from app.models.usuario import Perfil, Usuario, UsuarioPerfil
from app.schemas.usuario import UsuarioCreate
from app.services.auth import hash_password
from app.services.log_acesso import _ip_cliente

# Regras de autorização hierárquica
#
# Issue #123: a chave "administrador" nao existia. O perfil tem a permissao
# credenciamento:aprovar e passava na rota, mas pode_aprovar devolvia falso e a
# acao morria em 400 ("Autorização hierárquica negada") - era a mensagem
# "Fora do seu escopo de aprovação" que a Tatiana via na tela. Valia tanto para
# aprovar quanto para rejeitar, porque as duas usam a mesma tabela.
#
# O escopo do administrador segue a matriz de produto da issue #116: aprova
# administrador, gestor, instrutor e participante, e nao aprova auditor.
# "administrador_geral" ganhou administrador e auditor para o topo da hierarquia
# nunca poder menos que o nivel de baixo.
HIERARQUIA_APROVACAO = {
    "administrador_geral": ["administrador", "auditor", "instrutor", "gestor", "participante"],
    "administrador": ["administrador", "instrutor", "gestor", "participante"],
    "instrutor": ["gestor", "participante"],
    "gestor": ["participante"],
    "auditor": [],  # Perfil de leitura: não aprova ninguém
    "participante": [],  # Não pode aprovar ninguém
}


def pode_aprovar(perfil_aprovador: str, perfil_solicitado: str) -> bool:
    """
    Verifica se um perfil pode aprovar outro perfil
    conforme a hierarquia estabelecida
    """
    perfis_permitidos = HIERARQUIA_APROVACAO.get(perfil_aprovador, [])
    return perfil_solicitado in perfis_permitidos

def perfis_aprovaveis(nomes_perfis: list[str]) -> set[str]:
    """Uniao do que esses perfis podem aprovar.

    Uniao, e nao intersecao: um usuario pode ter varios perfis, e aprovar_solicitacao
    autoriza quando QUALQUER um deles permite. A lista pendente tem de mostrar
    exatamente o que ele conseguiria aprovar, senao volta a aparecer item com o
    botao negado (issue #123).
    """
    aprovaveis: set[str] = set()
    for nome in nomes_perfis:
        aprovaveis.update(HIERARQUIA_APROVACAO.get(nome, []))
    return aprovaveis


async def perfis_do_usuario(db: AsyncSession, usuario_id: uuid.UUID) -> list[str]:
    """Nomes dos perfis do usuario; cai em participante quando nao tem nenhum.

    Mesma regra que aprovar_solicitacao ja aplicava, extraida para a rota da
    lista pendente poder usar o mesmo criterio.
    """
    result = await db.execute(select(Perfil).join(UsuarioPerfil).where(UsuarioPerfil.usuario_id == usuario_id))
    return [p.nome for p in result.scalars().all()] or ["participante"]


async def criar_solicitacao_credenciamento(
    payload: UsuarioCreate, db: AsyncSession, request: Request | None = None
) -> SolicitacaoCredenciamento:
    """
    Cria uma solicitacao de credenciamento pendente
    Em vez de criar usuario ativo, cria solicitacao que precisa ser aprovada

    Issue #119: o aceite da LGPD passou a ser gravado aqui. A rota /auth/registro
    exigia payload.aceite_lgpd (422 sem ele) e este bloco descartava o valor, de
    modo que o usuario nascia com o default False do modelo: a pessoa marcava o
    termo no cadastro e a tela de Privacidade mostrava "pendente". Era o primeiro
    relato da Tatiana, que a issue dava como sem causa no codigo.
    """
    # Criar usuario com status_credenciamento='pendente'
    usuario = Usuario(
        nome_completo=payload.nome_completo,
        email=payload.email,
        cpf=payload.cpf,
        senha_hash=hash_password(payload.senha),
        orgao_instituicao=payload.orgao_instituicao,
        cargo=payload.cargo,
        telefone=payload.telefone,
        avatar_url=payload.avatar_url,
        ativo=False,  # Usuario fica inativo até aprovação
        status_credenciamento="pendente",  # Status de credenciamento pendente
        aceite_lgpd=payload.aceite_lgpd,
        data_aceite_lgpd=datetime.now(timezone.utc) if payload.aceite_lgpd else None,
        versao_termo_lgpd=settings.VERSAO_TERMO_LGPD if payload.aceite_lgpd else None,
        ip_aceite_lgpd=_ip_cliente(request) if request and payload.aceite_lgpd else None,
    )
    db.add(usuario)
    await db.flush()

    # Criar solicitacao de credenciamento
    solicitacao = SolicitacaoCredenciamento(
        usuario_id=usuario.id,
        perfil_solicitado=payload.perfil_solicitado,
        status="pendente",
    )
    db.add(solicitacao)
    await db.commit()
    await db.refresh(solicitacao)

    return solicitacao


async def aprovar_solicitacao(
    solicitacao_id: int, aprovador_id: uuid.UUID, observacao: str | None, db: AsyncSession
) -> dict:
    """
    Aprova uma solicitacao de credenciamento
    Cria usuario ativo, atribui perfil, marca solicitacao como aprovada
    """
    # Buscar solicitacao
    result = await db.execute(select(SolicitacaoCredenciamento).where(SolicitacaoCredenciamento.id == solicitacao_id))
    solicitacao = result.scalar_one_or_none()
    if not solicitacao:
        raise ValueError("Solicitacao não encontrada")
    if solicitacao.status != "pendente":
        raise ValueError("Solicitacao já foi processada")

    # Buscar perfil do aprovador
    result_aprovador = await db.execute(select(Usuario).where(Usuario.id == aprovador_id))
    aprovador = result_aprovador.scalar_one_or_none()
    if not aprovador:
        raise ValueError("Aprovador não encontrado")

    # Buscar perfis do aprovador para validar hierarquia
    nomes_aprovador = await perfis_do_usuario(db, aprovador_id)

    # Validar autorização hierárquica (qualquer perfil do aprovador pode aprovar)
    if not any(pode_aprovar(p, solicitacao.perfil_solicitado) for p in nomes_aprovador):
        raise ValueError(
            f"Nenhum dos perfis '{', '.join(nomes_aprovador)}' pode aprovar perfil "
            f"'{solicitacao.perfil_solicitado}'. Autorização hierárquica negada."
        )

    perfil_aprovador_nome = nomes_aprovador[0]

    # Buscar usuario solicitante
    result_usuario = await db.execute(select(Usuario).where(Usuario.id == solicitacao.usuario_id))
    usuario = result_usuario.scalar_one_or_none()
    if not usuario:
        raise ValueError("Usuario não encontrado")

    # Ativar usuario e atualizar campos de credenciamento
    usuario.ativo = True
    usuario.status_credenciamento = "aprovado"
    usuario.aprovado_por = aprovador_id
    usuario.data_aprovacao = datetime.now(timezone.utc)

    # Buscar perfil solicitado
    result_perfil = await db.execute(select(Perfil).where(Perfil.nome == solicitacao.perfil_solicitado))
    perfil = result_perfil.scalar_one_or_none()
    if perfil:
        # Atribuir perfil ao usuario (se ainda nao tiver -- provisionamento do
        # Keycloak ja cria o perfil; duplicar viola usuario_perfil_pkey -> 500).
        ja_tem = await db.execute(
            select(UsuarioPerfil).where(
                UsuarioPerfil.usuario_id == usuario.id,
                UsuarioPerfil.perfil_id == perfil.id,
            )
        )
        if not ja_tem.scalar_one_or_none():
            db.add(UsuarioPerfil(usuario_id=usuario.id, perfil_id=perfil.id))

    # Atualizar status da solicitacao
    solicitacao.status = "aprovado"
    solicitacao.avaliado_por = aprovador_id
    solicitacao.avaliado_em = datetime.now(timezone.utc)
    solicitacao.observacao_aprovacao = observacao

    # Criar registro de aprovacao hierarquica
    aprovacao = AprovacaoHierarquica(
        solicitacao_id=solicitacao.id,
        aprovador_id=aprovador_id,
        nivel_hierarquico=perfil_aprovador_nome,
        acao="aprovar",
        motivo=observacao,
    )
    db.add(aprovacao)

    await db.commit()
    await db.refresh(solicitacao)

    return {
        "message": "Solicitacao aprovada com sucesso",
        "solicitacao_id": solicitacao.id,
        "usuario_id": str(usuario.id),
        "status": solicitacao.status,
        "perfil_atribuido": solicitacao.perfil_solicitado,
        "aprovado_por": aprovador_id,
        "data_aprovacao": usuario.data_aprovacao,
    }


async def rejeitar_solicitacao(solicitacao_id: int, aprovador_id: uuid.UUID, motivo: str, db: AsyncSession) -> dict:
    """
    Rejeita uma solicitacao de credenciamento
    Marca solicitacao como rejeitada, usuario permanece inativo
    """
    # Buscar solicitacao
    result = await db.execute(select(SolicitacaoCredenciamento).where(SolicitacaoCredenciamento.id == solicitacao_id))
    solicitacao = result.scalar_one_or_none()
    if not solicitacao:
        raise ValueError("Solicitacao não encontrada")
    if solicitacao.status != "pendente":
        raise ValueError("Solicitacao já foi processada")

    # Buscar perfil do aprovador
    result_aprovador = await db.execute(select(Usuario).where(Usuario.id == aprovador_id))
    aprovador = result_aprovador.scalar_one_or_none()
    if not aprovador:
        raise ValueError("Aprovador não encontrado")

    # Buscar perfis do aprovador para validar hierarquia
    nomes_aprovador = await perfis_do_usuario(db, aprovador_id)

    # Validar autorização hierárquica (qualquer perfil do aprovador pode aprovar)
    if not any(pode_aprovar(p, solicitacao.perfil_solicitado) for p in nomes_aprovador):
        raise ValueError(
            f"Nenhum dos perfis '{', '.join(nomes_aprovador)}' pode rejeitar perfil "
            f"'{solicitacao.perfil_solicitado}'. Autorização hierárquica negada."
        )

    perfil_aprovador_nome = nomes_aprovador[0]

    # Buscar usuario solicitante
    result_usuario = await db.execute(select(Usuario).where(Usuario.id == solicitacao.usuario_id))
    usuario = result_usuario.scalar_one_or_none()
    if not usuario:
        raise ValueError("Usuario não encontrado")

    # Atualizar status do usuario
    usuario.status_credenciamento = "rejeitado"

    # Atualizar status da solicitacao
    solicitacao.status = "rejeitado"
    solicitacao.avaliado_por = aprovador_id
    solicitacao.avaliado_em = datetime.now(timezone.utc)
    solicitacao.motivo_rejeicao = motivo

    # Criar registro de aprovacao hierarquica
    aprovacao = AprovacaoHierarquica(
        solicitacao_id=solicitacao.id,
        aprovador_id=aprovador_id,
        nivel_hierarquico=perfil_aprovador_nome,
        acao="rejeitar",
        motivo=motivo,
    )
    db.add(aprovacao)

    await db.commit()
    await db.refresh(solicitacao)

    return {
        "message": "Solicitacao rejeitada",
        "solicitacao_id": solicitacao.id,
        "usuario_id": str(usuario.id),
        "status": solicitacao.status,
        "motivo": motivo,
        "rejeitado_por": aprovador_id,
        "data_rejeicao": solicitacao.avaliado_em,
    }
