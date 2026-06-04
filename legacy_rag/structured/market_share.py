"""Cálculo de market share — caminho dos números (ADR-0001).

market_share de um banco numa modalidade = carteira do banco ÷ carteira do sistema (soma de
todos), no mesmo período. É uma razão (a unidade do saldo cancela), determinística e auditável
por re-execução. Funções puras — testáveis sem rede.
"""
from __future__ import annotations

from collections.abc import Mapping


def market_share(saldos: Mapping[str, float], cod_inst: str) -> float | None:
    """Fatia do `cod_inst` no total do sistema. `saldos` = {cod_inst: saldo} da modalidade/período.

    Retorna None se o banco não está na base ou o total é zero — sinaliza o caminho de RECUSA
    (não inventa share quando não há dado).
    """
    total = sum(saldos.values())
    if total <= 0 or cod_inst not in saldos:
        return None
    return saldos[cod_inst] / total


def ranking(saldos: Mapping[str, float], top: int = 10) -> list[tuple[str, float, float]]:
    """Ranking (cod_inst, saldo, share) por saldo decrescente — para inspeção e apresentação."""
    total = sum(saldos.values())
    ordenado = sorted(saldos.items(), key=lambda kv: kv[1], reverse=True)
    return [(ci, s, (s / total if total else 0.0)) for ci, s in ordenado[:top]]
