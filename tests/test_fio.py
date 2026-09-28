import dataclasses
import uuid
from datetime import datetime, timezone

import pytest

from limencore.fio import EstadoFio, Fio, Transicao, TransicaoInvalida


PERMITIDAS = {
    ("JOGADO", "ESCOLHIDO"),
    ("JOGADO", "GUARDADO"),
    ("JOGADO", "DESCARTADO"),
    ("ESCOLHIDO", "JOGADO"),
    ("ESCOLHIDO", "RESOLVIDO"),
    ("ESCOLHIDO", "GUARDADO"),
    ("ESCOLHIDO", "DESCARTADO"),
    ("GUARDADO", "ESCOLHIDO"),
    ("GUARDADO", "DESCARTADO"),
}

NOMES = ["JOGADO", "ESCOLHIDO", "RESOLVIDO", "GUARDADO", "DESCARTADO"]
PARES = [(origem, destino) for origem in NOMES for destino in NOMES]


class TestEstadoFio:
    def test_os_cinco_e_so_eles(self):
        assert {e.name for e in EstadoFio} == {
            "JOGADO",
            "ESCOLHIDO",
            "RESOLVIDO",
            "GUARDADO",
            "DESCARTADO",
        }


class TestFioValido:
    def test_padrao(self):
        fio = Fio(despejo_id=str(uuid.uuid4()))
        assert fio.estado is EstadoFio.JOGADO
        assert fio.criado_em.tzinfo is not None
        assert uuid.UUID(fio.id).version == 4

    def test_dois_fios_tem_ids_diferentes(self):
        despejo_id = str(uuid.uuid4())
        assert Fio(despejo_id=despejo_id).id != Fio(despejo_id=despejo_id).id

    def test_frozen(self):
        fio = Fio(despejo_id=str(uuid.uuid4()))
        with pytest.raises(dataclasses.FrozenInstanceError):
            fio.estado = EstadoFio.ESCOLHIDO


class TestFioInvalido:
    def test_despejo_id_nao_uuid(self):
        with pytest.raises(ValueError):
            Fio(despejo_id="abc")

    def test_despejo_id_uuid1(self):
        with pytest.raises(ValueError):
            Fio(despejo_id=str(uuid.uuid1()))

    def test_estado_string(self):
        with pytest.raises(ValueError):
            Fio(despejo_id=str(uuid.uuid4()), estado="JOGADO")

    def test_criado_em_sem_timezone(self):
        with pytest.raises(ValueError):
            Fio(despejo_id=str(uuid.uuid4()), criado_em=datetime(2026, 1, 1))

    def test_id_nao_uuid(self):
        with pytest.raises(ValueError):
            Fio(despejo_id=str(uuid.uuid4()), id="abc")


class TestTransicoes:
    def test_sao_25_pares(self):
        assert len(PARES) == 25

    @pytest.mark.parametrize("origem,destino", PARES)
    def test_transicao(self, origem, destino):
        fio = Fio(despejo_id=str(uuid.uuid4()), estado=EstadoFio[origem])
        if (origem, destino) in PERMITIDAS:
            novo = fio.transicionar(EstadoFio[destino])
            assert isinstance(novo, Fio)
            assert novo.estado is EstadoFio[destino]
            assert novo.id == fio.id
            assert novo.despejo_id == fio.despejo_id
            assert novo.criado_em == fio.criado_em
            assert fio.estado is EstadoFio[origem]
        else:
            with pytest.raises(TransicaoInvalida):
                fio.transicionar(EstadoFio[destino])

    def test_transicao_invalida_e_value_error(self):
        assert issubclass(TransicaoInvalida, ValueError)


class TestTransicao:
    def test_nascimento_aceito(self):
        t = Transicao(
            fio_id=str(uuid.uuid4()),
            de=None,
            para=EstadoFio.JOGADO,
            instante=datetime.now(timezone.utc),
        )
        assert t.de is None
        assert t.para is EstadoFio.JOGADO

    def test_frozen(self):
        t = Transicao(
            fio_id=str(uuid.uuid4()),
            de=None,
            para=EstadoFio.JOGADO,
            instante=datetime.now(timezone.utc),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.para = EstadoFio.ESCOLHIDO

    @pytest.mark.parametrize(
        "campos",
        [
            {"fio_id": "abc"},
            {"de": "JOGADO"},
            {"para": "JOGADO"},
            {"para": None},
            {"instante": datetime(2026, 1, 1, 10, 0)},
        ],
    )
    def test_campos_invalidos(self, campos):
        base = {
            "fio_id": str(uuid.uuid4()),
            "de": None,
            "para": EstadoFio.JOGADO,
            "instante": datetime.now(timezone.utc),
        }
        with pytest.raises(ValueError):
            Transicao(**{**base, **campos})
