import dataclasses
from datetime import datetime, timezone

import pytest

from limencore.entry import ThoughtEntry


class TestValido:
    def test_conteudo_valido(self):
        e = ThoughtEntry(conteudo="um pensamento qualquer")
        assert e.conteudo == "um pensamento qualquer"

    def test_instante_gerado_automaticamente(self):
        antes = datetime.now(timezone.utc)
        e = ThoughtEntry(conteudo="x")
        depois = datetime.now(timezone.utc)
        assert antes <= e.instante <= depois
        assert e.instante.tzinfo is not None

    def test_id_gerado_automaticamente(self):
        e1 = ThoughtEntry(conteudo="x")
        e2 = ThoughtEntry(conteudo="y")
        assert e1.id != e2.id
        assert isinstance(e1.id, str) and e1.id

    def test_instante_explicito_utc_aceito(self):
        instante = datetime(2026, 1, 1, tzinfo=timezone.utc)
        e = ThoughtEntry(conteudo="x", instante=instante)
        assert e.instante == instante


class TestInvalido:
    def test_conteudo_vazio_falha(self):
        with pytest.raises(ValueError):
            ThoughtEntry(conteudo="")

    def test_conteudo_so_espacos_falha(self):
        with pytest.raises(ValueError):
            ThoughtEntry(conteudo="   ")

    def test_instante_sem_timezone_falha(self):
        with pytest.raises(ValueError):
            ThoughtEntry(conteudo="x", instante=datetime(2026, 1, 1))


class TestFrozen:
    def test_reatribuir_conteudo_falha(self):
        e = ThoughtEntry(conteudo="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.conteudo = "y"

    def test_reatribuir_instante_falha(self):
        e = ThoughtEntry(conteudo="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.instante = datetime.now(timezone.utc)
