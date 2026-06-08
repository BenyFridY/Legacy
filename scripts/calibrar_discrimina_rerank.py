"""Calibra/valida o LIMIAR_DISCRIMINA_RERANK (hoje 0,05) com NUMERO MEDIDO, nao chute.

A hipotese (ADR-0005): nas sondagens DIFICEIS (giria "calote", parafrase) o cross-encoder
"empata tudo" -> desvio-padrao (pstdev) das notas BAIXO; nas FACEIS ele discrimina -> pstdev
ALTO. Se um limiar separar limpo os dois grupos, o fallback-para-RRF esta justificado. Mede o
pstdev real das notas do reranker sobre os MESMOS candidatos que a producao funde (banco+periodo).

Espelha o gate (eval/calibracao_gate.py + scripts/calibrar_gate.py): medir antes de afirmar.

Uso: set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 &
     python scripts/calibrar_discrimina_rerank.py
"""
import statistics
import sys

from legacy_rag.torch_env import preparar_torch
preparar_torch()                       # torch ANTES de numpy/duckdb (conflito OpenMP no Windows)

from legacy_rag.config import DUCKDB_PATH, LIMIAR_DISCRIMINA_RERANK
from legacy_rag.eval.retrieval import carregar_sondagens
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.retrieval.hibrido import buscar_hibrido
from legacy_rag.retrieval.rerank import BGEReranker
from legacy_rag.structured.store import conectar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FUSAO = 10                             # mesmo pool que a producao funde antes do rerank


def main():
    con = conectar(str(DUCKDB_PATH))
    encoder, reranker = BGEM3Encoder(), BGEReranker()
    sondagens = carregar_sondagens()

    print(f"{'id':32}{'dif':9}{'n':>3}{'pstdev':>9}{'maxnota':>9}  fallback p/ RRF?")
    print("-" * 74)
    grupos = {"facil/media": [], "dificil": []}
    for s in sondagens:
        qv = encoder.encode([s.question])[0]
        hib = buscar_hibrido(con, s.question, qv, k=FUSAO, n_ramo=50, banco=s.banco, periodo=s.periodo)
        notas = reranker.pontuar(s.question, [r.texto for r in hib])
        if len(notas) < 2:
            continue
        sd = statistics.pstdev(notas)
        dispara = sd < LIMIAR_DISCRIMINA_RERANK
        grupo = "dificil" if s.dificuldade == "dificil" else "facil/media"
        grupos[grupo].append(sd)
        print(f"{s.id[:31]:32}{s.dificuldade:9}{len(notas):>3}{sd:>9.3f}{max(notas):>9.3f}"
              f"  {'SIM (mantem ordem RRF)' if dispara else ''}")

    print("-" * 74)
    for g, vals in grupos.items():
        if vals:
            print(f"  {g:14} pstdev: min={min(vals):.3f}  media={statistics.mean(vals):.3f}  "
                  f"max={max(vals):.3f}  (n={len(vals)})")
    print(f"\n  LIMIAR_DISCRIMINA_RERANK atual = {LIMIAR_DISCRIMINA_RERANK}")
    print("  Leitura: o limiar e bom se fica ACIMA do pstdev das dificeis e ABAIXO do das faceis.")


if __name__ == "__main__":
    main()
