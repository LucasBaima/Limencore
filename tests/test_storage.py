import sqlite3

import pytest

from limencore.storage import Armazenamento


class TestCriacao:
    def test_tabela_thoughts_existe(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='thoughts'"
        )
        assert cursor.fetchone() is not None
        armazenamento.fechar()

    def test_colunas_esperadas(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute("PRAGMA table_info(thoughts)")
        colunas = {linha[1] for linha in cursor.fetchall()}
        assert colunas == {"id", "conteudo", "instante"}
        armazenamento.fechar()


class TestIdempotencia:
    def test_inicializar_duas_vezes_nao_falha(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento._inicializar()
        armazenamento._inicializar()
        cursor = armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='thoughts'"
        )
        assert cursor.fetchone() is not None
        armazenamento.fechar()


class TestFechar:
    def test_fechar_encerra_conexao(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.fechar()
        with pytest.raises(sqlite3.ProgrammingError):
            armazenamento._conexao.execute("SELECT 1")
