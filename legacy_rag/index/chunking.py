"""Chunking — recorta o texto extraído em 'fichas' pequenas e buscáveis (caminho do texto).

Por que NÃO cortar em pedaços de tamanho fixo (a forma ingênua)? Porque isso parte uma
TABELA no meio (separando o número do seu rótulo) ou uma fala do CEO no meio da frase — e
são justamente esses trechos que as perguntas do case (B1/B3 tabelas, B2/B3 falas) precisam.

Decisões (defensáveis na apresentação):
1. A PÁGINA é a fronteira. Cada ficha vive dentro de UMA página, porque a página é a âncora
   da citação (não-negociável do case). Nunca juntamos texto de páginas diferentes numa ficha.
2. Dentro da página, empacotamos em fichas de ~ALVO caracteres, sempre quebrando em fim de
   frase/linha — NUNCA no meio de uma frase. Fichas vizinhas têm uma pequena SOBREPOSIÇÃO
   (overlap), pra uma ideia que cai bem na divisa não se perder.
3. Cada ficha carrega um CABEÇALHO de metadados (banco | período | tipo | página). Esse
   cabeçalho entra no texto que vai para a BUSCA (ajuda o casamento por embedding/BM25); os
   mesmos campos ficam guardados à parte para FILTRAR e CITAR. O texto CRU (sem cabeçalho) é
   o que se mostra na citação.
4. Chunking CIENTE DE TABELA. O overlap assume semântica de PROSA (contexto = o que veio logo
   antes); numa tabela o contexto é a linha de CABEÇALHO das colunas ("R$ milhões 4T25 3T25
   4T24..."). Quando uma tabela densa estoura o alvo e quebra em 2+ fichas, a continuação
   ficava com números órfãos de rótulo de coluna — o LLM (corretamente) não os lia. O fix:
   toda ficha que tem linha de DADOS de tabela mas nenhum cabeçalho de colunas ganha,
   re-prefixado, o cabeçalho MAIS PRÓXIMO da mesma página (mais próximo, e não "o anterior",
   porque o pypdf emite o texto na ordem do stream do PDF — o cabeçalho às vezes sai DEPOIS
   das linhas de dado). É a regra do Excel: repetir a linha de título em cada página impressa.
   Tudo heurístico e conservador: detecção por rótulos de período (4T25, Dez24, 12M25...) e
   densidade de números; sem cabeçalho detectável na página (gráficos, texto fundido), nada
   muda. O cabeçalho repetido é texto VERBATIM da mesma página — a citação segue honesta.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ALVO_CHARS = 1200     # tamanho-alvo da ficha (~300 tokens, a ~4 chars/token)
OVERLAP_CHARS = 200   # sobreposição entre fichas vizinhas (~50 tokens)

# Rótulos de período no formato dos releases: 4T25, 12M25, Dez25/Set24, 2024. Nos meses, a
# borda esquerda aceita DÍGITO ("Set24Jun25" — a extração funde tokens vizinhos; \b falharia
# em dígito->letra) mas bloqueia minúscula ("previdenciaJun" não é rótulo de período).
_RE_PERIODO = re.compile(
    r"\b[1-4][Tt]\d{2}\b"
    r"|\b(?:3|6|9|12)[Mm]\d{2}\b"
    r"|(?<![a-zà-öø-ÿ])(?:Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez)\.?/?\d{2}(?!\d)"
    r"|\b(?:19|20)\d{2}\b")

# Número "de tabela": decimal com vírgula (14,1 / (2,9) / 8,4%) ou inteiro com pontos de
# milhar (83.337 / 1.089.230). Ano solto ("2024") de propósito NÃO conta — prosa tem ano.
_RE_NUMERO_TABELA = re.compile(r"\(?\d[\d.]*,\d+\)?%?|\(?\d{1,3}(?:\.\d{3})+\)?")

_MAX_CHARS_CABECALHO = 300   # cabeçalho gigante (linha de título+dados fundida) não é re-prefixável


def _parece_cabecalho_de_tabela(u: str) -> bool:
    """Linha de cabeçalho de colunas: ≥2 rótulos de período, sem pontuação final de frase."""
    return (len(u) <= _MAX_CHARS_CABECALHO
            and u.rstrip()[-1:] not in ".!?;"
            and len(_RE_PERIODO.findall(u)) >= 2)


def _parece_linha_de_tabela(u: str) -> bool:
    """Linha de DADOS de tabela: ≥3 números 'de tabela', sem pontuação final de frase."""
    return u.rstrip()[-1:] not in ".!?;" and len(_RE_NUMERO_TABELA.findall(u)) >= 3


@dataclass
class Chunk:
    """Uma ficha: a unidade de BUSCA e de CITAÇÃO."""
    banco: str
    periodo: str
    tipo_doc: str
    pagina: int      # 1 = primeira página (âncora da citação)
    ordinal: int     # posição da ficha dentro da página (0, 1, 2, ...)
    texto: str       # texto CRU do trecho (o que aparece na citação)

    @property
    def cabecalho(self) -> str:
        return f"[banco={self.banco} | período={self.periodo} | tipo={self.tipo_doc} | pág.{self.pagina}]"

    @property
    def indexavel(self) -> str:
        """O que vai para embedding/BM25: cabeçalho de metadados + trecho cru."""
        return f"{self.cabecalho}\n{self.texto}"


def _unidades(texto: str) -> list[str]:
    """Quebra o texto em unidades indivisíveis (frases/linhas) — não cortamos abaixo disto."""
    partes = re.split(r"(?<=[.!?])\s+|\n+", texto.strip())
    return [p.strip() for p in partes if p.strip()]


def _empacotar(unidades: list[str], alvo: int, overlap: int) -> list[list[int]]:
    """Agrupa unidades em fichas de ~alvo chars, com sobreposição, sem nunca partir uma unidade.

    Devolve ÍNDICES (posições em `unidades`), não textos: o pós-passe de tabela precisa saber
    ONDE na página cada ficha mora para achar o cabeçalho mais próximo.
    """
    fichas: list[list[int]] = []
    atual: list[int] = []
    tam = 0
    for i, u in enumerate(unidades):
        if atual and tam + len(u) + 1 > alvo:           # encheu: fecha a ficha atual
            fichas.append(atual)
            carry: list[int] = []                        # monta o overlap p/ a próxima ficha
            ctam = 0
            for j in reversed(atual):                    # últimas unidades, até ~overlap chars
                if carry and ctam + len(unidades[j]) > overlap:
                    break
                carry.insert(0, j)
                ctam += len(unidades[j]) + 1
            atual = list(carry)
            tam = sum(len(unidades[j]) + 1 for j in atual)
        atual.append(i)
        tam += len(u) + 1
    if atual:
        fichas.append(atual)
    return fichas


def _montar_fichas(unidades: list[str], fichas_idx: list[list[int]]) -> list[str]:
    """Índices -> textos, re-prefixando o cabeçalho de tabela nas fichas ÓRFÃS (decisão 4).

    Órfã = tem linha de DADOS de tabela mas nenhum cabeçalho de colunas. Ganha o cabeçalho
    mais próximo da página (distância em unidades); página sem cabeçalho detectável = no-op.
    """
    cabecalhos = [i for i, u in enumerate(unidades) if _parece_cabecalho_de_tabela(u)]
    textos: list[str] = []
    for idx in fichas_idx:
        unids = [unidades[j] for j in idx]
        orfa = (any(_parece_linha_de_tabela(u) for u in unids)
                and not any(_parece_cabecalho_de_tabela(u) for u in unids))
        if orfa and cabecalhos:
            mais_perto = min(cabecalhos, key=lambda c: min(abs(c - j) for j in idx))
            unids.insert(0, unidades[mais_perto])
        textos.append(" ".join(unids))
    return textos


def chunkar_documento(paginas: list[str], banco: str, periodo: str, tipo_doc: str,
                      alvo: int = ALVO_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    """Recorta um documento (lista de páginas, índice 0 = pág. 1) em fichas com metadados de citação."""
    chunks: list[Chunk] = []
    for i, texto_pag in enumerate(paginas, start=1):
        unidades = _unidades(texto_pag)
        for j, ficha in enumerate(_montar_fichas(unidades, _empacotar(unidades, alvo, overlap))):
            chunks.append(Chunk(banco, periodo, tipo_doc, i, j, ficha))
    return chunks
