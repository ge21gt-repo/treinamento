# LMS IDE-SP — Backend API

Backend da Plataforma de Capacitacao e Treinamento do Projeto IDE-SP.

## Stack

- **Python 3.12** + **FastAPI**
- **PostgreSQL 15+** com schema `lms`
- **SQLAlchemy 2.0** (async) + **Alembic** (migrations)
- **JWT** (python-jose) + **bcrypt** (passlib)
- Deploy via **fly.io**

## Requisitos

- Python 3.12+
- PostgreSQL 15+

## Setup Local

```bash
# Criar venv e instalar dependencias
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configurar banco
cp .env.example .env
# Edite .env com sua DATABASE_URL

# Criar schema e rodar migrations
alembic upgrade head

# Seed inicial (perfis e niveis)
psql $DATABASE_URL -f scripts/init_db.sql

# Rodar servidor
uvicorn app.main:app --reload
```

## Endpoints

Acesse `/docs` para a documentacao interativa (Swagger UI).

### Dominios

| Prefixo | Descricao |
|---------|-----------|
| `/api/v1/auth` | Registro e login |
| `/api/v1/usuarios` | CRUD de usuarios e perfis |
| `/api/v1/trilhas` | Trilhas de aprendizagem |
| `/api/v1/cursos` | Cursos, modulos, unidades, inscricoes, progresso |
| `/api/v1/conteudos` | Conteudos e materiais complementares |
| `/api/v1/avaliacoes` | Avaliacoes, questoes, alternativas, respostas |
| `/api/v1/gamificacao` | XP, badges, missoes, streaks, leaderboard |
| `/api/v1/sessoes` | Sessoes ao vivo e presenca |
| `/api/v1/comunicacao` | Chat e forum |
| `/api/v1/certificados` | Modelos e emissao de certificados |
| `/api/v1/dashboard` | Analytics e metricas |

## Deploy (fly.io)

```bash
fly launch
fly postgres create --name lms-idesp-db --region gru
fly postgres attach lms-idesp-db
fly secrets set SECRET_KEY="sua-chave-secreta"
fly deploy
```

## Modelo de Dados

28 tabelas organizadas em 9 dominios funcionais no schema `lms`.
Veja `scripts/init_db.sql` para o DDL completo e seeds.
