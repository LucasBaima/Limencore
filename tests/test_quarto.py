from datetime import datetime, timezone

import pytest

from limencore.agente.encaminhamento import Conferencia, Encaminhamento, RegistroDaSessao
from limencore.agente.quarto import Escrito, Quarto
from limencore.agente.recepcao import Recepcao
from limencore.fio import EstadoFio
from limencore.nota import Nota, TipoNota
from limencore.storage import Armazenamento


class DetectorQueFalha:
    def avaliar(self, texto):
        raise RuntimeError("detector quebrou")


@pytest.fixture
def armazenamento():
    a = Armazenamento(":memory:")
    yield a
    a.fechar()


@pytest.fixture
def fio(armazenamento):
    (fio,) = Recepcao(armazenamento).receber("o prazo do relatorio").fios
    return armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)


def test_escrever_normal_devolve_nota(armazenamento, fio):
    resultado = Quarto(armazenamento).escrever(fio, "falta a parte dos numeros")
    assert isinstance(resultado, Escrito)
    assert isinstance(resultado.nota, Nota)
    notas = armazenamento.notas(fio.id)
    assert len(notas) == 1
    assert notas[0].tipo is TipoNota.NOTA


def test_explicito_encaminha_sem_gravar_nada(armazenamento, fio):
    antes = armazenamento.listar()
    resultado = Quarto(armazenamento).escrever(fio, "acho que quero me matar")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is True
    assert armazenamento.notas(fio.id) == []
    assert armazenamento.listar() == antes
    assert armazenamento.buscar_fios(fio.despejo_id)[0].estado is EstadoFio.ESCOLHIDO


def test_ambiguo_confere_sem_gravar(armazenamento, fio):
    resultado = Quarto(armazenamento).escrever(fio, "nao aguento mais esse relatorio")
    assert isinstance(resultado, Conferencia)
    assert resultado.texto == "nao aguento mais esse relatorio"
    assert armazenamento.notas(fio.id) == []


def test_confirmar_falso_grava_a_nota(armazenamento, fio):
    quarto = Quarto(armazenamento)
    conferencia = quarto.escrever(fio, "nao aguento mais esse relatorio")
    resultado = quarto.confirmar(fio, conferencia, False)
    assert isinstance(resultado, Escrito)
    assert isinstance(resultado.nota, Nota)
    assert [n.texto for n in armazenamento.notas(fio.id)] == ["nao aguento mais esse relatorio"]


def test_confirmar_verdadeiro_encaminha_sem_gravar(armazenamento, fio):
    antes = armazenamento.listar()
    quarto = Quarto(armazenamento)
    conferencia = quarto.escrever(fio, "nao aguento mais esse relatorio")
    resultado = quarto.confirmar(fio, conferencia, True)
    assert isinstance(resultado, Encaminhamento)
    assert armazenamento.notas(fio.id) == []
    assert armazenamento.listar() == antes


def test_sessao_compartilhada_com_a_recepcao(armazenamento, fio):
    sessao = RegistroDaSessao()
    entrada = Recepcao(armazenamento, sessao=sessao).receber(
        "quero me matar", instante=datetime.now(timezone.utc)
    )
    assert isinstance(entrada, Encaminhamento)
    resultado = Quarto(armazenamento, sessao=sessao).escrever(fio, "nao aguento mais")
    assert isinstance(resultado, Encaminhamento)
    assert resultado.oferece_retorno is False
    assert armazenamento.notas(fio.id) == []


def test_detector_que_falha_encaminha(armazenamento, fio):
    resultado = Quarto(armazenamento, DetectorQueFalha()).escrever(fio, "falta a parte dos numeros")
    assert isinstance(resultado, Encaminhamento)
    assert armazenamento.notas(fio.id) == []
