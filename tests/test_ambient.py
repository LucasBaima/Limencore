import pytest

from limencore.ambient import ContextoAmbiente


class TestValido:
    def test_vazio_tudo_none(self):
        c = ContextoAmbiente()
        assert c.sono_horas is None
        assert c.sono_interrupcoes is None
        assert c.cafeina_mg is None
        assert c.energia == {}

    def test_energia_valida(self):
        c = ContextoAmbiente(energia={"Trabalho": 60, "Casa & Responsabilidades": 30})
        assert c.energia["Trabalho"] == 60

    def test_ambiente_completo(self):
        c = ContextoAmbiente(
            sono_horas=7.5,
            sono_interrupcoes=2,
            cafeina_mg=200,
            energia={"Trabalho": 50},
        )
        assert c.cafeina_mg == 200

    def test_energia_custom_string_aceita(self):
        c = ContextoAmbiente(energia={"academia": 20})
        assert c.energia["academia"] == 20


class TestOpcional:
    # ausencia != invalido (DECISIONS §9): campo None passa, nunca bloqueia.
    def test_so_sono(self):
        c = ContextoAmbiente(sono_horas=8)
        assert c.sono_horas == 8
        assert c.sono_interrupcoes is None

    def test_so_cafeina(self):
        assert ContextoAmbiente(cafeina_mg=100).cafeina_mg == 100

    def test_energia_ausente_vira_dict_vazio(self):
        assert ContextoAmbiente().energia == {}


class TestInvalido:
    @pytest.mark.parametrize("chave", ["", "  "])
    def test_energia_chave_vazia_ou_espaco_estoura(self, chave):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={chave: 20})

    def test_energia_valor_fracionario(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={"Trabalho": 22.5})

    def test_energia_valor_bool(self):
        # True vale 1 em Python; o guard barra bool de proposito.
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={"Trabalho": True})

    def test_sono_interrupcoes_fracionario(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(sono_interrupcoes=2.5)


class TestBorda:
    # --- energia: soma total ---
    def test_soma_exatamente_100_ok(self):
        ContextoAmbiente(energia={"Trabalho": 70, "Casa & Responsabilidades": 30})

    def test_soma_101_falha(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={"Trabalho": 70, "Casa & Responsabilidades": 31})

    def test_soma_100_mista_default_e_custom_ok(self):
        ContextoAmbiente(energia={"Trabalho": 60, "academia": 40})

    def test_soma_101_mista_default_e_custom_falha(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={"Trabalho": 61, "academia": 40})

    # --- energia: valor individual ---
    @pytest.mark.parametrize("valor", [0, 100])
    def test_energia_valor_no_limite_ok(self, valor):
        ContextoAmbiente(energia={"Trabalho": valor})

    @pytest.mark.parametrize("valor", [-1, 101])
    def test_energia_valor_fora_falha(self, valor):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={"Trabalho": valor})

    # --- sono_horas: 0 a 24 ---
    @pytest.mark.parametrize("h", [0, 24])
    def test_sono_no_limite_ok(self, h):
        ContextoAmbiente(sono_horas=h)

    @pytest.mark.parametrize("h", [-0.1, 24.1])
    def test_sono_fora_falha(self, h):
        with pytest.raises(ValueError):
            ContextoAmbiente(sono_horas=h)

    # --- sono_interrupcoes: 0 a 10 ---
    @pytest.mark.parametrize("n", [0, 10])
    def test_interrupcoes_no_limite_ok(self, n):
        ContextoAmbiente(sono_interrupcoes=n)

    def test_interrupcoes_acima_falha(self):
        with pytest.raises(ValueError):
            ContextoAmbiente(sono_interrupcoes=11)

    # --- cafeina_mg: 0 a 500 ---
    @pytest.mark.parametrize("mg", [0, 500])
    def test_cafeina_no_limite_ok(self, mg):
        ContextoAmbiente(cafeina_mg=mg)

    @pytest.mark.parametrize("mg", [-1, 501])
    def test_cafeina_fora_falha(self, mg):
        with pytest.raises(ValueError):
            ContextoAmbiente(cafeina_mg=mg)


class TestSnapDefault:
    @pytest.mark.parametrize("chave", ["trabalho", "  TRABALHO ", "Trabalho", "TRABALHO"])
    def test_snap_default_ignora_caixa_e_espaco(self, chave):
        c = ContextoAmbiente(energia={chave: 40})
        assert c.energia == {"Trabalho": 40}

    def test_custom_preserva_grafia(self):
        c = ContextoAmbiente(energia={"  Academia ": 20})
        assert c.energia == {"Academia": 20}

    def test_soma_e_calculada_pos_dedup(self):
        # "trabalho" e "TRABALHO" colapsam na mesma chave canonica; a soma
        # deve considerar apenas o valor final (60), nao 60+60.
        c = ContextoAmbiente(energia={"trabalho": 60, "TRABALHO": 60})
        assert c.energia == {"Trabalho": 60}

    @pytest.mark.parametrize("chave", ["", "  "])
    def test_chave_vazia_ou_espaco_estoura(self, chave):
        with pytest.raises(ValueError):
            ContextoAmbiente(energia={chave: 20})