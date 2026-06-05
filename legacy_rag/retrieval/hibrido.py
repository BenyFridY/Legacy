"""Busca híbrida = vetorial (sentido) + BM25 (termo exato), fundidos por RRF.

Por que RRF (Reciprocal Rank Fusion)? As duas buscas dão notas em escalas incomparáveis
(cosseno 0–1 vs BM25 solto). Normalizar é frágil. O RRF descarta a nota e usa só a POSIÇÃO:
cada lista dá a um item `1/(k + posição)` (k≈60). Quem aparece bem nas DUAS listas soma os
votos e sobe ao topo. Simples, robusto e sem tuning de escala (ADR-0001).

Fluxo: busca cada ramo top-N (≈50), funde por RRF, devolve top-k. O reranker (passo seguinte)
afina esse top-k. O pré-filtro por metadados é repassado aos dois ramos.
"""
from __future__ import annotations

import duckdb

from legacy_rag.retrieval.lexical import buscar_bm25
from legacy_rag.retrieval.vetorial import Resultado, buscar_vetorial


def fundir_rrf(listas: list[list[Resultado]], k: int = 60) -> list[Resultado]:
    """Funde várias listas ranqueadas por RRF. Cada item ganha Σ 1/(k + posição_1based) por lista."""
    acc: dict[int, list] = {}                       # chunk_id -> [score_rrf, Resultado representativo]
    for lista in listas:
        for posicao, r in enumerate(lista, start=1):
            slot = acc.setdefault(r.chunk_id, [0.0, r])
            slot[0] += 1.0 / (k + posicao)
    fundidos = [Resultado(rr.chunk_id, rr.banco, rr.periodo, rr.tipo_doc,
                          rr.pagina, rr.ordinal, rr.texto, score=score)
                for score, rr in acc.values()]
    fundidos.sort(key=lambda r: r.score, reverse=True)
    return fundidos


def buscar_hibrido(con: duckdb.DuckDBPyConnection, query: str, query_vec, k: int = 5,
                   n_ramo: int = 50, k_rrf: int = 60, banco: str | None = None,
                   periodo: str | None = None, tipo_doc: str | None = None) -> list[Resultado]:
    """Top-k fundindo busca vetorial + BM25 (cada ramo top-n_ramo), com pré-filtro por metadados."""
    filtros = dict(banco=banco, periodo=periodo, tipo_doc=tipo_doc)
    vet = buscar_vetorial(con, query_vec, k=n_ramo, **filtros)
    lex = buscar_bm25(con, query, k=n_ramo, **filtros)
    return fundir_rrf([vet, lex], k=k_rrf)[:k]
