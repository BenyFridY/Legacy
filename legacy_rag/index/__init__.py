"""Etapas 2-3 — Indexação do TEXTO (preparar para a busca).

Módulos planejados:
- chunking.py → corta releases/transcrições em chunks (por seção / por fala; tabela = 1 chunk).
- embed.py    → BGE-M3 transforma cada chunk em vetor (1024 dims).
- build.py    → monta o índice no DuckDB: vetores + FTS/BM25 + metadados (banco, período, fonte).

O metadado de origem viaja junto com o chunk — é o que permite citar a fonte depois (Aulas 1-2).
"""
