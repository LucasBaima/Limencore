import sqlite3


class Armazenamento:
    def __init__(self, caminho: str = "limencore.db"):
        self.caminho = caminho
        self._conexao = sqlite3.connect(caminho)
        self._inicializar()

    def _inicializar(self):
        self._conexao.execute(
            """
            CREATE TABLE IF NOT EXISTS thoughts (
                id TEXT PRIMARY KEY,
                conteudo TEXT NOT NULL,
                instante TEXT NOT NULL
            )
            """
        )
        self._conexao.commit()

    def fechar(self):
        self._conexao.close()
