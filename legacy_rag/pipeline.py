"""Orquestrador — o "maestro" que liga todas as peças numa resposta de ponta a ponta.

    pergunta
       -> ROTEADOR (escopo? caminho?)
          - nao_respondivel -> RECUSA por escopo (Estágio 1), com motivo
          - doc_unico   -> busca híbrida + rerank -> gate de evidência -> geração citada
          - computada   -> market share em SQL (determinístico, auditável) -> resposta citada
          - multi_fonte -> DECLARADO (texto) + COMPUTADO (número) -> LLM reconcilia, cita os dois

Tudo por INJEÇÃO DE DEPENDÊNCIAS (`Dependencias`): a conexão DuckDB, o encoder, o reranker e o
LLM entram de fora. Assim o orquestrador é testável de ponta a ponta com FAKES (sem torch, sem
rede, sem chave) — provamos o FLUXO e as RECUSAS; a qualidade semântica entra com os modelos reais.

Honestidade: o caminho computado depende do mapa banco->cod_inst do Bacen (cadastro em HTTP 500;
ver memória/ADR). Sem o mapa, o caminho computado RECUSA explicando — não inventa um número.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from legacy_rag.config import ENTIDADES, LIMIAR_EVIDENCIA_PADRAO, MODALIDADE_FOCO, ROTULOS_MODALIDADE
from legacy_rag.generation.answer import (
    INSTRUCAO,
    SENTINELA_NAO_ENCONTRADO,
    Resposta,
    responder_de_contexto,
)
from legacy_rag.generation.gate import gate_evidencia
from legacy_rag.retrieval.hibrido import buscar_hibrido
from legacy_rag.retrieval.rerank import rerankar
from legacy_rag.router.router import Rota, rotear
from legacy_rag.structured.store import market_share_conglomerado_serie


def _mapa_prudencial_padrao() -> dict[str, str]:
    """banco -> código do conglomerado prudencial, a partir do config (núcleo verificado)."""
    return {b: info["cod_prudencial"] for b, info in ENTIDADES.items() if info.get("cod_prudencial")}


@dataclass
class Dependencias:
    """As peças concretas que o orquestrador usa. Entram de fora -> testável com fakes."""
    con: object                                   # conexão DuckDB (chunks + carteira_pf + cadastro)
    encoder: object = None                        # Encoder (embeda a pergunta)
    reranker: object = None                       # Reranker (afina o top-k)
    llm: object = None                            # LLMClient (redige)
    mapa_prudencial: dict[str, str] = field(default_factory=_mapa_prudencial_padrao)  # banco -> conglomerado
    modalidade: str = MODALIDADE_FOCO
    limiar: float = LIMIAR_EVIDENCIA_PADRAO
    k: int = 5
    k_multi: int = 10        # multi_fonte confronta 2 fontes -> mais contexto (achar a célula da tabela declarada)
    n_ramo: int = 50


# --------------------------------------------------------------------------
# Ponto de entrada.
# --------------------------------------------------------------------------

def responder(pergunta: str, deps: Dependencias) -> Resposta:
    """Roteia a pergunta e devolve a resposta citada (ou a recusa explicada)."""
    rota = rotear(pergunta)
    if rota.deve_recusar:                                   # Estágio 1: recusa por escopo
        return Resposta(texto="Não disponível na base.", recusou=True, motivo=rota.motivo_recusa)
    if rota.categoria == "computada":
        return _caminho_computado(rota, deps)
    if rota.categoria == "multi_fonte":
        return _caminho_multi(pergunta, rota, deps)
    return _caminho_texto(pergunta, rota, deps)             # doc_unico (default)


# --------------------------------------------------------------------------
# Caminho do TEXTO (doc_unico): busca híbrida -> rerank -> gate -> geração citada.
# --------------------------------------------------------------------------

def _buscar_texto(pergunta: str, rota: Rota, deps: Dependencias, k: int | None = None):
    k = deps.k if k is None else k                                # multi_fonte passa um k maior (k=0 é respeitado)
    query_vec = deps.encoder.encode([pergunta])[0]
    banco = rota.bancos[0] if len(rota.bancos) == 1 else None     # pré-filtro só se houver 1 banco
    periodo = rota.periodos[0] if len(rota.periodos) == 1 else None  # e só se houver 1 trimestre (ex.: "4T25")
    # Filtro de metadados (banco + período) fixa o DOCUMENTO certo num corpus multi-período: sem ele,
    # a página de consignado do 3T25 compete com a do 4T25. Ver ADR-0005 (retrieval ciente de período).
    res = buscar_hibrido(deps.con, pergunta, query_vec, k=k, n_ramo=deps.n_ramo, banco=banco, periodo=periodo)
    if deps.reranker is not None:
        res = rerankar(pergunta, res, deps.reranker, top_k=k)
    return res


def _caminho_texto(pergunta: str, rota: Rota, deps: Dependencias) -> Resposta:
    return responder_de_contexto(pergunta, _buscar_texto(pergunta, rota, deps), deps.llm, deps.limiar)


# --------------------------------------------------------------------------
# Caminho dos NÚMEROS (computada): market share em SQL, determinístico e auditável.
# --------------------------------------------------------------------------

def _rotulo(modalidade: str) -> str:
    """Apelido legível da modalidade p/ exibição (o nome técnico do Bacen vira 'consignado')."""
    return ROTULOS_MODALIDADE.get(modalidade, modalidade)


def _citacao_ifdata(modalidade: str) -> str:
    return (f"Bacen IF.data, modalidade={_rotulo(modalidade)} ({modalidade}), "
            f"market share = carteira / Σ sistema (calc. em SQL)")


def _formatar_serie(banco: str, modalidade: str, serie: list[tuple[int, float]]) -> str:
    pontos = ", ".join(f"{am // 100}-{am % 100:02d}: {sh * 100:.1f}%" for am, sh in serie)
    ini, fim = serie[0][1] * 100, serie[-1][1] * 100
    tend = "estável" if abs(fim - ini) < 0.1 else ("alta" if fim > ini else "queda")
    return (f"Market share de {banco} em {_rotulo(modalidade)}: {pontos}. "
            f"Variação no período: {ini:.1f}% -> {fim:.1f}% ({tend}).")


def _computar_serie(rota: Rota, deps: Dependencias):
    """Devolve (banco, série) ou None se não dá p/ computar (sem banco único / sem conglomerado / sem dado).

    Usa o share por CONGLOMERADO prudencial (soma os CNPJs do banco) — o share "por banco" correto.
    """
    if len(rota.bancos) != 1:
        return None
    banco = rota.bancos[0]
    prud = deps.mapa_prudencial.get(banco)
    if not prud:
        return None
    serie = market_share_conglomerado_serie(deps.con, prud, deps.modalidade)
    return (banco, serie) if serie else None


def _caminho_computado(rota: Rota, deps: Dependencias) -> Resposta:
    computado = _computar_serie(rota, deps)
    if computado is None:
        return Resposta(texto="Não disponível na base.", recusou=True,
                        motivo="market share não computável (banco único? conglomerado mapeado? série na base?).")
    banco, serie = computado
    return Resposta(texto=_formatar_serie(banco, deps.modalidade, serie),
                    citacoes=[_citacao_ifdata(deps.modalidade)])


# --------------------------------------------------------------------------
# Caminho MULTI-FONTE (B3): cruza o DECLARADO (texto) com o COMPUTADO (número).
# --------------------------------------------------------------------------

def _caminho_multi(pergunta: str, rota: Rota, deps: Dependencias) -> Resposta:
    resultados = _buscar_texto(pergunta, rota, deps, k=deps.k_multi)
    tem_texto = gate_evidencia(resultados, deps.limiar).responder
    computado = _computar_serie(rota, deps)

    if not tem_texto and computado is None:                 # nem declarado nem computado -> recusa
        return Resposta(texto="Não disponível na base.", recusou=True,
                        motivo="sem evidência no caminho declarado (texto) nem no computado (IF.data).")

    blocos, citacoes = [], []
    if tem_texto:
        for i, r in enumerate(resultados, 1):
            blocos.append(f"[T{i}] ({r.citacao})\n{r.texto}")
            citacoes.append(r.citacao)
    if computado is not None:
        banco, serie = computado
        cit = _citacao_ifdata(deps.modalidade)
        blocos.append(f"[N1] ({cit})\n{_formatar_serie(banco, deps.modalidade, serie)}")
        citacoes.append(cit)

    contexto = "\n\n".join(blocos)
    evidencias = Resposta(texto="Evidências para comparação (declarado x computado):\n" + contexto,
                          citacoes=citacoes)
    # Sem LLM (fallback determinístico): devolve as duas evidências lado a lado, já citadas.
    if deps.llm is None:
        return evidencias

    prompt = (f"{INSTRUCAO}\n\nCONTEXTO (T = declarado no texto; N = computado do IF.data):\n"
              f"{contexto}\n\nPERGUNTA: {pergunta}\n\nRESPOSTA:")
    saida = deps.llm.completar(prompt).strip()
    # Se o LLM não narrou a reconciliação (ex.: figura declarada numa CÉLULA de tabela sem cabeçalho
    # no chunk -> ele não inventa), NÃO recusamos: temos as duas evidências citadas -> mostramos lado a
    # lado p/ o analista comparar. Honesto (não fabrica o número) e útil (não vira recusa). Ver ADR-0005.
    if SENTINELA_NAO_ENCONTRADO in saida.upper():
        return evidencias
    return Resposta(texto=saida, citacoes=citacoes)
