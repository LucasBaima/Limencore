from dataclasses import dataclass
from datetime import datetime

from limencore.fio import _validar_uuid4


@dataclass(frozen=True)
class Reservado:  # texto que a pessoa ESCOLHEU guardar; separado de todo o resto
    id: str
    texto: str
    instante: datetime

    def __post_init__(self):
        _validar_uuid4(self.id, "id")
        if not isinstance(self.texto, str) or not self.texto.strip():
            raise ValueError("reservado vazio")
        if self.instante.tzinfo is None:
            raise ValueError("instante sem timezone: use datetime timezone-aware (UTC)")
