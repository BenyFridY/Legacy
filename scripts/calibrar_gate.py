"""Calibra o GATE DE EVIDENCIA (Estagio 2) contra o mini-gold eval/gate_gold.yaml.

Pontua cada pergunta com o retrieval REAL (encoder + reranker, SEM LLM -> rapido), pega a MELHOR
nota do reranker e varre o limiar, contando os dois erros: over-recusa (respondivel recusada) x
vazamento (fora-da-base que passou). Imprime a tabela e o 'joelho' recomendado, comparando ao
valor atual (0,30). E o numero que faltava no criterio de avaliacao (mede a recusa por EVIDENCIA,
nao so a recusa por escopo do roteador). Ver legacy_rag/eval/calibracao_gate.py.

Uso (depois de ingerir o corpus):
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 & python scripts/calibrar_gate.py
"""
import sys

from legacy_rag.runtime import construir_deps   # preparar_torch() roda no import (torch antes de numpy)

import yaml

from legacy_rag.config import LIMIAR_EVIDENCIA_PADRAO, ROOT
from legacy_rag.eval.calibracao_gate import Amostra, escolher_joelho, formatar_relatorio, varrer_limiar
from legacy_rag.pipeline import _buscar_texto
from legacy_rag.router.router import rotear

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

GOLD = ROOT / "eval" / "gate_gold.yaml"
LIMIARES = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]


def main() -> None:
    casos = yaml.safe_load(GOLD.read_text(encoding="utf-8"))["casos"]
    deps = construir_deps(com_llm=False)          # so pontuacao do retrieval; geracao nao importa aqui
    print(f">>> Pontuando {len(casos)} casos do mini-gold com retrieval real (encoder + reranker)...\n")

    amostras = []
    for c in casos:
        rota = rotear(c["question"])
        melhor = max((r.score for r in _buscar_texto(c["question"], rota, deps)), default=0.0)
        amostras.append(Amostra(c["id"], melhor, c["esperado"] == "answer"))
        print(f"  {c['id']:26} esperado={c['esperado']:7} rota={rota.categoria:15} melhor_nota={melhor:.3f}")

    pontos = varrer_limiar(amostras, LIMIARES)
    print("\n" + formatar_relatorio(pontos, atual=LIMIAR_EVIDENCIA_PADRAO))
    joelho = escolher_joelho(pontos)
    print(f"\n>>> Atual em config.py: LIMIAR_EVIDENCIA_PADRAO = {LIMIAR_EVIDENCIA_PADRAO:.2f}")
    print(f">>> Joelho medido: {joelho.limiar:.2f} "
          f"(over-recusa {joelho.taxa_over_recusa*100:.0f}%, vazamento {joelho.taxa_vazamento*100:.0f}%)")


if __name__ == "__main__":
    main()
