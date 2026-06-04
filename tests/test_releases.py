"""Testes da extração de PDF (sem rede): bytes de PDF -> texto por página.

`baixar()` toca a internet, então NÃO é testado aqui (seria frágil/offline-dependente);
provamos `baixar` ao vivo na demo. Aqui isolamos a parte PURA — `extrair_paginas` /
`extrair_texto` — alimentando um PDF mínimo montado na mão (offsets de xref calculados
em Python, então é um PDF de verdade, válido, que o pypdf lê de fato).
"""

from legacy_rag.ingestion.releases import extrair_paginas, extrair_texto


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
