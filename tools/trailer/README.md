# Trailer promocional

Trailer de ~80 s no estilo de trailers de jogos de pequenos estúdios, feito 100% por código a partir de **telas reais do programa**
(nada de mockup, no tema escuro) e de uma trilha **original sintetizada** (sem samples, sem direitos autorais).

```bash
pip install playwright pillow numpy scipy imageio-ffmpeg && python -m playwright install chromium
python tools/trailer/capture_assets.py     # 1) captura as telas reais (partida de demonstração) em build/trailer/assets
python tools/trailer/make_audio.py         # 2) sintetiza a trilha em build/trailer/audio.wav
python tools/trailer/render.py --preview   # 3) (opcional) folhas de contato dos quadros-chave
python tools/trailer/render.py --full      # 4) vídeo final: build/trailer/kibitz-trailer.mp4 (1080p, 30 fps)
```

| Arquivo | O que faz |
|---|---|
| `timeline.json` | BPM, cenas e cues em "batidas originais" (1 batida = 0,6 s) e a **dobra de tempo** (`warp`): alonga cenas para dar tempo de ler. `trailer.html` e `make_audio.py` aplicam a mesma dobra, então imagem e som continuam na mesma batida. |
| `trailer.html` | Motor de cena: `renderFrame(t)` desenha um quadro como função do tempo (tipografia animada, câmera, glitch…). |
| `capture_assets.py` | Sobe o app numa pasta temporária e captura as telas e o raciocínio real da IA usados no vídeo. |
| `make_audio.py` | Trilha: pad, baixo com sidechain, bateria, piano, risers e impactos, em Lá menor a 100 BPM. |
| `render.py` | Renderiza quadro a quadro com Playwright e codifica com ffmpeg (H.264 + AAC, BT.709). |

Regras do vídeo: **nenhuma estatística ou número na tela** (os números que aparecem pequenos são só da interface real), todo texto
tem tempo de leitura (cenas esticadas pela dobra) e a citação é um comentário real da partida de demonstração. Os comentários de
revisão mostrados são sobre lances da IA.
