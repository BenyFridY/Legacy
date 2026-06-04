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
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ALVO_CHARS = 1200     # tamanho-alvo da ficha (~300 tokens, a ~4 chars/token)
OVERLAP_CHARS = 200   # sobreposição entre fichas vizinhas (~50 tokens)


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


def _empacotar(unidades: list[str], alvo: int, overlap: int) -> list[str]:
    """Agrupa unidades em fichas de ~alvo chars, com sobreposição, sem nunca partir uma unidade."""
    fichas: list[str] = []
    atual: list[str] = []
    tam = 0
    for u in unidades:
        if atual and tam + len(u) + 1 > alvo:           # encheu: fecha a ficha atual
            fichas.append(" ".join(atual))
            carry: list[str] = []                        # monta o overlap p/ a próxima ficha
            ctam = 0
            for x in reversed(atual):                    # últimas unidades, até ~overlap chars
                if carry and ctam + len(x) > overlap:
                    break
                carry.insert(0, x)
                ctam += len(x) + 1
            atual = carry
            tam = sum(len(x) + 1 for x in atual)
        atual.append(u)
        tam += len(u) + 1
    if atual:
        fichas.append(" ".join(atual))
    return fichas


def chunkar_documento(paginas: list[str], banco: str, periodo: str, tipo_doc: str,
                      alvo: int = ALVO_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    """Recorta um documento (lista de páginas, índice 0 = pág. 1) em fichas com metadados de citação."""
    chunks: list[Chunk] = []
    for i, texto_pag in enumerate(paginas, start=1):
        for j, ficha in enumerate(_empacotar(_unidades(texto_pag), alvo, overlap)):
            chunks.append(Chunk(banco, periodo, tipo_doc, i, j, ficha))
    return chunks
