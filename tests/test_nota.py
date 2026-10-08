import dataclasses
import uuid
from datetime import datetime, timezone

import pytest

from limencore.nota import Nota, TipoNota

FIO_ID = str(uuid.uuid4())
AGORA = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_nota_valida():
    nota = Nota(fio_id=FIO_ID, tipo=TipoNota.NOTA, texto="algo", instante=AGORA)
    assert nota.fio_id == FIO_ID
    assert nota.tipo is TipoNota.NOTA
    assert nota.texto == "algo"
    assert nota.instante == AGORA


def test_nota_e_frozen():
    nota = Nota(fio_id=FIO_ID, tipo=TipoNota.NOTA, texto="algo", instante=AGORA)
    with pytest.raises(dataclasses.FrozenInstanceError):
        nota.texto = "outro"


def test_texto_preservado_exatamente():
    texto = "  com espaço\nem duas linhas  "
    nota = Nota(fio_id=FIO_ID, tipo=TipoNota.POUSO, texto=texto, instante=AGORA)
    assert nota.texto == texto


@pytest.mark.parametrize(
    "kwargs",
    [
        {"texto": ""},
        {"texto": "   "},
        {"tipo": "NOTA"},
        {"instante": datetime(2026, 1, 2, 3, 4, 5)},
        {"fio_id": "abc"},
    ],
)
def test_invalidos_levantam(kwargs):
    base = {"fio_id": FIO_ID, "tipo": TipoNota.NOTA, "texto": "algo", "instante": AGORA}
    base.update(kwargs)
    with pytest.raises(ValueError):
        Nota(**base)
