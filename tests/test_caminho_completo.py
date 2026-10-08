from limencore.agente.recepcao import Recepcao
from limencore.fio import EstadoFio
from limencore.nota import TipoNota
from limencore.storage import Armazenamento


def test_caminho_completo_recebe_escreve_e_pousa():
    armazenamento = Armazenamento(":memory:")
    recebido = Recepcao(armazenamento).receber("o prazo do relatorio")
    (fio,) = recebido.fios

    fio = armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
    armazenamento.escrever(fio, "falta a parte dos numeros")
    armazenamento.escrever(fio, "a introducao ja esta pronta")
    fio = armazenamento.pousar(fio, "entrego a primeira parte hoje")

    assert fio.estado is EstadoFio.RESOLVIDO
    assert armazenamento.buscar_fios(recebido.despejo.id)[0].estado is EstadoFio.RESOLVIDO
    assert fio.id not in {f.id for f in armazenamento.mesa()}

    notas = armazenamento.notas(fio.id)
    assert [n.tipo for n in notas] == [TipoNota.NOTA, TipoNota.NOTA, TipoNota.POUSO]
    assert [n.texto for n in notas] == [
        "falta a parte dos numeros",
        "a introducao ja esta pronta",
        "entrego a primeira parte hoje",
    ]

    assert [(t.de, t.para) for t in armazenamento.historico(fio.id)] == [
        (None, EstadoFio.JOGADO),
        (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO),
        (EstadoFio.ESCOLHIDO, EstadoFio.RESOLVIDO),
    ]

    assert armazenamento.listar() == [recebido.despejo]
    armazenamento.fechar()
