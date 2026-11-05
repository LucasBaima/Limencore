from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import uuid

from limencore.assunto import normalizar_assunto
from limencore.corte import Trecho


class EstadoFio(Enum):
    JOGADO = "Jogado"          # na mesa, visivel
    ESCOLHIDO = "Escolhido"    # dentro do quarto
    RESOLVIDO = "Resolvido"    # pousou (clareza ou proximo passo); final
    GUARDADO = "Guardado"      # fora da vista, com recibo; volta por pull
    DESCARTADO = "Descartado"  # solto por decisao dele; final; NAO apaga
    JUNTADO = "Juntado"        # foi juntado em outro fio (juntado_em); final; NAO apaga


TRANSICOES: dict[EstadoFio, frozenset[EstadoFio]] = {
    EstadoFio.JOGADO: frozenset({EstadoFio.ESCOLHIDO, EstadoFio.GUARDADO, EstadoFio.DESCARTADO, EstadoFio.JUNTADO}),
    EstadoFio.ESCOLHIDO: frozenset({
        EstadoFio.JOGADO, EstadoFio.RESOLVIDO, EstadoFio.GUARDADO, EstadoFio.DESCARTADO, EstadoFio.JUNTADO,
    }),
    EstadoFio.GUARDADO: frozenset({EstadoFio.ESCOLHIDO, EstadoFio.DESCARTADO}),
    EstadoFio.RESOLVIDO: frozenset(),
    EstadoFio.DESCARTADO: frozenset(),
    EstadoFio.JUNTADO: frozenset(),
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
    assunto_chave: str | None = None  #Cada um nasce sem assunto
    trechos: tuple[Trecho, ...] = ()  # vazio = o despejo inteiro
    juntado_em: str | None = None  # so no JUNTADO: o fio que recebeu este
    ultimo_toque: datetime | None = None  # None ate o primeiro entrar

    def __post_init__(self):
        _validar_uuid4(self.despejo_id, "despejo_id")
        _validar_uuid4(self.id, "id")
        if not isinstance(self.estado, EstadoFio):
            raise ValueError(f"estado invalido: esperado EstadoFio, veio {self.estado!r}")
        if self.criado_em.tzinfo is None:
            raise ValueError("criado_em sem timezone: use datetime timezone-aware (UTC)")
        if self.assunto_chave is not None and normalizar_assunto(self.assunto_chave) != self.assunto_chave:
            raise ValueError(f"assunto_chave nao normalizada: {self.assunto_chave!r}")
        if not isinstance(self.trechos, tuple) or any(not isinstance(t, Trecho) for t in self.trechos):
            raise ValueError(f"trechos invalidos: esperado tuple de Trecho, veio {self.trechos!r}")
        if self.juntado_em is not None:
            _validar_uuid4(self.juntado_em, "juntado_em")
        if self.ultimo_toque is not None and self.ultimo_toque.tzinfo is None:
            raise ValueError("ultimo_toque sem timezone: use datetime timezone-aware (UTC)")

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
    motivo: str | None = None  # None = transicao normal; "desfazer" = volta de uma operacao

    def __post_init__(self):
        _validar_uuid4(self.fio_id, "fio_id")
        if self.de is not None and not isinstance(self.de, EstadoFio):
            raise ValueError(f"de invalido: esperado EstadoFio ou None, veio {self.de!r}")
        if not isinstance(self.para, EstadoFio):
            raise ValueError(f"para invalido: esperado EstadoFio, veio {self.para!r}")
        if self.instante.tzinfo is None:
            raise ValueError("instante sem timezone: use datetime timezone-aware (UTC)")
        if self.motivo is not None and (not isinstance(self.motivo, str) or not self.motivo.strip()):
            raise ValueError(f"motivo invalido: {self.motivo!r}")
