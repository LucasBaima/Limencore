import sqlite3
import uuid
from datetime import datetime, timezone

import pytest

from limencore.despejo import Despejo
from limencore.fio import EstadoFio, Fio
from limencore.storage import Armazenamento


def test_jornada_completa():
    armazenamento = Armazenamento(":memory:")
    despejo = Despejo(conteudo="o chefe cobrou o relatorio de novo")
    armazenamento.salvar(despejo)
    fio = Fio(despejo_id=despejo.id)
    armazenamento.salvar_fio(fio)

    fio = armazenamento.marcar_assunto(fio, "O Chefe")
    fio = armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
    fio = armazenamento.atualizar_estado(fio, EstadoFio.GUARDADO)

    assert fio in armazenamento.guardados()
    assert fio not in armazenamento.mesa()

    fio = armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
    fio = armazenamento.atualizar_estado(fio, EstadoFio.RESOLVIDO)

    assert fio not in armazenamento.mesa()
    assert fio not in armazenamento.guardados()
    assert [(t.de, t.para) for t in armazenamento.historico(fio.id)] == [
        (None, EstadoFio.JOGADO),
        (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO),
        (EstadoFio.ESCOLHIDO, EstadoFio.GUARDADO),
        (EstadoFio.GUARDADO, EstadoFio.ESCOLHIDO),
        (EstadoFio.ESCOLHIDO, EstadoFio.RESOLVIDO),
    ]
    do_assunto = armazenamento.fios_do_assunto("o chefe")
    assert len(do_assunto) == 1
    assert do_assunto[0].estado == EstadoFio.RESOLVIDO
    assert do_assunto[0].assunto_chave == "o chefe"
    armazenamento.fechar()


def test_banco_mais_antigo_ate_hoje(tmp_path):
    caminho = str(tmp_path / "antigo.db")
    despejo_id = str(uuid.uuid4())
    instante = datetime(2025, 3, 10, 12, 0, tzinfo=timezone.utc)
    conexao = sqlite3.connect(caminho)
    conexao.execute(
        "CREATE TABLE thoughts (id TEXT PRIMARY KEY, conteudo TEXT NOT NULL, instante TEXT NOT NULL)"
    )
    conexao.execute(
        "INSERT INTO thoughts (id, conteudo, instante) VALUES (?, ?, ?)",
        (despejo_id, "pensamento antigo", instante.isoformat()),
    )
    conexao.commit()
    conexao.close()

    armazenamento = Armazenamento(caminho)
    tabelas = {
        nome for (nome,) in armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"despejos", "fios", "transicoes", "assuntos", "contexto_dia", "categorias"} <= tabelas
    assert "thoughts" not in tabelas
    colunas_fios = {
        linha[1] for linha in armazenamento._conexao.execute("PRAGMA table_info(fios)")
    }
    assert "assunto_chave" in colunas_fios

    assert armazenamento.listar() == [
        Despejo(conteudo="pensamento antigo", instante=instante, id=despejo_id)
    ]

    fio = Fio(despejo_id=despejo_id)
    armazenamento.salvar_fio(fio)
    armazenamento.marcar_assunto(fio, "Trabalho")
    armazenamento.fechar()


def test_tudo_sobrevive_a_reabrir(tmp_path):
    caminho = str(tmp_path / "limencore.db")
    armazenamento = Armazenamento(caminho)
    despejo = Despejo(conteudo="preciso falar com a Ana")
    armazenamento.salvar(despejo)
    fio = Fio(despejo_id=despejo.id)
    armazenamento.salvar_fio(fio)
    fio = armazenamento.marcar_assunto(fio, "  Conversa com a  Ana ")
    fio_devolvido = armazenamento.atualizar_estado(fio, EstadoFio.GUARDADO)
    armazenamento.fechar()

    reaberto = Armazenamento(caminho)
    assert reaberto.buscar_fios(despejo.id) == [fio_devolvido]
    assert len(reaberto.historico(fio_devolvido.id)) == 2
    assunto = reaberto.buscar_assunto(fio_devolvido.assunto_chave)
    assert assunto is not None
    assert assunto.rotulo == "Conversa com a Ana"
    assert fio_devolvido in reaberto.guardados()
    reaberto.fechar()


def test_assunto_inexistente_e_barrado():
    armazenamento = Armazenamento(":memory:")
    despejo = Despejo(conteudo="algo solto")
    armazenamento.salvar(despejo)

    with pytest.raises(sqlite3.IntegrityError):
        armazenamento.salvar_fio(Fio(despejo_id=despejo.id, assunto_chave="nao existe"))

    assert armazenamento.buscar_fios(despejo.id) == []
    armazenamento.fechar()
