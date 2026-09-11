# Epic Seven Daily Bot

Automatiza atividades diárias do Epic Seven (mail, sanctuary, hunt com filtro
de stats, guild, world boss, shop, lojinha do labirinto). Foco no **PC Client**
(Stove launcher) com fallback para emuladores Android via ADB.

> ⚠️ Use por sua conta e risco. Stove pode banir contas que automatizam input.
> Recomendado: testar em conta secundária e usar emulador antes do PC Client.

## O que está pronto

- **Core**: driver mouse (PC Client) + driver ADB (emulador), template matcher
  com `cv2.matchTemplate`, classe `Routine` com retry/timeout/screenshot em falha,
  orchestrator que encadeia routines via `config.yaml` e escreve histórico CSV.
- **Routines (lógica completa, faltam apenas templates PNG)**:
  - `login` — coleta mail
  - `sanctuary` — gold tree, training camp, forest of souls
  - `guild` — check-in + donation
  - `worldboss` — uma rodada com time padrão
  - `hunt` — auto-hunt com **stop-on-drop** (OCR Tesseract dos substats)
  - `shop` — delega ao `Epic-Seven-E7-Secret-Shop-Refresh` existente
  - `labyrinth_shop` — entra no labirinto e compra na lojinha do NPC

## Setup rápido (PC Client, PT-BR)

### 1. Instalar dependências
```bash
python -m pip install -r requirements.txt
```

Para a routine `hunt` (OCR de substats), instale Tesseract OCR com idioma português:
- Baixe: https://github.com/UB-Mannheim/tesseract/wiki
- Marque "Portuguese" durante a instalação
- Adicione `C:\Program Files\Tesseract-OCR` ao PATH

### 2. Configurar
Edite `config.yaml`. O default já está em modo **mouse / PC Client**:
```yaml
driver:
  kind: mouse
  window_title: "Epic Seven"   # exato — passe o mouse no ícone da taskbar p/ ver
  width: 1280                  # janela será redimensionada para isso
  height: 720
```

### 3. Capturar templates (a parte que requer trabalho manual)

Cada routine precisa de pequenos PNGs que identificam botões/ícones na sua
tela. Templates são específicos para a sua resolução e idioma — por isso
ninguém pode pré-fornecer.

Workflow:
```bash
# 1. Abra o jogo, espere chegar no lobby
# 2. Para cada template necessário, rode:
python tools/capture.py common/lobby_anchor

# Uma janela abre mostrando o screenshot da sua tela do jogo.
# Arraste um retângulo bem ajustado em volta do elemento.
# Pressione ENTER ou ESPAÇO. O PNG é salvo em assets/common/lobby_anchor.png
```

**Lista de templates por prioridade** (capture os comuns primeiro, eles servem
para todas as routines):

#### Comuns (CAPTURE PRIMEIRO — são reusados)
- `common/lobby_anchor` — qualquer ícone único do lobby (ex: ícone de energia)
- `common/back_arrow` — seta de voltar in-game
- `common/confirm` — botão "OK" / "Confirmar"
- `common/cancel` — botão "Cancelar" / X

#### Login (mais simples — comece por aqui pra validar tudo)
- `login/mail_icon` — envelope no canto do lobby
- `login/claim_all` — botão "Receber tudo" dentro da caixa de mensagem
- `login/login_bonus` — banner do bônus diário (opcional)

#### Sanctuary
- `sanctuary/sanctuary_icon`, `gold_tree`, `gold_tree_harvest`
- `sanctuary/training_camp`, `training_collect`, `training_dispatch`
- `sanctuary/forest`, `forest_collect`

#### Guild
- `guild/guild_icon`, `checkin`, `donate`, `donate_max`

#### World Boss
- `worldboss/worldboss_icon`, `start_button`, `confirm_team`, `result_screen`

#### Hunt (mais complexa)
- `hunt/hunt_icon`, `hunt/wyvern` (e/ou banshee/golem), `hunt/difficulty_13`
- `hunt/start_battle`, `hunt/result_victory`
- `hunt/gear_drop_popup` — banner que aparece quando dropa equipamento
- `hunt/no_drop_continue` — botão "Continuar" da tela de vitória sem drop
- `hunt/drop_close` — fechar/avançar no popup de drop
- `hunt/gear_kind_boots`, `gear_kind_ring`, etc — para identificar tipo do drop

#### Labyrinth Shop
- `labyrinth_shop/labyrinth_icon`, `shop_npc`, `covenant`, `friendship`,
  `buy_button`, `exit_labyrinth`

### 4. Validar templates capturados
```bash
python tools/calibrate.py --filter common/
python tools/calibrate.py --filter login/
```

Cada template deve aparecer com `OK conf=0.9XX`. Se vier `LOW conf=0.6X`,
recapture com um recorte mais apertado.

### 5. Rodar a primeira routine (validação)
```bash
python run.py routine login -v
```

Se passar, edite `config.yaml` para incluir só `login` em `daily:` e teste:
```bash
python run.py daily -v
```

Vá adicionando routines uma a uma conforme captura os templates.

## Uso diário

```bash
python run.py daily              # roda a chain completa do config.yaml
python run.py routine hunt -v    # roda só hunt com logs INFO
python run.py routine hunt -vv   # logs DEBUG (todos comandos ADB/mouse)
python run.py list               # lista routines registradas
```

Histórico em `logs/routine_history.csv`. Falhas geram screenshot em `logs/`.

## Auto-hunt: como funciona o filtro

No `config.yaml`:
```yaml
routines:
  hunt:
    target: wyvern
    difficulty: 13
    stop_on_drop:
      - gear: boots
        main_stat: speed
        substats_any: [speed, crit_chance, crit_damage]
      - gear: ring
        main_stat: attack_pct
    max_battles: 60
```

Cada item da lista é uma **regra OR**. Se qualquer regra bater no drop, o bot
para e te avisa. Dentro de uma regra:
- `gear`: tipo (boots, ring, weapon, helmet, armor, necklace)
- `main_stat`: stat principal exato
- `substats_any`: pelo menos um destes nos substats
- `substats_all`: todos estes nos substats

Como funciona internamente:
1. Ao final da batalha o bot detecta o popup de drop via template.
2. Identifica o tipo do gear comparando templates `gear_kind_*`.
3. Recorta a região onde os substats aparecem e roda Tesseract com idioma `por`.
4. Parseia os 4 substats em `(stat, valor)` usando aliases PT-BR.
5. Compara com cada filtro. Match → para. Sem match → fecha popup, próxima.

A região de OCR é definida em `e7bot/routines/hunt.py` como
`SUBSTAT_REGION_NORM = (0.40, 0.55, 0.30, 0.20)` — frações da janela. Ajuste se
o popup do seu cliente tiver layout diferente.

## Arquitetura

```
e7-daily-bot/
├── e7bot/
│   ├── core/
│   │   ├── driver.py          # AdbDriver (emulador)
│   │   ├── mouse_driver.py    # MouseDriver (PC Client)
│   │   ├── matcher.py         # template matching com find/wait_for/tap_when_found
│   │   └── routine.py         # base class + StepContext + RoutineResult
│   ├── routines/
│   │   ├── _base.py           # LobbyRoutine: ensure_lobby, confirm_dialog, ...
│   │   ├── login.py
│   │   ├── sanctuary.py
│   │   ├── guild.py
│   │   ├── hunt.py
│   │   ├── worldboss.py
│   │   ├── shop.py            # delega ao Shop Refresh existente
│   │   └── labyrinth_shop.py
│   ├── ocr/
│   │   └── stat_reader.py     # Tesseract + parser PT-BR
│   └── orchestrator.py
├── assets/                    # templates PNG (você captura)
├── tools/
│   ├── capture.py             # captura região como template
│   └── calibrate.py           # valida que todos templates batem
├── config.yaml
└── run.py
```

## Troubleshooting

**`Window with title 'Epic Seven' not found`** — o título exato pode variar.
Passe o mouse no ícone da taskbar do jogo, copie o título completo e cole em
`config.yaml > driver.window_title`.

**Templates com confiança baixa (`LOW conf=0.6X`)** — recapture com recorte
mais apertado. Evite incluir bordas com gradiente ou animações.

**`pytesseract` não encontrado** — instale Tesseract OCR no sistema (link acima)
e adicione ao PATH. Sem isso o `hunt` filtra só por tipo de gear.

**Bot é detectado / banido** — não use no PC Client em conta principal. Os
`tap_jitter_px` e `tap_delay` em config ajudam, mas não eliminam risco.

## Inventory Analyzer (build / junk / fit) — não precisa do emulador

Lê os saves do Fribbels e te dá três visões acionáveis sem precisar mexer no
otimizador. Útil para decidir quem buildar e o que jogar fora.

### Como funciona

1. Pega o save mais recente em `~/Documents/FribbelsOptimizerSaves/` (ou passe
   `--save <caminho>`).
2. Cruza seus heróis e itens com a biblioteca em [data/meta_builds.yaml](data/meta_builds.yaml)
   (~25 heróis curados — DPS cleavers, supports, hunt specialists, PvP).
3. Pontua cada item contra cada build relevante: set match + main stat fit +
   substats prioritários + rank/enhance.

### Comandos

```bash
# Visão geral: prioridades + 20 piores itens
python run.py analyze

# Quem da minha conta vale buildar (em ordem de tier)
python run.py priorities

# Itens com score baixo em TODA roster — candidatos a descarte
python run.py junk --limit 50
python run.py junk --include-locked    # também mostra itens locked (raro)

# Top-3 melhores itens do meu inventário pra Ruele em cada slot
python run.py fit "Ruele of Light" --top 3

# Acabei de pegar este item — alguém da minha conta quer?
python run.py whois <item_id>

# Tudo aceita --save <path>, --meta <path>, --junk-threshold <num>
python run.py junk --junk-threshold 50    # mais agressivo: descarta o que tiver score < 50
```

### Exemplo de saída real (testgear.json)

```
=== Inventory summary ===
  Heroes:                    10
  Heroes with meta build:    3
  Items total:               772
    locked:                  2
    unlocked:                770
  Junk candidates:           43  (5.6% of inventory, threshold=30)

=== Build priorities (3 owned heroes match meta) ===
Tier  Hero                    R  Slots  Role
  1   Ruele of Light          5  6/6    Revive healer
  1   Martial Artist Ken      5  0/6    Single-target stripper / DPS
  1   Seaside Bellona         5  0/6    Single-target nuker / cleave

=== Junk candidates ===
  1   -56.1  necklace   CriticalSet    Good    +12  crit_chance   crit_damage=4, defense=23, attack=65, ...
  2   -41.8  boots      InjurySet      Rare    +9   attack_pct    speed=2, crit_damage=4, health_pct=4
  ...
```

### Adicionando seus heróis ao meta

Os 25 builds default cobrem heróis populares. Para adicionar um nicho seu:

1. Edite [data/meta_builds.yaml](data/meta_builds.yaml).
2. Use o nome canônico do herói (igual ao Fribbels — em inglês).
3. Defina `sets_priority`, `main_necklace`, `main_ring`, `main_boots`, e
   `substats_priority`. Veja os builds existentes como template.

Ou crie um arquivo separado e passe `python run.py analyze --meta meu_meta.yaml`.

### Score por dentro

Para cada item × build:
- **Set component**: `+50` se for set #1 da prioridade, decai 60% por posição.
- **Main component** (só N/R/B): `+40` se main aceitável (#1), `-50` se não.
- **Substats component**: cada substat na lista de prioridade contribui peso
  decrescente (decay 0.65), escalado pela qualidade do roll (`valor / ceiling`).
  Bonus de `+5` se tem speed mesmo não sendo prioridade top.
- **Rank/Enhance**: Epic +15, Heroic +5, Rare/Good penalizados. +0/+9 epic não
  é punido (gear novo com potencial).

Score >= 70 → ótimo. 30..70 → ok. < 30 → junk candidate.

### Sinergia com o resto

```
[Fribbels Optimizer]               # você importa gear (auto)
        ↓ salva em ~/Documents/...
        ↓
[python run.py analyze]            # eu te digo o que descartar e quem buildar
        ↓
[Fribbels Optimizer (otimizar)]    # você roda otimização nos heroes priorizados
        ↓
[python run.py daily]              # bot roda dailies, refresh shop, hunt etc
        ↓ (futuro)
[python run.py routine hunt]       # quando dropar gear bom, pausa e te avisa
```

## Build planner (com dados reais da comunidade Fribbels)

Esta camada usa a **mesma API que alimenta a [hero-library do Fribbels](https://fribbels.github.io/e7/hero-library.html)**
(`POST krivpfvxi0...amazonaws.com/dev/getBuilds`) — ela retorna até 3000 builds
reais submetidos pela comunidade por herói, com sets equipados e stats finais.

Cruzo isso com seu inventário pra responder duas perguntas:
- **"Quais heroes da minha wishlist eu já consigo buildar agora?"**
- **"O que preciso upar/farmar pra fechar a build dele?"**

### Setup

1. Edite [priorities.yaml](priorities.yaml) com sua lista de prioridades:
   ```yaml
   priorities:
     - name: Ruele of Light
       action: improve     # build | improve | maintain | skip
       priority: 1
       notes: "Healer principal"
     - name: Martial Artist Ken
       action: build
       priority: 2
   ```

2. Pré-carregue cache de builds da comunidade (dura 14 dias):
   ```bash
   python run.py fetch-builds                    # todos da wishlist
   python run.py fetch-builds "Ruele of Light"   # um hero específico
   python run.py fetch-builds --force            # ignorar cache
   ```

### Comandos novos

```bash
# Mostra sua wishlist com flag de owned/not-owned
python run.py wishlist

# Resumo: cada hero da wishlist + status de build
python run.py readiness
# Output:
#   READY    100%  Ruele of Light       SpeedSet(4) + HealthSet(2)
#   ALMOST   83%   Seaside Bellona      LifestealSet(4) + ImmunitySet(2)
#   ALMOST   67%   Martial Artist Ken   DestructionSet(4) + PenetrationSet(2)

# Detalhe por slot — qual item escolhi pra cada posição e por que
python run.py readiness "Ruele of Light"

# Plano de upgrade: o que upar/farmar pra fechar a build
python run.py upgrade "Martial Artist Ken"
# Output sorted by impact:
#   farm   ring    -    Farm ring of PenetrationSet at Banshee Hunt 11+. ...
#   farm   boots   -    Farm boots of PenetrationSet at Banshee Hunt 11+. ...
```

### Como o readiness funciona

1. Pega o **combo de set mais popular** entre os 1000 builds mais recentes
   submetidos pra esse hero. Ex: Ruele = SpeedSet(4)+HealthSet(2) (29.5% das submissões).
2. Atribui slots ao combo (slots 1-4 para o set 4-piece, 5-6 para o 2-piece).
3. Pra cada slot, busca o melhor item do seu inventário que:
   - Pertence ao set requerido
   - Tem main stat aceitável (do `meta_builds.yaml`)
   - Pontua bem nos substats prioritários do hero
4. Slot com score >= 50 → "ready"; < 50 ou sem item do set → "not ready"
5. % readiness = ready_slots / 6

### Como o upgrade funciona

Pra cada slot não-ready:
1. **Action `enhance`**: tem itens do set certo no inventário com `+enhance < 15`?
   Projeta o score se fosse +15 e mostra os 3 maiores ganhos.
2. **Action `farm`**: zero candidatos? Sugere onde farmar (Hunt 11+ baseado
   no set requerido). Tabela completa em `e7bot/builder/upgrade.py:SET_FARM_SOURCES`.

Ações sorteadas por **estimated_score_gain** descendente — você sabe onde
investir cromos primeiro pra maior impacto.

### Cache local

Builds ficam em `cache/fribbels/builds/<HeroName>.json`. Após 14 dias o sistema
re-faz o fetch. Pra forçar atualização: `--force`. Cache total para 100 heroes
~ 60 MB (cada hero retorna 3000 builds × ~250 bytes/build).

### Arquitetura — como tudo se encaixa

```
              priorities.yaml (você edita)
                       ↓
              ┌─────────────────────┐
              │   wishlist heroes   │
              └──────────┬──────────┘
                         │
        ┌────────────────┼─────────────────────┐
        │                │                     │
        ▼                ▼                     ▼
  meta_builds.yaml   FribbelsClient       Fribbels save (~/Documents/...)
  (você curou)       (3000 builds/hero)   (auto-import)
        │                │                     │
        └────────┬───────┘                     │
                 │                             │
                 ▼                             ▼
       community top combo                user inventory
                 │                             │
                 └─────────────┬───────────────┘
                               ▼
                    ReadinessChecker
                    (slot picks + score)
                               │
                               ▼
                    UpgradeRecommender
                    (enhance / farm actions)
                               │
                               ▼
                          actionable plan
```

## GUI web local (Streamlit)

Toda a análise + ações disponíveis numa interface clicável que abre no navegador.
Sem build step, sem instalação de Node — é Python puro.

### Iniciar

```bash
# Opção A: duplo-clique
webapp.bat

# Opção B: linha de comando
py -m streamlit run webapp/app.py
```

Abre automaticamente em http://localhost:8501. Hot-reload: edite qualquer
arquivo em `webapp/` e o navegador atualiza sozinho.

### Páginas disponíveis

| Página | O que tem |
|---|---|
| **🏠 Home** | Sumário (itens, junk, heroes), prontidão da wishlist em cards com barras de progresso, atalhos pras outras páginas |
| **📊 Inventário** | Junk pile (tabela ordenável + download CSV), prioridades de build, breakdown por raridade/set/tipo. Slider de threshold ao vivo. |
| **⚔️ Prontidão** | Cards por hero com status (READY/ALMOST/PARTIAL/NOT_READY), botão "Detalhe" que abre tabela slot-a-slot e plano de upgrade |
| **🎁 Drop Check** | Cola um item ID OU filtra inventário interativamente. Veredito visual (✅ KEEP / 🗑️ DISCARD) + tabela de impacto por hero |
| **⚖️ Comparar** | Dropdown de 2 heroes → comparação lado a lado com banner de "buildar X primeiro" |
| **📝 Wishlist** | Editor CRUD inline da `priorities.yaml` (data_editor do Streamlit), sugestões automáticas de heroes próprios sem entrada |

### Configuração

Sidebar de cada página tem o campo "Save do Fribbels" — aponta pro arquivo
`.txt`/`.json`. Default tenta encontrar automaticamente em
`~/Documents/FribbelsOptimizerSaves/`.

Botão "🔄 Recarregar dados" limpa o cache do Streamlit e relê o save (use após
o Fribbels reimportar).

### Notificações

Toast no canto da tela quando algo acontece — ex.: "Item vale guardar! ✅" ao
rodar drop check.

### Performance

- Save é cacheado em memória com TTL de 1h.
- Builds da comunidade são cacheados em disco (14 dias) — primeira vez que abrir
  a página de prontidão, ela baixa builds dos heroes da wishlist (~300ms cada).
- Análise completa de 772 itens × 30 builds → ~2s na primeira vez, instantâneo
  depois.

## Próximos passos sugeridos

- [ ] Adicionar dispatch (coletar + reenviar heroes)
- [ ] Adicionar arena 3× / spirit altar 3× se você quiser
- [ ] Notificação Discord/Telegram quando hunt encontra match ou junk excede X%
- [ ] Integração: após hunt match, disparar scanner para importar gear no otimizador
- [ ] Modo `--export-discard` que gera lista de IDs para você selecionar no Fribbels
