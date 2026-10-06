import html
from html.parser import HTMLParser

TAGS_PERMITIDAS = {"p", "br", "strong", "em", "u", "ul", "ol", "li", "h2", "h3", "a"}
MAX_TEXTO = 100_000


class _LimpaHTML(HTMLParser):
    """Reconstroi o HTML mantendo apenas as tags/atributos permitidos (issue #91).

    O texto e renderizado para outros usuarios, entao a barreira nao pode
    ficar so no editor do frontend.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.abertas: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in TAGS_PERMITIDAS:
            return
        if tag == "a":
            href = next((v for k, v in attrs if k == "href"), None)
            if not (href and href.strip().lower().startswith(("http://", "https://"))):
                return
            self.out.append(f'<a href="{html.escape(href, quote=True)}">')
            self.abertas.append("a")
            return
        if tag == "br":
            self.out.append("<br>")
            return
        self.out.append(f"<{tag}>")
        self.abertas.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.out.append("<br>")

    def handle_endtag(self, tag):
        if tag in ("br",):
            return
        if tag in self.abertas:
            while self.abertas:
                t = self.abertas.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        self.out.append(html.escape(data))


def sanitizar_html(texto: str | None) -> str | None:
    """Remove tags/atributos potencialmente perigosos de um texto HTML."""
    if texto is None:
        return None
    if len(texto) > MAX_TEXTO:
        raise ValueError(f"conteudo_texto excede o limite de {MAX_TEXTO} caracteres")
    parser = _LimpaHTML()
    parser.feed(texto)
    parser.close()
    while parser.abertas:
        parser.out.append(f"</{parser.abertas.pop()}>")
    return "".join(parser.out)
