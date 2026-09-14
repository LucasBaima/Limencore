import sqlite3
from datetime import datetime, timezone

import pytest

from limencore.ambient import ContextoAmbiente
from limencore.entry import ThoughtEntry
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

    def test_tabela_contexto_dia_existe(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='contexto_dia'"
        )
        assert cursor.fetchone() is not None
        armazenamento.fechar()

    def test_contexto_dia_colunas_esperadas(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute("PRAGMA table_info(contexto_dia)")
        colunas = {linha[1] for linha in cursor.fetchall()}
        assert colunas == {
            "entry_date",
            "sono_horas",
            "sono_interrupcoes",
            "cafeina_mg",
            "energia",
            "created_at",
        }
        armazenamento.fechar()

    def test_contexto_dia_entry_date_e_primary_key(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute("PRAGMA table_info(contexto_dia)")
        colunas = {linha[1]: linha[5] for linha in cursor.fetchall()}
        assert colunas["entry_date"] == 1
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

    def test_inicializar_duas_vezes_nao_falha_contexto_dia(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento._inicializar()
        armazenamento._inicializar()
        cursor = armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='contexto_dia'"
        )
        assert cursor.fetchone() is not None
        armazenamento.fechar()


class TestSalvar:
    def test_salvar_persiste_id_conteudo_instante(self):
        armazenamento = Armazenamento(":memory:")
        entry = ThoughtEntry(conteudo="primeiro pensamento")
        armazenamento.salvar(entry)
        cursor = armazenamento._conexao.execute(
            "SELECT id, conteudo, instante FROM thoughts WHERE id = ?", (entry.id,)
        )
        linha = cursor.fetchone()
        assert linha == (entry.id, entry.conteudo, entry.instante.isoformat())
        armazenamento.fechar()

    def test_salvar_duas_entries_diferentes(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar(ThoughtEntry(conteudo="pensamento um"))
        armazenamento.salvar(ThoughtEntry(conteudo="pensamento dois"))
        cursor = armazenamento._conexao.execute("SELECT COUNT(*) FROM thoughts")
        assert cursor.fetchone()[0] == 2
        armazenamento.fechar()

    def test_salvar_mesma_entry_duas_vezes_estoura_integridade(self):
        armazenamento = Armazenamento(":memory:")
        entry = ThoughtEntry(conteudo="pensamento repetido")
        armazenamento.salvar(entry)
        with pytest.raises(sqlite3.IntegrityError):
            armazenamento.salvar(entry)
        armazenamento.fechar()


class TestSalvarContexto:
    def test_round_trip(self):
        armazenamento = Armazenamento(":memory:")
        contexto = ContextoAmbiente(
            sono_horas=7.5,
            sono_interrupcoes=1,
            cafeina_mg=100,
            energia={"Trabalho": 40, "Casa & Responsabilidades": 20},
        )
        armazenamento.salvar_contexto("2026-01-01", contexto)
        lido = armazenamento.buscar_contexto("2026-01-01")
        assert lido == contexto
        armazenamento.fechar()

    def test_round_trip_mistura_default_e_custom(self):
        armazenamento = Armazenamento(":memory:")
        contexto = ContextoAmbiente(energia={"Trabalho": 60, "academia": 40})
        armazenamento.salvar_contexto("2026-01-01", contexto)
        lido = armazenamento.buscar_contexto("2026-01-01")
        assert lido == contexto
        assert sum(lido.energia.values()) == 100
        armazenamento.fechar()

    def test_overwrite_mesmo_entry_date(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto(
            "2026-01-01",
            ContextoAmbiente(sono_horas=5, energia={"Trabalho": 10}),
        )
        armazenamento.salvar_contexto(
            "2026-01-01",
            ContextoAmbiente(sono_horas=8, energia={"Casa & Responsabilidades": 30}),
        )
        cursor = armazenamento._conexao.execute(
            "SELECT COUNT(*) FROM contexto_dia"
        )
        assert cursor.fetchone()[0] == 1
        lido = armazenamento.buscar_contexto("2026-01-01")
        assert lido == ContextoAmbiente(
            sono_horas=8, energia={"Casa & Responsabilidades": 30}
        )
        armazenamento.fechar()

    def test_created_at_preservado_no_overwrite(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto("2026-01-01", ContextoAmbiente(sono_horas=5))
        cursor = armazenamento._conexao.execute(
            "SELECT created_at FROM contexto_dia WHERE entry_date = ?",
            ("2026-01-01",),
        )
        created_at_original = cursor.fetchone()[0]

        armazenamento.salvar_contexto("2026-01-01", ContextoAmbiente(sono_horas=8))
        cursor = armazenamento._conexao.execute(
            "SELECT created_at FROM contexto_dia WHERE entry_date = ?",
            ("2026-01-01",),
        )
        created_at_novo = cursor.fetchone()[0]

        assert created_at_original == created_at_novo
        armazenamento.fechar()

    def test_buscar_contexto_inexistente_retorna_none(self):
        armazenamento = Armazenamento(":memory:")
        assert armazenamento.buscar_contexto("2099-12-31") is None
        armazenamento.fechar()


class TestCanonicalizacaoCrossDay:
    def test_custom_canonicaliza_pela_primeira_grafia(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto(
            "2026-01-01", ContextoAmbiente(energia={"academia": 30})
        )
        armazenamento.salvar_contexto(
            "2026-01-02", ContextoAmbiente(energia={"Academia": 40})
        )

        lido = armazenamento.buscar_contexto("2026-01-02")

        assert "academia" in lido.energia
        assert lido.energia["academia"] == 40
        armazenamento.fechar()

    def test_categorias_tem_uma_linha_para_o_custom(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto(
            "2026-01-01", ContextoAmbiente(energia={"academia": 30})
        )
        armazenamento.salvar_contexto(
            "2026-01-02", ContextoAmbiente(energia={"Academia": 40})
        )

        cursor = armazenamento._conexao.execute("SELECT COUNT(*) FROM categorias")
        assert cursor.fetchone()[0] == 1
        armazenamento.fechar()

    def test_default_nao_entra_em_categorias(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto(
            "2026-01-01", ContextoAmbiente(energia={"trabalho": 50})
        )

        cursor = armazenamento._conexao.execute("SELECT COUNT(*) FROM categorias")
        assert cursor.fetchone()[0] == 0
        armazenamento.fechar()

    def test_round_trip_default_e_custom_continua_igual(self):
        armazenamento = Armazenamento(":memory:")
        contexto = ContextoAmbiente(energia={"Trabalho": 60, "academia": 40})
        armazenamento.salvar_contexto("2026-01-01", contexto)
        lido = armazenamento.buscar_contexto("2026-01-01")
        assert lido == contexto
        armazenamento.fechar()


class TestListar:
    def test_listar_retorna_thoughts_ordenados_por_instante(self):
        armazenamento = Armazenamento(":memory:")
        e1 = ThoughtEntry(
            conteudo="primeiro", instante=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        e2 = ThoughtEntry(
            conteudo="segundo", instante=datetime(2026, 1, 2, tzinfo=timezone.utc)
        )
        e3 = ThoughtEntry(
            conteudo="terceiro", instante=datetime(2026, 1, 3, tzinfo=timezone.utc)
        )
        armazenamento.salvar(e3)
        armazenamento.salvar(e1)
        armazenamento.salvar(e2)

        resultado = armazenamento.listar()

        assert len(resultado) == 3
        assert [e.conteudo for e in resultado] == ["primeiro", "segundo", "terceiro"]
        for entry in resultado:
            assert isinstance(entry.instante, datetime)
            assert entry.instante.tzinfo is not None
        armazenamento.fechar()


class TestFechar:
    def test_fechar_encerra_conexao(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.fechar()
        with pytest.raises(sqlite3.ProgrammingError):
            armazenamento._conexao.execute("SELECT 1")
