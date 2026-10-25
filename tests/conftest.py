from datetime import datetime, timedelta, timezone

import pytest

from limencore.corte import Trecho
from limencore.despejo import Despejo
from limencore.fio import EstadoFio, Fio
from limencore.storage import Armazenamento


class Relogio:  # relogio injetavel: anda so quando o teste manda
    def __init__(self):
        self.agora = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.agora

    def andar(self, segundos: float) -> None:
        self.agora += timedelta(seconds=segundos)


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def banco(relogio):
    a = Armazenamento(":memory:", relogio=relogio)
    yield a
    a.fechar()


def despejo_com_fios(armazenamento, texto, *grupos, estado=EstadoFio.JOGADO):
    """Salva um despejo com um fio por grupo de (inicio, fim); sem grupos, um fio inteiro."""
    despejo = Despejo(conteudo=texto)
    base = datetime.now(timezone.utc)
    if grupos:
        fios = [
            Fio(
                despejo_id=despejo.id,
                estado=estado,
                criado_em=base + timedelta(microseconds=i),
                trechos=tuple(Trecho(i_, f_) for i_, f_ in grupo),
            )
            for i, grupo in enumerate(grupos)
        ]
    else:
        fios = [Fio(despejo_id=despejo.id, estado=estado)]
    armazenamento.salvar_despejo_com_fios(despejo, fios)
    return despejo, fios
