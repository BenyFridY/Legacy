"""PROVA DE RETRIEVAL SEMANTICO REAL — abre a torneira e mostra que sai agua limpa.

A suite de testes prova o ENCANAMENTO com um encoder FALSO (os dados fluem, as recusas disparam,
as citacoes se anexam). Eles NAO provam qualidade semantica. Este script pluga os modelos
REAIS (BGE-M3 + bge-reranker-v2-m3), ingere um release de verdade e faz buscas que so acertam
se o sistema entender SIGNIFICADO — nao apenas casar palavra exata.

Como ler a saida:
  - "VETORIAL PURO" isola o significado: so o vetor decide (sem BM25, sem rerank).
  - "HIBRIDO + RERANKER" e o que o sistema usa em producao (vetorial + BM25 -> RRF -> rerank).
    A nota final (0-1) e a do cross-encoder — a MESMA que o gate de evidencia (Estagio 2) usa.

As PROVAS sao perguntas realistas de research; a de 'calote' nao tem nenhuma palavra em comum
com 'inadimplencia' -> testa sinonimo puro. A secao LIMITE e uma descoberta honesta: uma
parafrase perifrastica extrema ('descontado da folha') escapa ao vetor denso — por isso a
busca e HIBRIDA (o BM25 cobre o termo exato) e por isso o consignado fino vem do caminho dos
numeros (Bacen). Mostrar o limite e maturidade, nao defeito.

Idempotente: ingere so na primeira vez (dedup por banco/periodo/tipo).
Uso:  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & python scripts/prova_retrieval_real.py
"""
import sys

from legacy_rag.torch_env import preparar_torch
preparar_torch()                       # torch ANTES de numpy/duckdb (conflito OpenMP no conda/Windows)

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.index.store_texto import garantir_schema
from legacy_rag.ingestion.ingerir import ingerir_release
from legacy_rag.retrieval.hibrido import buscar_hibrido
from legacy_rag.retrieval.rerank import BGEReranker, rerankar
from legacy_rag.retrieval.vetorial import buscar_vetorial
from legacy_rag.structured.store import conectar

try:                                   # saida em UTF-8 -> acentos dos PDFs sem mojibake
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Release real, URL do CDN mziq validada (Itau "Analise Gerencial da Operacao" 4T25; 169 pp).
URL_ITAU_4T25 = ("https://filemanager-cdn.mziq.com/published/"
                 "42787847-4cf6-4461-94a5-40ed237dca33/"
                 "fb7d9580-424d-47aa-924e-8cf202975d59_itau_unibanco_holding_s.a..pdf")
BANCO, PERIODO, TIPO = "Itau", "4T25", "release"

# PROVAS: perguntas realistas de research que o PIPELINE COMPLETO acerta (a pagina-resposta no topo).
PROVAS = [
    ("qual o saldo da carteira de credito consignado do Itau",
     "consignado: deve achar a tabela/destaque da carteira (pag. 21)"),
    ("qual foi o lucro liquido recorrente do banco no trimestre",
     "resultado do periodo: deve achar o Sumario Executivo (pag. 8)"),
]
# LIMITES (honestidade): dois casos que NAO casam — cada um com sua licao de engenharia.
LIMITES = [
    ("qual o nivel de calote dos clientes do banco",
     "GIRIA: o VETOR liga 'calote'->inadimplencia (pag.14 no topo do vetorial), mas o RERANKER "
     "formal nao, e empata tudo em ~0.5 -> apaga o sinal do vetor. (candidato a ADR: cair p/ RRF "
     "quando o reranker nao discrimina)"),
    ("emprestimo descontado direto da folha de pagamento do trabalhador",
     "PARAFRASE EXTREMA: definicao de consignado, ZERO palavra em comum -> nem vetor nem reranker "
     "ligam. Licao: por isso a busca e HIBRIDA (BM25 cobre o termo) e o consignado fino vem dos NUMEROS"),
]


def _mostrar(titulo, resultados):
    print(f"    {titulo}")
    if not resultados:
        print("      (vazio)")
        return
    for i, r in enumerate(resultados, 1):
        trecho = " ".join(r.texto.split())[:100]
        print(f"      {i}. nota={r.score:.3f}  [{r.citacao}]")
        print(f"         {trecho}...")


def _buscar(con, encoder, reranker, pergunta):
    qv = encoder.encode([pergunta])[0]
    vet = buscar_vetorial(con, qv, k=3, banco=BANCO)
    hib = buscar_hibrido(con, pergunta, qv, k=5, n_ramo=50, banco=BANCO)
    top = rerankar(pergunta, hib, reranker, top_k=3)
    return vet, top


def main():
    con = conectar(str(DUCKDB_PATH))
    garantir_schema(con)
    encoder, reranker = BGEM3Encoder(), BGEReranker()

    ja = con.execute("SELECT COUNT(*) FROM chunks WHERE banco=? AND periodo=? AND tipo_doc=?",
                     [BANCO, PERIODO, TIPO]).fetchone()[0]
    if ja:
        print(f">>> {BANCO} {PERIODO} ja ingerido ({ja} chunks). Pulando download/embedding.")
    else:
        print(f">>> Ingerindo {BANCO} {PERIODO} com BGE-M3 REAL (baixa PDF + embeda; minutos)...")
        n = ingerir_release(con, URL_ITAU_4T25, BANCO, PERIODO, TIPO, encoder)
        print(f">>> Ingeridos {n} chunks com vetores 1024-dim reais.")

    print(f"\n=== PROVAS DE RETRIEVAL — o pipeline acerta (corpus: {BANCO} {PERIODO}) ===")
    for pergunta, nota in PROVAS:
        print(f"\n--- PERGUNTA: {pergunta}\n    ({nota})")
        vet, top = _buscar(con, encoder, reranker, pergunta)
        _mostrar("VETORIAL PURO (so significado):", vet)
        _mostrar("HIBRIDO + RERANKER (o que o sistema usa):", top)

    print("\n=== LIMITES (honestidade) — onde nao casa, e por que ===")
    for pergunta, licao in LIMITES:
        print(f"\n--- PERGUNTA: {pergunta}\n    ({licao})")
        vet, top = _buscar(con, encoder, reranker, pergunta)
        _mostrar("VETORIAL PURO:", vet)
        _mostrar("HIBRIDO + RERANKER:", top)


if __name__ == "__main__":
    main()
