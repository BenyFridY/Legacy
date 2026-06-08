"""Eval de FIDELIDADE com modelos REAIS (BGE-M3 + reranker + Groq como juiz).

Roda o pipeline de TEXTO (doc_unico) em perguntas respondíveis do Itaú 4T25, captura a RESPOSTA
e o CONTEXTO que a embasou, e pede a um LLM-juiz (Groq, temperatura 0) para auditar se a resposta
é inteiramente sustentada por esse contexto. Saída: taxa de fidelidade + alegações sem suporte.

HONESTIDADE: (1) o juiz é um modelo INDEPENDENTE do gerador (juiz = GROQ_JUIZ_MODELO, default
openai/gpt-oss-120b; gerador = Llama 3.3 70B) -> remove o viés de auto-avaliação; ainda assim
reportamos as alegações sem suporte para auditoria humana, não só a taxa. (2) n cobre vários bancos
(Itaú/Bradesco/BB/Santander). (3) Reusamos `_buscar_texto` do pipeline: o eval mede EXATAMENTE a
recuperação que a produção usa (mesma busca híbrida + rerank).

Rodar:
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 & python scripts/eval_fidelidade_real.py
"""
from legacy_rag.torch_env import preparar_torch  # importa torch ANTES de numpy/duckdb (Windows/conda)

preparar_torch()

import os
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
from legacy_rag.generation.llm import GROQ_MODELO_PADRAO, GroqClient, criar_llm
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.pipeline import Dependencias, _buscar_texto  # _buscar_texto: MESMA busca da producao
from legacy_rag.retrieval.rerank import BGEReranker
from legacy_rag.router.router import rotear
from legacy_rag.structured.store import conectar

# Perguntas respondiveis cobrindo VARIOS bancos (corpus heterogeneo). Frases alinhadas ao termo
# do proprio documento onde possivel (ex.: Itau usa "Resultado Recorrente Gerencial", nao "lucro
# liquido recorrente"). Casos que recusarem sao pulados e reportados (honesto).
PERGUNTAS = [
    ("itau-resultado", "Qual foi o Resultado Recorrente Gerencial do Itaú no 4T25?"),
    ("itau-consignado", "Qual o saldo da carteira de crédito consignado do Itaú no 4T25?"),
    ("itau-inadimplencia", "Qual foi o índice de inadimplência acima de 90 dias do Itaú no 4T25?"),
    ("itau-basileia", "Qual foi o índice de Basileia do Itaú no 4T25?"),
    ("itau-guidance", "Qual a faixa de guidance de custo de crédito do Itaú para 2026?"),
    ("bradesco-share", "Qual o market share de consignado que o Bradesco reporta no 4T25?"),
    ("bb-lucro", "Qual foi o lucro líquido ajustado do Banco do Brasil no 4T25?"),
    ("santander-lucro", "Qual foi o lucro líquido gerencial do Santander Brasil no 4T25?"),
]


def main():
    carregar_dotenv()  # LLM_PROVIDER=groq_free + GROQ_API_KEY
    con = conectar(DUCKDB_PATH)
    deps = Dependencias(con=con, encoder=BGEM3Encoder(), reranker=BGEReranker(), llm=criar_llm())
    # Juiz INDEPENDENTE: modelo de FAMILIA diferente do gerador (anti viés de auto-avaliação).
    juiz_modelo = os.getenv("GROQ_JUIZ_MODELO", "openai/gpt-oss-120b")
    juiz = LLMJuizFidelidade(GroqClient(modelo=juiz_modelo))

    print(f">>> Eval de fidelidade — gerador={GROQ_MODELO_PADRAO} | juiz INDEPENDENTE={juiz_modelo}")
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
