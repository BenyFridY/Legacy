"""Eval de FIDELIDADE com modelos REAIS (BGE-M3 + reranker + Groq como juiz).

Roda o pipeline de TEXTO (doc_unico) em perguntas respondíveis do Itaú 4T25, captura a RESPOSTA
e o CONTEXTO que a embasou, e pede a um LLM-juiz (Groq, temperatura 0) para auditar se a resposta
é inteiramente sustentada por esse contexto. Saída: taxa de fidelidade + alegações sem suporte.

HONESTIDADE: (1) juiz e gerador são o MESMO modelo (Groq/Llama 3.3 70B) -> há risco de viés de
auto-avaliação; por isso reportamos as alegações sem suporte para auditoria humana, não só a taxa.
(2) Corpus = só Itaú 4T25 hoje. (3) Reusamos `_buscar_texto` do pipeline de propósito: o eval
mede EXATAMENTE a recuperação que a produção usa (mesma busca híbrida + rerank).

Rodar:
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 & python scripts/eval_fidelidade_real.py
"""
from legacy_rag.torch_env import preparar_torch  # importa torch ANTES de numpy/duckdb (Windows/conda)

preparar_torch()

import sys

sys.stdout.reconfigure(encoding="utf-8")  # evita o mojibake cp1252 do console do Windows

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.env import carregar_dotenv
from legacy_rag.eval.faithfulness import (
    CasoFidelidade,
    LLMJuizFidelidade,
    avaliar_fidelidade,
    formatar_relatorio,
)
from legacy_rag.generation.answer import responder_de_contexto
from legacy_rag.generation.llm import criar_llm
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.pipeline import Dependencias, _buscar_texto  # _buscar_texto: MESMA busca da producao
from legacy_rag.retrieval.rerank import BGEReranker
from legacy_rag.router.router import rotear
from legacy_rag.structured.store import conectar

PERGUNTAS = [
    ("itau-lucro", "Qual foi o lucro líquido recorrente do Itaú no 4T25?"),
    ("itau-consignado", "Qual o saldo da carteira de crédito consignado do Itaú no 4T25?"),
    ("itau-inadimplencia", "Qual foi o índice de inadimplência acima de 90 dias do Itaú no 4T25?"),
    ("itau-margem", "Como evoluiu a margem financeira com clientes do Itaú no 4T25?"),
    ("itau-guidance", "Qual a faixa de guidance de custo de crédito do Itaú para 2026?"),
]


def main():
    carregar_dotenv()  # LLM_PROVIDER=groq_free + GROQ_API_KEY
    con = conectar(DUCKDB_PATH)
    deps = Dependencias(con=con, encoder=BGEM3Encoder(), reranker=BGEReranker(), llm=criar_llm())
    juiz = LLMJuizFidelidade(criar_llm())

    print(">>> Eval de fidelidade (BGE-M3 + reranker + Groq juiz)...")
    casos = []
    for id_, pergunta in PERGUNTAS:
        rota = rotear(pergunta)
        resultados = _buscar_texto(pergunta, rota, deps)
        resp = responder_de_contexto(pergunta, resultados, deps.llm, deps.limiar)
        if resp.recusou:
            print(f"  [pulado: recusou] {id_}: {resp.motivo}")
            continue
        # contexto = os MESMOS trechos citados que embasaram a resposta (cada um com sua citação)
        contexto = "\n\n".join(f"[{r.citacao}] {r.texto}" for r in resultados)
        casos.append(CasoFidelidade(id_, pergunta, resp.texto, contexto))
        print(f"  [respondeu] {id_}: {resp.texto[:60]!r}")

    print()
    print(formatar_relatorio(avaliar_fidelidade(casos, juiz)))


if __name__ == "__main__":
    main()
