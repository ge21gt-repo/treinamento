"""Templates de certificado (US-15, T-15.1)."""


def mascarar_cpf(cpf: str | None) -> str:
    """Mascara o CPF no formato ***.456.789-** (LGPD)."""
    if not cpf:
        return "-"
    digits = "".join(d for d in cpf if d.isdigit())
    if len(digits) != 11:
        return cpf
    return f"***.***.789-**"


def TEMPLATE_CERTIFICADO_PADRAO() -> str:
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  body { font-family: Georgia, serif; margin: 0; padding: 0; }
  .certificado { border: 8px double #1a3d6d; margin: 40px; padding: 40px; text-align: center; }
  .titulo { font-size: 42px; color: #1a3d6d; letter-spacing: 4px; margin: 10px 0; }
  .texto { font-size: 18px; color: #333; margin: 20px 0; }
  .nome { font-size: 32px; color: #000; font-weight: bold; margin: 20px 0; }
  .dados { font-size: 16px; color: #555; margin: 10px 0; }
  .codigo { font-size: 13px; color: #888; margin-top: 30px; word-break: break-all; }
  .assinatura { margin-top: 50px; font-size: 14px; color: #666; }
</style>
</head>
<body>
<div class="certificado">
  <div class="titulo">CERTIFICADO</div>
  <div class="texto">Conferimos a</div>
  <div class="nome">{{NOME}}</div>
  <div class="dados">CPF: {{CPF}} · {{PREFEITURA}}</div>
  <div class="texto">a conclusão com aproveitamento do curso</div>
  <div class="nome" style="font-size:24px;">{{CURSO}}</div>
  <div class="dados">Carga horária: {{CARGA_HORARIA}} horas</div>
  <div class="dados">Nota final: {{NOTA}} · Emitido em {{DATA}}</div>
  <div class="assinatura">_____________________________<br>Coordenação de Capacitação</div>
  <div class="codigo">Código de validação: {{CODIGO}}</div>
</div>
</body>
</html>"""


def render_template_certificado(dados: dict) -> str:
    """Renderiza o template HTML com os dados do certificado."""
    html = TEMPLATE_CERTIFICADO_PADRAO()
    for chave, valor in dados.items():
        html = html.replace("{{" + chave + "}}", str(valor if valor is not None else "-"))
    return html

def TEMPLATE_PAGINA_VALIDACAO() -> str:
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Validacao de Certificado</title>
<style>
  body { font-family: Arial, sans-serif; background: #f5f7fa; margin: 0; padding: 40px; display: flex; justify-content: center; }
  .card { background: #fff; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,.1); max-width: 640px; width: 100%; padding: 40px; text-align: center; }
  .selo { font-size: 64px; }
  .status { font-size: 24px; font-weight: bold; color: #1a7f37; margin: 10px 0; }
  .status.invalido { color: #cf222e; }
  .dados { margin: 24px 0; color: #333; }
  .dados p { margin: 6px 0; font-size: 16px; }
  .dados strong { color: #1a3d6d; }
  .qrcode { margin: 20px auto; }
  .codigo { font-size: 13px; color: #888; word-break: break-all; margin-top: 16px; }
  .rodape { margin-top: 24px; font-size: 12px; color: #aaa; }
</style>
</head>
<body>
<div class="card">
  <div class="selo">{{SELO}}</div>
  <div class="status {{CLASSE}}">{{STATUS}}</div>
  <div class="dados">
    <p><strong>{{NOME}}</strong></p>
    <p>CPF: {{CPF}} · {{PREFEITURA}}</p>
    <p>Curso: {{CURSO}}</p>
    <p>Carga horaria: {{CARGA_HORARIA}} horas · Nota: {{NOTA}}</p>
    <p>Emitido em {{DATA}}</p>
  </div>
  <div class="qrcode">{{QR_CODE_HTML}}</div>
  <div class="codigo">Codigo de validacao: {{CODIGO}}</div>
  <div class="rodape">Plataforma de Capacitacao e Treinamento</div>
</div>
</body>
</html>"""


def render_pagina_validacao(dados: dict) -> str:
    """Renderiza a pagina publica de validacao do certificado (T-15.5)."""
    html = TEMPLATE_PAGINA_VALIDACAO()
    for chave, valor in dados.items():
        html = html.replace("{{" + chave + "}}", str(valor if valor is not None else "-"))
    return html
