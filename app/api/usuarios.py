import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import check_unique_fields
from app.api.deps import get_current_user, require_permissao
from app.database import get_db
from app.models.credenciamento import AprovacaoHierarquica, SolicitacaoCredenciamento
from app.models.usuario import Perfil, Usuario, UsuarioPerfil, UsuarioPreferencias
from app.services.paginacao import apply_search, count_query
from app.services.rbac import Permissoes, can_create_perfil
from app.config import settings
from app.schemas.usuario import (
    AceiteLgpdRead,
    AceiteLgpdRequest,
    CriarSubordinadoRequest,
    PerfilCreate,
    PerfilRead,
    PerfilUpdate,
    PreferenciasRead,
    PreferenciasUpdate,
    UsuarioPerfilCreate,
    UsuarioRead,
    UsuarioUpdate,
    UsuarioUpdateMe,
    validar_preferencias,
)
from app.services.auth import hash_password
from app.services.lgpd import aceite_pendente
from app.services.log_acesso import _ip_cliente

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("/me", response_model=UsuarioRead)
async def me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    # Issue #100: o Keycloak nao passa por POST /auth/login. Registrar o login
    # aqui — mas so quando a sessao e nova (issue #100, efeito colateral): o
    # front chama /me a cada F5 e a cada renovacao silenciosa do token, entao
    # gravar sempre infla o log_acesso e o relatorio "quem acessou".
    if current_user.auth_provider == "keycloak":
        await _registrar_login_keycloak_se_novo(db, request, current_user)
    return current_user


async def _registrar_login_keycloak_se_novo(
    db: AsyncSession, request: Request, current_user: Usuario
) -> None:
    """Grava acao=login so se a autenticacao Keycloak for nova (issue #100).

    Usa o `auth_time` do token (quando a pessoa de fato se autenticou), que se
    mantem nas renovacoes. Sem `auth_time`, usa uma janela de 30 min: nao grava
    se ja houver um login da pessoa nesse intervalo.
    """
    from datetime import timedelta

    from app.models.log import LogAcesso
    from app.services.log_acesso import registrar_log_acesso

    auth_time = None
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        from app.services.keycloak import validar_token_keycloak

        payload = validar_token_keycloak(auth.split(" ", 1)[1]) or {}
        at = payload.get("auth_time")
        if at:
            auth_time = datetime.fromtimestamp(int(at), tz=timezone.utc)
    if auth_time is None:
        auth_time = datetime.now(timezone.utc) - timedelta(minutes=30)

    ja = (
        await db.execute(
            select(LogAcesso.id)
            .where(
                LogAcesso.usuario_id == current_user.id,
                LogAcesso.acao == "login",
                LogAcesso.criado_em >= auth_time,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if ja:
        return
    await registrar_log_acesso(
        db, request, usuario_id=current_user.id, acao="login", recurso_tipo="/api/v1/usuarios/me"
    )
    await db.commit()


@router.patch("/me", response_model=UsuarioRead)
async def atualizar_me(
    payload: UsuarioUpdateMe,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Edita o proprio cadastro (issue #94).

    So aceita campos nao sensiveis (nome, telefone, orgao, cargo, avatar).
    Email, ativo, cpf e perfis ficam fora (extra=forbid). Unicidade de telefone
    e checada antes. Audita como `atualizar` em usuarios.
    """
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    if "telefone" in dados and dados["telefone"]:
        existing = await db.execute(
            select(Usuario).where(Usuario.telefone == dados["telefone"], Usuario.id != current_user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Telefone ja cadastrado")

    from app.services.auditoria import _serializar

    dados_antes = _serializar(current_user)
    for campo, valor in dados.items():
        setattr(current_user, campo, valor)
    await db.commit()
    await db.refresh(current_user)

    from app.services.auditoria import registrar_auditoria

    await registrar_auditoria(
        db, tabela="usuarios", registro_id=current_user.id, acao="atualizar",
        dados_anteriores=dados_antes, dados_novos=_serializar(current_user),
        usuario_id=current_user.id, request=request,
    )
    await db.commit()
    return current_user


async def _ler_preferencias(db: AsyncSession, usuario_id: uuid.UUID) -> PreferenciasRead:
    """Le a linha de preferencias como colunas, nao como objeto ORM (issue #124).

    Colunas e nao ORM de proposito: depois de um commit os atributos do objeto
    ficam expirados, e serializar um deles dispara IO sincrono em contexto
    async - o MissingGreenlet que virava 500 na issue #114.
    """
    linha = (
        await db.execute(
            select(UsuarioPreferencias.dados, UsuarioPreferencias.atualizado_em).where(
                UsuarioPreferencias.usuario_id == usuario_id
            )
        )
    ).first()
    if linha is None:
        return PreferenciasRead(dados={}, atualizado_em=None)
    return PreferenciasRead(dados=linha[0] or {}, atualizado_em=linha[1])


@router.get("/me/preferencias", response_model=PreferenciasRead)
async def minhas_preferencias(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Preferencias de interface do proprio usuario (issue #124).

    Quem nunca gravou recebe dados vazio e atualizado_em nulo, e nenhuma linha
    e criada: o front le isto a cada entrada, e criar linha na leitura encheria
    a tabela de linhas vazias de quem nunca mexeu em preferencia alguma.

    So o proprio usuario le as suas: o id sai do token, nao do caminho, logo
    nao existe forma de pedir as preferencias de outra pessoa.
    """
    return await _ler_preferencias(db, current_user.id)


@router.patch("/me/preferencias", response_model=PreferenciasRead)
async def atualizar_minhas_preferencias(
    payload: PreferenciasUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Mescla rasa nas preferencias do proprio usuario (issue #124).

    Mescla, e nao substituicao: duas abas ou dois dispositivos gravando
    preferencias diferentes nao apagam a escolha um do outro, o que um PUT do
    objeto inteiro faria. Chave com valor null e removida.

    Sem auditoria, como a issue pede: e preferencia de interface, nao dado
    cadastral, e o front grava a cada mudanca - a auditoria viraria ruido.
    """
    for tentativa in (1, 2):
        # FOR UPDATE: sem o lock, duas gravacoes simultaneas leem o mesmo
        # estado e a ultima a gravar apaga a chave da outra - exatamente o que
        # a mescla existe para evitar.
        pref = (
            await db.execute(
                select(UsuarioPreferencias)
                .where(UsuarioPreferencias.usuario_id == current_user.id)
                .with_for_update()
            )
        ).scalar_one_or_none()

        atual = dict(pref.dados or {}) if pref is not None else {}
        for chave, valor in payload.dados.items():
            if valor is None:
                atual.pop(chave, None)
            else:
                atual[chave] = valor

        # O limite vale para o que fica guardado, nao so para o corpo: duas
        # gravacoes de 10 KB passariam uma a uma e deixariam 20 KB na linha.
        try:
            validar_preferencias(atual)
        except ValueError as erro:
            raise HTTPException(status_code=422, detail=str(erro)) from erro

        if pref is None:
            db.add(UsuarioPreferencias(usuario_id=current_user.id, dados=atual))
        else:
            # Dict novo, nao mutacao no lugar: o JSONB nao e MutableDict, e
            # alterar o dict existente nao marca o atributo como sujo - o
            # UPDATE nao sairia.
            pref.dados = atual

        try:
            await db.commit()
        except IntegrityError:
            # Primeira gravacao simultanea de duas abas: as duas encontram a
            # linha inexistente e as duas tentam inserir. Relendo, a segunda
            # mescla sobre o que a primeira gravou em vez de devolver erro e
            # perder a preferencia.
            await db.rollback()
            if tentativa == 2:
                raise
            continue
        break

    return await _ler_preferencias(db, current_user.id)


@router.post("/me/aceite-lgpd", response_model=AceiteLgpdRead)
async def aceitar_lgpd(
    request: Request,
    payload: AceiteLgpdRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Registra o aceite do termo pelo proprio usuario (issue #119).

    Idempotente: aceitar de novo a MESMA versao nao mexe na data do primeiro
    aceite. A data e o fato que interessa - sobrescreve-la a cada chamada do
    front apagaria quando a pessoa de fato consentiu. Aceitar uma versao nova
    grava data, IP e versao novos.

    So o proprio usuario: o id sai do token, nao do corpo nem do caminho.
    """
    versao = (payload.versao_termo if payload and payload.versao_termo else None) or settings.VERSAO_TERMO_LGPD

    ja_aceito = current_user.aceite_lgpd and (current_user.versao_termo_lgpd or "") == versao
    if not ja_aceito:
        from app.services.auditoria import _serializar, registrar_auditoria

        dados_antes = _serializar(current_user)
        current_user.aceite_lgpd = True
        current_user.data_aceite_lgpd = datetime.now(timezone.utc)
        current_user.versao_termo_lgpd = versao
        current_user.ip_aceite_lgpd = _ip_cliente(request)

        # Snapshot montado antes do commit e auditoria na mesma transacao, pelo
        # motivo da #114. Aqui a auditoria nao e ruido como nas preferencias
        # (#124): consentimento e fato juridico, e log_auditoria tem trigger de
        # imutabilidade - e o que da o historico dos aceites, que a linha do
        # usuario nao da, porque guarda so o ultimo.
        dados_novos = _serializar(current_user)
        await registrar_auditoria(
            db,
            tabela="usuarios",
            registro_id=current_user.id,
            acao="aceite_lgpd",
            dados_anteriores=dados_antes,
            dados_novos=dados_novos,
            usuario_id=current_user.id,
            request=request,
        )
        await db.commit()

    return AceiteLgpdRead(
        aceite_lgpd=True,
        data_aceite_lgpd=current_user.data_aceite_lgpd,
        versao_termo_lgpd=current_user.versao_termo_lgpd,
        aceite_lgpd_pendente=aceite_pendente(True, current_user.versao_termo_lgpd),
    )


@router.get("", response_model=list[UsuarioRead])
async def listar_usuarios(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    perfil_nome: str | None = Query(None, description="Filtrar por nome do perfil"),
    q: str | None = Query(None, description="Busca textual por nome ou email"),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    _: Usuario = Depends(require_permissao(Permissoes.USUARIO_LISTAR)),
):
    query = select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil))

    if perfil_nome:
        query = (
            query.join(UsuarioPerfil, Usuario.id == UsuarioPerfil.usuario_id)
            .join(Perfil)
            .where(Perfil.nome == perfil_nome)
        )

    query = apply_search(query, [Usuario.nome_completo, Usuario.email], q)
    total = await count_query(db, query)

    result = await db.execute(query.offset(skip).limit(limit))
    items = result.scalars().all()

    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/{usuario_id}", response_model=UsuarioRead)
async def obter_usuario(
    usuario_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.USUARIO_LISTAR)),
):
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.id == usuario_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    return user


async def _checar_unicidade_edicao(db: AsyncSession, usuario_id: uuid.UUID, dados: dict):
    """Valida unicidade de email e telefone numa edicao, ignorando a propria linha.

    O check_unique_fields de auth.py serve ao cadastro: nao exclui usuario
    nenhum, entao reenviar o mesmo email no PATCH daria 409 indevido. Sem esta
    checagem o valor repetido violava o unique do banco e subia como 500 -
    a convencao do projeto e validar antes do UPDATE e devolver 4xx.
    """
    for campo, rotulo in (("email", "Email"), ("telefone", "Telefone")):
        valor = dados.get(campo)
        if not valor:
            continue
        existente = await db.scalar(
            select(Usuario.id).where(getattr(Usuario, campo) == valor, Usuario.id != usuario_id)
        )
        if existente:
            raise HTTPException(status_code=409, detail=f"{rotulo} ja cadastrado")


@router.patch("/{usuario_id}", response_model=UsuarioRead)
async def atualizar_usuario(
    usuario_id: uuid.UUID,
    payload: UsuarioUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.USUARIO_EDITAR)),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    from app.services.auditoria import _serializar

    # LGPD: nao gravar senha/cpf/telefone em claro no snapshot de auditoria.
    dados_antes = _serializar(user)
    dados_antes.pop("senha_hash", None)
    dados_antes.pop("cpf", None)
    dados_antes.pop("telefone", None)
    dados = payload.model_dump(exclude_unset=True)
    await _checar_unicidade_edicao(db, usuario_id, dados)
    for field, value in dados.items():
        setattr(user, field, value)
    from app.services.auditoria import registrar_auditoria

    # Issue #114: o snapshot e montado ANTES do commit. Serializar depois tocava
    # atributo expirado e disparava IO sincrono em contexto async
    # (MissingGreenlet), virando 500 com o UPDATE ja gravado. Pelo mesmo motivo
    # o UPDATE e a auditoria agora vao num commit unico: erro na auditoria nao
    # deixa mais a alteracao gravada sem registro.
    dados_novos = _serializar(user)
    dados_novos.pop("senha_hash", None)
    dados_novos.pop("cpf", None)
    dados_novos.pop("telefone", None)
    await registrar_auditoria(
        db, tabela="usuarios", registro_id=usuario_id, acao="atualizar",
        dados_anteriores=dados_antes, dados_novos=dados_novos,
        usuario_id=current_user.id, request=request,
    )
    try:
        await db.commit()
    except IntegrityError:
        # Corrida entre a checagem acima e o commit (duas edicoes simultaneas
        # para o mesmo email/telefone). Sem isto a violacao de unique sobe 500.
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email ou telefone ja cadastrado")
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.id == usuario_id)
    )
    return result.scalar_one()


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_usuario(
    usuario_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_permissao(Permissoes.USUARIO_EXCLUIR)),
):
    result = await db.execute(select(Usuario).where(Usuario.id == usuario_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    from app.services.auditoria import _serializar

    # LGPD: nao gravar senha/cpf/telefone em claro no snapshot de auditoria.
    dados_antes = _serializar(user)
    dados_antes.pop("senha_hash", None)
    dados_antes.pop("cpf", None)
    dados_antes.pop("telefone", None)
    from app.services.auditoria import registrar_auditoria

    # Issue #114: delete e auditoria no mesmo commit. Antes eram dois, e uma
    # falha no segundo apagava o usuario sem deixar linha de auditoria.
    await db.delete(user)
    await registrar_auditoria(
        db, tabela="usuarios", registro_id=usuario_id, acao="excluir",
        dados_anteriores=dados_antes, usuario_id=current_user.id, request=request,
    )
    await db.commit()


# --- Perfis ---


@router.get("/perfis/todos", response_model=list[PerfilRead])
async def listar_perfis(
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.USUARIO_LISTAR)),
):
    result = await db.execute(select(Perfil))
    return result.scalars().all()


@router.post("/perfis", response_model=PerfilRead, status_code=status.HTTP_201_CREATED)
async def criar_perfil(
    payload: PerfilCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.PERFIL_CRIAR)),
):
    perfil = Perfil(**payload.model_dump())
    db.add(perfil)
    await db.commit()
    await db.refresh(perfil)
    return perfil


@router.post("/perfis/atribuir", status_code=status.HTTP_201_CREATED)
async def atribuir_perfil(
    payload: UsuarioPerfilCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.PERFIL_ATRIBUIR)),
    current_user: Usuario = Depends(get_current_user),
):
    up = UsuarioPerfil(
        usuario_id=payload.usuario_id,
        perfil_id=payload.perfil_id,
        atribuido_por=current_user.id,
    )
    db.add(up)
    await db.commit()
    return {"detail": "Perfil atribuido com sucesso"}


@router.patch("/perfis/{perfil_id}", response_model=PerfilRead)
async def atualizar_perfil(
    perfil_id: int,
    payload: PerfilUpdate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.PERFIL_EDITAR)),
):
    result = await db.execute(select(Perfil).where(Perfil.id == perfil_id))
    perfil = result.scalar_one_or_none()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(perfil, field, value)
    await db.commit()
    await db.refresh(perfil)
    return perfil


@router.delete("/perfis/{perfil_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_perfil(
    perfil_id: int,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_permissao(Permissoes.PERFIL_EXCLUIR)),
):
    result = await db.execute(select(Perfil).where(Perfil.id == perfil_id))
    perfil = result.scalar_one_or_none()
    if not perfil:
        raise HTTPException(status_code=404, detail="Perfil nao encontrado")
    # Nao permitir excluir perfil com usuarios vinculados
    count_result = await db.execute(
        select(func.count()).select_from(UsuarioPerfil).where(UsuarioPerfil.perfil_id == perfil_id)
    )
    if count_result.scalar_one() > 0:
        raise HTTPException(
            status_code=409, detail="Perfil possui usuarios vinculados. Remova os vinculos antes de excluir."
        )
    await db.delete(perfil)
    await db.commit()


@router.post("/criar-subordinado", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
async def criar_subordinado(
    payload: CriarSubordinadoRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
    _: None = Depends(require_permissao(Permissoes.USUARIO_CRIAR)),
):
    """Endpoint para gestor criar conta de subordinado com perfil definido"""
    # Verificar se o perfil solicitado existe no banco
    perfil_existente = await db.execute(select(Perfil).where(Perfil.nome == payload.perfil))
    perfil = perfil_existente.scalar_one_or_none()
    if not perfil:
        raise HTTPException(status_code=400, detail=f"Perfil '{payload.perfil}' não encontrado")

    # Validar hierarquia: quem cria pode criar este perfil?
    perfis_criador = [up.perfil.nome for up in current_user.perfis] if current_user.perfis else []
    autorizado = any(can_create_perfil(p, payload.perfil) for p in perfis_criador)
    if not autorizado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Seu perfil não tem permissão para criar usuários do perfil '{payload.perfil}'",
        )

    # Issue #119 item 1: o aceite deixou de ser exigido aqui. Quem cria a conta
    # nao pode consentir pelo outro - a propria pessoa aceita no primeiro
    # acesso, pela rota POST /usuarios/me/aceite-lgpd. O campo aceite_lgpd
    # continua aceito no corpo, para nao quebrar quem ja chama, mas e ignorado.

    # Verificar unicidade de email, CPF e telefone
    await check_unique_fields(db, payload.email, payload.cpf, payload.telefone)

    # Criar usuario subordinado
    subordinado = Usuario(
        nome_completo=payload.nome_completo,
        email=payload.email,
        cpf=payload.cpf,
        senha_hash=hash_password(payload.senha),
        orgao_instituicao=payload.orgao_instituicao,
        cargo=payload.cargo,
        telefone=payload.telefone,
        ativo=True,
        status_credenciamento="aprovado",
        criado_por=current_user.id,
        # Issue #119 item 1: nasce sem aceite, como o usuario do Keycloak.
        aceite_lgpd=False,
        data_aceite_lgpd=None,
    )
    db.add(subordinado)
    await db.flush()

    # Atribuir perfil solicitado
    db.add(UsuarioPerfil(usuario_id=subordinado.id, perfil_id=perfil.id, atribuido_por=current_user.id))

    # Criar solicitacao de credenciamento como aprovada (trilha de auditoria)
    solicitacao = SolicitacaoCredenciamento(
        usuario_id=subordinado.id,
        perfil_solicitado=payload.perfil,
        status="aprovado",
        avaliado_por=current_user.id,
        avaliado_em=datetime.now(timezone.utc),
    )
    db.add(solicitacao)
    await db.flush()

    # Registrar aprovacao hierarquica
    perfis_criador = [up.perfil.nome for up in current_user.perfis] if current_user.perfis else []
    nivel_hierarquico = perfis_criador[0] if perfis_criador else "participante"
    db.add(AprovacaoHierarquica(
        solicitacao_id=solicitacao.id,
        aprovador_id=current_user.id,
        nivel_hierarquico=nivel_hierarquico,
        acao="aprovar",
        motivo="Criado por superior hierarquico",
    ))

    await db.commit()
    await db.refresh(subordinado)
    # Issue #85: criar subordinado tambem gera auditoria (como PATCH/DELETE).
    from app.services.auditoria import _serializar, registrar_auditoria

    dados_novos = _serializar(subordinado)
    dados_novos.pop("senha_hash", None)
    dados_novos.pop("cpf", None)
    dados_novos.pop("telefone", None)
    await registrar_auditoria(
        db, tabela="usuarios", registro_id=subordinado.id, acao="criar",
        dados_novos=dados_novos, usuario_id=current_user.id, request=request,
    )
    await db.commit()
    # Carregar perfis para o schema UsuarioRead
    result = await db.execute(
        select(Usuario).options(selectinload(Usuario.perfis).selectinload(UsuarioPerfil.perfil)).where(Usuario.id == subordinado.id)
    )
    return result.scalar_one()
