"""RUNNER do eval de retrieval com os MODELOS REAIS (BGE-M3 + bge-reranker-v2-m3).

Pluga a busca real (hibrido + rerank) na logica de avaliacao de legacy_rag/eval/retrieval.py
e mede hit@k / MRR contra o gold curado (eval/retrieval_gold.yaml). Honesto: inclui sondagens
dificeis (giria, parafrase) que esperamos falhar — o numero NAO sera 100%, e e esse o ponto.

O eval mede a MESMA busca da PRODUCAO (legacy_rag/pipeline.py:_buscar_texto): pre-filtro
banco+periodo (a pergunta nomeia o trimestre -> fixa o documento certo num corpus multi-periodo),
funde FUSAO candidatos e o cross-encoder devolve os FINAL melhores. O numero reproduz o caminho
que roda em producao, nao uma busca so-banco.

Pre-requisito: o corpus do gold ja ingerido (rode scripts/ingerir_corpus.py antes).
Uso:  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 &
      python scripts/eval_retrieval_real.py
"""
import sys

from legacy_rag.torch_env import preparar_torch
preparar_torch()                       # torch ANTES de numpy/duckdb (conflito OpenMP no conda/Windows)

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.eval.retrieval import avaliar_retrieval, carregar_sondagens, formatar_relatorio
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.retrieval.hibrido import buscar_hibrido
from legacy_rag.retrieval.rerank import BGEReranker, rerankar
from legacy_rag.structured.store import conectar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FUSAO = 10                             # pool que o pipeline funde antes do rerank (Dependencias.k_rerank)
FINAL = 5                              # top-k FINAL que a producao entrega (Dependencias.k) — o que o usuario ve


def main():
    con = conectar(str(DUCKDB_PATH))
    encoder, reranker = BGEM3Encoder(), BGEReranker()
    sondagens = carregar_sondagens()

    # Espelha legacy_rag/pipeline.py:_buscar_texto -> pre-filtro banco+periodo, funde FUSAO, rerank -> FINAL.
    def busca_fn(s):
        qv = encoder.encode([s.question])[0]
        hib = buscar_hibrido(con, s.question, qv, k=FUSAO, n_ramo=50, banco=s.banco, periodo=s.periodo)
        top = rerankar(s.question, hib, reranker, top_k=FINAL)
        return [r.chunk_id for r in top]

    print(f">>> Avaliando {len(sondagens)} sondagens com BGE-M3 + reranker reais...")
    res = avaliar_retrieval(con, sondagens, busca_fn, ks=(1, 3, 5))
    print(formatar_relatorio(res))

    faceis = [r for r in res.por_sondagem if r.dificuldade != "dificil"]
    if faceis:
        taxa = sum(1 for r in faceis if r.hits.get(3)) / len(faceis)
        print(f"\n  Leitura: hit@3 nas sondagens realistas (sem giria/parafrase): {taxa*100:.0f}%")
    print("  As 'dificil' (giria/parafrase) sao limites conhecidos — ver scripts/prova_retrieval_real.py.")


if __name__ == "__main__":
    main()
