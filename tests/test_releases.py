"""Testes da extração de PDF (sem rede): bytes de PDF -> texto por página.

`baixar()` toca a internet, então NÃO é testado aqui (seria frágil/offline-dependente);
provamos `baixar` ao vivo na demo. Aqui isolamos a parte PURA — `extrair_paginas` /
`extrair_texto` — alimentando um PDF mínimo montado na mão (offsets de xref calculados
em Python, então é um PDF de verdade, válido, que o pypdf lê de fato).
"""

import pytest
import requests

from legacy_rag.ingestion import releases
from legacy_rag.ingestion.releases import extrair_paginas, extrair_texto


class _Resp:
    """Resposta HTTP falsa (status + bytes), com raise_for_status como o requests."""

    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)


def test_baixar_repete_em_falha_transitoria(monkeypatch):
    """ConnectionError na 1ª, sucesso na 2ª -> retorna os bytes (provou o retry)."""
    chamadas = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise requests.exceptions.ConnectionError("conexao caiu")
        return _Resp(b"%PDF-1.4 ok", 200)

    monkeypatch.setattr(releases.requests, "get", fake_get)
    monkeypatch.setattr(releases.time, "sleep", lambda _s: None)   # não espera de verdade
    assert releases.baixar("http://x/doc.pdf") == b"%PDF-1.4 ok"
    assert chamadas["n"] == 2


def test_baixar_nao_repete_em_4xx(monkeypatch):
    """403/404 é PERMANENTE: levanta na hora, sem gastar tentativas (não adianta repetir)."""
    chamadas = {"n": 0}

    def fake_get(url, headers=None, timeout=None):
        chamadas["n"] += 1
        return _Resp(b"", 404)

    monkeypatch.setattr(releases.requests, "get", fake_get)
    monkeypatch.setattr(releases.time, "sleep", lambda _s: None)
    with pytest.raises(requests.exceptions.HTTPError):
        releases.baixar("http://x/nao-existe.pdf", tentativas=3)
    assert chamadas["n"] == 1                                      # não repetiu no 4xx


def _pdf(paginas: list[str]) -> bytes:
    """Monta um PDF válido de N páginas, uma linha de texto por página (para teste)."""
    n = len(paginas)
    objs = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (b"<< /Type /Pages /Kids ["
            + b" ".join(("%d 0 R" % (4 + i)).encode() for i in range(n))
            + b"] /Count " + str(n).encode() + b" >>"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, texto in enumerate(paginas):
        page_obj, cont_obj = 4 + i, 4 + n + i
        objs[page_obj] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents "
                          + ("%d 0 R" % cont_obj).encode()
                          + b" /Resources << /Font << /F1 3 0 R >> >> >>")
        fluxo = b"BT /F1 24 Tf 72 720 Td (" + texto.encode("latin-1") + b") Tj ET"
        objs[cont_obj] = b"<< /Length " + str(len(fluxo)).encode() + b" >>\nstream\n" + fluxo + b"\nendstream"

    total = 3 + 2 * n
    out = b"%PDF-1.4\n"
    offsets = {}
    for num in range(1, total + 1):
        offsets[num] = len(out)
        out += str(num).encode() + b" 0 obj\n" + objs[num] + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(total + 1).encode() + b"\n0000000000 65535 f \n"
    for num in range(1, total + 1):
        out += ("%010d 00000 n \n" % offsets[num]).encode()
    out += (b"trailer\n<< /Size " + str(total + 1).encode() + b" /Root 1 0 R >>\n"
            + b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF")
    return out


def test_extrai_o_texto_de_uma_pagina():
    pdf = _pdf(["Consignado cresceu para 14 por cento"])
    assert extrair_paginas(pdf) == ["Consignado cresceu para 14 por cento"]


def test_preserva_ordem_e_numero_de_paginas():
    # A página é a âncora da citação: ordem e contagem precisam ser fiéis.
    paginas = extrair_paginas(_pdf(["pagina um", "pagina dois", "pagina tres"]))
    assert len(paginas) == 3
    assert paginas[0] == "pagina um"
    assert paginas[2] == "pagina tres"


def test_extrair_texto_junta_as_paginas():
    assert extrair_texto(_pdf(["alpha", "beta"])) == "alpha\n\nbeta"
