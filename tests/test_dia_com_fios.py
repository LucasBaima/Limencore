import dataclasses
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from conftest import despejo_com_fios
from limencore.corte import Trecho
from limencore.despejo import Despejo
from limencore.fio import EstadoFio, Fio
from limencore.storage import LIMITE_DO_TITULO, DespejoDoDia

SP = ZoneInfo("America/Sao_Paulo")


def _despejo_em(banco, instante, *grupos, conteudo="o prazo do relatorio. a viagem de sabado"):
    despejo = Despejo(conteudo=conteudo, instante=instante)
    fios = [
        Fio(despejo_id=despejo.id, trechos=tuple(Trecho(i, f) for i, f in grupo)) for grupo in grupos
    ] or [Fio(despejo_id=despejo.id)]
    banco.salvar_despejo_com_fios(despejo, fios)
    return despejo, fios


class TestBuscarFio:
    @pytest.mark.parametrize(
        "caminho",
        [
            (),
            (EstadoFio.ESCOLHIDO,),
            (EstadoFio.ESCOLHIDO, EstadoFio.RESOLVIDO),
            (EstadoFio.GUARDADO,),
            (EstadoFio.DESCARTADO,),
        ],
    )
    def test_acha_em_cada_estado(self, banco, caminho):
        _, (fio,) = despejo_com_fios(banco, "um despejo")
        for estado in caminho:
            fio = banco.atualizar_estado(fio, estado)
        achado = banco.buscar_fio(fio.id)
        assert achado == fio

    def test_acha_juntado(self, banco):
        _, (a, b) = despejo_com_fios(banco, "o prazo. a viagem", [(0, 8)], [(9, 17)])
        banco.juntar(a, b)
        achado = banco.buscar_fio(b.id)
        assert achado.estado is EstadoFio.JUNTADO
        assert achado.juntado_em == a.id

    def test_inexistente(self, banco):
        assert banco.buscar_fio(Fio(despejo_id=Despejo(conteudo="x").id).id) is None


class TestTitulo:
    def test_sem_titulo(self, banco):
        despejo, _ = despejo_com_fios(banco, "um despejo")
        assert banco.titulo_do_despejo(despejo.id) is None

    def test_renomear_apara(self, banco):
        despejo, _ = despejo_com_fios(banco, "um despejo")
        banco.renomear_despejo(despejo.id, "  manha corrida \n")
        assert banco.titulo_do_despejo(despejo.id) == "manha corrida"

    def test_renomear_de_novo_sobrescreve(self, banco, relogio):
        despejo, _ = despejo_com_fios(banco, "um despejo")
        banco.renomear_despejo(despejo.id, "primeiro")
        relogio.andar(5)
        banco.renomear_despejo(despejo.id, "segundo")
        assert banco.titulo_do_despejo(despejo.id) == "segundo"
        linhas = banco._conexao.execute("SELECT titulo, atualizado_em FROM titulos_despejo").fetchall()
        assert linhas == [("segundo", relogio.agora.isoformat())]

    @pytest.mark.parametrize("vazio", [None, "", "   "])
    def test_vazio_remove(self, banco, vazio):
        despejo, _ = despejo_com_fios(banco, "um despejo")
        banco.renomear_despejo(despejo.id, "algum")
        banco.renomear_despejo(despejo.id, vazio)
        assert banco.titulo_do_despejo(despejo.id) is None
        assert banco._conexao.execute("SELECT COUNT(*) FROM titulos_despejo").fetchone() == (0,)

    def test_limite(self, banco):
        despejo, _ = despejo_com_fios(banco, "um despejo")
        banco.renomear_despejo(despejo.id, "a" * LIMITE_DO_TITULO)
        assert banco.titulo_do_despejo(despejo.id) == "a" * LIMITE_DO_TITULO
        with pytest.raises(ValueError, match="120"):
            banco.renomear_despejo(despejo.id, "b" * (LIMITE_DO_TITULO + 1))
        assert banco.titulo_do_despejo(despejo.id) == "a" * LIMITE_DO_TITULO

    def test_limite_conta_depois_de_aparar(self, banco):
        despejo, _ = despejo_com_fios(banco, "um despejo")
        banco.renomear_despejo(despejo.id, "  " + "a" * LIMITE_DO_TITULO + "  ")
        assert banco.titulo_do_despejo(despejo.id) == "a" * LIMITE_DO_TITULO

    def test_despejo_inexistente(self, banco):
        with pytest.raises(ValueError, match="despejo nao encontrado"):
            banco.renomear_despejo(Despejo(conteudo="x").id, "titulo")
        assert banco._conexao.execute("SELECT COUNT(*) FROM titulos_despejo").fetchone() == (0,)

    def test_titulo_nao_str(self, banco):
        despejo, _ = despejo_com_fios(banco, "um despejo")
        with pytest.raises(ValueError):
            banco.renomear_despejo(despejo.id, 42)

    def test_conteudo_intacto(self, banco):
        despejo, _ = despejo_com_fios(banco, "um despejo que nao muda")
        banco.renomear_despejo(despejo.id, "outro nome")
        assert banco.buscar_despejo(despejo.id) == despejo

    def test_nenhum_titulo_padrao_gravado(self, banco):
        despejo_com_fios(banco, "um despejo")
        assert banco._conexao.execute("SELECT COUNT(*) FROM titulos_despejo").fetchone() == (0,)

    def test_criacao_idempotente(self, tmp_path):
        from limencore.storage import Armazenamento

        caminho = str(tmp_path / "t.db")
        a = Armazenamento(caminho)
        despejo, _ = despejo_com_fios(a, "um despejo")
        a.renomear_despejo(despejo.id, "fica")
        a.fechar()
        b = Armazenamento(caminho)
        assert b.titulo_do_despejo(despejo.id) == "fica"
        b.fechar()


class TestDiaComFios:
    def test_frozen(self, banco):
        despejo, _ = _despejo_em(banco, datetime(2026, 3, 10, 15, tzinfo=timezone.utc))
        (dia,) = banco.dia_com_fios(date(2026, 3, 10), SP)
        assert isinstance(dia, DespejoDoDia)
        with pytest.raises(dataclasses.FrozenInstanceError):
            dia.titulo = "x"

    def test_dois_no_mesmo_dia_mais_recente_primeiro(self, banco):
        cedo, _ = _despejo_em(banco, datetime(2026, 3, 10, 9, tzinfo=SP))
        tarde, _ = _despejo_em(banco, datetime(2026, 3, 10, 20, tzinfo=SP))
        dia = banco.dia_com_fios(date(2026, 3, 10), SP)
        assert [d.despejo for d in dia] == [tarde, cedo]

    def test_23h_local_nao_vaza(self, banco):
        noite, _ = _despejo_em(banco, datetime(2026, 3, 10, 23, 30, tzinfo=SP))
        assert [d.despejo for d in banco.dia_com_fios(date(2026, 3, 10), SP)] == [noite]
        assert banco.dia_com_fios(date(2026, 3, 11), SP) == []

    def test_fios_em_ordem_de_posicao(self, banco):
        # criados fora da ordem do texto
        _, (depois, antes) = _despejo_em(banco, datetime(2026, 3, 10, 12, tzinfo=SP), [(22, 40)], [(0, 20)])
        (dia,) = banco.dia_com_fios(date(2026, 3, 10), SP)
        assert [f.id for f in dia.fios] == [antes.id, depois.id]
        assert isinstance(dia.fios, tuple)

    def test_juntado_nao_aparece(self, banco):
        _, (a, b) = _despejo_em(banco, datetime(2026, 3, 10, 12, tzinfo=SP), [(0, 20)], [(22, 40)])
        banco.juntar(a, b)
        (dia,) = banco.dia_com_fios(date(2026, 3, 10), SP)
        assert [f.id for f in dia.fios] == [a.id]
        assert all(f.estado is not EstadoFio.JUNTADO for f in dia.fios)

    def test_aberto(self, banco):
        _, (a, b) = _despejo_em(banco, datetime(2026, 3, 10, 12, tzinfo=SP), [(0, 20)], [(22, 40)])
        banco.guardar(a)
        (dia,) = banco.dia_com_fios(date(2026, 3, 10), SP)
        assert dia.tem_fio_aberto is True

    def test_escolhido_conta_como_aberto(self, banco):
        _, (a,) = _despejo_em(banco, datetime(2026, 3, 10, 12, tzinfo=SP))
        banco.atualizar_estado(a, EstadoFio.ESCOLHIDO)
        (dia,) = banco.dia_com_fios(date(2026, 3, 10), SP)
        assert dia.tem_fio_aberto is True

    def test_nada_aberto_quando_resolvidos_ou_guardados(self, banco):
        _, (a, b) = _despejo_em(banco, datetime(2026, 3, 10, 12, tzinfo=SP), [(0, 20)], [(22, 40)])
        banco.pousar(banco.atualizar_estado(a, EstadoFio.ESCOLHIDO))
        banco.guardar(b)
        (dia,) = banco.dia_com_fios(date(2026, 3, 10), SP)
        assert dia.tem_fio_aberto is False
        assert {f.estado for f in dia.fios} == {EstadoFio.RESOLVIDO, EstadoFio.GUARDADO}

    def test_titulo(self, banco):
        com, _ = _despejo_em(banco, datetime(2026, 3, 10, 9, tzinfo=SP))
        sem, _ = _despejo_em(banco, datetime(2026, 3, 10, 10, tzinfo=SP))
        banco.renomear_despejo(com.id, "a manha")
        titulos = {d.despejo.id: d.titulo for d in banco.dia_com_fios(date(2026, 3, 10), SP)}
        assert titulos == {com.id: "a manha", sem.id: None}

    def test_sem_campo_de_contagem(self):
        assert [c.name for c in dataclasses.fields(DespejoDoDia)] == [
            "despejo", "titulo", "fios", "tem_fio_aberto",
        ]
