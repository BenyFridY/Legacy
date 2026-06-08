"""Calibração do GATE DE EVIDÊNCIA (Estágio 2) — acha o limiar que melhor separa responder x recusar.

O gate decide "responder ou recusar" comparando a MELHOR nota do reranker a um limiar. Esse limiar
era um PLACEHOLDER (0,30); a bateria empírica mostrou que ele é frouxo (deixou "receita de bolo"
passar — quem segurou foi o LLM). Aqui o medimos: dado um mini-gold (perguntas RESPONDÍVEIS x
FORA-DA-BASE) e a melhor nota do reranker de cada uma, varremos o limiar e contamos os dois erros:

  over-recusa  = pergunta RESPONDÍVEL recusada    (melhor_nota < limiar)  -> sistema covarde
  vazamento    = pergunta FORA-DA-BASE que passou  (melhor_nota >= limiar) -> risco de alucinação

O "joelho" minimiza a soma das duas taxas (empate -> menor limiar). A coleta das notas (cara, com
modelos reais) é separada deste cálculo (puro, testável sem torch): ver scripts/calibrar_gate.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass
class Amostra:
    """Uma pergunta do mini-gold: a melhor nota do reranker e se ela DEVERIA ser respondida."""
    id: str
    melhor_nota: float
    deve_responder: bool


@dataclass
class PontoCalibracao:
    limiar: float
    over_recusa: int        # respondíveis recusadas (falso negativo)
    vazamento: int          # fora-da-base que passaram (falso positivo -> risco de alucinação)
    n_resp: int
    n_fora: int

    @property
    def taxa_over_recusa(self) -> float:
        return self.over_recusa / self.n_resp if self.n_resp else 0.0

    @property
    def taxa_vazamento(self) -> float:
        return self.vazamento / self.n_fora if self.n_fora else 0.0

    @property
    def custo(self) -> float:
        """Soma das duas taxas de erro — o que o 'joelho' minimiza."""
        return self.taxa_over_recusa + self.taxa_vazamento


def varrer_limiar(amostras: Sequence[Amostra],
                  limiares: Sequence[float]) -> list[PontoCalibracao]:
    """Para cada limiar, conta over-recusa (respondível recusada) e vazamento (fora-da-base passou)."""
    resp = [a for a in amostras if a.deve_responder]
    fora = [a for a in amostras if not a.deve_responder]
    pontos = []
    for limiar in limiares:
        over = sum(1 for a in resp if a.melhor_nota < limiar)
        vaz = sum(1 for a in fora if a.melhor_nota >= limiar)
        pontos.append(PontoCalibracao(round(float(limiar), 3), over, vaz, len(resp), len(fora)))
    return pontos


def escolher_joelho(pontos: Sequence[PontoCalibracao]) -> PontoCalibracao:
    """O limiar de menor custo (over-recusa + vazamento); empate -> menor limiar (mais permissivo)."""
    return min(pontos, key=lambda p: (p.custo, p.limiar))


def formatar_relatorio(pontos: Sequence[PontoCalibracao], atual: float | None = None) -> str:
    """Tabela ASCII (robusta ao console do Windows): limiar x over-recusa x vazamento x custo."""
    joelho = escolher_joelho(pontos)
    linhas = ["=" * 60, "CALIBRACAO DO GATE DE EVIDENCIA (Estagio 2)", "=" * 60,
              "  limiar  over-recusa   vazamento    custo"]
    for p in pontos:
        marca = "  <- joelho" if p.limiar == joelho.limiar else ""
        if atual is not None and abs(p.limiar - atual) < 1e-9:
            marca += "  (atual)"
        linhas.append(f"   {p.limiar:0.2f}    {p.over_recusa}/{p.n_resp} ({p.taxa_over_recusa*100:4.0f}%)   "
                      f"{p.vazamento}/{p.n_fora} ({p.taxa_vazamento*100:4.0f}%)   {p.custo:.2f}{marca}")
    linhas.append("-" * 60)
    linhas.append(f"  Recomendado (joelho): limiar = {joelho.limiar:0.2f}  (custo {joelho.custo:.2f})")
    linhas.append("=" * 60)
    return "\n".join(linhas)
