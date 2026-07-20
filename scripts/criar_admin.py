#!/usr/bin/env python3
"""Script para criar o primeiro usuário administrador_geral (bootstrap).

Uso:
    python scripts/criar_admin.py --email admin@exemplo.com --senha "SenhaForte123!"
    python scripts/criar_admin.py  # modo interativo, pergunta email/senha

Variáveis de ambiente:
    ADMIN_EMAIL, ADMIN_SENHA — para uso não-interativo (CI/Docker).
"""

import argparse
import getpass
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.services.auth import hash_password


async def criar_admin(email: str, senha: str) -> bool:
    url = settings.TEST_DATABASE_URL or settings.DATABASE_URL
    engine = create_async_engine(url)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS lms"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lms.perfis (
                id SERIAL PRIMARY KEY, nome VARCHAR(50) UNIQUE NOT NULL,
                descricao TEXT, permissoes JSONB, criado_em TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        await conn.execute(text("""
            INSERT INTO lms.perfis (nome, descricao)
            VALUES ('administrador_geral', 'Gerencia total da plataforma')
            ON CONFLICT (nome) DO NOTHING
        """))

        r = await conn.execute(
            text("SELECT id FROM lms.perfis WHERE nome = 'administrador_geral'")
        )
        perfil_id = r.scalar_one()

        r = await conn.execute(
            text("""
                SELECT u.id FROM lms.usuarios u
                JOIN lms.usuario_perfil up ON u.id = up.usuario_id
                WHERE up.perfil_id = :pid LIMIT 1
            """),
            {"pid": perfil_id},
        )
        if r.scalar_one_or_none():
            print("Já existe um administrador_geral cadastrado. Nada foi alterado.")
            await engine.dispose()
            return False

        admin_id = uuid.uuid4()
        await conn.execute(
            text("""
                INSERT INTO lms.usuarios
                    (id, nome_completo, email, senha_hash, ativo,
                     status_credenciamento, aceite_lgpd)
                VALUES (:id, 'Administrador Geral', :email, :hash, true, 'aprovado', true)
            """),
            {"id": admin_id, "email": email, "hash": hash_password(senha)},
        )
        await conn.execute(
            text("""
                INSERT INTO lms.usuario_perfil (usuario_id, perfil_id, atribuido_por)
                VALUES (:uid, :pid, :uid)
            """),
            {"uid": admin_id, "pid": perfil_id},
        )
        print(f"Administrador_geral criado com sucesso!")
        print(f"  Email: {email}")
        print(f"  ID:    {admin_id}")
        print("Faça login em /api/v1/auth/login para obter o token JWT.")
        await engine.dispose()
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Cria o primeiro administrador_geral da plataforma"
    )
    parser.add_argument("--email", help="Email do administrador")
    parser.add_argument("--senha", help="Senha do administrador")
    args = parser.parse_args()

    email = args.email or os.environ.get("ADMIN_EMAIL")
    senha = args.senha or os.environ.get("ADMIN_SENHA")

    if not email:
        email = input("Email do administrador: ").strip()
    if not senha:
        senha = getpass.getpass("Senha do administrador: ")

    if not email or not senha:
        print("Email e senha são obrigatórios.", file=sys.stderr)
        sys.exit(1)

    import asyncio

    success = asyncio.run(criar_admin(email, senha))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
