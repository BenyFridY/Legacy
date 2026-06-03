"""legacy_rag — sistema de retrieval dual-path para research de equities.

Arquitetura (ADR-0001): caminho de texto (busca híbrida BM25+densa+rerank) +
caminho estruturado (DuckDB/SQL com cálculo em código) + roteador determinístico,
com citação e recusa por construção.
"""

__version__ = "0.1.0"
