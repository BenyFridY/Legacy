"""Carregador minimalista de .env — sem dependencia externa (evita puxar python-dotenv).

Le pares KEY=VALUE de um arquivo .env (gitignored) e popula os.environ, SEM sobrescrever
variaveis ja definidas no ambiente (precedencia: ambiente real > .env). Linhas em branco e
comentarios (#) sao ignorados; aspas ao redor do valor sao removidas. Assim o usuario so cola
a GROQ_API_KEY no .env e qualquer entrypoint que chame carregar_dotenv() a enxerga.
"""
from __future__ import annotations

import os
from pathlib import Path

from legacy_rag.config import ROOT


def carregar_dotenv(caminho: str | Path = ROOT / ".env") -> dict[str, str]:
    """Le o .env e injeta em os.environ (sem sobrescrever o que ja existe). Devolve o que leu."""
    p = Path(caminho)
    lidos: dict[str, str] = {}
    if not p.exists():
        return lidos
    for linha in p.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
        lidos[chave] = valor
        os.environ.setdefault(chave, valor)        # ambiente real tem precedencia
    return lidos
