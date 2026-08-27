# Limencore



> Um lugar para pensar — não para se cobrar.

Limencore é uma ferramenta open-core de autoconhecimento para quem carrega a mente cheia: pensamentos misturados com problemas, preocupações que voltam, a sensação de não conseguir organizar o que se sente.

Em vez de pedir que você resuma o dia em notas e gráficos, o Limencore parte do pensamento em si. Você despeja o que está na cabeça, do jeito bagunçado que ele vem, e a ferramenta ajuda você a enxergar seus próprios padrões ao longo do tempo — o que volta, o que muda, o que pesa.

O foco é **reflexão e autoconhecimento**. Não é diagnóstico, tratamento, nem aconselhamento — é um espelho, não um conselheiro.

---

## Como isto é diferente de um app de humor

A maioria dos apps de bem-estar registra *estado*: seu humor hoje, quantas horas dormiu, quanto café tomou. Útil, mas parte do princípio de que você já organizou o que sente antes de registrar.

O Limencore parte do oposto. Ele aceita o caos primeiro — o pensamento cru — e ajuda a organização a surgir depois, no seu ritmo, sem transformar a reflexão num formulário. O objetivo não é arquivar como você esteve; é ajudar você a sair de onde travou.

---

## Estado do projeto

Em desenvolvimento inicial. O repositório é construído de forma incremental, em commits pequenos e documentados. O que existe hoje é a fundação: o modelo de dados de uma entrada.

Este README descreve a direção do projeto, não um produto pronto. Recursos citados como planejados ainda não existem.

---

## MVP planejado

A primeira versão pública deve incluir:

- Registro de pensamentos em texto livre, com carimbo de tempo
- Contexto opcional do dia (sono, energia, etc.) como pano de fundo
- Banco de dados local (SQLite) — seus dados ficam no seu aparelho
- Histórico de entradas
- Leitura de padrões ao longo do tempo (recorrência, mudança)

O contexto do dia é sempre secundário e opcional: o produto funciona sem preencher nada disso.

---

## Estrutura do projeto

```text
limencore/
├── src/
│   └── limencore/
│       ├── __init__.py
│       ├── main.py
│       └── entry.py        # modelo da entrada-pensamento
├── tests/
├── docs/
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

---

## Privacidade

Os dados ficam no seu aparelho. O Limencore é pensado para funcionar localmente, sem enviar seus pensamentos para servidores externos.

---

## Licença

Este projeto é licenciado sob a Apache License 2.0. Veja o arquivo `LICENSE`.
