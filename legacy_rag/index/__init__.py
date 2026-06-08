"""Etapas 2-3 — Indexação do TEXTO (preparar para a busca).

Módulos:
- chunking.py    → corta releases/transcrições em chunks (página = âncora de citação; ~1200 chars).
- embed.py       → BGE-M3 transforma cada chunk em vetor (1024 dims), atrás de uma interface trocável.
- store_texto.py → tabela `chunks` no DuckDB: vetor FLOAT[] + metadados (banco, período, tipo, página).

(O BM25 é calculado em MEMÓRIA em retrieval/lexical.py; o índice aqui guarda vetores + metadados.)
O metadado de origem viaja junto com o chunk — é o que permite citar a fonte depois (Aulas 1-2).
"""
