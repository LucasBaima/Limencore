import dataclasses
from pathlib import Path

import limencore
from limencore.agente.encaminhamento import Encaminhamento
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


def test_encaminhamento_nao_carrega_fio_movimento_nem_estado():
    campos = {f.name for f in dataclasses.fields(Encaminhamento)}
    assert campos.isdisjoint({"fios", "movimento", "estado"})


def test_encaminhamento_nao_deixa_rastro_no_loop():
    armazenamento = Armazenamento(":memory:")
    try:
        resultado = Recepcao(armazenamento).receber("quero me matar")
        assert isinstance(resultado, Encaminhamento)
        assert armazenamento.mesa() == []
        assert armazenamento.guardados() == []
        for tabela in ("transicoes", "notas", "fios"):
            (n,) = armazenamento._conexao.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()
            assert n == 0, tabela
    finally:
        armazenamento.fechar()


def test_vocabulario_do_src():
    raiz = Path(limencore.__file__).parent
    for arquivo in raiz.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8").casefold()
        assert "crise" not in texto and "crisis" not in texto, arquivo
