"""Reranker — a "entrevista cara" que afina o top-k da busca híbrida.

A busca híbrida (vetorial + BM25 + RRF) é a triagem barata: separa ~50 candidatos olhando
pergunta e trecho SEPARADOS. O reranker é um cross-encoder (bge-reranker-v2-m3) que lê
pergunta + trecho JUNTOS e dá uma nota de relevância muito mais precisa. Custa caro por par,
então só roda nos poucos candidatos do topo (top_k) — não no corpus inteiro.

Como o embedding, o modelo é pesado (precisa de torch) e fica atrás de uma INTERFACE
trocável (Reranker), com import preguiçoso — o pipeline é testável com um reranker falso.
"""
from __future__ import annotations

from typing import Protocol, Sequence

from legacy_rag.config import RERANK_MODEL
from legacy_rag.retrieval.vetorial import Resultado


class Reranker(Protocol):
    """Contrato: dada a pergunta e uma lista de textos, devolve uma nota de relevância por texto."""

    def pontuar(self, query: str, textos: Sequence[str]) -> list[float]: ...


class BGEReranker:
    """Reranker de produção: BAAI/bge-reranker-v2-m3 (cross-encoder). Carrega torch/FlagEmbedding
    preguiçosamente; normalize=True devolve nota 0–1 (sigmoid)."""

    def __init__(self, modelo: str = RERANK_MODEL, use_fp16: bool = False):
        self._nome = modelo
        self._fp16 = use_fp16
        self._modelo = None

    def _carregar(self):
        if self._modelo is None:
            from legacy_rag.torch_env import permitir_omp_duplicado
            permitir_omp_duplicado()                # antes de torch (conflito OpenMP/conda)
            from FlagEmbedding import FlagReranker   # import preguiçoso (puxa torch)

            self._modelo = FlagReranker(self._nome, use_fp16=self._fp16)
        return self._modelo

    def pontuar(self, query: str, textos: Sequence[str]) -> list[float]:
        if not textos:
            return []
        notas = self._carregar().compute_score([[query, t] for t in textos], normalize=True)
        return [float(s) for s in (notas if isinstance(notas, list) else [notas])]


def rerankar(query: str, resultados: list[Resultado], reranker: Reranker,
             top_k: int | None = None) -> list[Resultado]:
    """Reordena os resultados pela nota do reranker (cross-encoder) e devolve o top_k."""
    if not resultados:
        return []
    notas = reranker.pontuar(query, [r.texto for r in resultados])
    reordenados = sorted(
        (Resultado(r.chunk_id, r.banco, r.periodo, r.tipo_doc, r.pagina, r.ordinal, r.texto, score=float(s))
         for r, s in zip(resultados, notas)),
        key=lambda r: r.score, reverse=True)
    return reordenados[:top_k] if top_k is not None else reordenados
