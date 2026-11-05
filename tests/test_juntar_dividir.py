import pytest

from conftest import despejo_com_fios
from limencore.corte import Trecho, recortar
from limencore.fio import EstadoFio, TransicaoInvalida

TEXTO = "o prazo do relatorio. a viagem de sabado. o carro na oficina"
#        0         1         2         3         4         5
#        0123456789012345678901234567890123456789012345678901234567890


def _todos_os_ids(banco):
    return {i for (i,) in banco._conexao.execute("SELECT id FROM fios")}


def _sem_juntado(banco):
    return set(EstadoFio) - {EstadoFio.JUNTADO}


@pytest.fixture
def tres(banco):
    despejo, fios = despejo_com_fios(banco, TEXTO, [(0, 21)], [(22, 41)], [(42, 60)])
    return despejo, fios


class TestJuntar:
    def test_preserva_trechos_exatos_e_ordem(self, banco, tres):
        _, (a, b, c) = tres
        sobrevivente = banco.juntar(c, a)
        assert sobrevivente.id == a.id
        assert sobrevivente.trechos == (Trecho(0, 21), Trecho(42, 60))
        assert banco.janela(a.id).trechos == (Trecho(0, 21), Trecho(42, 60))
        assert [recortar(TEXTO, t) for t in sobrevivente.trechos] == [
            "o prazo do relatorio.", "o carro na oficina",
        ]

    @pytest.mark.parametrize("ordem", ["ab", "ba"])
    def test_sobrevive_o_primeiro_no_texto(self, banco, tres, ordem):
        _, (a, b, _) = tres
        pares = {"ab": (a, b), "ba": (b, a)}[ordem]
        assert banco.juntar(*pares).id == a.id
        (juntado,) = banco.buscar_fios(a.despejo_id, estados=[EstadoFio.JUNTADO])
        assert juntado.id == b.id
        assert juntado.juntado_em == a.id

    def test_fio_inteiro_conta_como_zero(self, banco):
        despejo, (parte,) = despejo_com_fios(banco, TEXTO, [(0, 21)])
        from limencore.fio import Fio
        inteiro = Fio(despejo_id=despejo.id)
        banco.salvar_fio(inteiro)
        banco.atualizar_estado(parte, EstadoFio.ESCOLHIDO)
        sobrevivente = banco.juntar(parte, inteiro)
        assert sobrevivente.trechos == ()
        assert sobrevivente.estado is EstadoFio.ESCOLHIDO

    @pytest.mark.parametrize(
        "estado_a,estado_b,esperado",
        [
            (EstadoFio.JOGADO, EstadoFio.JOGADO, EstadoFio.JOGADO),
            (EstadoFio.ESCOLHIDO, EstadoFio.JOGADO, EstadoFio.ESCOLHIDO),
            (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO, EstadoFio.ESCOLHIDO),
            (EstadoFio.ESCOLHIDO, EstadoFio.ESCOLHIDO, EstadoFio.ESCOLHIDO),
        ],
    )
    def test_regra_de_estado(self, banco, tres, estado_a, estado_b, esperado):
        _, (a, b, _) = tres
        if estado_a is not EstadoFio.JOGADO:
            a = banco.atualizar_estado(a, estado_a)
        if estado_b is not EstadoFio.JOGADO:
            b = banco.atualizar_estado(b, estado_b)
        sobrevivente = banco.juntar(a, b)
        assert sobrevivente.estado is esperado
        historico = [(t.de, t.para) for t in banco.historico(a.id)]
        if estado_a is EstadoFio.JOGADO and esperado is EstadoFio.ESCOLHIDO:
            assert historico[-1] == (EstadoFio.JOGADO, EstadoFio.ESCOLHIDO)
        assert banco.historico(b.id)[-1].para is EstadoFio.JUNTADO

    def test_janela_traz_eventos_dos_dois_e_dos_juntados_recursivos(self, banco, relogio, tres):
        _, (a, b, c) = tres
        a, b, c = (banco.atualizar_estado(f, EstadoFio.ESCOLHIDO) for f in (a, b, c))
        banco.escrever(a, "nota de a")
        relogio.andar(1)
        banco.escrever(b, "nota de b")
        relogio.andar(1)
        banco.registrar_turno(c, "turno de c")
        relogio.andar(1)
        banco.registrar_turno(b, "turno de b")
        banco.juntar(b, c)
        banco.juntar(a, b)
        eventos = banco.janela(a.id).eventos
        assert [(e.autoria, e.texto) for e in eventos] == [
            ("usuario", "nota de a"),
            ("usuario", "nota de b"),
            ("agente", "turno de c"),
            ("agente", "turno de b"),
        ]

    def test_nenhuma_nota_ou_turno_muda_de_fio(self, banco, tres):
        _, (a, b, _) = tres
        b = banco.atualizar_estado(b, EstadoFio.ESCOLHIDO)
        banco.escrever(b, "nota de b")
        banco.registrar_turno(b, "turno de b")
        banco.juntar(a, b)
        assert [n.texto for n in banco.notas(b.id)] == ["nota de b"]
        assert [t.texto for t in banco.turnos(b.id)] == ["turno de b"]
        assert banco.notas(a.id) == []
        assert banco.turnos(a.id) == []

    def test_recusas(self, banco, tres):
        _, (a, b, c) = tres
        _, (outro,) = despejo_com_fios(banco, "outro despejo")
        with pytest.raises(ValueError):
            banco.juntar(a, a)
        with pytest.raises(ValueError):
            banco.juntar(a, outro)
        c = banco.guardar(c)
        with pytest.raises(TransicaoInvalida):
            banco.juntar(a, c)
        banco.juntar(a, b)
        with pytest.raises(TransicaoInvalida):
            banco.juntar(a, b)

    def test_atualizar_estado_nao_leva_a_juntado(self, banco, tres):
        _, (a, _, _) = tres
        with pytest.raises(TransicaoInvalida):
            banco.atualizar_estado(a, EstadoFio.JUNTADO)

    def test_falha_no_meio_nao_deixa_rastro(self, banco, tres, monkeypatch):
        _, (a, b, _) = tres

        def quebra(*args):
            raise RuntimeError("falhou")

        monkeypatch.setattr(banco, "_registrar_operacao", quebra)
        with pytest.raises(RuntimeError):
            banco.juntar(a, b)
        assert [f.estado for f in banco.buscar_fios(a.despejo_id)] == [EstadoFio.JOGADO] * 3
        assert banco.buscar_fios(a.despejo_id)[0].trechos == (Trecho(0, 21),)


class TestJuntadoSomeDasConsultas:
    def test_some_de_todas_as_listagens(self, banco, tres):
        _, (a, b, _) = tres
        banco.marcar_assunto(a, "trabalho")
        banco.marcar_assunto(b, "trabalho")
        banco.juntar(a, b)
        assert b.id not in {f.id for f in banco.buscar_fios(a.despejo_id)}
        assert b.id not in {f.id for f in banco.mesa()}
        assert b.id not in {f.id for f in banco.guardados()}
        assert b.id not in {f.id for f in banco.fios_do_assunto("trabalho")}
        assert b.id not in {f.id for f in banco.buscar_fios(a.despejo_id, estados=_sem_juntado(banco))}

    def test_aparece_quando_pedido(self, banco, tres):
        _, (a, b, _) = tres
        banco.marcar_assunto(b, "trabalho")
        banco.juntar(a, b)
        assert [f.id for f in banco.buscar_fios(a.despejo_id, estados=[EstadoFio.JUNTADO])] == [b.id]
        assert [f.id for f in banco.fios_do_assunto("trabalho", estados=[EstadoFio.JUNTADO])] == [b.id]

    def test_estados_vazio_e_recusado(self, banco, tres):
        _, (a, _, _) = tres
        with pytest.raises(ValueError):
            banco.buscar_fios(a.despejo_id, estados=[])


class TestDividir:
    def test_no_meio_de_um_trecho(self, banco, relogio):
        _, (fio,) = despejo_com_fios(banco, TEXTO, estado=EstadoFio.ESCOLHIDO)
        banco.escrever(fio, "uma nota")
        banco.registrar_turno(fio, "um turno")
        fio = banco.entrar(fio)
        primeira, segunda = banco.dividir(fio, 22)
        assert primeira.id == fio.id
        assert primeira.estado is EstadoFio.ESCOLHIDO
        assert primeira.trechos == (Trecho(0, 21),)  # o espaco da ponta sai
        assert primeira.ultimo_toque == fio.ultimo_toque
        assert segunda.trechos == (Trecho(22, 60),)
        assert segunda.estado is EstadoFio.JOGADO
        assert [n.texto for n in banco.notas(fio.id)] == ["uma nota"]
        assert [t.texto for t in banco.turnos(fio.id)] == ["um turno"]
        assert banco.notas(segunda.id) == []
        assert banco.turnos(segunda.id) == []
        assert [(t.de, t.para) for t in banco.historico(segunda.id)] == [(None, EstadoFio.JOGADO)]
        guardados = {f.id: f for f in banco.buscar_fios(fio.despejo_id)}
        assert guardados[fio.id].trechos == (Trecho(0, 21),)
        assert guardados[segunda.id].trechos == (Trecho(22, 60),)

    def test_corte_no_espaco_apara_as_duas_pontas(self, banco):
        _, (fio,) = despejo_com_fios(banco, TEXTO, estado=EstadoFio.ESCOLHIDO)
        primeira, segunda = banco.dividir(fio, 21)
        assert [recortar(TEXTO, t) for t in primeira.trechos] == ["o prazo do relatorio."]
        assert [recortar(TEXTO, t) for t in segunda.trechos] == ["a viagem de sabado. o carro na oficina"]

    def test_na_fronteira_entre_trechos(self, banco, tres):
        _, (a, b, c) = tres
        a = banco.juntar(a, b)
        a = banco.juntar(a, c)
        a = banco.atualizar_estado(a, EstadoFio.ESCOLHIDO)
        primeira, segunda = banco.dividir(a, 41)
        assert primeira.trechos == (Trecho(0, 21), Trecho(22, 41))
        assert segunda.trechos == (Trecho(42, 60),)

    def test_fronteira_no_vao_entre_trechos(self, banco):
        _, (a, b) = despejo_com_fios(banco, TEXTO, [(0, 7)], [(42, 49)])
        a = banco.juntar(a, b)
        a = banco.atualizar_estado(a, EstadoFio.ESCOLHIDO)
        primeira, segunda = banco.dividir(a, 30)
        assert primeira.trechos == (Trecho(0, 7),)
        assert segunda.trechos == (Trecho(42, 49),)

    def test_emoji_conta_code_points(self, banco):
        texto = "😀 um pensamento 🌧️ outro pensamento"
        _, (fio,) = despejo_com_fios(banco, texto, estado=EstadoFio.ESCOLHIDO)
        corte = texto.index("🌧")
        primeira, segunda = banco.dividir(fio, corte)
        assert [recortar(texto, t) for t in primeira.trechos] == ["😀 um pensamento"]
        assert [recortar(texto, t) for t in segunda.trechos] == ["🌧️ outro pensamento"]
        assert primeira.trechos == (Trecho(0, 15),)
        assert segunda.trechos == (Trecho(16, len(texto)),)
        assert len(texto) == 35

    @pytest.mark.parametrize("corte", [0, 60, 2, 61, -1])
    def test_parte_vazia_ou_fora_e_recusada(self, banco, corte):
        texto = "  " + "x" * 56 + "  "
        _, (fio,) = despejo_com_fios(banco, texto, estado=EstadoFio.ESCOLHIDO)
        antes = _todos_os_ids(banco)
        with pytest.raises(ValueError):
            banco.dividir(fio, corte)
        assert _todos_os_ids(banco) == antes
        assert banco.buscar_fios(fio.despejo_id)[0].trechos == ()

    def test_parte_so_de_espaco_e_recusada(self, banco):
        texto = "abc      def"
        _, (fio,) = despejo_com_fios(banco, texto, [(0, 9)], estado=EstadoFio.ESCOLHIDO)
        with pytest.raises(ValueError):
            banco.dividir(fio, 5)  # a segunda parte seria so espacos
        assert banco.buscar_fios(fio.despejo_id)[0].trechos == (Trecho(0, 9),)

    def test_so_escolhido(self, banco, tres):
        _, (a, _, _) = tres
        with pytest.raises(TransicaoInvalida):
            banco.dividir(a, 5)

    def test_corte_nao_int(self, banco):
        _, (fio,) = despejo_com_fios(banco, TEXTO, estado=EstadoFio.ESCOLHIDO)
        with pytest.raises(ValueError):
            banco.dividir(fio, 5.0)


class TestNenhumFioApagado:
    def test_juntar_e_dividir_nao_apagam(self, banco, tres):
        _, (a, b, c) = tres
        antes = _todos_os_ids(banco)
        a = banco.juntar(a, b)
        a = banco.atualizar_estado(a, EstadoFio.ESCOLHIDO)
        _, novo = banco.dividir(a, 10)
        assert antes <= _todos_os_ids(banco)
        assert _todos_os_ids(banco) == antes | {novo.id}
