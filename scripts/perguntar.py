"""Pergunta LIVRE ao sistema (modelos reais) — diagnóstico de rota + resposta/recusa.

Uso:
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 &
  python scripts/perguntar.py "Qual o lucro do Itau no 4T25?"

Sem argumento, roda uma BATERIA que inclui perguntas FORA DE ESCOPO (receita de comida, futebol)
para mostrar a recusa segura — exatamente a defesa contra alucinação que o case exige. A recusa
por evidência (Estágio 2) já imprime a melhor nota do reranker no motivo.
"""
import sys

from legacy_rag.runtime import construir_deps  # chama preparar_torch() ao importar
from legacy_rag.pipeline import responder
from legacy_rag.router.router import rotear

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# (rótulo do que estamos testando, pergunta)
BATERIA = [
    ("FORA DE ESCOPO — receita de comida", "Qual a receita de um bolo de cenoura com cobertura de chocolate?"),
    ("FORA DE ESCOPO — conhecimento geral", "Quem ganhou a Copa do Mundo de futebol de 2022?"),
    ("FORA DE ESCOPO — outra indústria", "Qual foi a produção de petróleo da Petrobras em 2024?"),
    ("DENTRO — métrica não ingerida (deve recusar pelo gate)", "Qual foi o índice de Basileia do Itaú no 4T25?"),
    ("DENTRO — sanidade (deve responder)", "Qual foi o lucro líquido recorrente do Itaú no 4T25?"),
]


def diagnosticar(pergunta: str, deps) -> None:
    rota = rotear(pergunta)
    print(f"  rota={rota.categoria}  bancos={rota.bancos or '-'}  anos={rota.anos or '-'}  métrica={rota.metrica}")
    if rota.motivo_recusa:
        print(f"  (recusa de escopo no roteador: {rota.motivo_recusa})")
    resp = responder(pergunta, deps)
    print("  " + resp.formatado.replace("\n", "\n  "))


def main() -> None:
    deps = construir_deps()
    redator = type(deps.llm).__name__ if deps.llm else "NENHUM (fallback determinístico)"
    print(f">>> Redator: {redator}\n")

    perguntas = [("CLI", " ".join(sys.argv[1:]))] if len(sys.argv) > 1 else BATERIA
    for rotulo, pergunta in perguntas:
        print("=" * 78)
        print(f"[{rotulo}]")
        print(f"P: {pergunta}")
        print("-" * 78)
        diagnosticar(pergunta, deps)
        print()


if __name__ == "__main__":
    main()
