"""Testes do reranker (sem torch): reordena o top-k por relevância, via reranker FALSO injetado."""

from legacy_rag.retrieval.rerank import rerankar
from legacy_rag.retrieval.vetorial import Resultado


class FakeReranker:
    """Nota = quantas vezes os termos da pergunta aparecem no texto (determinístico, sem modelo)."""

    def pontuar(self, query, textos):
        termos = set(query.lower().split())
        return [float(sum(t.lower().count(w) for w in termos)) for t in textos]


def _res(cid, texto):
    return Resultado(cid, "BB", "3T24", "release", 1, 0, texto, score=0.0)


def test_reordena_por_relevancia():
    res = [_res(1, "alpha beta"), _res(2, "consignado consignado aqui"), _res(3, "gamma")]
    out = rerankar("consignado", res, FakeReranker())
    assert out[0].chunk_id == 2                  # o mais relevante sobe ao topo


def test_score_vira_o_do_reranker():
    res = [_res(2, "consignado consignado aqui")]
    out = rerankar("consignado", res, FakeReranker())
    assert out[0].score == 2.0                   # 'consignado' aparece 2x


def test_top_k_limita():
    res = [_res(1, "alpha"), _res(2, "consignado consignado"), _res(3, "gamma")]
    out = rerankar("consignado", res, FakeReranker(), top_k=1)
    assert len(out) == 1 and out[0].chunk_id == 2


def test_lista_vazia():
    assert rerankar("consignado", [], FakeReranker()) == []
