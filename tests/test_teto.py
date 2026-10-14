import dataclasses
from pathlib import Path

import pytest

import limencore
from limencore.agente.encaminhamento import Conferencia, Encaminhamento, Passagem
from limencore.agente.movimento import Forma
from limencore.agente.pergunta import CamadaContencao
from limencore.agente.recepcao import Recepcao
from limencore.fio import EstadoFio
from limencore.storage import Armazenamento


def test_formas_sao_so_as_tres():
    assert {f.name for f in Forma} == {"DIVIDIR", "UM_SO", "LIGAR"}


def test_estados_do_fio_sao_so_os_cinco():
    assert {e.name for e in EstadoFio} == {
        "JOGADO", "ESCOLHIDO", "RESOLVIDO", "GUARDADO", "DESCARTADO",
    }


def test_camadas_sao_so_as_quatro():
    assert {c.name for c in CamadaContencao} == {
        "SITUACAO", "PENSAMENTO", "EMOCAO", "PREOCUPACAO",
    }


def test_passagens_sao_so_as_tres():
    assert {p.name for p in Passagem} == {"SEGUIR", "CONFERIR", "ENCAMINHAR"}


@pytest.mark.parametrize("classe", [Encaminhamento, Conferencia])
def test_saidas_do_portao_nao_carregam_fio_movimento_estado_nem_despejo(classe):
    campos = {f.name for f in dataclasses.fields(classe)}
    assert campos.isdisjoint({"fios", "movimento", "estado", "despejo"})


def test_encaminhamento_e_conferencia_nao_deixam_rastro():
    armazenamento = Armazenamento(":memory:")
    try:
        recepcao = Recepcao(armazenamento)
        assert isinstance(recepcao.receber("quero sumir"), Conferencia)
        assert isinstance(recepcao.receber("quero me matar"), Encaminhamento)
        assert armazenamento.mesa() == []
        assert armazenamento.guardados() == []
        for tabela in ("despejos", "fios", "transicoes", "notas", "reservados"):
            (n,) = armazenamento._conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()
            assert n == 0, tabela
    finally:
        armazenamento.fechar()


def test_vocabulario_do_src():
    raiz = Path(limencore.__file__).parent
    for arquivo in raiz.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8").casefold()
        assert "crise" not in texto and "crisis" not in texto, arquivo
