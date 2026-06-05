"""Busca lexical (BM25) — acha por PALAVRA exata, não por sentido.

Complementa a busca vetorial: o vetor erra termos/códigos/números literais ("4,5%",
"4.966/21", "consignado CLT"); o BM25 acerta justamente isso. O BM25 é um "Ctrl+F com nota":
pontua um documento pela frequência dos termos da pergunta nele, dando mais peso a termos
RAROS no corpus. Na fusão (RRF) os dois sinais se somam.

Usamos rank-bm25 (Okapi BM25) em memória — simples e exato para o nosso tamanho; a alternativa
seria o FTS do DuckDB com stemmer PT (ver ADR de escala). Mesmo pré-filtro por metadados da
busca vetorial, e devolvemos o mesmo Resultado (com .citacao) para a fusão combinar fácil.
"""
from __future__ import annotations

import re
import unicodedata

import duckdb
import numpy as np
from rank_bm25 import BM25Okapi

from legacy_rag.retrieval.vetorial import Resultado


def tokenizar(texto: str) -> list[str]:
    """Normaliza para casar palavras em PT: minúsculas, sem acento, só tokens alfanuméricos."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                         if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", sem_acento)


def buscar_bm25(con: duckdb.DuckDBPyConnection, query: str, k: int = 5,
                banco: str | None = None, periodo: str | None = None,
                tipo_doc: str | None = None) -> list[Resultado]:
    """Top-k fichas por BM25 sobre o texto, com pré-filtro opcional por metadados."""
    cond, params = [], []
    for col, val in (("banco", banco), ("periodo", periodo), ("tipo_doc", tipo_doc)):
        if val is not None:
            cond.append(f"{col} = ?")
            params.append(val)
    sql = "SELECT chunk_id, banco, periodo, tipo_doc, pagina, ordinal, texto FROM chunks"
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    rows = con.execute(sql, params).fetchall()
    if not rows:
        return []
    bm25 = BM25Okapi([tokenizar(r[6]) for r in rows])
    scores = bm25.get_scores(tokenizar(query))
    ordem = np.argsort(-scores)[:k]
    return [Resultado(*rows[i], score=float(scores[i])) for i in ordem]
