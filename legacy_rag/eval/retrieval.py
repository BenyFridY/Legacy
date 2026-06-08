"""Avaliacao de RETRIEVAL (hit@k / MRR) contra um gold curado por pagina.

Mede a pergunta central da rubrica (25%): "dada a pergunta, a PAGINA-resposta aparece no
top-k?". Diferente do runner de recusa-por-escopo (eval/runner.py, deterministico e sem
modelo), este avalia o RANKING — entao depende de uma funcao de busca. Mas a busca entra por
INJECAO (`busca_fn`): assim a logica de avaliacao e testavel com um fake (sem torch/rede) e o
runner real (scripts/eval_retrieval_real.py) pluga BGE-M3 + reranker.

Unidade de relevancia = CHUNK, gold = "qualquer chunk de uma pagina-gold". O YAML lista o gold
por PAGINA (estavel, legivel); aqui resolvemos pagina -> chunk_ids no DB. Reaproveita as
metricas puras de metrics.py (hit_at_k, reciprocal_rank) — chunk_id (int) serve como id.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

import duckdb
import yaml

from legacy_rag.config import ROOT
from legacy_rag.eval.metrics import hit_at_k, reciprocal_rank

CAMINHO_GOLD_PADRAO = ROOT / "eval" / "retrieval_gold.yaml"
KS_PADRAO = (1, 3, 5)

# busca_fn: recebe uma Sondagem e devolve os chunk_ids RANQUEADOS (rank 1 primeiro).
BuscaFn = Callable[["Sondagem"], Sequence[int]]


@dataclass
class Sondagem:
    """Uma pergunta de retrieval + o gold (paginas-resposta) e metadados de filtro/dificuldade."""
    id: str
    banco: str
    periodo: str
    tipo_doc: str
    question: str
    gold_paginas: list[int]
    dificuldade: str = "media"
    note: str = ""


@dataclass
class ResultadoSondagem:
    id: str
    dificuldade: str
    hits: dict[int, bool]          # k -> a pagina-gold entrou no top-k?
    rr: float                      # reciprocal rank (1/posicao do 1o chunk-gold)
    n_gold: int                    # quantos chunks-gold existem (sanidade)


@dataclass
class ResultadoRetrieval:
    por_sondagem: list[ResultadoSondagem] = field(default_factory=list)
    ks: tuple[int, ...] = KS_PADRAO

    @property
    def n(self) -> int:
        return len(self.por_sondagem)

    def hit_rate(self, k: int) -> float:
        """Fracao das sondagens em que a pagina-resposta entrou no top-k."""
        if not self.por_sondagem:
            return 0.0
        return sum(1 for r in self.por_sondagem if r.hits.get(k)) / len(self.por_sondagem)

    @property
    def mrr(self) -> float:
        if not self.por_sondagem:
            return 0.0
        return sum(r.rr for r in self.por_sondagem) / len(self.por_sondagem)


def carregar_sondagens(caminho: str | Path = CAMINHO_GOLD_PADRAO) -> list[Sondagem]:
    """Le o YAML de gold de retrieval e devolve a lista de Sondagem."""
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8"))
    return [Sondagem(**item) for item in dados["sondagens"]]


def resolver_gold_chunk_ids(con: duckdb.DuckDBPyConnection, s: Sondagem) -> set[int]:
    """Pagina-gold -> conjunto de chunk_ids daquele documento naquelas paginas."""
    if not s.gold_paginas:
        return set()
    marcadores = ",".join("?" for _ in s.gold_paginas)
    sql = (f"SELECT chunk_id FROM chunks WHERE banco=? AND periodo=? AND tipo_doc=? "
           f"AND pagina IN ({marcadores})")
    params = [s.banco, s.periodo, s.tipo_doc, *s.gold_paginas]
    return {row[0] for row in con.execute(sql, params).fetchall()}


def avaliar_sondagem(con: duckdb.DuckDBPyConnection, s: Sondagem, busca_fn: BuscaFn,
                     ks: Sequence[int] = KS_PADRAO) -> ResultadoSondagem:
    gold = resolver_gold_chunk_ids(con, s)
    ranqueados = list(busca_fn(s))
    return ResultadoSondagem(
        id=s.id, dificuldade=s.dificuldade,
        hits={k: hit_at_k(ranqueados, gold, k) for k in ks},
        rr=reciprocal_rank(ranqueados, gold),
        n_gold=len(gold),
    )


def avaliar_retrieval(con: duckdb.DuckDBPyConnection, sondagens: Sequence[Sondagem],
                      busca_fn: BuscaFn, ks: Sequence[int] = KS_PADRAO) -> ResultadoRetrieval:
    """Roda todas as sondagens e agrega hit@k e MRR."""
    return ResultadoRetrieval(
        por_sondagem=[avaliar_sondagem(con, s, busca_fn, ks) for s in sondagens],
        ks=tuple(ks),
    )


def formatar_relatorio(res: ResultadoRetrieval) -> str:
    """Relatorio ASCII-only (robusto ao console cp1252 do Windows)."""
    linhas = ["=" * 64, "EVAL DE RETRIEVAL (hit@k / MRR) — gold por pagina", "=" * 64,
              f"sondagens: {res.n}"]
    ks = res.ks
    cab = "  " + "id".ljust(28) + "dif".ljust(9) + "  ".join(f"h@{k}" for k in ks) + "   RR"
    linhas.append(cab)
    orfaos = []
    for r in res.por_sondagem:
        marca = lambda b: " ok " if b else "  . "
        hits = "".join(marca(r.hits.get(k, False)) for k in ks)
        aviso = "  <- GOLD-VAZIO" if r.n_gold == 0 else ""
        linhas.append(f"  {r.id.ljust(28)}{r.dificuldade.ljust(9)}{hits}  {r.rr:.2f}{aviso}")
        if r.n_gold == 0:
            orfaos.append(r.id)
    linhas.append("-" * 64)
    for k in ks:
        linhas.append(f"  hit@{k}: {res.hit_rate(k) * 100:5.1f}%")
    linhas.append(f"  MRR  : {res.mrr:.3f}")
    if orfaos:                          # gold que nao resolve (pagina/tipo/periodo errado) vira miss SILENCIOSO
        linhas.append("-" * 64)
        linhas.append(f"  AVISO: {len(orfaos)} sondagem(ns) com gold IRRESOLVIVEL (pagina/tipo/periodo nao")
        linhas.append("         existe no DB) -> contam como MISS e DEPRIMEM o agregado. Confira o YAML:")
        linhas.append(f"         {', '.join(orfaos)}")
    linhas.append("=" * 64)
    return "\n".join(linhas)
