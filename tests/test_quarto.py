import pytest

from limencore.agente.encaminhamento import Encaminhamento
from limencore.agente.quarto import Quarto
from limencore.agente.recepcao import Recepcao
from limencore.fio import EstadoFio
from limencore.nota import Nota, TipoNota
from limencore.storage import Armazenamento


class DetectorQueFalha:
    def deve_encaminhar(self, texto):
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
    assert isinstance(resultado, Nota)
    notas = armazenamento.notas(fio.id)
    assert len(notas) == 1
    assert notas[0].tipo is TipoNota.NOTA


def test_texto_que_dispara_encaminha_sem_nota(armazenamento, fio):
    antes = {d.id for d in armazenamento.listar()}
    resultado = Quarto(armazenamento).escrever(fio, "acho que quero me matar")
    assert isinstance(resultado, Encaminhamento)
    assert armazenamento.notas(fio.id) == []
    assert armazenamento.buscar_fios(fio.despejo_id)[0].estado is EstadoFio.ESCOLHIDO
    novos = [d for d in armazenamento.listar() if d.id not in antes]
    assert len(novos) == 1
    assert novos[0].conteudo == "acho que quero me matar"
    assert novos[0].id == resultado.despejo.id
    assert armazenamento.buscar_fios(novos[0].id) == []


def test_detector_que_falha_encaminha(armazenamento, fio):
    resultado = Quarto(armazenamento, DetectorQueFalha()).escrever(fio, "falta a parte dos numeros")
    assert isinstance(resultado, Encaminhamento)
    assert armazenamento.notas(fio.id) == []
