"""Caminho do TEXTO — busca (Aulas 2-3).

Módulos:
- vetorial.py → busca densa por SIGNIFICADO (BGE-M3, cosseno brute-force + pré-filtro de metadados).
- lexical.py  → BM25 por PALAVRA exata (rank-bm25 / Okapi, em MEMÓRIA — não é o FTS do DuckDB).
- hibrido.py  → funde vetorial + BM25 por RRF (Reciprocal Rank Fusion: combina por posição, não nota).
- rerank.py   → bge-reranker-v2-m3 reordena o topo; com FALLBACK p/ a ordem do RRF quando ele "empata".

Devolve trechos JÁ com os metadados de origem, prontos para citação.
"""
