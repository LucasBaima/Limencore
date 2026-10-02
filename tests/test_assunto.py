import dataclasses

import pytest

from limencore.assunto import Assunto, limpar_rotulo, normalizar_assunto


class TestNormalizarAssunto:
    def test_espacos_e_maiusculas(self):
        assert normalizar_assunto("  A Saída   do Chefe ") == "a saída do chefe"

    def test_mantem_acento(self):
        assert normalizar_assunto("País") != normalizar_assunto("Pais")

    @pytest.mark.parametrize("texto", ["", "   ", "\t\n "])
    def test_vazio_falha(self, texto):
        with pytest.raises(ValueError):
            normalizar_assunto(texto)

    @pytest.mark.parametrize("texto", [None, 3])
    def test_nao_string_falha(self, texto):
        with pytest.raises(ValueError):
            normalizar_assunto(texto)


class TestLimparRotulo:
    def test_preserva_maiusculas(self):
        assert limpar_rotulo("  A Saída   do Chefe ") == "A Saída do Chefe"

    def test_vazio_falha(self):
        with pytest.raises(ValueError):
            limpar_rotulo("   ")


class TestAssunto:
    def test_aceita_chave_e_rotulo_limpos(self):
        assunto = Assunto(chave="a saída do chefe", rotulo="A Saída do Chefe")
        assert assunto.chave == "a saída do chefe"
        assert assunto.rotulo == "A Saída do Chefe"

    def test_chave_nao_normalizada_falha(self):
        with pytest.raises(ValueError):
            Assunto(chave="A Saída do Chefe", rotulo="A Saída do Chefe")

    def test_rotulo_com_espaco_sobrando_falha(self):
        with pytest.raises(ValueError):
            Assunto(chave="a saída do chefe", rotulo=" A Saída do Chefe")

    def test_frozen(self):
        assunto = Assunto(chave="chefe", rotulo="Chefe")
        with pytest.raises(dataclasses.FrozenInstanceError):
            assunto.rotulo = "outro"
