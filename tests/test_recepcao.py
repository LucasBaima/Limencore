from datetime import datetime, timezone

import pytest

from limencore.agente.encaminhamento import Conferencia, Encaminhamento, Passagem, RegistroDaSessao
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


class DetectorQueFalha:
    def avaliar(self, texto):
        raise RuntimeError("detector quebrou")


class DetectorNunca:
    def avaliar(self, texto):
        return Passagem.SEGUIR


def _nada_salvo(armazenamento):
    assert armazenamento.listar() == []
    assert armazenamento.mesa() == []
    (n,) = armazenamento._conexao.execute("SELECT COUNT(*) FROM fios").fetchone()
    assert n == 0


def test_explicito_encaminha_sem_salvar(armazenamento):
    espiao = SeletorEspiao()
    resultado = Recepcao(armazenamento, espiao).receber("quero me matar")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is True
    assert resultado.texto == "quero me matar"
    _nada_salvo(armazenamento)
    assert espiao.recebidos == []


def test_ambiguo_confere_sem_salvar(armazenamento):
    espiao = SeletorEspiao()
    instante = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    resultado = Recepcao(armazenamento, espiao).receber("quero sumir", instante=instante)
    assert resultado == Conferencia(texto="quero sumir", instante=instante)
    _nada_salvo(armazenamento)
    assert espiao.recebidos == []


def test_confirmar_falso_segue_com_texto_e_instante_originais(armazenamento):
    recepcao = Recepcao(armazenamento)
    instante = datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc)
    conferencia = recepcao.receber("esse prazo vai me matar", instante=instante)
    resultado = recepcao.confirmar(conferencia, False)
    assert isinstance(resultado, Recebido)
    (despejo,) = armazenamento.listar()
    assert despejo.conteudo == "esse prazo vai me matar"
    assert despejo.instante == instante
    assert len(armazenamento.buscar_fios(despejo.id)) == 1


def test_confirmar_falso_nao_roda_o_detector_de_novo(armazenamento):
    recepcao = Recepcao(armazenamento, detector=DetectorQueFalha())
    conferencia = Conferencia(texto="quero sumir", instante=datetime.now(timezone.utc))
    assert isinstance(recepcao.confirmar(conferencia, False), Recebido)


def test_confirmar_verdadeiro_encaminha_sem_salvar(armazenamento):
    recepcao = Recepcao(armazenamento)
    conferencia = recepcao.receber("quero sumir")
    resultado = recepcao.confirmar(conferencia, True)
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is True
    _nada_salvo(armazenamento)


def test_reincidencia_encaminha_sem_retorno(armazenamento):
    sessao = RegistroDaSessao()
    recepcao = Recepcao(armazenamento, sessao=sessao)
    primeiro = recepcao.receber("quero me matar", instante=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc))
    segundo = recepcao.receber("quero sumir", instante=datetime(2026, 1, 2, 10, 10, tzinfo=timezone.utc))
    assert isinstance(primeiro, Encaminhamento) and primeiro.oferece_retorno is True
    assert isinstance(segundo, Encaminhamento)
    assert segundo.oferece_retorno is False
    _nada_salvo(armazenamento)


def test_reincidencia_nao_afeta_texto_neutro(armazenamento):
    recepcao = Recepcao(armazenamento)
    recepcao.receber("quero me matar", instante=datetime(2026, 1, 2, 10, 0, tzinfo=timezone.utc))
    resultado = recepcao.receber("o prazo", instante=datetime(2026, 1, 2, 10, 5, tzinfo=timezone.utc))
    assert isinstance(resultado, Recebido)


def test_detector_que_falha_encaminha(armazenamento):
    resultado = Recepcao(armazenamento, detector=DetectorQueFalha()).receber("um pensamento")
    assert isinstance(resultado, Encaminhamento)
    _nada_salvo(armazenamento)


def test_detector_injetado_substitui_o_padrao(armazenamento):
    resultado = Recepcao(armazenamento, detector=DetectorNunca()).receber("quero me matar")
    assert isinstance(resultado, Recebido)
    assert len(resultado.fios) == 1
    assert len(armazenamento.buscar_fios(resultado.despejo.id)) == 1
