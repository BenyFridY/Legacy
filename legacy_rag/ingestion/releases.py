"""Ingestão de releases — baixa o PDF da fonte pública e extrai o texto (ADR-0001/0004).

Por que baixar do CDN e não da página de RI?
    As páginas de Relações com Investidores dos bancos respondem **HTTP 403** a um cliente
    programático (anti-robô). Mas o ARQUIVO em si mora num CDN público da plataforma mziq
    (filemanager-cdn.mziq.com / api.mziq.com). Pegamos os bytes direto de lá.

Duas responsabilidades, separadas de propósito:
    baixar(url)            -> bytes do PDF        (toca a REDE; pode falhar/variar no tempo)
    extrair_paginas(bytes) -> [texto por página]  (função PURA; mesmos bytes => mesmo texto)

Guardamos o texto PÁGINA A PÁGINA porque a citação — um não-negociável do case — precisa
apontar "banco X, período Y, documento Z, página N". A página é a âncora da citação; por
isso ela é a unidade que preservamos já na extração (o chunking, no próximo passo, herda).
"""
from __future__ import annotations

import io

import requests
from pypdf import PdfReader

# Mesmo User-Agent identificável que usamos no cliente do Bacen: educado e rastreável.
_HEADERS = {"User-Agent": "LegacyCase/0.1 (research; beny.frid@hashdex.com)"}


def baixar(url: str, timeout: int = 120) -> bytes:
    """Baixa os bytes crus de um PDF público (segue redirecionamento; erro HTTP vira exceção).

    Não interpreta nada: a responsabilidade aqui é só "trazer o arquivo da rede". A separação
    entre baixar (impuro) e extrair (puro) é o que deixa a extração testável sem internet.
    """
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def extrair_paginas(pdf_bytes: bytes) -> list[str]:
    """Texto de cada página do PDF (lista: índice 0 = página 1; índice n-1 = página n).

    Pressuposto: o PDF tem CAMADA DE TEXTO (os releases dos bancos têm — são gerados a partir
    de texto, não escaneados). Um PDF que fosse imagem pura exigiria OCR, o que está fora do
    escopo; se algum dia aparecer, ele se denuncia aqui devolvendo páginas vazias.
    """
    leitor = PdfReader(io.BytesIO(pdf_bytes))
    return [(pagina.extract_text() or "") for pagina in leitor.pages]


def extrair_texto(pdf_bytes: bytes) -> str:
    """Texto do documento inteiro (páginas unidas por quebra dupla — conveniência sobre extrair_paginas)."""
    return "\n\n".join(extrair_paginas(pdf_bytes))
