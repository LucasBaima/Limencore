import json

import pytest

from conftest import despejo_com_fios
from limencore.corte import Trecho
from limencore.fio import EstadoFio, TransicaoInvalida
from limencore.nota import TipoNota
from limencore.storage import Armazenamento

TEXTO = "o prazo do relatorio. a viagem de sabado. o carro na oficina"


@pytest.fixture
def tres(banco):
    return despejo_com_fios(banco, TEXTO, [(0, 21)], [(22, 41)], [(42, 60)])


def _ids(banco):
    return {i for (i,) in banco._conexao.execute("SELECT id FROM fios")}


def _foto(banco, despejo_id):
    # estado, trechos e juntado_em de todos os fios do despejo, juntados inclusive
    return {
        f.id: (f.estado, f.trechos, f.juntado_em)
        for f in banco.buscar_fios(despejo_id, estados=list(EstadoFio))
    }


class TestRegistro:
    def test_cada_operacao_registra(self, banco, tres):
        _, (a, b, c) = tres
        banco.guardar(c)
        a = banco.juntar(a, b)
        a = banco.entrar(a)
        _, novo = banco.dividir(a, 10)
        banco.pousar(a)
        tipos = [t for (t,) in banco._conexao.execute("SELECT tipo FROM operacoes ORDER BY id")]
        assert tipos == ["GUARDAR", "JUNTAR", "DIVIDIR", "POUSAR"]
        (dados,) = banco._conexao.execute(
            "SELECT dados FROM operacoes WHERE tipo = 'DIVIDIR'"
        ).fetchone()
        assert json.loads(dados)["outro"] == novo.id

    def test_entrar_nao_registra(self, banco, tres):
        _, (a, _, _) = tres
        banco.entrar(a)
        assert banco._conexao.execute("SELECT COUNT(*) FROM operacoes").fetchone() == (0,)

    def test_operacao_some_com_rollback(self, banco, tres, monkeypatch):
        _, (a, _, _) = tres

        def quebra(*args, **kwargs):
            raise RuntimeError("falhou")

        monkeypatch.setattr(banco, "_mudar_estado", quebra)
        with pytest.raises(RuntimeError):
            banco.guardar(a)
        assert banco._conexao.execute("SELECT COUNT(*) FROM operacoes").fetchone() == (0,)


class TestDesfazerGuardarEPousar:
    @pytest.mark.parametrize("origem", [EstadoFio.JOGADO, EstadoFio.ESCOLHIDO])
    def test_guardar_volta_ao_anterior(self, banco, tres, origem):
        _, (a, _, _) = tres
        if origem is EstadoFio.ESCOLHIDO:
            a = banco.entrar(a)
        a = banco.guardar(a)
        a = banco.desfazer(a)
        assert a.estado is origem
        ultima = banco.historico(a.id)[-1]
        assert (ultima.de, ultima.para, ultima.motivo) == (EstadoFio.GUARDADO, origem, "desfazer")

    def test_atualizar_estado_para_guardado_tambem_e_desfazivel(self, banco, tres):
        _, (a, _, _) = tres
        a = banco.atualizar_estado(a, EstadoFio.GUARDADO)
        assert banco.desfazer(a).estado is EstadoFio.JOGADO

    def test_pousar_volta_e_nota_de_pouso_sobrevive(self, banco, tres):
        _, (a, _, _) = tres
        a = banco.entrar(a)
        banco.escrever(a, "uma nota")
        a = banco.pousar(a, "entrego hoje")
        a = banco.desfazer(a)
        assert a.estado is EstadoFio.ESCOLHIDO
        assert [(n.tipo, n.texto) for n in banco.notas(a.id)] == [
            (TipoNota.NOTA, "uma nota"), (TipoNota.POUSO, "entrego hoje"),
        ]

    def test_historico_mostra_ida_e_volta(self, banco, tres):
        _, (a, _, _) = tres
        a = banco.entrar(a)
        a = banco.pousar(a)
        banco.desfazer(a)
        assert [(t.de, t.para, t.motivo) for t in banco.historico(a.id)] == [
            (None, EstadoFio.JOGADO, None),
            (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO, None),
            (EstadoFio.ESCOLHIDO, EstadoFio.RESOLVIDO, None),
            (EstadoFio.RESOLVIDO, EstadoFio.ESCOLHIDO, "desfazer"),
        ]

    def test_saidas_de_resolvido_e_guardado_so_pelo_desfazer(self, banco, tres):
        _, (a, b, _) = tres
        a = banco.pousar(banco.entrar(a))
        with pytest.raises(TransicaoInvalida):
            banco.atualizar_estado(a, EstadoFio.ESCOLHIDO)
        b = banco.guardar(b)
        with pytest.raises(TransicaoInvalida):
            banco.atualizar_estado(b, EstadoFio.JOGADO)


class TestDesfazerJuntar:
    def test_volta_exatamente_ao_anterior(self, banco, tres):
        despejo, (a, b, _) = tres
        b = banco.entrar(b)
        banco.escrever(b, "nota de b")
        antes = _foto(banco, despejo.id)
        banco.juntar(a, b)
        banco.desfazer(a)
        assert _foto(banco, despejo.id) == antes
        assert [n.texto for n in banco.notas(b.id)] == ["nota de b"]
        assert banco.janela(a.id).eventos == ()
        assert (banco.historico(a.id)[-1].de, banco.historico(a.id)[-1].para) == (
            EstadoFio.ESCOLHIDO, EstadoFio.JOGADO,
        )
        assert banco.historico(a.id)[-1].motivo == "desfazer"
        ultima_b = banco.historico(b.id)[-1]
        assert (ultima_b.de, ultima_b.para, ultima_b.motivo) == (
            EstadoFio.JUNTADO, EstadoFio.ESCOLHIDO, "desfazer",
        )

    def test_pelo_fio_juntado(self, banco, tres):
        despejo, (a, b, _) = tres
        antes = _foto(banco, despejo.id)
        banco.juntar(a, b)
        banco.desfazer(b)
        assert _foto(banco, despejo.id) == antes


class TestDesfazerDividir:
    def test_volta_e_o_novo_vira_juntado(self, banco, tres):
        despejo, (a, _, _) = tres
        a = banco.entrar(a)
        antes = _foto(banco, despejo.id)
        _, novo = banco.dividir(a, 10)
        banco.desfazer(a)
        depois = _foto(banco, despejo.id)
        assert depois[a.id] == antes[a.id]
        assert depois[novo.id] == (EstadoFio.JUNTADO, (Trecho(11, 21),), a.id)
        assert novo.id not in {f.id for f in banco.buscar_fios(despejo.id)}
        ultima = banco.historico(novo.id)[-1]
        assert (ultima.de, ultima.para, ultima.motivo) == (EstadoFio.JOGADO, EstadoFio.JUNTADO, "desfazer")

    def test_fio_inteiro_volta_a_ser_inteiro(self, banco):
        despejo, (fio,) = despejo_com_fios(banco, TEXTO, estado=EstadoFio.ESCOLHIDO)
        banco.dividir(fio, 22)
        assert banco.desfazer(fio).trechos == ()


class TestRecusas:
    def test_sem_operacao(self, banco, tres):
        _, (a, _, _) = tres
        with pytest.raises(ValueError):
            banco.desfazer(a)

    def test_fora_da_janela(self, banco, relogio, tres):
        _, (a, _, _) = tres
        a = banco.guardar(a)
        relogio.andar(10)
        with pytest.raises(ValueError):
            banco.desfazer(a)
        assert banco.buscar_fios(a.despejo_id, estados=[EstadoFio.GUARDADO])[0].id == a.id

    def test_dentro_da_janela(self, banco, relogio, tres):
        _, (a, _, _) = tres
        a = banco.guardar(a)
        relogio.andar(9.9)
        assert banco.desfazer(a).estado is EstadoFio.JOGADO

    def test_janela_configuravel(self, banco, relogio, tres):
        _, (a, _, _) = tres
        a = banco.guardar(a)
        relogio.andar(30)
        assert banco.desfazer(a, janela_segundos=60).estado is EstadoFio.JOGADO

    def test_recusa_se_nao_for_a_ultima(self, banco, tres):
        despejo, (a, b, _) = tres
        banco.juntar(a, b)
        a = banco.guardar(banco.entrar(a))
        # a ultima de b e o JUNTAR, mas a tem operacao depois
        with pytest.raises(ValueError):
            banco.desfazer(b)
        assert banco.buscar_fios(despejo.id, estados=[EstadoFio.JUNTADO])[0].id == b.id

    def test_desfaz_em_pilha(self, banco, tres):
        despejo, (a, b, _) = tres
        antes = _foto(banco, despejo.id)
        a = banco.juntar(a, b)
        a = banco.guardar(a)
        banco.desfazer(a)
        banco.desfazer(a)
        assert _foto(banco, despejo.id) == antes
        with pytest.raises(ValueError):
            banco.desfazer(a)

    def test_ja_desfeita_nao_desfaz_de_novo(self, banco, tres):
        _, (a, _, _) = tres
        a = banco.guardar(a)
        banco.desfazer(a)
        with pytest.raises(ValueError):
            banco.desfazer(a)

    def test_estado_mudou_sem_operacao(self, banco, tres):
        _, (a, _, _) = tres
        a = banco.guardar(a)
        a = banco.atualizar_estado(a, EstadoFio.ESCOLHIDO)  # volta por pull
        with pytest.raises(ValueError):
            banco.desfazer(a)
        assert banco.buscar_fios(a.despejo_id)[0].estado is EstadoFio.ESCOLHIDO


class TestNenhumFioApagado:
    def test_desfazer_nao_apaga(self, banco, tres):
        _, (a, b, _) = tres
        antes = _ids(banco)
        a = banco.juntar(a, b)
        banco.desfazer(a)
        a = banco.entrar(a)
        _, novo = banco.dividir(a, 10)
        banco.desfazer(a)
        assert _ids(banco) == antes | {novo.id}


class TestMigracao:
    def test_banco_antigo_ganha_colunas_e_tabelas(self, tmp_path):
        import sqlite3
        caminho = str(tmp_path / "velho.db")
        conexao = sqlite3.connect(caminho)
        conexao.executescript(
            """
            CREATE TABLE fios (id TEXT PRIMARY KEY, despejo_id TEXT NOT NULL,
                               estado TEXT NOT NULL, criado_em TEXT NOT NULL);
            CREATE TABLE transicoes (seq INTEGER PRIMARY KEY AUTOINCREMENT, fio_id TEXT NOT NULL,
                                     de TEXT, para TEXT NOT NULL, instante TEXT NOT NULL);
            """
        )
        conexao.commit()
        conexao.close()
        for _ in range(2):  # idempotente
            a = Armazenamento(caminho)
            colunas_fios = {l[1] for l in a._conexao.execute("PRAGMA table_info(fios)")}
            colunas_transicoes = {l[1] for l in a._conexao.execute("PRAGMA table_info(transicoes)")}
            tabelas = {n for (n,) in a._conexao.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert {"juntado_em", "ultimo_toque", "assunto_chave"} <= colunas_fios
            assert "motivo" in colunas_transicoes
            assert {"turnos", "operacoes"} <= tabelas
            a.fechar()
