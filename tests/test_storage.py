import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from limencore.ambient import ContextoAmbiente
from limencore.despejo import Despejo
from limencore.fio import EstadoFio, Fio, TransicaoInvalida
from limencore.nota import TipoNota
from limencore.storage import Armazenamento, Dia


class TestCriacao:
    def test_tabela_thoughts_existe(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='despejos'"
        )
        assert cursor.fetchone() is not None
        armazenamento.fechar()

    def test_colunas_esperadas(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute("PRAGMA table_info(despejos)")
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
            "SELECT name FROM sqlite_master WHERE type='table' AND name='despejos'"
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
        entry = Despejo(conteudo="primeiro pensamento")
        armazenamento.salvar(entry)
        cursor = armazenamento._conexao.execute(
            "SELECT id, conteudo, instante FROM despejos WHERE id = ?", (entry.id,)
        )
        linha = cursor.fetchone()
        assert linha == (entry.id, entry.conteudo, entry.instante.isoformat())
        armazenamento.fechar()

    def test_salvar_duas_entries_diferentes(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar(Despejo(conteudo="pensamento um"))
        armazenamento.salvar(Despejo(conteudo="pensamento dois"))
        cursor = armazenamento._conexao.execute("SELECT COUNT(*) FROM despejos")
        assert cursor.fetchone()[0] == 2
        armazenamento.fechar()

    def test_salvar_mesma_entry_duas_vezes_estoura_integridade(self):
        armazenamento = Armazenamento(":memory:")
        entry = Despejo(conteudo="pensamento repetido")
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
        e1 = Despejo(
            conteudo="primeiro", instante=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        e2 = Despejo(
            conteudo="segundo", instante=datetime(2026, 1, 2, tzinfo=timezone.utc)
        )
        e3 = Despejo(
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
        virada = Despejo(
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
        inicio_exato = Despejo(
            conteudo="inicio",
            instante=datetime(2026, 1, 1, 15, 0, 0, tzinfo=timezone.utc),  # 00:00 Tokyo 01/02
        )
        fim_do_dia = Despejo(
            conteudo="fim",
            instante=datetime(2026, 1, 2, 14, 59, 59, tzinfo=timezone.utc),  # 23:59:59 Tokyo 01/02
        )
        proximo_dia = Despejo(
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
        entry = Despejo(
            conteudo="pensamento",
            instante=datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc),  # 00:00 Tokyo 01/02
        )
        armazenamento.salvar(entry)
        contexto = ContextoAmbiente(sono_horas=7, energia={"Trabalho": 50})
        armazenamento.salvar_contexto("2026-01-02", contexto)

        dia = armazenamento.buscar_dia(date(2026, 1, 2), self.TOKYO)

        assert dia == Dia(despejos=[entry], contexto=contexto)
        armazenamento.fechar()

    def test_dia_sem_contexto_e_none(self):
        armazenamento = Armazenamento(":memory:")
        entry = Despejo(
            conteudo="pensamento",
            instante=datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc),
        )
        armazenamento.salvar(entry)

        dia = armazenamento.buscar_dia(date(2026, 1, 2), self.TOKYO)

        assert dia.contexto is None
        assert dia.despejos == [entry]
        armazenamento.fechar()

    def test_dia_sem_thoughts_e_lista_vazia(self):
        armazenamento = Armazenamento(":memory:")
        contexto = ContextoAmbiente(sono_horas=7)
        armazenamento.salvar_contexto("2026-01-02", contexto)

        dia = armazenamento.buscar_dia(date(2026, 1, 2), self.TOKYO)

        assert dia.despejos == []
        assert dia.contexto == contexto
        armazenamento.fechar()

    def test_dia_totalmente_vazio(self):
        armazenamento = Armazenamento(":memory:")
        dia = armazenamento.buscar_dia(date(2026, 1, 2), self.TOKYO)
        assert dia == Dia(despejos=[], contexto=None)
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
        t = Despejo(
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


class TestMigracaoThoughts:
    def _criar_banco_antigo(self, caminho: str, id_: str, conteudo: str, instante: str):
        conexao = sqlite3.connect(caminho)
        conexao.execute(
            """
            CREATE TABLE thoughts (
                id TEXT PRIMARY KEY,
                conteudo TEXT NOT NULL,
                instante TEXT NOT NULL
            )
            """
        )
        conexao.execute(
            "INSERT INTO thoughts (id, conteudo, instante) VALUES (?, ?, ?)",
            (id_, conteudo, instante),
        )
        conexao.commit()
        conexao.close()

    def test_banco_antigo_e_migrado(self, tmp_path):
        caminho = tmp_path / "antigo.db"
        id_ = str(uuid.uuid4())
        instante = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        self._criar_banco_antigo(str(caminho), id_, "pensamento antigo", instante)

        armazenamento = Armazenamento(str(caminho))
        resultado = armazenamento.listar()

        assert len(resultado) == 1
        assert isinstance(resultado[0], Despejo)
        assert resultado[0].id == id_

        tabelas = {
            nome for (nome,) in armazenamento._conexao.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "thoughts" not in tabelas
        assert "despejos" in tabelas
        armazenamento.fechar()

    def test_migracao_idempotente(self, tmp_path):
        caminho = tmp_path / "antigo.db"
        id_ = str(uuid.uuid4())
        instante = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
        self._criar_banco_antigo(str(caminho), id_, "pensamento antigo", instante)

        armazenamento1 = Armazenamento(str(caminho))
        armazenamento1.fechar()

        armazenamento2 = Armazenamento(str(caminho))
        cursor = armazenamento2._conexao.execute("SELECT COUNT(*) FROM despejos")
        assert cursor.fetchone()[0] == 1
        armazenamento2.fechar()


class TestFios:
    def test_tabela_fios_existe(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fios'"
        )
        assert cursor.fetchone() is not None
        armazenamento.fechar()

    def test_salvar_e_buscar(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento com fios")
        armazenamento.salvar(despejo)
        fio1 = Fio(
            despejo_id=despejo.id,
            criado_em=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        )
        fio2 = Fio(
            despejo_id=despejo.id,
            criado_em=datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
        )
        armazenamento.salvar_fio(fio2)
        armazenamento.salvar_fio(fio1)
        assert armazenamento.buscar_fios(despejo.id) == [fio1, fio2]
        armazenamento.fechar()

    def test_buscar_despejo_sem_fios(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento sem fios")
        armazenamento.salvar(despejo)
        assert armazenamento.buscar_fios(despejo.id) == []
        armazenamento.fechar()

    def test_fio_de_despejo_inexistente_falha(self):
        armazenamento = Armazenamento(":memory:")
        with pytest.raises(sqlite3.IntegrityError):
            armazenamento.salvar_fio(Fio(despejo_id=str(uuid.uuid4())))
        armazenamento.fechar()

    def test_estado_gravado_pelo_nome(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        fio = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio)
        armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
        cursor = armazenamento._conexao.execute("SELECT estado FROM fios")
        assert cursor.fetchone()[0] == "ESCOLHIDO"
        armazenamento.fechar()

    def test_atualizar_estado_persiste(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        fio = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio)
        retorno = armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
        assert retorno.estado is EstadoFio.ESCOLHIDO
        [salvo] = armazenamento.buscar_fios(despejo.id)
        assert salvo.estado is EstadoFio.ESCOLHIDO
        armazenamento.fechar()

    def test_atualizar_transicao_invalida_nao_grava(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        fio = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio)
        with pytest.raises(TransicaoInvalida):
            armazenamento.atualizar_estado(fio, EstadoFio.RESOLVIDO)
        [salvo] = armazenamento.buscar_fios(despejo.id)
        assert salvo.estado is EstadoFio.JOGADO
        armazenamento.fechar()

    def test_atualizar_com_fio_desatualizado_falha(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        fio_antigo = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio_antigo)
        armazenamento.atualizar_estado(fio_antigo, EstadoFio.ESCOLHIDO)
        with pytest.raises(ValueError, match="desatualizado"):
            armazenamento.atualizar_estado(fio_antigo, EstadoFio.GUARDADO)
        [salvo] = armazenamento.buscar_fios(despejo.id)
        assert salvo.estado is EstadoFio.ESCOLHIDO
        armazenamento.fechar()


MAIS_5 = timezone(timedelta(hours=5))
MENOS_3 = timezone(timedelta(hours=-3))


class TestUtcNaGravacao:
    def _despejo_mais_5(self):
        return Despejo(
            conteudo="pensamento em outro fuso",
            instante=datetime(2026, 1, 2, 1, 0, tzinfo=MAIS_5),
        )

    def test_despejo_gravado_em_utc(self):
        armazenamento = Armazenamento(":memory:")
        armazenamento.salvar(self._despejo_mais_5())
        cursor = armazenamento._conexao.execute("SELECT instante FROM despejos")
        assert cursor.fetchone()[0] == "2026-01-01T20:00:00+00:00"
        armazenamento.fechar()

    def test_despejo_lido_e_o_mesmo_instante(self):
        armazenamento = Armazenamento(":memory:")
        original = self._despejo_mais_5()
        armazenamento.salvar(original)
        [lido] = armazenamento.listar()
        assert lido.instante == original.instante
        assert lido.instante.utcoffset() == timedelta(0)
        armazenamento.fechar()

    def test_buscar_por_data_com_fuso_nao_utc(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo_mais_5()
        armazenamento.salvar(despejo)
        dia_1 = armazenamento.buscar_por_data(date(2026, 1, 1), ZoneInfo("UTC"))
        dia_2 = armazenamento.buscar_por_data(date(2026, 1, 2), ZoneInfo("UTC"))
        assert [d.id for d in dia_1] == [despejo.id]
        assert despejo.id not in [d.id for d in dia_2]
        armazenamento.fechar()

    def test_listar_ordena_por_instante_real(self):
        armazenamento = Armazenamento(":memory:")
        a = Despejo(
            conteudo="despejo A",
            instante=datetime(2026, 1, 1, 12, 0, tzinfo=MENOS_3),
        )
        b = Despejo(
            conteudo="despejo B",
            instante=datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc),
        )
        armazenamento.salvar(a)
        armazenamento.salvar(b)
        assert [d.id for d in armazenamento.listar()] == [b.id, a.id]
        armazenamento.fechar()

    def test_fio_gravado_em_utc(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        armazenamento.salvar_fio(
            Fio(
                despejo_id=despejo.id,
                criado_em=datetime(2026, 1, 2, 1, 0, tzinfo=MAIS_5),
            )
        )
        cursor = armazenamento._conexao.execute("SELECT criado_em FROM fios")
        assert cursor.fetchone()[0] == "2026-01-01T20:00:00+00:00"
        armazenamento.fechar()

    def test_buscar_fios_ordena_por_instante_real(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        fio_a = Fio(
            despejo_id=despejo.id,
            criado_em=datetime(2026, 1, 1, 12, 0, tzinfo=MENOS_3),
        )
        fio_b = Fio(
            despejo_id=despejo.id,
            criado_em=datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc),
        )
        armazenamento.salvar_fio(fio_a)
        armazenamento.salvar_fio(fio_b)
        assert [f.id for f in armazenamento.buscar_fios(despejo.id)] == [
            fio_b.id,
            fio_a.id,
        ]
        armazenamento.fechar()


class TestHistorico:
    def _fio_salvo(self, armazenamento):
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        fio = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio)
        return fio

    def test_tabela_transicoes_existe(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='transicoes'"
        )
        assert cursor.fetchone() is not None
        armazenamento.fechar()

    def test_salvar_fio_registra_nascimento(self):
        armazenamento = Armazenamento(":memory:")
        fio = self._fio_salvo(armazenamento)
        [nascimento] = armazenamento.historico(fio.id)
        assert nascimento.fio_id == fio.id
        assert nascimento.de is None
        assert nascimento.para is EstadoFio.JOGADO
        armazenamento.fechar()

    def test_historico_completo_em_ordem(self):
        armazenamento = Armazenamento(":memory:")
        fio = self._fio_salvo(armazenamento)
        fio = armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
        fio = armazenamento.atualizar_estado(fio, EstadoFio.GUARDADO)
        fio = armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
        assert [(t.de, t.para) for t in armazenamento.historico(fio.id)] == [
            (None, EstadoFio.JOGADO),
            (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO),
            (EstadoFio.ESCOLHIDO, EstadoFio.GUARDADO),
            (EstadoFio.GUARDADO, EstadoFio.ESCOLHIDO),
        ]
        armazenamento.fechar()

    def test_transicao_invalida_nao_registra(self):
        armazenamento = Armazenamento(":memory:")
        fio = self._fio_salvo(armazenamento)
        with pytest.raises(TransicaoInvalida):
            armazenamento.atualizar_estado(fio, EstadoFio.RESOLVIDO)
        assert len(armazenamento.historico(fio.id)) == 1
        armazenamento.fechar()

    def test_fio_desatualizado_nao_registra(self):
        armazenamento = Armazenamento(":memory:")
        fio = self._fio_salvo(armazenamento)
        armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
        with pytest.raises(ValueError, match="desatualizado"):
            armazenamento.atualizar_estado(fio, EstadoFio.GUARDADO)
        assert len(armazenamento.historico(fio.id)) == 2
        armazenamento.fechar()

    def test_instante_em_utc(self):
        armazenamento = Armazenamento(":memory:")
        fio = self._fio_salvo(armazenamento)
        (bruto,) = armazenamento._conexao.execute(
            "SELECT instante FROM transicoes"
        ).fetchone()
        assert bruto.endswith("+00:00")
        [nascimento] = armazenamento.historico(fio.id)
        assert nascimento.instante.utcoffset() == timedelta(0)
        armazenamento.fechar()

    def test_historico_de_fio_inexistente(self):
        armazenamento = Armazenamento(":memory:")
        assert armazenamento.historico(str(uuid.uuid4())) == []
        armazenamento.fechar()

    def test_historicos_separados_por_fio(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento com dois fios")
        armazenamento.salvar(despejo)
        fio_a = Fio(despejo_id=despejo.id)
        fio_b = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio_a)
        armazenamento.salvar_fio(fio_b)
        armazenamento.atualizar_estado(fio_a, EstadoFio.ESCOLHIDO)
        historico_a = armazenamento.historico(fio_a.id)
        historico_b = armazenamento.historico(fio_b.id)
        assert all(t.fio_id == fio_a.id for t in historico_a)
        assert all(t.fio_id == fio_b.id for t in historico_b)
        assert [(t.de, t.para) for t in historico_a] == [
            (None, EstadoFio.JOGADO),
            (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO),
        ]
        assert [(t.de, t.para) for t in historico_b] == [(None, EstadoFio.JOGADO)]
        armazenamento.fechar()


class TestAtomicidade:
    def _falhar(self, *args, **kwargs):
        raise RuntimeError("falha simulada no registro")

    def test_salvar_fio_desfaz_se_transicao_falhar(self, monkeypatch):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        monkeypatch.setattr(armazenamento, "_registrar_transicao", self._falhar)
        with pytest.raises(RuntimeError):
            armazenamento.salvar_fio(Fio(despejo_id=despejo.id))
        assert armazenamento.buscar_fios(despejo.id) == []
        armazenamento.fechar()

    def test_atualizar_estado_desfaz_se_transicao_falhar(self, monkeypatch):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        fio = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio)
        monkeypatch.setattr(armazenamento, "_registrar_transicao", self._falhar)
        with pytest.raises(RuntimeError):
            armazenamento.atualizar_estado(fio, EstadoFio.ESCOLHIDO)
        [salvo] = armazenamento.buscar_fios(despejo.id)
        assert salvo.estado is EstadoFio.JOGADO
        assert len(armazenamento.historico(fio.id)) == 1
        armazenamento.fechar()


def _levar_a(armazenamento, fio, estado):
    caminhos = {
        EstadoFio.JOGADO: [],
        EstadoFio.ESCOLHIDO: [EstadoFio.ESCOLHIDO],
        EstadoFio.GUARDADO: [EstadoFio.GUARDADO],
        EstadoFio.RESOLVIDO: [EstadoFio.ESCOLHIDO, EstadoFio.RESOLVIDO],
        EstadoFio.DESCARTADO: [EstadoFio.DESCARTADO],
    }
    for passo in caminhos[estado]:
        fio = armazenamento.atualizar_estado(fio, passo)
    return fio


class TestMesa:
    def _despejo(self, armazenamento):
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        return despejo

    def _fio(self, armazenamento, despejo, estado=EstadoFio.JOGADO, criado_em=None):
        fio = Fio(despejo_id=despejo.id) if criado_em is None else Fio(
            despejo_id=despejo.id, criado_em=criado_em
        )
        armazenamento.salvar_fio(fio)
        return _levar_a(armazenamento, fio, estado)

    def test_mesa_vazia(self):
        armazenamento = Armazenamento(":memory:")
        assert armazenamento.mesa() == []
        armazenamento.fechar()

    def test_so_abertos(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        jogado = self._fio(armazenamento, despejo, EstadoFio.JOGADO)
        escolhido = self._fio(armazenamento, despejo, EstadoFio.ESCOLHIDO)
        for estado in (EstadoFio.GUARDADO, EstadoFio.RESOLVIDO, EstadoFio.DESCARTADO):
            self._fio(armazenamento, despejo, estado)
        mesa = armazenamento.mesa()
        assert len(mesa) == 2
        assert set(mesa) == {jogado, escolhido}
        armazenamento.fechar()

    def test_escolhido_primeiro(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        self._fio(armazenamento, despejo, criado_em=base)
        self._fio(armazenamento, despejo, criado_em=base + timedelta(hours=1))
        escolhido = self._fio(
            armazenamento, despejo, EstadoFio.ESCOLHIDO, criado_em=base + timedelta(hours=2)
        )
        mesa = armazenamento.mesa()
        assert mesa[0] == escolhido
        assert [f.estado for f in mesa[1:]] == [EstadoFio.JOGADO, EstadoFio.JOGADO]
        armazenamento.fechar()

    def test_ordem_do_despejo(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        terceiro = self._fio(armazenamento, despejo, criado_em=base + timedelta(hours=2))
        primeiro = self._fio(armazenamento, despejo, criado_em=base)
        segundo = self._fio(armazenamento, despejo, criado_em=base + timedelta(hours=1))
        assert armazenamento.mesa() == [primeiro, segundo, terceiro]
        armazenamento.fechar()

    def test_todos_os_despejos(self):
        armazenamento = Armazenamento(":memory:")
        despejo_a = self._despejo(armazenamento)
        despejo_b = self._despejo(armazenamento)
        fio_a = self._fio(armazenamento, despejo_a)
        fio_b = self._fio(armazenamento, despejo_b)
        assert set(armazenamento.mesa()) == {fio_a, fio_b}
        armazenamento.fechar()


class TestGuardados:
    def _despejo(self, armazenamento):
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        return despejo

    def _fio(self, armazenamento, despejo, estado=EstadoFio.JOGADO):
        fio = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio)
        return _levar_a(armazenamento, fio, estado)

    def _envelhecer_guardado(self, armazenamento, fio_id, instante):
        armazenamento._conexao.execute(
            "UPDATE transicoes SET instante = ? WHERE fio_id = ? AND para = 'GUARDADO'",
            (instante, fio_id),
        )
        armazenamento._conexao.commit()

    def test_guardados_vazio(self):
        armazenamento = Armazenamento(":memory:")
        assert armazenamento.guardados() == []
        armazenamento.fechar()

    def test_so_guardados(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        for estado in (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO,
                       EstadoFio.RESOLVIDO, EstadoFio.DESCARTADO):
            self._fio(armazenamento, despejo, estado)
        guardado = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        assert armazenamento.guardados() == [guardado]
        armazenamento.fechar()

    def test_mais_recente_primeiro(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        a = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        b = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        assert [f.id for f in armazenamento.guardados()] == [b.id, a.id]
        armazenamento.fechar()

    def test_reguardar_volta_pro_topo(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        a = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        b = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        a = armazenamento.atualizar_estado(a, EstadoFio.ESCOLHIDO)
        a = armazenamento.atualizar_estado(a, EstadoFio.GUARDADO)
        assert [f.id for f in armazenamento.guardados()] == [a.id, b.id]
        armazenamento.fechar()

    def test_puxado_sai_da_lista(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        a = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        armazenamento.atualizar_estado(a, EstadoFio.ESCOLHIDO)
        assert armazenamento.guardados() == []
        armazenamento.fechar()

    def test_desde_filtra(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        a = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        b = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        self._envelhecer_guardado(armazenamento, a.id, "2026-01-01T00:00:00+00:00")
        desde = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert [f.id for f in armazenamento.guardados(desde=desde)] == [b.id]
        assert [f.id for f in armazenamento.guardados()] == [b.id, a.id]
        armazenamento.fechar()

    def test_desde_com_fuso_nao_utc(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        a = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        b = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        self._envelhecer_guardado(armazenamento, a.id, "2026-01-01T00:00:00+00:00")
        desde = datetime(2026, 5, 31, 21, 0, tzinfo=MENOS_3)  # = 2026-06-01T00:00 UTC
        assert [f.id for f in armazenamento.guardados(desde=desde)] == [b.id]
        assert [f.id for f in armazenamento.guardados()] == [b.id, a.id]
        armazenamento.fechar()

    def test_desde_sem_timezone_falha(self):
        armazenamento = Armazenamento(":memory:")
        with pytest.raises(ValueError, match="timezone"):
            armazenamento.guardados(desde=datetime(2026, 1, 1))
        armazenamento.fechar()

    def test_guardado_sem_historico_nao_some(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        legado_id = str(uuid.uuid4())
        armazenamento._conexao.execute(
            "INSERT INTO fios (id, despejo_id, estado, criado_em) VALUES (?, ?, ?, ?)",
            (legado_id, despejo.id, "GUARDADO", "2025-01-01T00:00:00+00:00"),
        )
        armazenamento._conexao.commit()
        b = self._fio(armazenamento, despejo, EstadoFio.GUARDADO)
        assert [f.id for f in armazenamento.guardados()] == [b.id, legado_id]
        desde = datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert [f.id for f in armazenamento.guardados(desde=desde)] == [b.id]
        armazenamento.fechar()


class TestAssuntos:
    def _fio_salvo(self, armazenamento):
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        fio = Fio(despejo_id=despejo.id)
        armazenamento.salvar_fio(fio)
        return fio

    def test_tabela_assuntos_existe(self):
        armazenamento = Armazenamento(":memory:")
        cursor = armazenamento._conexao.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='assuntos'"
        )
        assert cursor.fetchone() is not None
        armazenamento.fechar()

    def test_primeira_grafia_vence(self):
        armazenamento = Armazenamento(":memory:")
        primeiro = armazenamento.registrar_assunto("A Saída do Chefe")
        segundo = armazenamento.registrar_assunto("a  saída do CHEFE")
        assert primeiro == segundo
        assert segundo.rotulo == "A Saída do Chefe"
        (total,) = armazenamento._conexao.execute("SELECT COUNT(*) FROM assuntos").fetchone()
        assert total == 1
        armazenamento.fechar()

    def test_marcar_persiste(self):
        armazenamento = Armazenamento(":memory:")
        fio = self._fio_salvo(armazenamento)
        retorno = armazenamento.marcar_assunto(fio, "A Saída do Chefe")
        assert retorno.assunto_chave == "a saída do chefe"
        [salvo] = armazenamento.buscar_fios(fio.despejo_id)
        assert salvo.assunto_chave == "a saída do chefe"
        assert salvo == retorno
        armazenamento.fechar()

    def test_grafias_diferentes_mesmo_assunto(self):
        armazenamento = Armazenamento(":memory:")
        fio_a = armazenamento.marcar_assunto(self._fio_salvo(armazenamento), "Chefe")
        fio_b = armazenamento.marcar_assunto(self._fio_salvo(armazenamento), "chefe ")
        assert fio_a.assunto_chave == fio_b.assunto_chave == "chefe"
        armazenamento.fechar()

    def test_remarcar_troca(self):
        armazenamento = Armazenamento(":memory:")
        fio = self._fio_salvo(armazenamento)
        fio = armazenamento.marcar_assunto(fio, "chefe")
        fio = armazenamento.marcar_assunto(fio, "mãe")
        [salvo] = armazenamento.buscar_fios(fio.despejo_id)
        assert salvo.assunto_chave == "mãe"
        armazenamento.fechar()

    def test_marcar_nao_muda_estado_nem_historico(self):
        armazenamento = Armazenamento(":memory:")
        fio = self._fio_salvo(armazenamento)
        armazenamento.marcar_assunto(fio, "chefe")
        [salvo] = armazenamento.buscar_fios(fio.despejo_id)
        assert salvo.estado is EstadoFio.JOGADO
        assert len(armazenamento.historico(fio.id)) == 1
        armazenamento.fechar()

    def test_marcar_fio_inexistente_desfaz(self):
        armazenamento = Armazenamento(":memory:")
        nunca_salvo = Fio(despejo_id=str(uuid.uuid4()))
        with pytest.raises(ValueError, match="nao encontrado"):
            armazenamento.marcar_assunto(nunca_salvo, "chefe")
        assert armazenamento.buscar_assunto("chefe") is None
        (total,) = armazenamento._conexao.execute("SELECT COUNT(*) FROM assuntos").fetchone()
        assert total == 0
        armazenamento.fechar()

    def test_buscar_assunto_inexistente(self):
        armazenamento = Armazenamento(":memory:")
        assert armazenamento.buscar_assunto("chefe") is None
        armazenamento.fechar()

    def test_mesa_e_guardados_trazem_assunto(self):
        armazenamento = Armazenamento(":memory:")
        fio = armazenamento.marcar_assunto(self._fio_salvo(armazenamento), "Chefe")
        [na_mesa] = armazenamento.mesa()
        assert na_mesa.assunto_chave == "chefe"
        fio = armazenamento.atualizar_estado(fio, EstadoFio.GUARDADO)
        [guardado] = armazenamento.guardados()
        assert guardado.assunto_chave == "chefe"
        assert guardado == fio
        armazenamento.fechar()

    def test_migracao_coluna_assunto(self, tmp_path):
        caminho = str(tmp_path / "antigo.db")
        despejo_id = str(uuid.uuid4())
        fio_id = str(uuid.uuid4())
        conexao = sqlite3.connect(caminho)
        conexao.execute(
            """
            CREATE TABLE despejos (
                id TEXT PRIMARY KEY,
                conteudo TEXT NOT NULL,
                instante TEXT NOT NULL
            )
            """
        )
        conexao.execute(
            """
            CREATE TABLE fios (
                id TEXT PRIMARY KEY,
                despejo_id TEXT NOT NULL REFERENCES despejos(id),
                estado TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )
        conexao.execute(
            "INSERT INTO despejos (id, conteudo, instante) VALUES (?, ?, ?)",
            (despejo_id, "pensamento antigo", "2026-01-01T00:00:00+00:00"),
        )
        conexao.execute(
            "INSERT INTO fios (id, despejo_id, estado, criado_em) VALUES (?, ?, ?, ?)",
            (fio_id, despejo_id, "JOGADO", "2026-01-01T00:00:00+00:00"),
        )
        conexao.commit()
        conexao.close()

        armazenamento = Armazenamento(caminho)
        colunas = {
            linha[1] for linha in armazenamento._conexao.execute("PRAGMA table_info(fios)")
        }
        assert "assunto_chave" in colunas
        [fio] = armazenamento.buscar_fios(despejo_id)
        assert fio.id == fio_id
        assert fio.assunto_chave is None
        armazenamento.fechar()

        de_novo = Armazenamento(caminho)
        assert [f.id for f in de_novo.buscar_fios(despejo_id)] == [fio_id]
        de_novo.fechar()


class TestFiosDoAssunto:
    def _despejo(self, armazenamento):
        despejo = Despejo(conteudo="pensamento")
        armazenamento.salvar(despejo)
        return despejo

    def _fio(self, armazenamento, despejo, assunto=None, criado_em=None):
        fio = Fio(despejo_id=despejo.id) if criado_em is None else Fio(
            despejo_id=despejo.id, criado_em=criado_em
        )
        armazenamento.salvar_fio(fio)
        if assunto is not None:
            fio = armazenamento.marcar_assunto(fio, assunto)
        return fio

    def test_assunto_sem_fios(self):
        armazenamento = Armazenamento(":memory:")
        assert armazenamento.fios_do_assunto("chefe") == []
        armazenamento.fechar()

    def test_so_fios_do_assunto(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        do_chefe = self._fio(armazenamento, despejo, "chefe")
        self._fio(armazenamento, despejo, "mãe")
        self._fio(armazenamento, despejo)
        assert armazenamento.fios_do_assunto("chefe") == [do_chefe]
        armazenamento.fechar()

    def test_despejos_diferentes_em_ordem_de_criacao(self):
        armazenamento = Armazenamento(":memory:")
        despejo_a = self._despejo(armazenamento)
        despejo_b = self._despejo(armazenamento)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        terceiro = self._fio(armazenamento, despejo_a, "chefe", base + timedelta(hours=2))
        primeiro = self._fio(armazenamento, despejo_b, "chefe", base)
        segundo = self._fio(armazenamento, despejo_a, "chefe", base + timedelta(hours=1))
        assert armazenamento.fios_do_assunto("chefe") == [primeiro, segundo, terceiro]
        armazenamento.fechar()

    def test_todos_os_estados(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        resolvido = _levar_a(
            armazenamento, self._fio(armazenamento, despejo, "chefe", base), EstadoFio.RESOLVIDO
        )
        descartado = _levar_a(
            armazenamento,
            self._fio(armazenamento, despejo, "chefe", base + timedelta(hours=1)),
            EstadoFio.DESCARTADO,
        )
        assert armazenamento.fios_do_assunto("chefe") == [resolvido, descartado]
        armazenamento.fechar()

    def test_grafias_diferentes_acham_o_mesmo(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        fio = self._fio(armazenamento, despejo, "Chefe")
        assert armazenamento.fios_do_assunto("  chefe ") == [fio]
        armazenamento.fechar()

    def test_desde_filtra(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        self._fio(armazenamento, despejo, "chefe", datetime(2026, 1, 1, tzinfo=timezone.utc))
        novo = self._fio(
            armazenamento, despejo, "chefe", datetime(2026, 7, 1, tzinfo=timezone.utc)
        )
        desde = datetime(2026, 6, 1, tzinfo=timezone.utc)
        assert armazenamento.fios_do_assunto("chefe", desde=desde) == [novo]
        assert len(armazenamento.fios_do_assunto("chefe")) == 2
        armazenamento.fechar()

    def test_desde_com_fuso_nao_utc(self):
        armazenamento = Armazenamento(":memory:")
        despejo = self._despejo(armazenamento)
        base = datetime(2026, 6, 1, tzinfo=timezone.utc)
        self._fio(armazenamento, despejo, "chefe", base - timedelta(minutes=1))
        self._fio(armazenamento, despejo, "chefe", base)
        self._fio(armazenamento, despejo, "chefe", base + timedelta(hours=1))
        em_utc = armazenamento.fios_do_assunto("chefe", desde=base)
        desde = datetime(2026, 5, 31, 21, 0, tzinfo=MENOS_3)  # = 2026-06-01T00:00 UTC
        assert armazenamento.fios_do_assunto("chefe", desde=desde) == em_utc
        assert len(em_utc) == 2
        armazenamento.fechar()

    def test_desde_sem_timezone_falha(self):
        armazenamento = Armazenamento(":memory:")
        with pytest.raises(ValueError, match="timezone"):
            armazenamento.fios_do_assunto("chefe", desde=datetime(2026, 1, 1))
        armazenamento.fechar()

    def test_texto_vazio_falha(self):
        armazenamento = Armazenamento(":memory:")
        with pytest.raises(ValueError):
            armazenamento.fios_do_assunto("   ")
        armazenamento.fechar()


class TestSalvarDespejoComFios:
    def test_grava_despejo_e_fios_com_nascimento(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="dois fios")
        fios = [Fio(despejo_id=despejo.id), Fio(despejo_id=despejo.id)]
        armazenamento.salvar_despejo_com_fios(despejo, fios)
        assert [d.id for d in armazenamento.listar()] == [despejo.id]
        assert {f.id for f in armazenamento.buscar_fios(despejo.id)} == {f.id for f in fios}
        for fio in fios:
            historico = armazenamento.historico(fio.id)
            assert len(historico) == 1
            assert historico[0].de is None
            assert historico[0].para is EstadoFio.JOGADO
        armazenamento.fechar()

    def test_lista_vazia_levanta_e_nao_grava(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="sem fio")
        with pytest.raises(ValueError, match="ao menos um fio"):
            armazenamento.salvar_despejo_com_fios(despejo, [])
        assert armazenamento.listar() == []
        armazenamento.fechar()

    def test_fio_de_outro_despejo_levanta_e_nao_grava(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="meu")
        outro = Despejo(conteudo="outro")
        fios = [Fio(despejo_id=despejo.id), Fio(despejo_id=outro.id)]
        with pytest.raises(ValueError, match="fio de outro despejo"):
            armazenamento.salvar_despejo_com_fios(despejo, fios)
        assert armazenamento.listar() == []
        assert armazenamento.buscar_fios(despejo.id) == []
        armazenamento.fechar()

    def test_falha_no_meio_desfaz_tudo(self, monkeypatch):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="vai falhar")

        def falhar(fio):
            raise RuntimeError("falha simulada")

        monkeypatch.setattr(armazenamento, "_inserir_fio", falhar)
        with pytest.raises(RuntimeError):
            armazenamento.salvar_despejo_com_fios(despejo, [Fio(despejo_id=despejo.id)])
        assert armazenamento.listar() == []
        armazenamento.fechar()


def _fio_salvo(armazenamento, estado=EstadoFio.JOGADO):
    despejo = Despejo(conteudo="um despejo")
    fio = Fio(despejo_id=despejo.id)
    armazenamento.salvar_despejo_com_fios(despejo, [fio])
    return _levar_a(armazenamento, fio, estado)


class TestQuarto:
    def test_escrever_em_escolhido_grava_nota(self):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        nota = armazenamento.escrever(fio, "primeira")
        assert nota.tipo is TipoNota.NOTA
        assert nota.texto == "primeira"
        assert armazenamento.notas(fio.id) == [nota]
        armazenamento.fechar()

    def test_tres_notas_voltam_em_ordem(self):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        for texto in ["um", "dois", "tres"]:
            armazenamento.escrever(fio, texto)
        assert [n.texto for n in armazenamento.notas(fio.id)] == ["um", "dois", "tres"]
        armazenamento.fechar()

    @pytest.mark.parametrize("estado", [EstadoFio.JOGADO, EstadoFio.GUARDADO])
    def test_escrever_fora_do_quarto_levanta(self, estado):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, estado)
        with pytest.raises(ValueError, match="fora do quarto"):
            armazenamento.escrever(fio, "nao entra")
        assert armazenamento.notas(fio.id) == []
        armazenamento.fechar()

    def test_fio_desatualizado_levanta(self):
        armazenamento = Armazenamento(":memory:")
        escolhido = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        armazenamento.atualizar_estado(escolhido, EstadoFio.GUARDADO)
        with pytest.raises(ValueError):
            armazenamento.escrever(escolhido, "nao entra")
        assert armazenamento.notas(escolhido.id) == []
        armazenamento.fechar()

    def test_texto_vazio_levanta(self):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        with pytest.raises(ValueError):
            armazenamento.escrever(fio, "   ")
        assert armazenamento.notas(fio.id) == []
        armazenamento.fechar()

    def test_escrever_nao_muda_estado_nem_historico(self):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        historico_antes = armazenamento.historico(fio.id)
        armazenamento.escrever(fio, "so escrevo")
        assert armazenamento.buscar_fios(fio.despejo_id)[0].estado is EstadoFio.ESCOLHIDO
        assert armazenamento.historico(fio.id) == historico_antes
        armazenamento.fechar()


class TestPouso:
    def test_pousar_resolve_e_grava_pouso(self):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        armazenamento.escrever(fio, "antes")
        novo = armazenamento.pousar(fio, "  a frase exata\n")
        assert novo.estado is EstadoFio.RESOLVIDO
        assert armazenamento.buscar_fios(fio.despejo_id)[0].estado is EstadoFio.RESOLVIDO
        ultima = armazenamento.historico(fio.id)[-1]
        assert (ultima.de, ultima.para) == (EstadoFio.ESCOLHIDO, EstadoFio.RESOLVIDO)
        nota = armazenamento.notas(fio.id)[-1]
        assert nota.tipo is TipoNota.POUSO
        assert nota.texto == "  a frase exata\n"
        assert fio.id not in {f.id for f in armazenamento.mesa()}
        armazenamento.fechar()

    def test_pousar_jogado_levanta_transicao_invalida(self):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.JOGADO)
        with pytest.raises(TransicaoInvalida):
            armazenamento.pousar(fio, "cedo demais")
        assert armazenamento.notas(fio.id) == []
        armazenamento.fechar()

    def test_pousar_sem_frase_resolve_sem_nota(self):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        novo = armazenamento.pousar(fio)
        assert novo.estado is EstadoFio.RESOLVIDO
        assert armazenamento.buscar_fios(fio.despejo_id)[0].estado is EstadoFio.RESOLVIDO
        ultima = armazenamento.historico(fio.id)[-1]
        assert (ultima.de, ultima.para) == (EstadoFio.ESCOLHIDO, EstadoFio.RESOLVIDO)
        assert [n for n in armazenamento.notas(fio.id) if n.tipo is TipoNota.POUSO] == []
        armazenamento.fechar()

    def test_pousar_com_frase_so_espacos_resolve_sem_nota(self):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        novo = armazenamento.pousar(fio, "   ")
        assert novo.estado is EstadoFio.RESOLVIDO
        assert armazenamento.buscar_fios(fio.despejo_id)[0].estado is EstadoFio.RESOLVIDO
        ultima = armazenamento.historico(fio.id)[-1]
        assert (ultima.de, ultima.para) == (EstadoFio.ESCOLHIDO, EstadoFio.RESOLVIDO)
        assert armazenamento.notas(fio.id) == []
        armazenamento.fechar()

    def test_fio_desatualizado_levanta(self):
        armazenamento = Armazenamento(":memory:")
        escolhido = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        armazenamento.atualizar_estado(escolhido, EstadoFio.GUARDADO)
        historico_antes = armazenamento.historico(escolhido.id)
        with pytest.raises(ValueError, match="desatualizado"):
            armazenamento.pousar(escolhido, "tarde demais")
        assert armazenamento.buscar_fios(escolhido.despejo_id)[0].estado is EstadoFio.GUARDADO
        assert armazenamento.historico(escolhido.id) == historico_antes
        assert armazenamento.notas(escolhido.id) == []
        armazenamento.fechar()

    def test_falha_na_nota_desfaz_a_transicao(self, monkeypatch):
        armazenamento = Armazenamento(":memory:")
        fio = _fio_salvo(armazenamento, EstadoFio.ESCOLHIDO)
        historico_antes = armazenamento.historico(fio.id)

        def falhar(fio_id, tipo, texto):
            raise RuntimeError("falha simulada")

        monkeypatch.setattr(armazenamento, "_inserir_nota", falhar)
        with pytest.raises(RuntimeError):
            armazenamento.pousar(fio, "nao fica")
        assert armazenamento.buscar_fios(fio.despejo_id)[0].estado is EstadoFio.ESCOLHIDO
        assert armazenamento.historico(fio.id) == historico_antes
        armazenamento.fechar()

    def test_pousar_um_nao_toca_o_outro(self):
        armazenamento = Armazenamento(":memory:")
        despejo = Despejo(conteudo="dois fios")
        um, outro = Fio(despejo_id=despejo.id), Fio(despejo_id=despejo.id)
        armazenamento.salvar_despejo_com_fios(despejo, [um, outro])
        um = armazenamento.atualizar_estado(um, EstadoFio.ESCOLHIDO)
        armazenamento.pousar(um, "este pousou")
        estados = {f.id: f.estado for f in armazenamento.buscar_fios(despejo.id)}
        assert estados[outro.id] is EstadoFio.JOGADO
        assert len(armazenamento.historico(outro.id)) == 1
        armazenamento.fechar()
