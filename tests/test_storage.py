import sqlite3
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from limencore.ambient import ContextoAmbiente
from limencore.entry import ThoughtEntry
from limencore.storage import Armazenamento, Dia


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





class TestBuscarPorData:
    TOKYO = ZoneInfo("Asia/Tokyo")  # UTC+9, sem horario de verao: fuso estavel p/ teste

    def test_thought_perto_da_virada_cai_no_dia_local_certo(self):
        armazenamento = Armazenamento(":memory:")
        # 2026-01-02 00:30 em Tokyo == 2026-01-01 15:30 UTC (dia UTC diferente do local)
        virada = ThoughtEntry(
            conteudo="virada",
            instante=datetime(2026, 1, 1, 15, 30, tzinfo=timezone.utc),
        )
        armazenamento.salvar(virada)

        dia_local_correto = armazenamento.buscar_por_data(date(2026, 1, 2), self.TOKYO)
        dia_utc_ingenuo = armazenamento.buscar_por_data(date(2026, 1, 1), self.TOKYO)

        assert [e.conteudo for e in dia_local_correto] == ["virada"]
        assert dia_utc_ingenuo == []
        armazenamento.fechar()



    def test_janela_completa_do_dia_local_inclusiva_exclusiva(self):
        armazenamento = Armazenamento(":memory:")
        inicio_exato = ThoughtEntry(
            conteudo="inicio",
            instante=datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc),  # 00:00 Tokyo 01/02
        )
        fim_do_dia = ThoughtEntry(
            conteudo="fim",
            instante=datetime(2026, 1, 2, 14, 59, 59, tzinfo=timezone.utc),  # 23:59:59 Tokyo 01/02
        )
        proximo_dia = ThoughtEntry(
            conteudo="proximo",
            instante=datetime(2026, 1, 2, 15, 0, 0, tzinfo=timezone.utc),  # 00:00 Tokyo 01/03
        )
        armazenamento.salvar(proximo_dia)
        armazenamento.salvar(inicio_exato)
        armazenamento.salvar(fim_do_dia)

        resultado = armazenamento.buscar_por_data(date(2026, 1, 2), self.TOKYO)

        assert [e.conteudo for e in resultado] == ["inicio", "fim"]
        armazenamento.fechar()



    def test_dia_sem_thoughts_retorna_lista_vazia(self):
        armazenamento = Armazenamento(":memory:")
        assert armazenamento.buscar_por_data(date(2026, 1, 2), self.TOKYO) == []
        armazenamento.fechar()




class TestBuscarDia:
    TOKYO = ZoneInfo("Asia/Tokyo")

    def test_junta_thoughts_e_contexto_do_mesmo_dia(self):
        armazenamento = Armazenamento(":memory:")
        entry = ThoughtEntry(
            conteudo="pensamento",
            instante=datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc),  # 00:00 Tokyo 01/02
        )
        armazenamento.salvar(entry)
        contexto = ContextoAmbiente(sono_horas=7, energia={"Trabalho": 50})
        armazenamento.salvar_contexto("2026-01-02", contexto)

        dia = armazenamento.buscar_dia(date(2026, 1, 2), self.TOKYO)

        assert dia == Dia(thoughts=[entry], contexto=contexto)
        armazenamento.fechar()

    def test_dia_sem_contexto_e_none(self):
        armazenamento = Armazenamento(":memory:")
        entry = ThoughtEntry(
            conteudo="pensamento",
            instante=datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc),
        )
        armazenamento.salvar(entry)

        dia = armazenamento.buscar_dia(date(2026, 1, 2), self.TOKYO)

        assert dia.contexto is None
        assert dia.thoughts == [entry]
        armazenamento.fechar()

    def test_dia_sem_thoughts_e_lista_vazia(self):
        armazenamento = Armazenamento(":memory:")
        contexto = ContextoAmbiente(sono_horas=7)
        armazenamento.salvar_contexto("2026-01-02", contexto)

        dia = armazenamento.buscar_dia(date(2026, 1, 2), self.TOKYO)

        assert dia.thoughts == []
        assert dia.contexto == contexto
        armazenamento.fechar()

    def test_dia_totalmente_vazio(self):
        armazenamento = Armazenamento(":memory:")
        dia = armazenamento.buscar_dia(date(2026, 1, 2), self.TOKYO)
        assert dia == Dia(thoughts=[], contexto=None)
        armazenamento.fechar()





class TestListarContextos:
    def test_intervalo_inclusivo_ordenado(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto("2026-01-03", ContextoAmbiente(sono_horas=6))
        armazenamento.salvar_contexto("2026-01-01", ContextoAmbiente(sono_horas=7))
        armazenamento.salvar_contexto("2026-01-02", ContextoAmbiente(sono_horas=8))

        resultado = armazenamento.listar_contextos("2026-01-01", "2026-01-03")

        assert [d for d, _ in resultado] == ["2026-01-01", "2026-01-02", "2026-01-03"]
        armazenamento.fechar()

    def test_fora_do_intervalo_excluido(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto("2025-12-31", ContextoAmbiente(sono_horas=6))
        armazenamento.salvar_contexto("2026-01-01", ContextoAmbiente(sono_horas=7))
        armazenamento.salvar_contexto("2026-02-01", ContextoAmbiente(sono_horas=8))

        resultado = armazenamento.listar_contextos("2026-01-01", "2026-01-31")

        assert [d for d, _ in resultado] == ["2026-01-01"]
        armazenamento.fechar()

    def test_intervalo_sem_registros_retorna_lista_vazia(self):
        armazenamento = Armazenamento(":memory:")
        assert armazenamento.listar_contextos("2026-01-01", "2026-01-31") == []
        armazenamento.fechar()




class TestFechar:
    def test_fechar_encerra_conexao(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.fechar()
        with pytest.raises(sqlite3.ProgrammingError):
            armazenamento._conexao.execute("SELECT 1")




class TestOffsetHistorico:
    # Complementa a TestBuscarPorData (Tóquio): Tóquio não tem horário
    # de verão, então aquela classe prova a lógica da janela, mas NÃO a escolha de
    # ZoneInfo sobre offset fixo — trocar ZoneInfo("Asia/Tokyo") por um offset fixo
    # de +9 passaria igual. Esta classe usa um fuso COM DST pra travar essa escolha:
    # se alguém trocar ZoneInfo por timezone(timedelta(...)), ela quebra.
    NY = ZoneInfo("America/New_York")  # EDT (UTC-4) no verão, EST (UTC-5) no inverno

    def test_dst_respeitado_offset_fixo_falharia(self):
        armazenamento = Armazenamento(":memory:")
        # 01/07 é verão → EDT (UTC-4). 00:30 local == 04:30 UTC.
        # Com offset fixo EST (-5), 04:30 UTC viraria 23:30 de 30/06 e cairia no dia
        # anterior — o thought sumiria da busca por 01/07. ZoneInfo evita isso.
        t = ThoughtEntry(
            conteudo="verao",
            instante=datetime(2026, 7, 1, 4, 30, tzinfo=timezone.utc),
        )
        armazenamento.salvar(t)
        resultado = armazenamento.buscar_por_data(date(2026, 7, 1), self.NY)
        assert [e.conteudo for e in resultado] == ["verao"]
        armazenamento.fechar()




class TestListarContextosEnergia: 
    # Estende a TestListarContextos, que só verificava sono_horas.que só verificava sono_horas.
    # Aqui provamos que a ENERGIA (o JSON) sobrevive o round-trip e que o ramo
    # `energia or "{}"` (contexto salvo sem energia) não quebra o parse.

    def test_energia_sobrevive_round_trip(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto("2026-01-01", ContextoAmbiente(energia={"Trabalho": 40}))
        [(_, via_lista)] = armazenamento.listar_contextos("2026-01-01", "2026-01-01")
        # cruza os dois caminhos de leitura: listar_contextos tem que remontar o
        # mesmo ContextoAmbiente que buscar_contexto devolve.
        assert via_lista == armazenamento.buscar_contexto("2026-01-01")
        assert via_lista.energia == {"Trabalho": 40}
        armazenamento.fechar()
        

    def test_contexto_sem_energia_volta_dict_vazio(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar_contexto("2026-01-01", ContextoAmbiente(sono_horas=7))
        [(_, ctx)] = armazenamento.listar_contextos("2026-01-01", "2026-01-01")
        assert ctx.energia == {}
        armazenamento.fechar()