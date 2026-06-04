"""Caminho do TEXTO — busca (Aulas 2-3).

Módulos planejados:
- hybrid.py → BM25 (palavra exata) + vetorial/BGE-M3 (significado), fundidos por RRF
              (Reciprocal Rank Fusion — combina por posição, não por nota bruta).
- rerank.py → bge-reranker-v2-m3 reordena os ~20 candidatos para o top-5 (a "entrevista final").

Devolve trechos JÁ com os metadados de origem, prontos para citação.
"""
