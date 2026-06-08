"""Orquestrador — o "maestro" que liga todas as peças numa resposta de ponta a ponta.

    pergunta
       -> ROTEADOR (escopo? caminho?)
          - nao_respondivel -> RECUSA por escopo (Estágio 1), com motivo
          - doc_unico   -> busca híbrida + rerank -> gate de evidência -> geração citada
          - computada   -> market share em SQL (determinístico, auditável) -> resposta citada
          - comparativo -> market share de 2+ bancos comparado (cross-bank), tudo em SQL
          - multi_fonte -> DECLARADO (texto) + COMPUTADO (número) -> LLM reconcilia, cita os dois

Tudo por INJEÇÃO DE DEPENDÊNCIAS (`Dependencias`): a conexão DuckDB, o encoder, o reranker e o
LLM entram de fora. Assim o orquestrador é testável de ponta a ponta com FAKES (sem torch, sem
rede, sem chave) — provamos o FLUXO e as RECUSAS; a qualidade semântica entra com os modelos reais.

Honestidade: o caminho computado usa o mapa banco->conglomerado prudencial do config (4 bancos do
núcleo com cod_prudencial verificado ao vivo no IfDataCadastro, AnoMes=202412) e calcula a série de
market share em SQL — a fonte está acessível (HTTP 200; ver bacen.cadastro_conglomerado). Se uma
fonte cair ou um banco não tiver conglomerado mapeado, o caminho RECUSA explicando, em vez de
inventar um número (e o cadastro degrada para {} mantendo o cálculo por CodInst cru).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from legacy_rag.config import ANO_COBERTURA_MAX, ENTIDADES, LIMIAR_EVIDENCIA_PADRAO, ROTULOS_MODALIDADE
from legacy_rag.generation.answer import (
    INSTRUCAO_MULTI,
    SENTINELA_NAO_ENCONTRADO,
    Resposta,
    responder_de_contexto,
)
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
    limiar: float = LIMIAR_EVIDENCIA_PADRAO
    k: int = 5               # top-k FINAL que a resposta usa (o que o usuário vê)
    k_rerank: int = 10       # candidatos que o reranker ENXERGA: funde um pool maior, afina, devolve top-k (ADR-0005)
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
    if rota.categoria == "comparativo":
        return _caminho_comparativo(rota, deps)
    if rota.categoria == "multi_fonte":
        return _caminho_multi(pergunta, rota, deps)
    return _caminho_texto(pergunta, rota, deps)             # doc_unico (default)


# --------------------------------------------------------------------------
# Caminho do TEXTO (doc_unico): busca híbrida -> rerank -> gate -> geração citada.
# --------------------------------------------------------------------------

def _buscar_texto(pergunta: str, rota: Rota, deps: Dependencias, k: int | None = None):
    k = deps.k if k is None else k                                # top-k FINAL (o que a resposta usa)
    pool = max(k, deps.k_rerank)                                  # funde um pool maior p/ o reranker afinar
    query_vec = deps.encoder.encode([pergunta])[0]
    banco = rota.bancos[0] if len(rota.bancos) == 1 else None     # pré-filtro só se houver 1 banco
    periodo = rota.periodos[0] if len(rota.periodos) == 1 else None  # e só se houver 1 trimestre (ex.: "4T25")
    # Filtro de metadados (banco + período) fixa o DOCUMENTO certo num corpus multi-período: sem ele,
    # a página de consignado do 3T25 compete com a do 4T25. Ver ADR-0005 (retrieval ciente de período).
    res = buscar_hibrido(deps.con, pergunta, query_vec, k=pool, n_ramo=deps.n_ramo, banco=banco, periodo=periodo)
    if deps.reranker is not None:
        res = rerankar(pergunta, res, deps.reranker, top_k=k)     # cross-encoder vê `pool`, devolve os `k` melhores
    return res


_MARCA_VALOR = re.compile(r"\s*(?:mil|milh|bilh|tri|%)", re.IGNORECASE)  # "2027 milhões", "2027%" -> é VALOR


def _documenta_ano(texto: str, ano: int) -> bool:
    """O trecho menciona `ano` como ANO (referência temporal) — não como CÓDIGO nem VALOR monetário?

    Evita falsos positivos do substring ingênuo: '2027' dentro de 'C0052027' (sem fronteira de palavra),
    de 'R$ 2027 milhões' (precedido por R$) ou de '2027 milhões' (seguido de magnitude). Conservador:
    na dúvida (ex.: precedido por dígito/cifrão ou seguido de 'milhões'), NÃO conta como ano.
    """
    for m in re.finditer(rf"\b{ano}\b", texto):            # \b já descarta '2027' dentro de 'C0052027'
        antes = texto[max(0, m.start() - 3):m.start()].replace(" ", "").lower()
        if antes.endswith(("r$", "$")):                    # R$ 2027 -> valor, não ano
            continue
        if _MARCA_VALOR.match(texto[m.end():m.end() + 12].lower()):  # 2027 milhões/% -> valor
            continue
        return True
    return False


def _aterrar_ano_futuro(rota: Rota, resultados, limiar: float) -> str | None:
    """Trava de aterramento p/ ANO FUTURO documentado (ADR-0005). Se a pergunta cita um ano além da
    cobertura, só deixamos responder quando um trecho RELEVANTE (acima do gate) menciona esse ano
    COMO ANO (não como código/valor — ver `_documenta_ano`) — ex.: vencimento de dívida, vigência de
    norma. Senão, recusa: impede inferir um VALOR futuro a partir de um trecho de outro período.
    Não dispara se a pergunta não cita ano futuro."""
    anos_fut = [a for a in rota.anos if a > ANO_COBERTURA_MAX]
    if not anos_fut:
        return None
    relevantes = [r for r in resultados if r.score >= limiar]
    if not relevantes:
        return None                      # sem evidência forte: o gate normal recusa (motivo mais preciso)
    if any(_documenta_ano(r.texto, a) for r in relevantes for a in anos_fut):
        return None                      # aterrado: há trecho relevante documentando o ano -> responde
    return (f"R1-evidência: a pergunta cita {max(anos_fut)} (além de {ANO_COBERTURA_MAX}); nenhum trecho "
            f"recuperado documenta esse período -> recuso em vez de inferir o futuro.")


def _caminho_texto(pergunta: str, rota: Rota, deps: Dependencias) -> Resposta:
    resultados = _buscar_texto(pergunta, rota, deps)
    motivo = _aterrar_ano_futuro(rota, resultados, deps.limiar)
    if motivo is not None:
        return Resposta(texto="Não disponível na base.", recusou=True, motivo=motivo)
    return responder_de_contexto(pergunta, resultados, deps.llm, deps.limiar)


# --------------------------------------------------------------------------
# Caminho dos NÚMEROS (computada): market share em SQL, determinístico e auditável.
# --------------------------------------------------------------------------

_TRIM_MES = {"1": 3, "2": 6, "3": 9, "4": 12}   # trimestre -> mês de fechamento (IF.data é trimestral)


def _periodo_para_am(periodo: str) -> int | None:
    """'4T25' -> 202512 ; '3T25' -> 202509. Devolve None se não for token de trimestre."""
    m = re.fullmatch(r"([1-4])T(\d{2})", periodo)
    return (2000 + int(m.group(2))) * 100 + _TRIM_MES[m.group(1)] if m else None


def _janela_da_rota(rota: Rota) -> tuple[int | None, int | None]:
    """Janela (am_ini, am_fim) em YYYYMM p/ RECORTAR a série no caminho de números, vinda da pergunta.

    Precedência: trimestre explícito ('4T25') manda; senão ano(s) ('2024' -> ano inteiro 202401-202412;
    '2023 a 2025' -> 202301-202512); senão sem recorte (série inteira). É o que faz "...de 2023 a 2024"
    e "...de 2024 a 2025" darem respostas DIFERENTES (antes os anos eram decorativos). Ver ADR-0005.
    """
    ams = [a for a in (_periodo_para_am(p) for p in rota.periodos) if a is not None]
    if ams:
        return (min(ams), max(ams))
    if rota.anos:
        return (min(rota.anos) * 100 + 1, max(rota.anos) * 100 + 12)
    return (None, None)


def _rotulo(modalidade: str) -> str:
    """Apelido legível da modalidade p/ exibição (o nome técnico do Bacen vira 'consignado')."""
    return ROTULOS_MODALIDADE.get(modalidade, modalidade)


def _citacao_ifdata(modalidade: str) -> str:
    return (f"Bacen IF.data, modalidade={_rotulo(modalidade)} ({modalidade}), "
            f"market share = carteira / Σ sistema (calc. em SQL)")


def _formatar_serie(banco: str, modalidade: str, serie: list[tuple[int, float]]) -> str:
    pontos = ", ".join(f"{am // 100}-{am % 100:02d}: {sh * 100:.1f}%" for am, sh in serie)
    ini, fim = serie[0][1] * 100, serie[-1][1] * 100
    am0, amN = serie[0][0], serie[-1][0]                       # nomeia o intervalo REAL coberto
    janela = f"{am0 // 100}-{am0 % 100:02d} a {amN // 100}-{amN % 100:02d}"
    tend = "estável" if abs(fim - ini) < 0.1 else ("alta" if fim > ini else "queda")
    return (f"Market share de {banco} em {_rotulo(modalidade)}: {pontos}. "
            f"Variação ({janela}): {ini:.1f}% -> {fim:.1f}% ({tend}).")


def _computar_serie(rota: Rota, deps: Dependencias, am_ini: int | None = None, am_fim: int | None = None):
    """Devolve (banco, série) ou None se não dá p/ computar (sem banco único / sem conglomerado / sem dado).

    Usa o share por CONGLOMERADO prudencial (soma os CNPJs do banco) — o share "por banco" correto.
    `am_ini`/`am_fim` recortam a janela (vinda de _janela_da_rota); sem janela, série inteira.
    """
    if len(rota.bancos) != 1:
        return None
    banco = rota.bancos[0]
    prud = deps.mapa_prudencial.get(banco)
    if not prud:
        return None
    serie = market_share_conglomerado_serie(deps.con, prud, rota.modalidade, am_ini, am_fim)
    return (banco, serie) if serie else None


def _caminho_computado(rota: Rota, deps: Dependencias) -> Resposta:
    am_ini, am_fim = _janela_da_rota(rota)                     # recorta pela janela pedida na pergunta
    computado = _computar_serie(rota, deps, am_ini, am_fim)
    if computado is None:
        return Resposta(texto="Não disponível na base.", recusou=True,
                        motivo="market share não computável (banco único? conglomerado mapeado? "
                               "série na base na janela pedida?).")
    banco, serie = computado
    return Resposta(texto=_formatar_serie(banco, rota.modalidade, serie),
                    citacoes=[_citacao_ifdata(rota.modalidade)])


# --------------------------------------------------------------------------
# Caminho COMPARATIVO (cross-bank): compara o market share de 2+ bancos, tudo em SQL.
# --------------------------------------------------------------------------

_TOL_EMPATE_PP = 0.05   # diferença de variação abaixo disto (p.p.) = empate (não elege líder arbitrário)


def _caminho_comparativo(rota: Rota, deps: Dependencias) -> Resposta:
    """Compara o market share de 2+ bancos (SQL), alinhando-os pela MESMA janela de período.

    Correções (ADR-0005): (1) recorta pela janela pedida na pergunta (_janela_da_rota) — "...de 2023 a
    2024" e "...de 2024 a 2025" deixam de dar a mesma resposta; (2) mede a variação de todos sobre os
    trimestres COMUNS (interseção), não sobre os extremos próprios de cada um (antes era maçã x laranja);
    (3) QUANTIFICA o quanto o líder ganhou A MAIS (p.p.) e trata EMPATE sem eleger líder arbitrário.
    Recusa honesta se < 2 bancos computáveis, ou se não houver trimestre comum a todos.
    """
    am_ini, am_fim = _janela_da_rota(rota)
    series = []
    for banco in rota.bancos:
        prud = deps.mapa_prudencial.get(banco)
        if not prud:
            continue
        s = market_share_conglomerado_serie(deps.con, prud, rota.modalidade, am_ini, am_fim)
        if s:
            series.append((banco, dict(s)))                   # {ano_mes: share}
    if len(series) < 2:
        return Resposta(texto="Não disponível na base.", recusou=True,
                        motivo="comparação cross-bank exige série de ao menos 2 bancos "
                               "(conglomerado mapeado? série na base na janela pedida?).")
    comuns = sorted(set.intersection(*[set(d) for _, d in series]))   # trimestres comuns a TODOS
    if not comuns:
        return Resposta(texto="Não disponível na base.", recusou=True,
                        motivo="os bancos não têm nenhum trimestre em comum na janela pedida -> incomparável.")
    am0, amN = comuns[0], comuns[-1]
    cit = [_citacao_ifdata(rota.modalidade)]

    if am0 == amN:                                            # uma única foto comum -> compara NÍVEIS
        janela = f"{am0 // 100}-{am0 % 100:02d}"
        niveis = sorted(((b, d[am0] * 100) for b, d in series), key=lambda x: x[1], reverse=True)
        corpo = "; ".join(f"{b}: {v:.1f}%" for b, v in niveis)
        gap = niveis[0][1] - niveis[1][1]
        veredito = (f"Maior participação em {janela}: {niveis[0][0]} (+{gap:.1f} p.p. acima de {niveis[1][0]})."
                    if gap >= _TOL_EMPATE_PP else f"Empate técnico entre {niveis[0][0]} e {niveis[1][0]}.")
        resumo = (f"Market share em {_rotulo(rota.modalidade)} ({janela}, Bacen IF.data, calc. em SQL) — "
                  f"{corpo}. {veredito}")
        return Resposta(texto=resumo, citacoes=cit)

    # janela com >=2 trimestres comuns -> compara a VARIAÇÃO sobre os MESMOS extremos (am0 -> amN)
    janela = f"{am0 // 100}-{am0 % 100:02d} a {amN // 100}-{amN % 100:02d}"
    detalhes = sorted(((b, d[amN] * 100 - d[am0] * 100, d[am0] * 100, d[amN] * 100) for b, d in series),
                      key=lambda x: x[1], reverse=True)        # (banco, delta_pp, ini, fim), maior variação 1º
    corpo = "; ".join(f"{b}: {ini:.1f}% -> {fim:.1f}% ({dl:+.1f} p.p.)" for b, dl, ini, fim in detalhes)
    (lider, d_lider, _, _), (segundo, d_seg, _, _) = detalhes[0], detalhes[1]
    if abs(d_lider - d_seg) < _TOL_EMPATE_PP:
        veredito = f"Variação equivalente no período entre {lider} e {segundo} (diferença < {_TOL_EMPATE_PP:.2f} p.p.)."
    else:
        verbo = "ganhou mais" if d_lider > 0 else "perdeu menos"
        veredito = f"Quem {verbo} participação: {lider} ({d_lider - d_seg:+.1f} p.p. a mais que {segundo})."
    resumo = (f"Market share em {_rotulo(rota.modalidade)} ({janela}, Bacen IF.data, calc. em SQL) — "
              f"{corpo}. {veredito}")
    return Resposta(texto=resumo, citacoes=cit)


# --------------------------------------------------------------------------
# Caminho MULTI-FONTE (B3): cruza o DECLARADO (texto) com o COMPUTADO (número).
# --------------------------------------------------------------------------

def _curto(texto: str, n: int = 320) -> str:
    """Trecho curto p/ EXIBIR no fallback de evidências (o LLM ainda recebe o texto completo)."""
    return texto if len(texto) <= n else texto[:n].rsplit(" ", 1)[0] + " [...]"


def _caminho_multi(pergunta: str, rota: Rota, deps: Dependencias) -> Resposta:
    resultados = _buscar_texto(pergunta, rota, deps, k=deps.k_multi)
    # Trava de ANO FUTURO também aqui (não só no texto): se a pergunta cita ano além da cobertura e
    # nenhum trecho relevante o documenta, recusa em vez de deixar o LLM inferir um valor futuro a
    # partir de evidência de outro período (a brecha era metrica='outra', que escapa do R1). Ver ADR-0005.
    motivo = _aterrar_ano_futuro(rota, resultados, deps.limiar)
    if motivo is not None:
        return Resposta(texto="Não disponível na base.", recusou=True, motivo=motivo)
    # Só os trechos que PASSAM o gate de evidência entram no confronto. Sem esse filtro, as ~10 páginas
    # recuperadas (incl. parecer de auditoria, nota de hedge, IFRS) viram um paredão que afoga o sinal e
    # faz o LLM desistir -> caía no "despejo" de tudo. Filtrar deixa o contexto enxuto, citável e o LLM
    # reconcilia (declarado x computado) em vez de devolver evidência crua. Ver ADR-0005.
    relevantes = [r for r in resultados if r.score >= deps.limiar]
    tem_texto = len(relevantes) > 0
    # O caminho SQL só sabe computar MARKET SHARE. Numa pergunta de custo de crédito/guidance (B1),
    # anexar a série de share de consignado seria evidência ENGANOSA -> só computa quando a métrica é share.
    # Alinha pela MESMA janela de período do lado declarado (ex.: declarado no 4T25 -> computa no 4T25).
    am_ini, am_fim = _janela_da_rota(rota)
    computado = _computar_serie(rota, deps, am_ini, am_fim) if rota.metrica == "market_share" else None

    if not tem_texto and computado is None:                 # nem declarado nem computado -> recusa
        return Resposta(texto="Não disponível na base.", recusou=True,
                        motivo="sem evidência no caminho declarado (texto) nem no computado (IF.data).")

    partes, citacoes = [], []            # partes = (rótulo, citação, texto): full p/ o LLM, truncado p/ exibir
    if tem_texto:
        for i, r in enumerate(relevantes, 1):
            partes.append((f"T{i}", r.citacao, r.texto))
            citacoes.append(r.citacao)
    if computado is not None:
        banco, serie = computado
        cit = _citacao_ifdata(rota.modalidade)
        partes.append(("N1", cit, _formatar_serie(banco, rota.modalidade, serie)))
        citacoes.append(cit)

    # Cabeçalho HONESTO: nomeia só os lados que de fato entraram (não promete 'x computado' se só há texto).
    if tem_texto and computado is not None:
        cabecalho = "Evidências para comparação (declarado x computado):"
    elif tem_texto:
        cabecalho = "Evidências (declarado; sem série computável do IF.data para esta métrica):"
    else:
        cabecalho = "Evidências (computado do IF.data; sem trecho declarado relevante na base):"

    contexto = "\n\n".join(f"[{tag}] ({cit})\n{txt}" for tag, cit, txt in partes)   # full p/ o LLM
    evidencias = Resposta(texto=cabecalho + "\n" + "\n\n".join(           # truncado p/ não virar paredão
        f"[{tag}] ({cit})\n{_curto(txt)}" for tag, cit, txt in partes), citacoes=citacoes)
    # Só COMPUTADO (nenhum trecho declarado passou o gate): o número do IF.data já é determinístico e
    # citado — devolvemos a evidência direto, SEM o LLM. A INSTRUCAO_MULTI pede "cite o lado declarado",
    # mas aqui o único número declarado visível estaria na PERGUNTA -> o LLM poderia ecoá-lo como fato.
    # Pular o LLM neste ramo elimina esse risco de eco/injeção. Ver ADR-0005.
    if computado is not None and not tem_texto:
        return evidencias
    # Sem LLM (fallback determinístico): devolve as evidências (já citadas) lado a lado.
    if deps.llm is None:
        return evidencias

    prompt = (f"{INSTRUCAO_MULTI}\n\nEVIDÊNCIAS (T = declarado no texto; N = computado do IF.data):\n"
              f"{contexto}\n\nPERGUNTA: {pergunta}\n\nRESPOSTA:")
    saida = deps.llm.completar(prompt).strip()
    # Se mesmo assim o LLM não reconciliar (devolve o sentinela), NÃO recusamos: mostramos as duas
    # evidências citadas lado a lado p/ o analista comparar. Honesto (não inventa) e útil. Ver ADR-0005.
    if SENTINELA_NAO_ENCONTRADO in saida.upper():
        return evidencias
    return Resposta(texto=saida, citacoes=citacoes)
