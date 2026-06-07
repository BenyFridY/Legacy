"""Geração da resposta — pega a evidência recuperada e produz uma resposta CITADA, ou RECUSA.

Fluxo de `responder_de_contexto`:
  1) GATE DE EVIDÊNCIA (Estágio 2): nota fraca -> recusa "não disponível na base" (não redige).
  2) MONTA O PROMPT: instrução + trechos numerados (com a citação de cada um) + a pergunta.
  3) LLM REDIGE usando SÓ o contexto; se nem assim achar, devolve o sentinela NAO_ENCONTRADO
     (defesa em profundidade: além do gate, o próprio LLM pode recusar).
  4) CITAÇÃO ESTRUTURAL: anexamos por CÓDIGO a citação dos trechos usados — não dependemos
     de o LLM lembrar de citar. Toda resposta sai com suas fontes (regra inegociável do case).

Isto é o BLOCO de geração ("dado o contexto, responda ou recuse"). O orquestrador completo
(pergunta -> roteador -> busca/SQL -> este bloco) vive em `legacy_rag/pipeline.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from legacy_rag.config import LIMIAR_EVIDENCIA_PADRAO
from legacy_rag.generation.gate import gate_evidencia
from legacy_rag.generation.llm import LLMClient
from legacy_rag.retrieval.vetorial import Resultado

SENTINELA_NAO_ENCONTRADO = "NAO_ENCONTRADO"

INSTRUCAO = (
    "Você é um assistente de research de equities. Responda à PERGUNTA usando SOMENTE os "
    "trechos do CONTEXTO. Não invente números nem fatos. Se o contexto não contiver a "
    f"resposta, responda exatamente '{SENTINELA_NAO_ENCONTRADO}'. Seja conciso e em português."
)


@dataclass
class Resposta:
    texto: str
    citacoes: list[str] = field(default_factory=list)
    recusou: bool = False
    motivo: str | None = None

    @property
    def formatado(self) -> str:
        """Texto pronto para exibir: resposta + bloco de fontes (ou a recusa)."""
        if self.recusou:
            return f"[RECUSA] {self.texto}" + (f" ({self.motivo})" if self.motivo else "")
        if not self.citacoes:
            return self.texto
        fontes = "\n".join(f"  - {c}" for c in self.citacoes)
        return f"{self.texto}\n\nFontes:\n{fontes}"


def montar_prompt(pergunta: str, resultados: list[Resultado]) -> str:
    """Instrução + trechos numerados (cada um com sua citação) + a pergunta."""
    blocos = [f"[{i}] ({r.citacao})\n{r.texto}" for i, r in enumerate(resultados, 1)]
    contexto = "\n\n".join(blocos)
    return f"{INSTRUCAO}\n\nCONTEXTO:\n{contexto}\n\nPERGUNTA: {pergunta}\n\nRESPOSTA:"


def responder_de_contexto(pergunta: str, resultados: list[Resultado], llm: LLMClient | None,
                          limiar: float = LIMIAR_EVIDENCIA_PADRAO) -> Resposta:
    """Gate de evidência -> (recusa) ou (LLM redige + citação estrutural).

    Sem LLM (sem chave): degrada com elegância — devolve os trechos recuperados JÁ CITADOS, em vez
    de quebrar. Honra a promessa "sem chave o sistema ainda recupera e cita; só não redige texto livre".
    """
    decisao = gate_evidencia(resultados, limiar)
    if not decisao.responder:
        return Resposta(texto="Não disponível na base.", recusou=True, motivo=decisao.motivo)

    # Citação ESTRUTURAL: as fontes vêm dos trechos que embasaram a resposta, por código.
    # dict.fromkeys -> dedup preservando a ordem (vários chunks da MESMA página viram 1 fonte).
    citacoes = list(dict.fromkeys(r.citacao for r in resultados))

    if llm is None:                                    # fallback determinístico: sem redator, mostra evidência
        contexto = "\n\n".join(f"[{i}] ({r.citacao})\n{r.texto}" for i, r in enumerate(resultados, 1))
        return Resposta(texto="Trechos recuperados (sem redator LLM ativo):\n" + contexto, citacoes=citacoes)

    saida = llm.completar(montar_prompt(pergunta, resultados)).strip()
    if SENTINELA_NAO_ENCONTRADO in saida.upper():
        return Resposta(texto="Não disponível na base.", recusou=True,
                        motivo="O LLM não encontrou a resposta no contexto fornecido.")
    return Resposta(texto=saida, citacoes=citacoes, recusou=False)
