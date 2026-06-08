"""Roteador determinístico — o "cérebro" que decide o caminho de cada pergunta.

Duas decisões, NESTA ordem:

  1) GATE DE ESCOPO — a pergunta é respondível pela base? Se não, vira `nao_respondivel`
     e o sistema RECUSA antes mesmo de buscar (a regra inegociável do case). Três regras:
       R1  período futuro/inexistente (ano além da cobertura da base).
       R2  comparação entre BASES CONTÁBEIS incompatíveis (IFRS x Cosif) numa métrica de
           release/Cosif (guidance / custo de crédito / PDD). É uma CONJUNÇÃO: só dispara com
           (comparação) E (entidade só-IFRS) E (métrica de release) — NUNCA pelo nome "Nubank".
       R3  pedido de citação VERBATIM ("frase literal") de entidade sem transcrição oficial na
           base. Ancorado no flag `tem_verbatim` por-entidade (não na palavra "Itaú"); e só
           dispara em "frase literal/verbatim", não em "o que declarou" (paráfrase é respondível).

  2) CAMINHO (se estiver no escopo):
       doc_unico   um fato em um único documento (release/MD&A).
       computada   número/série calculado do IF.data via SQL (market share etc.).
       multi_fonte cruza o DECLARADO (texto) com o COMPUTADO (número) — o coração do Caso B.

Por que DETERMINÍSTICO (regras), e não um LLM decidindo solto? REPRODUTIBILIDADE. O eval vale
metade da nota e mede o sistema repetidamente; um roteador-LLM daria caminhos diferentes para a
MESMA pergunta e o número de eval tremeria. Regras: mesma entrada -> mesmo caminho -> eval confiável
e auditável. O preço é fragilidade (uma frase com palavras estranhas pode cair no caminho errado);
por isso a acurácia do roteamento é MEDIDA no eval, não escondida.

LIMITAÇÕES CONHECIDAS (1º corte; ver ADR-0005). Cobre R1/R2/R3 + as 11 perguntas do eval. Lacunas
documentadas para a ingestão larga (ADR-0004), deixadas honestas em vez de fingidas:
  R4  distinguir REALIZADO de GUIDANCE dentro de 2026 (pedir realizado de período ainda não
      publicado deveria recusar) — hoje cai no gate de evidência (Estágio 2).
  R5  entidade ingerida fora do núcleo de prova (Santander, Nubank em Cosif) -> responder, não
      recusar pelo nome (já tratado: ENTIDADES inclui os dois com base_contabil="cosif").
  R6  métrica não-ingerida (ROE, Basileia, NPL) -> cai no gate de evidência (Estágio 2).
A recusa-por-evidência (Estágio 2) depende do reranker real e é avaliada só com os modelos plugados.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from legacy_rag.config import ANO_COBERTURA_MAX, ENTIDADES

CATEGORIAS = ("doc_unico", "computada", "multi_fonte", "nao_respondivel")


# --------------------------------------------------------------------------
# Normalização: tudo minúsculo e sem acento, para casar regras sem depender de
# o usuário ter digitado "Itaú" ou "itau".
# --------------------------------------------------------------------------

def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# --------------------------------------------------------------------------
# Slots: os "fatos" que extraímos da pergunta antes de decidir qualquer coisa.
# Separar EXTRAÇÃO de DECISÃO deixa cada regra curta e testável.
# --------------------------------------------------------------------------

@dataclass
class Slots:
    bancos: list[str] = field(default_factory=list)   # chaves de ENTIDADES mencionadas
    anos: list[int] = field(default_factory=list)      # anos citados (de "2027" e de "4T25")
    periodos: list[str] = field(default_factory=list)  # trimestres citados ("4t25" -> "4T25"), p/ filtro de metadados
    metrica: str = "outra"                              # rótulo grosso p/ transparência/log
    cita_ifdata: bool = False                           # "segundo o IF.data", "Bacen"
    declarado: bool = False                             # "declarou", "CEO", "guidance", "estratégia"
    confronto: bool = False                             # "confirmou", "subiu", "vs" — promete-vs-entrega
    serie: bool = False                                 # "evoluiu", "últimos N trimestres", "trajetória"
    comparacao: bool = False                            # "compare ... com", "versus"
    pede_verbatim: bool = False                         # "frase literal", "transcrição verbatim"


def _detectar_bancos(t: str) -> list[str]:
    achados = []
    for chave, info in ENTIDADES.items():
        if any(a in t for a in info["aliases"]):
            achados.append(chave)
    return achados


def _detectar_anos(t: str) -> list[int]:
    anos = [int(a) for a in re.findall(r"\b(20\d{2})\b", t)]            # "2025", "2027"
    for q, yy in re.findall(r"\b([1-4])t(\d{2})\b", t):                 # "4t25" -> 2025
        anos.append(2000 + int(yy))
    return sorted(set(anos))


def _detectar_periodos(t: str) -> list[str]:
    """Trimestres citados, no formato do DB ("4t25" -> "4T25"). Usado como FILTRO DE METADADOS
    p/ fixar o documento certo num corpus multi-período. Só TOKEN DE TRIMESTRE (4T25) vira filtro —
    um ano "solto" (ex.: 'guidance para 2026') é ASSUNTO, não o período do documento, e não filtra."""
    vistos = dict.fromkeys(f"{q}T{yy}" for q, yy in re.findall(r"\b([1-4])t(\d{2})\b", t))
    return list(vistos)


def extrair_slots(pergunta: str) -> Slots:
    """Lê a pergunta e preenche os slots por regras léxicas (determinístico, sem modelo)."""
    t = _sem_acento(pergunta)

    if re.search(r"market share|participacao de mercado|\bshare\b", t):
        metrica = "market_share"
    elif re.search(r"custo (do|de) credito|\bpdd\b|provis", t):
        metrica = "custo_credito"
    elif re.search(r"guidance|projec", t):
        metrica = "guidance"
    else:
        metrica = "outra"

    return Slots(
        bancos=_detectar_bancos(t),
        anos=_detectar_anos(t),
        periodos=_detectar_periodos(t),
        metrica=metrica,
        cita_ifdata=bool(re.search(r"if[\s.]?data|bacen", t)),
        declarado=bool(re.search(r"declar|disse|afirm|coment|\bceo\b|telecon|\bcall\b|guidance|estrateg|prometeu", t)),
        confronto=bool(re.search(r"confirm|bate com|\bvs\b|versus|subiu|caiu|aumentou|diminuiu|se confirmou", t)),
        serie=bool(re.search(r"evolu|trajet|ao longo|ultimos|trimestres seguintes|\bserie\b", t)),
        comparacao=bool(re.search(r"\bcompar|\bvs\b|versus|em relacao a", t)),
        pede_verbatim=bool(re.search(r"frase literal|verbatim|cite a frase|transcricao (literal|verbatim)", t)),
    )


# --------------------------------------------------------------------------
# Estágio 1 — gate de escopo (R1/R2/R3). Devolve o MOTIVO da recusa, ou None.
# --------------------------------------------------------------------------

_METRICAS_RELEASE_COSIF = {"guidance", "custo_credito"}  # só existem no release/Cosif


def _gate_escopo(s: Slots) -> str | None:
    # R1 — período futuro/inexistente.
    if s.anos and max(s.anos) > ANO_COBERTURA_MAX:
        return (f"R1: período {max(s.anos)} está além da cobertura da base "
                f"(realizado até 4T25, guidance até {ANO_COBERTURA_MAX}).")

    # R2 — comparação entre bases contábeis incompatíveis (CONJUNÇÃO, nunca só o nome).
    ifrs = [b for b in s.bancos if ENTIDADES[b]["base_contabil"] == "ifrs"]
    if s.comparacao and ifrs and s.metrica in _METRICAS_RELEASE_COSIF:
        return (f"R2: comparação entre bases contábeis incompatíveis (IFRS {ifrs} x Cosif) numa "
                f"métrica de release/Cosif ('{s.metrica}'). Sem base comum -> incomparável.")

    # R3 — citação verbatim de entidade sem transcrição oficial na base.
    if s.pede_verbatim:
        sem_verbatim = [b for b in s.bancos if not ENTIDADES[b]["tem_verbatim"]]
        if sem_verbatim:
            return (f"R3: pedido de citação verbatim de entidade sem transcrição oficial na base "
                    f"({sem_verbatim}). Citar literalmente o que não está na base = inventar.")

    return None


# --------------------------------------------------------------------------
# Estágio 1 (continuação) — classificação do caminho (só se estiver no escopo).
# Precedência: confronto declarado-vs-computado -> número puro -> fato único.
# --------------------------------------------------------------------------

def _classificar_caminho(s: Slots) -> str:
    # multi_fonte: cruza o DECLARADO (texto) com o COMPUTADO/realizado (número).
    if s.confronto and (s.declarado or s.cita_ifdata):
        return "multi_fonte"
    # computada: número/série do IF.data. "market share + evoluiu/série" também é número puro
    # (não temos market share confiável em texto). O `not declarado` desempata o caso Q3:
    # "market share que o CEO DECLAROU" tem 'market share' mas é um fato de TEXTO -> doc_unico.
    if (s.cita_ifdata or (s.metrica == "market_share" and s.serie)) and not s.declarado:
        return "computada"
    return "doc_unico"


# --------------------------------------------------------------------------
# A rota: o que o roteador devolve para o resto do sistema.
# --------------------------------------------------------------------------

@dataclass
class Rota:
    categoria: str                 # uma de CATEGORIAS
    bancos: list[str]              # entidades detectadas (chaves de ENTIDADES)
    anos: list[int]                # anos detectados
    metrica: str                   # rótulo grosso da métrica
    periodos: list[str] = field(default_factory=list)  # trimestres ("4T25") p/ filtro de metadados
    motivo_recusa: str | None = None   # preenchido quando categoria == "nao_respondivel"

    @property
    def deve_recusar(self) -> bool:
        return self.categoria == "nao_respondivel"


def rotear(pergunta: str) -> Rota:
    """Decide o caminho da pergunta: escopo primeiro (recusa cedo), depois o caminho."""
    s = extrair_slots(pergunta)
    motivo = _gate_escopo(s)
    if motivo is not None:
        return Rota("nao_respondivel", s.bancos, s.anos, s.metrica,
                    periodos=s.periodos, motivo_recusa=motivo)
    return Rota(_classificar_caminho(s), s.bancos, s.anos, s.metrica, periodos=s.periodos)
