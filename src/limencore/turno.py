from dataclasses import dataclass
from datetime import datetime

from limencore.fio import _validar_uuid4


@dataclass(frozen=True)
class Turno:  # fala do agente dentro de um fio; nunca se mistura com Nota
    fio_id: str
    seq: int  # ordem dentro do fio, a partir de 1
    texto: str
    instante: datetime

    def __post_init__(self):
        _validar_uuid4(self.fio_id, "fio_id")
        if not isinstance(self.seq, int) or isinstance(self.seq, bool) or self.seq < 1:
            raise ValueError(f"seq invalido: esperado int >= 1, veio {self.seq!r}")
        if not isinstance(self.texto, str) or not self.texto.strip():
            raise ValueError("turno vazio")
        if self.instante.tzinfo is None:
            raise ValueError("instante sem timezone: use datetime timezone-aware (UTC)")
