"""Eval de FIDELIDADE (faithfulness) — a resposta fica fiel ao contexto citado?

As outras duas pernas do eval medem: (retrieval) o trecho certo sobe ao topo? e (escopo) recusamos
o que está fora da base? Falta a terceira, e a mais crítica para research: quando o sistema
RESPONDE, cada afirmação da resposta está SUPORTADA pelos trechos citados? Num relatório de
equities, alucinar um número é o pecado capital — então medimos isso explicitamente.

COMO: um JUIZ (LLM, atrás de interface trocável) vê SÓ (pergunta, resposta, contexto citado) e
decide se a resposta é inteiramente sustentada pelo contexto, listando qualquer alegação sem
suporte. O juiz é INJETÁVEL -> a lógica é testável com um juiz FALSO determinístico (sem rede,
sem chave, sem torch).

HONESTIDADE: faithfulness por LLM-juiz tem RUÍDO. Mitigamos com temperatura 0 e, sobretudo,
REPORTANDO as alegações-sem-suporte para auditoria humana — a taxa é um sinal, não um oráculo.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from legacy_rag.generation.llm import LLMClient


@dataclass
class CasoFidelidade:
    """Um caso a julgar: a pergunta, a resposta gerada e o contexto que a embasou (já citado)."""
    id: str
    pergunta: str
    resposta: str
    contexto: str


@dataclass
class Veredito:
    """O julgamento de um caso. `fundamentada` = toda alegação tem suporte no contexto."""
    fundamentada: bool
    alegacoes_sem_suporte: list[str] = field(default_factory=list)
    justificativa: str = ""


class JuizFidelidade(Protocol):
    """Interface trocável do juiz — permite um juiz FALSO nos testes e o LLM real no runner."""

    def julgar(self, caso: CasoFidelidade) -> Veredito: ...


PROMPT_JUIZ = (
    "Você é um auditor rigoroso de fidelidade factual. Receberá uma PERGUNTA, uma RESPOSTA e o "
    "CONTEXTO que deveria sustentá-la. Sua tarefa: decidir se TODA afirmação factual da RESPOSTA "
    "está SUPORTADA pelo CONTEXTO (números, datas, entidades têm de bater). NÃO use conhecimento "
    "externo; só o CONTEXTO conta. Se algo na resposta não estiver no contexto, é 'sem suporte'.\n\n"
    "Responda EXCLUSIVAMENTE com um JSON válido, sem texto antes ou depois, no formato:\n"
    '{{"fundamentada": true|false, "alegacoes_sem_suporte": ["..."], "justificativa": "uma frase"}}\n\n'
    "PERGUNTA: {pergunta}\n\nRESPOSTA: {resposta}\n\nCONTEXTO:\n{contexto}\n\nJSON:"
)


def _parse_veredito(saida: str) -> Veredito:
    """Extrai o JSON do juiz de forma defensiva. Se não der para confirmar, trata como NÃO fundamentada.

    Conservador de propósito: um juiz ilegível não pode 'absolver' a resposta — para faithfulness,
    'não consegui confirmar suporte' deve contar contra, não a favor.
    """
    ini, fim = saida.find("{"), saida.rfind("}")
    if ini == -1 or fim == -1 or fim < ini:
        return Veredito(fundamentada=False, justificativa=f"juiz ilegível: {saida[:120]!r}")
    try:
        dados = json.loads(saida[ini:fim + 1])
    except (json.JSONDecodeError, ValueError):
        return Veredito(fundamentada=False, justificativa=f"JSON inválido do juiz: {saida[ini:fim+1][:120]!r}")
    sem_suporte = dados.get("alegacoes_sem_suporte") or []
    if not isinstance(sem_suporte, list):
        sem_suporte = [str(sem_suporte)]
    return Veredito(
        fundamentada=_para_bool(dados.get("fundamentada", False)),
        alegacoes_sem_suporte=[str(x) for x in sem_suporte],
        justificativa=str(dados.get("justificativa", "")),
    )


def _para_bool(v) -> bool:
    """Bool robusto e CONSERVADOR: o LLM às vezes serializa o booleano como STRING ("false").
    bool("false") seria True (erro!), invertendo a recusa -> só True/"true"/"sim"/1 contam como fiel."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "sim", "yes", "verdadeiro")
    return bool(v)


class LLMJuizFidelidade:
    """Juiz real: monta o prompt, chama o LLMClient (temperatura 0 no GroqClient) e parseia o JSON."""

    def __init__(self, llm: LLMClient):
        self.llm = llm

    def julgar(self, caso: CasoFidelidade) -> Veredito:
        prompt = PROMPT_JUIZ.format(pergunta=caso.pergunta, resposta=caso.resposta, contexto=caso.contexto)
        return _parse_veredito(self.llm.completar(prompt).strip())


@dataclass
class ResultadoFidelidade:
    """Agregado: quantos casos foram julgados fiéis, a taxa, e os vereditos para auditoria."""
    vereditos: list[tuple[CasoFidelidade, Veredito]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.vereditos)

    @property
    def fundamentadas(self) -> int:
        return sum(1 for _, v in self.vereditos if v.fundamentada)

    @property
    def taxa(self) -> float | None:
        """Fração de respostas inteiramente sustentadas pelo contexto (None se não há casos)."""
        return self.fundamentadas / self.total if self.total else None


def avaliar_fidelidade(casos: Sequence[CasoFidelidade], juiz: JuizFidelidade) -> ResultadoFidelidade:
    """Julga cada caso com o juiz injetado e agrega — a lógica é independente do juiz ser real ou fake."""
    return ResultadoFidelidade(vereditos=[(c, juiz.julgar(c)) for c in casos])


def formatar_relatorio(resultado: ResultadoFidelidade) -> str:
    """Relatório ASCII puro (robusto ao console cp1252 do Windows), com as alegações sem suporte."""
    linhas = [
        "=" * 64,
        "EVAL - Fidelidade (faithfulness): a resposta e sustentada pelo contexto?",
        "=" * 64,
        f"casos: {resultado.total}",
        f"  {'id':<32} {'fiel?':<6} alegacoes_sem_suporte",
        "-" * 64,
    ]
    for caso, v in resultado.vereditos:
        marca = "ok" if v.fundamentada else "X"
        extra = "" if v.fundamentada else " | ".join(v.alegacoes_sem_suporte)[:60]
        linhas.append(f"  {caso.id:<32} {marca:<6} {extra}")
    linhas.append("-" * 64)
    taxa = resultado.taxa
    taxa_txt = "n/a" if taxa is None else f"{taxa * 100:.0f}%"
    linhas.append(f"  Taxa de fidelidade: {taxa_txt}  ({resultado.fundamentadas}/{resultado.total})")
    linhas.append("=" * 64)
    return "\n".join(linhas)
