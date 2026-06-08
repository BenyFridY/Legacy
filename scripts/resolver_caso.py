"""RESOLUCAO DO CASO B (ponta a ponta) — o sistema VIVO respondendo, com modelos reais.

Liga tudo: pergunta -> roteador -> (busca hibrida+rerank no texto | SQL nos numeros) -> gate
de evidencia -> redator real (Groq) com CITACAO estrutural, ou RECUSA explicada. Exercita as
QUATRO rotas (= as 3 categorias do enunciado + o cruzamento que e o coracao do Caso B):
  - documento unico  (texto do release do Itau)
  - computada        (market share via Bacen, SQL deterministico; generaliza p/ qualquer modalidade)
  - multi-fonte (B3) (declarado no texto x computado do Bacen, lado a lado)
  - nao-respondivel  (recusa por escopo, sem inventar)

Pre-requisitos: base ingerida (scripts/ingerir_numeros.py + scripts/prova_retrieval_real.py)
e GROQ_API_KEY no .env. Uso:
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 &
  python scripts/resolver_caso.py
"""
import sys

from legacy_rag.torch_env import preparar_torch
preparar_torch()                       # torch ANTES de numpy/duckdb (conflito OpenMP no Windows)

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.env import carregar_dotenv
from legacy_rag.generation.llm import criar_llm
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.pipeline import Dependencias, responder
from legacy_rag.retrieval.rerank import BGEReranker
from legacy_rag.structured.store import conectar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# (categoria do case, pergunta) — todas respondiveis/recusaveis com a base atual (Itau 4T25 + Bacen).
PERGUNTAS = [
    ("documento unico (texto)",
     # termo EXATO do documento ("Resultado Recorrente Gerencial" = lucro recorrente do Itau):
     # robusto, evita a borderline "lucro liquido recorrente" que oscila no LLM mesmo a temp 0.
     "Qual foi o Resultado Recorrente Gerencial do Itau no 4T25?"),
    ("documento unico (texto)",
     "Qual o saldo da carteira de credito consignado do Itau no 4T25?"),
    ("computada (numeros / Bacen)",
     "Como evoluiu o market share do Banco do Brasil em consignado nos ultimos trimestres?"),
    ("computada (generaliza: OUTRA modalidade)",
     # o caminho de numeros e generico: a modalidade vem da pergunta (aqui, cartao em vez de consignado)
     "Qual o market share do Nubank em cartao de credito, segundo o IF.data?"),
    ("multi-fonte (declarado x computado, B3)",
     # o coracao do Caso B: o que o CEO DECLAROU (transcricao) x o que COMPUTAMOS do Bacen
     "O market share de consignado do Bradesco no balanco bate com o que computamos do Bacen IF.data?"),
    ("nao-respondivel (futuro)",
     "Qual sera o custo de credito do Bradesco no 2o trimestre de 2027?"),
    ("nao-respondivel (cruza base contabil)",
     "Compare o guidance de custo de credito do Nubank com o do Itau."),
]


def main():
    carregar_dotenv()
    llm = criar_llm()
    print(f">>> Redator: {type(llm).__name__ if llm else 'NENHUM (fallback deterministico)'}")
    deps = Dependencias(con=conectar(str(DUCKDB_PATH)),
                        encoder=BGEM3Encoder(), reranker=BGEReranker(), llm=llm)

    for categoria, pergunta in PERGUNTAS:
        print("\n" + "=" * 72)
        print(f"[{categoria}]  {pergunta}")
        print("-" * 72)
        resp = responder(pergunta, deps)
        print(resp.formatado)


if __name__ == "__main__":
    main()
