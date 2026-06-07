"""Caso B3 AO VIVO — cruza o DECLARADO (texto do Bradesco) com o COMPUTADO (Bacen IF.data).

Esta é a assinatura do Caso B e o único caminho (multi_fonte) que antes só rodava com fakes.
Pré-requisitos: `python scripts/ingerir_bradesco.py` (texto) e `python scripts/ingerir_numeros.py`
(números) já rodados na base `data/legacy.duckdb`.

  DECLARADO: o RAEF 4T25 do Bradesco reporta share de consignado ~14% (tabela da p.41).
  COMPUTADO: market share por conglomerado prudencial do Bradesco no Bacen IF.data (~14,0% no 4T24).
  -> o pipeline recupera o texto, computa a série em SQL e o LLM reconcilia, citando OS DOIS lados.

Rodar:
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 & python scripts/resolver_b3.py
"""
from legacy_rag.torch_env import preparar_torch  # torch ANTES de numpy/duckdb (Windows/conda)

preparar_torch()

import sys

sys.stdout.reconfigure(encoding="utf-8")

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.env import carregar_dotenv
from legacy_rag.generation.llm import criar_llm
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.pipeline import Dependencias, responder
from legacy_rag.retrieval.rerank import BGEReranker
from legacy_rag.structured.store import conectar

PERGUNTA = ("O market share de crédito consignado do Bradesco (INSS, setor privado e público) que ele "
            "reporta no balanço bate com o que computamos a partir do Bacen IF.data?")


def main():
    carregar_dotenv()
    con = conectar(str(DUCKDB_PATH))
    deps = Dependencias(con=con, encoder=BGEM3Encoder(), reranker=BGEReranker(), llm=criar_llm())

    print(">>> Caso B3 ao vivo (multi_fonte: declarado x computado)")
    print("=" * 72)
    print(f"[multi_fonte]  {PERGUNTA}")
    print("-" * 72)
    print(responder(PERGUNTA, deps).formatado)
    print("=" * 72)


if __name__ == "__main__":
    main()
