from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from limencore.fio import _validar_uuid4


class TipoNota(Enum):
    NOTA = "Nota"    # o que ele escreve dentro do quarto
    POUSO = "Pouso"  # frase opcional registrada junto com o pouso


@dataclass(frozen=True)
class Nota:  # guardada exatamente como ele escreveu
    fio_id: str
    tipo: TipoNota
    texto: str
    instante: datetime

    def __post_init__(self):
        _validar_uuid4(self.fio_id, "fio_id")
        if not isinstance(self.tipo, TipoNota):
            raise ValueError(f"tipo invalido: esperado TipoNota, veio {self.tipo!r}")
        if not isinstance(self.texto, str) or not self.texto.strip():
            raise ValueError("nota vazia")
        if self.instante.tzinfo is None:
            raise ValueError("instante sem timezone: use datetime timezone-aware (UTC)")
