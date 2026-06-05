"""Preparação do torch no ambiente (conda + Windows) — chamar ANTES de numpy e dos modelos.

Dois problemas DIAGNOSTICADOS neste ambiente (miniconda, py3.13), ambos com a mesma raiz (o
runtime OpenMP do conda/MKL conflita com o do torch):

  1) "OMP: Error #15" — duas libs OpenMP (libomp do torch vs libiomp5md do MKL) inicializadas.
     Corrige com KMP_DUPLICATE_LIB_OK=TRUE.
  2) "OSError [WinError 127] ... shm.dll" — se o numpy (que puxa o MKL do conda) é importado
     ANTES do torch, o torch não acha um procedimento nas DLLs e falha. Verificado empiricamente:
     torch-antes-de-numpy funciona; numpy-antes-de-torch quebra. Corrige importando torch PRIMEIRO.

`preparar_torch()` resolve os dois: seta a flag e força o import do torch antes do numpy. É
seguro p/ a matemática (matmul/softmax conferem com resultado conhecido). Idempotente.

IMPORTANTE: chamar como a PRIMEIRA coisa do script/entrypoint que usa modelos reais, ANTES de
importar numpy ou módulos do legacy_rag que puxam numpy. Os testes (com fakes) NÃO chamam isto,
então o pacote continua importável sem torch.
"""
import os


def preparar_torch():
    """Seta KMP_DUPLICATE_LIB_OK e importa torch ANTES do numpy. Devolve o módulo torch."""
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # problema (1): OMP duplicado
    import torch                                            # problema (2): torch antes de numpy
    return torch
