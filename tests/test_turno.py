import dataclasses
import uuid
from datetime import datetime, timezone

import pytest

from conftest import despejo_com_fios
from limencore.fio import EstadoFio
from limencore.nota import Nota
from limencore.turno import Turno


class TestTurnoValido:
    def test_frozen(self):
        t = Turno(fio_id=str(uuid.uuid4()), seq=1, texto="x", instante=datetime.now(timezone.utc))
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.texto = "y"

    @pytest.mark.parametrize(
        "campos",
        [
            {"texto": ""},
            {"texto": "   "},
            {"texto": None},
            {"fio_id": "abc"},
            {"seq": 0},
            {"seq": True},
            {"instante": datetime(2026, 1, 1)},
        ],
    )
    def test_campos_invalidos(self, campos):
        base = {"fio_id": str(uuid.uuid4()), "seq": 1, "texto": "x", "instante": datetime.now(timezone.utc)}
        with pytest.raises(ValueError):
            Turno(**{**base, **campos})


class TestTurnosNoBanco:
    def test_ida_e_volta(self, banco, relogio):
        _, (fio,) = despejo_com_fios(banco, "o prazo")
        turno = banco.registrar_turno(fio, "um turno")
        assert turno == Turno(fio_id=fio.id, seq=1, texto="um turno", instante=relogio.agora)
        assert banco.turnos(fio.id) == [turno]

    def test_ordem_por_seq(self, banco, relogio):
        _, (fio,) = despejo_com_fios(banco, "o prazo")
        for texto in ("primeiro", "segundo", "terceiro"):
            banco.registrar_turno(fio, texto)
        relogio.andar(-60)  # instante fora de ordem nao muda a ordem
        banco.registrar_turno(fio, "quarto")
        turnos = banco.turnos(fio.id)
        assert [t.seq for t in turnos] == [1, 2, 3, 4]
        assert [t.texto for t in turnos] == ["primeiro", "segundo", "terceiro", "quarto"]

    def test_seq_e_por_fio(self, banco):
        _, (a, b) = despejo_com_fios(banco, "um dois", [(0, 3)], [(4, 8)])
        banco.registrar_turno(a, "x")
        banco.registrar_turno(a, "y")
        assert banco.registrar_turno(b, "z").seq == 1

    def test_notas_e_turnos_separados(self, banco):
        _, (fio,) = despejo_com_fios(banco, "o prazo", estado=EstadoFio.ESCOLHIDO)
        banco.escrever(fio, "uma nota")
        banco.registrar_turno(fio, "um turno")
        assert [n.texto for n in banco.notas(fio.id)] == ["uma nota"]
        assert all(isinstance(n, Nota) for n in banco.notas(fio.id))
        assert [t.texto for t in banco.turnos(fio.id)] == ["um turno"]
        assert all(isinstance(t, Turno) for t in banco.turnos(fio.id))
        (n_notas,) = banco._conexao.execute("SELECT COUNT(*) FROM notas").fetchone()
        (n_turnos,) = banco._conexao.execute("SELECT COUNT(*) FROM turnos").fetchone()
        assert (n_notas, n_turnos) == (1, 1)

    def test_turno_vazio_nao_grava(self, banco):
        _, (fio,) = despejo_com_fios(banco, "o prazo")
        with pytest.raises(ValueError):
            banco.registrar_turno(fio, "  ")
        assert banco.turnos(fio.id) == []

    def test_fio_inexistente(self, banco):
        _, (fio,) = despejo_com_fios(banco, "o prazo")
        with pytest.raises(ValueError):
            banco.registrar_turno(dataclasses.replace(fio, id=str(uuid.uuid4())), "x")

    def test_apagar_o_fio_apaga_os_turnos(self, banco):
        _, (fio,) = despejo_com_fios(banco, "o prazo")
        banco.registrar_turno(fio, "um turno")
        # trechos e transicoes nao tem cascade: saem antes, so pra exercitar o FK dos turnos
        banco._conexao.execute("DELETE FROM transicoes WHERE fio_id = ?", (fio.id,))
        banco._conexao.execute("DELETE FROM trechos_fio WHERE fio_id = ?", (fio.id,))
        banco._conexao.execute("DELETE FROM fios WHERE id = ?", (fio.id,))
        banco._conexao.commit()
        assert banco.turnos(fio.id) == []
        (n,) = banco._conexao.execute("SELECT COUNT(*) FROM turnos").fetchone()
        assert n == 0

    def test_secure_delete_ligado(self, banco):
        (valor,) = banco._conexao.execute("PRAGMA secure_delete").fetchone()
        assert valor == 1

    def test_tabela_idempotente(self, tmp_path):
        from limencore.storage import Armazenamento
        caminho = str(tmp_path / "t.db")
        a = Armazenamento(caminho)
        _, (fio,) = despejo_com_fios(a, "o prazo")
        a.registrar_turno(fio, "um turno")
        a.fechar()
        b = Armazenamento(caminho)
        assert [t.texto for t in b.turnos(fio.id)] == ["um turno"]
        b.fechar()
