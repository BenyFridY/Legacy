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


class RerankerCego:
    """Reranker que NÃO discrimina: devolve notas quase iguais (simula o empate com gíria)."""

    def pontuar(self, query, textos):
        return [0.50 + 0.001 * i for i in range(len(textos))]   # variação << limiar (0.05)


def test_fallback_rrf_quando_reranker_nao_discrimina():
    """Reranker cego -> preserva a ORDEM DE ENTRADA (RRF), em vez de reordenar por ruído."""
    res = [_res(1, "trecho A"), _res(2, "trecho B"), _res(3, "trecho C")]   # entrada = ordem do RRF
    out = rerankar("qualquer", res, RerankerCego())
    assert [r.chunk_id for r in out] == [1, 2, 3]        # NÃO reordenou (manteve o RRF)
    assert out[0].score == 0.50                          # mas a nota do reranker continua anexada (p/ o gate)


def test_reranker_que_discrimina_reordena_mesmo_contra_rrf():
    """Quando o reranker discrimina (alta variância), a ordem dele vence a de entrada."""
    res = [_res(1, "alpha"), _res(2, "consignado consignado consignado"), _res(3, "beta")]
    out = rerankar("consignado", res, FakeReranker())    # notas [0, 3, 0] -> pstdev alto
    assert out[0].chunk_id == 2                           # reordenou: o relevante subiu
