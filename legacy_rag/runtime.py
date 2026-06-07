"""Fábrica única das dependências REAIS do pipeline (modelos + DuckDB + LLM).

Centraliza o boilerplate que estava repetido nos scripts (resolver_caso, resolver_b3): preparar
o torch ANTES de numpy/duckdb (conflito OpenMP/DLL no Windows), carregar o .env, instanciar
encoder/reranker/LLM e abrir a conexão. O CLI (`scripts/perguntar.py`) e a UI de demo
(`scripts/ui_demo.py`) montam o sistema por AQUI — uma fonte única da verdade.

IMPORTANTE: este módulo chama `preparar_torch()` no topo, então importá-lo já deixa o torch
pronto antes do numpy. Importe-o como uma das PRIMEIRAS coisas do entrypoint.
"""
from __future__ import annotations

from legacy_rag.torch_env import preparar_torch

preparar_torch()  # torch ANTES de numpy/duckdb (conflito OpenMP/DLL no Windows). Idempotente.

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.env import carregar_dotenv
from legacy_rag.generation.llm import criar_llm
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.pipeline import Dependencias
from legacy_rag.retrieval.rerank import BGEReranker
from legacy_rag.structured.store import conectar


def construir_deps(*, com_llm: bool = True, db_path: str | None = None) -> Dependencias:
    """Monta as Dependencias reais: DuckDB + BGE-M3 + reranker + (opcional) o redator LLM.

    com_llm=False pula o redator (o sistema ainda roteia, recupera, computa números e recusa —
    só não redige texto livre); útil para inspecionar retrieval/recusa sem depender de chave.
    """
    carregar_dotenv()
    llm = criar_llm() if com_llm else None
    return Dependencias(
        con=conectar(db_path or str(DUCKDB_PATH)),
        encoder=BGEM3Encoder(),
        reranker=BGEReranker(),
        llm=llm,
    )
