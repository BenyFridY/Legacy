"""Testes do chunking (sem rede): páginas de texto -> fichas com metadados de citação.

Invariantes que defendem as decisões de design (ver chunking.py):
- a ficha vive dentro de UMA página (âncora de citação);
- nunca corta no meio de uma frase;
- fichas vizinhas têm sobreposição (overlap);
- o texto que vai à busca (.indexavel) embute os metadados; o texto cru (citação) não.
"""

from legacy_rag.index.chunking import chunkar_documento

PAG_LONGA = ("O custo de credito ficou em 4,5 por cento. "
             "A carteira de consignado cresceu no trimestre. "
             "O guidance para 2025 e de 4 a 4,5 por cento. "
             "A inadimplencia recuou levemente.")


def test_pagina_curta_vira_uma_unica_ficha():
    chunks = chunkar_documento(["Uma frase curta e so."], banco="BB", periodo="3T24", tipo_doc="release")
    assert len(chunks) == 1
    c = chunks[0]
    assert (c.pagina, c.ordinal) == (1, 0)
    assert c.texto == "Uma frase curta e so."


def test_nao_cruza_fronteira_de_pagina():
    chunks = chunkar_documento(["Pagina dez aqui.", "Pagina vinte aqui."],
                               banco="BB", periodo="3T24", tipo_doc="release")
    assert {c.pagina for c in chunks} == {1, 2}
    p1 = " ".join(c.texto for c in chunks if c.pagina == 1)
    p2 = " ".join(c.texto for c in chunks if c.pagina == 2)
    assert "dez" in p1 and "vinte" not in p1
    assert "vinte" in p2 and "dez" not in p2


def test_quebra_em_varias_fichas_sem_cortar_frase():
    chunks = chunkar_documento([PAG_LONGA], banco="Itau", periodo="4T24", tipo_doc="release",
                               alvo=100, overlap=30)
    assert len(chunks) >= 2
    for c in chunks:                      # toda ficha termina em fim de frase -> não cortou no meio
        assert c.texto[-1] in ".!?"


def test_fichas_vizinhas_tem_overlap():
    chunks = chunkar_documento([PAG_LONGA], banco="Itau", periodo="4T24", tipo_doc="release",
                               alvo=100, overlap=30)
    f0 = {s.strip() for s in chunks[0].texto.split(".") if s.strip()}
    f1 = {s.strip() for s in chunks[1].texto.split(".") if s.strip()}
    assert f0 & f1                        # compartilham ao menos uma frase (a sobreposição)


def test_indexavel_embute_metadados_e_texto_cru_nao():
    c = chunkar_documento(["Texto qualquer."], banco="Bradesco", periodo="2T24", tipo_doc="transcript")[0]
    idx = c.indexavel
    assert "Bradesco" in idx and "2T24" in idx and "transcript" in idx and "pág.1" in idx
    assert "Texto qualquer." in idx
    assert c.texto == "Texto qualquer."   # a citação mostra o trecho cru, sem o cabeçalho


def test_pagina_vazia_nao_gera_ficha():
    chunks = chunkar_documento(["   \n  ", "Conteudo real aqui."],
                               banco="BB", periodo="3T24", tipo_doc="release")
    assert {c.pagina for c in chunks} == {2}   # a página 1 (vazia) não vira ficha
