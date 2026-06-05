"""Testa a logica de avaliacao de retrieval (legacy_rag/eval/retrieval.py) SEM torch/rede.

A busca entra por injecao (busca_fn FAKE, deterministico): provamos resolucao pagina->chunk_id,
hit@k em posicoes conhecidas e MRR agregado. A qualidade semantica real e do runner com modelos.
"""
import pytest

from legacy_rag.eval.retrieval import (
    Sondagem,
    avaliar_retrieval,
    carregar_sondagens,
    formatar_relatorio,
    resolver_gold_chunk_ids,
)
from legacy_rag.index.store_texto import garantir_schema
from legacy_rag.structured.store import conectar


@pytest.fixture
def con():
    c = conectar(":memory:")
    garantir_schema(c)
    # Itau 4T25: paginas 7 (2 chunks), 8 (1), 14 (1), 99 (1 = distrator irrelevante).
    linhas = [
        ("Itau", "4T25", "release", 7, 0, "consignado tabela", [0.0]),
        ("Itau", "4T25", "release", 7, 1, "consignado destaque", [0.0]),
        ("Itau", "4T25", "release", 8, 0, "sumario executivo lucro", [0.0]),
        ("Itau", "4T25", "release", 14, 0, "qualidade do credito npl", [0.0]),
        ("Itau", "4T25", "release", 99, 0, "glossario irrelevante", [0.0]),
    ]
    c.executemany("INSERT INTO chunks (banco,periodo,tipo_doc,pagina,ordinal,texto,embedding) "
                  "VALUES (?,?,?,?,?,?,?)", linhas)
    return c


def _ids_da_pagina(con, pagina):
    return [r[0] for r in con.execute(
        "SELECT chunk_id FROM chunks WHERE pagina=? ORDER BY ordinal", [pagina]).fetchall()]


def test_resolver_gold_paginas_para_chunk_ids(con):
    s = Sondagem("x", "Itau", "4T25", "release", "q", gold_paginas=[7, 8])
    esperado = set(_ids_da_pagina(con, 7)) | set(_ids_da_pagina(con, 8))
    assert resolver_gold_chunk_ids(con, s) == esperado
    assert len(esperado) == 3                       # 2 chunks da pag.7 + 1 da pag.8


def test_hit_e_rr_quando_gold_esta_no_topo(con):
    s = Sondagem("acerto", "Itau", "4T25", "release", "q", gold_paginas=[7])
    ids7 = _ids_da_pagina(con, 7)
    busca = lambda _s: [ids7[0], 999, 998]          # chunk-gold em 1o lugar
    res = avaliar_retrieval(con, [s], busca, ks=(1, 3, 5))
    r = res.por_sondagem[0]
    assert r.hits[1] and r.hits[3] and r.hits[5]
    assert r.rr == 1.0
    assert res.mrr == 1.0 and res.hit_rate(1) == 1.0


def test_hit_so_no_top5_e_rr_fracionario(con):
    s = Sondagem("tarde", "Itau", "4T25", "release", "q", gold_paginas=[14])
    id14 = _ids_da_pagina(con, 14)[0]
    busca = lambda _s: [999, 998, 997, id14, 996]   # gold so na 4a posicao
    res = avaliar_retrieval(con, [s], busca, ks=(1, 3, 5))
    r = res.por_sondagem[0]
    assert not r.hits[1] and not r.hits[3] and r.hits[5]
    assert r.rr == pytest.approx(0.25)              # 1/4


def test_miss_total_quando_gold_ausente(con):
    s = Sondagem("erro", "Itau", "4T25", "release", "q", gold_paginas=[8])
    busca = lambda _s: [999, 998, 997]              # nenhum chunk-gold
    res = avaliar_retrieval(con, [s], busca, ks=(1, 3, 5))
    r = res.por_sondagem[0]
    assert not any(r.hits.values()) and r.rr == 0.0


def test_agregacao_hit_rate_mistura(con):
    s1 = Sondagem("a", "Itau", "4T25", "release", "q", gold_paginas=[7])
    s2 = Sondagem("b", "Itau", "4T25", "release", "q", gold_paginas=[8])
    ids7, id8 = _ids_da_pagina(con, 7), _ids_da_pagina(con, 8)[0]
    def busca(s):
        return [ids7[0]] if s.id == "a" else [999, 998, 997]   # a acerta@1, b erra
    res = avaliar_retrieval(con, [s1, s2], busca, ks=(1, 3, 5))
    assert res.hit_rate(1) == 0.5                   # 1 de 2
    assert res.mrr == pytest.approx(0.5)            # (1.0 + 0.0)/2
    assert "EVAL DE RETRIEVAL" in formatar_relatorio(res)


def test_carregar_gold_do_yaml_real():
    sondagens = carregar_sondagens()
    assert len(sondagens) >= 6
    ids = {s.id for s in sondagens}
    assert "itau-consignado-saldo" in ids
    s = next(s for s in sondagens if s.id == "itau-consignado-saldo")
    assert s.gold_paginas == [7, 21] and s.banco == "Itau"
