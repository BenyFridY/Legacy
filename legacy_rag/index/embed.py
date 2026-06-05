"""Embeddings — transforma cada ficha (texto) num VETOR de números (caminho do texto).

O que é um embedding? Uma lista de ~1024 números que captura o SIGNIFICADO do texto.
Textos com sentido parecido ficam com vetores PRÓXIMOS no espaço — então dá para buscar
por SENTIDO ("custo de crédito" aproxima de "PDD", "provisões"), não só por palavra exata
(isso o BM25/Ctrl+F já faz). Modelo: BAAI/bge-m3 (multilíngue, ótimo p/ PT; ADR-0003).

O modelo é PESADO (~2 GB, precisa de torch), então fica atrás de uma INTERFACE trocável
(Encoder), igual ao LLMClient do ADR-0003. Assim desenvolvemos e TESTAMOS todo o pipeline
(busca, eval) com um encoder leve/falso, e só plugamos o BGE-M3 real para gerar os números
finais. O import de torch/FlagEmbedding é PREGUIÇOSO (só ao instanciar o encoder real) —
por isso este módulo importa sem torch instalado.
"""
from __future__ import annotations

from typing import Protocol, Sequence

import numpy as np

from legacy_rag.config import EMBED_MODEL
from legacy_rag.index.chunking import Chunk


class Encoder(Protocol):
    """Contrato mínimo: virar uma lista de textos numa matriz de vetores (1 linha = 1 texto)."""

    dim: int

    def encode(self, textos: Sequence[str]) -> np.ndarray: ...


class BGEM3Encoder:
    """Encoder de produção: BAAI/bge-m3 (1024 dims, multilíngue).

    Carrega torch/FlagEmbedding PREGUIÇOSAMENTE, na primeira chamada — o modelo (~2 GB) é
    baixado e cacheado pelo HuggingFace nesse momento. use_fp16=False em CPU (fp16 é p/ GPU).
    """

    dim = 1024

    def __init__(self, modelo: str = EMBED_MODEL, use_fp16: bool = False):
        self._modelo_nome = modelo
        self._use_fp16 = use_fp16
        self._modelo = None

    def _carregar(self):
        if self._modelo is None:
            from legacy_rag.torch_env import permitir_omp_duplicado
            permitir_omp_duplicado()                     # antes de torch (conflito OpenMP/conda)
            from FlagEmbedding import BGEM3FlagModel      # import preguiçoso (puxa torch)

            self._modelo = BGEM3FlagModel(self._modelo_nome, use_fp16=self._use_fp16)
        return self._modelo

    def encode(self, textos: Sequence[str]) -> np.ndarray:
        saida = self._carregar().encode(list(textos), batch_size=32)["dense_vecs"]
        return np.asarray(saida, dtype=np.float32)


def embedar_chunks(chunks: Sequence[Chunk], encoder: Encoder, batch: int = 32) -> np.ndarray:
    """Embeda a forma .indexavel de cada ficha. Retorna matriz [n_chunks, dim].

    Embeda o .indexavel (cabeçalho de metadados + trecho), NÃO o texto cru — assim o contexto
    banco/período entra no vetor. Processa em LOTES para não estourar memória/CPU.
    """
    if not chunks:
        return np.zeros((0, encoder.dim), dtype=np.float32)
    vetores = [encoder.encode([c.indexavel for c in chunks[i:i + batch]])
               for i in range(0, len(chunks), batch)]
    return np.vstack(vetores)
