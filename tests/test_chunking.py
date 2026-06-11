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


# ---------------------------------------------------------------------------
# Decisão 4 — chunking ciente de tabela (re-prefixo do cabeçalho de colunas).
# Formato calcado no que o pypdf extrai dos releases reais (ver docstring).
# ---------------------------------------------------------------------------

CABECALHO = "R$ milhões 4T25 3T25 4T24"
LINHAS = [f"Produto {i} 1.{i:03d} 2.{i:03d} 3.{i:03d} {i},5 {i},9" for i in range(30)]
PAG_TABELA_DENSA = "\n".join([CABECALHO] + LINHAS)            # ~1.300 chars -> quebra em 2+


def test_tabela_quebrada_reprefixar_cabecalho_na_continuacao():
    chunks = chunkar_documento([PAG_TABELA_DENSA], banco="Bradesco", periodo="4T25",
                               tipo_doc="release", alvo=600, overlap=80)
    assert len(chunks) >= 2                                   # a tabela de fato estourou o alvo
    for c in chunks:                                          # NENHUMA ficha fica órfã de cabeçalho
        assert CABECALHO in c.texto
    for c in chunks[1:]:                                      # nas continuações, ele vem RE-PREFIXADO
        assert c.texto.startswith(CABECALHO)


def test_cabecalho_depois_dos_dados_tambem_serve():
    """Caso real (Bradesco 3T25 pág.41): o pypdf emite o cabeçalho DEPOIS das linhas — o
    re-prefixo busca o mais PRÓXIMO da página, não 'o último visto antes da quebra'."""
    pag = "\n".join(LINHAS + ["Set25 Jun25 Set24"])           # cabeçalho no FIM da página
    chunks = chunkar_documento([pag], banco="Bradesco", periodo="3T25",
                               tipo_doc="release", alvo=600, overlap=80)
    assert len(chunks) >= 2
    for c in chunks:
        assert "Set25 Jun25 Set24" in c.texto


def test_prosa_nao_ganha_prefixo_de_tabela():
    """Prosa com anos e percentuais NÃO dispara o re-prefixo (frase termina em ponto)."""
    pag = ("O lucro cresceu 12,5% em 2025, ante 10,1% em 2024. " * 12).strip()
    chunks = chunkar_documento([pag], banco="Itau", periodo="4T25",
                               tipo_doc="release", alvo=200, overlap=50)
    assert len(chunks) >= 2
    for c in chunks:                                          # toda ficha segue começando em prosa
        assert c.texto.startswith("O lucro cresceu")


def test_tabela_que_cabe_numa_ficha_fica_intocada():
    pag = "\n".join([CABECALHO] + LINHAS[:3])                 # pequena: cabe numa ficha só
    chunks = chunkar_documento([pag], banco="BB", periodo="4T25", tipo_doc="release")
    assert len(chunks) == 1
    assert chunks[0].texto.count(CABECALHO) == 1              # sem duplicar o cabeçalho


def test_pagina_de_grafico_sem_cabecalho_detectavel_e_noop():
    """Página só com sopa de rótulos de gráfico (sem cabeçalho de colunas): nada é prefixado."""
    soup = "DezSetJunMar25Dez24\n" + "\n".join(f"{i},{i} 1.{i:03d} 2.{i:03d}" for i in range(40))
    chunks = chunkar_documento([soup], banco="Bradesco", periodo="4T25",
                               tipo_doc="release", alvo=300, overlap=50)
    assert len(chunks) >= 2
    textos = [c.texto for c in chunks]
    juntado = " ".join(t for t in textos)
    assert juntado.startswith("DezSetJunMar25Dez24")          # ordem original preservada, sem prefixo
