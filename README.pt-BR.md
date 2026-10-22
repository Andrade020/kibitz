<div align="center">

<img src="docs/logo.png" alt="Logo do Think-Aloud Chess" width="120">

# Think-Aloud Chess

**Jogue xadrez contra um LLM que pensa em voz alta — e depois deixe que ele te ensine.**

[![Release](https://img.shields.io/github/v/release/Andrade020/think-aloud-chess?include_prereleases&label=release&color=f6e05e)](https://github.com/Andrade020/think-aloud-chess/releases)
[![CI](https://github.com/Andrade020/think-aloud-chess/actions/workflows/ci.yml/badge.svg)](https://github.com/Andrade020/think-aloud-chess/actions/workflows/ci.yml)
[![Licença: GPL v3+](https://img.shields.io/badge/licen%C3%A7a-GPL--3.0--or--later-blue.svg)](LICENSE)

[**⬇ Baixar para Windows**](https://github.com/Andrade020/think-aloud-chess/releases/download/v0.1.0-beta.1/ThinkAloudChess-0.1.0-beta.1-Setup.exe) · [English](README.md) · [Arquitetura](docs/ARCHITECTURE.md)

<img src="docs/img/review-walkthrough.gif" alt="Modo revisão: passando pela partida, com comentários e setas ao lado do tabuleiro" width="860">

</div>

> **Beta.** Funciona de ponta a ponta e tem testes automatizados. O instalador do Windows **ainda não é assinado digitalmente** (veja [Instalação](#instalação)).

## Por que isso existe

Motores como o Stockfish dizem *o que* é melhor, mas não *por que*, em termos humanos — "eu queria a sétima fila e prender o rei" é um conceito, não uma árvore de busca. Um modelo de linguagem pode jogar por intuição e explicar o que fez com esses conceitos. O problema: LLMs vão bem na abertura e mal depois, inventam lances ilegais, e uma dica de motor pode transformar a "explicação" numa justificativa inventada depois do fato.

O Think-Aloud Chess é um **jeito justo e auditável de jogar contra um LLM e aprender com ele**:

- o modelo **pensa em voz alta** a cada lance (leitura da posição, ameaças, plano, candidatos, checagem anti-erro) e tudo fica salvo;
- todo lance é **validado** contra a lista de lances legais; fatos objetivos (peças em risco, ameaças) são calculados por código;
- **você controla quanta ajuda de motor ele recebe**, e um motor escondido audita se ele raciocina de verdade ou só racionaliza a escolha do motor;
- depois, um **professor de IA** (com o Stockfish como verdade) revisa a partida no estilo do chess.com, explicando os erros **por conceitos** e desenhando setas.

## Recursos

- 🧠 **Raciocínio em camadas**, com o raciocínio de cada lance guardado (oculto até o fim da partida, para ser justo).
- 🛡️ **Sem lances alucinados**: validação, fatos por código e um revisor barato (Haiku) que só entra quando há sinal real de risco.
- ⚖️ **Ajuda de motor ajustável**: completa, só material, ou nenhuma. Auditoria de concordância com o motor.
- 🎓 **Revisão do professor** (opcional): Stockfish escolhe os momentos críticos; o professor explica por conceitos, inclusive onde o **próprio Claude errou a leitura**. Setas, casas destacadas, barra de avaliação, botão "próximo comentário", sons.
- 📊 **Auditoria**: precisão, perda média, erros e blunders dos dois lados.
- 💸 **Econômico em tokens**: cada lance é independente (o custo não cresce com a partida), com orçamento suave por partida.
- 🔌 **Traga o seu "cérebro"**: sua conta do **Claude Code** ou qualquer **API compatível com OpenAI** (DeepSeek, OpenAI, OpenRouter, Groq, Ollama…).
- 💾 **Suas partidas são suas**: exportar/importar `.gz`, autosave em Markdown legível, desfazer lance — tudo local.

## Instalação

### Windows (recomendado)

1. Baixe o **`ThinkAloudChess-<versão>-Setup.exe`** na [página de Releases](https://github.com/Andrade020/think-aloud-chess/releases).
2. Execute. Não precisa de administrador; o Python e o Stockfish já vêm junto.
3. Abra o **Think-Aloud Chess**. Um assistente na primeira abertura ajuda a conectar um "cérebro" (sua conta do Claude ou uma chave de API). Dá para abrir a **partida de demonstração**, uma partida terminada com revisão completa, sem gastar um token.

> **"O Windows protegeu o computador"?** O instalador beta ainda não é assinado digitalmente (certificados de assinatura custam dinheiro e exigem verificação de identidade), então o SmartScreen mostra *Editor desconhecido*. Clique em **Mais informações → Executar assim mesmo**. Você pode conferir o download com o `.sha256` publicado, e todo o código-fonte e o processo de build estão abertos. Os planos para assinar estão em [docs/SIGNING.md](docs/SIGNING.md).

### macOS / Linux / pelo código-fonte

```bash
pipx install git+https://github.com/Andrade020/think-aloud-chess.git   # ou: pip install .
think-aloud-chess            # abre http://127.0.0.1:5000
```

Requisitos: Python 3.10+. Para o modelo, **ou** o [Claude Code](https://claude.com/claude-code) (rode `claude` uma vez para entrar) **ou** uma chave de API de qualquer provedor compatível com OpenAI (configurada no app). O Stockfish é opcional, mas recomendado para a revisão (`winget install Stockfish.Stockfish`, `brew install stockfish`, `apt install stockfish`).

## Seus dados e privacidade

Tudo é local. Partidas, autosaves e o `config.json` (chaves de API) ficam na pasta de dados: `%LOCALAPPDATA%\ThinkAloudChess` no Windows, ou `./data` ao rodar de um clone. As chaves nunca vão para partidas, arquivos exportados nem para o navegador. O app só fala com o provedor **que você** configurar (e com o winget, só quando você pede para instalar o Claude Code). Sem telemetria. Veja [SECURITY.md](SECURITY.md).

## Limitações conhecidas (beta)

- A interface está só em português; internacionalização planejada.
- Um humano contra um LLM; sem relógio, sem livro de aberturas, sem tablebases (por escolha).
- O motor usado *durante* a partida é raso (3 lances); só o professor *depois* da partida usa o Stockfish.
- Instalador do Windows sem assinatura; macOS/Linux sem instalador por enquanto (use `pipx`).
- A estimativa de rating **não** é exibida de propósito: poucas partidas e uma régua rasa não a sustentam.

## Desenvolvimento

```bash
git clone https://github.com/Andrade020/think-aloud-chess && cd think-aloud-chess
pip install -e ".[dev]" && pytest          # 26 testes, sem rede e sem tokens
python -m think_aloud_chess                # roda do clone (dados em ./data)
powershell -File installer/build_windows.ps1   # gera o instalador do Windows
python tools/make_media.py                 # regenera as imagens do README
```

Contribuições são bem-vindas: veja [CONTRIBUTING.md](CONTRIBUTING.md).

## Licença e créditos

[GPL-3.0-or-later](LICENSE). Construído sobre [python-chess](https://github.com/niklasf/python-chess) (GPL-3.0+), [Flask](https://flask.palletsprojects.com/) (BSD-3) e [Stockfish](https://github.com/official-stockfish/Stockfish) (GPLv3, incluído no instalador). Sem vínculo com a Anthropic; "Claude" é marca da Anthropic.
