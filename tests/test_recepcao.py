from datetime import datetime, timezone

import pytest

from limencore.agente.movimento import Forma, Movimento
from limencore.agente.recepcao import Recebido, Recepcao
from limencore.fio import EstadoFio
from limencore.storage import Armazenamento


class SeletorEspiao:
    def __init__(self):
        self.recebidos = []

    def selecionar(self, entry):
        self.recebidos.append(entry)
        return Movimento(forma=Forma.UM_SO, alvos=(entry.id,))


class SeletorQueFalha:
    def selecionar(self, entry):
        raise RuntimeError("seletor quebrou")


class SeletorDividir:
    def selecionar(self, entry):
        return Movimento(forma=Forma.DIVIDIR, alvos=(entry.id,))


@pytest.fixture
def armazenamento():
    a = Armazenamento(":memory:")
    yield a
    a.fechar()


def test_receber_grava_despejo_fio_e_nascimento(armazenamento):
    recebido = Recepcao(armazenamento).receber("um pensamento")
    despejos = armazenamento.listar()
    assert len(despejos) == 1
    assert despejos[0].conteudo == "um pensamento"
    fios = armazenamento.buscar_fios(despejos[0].id)
    assert len(fios) == 1
    assert fios[0].estado is EstadoFio.JOGADO
    assert fios[0].id == recebido.fios[0].id
    historico = armazenamento.historico(fios[0].id)
    assert len(historico) == 1
    assert historico[0].de is None
    assert historico[0].para is EstadoFio.JOGADO


def test_devolve_recebido_com_movimento_um_so(armazenamento):
    recebido = Recepcao(armazenamento).receber("um pensamento")
    assert isinstance(recebido, Recebido)
    assert recebido.movimento.forma is Forma.UM_SO
    assert recebido.movimento.alvos == (recebido.despejo.id,)


def test_seletor_recebe_o_mesmo_despejo_salvo(armazenamento):
    espiao = SeletorEspiao()
    recebido = Recepcao(armazenamento, espiao).receber("espiado")
    assert espiao.recebidos == [recebido.despejo]
    assert espiao.recebidos[0] is recebido.despejo
    assert armazenamento.listar()[0].id == espiao.recebidos[0].id


def test_seletor_que_falha_nao_perde_o_despejo(armazenamento):
    recebido = Recepcao(armazenamento, SeletorQueFalha()).receber("salvo mesmo assim")
    assert recebido.movimento.forma is Forma.UM_SO
    assert recebido.movimento.alvos == (recebido.despejo.id,)
    assert [d.id for d in armazenamento.listar()] == [recebido.despejo.id]
    assert len(armazenamento.buscar_fios(recebido.despejo.id)) == 1
    assert len(recebido.fios) == 1


def test_seletor_dividir_ainda_cria_um_fio(armazenamento):
    recebido = Recepcao(armazenamento, SeletorDividir()).receber("varios misturados")
    assert recebido.movimento.forma is Forma.DIVIDIR
    assert len(recebido.fios) == 1
    assert len(armazenamento.buscar_fios(recebido.despejo.id)) == 1


def test_texto_vazio_levanta_e_nao_grava(armazenamento):
    with pytest.raises(ValueError):
        Recepcao(armazenamento).receber("   ")
    assert armazenamento.listar() == []


def test_instante_explicito_e_respeitado(armazenamento):
    instante = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    recebido = Recepcao(armazenamento).receber("com hora", instante=instante)
    assert recebido.despejo.instante == instante
    assert armazenamento.listar()[0].instante == instante
