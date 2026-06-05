"""Busca vetorial — dado o vetor de uma pergunta, acha as fichas mais próximas em SIGNIFICADO.

Busca EXATA (brute-force): compara a pergunta com todos os vetores e ordena por similaridade
de cosseno. Recall 100%, e a ~40k fichas leva ~8 ms em CPU — simples e defensável; o HNSW só
valeria acima de ~100k fichas (ver ADR de escala). O cosseno mede o ÂNGULO entre vetores:
quanto mais alinhados (mesmo sentido), mais perto de 1.

PRÉ-FILTRO por metadados (banco/período/tipo) ANTES de ranquear: as perguntas B1/B2 do case
comparam períodos/bancos específicos, então filtrar primeiro (no SQL) evita misturar fichas
de docs irrelevantes e melhora a precisão.
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np


@dataclass
class Resultado:
    """Uma ficha recuperada + sua nota. Carrega tudo o que a CITAÇÃO precisa."""
    chunk_id: int
    banco: str
    periodo: str
    tipo_doc: str
    pagina: int
    ordinal: int
    texto: str
    score: float

    @property
    def citacao(self) -> str:
        return f"{self.banco}, {self.periodo}, {self.tipo_doc}, pág. {self.pagina}"


def _cosseno(q: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Similaridade de cosseno entre o vetor q [d] e cada linha da matriz M [n, d]."""
    q = np.asarray(q, dtype=np.float32)
    qn = q / (np.linalg.norm(q) + 1e-9)
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    return Mn @ qn


def buscar_vetorial(con: duckdb.DuckDBPyConnection, query_vec, k: int = 5,
                    banco: str | None = None, periodo: str | None = None,
                    tipo_doc: str | None = None) -> list[Resultado]:
    """Top-k fichas mais próximas do vetor da pergunta, com pré-filtro opcional por metadados."""
    cond, params = [], []
    for col, val in (("banco", banco), ("periodo", periodo), ("tipo_doc", tipo_doc)):
        if val is not None:
            cond.append(f"{col} = ?")
            params.append(val)
    sql = "SELECT chunk_id, banco, periodo, tipo_doc, pagina, ordinal, texto, embedding FROM chunks"
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    rows = con.execute(sql, params).fetchall()
    if not rows:
        return []
    embs = np.array([r[7] for r in rows], dtype=np.float32)
    sims = _cosseno(query_vec, embs)
    ordem = np.argsort(-sims)[:k]                       # maiores similaridades primeiro
    return [Resultado(*rows[i][:7], score=float(sims[i])) for i in ordem]
