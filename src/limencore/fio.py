from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import uuid


class EstadoFio(Enum):
    JOGADO = "Jogado"          # na mesa, visivel
    ESCOLHIDO = "Escolhido"    # dentro do quarto
    RESOLVIDO = "Resolvido"    # pousou (clareza ou proximo passo); final
    GUARDADO = "Guardado"      # fora da vista, com recibo; volta por pull
    DESCARTADO = "Descartado"  # solto por decisao dele; final; NAO apaga


TRANSICOES: dict[EstadoFio, frozenset[EstadoFio]] = {
    EstadoFio.JOGADO: frozenset({EstadoFio.ESCOLHIDO, EstadoFio.GUARDADO, EstadoFio.DESCARTADO}),
    EstadoFio.ESCOLHIDO: frozenset({EstadoFio.JOGADO, EstadoFio.RESOLVIDO, EstadoFio.GUARDADO, EstadoFio.DESCARTADO}),
    EstadoFio.GUARDADO: frozenset({EstadoFio.ESCOLHIDO, EstadoFio.DESCARTADO}),
    EstadoFio.RESOLVIDO: frozenset(),
    EstadoFio.DESCARTADO: frozenset(),
}


class TransicaoInvalida(ValueError):
    pass


def _validar_uuid4(valor, nome: str) -> None:
    try:
        u = uuid.UUID(valor)
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"{nome} invalido (nao e uuid): {valor!r}")
    if u.version != 4:
        raise ValueError(f"{nome} nao e uuid4: {valor!r}")


@dataclass(frozen=True)
class Fio:  # Fio = unidade de um despejo que carrega estado (a "thread" do processo)
    despejo_id: str
    estado: EstadoFio = EstadoFio.JOGADO
    criado_em: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self):
        _validar_uuid4(self.despejo_id, "despejo_id")
        _validar_uuid4(self.id, "id")
        if not isinstance(self.estado, EstadoFio):
            raise ValueError(f"estado invalido: esperado EstadoFio, veio {self.estado!r}")
        if self.criado_em.tzinfo is None:
            raise ValueError("criado_em sem timezone: use datetime timezone-aware (UTC)")

    def transicionar(self, novo: EstadoFio) -> "Fio":
        if novo not in TRANSICOES[self.estado]:
            raise TransicaoInvalida(f"transicao proibida: {self.estado.name} -> {novo.name}")
        return replace(self, estado=novo)


@dataclass(frozen=True)
class Transicao:  # registro de uma mudanca de estado; de=None e o nascimento do fio
    fio_id: str
    de: EstadoFio | None
    para: EstadoFio
    instante: datetime

    def __post_init__(self):
        _validar_uuid4(self.fio_id, "fio_id")
        if self.de is not None and not isinstance(self.de, EstadoFio):
            raise ValueError(f"de invalido: esperado EstadoFio ou None, veio {self.de!r}")
        if not isinstance(self.para, EstadoFio):
            raise ValueError(f"para invalido: esperado EstadoFio, veio {self.para!r}")
        if self.instante.tzinfo is None:
            raise ValueError("instante sem timezone: use datetime timezone-aware (UTC)")
