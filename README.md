# Mara Slipstream CLI (`mara.py`)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Script de terminal para enviar transações Bitcoin pela **Slipstream**, o serviço da
pool **MARA** que aceita transações grandes ou fora do padrão diretamente, sem
passar pela fila normal do mempool.

Além de enviar e consultar o status, o script **consulta as taxas da MARA antes do
envio** — a taxa mínima aceita muda durante o dia (já vi passar de 1 para 2 sat/vB de
um dia para o outro), e sem essa checagem a transação é recusada só depois de você
colar o HEX inteiro.

---

## Recursos

- **Enviar transação** — envia um HEX já assinado para a Mara.
- **Consultar transação** — status pelo TXID.
- **Consultar taxas atuais** — taxa mínima de envio, taxa minerável, taxa de mercado e multiplicador.
- **Aviso antes do envio** — mostra a taxa mínima vigente e, se a `embit` estiver
  instalada, o tamanho da sua transação em vB e o **mínimo em sats** que ela precisa pagar.
- **TXID copiado automaticamente** para a área de transferência.
- **Ctrl+C não fecha as telas de resultado** — dá para selecionar e copiar o JSON/TXID
  sem derrubar o programa.
- **Modo script** — `python3 mara.py taxas` imprime as taxas e sai; ideal para cron/alertas.
- Lê HEX por **stdin/pipe** (sem precisar colar no terminal).

---

## Requisitos

- Python 3.8+
- [`requests`](https://pypi.org/project/requests/)

```bash
pip install requests
```

Opcional:

- [`embit`](https://pypi.org/project/embit/) — habilita o cálculo de `vsize` e do
  mínimo em sats antes do envio.
- Ferramenta de área de transferência: `wl-clipboard` (`wl-copy`), `xclip`, `xsel`
  ou o pacote `pyperclip`. Sem nenhuma delas, o TXID é apenas exibido na tela.

```bash
pip install embit          # opcional
sudo apt install wl-clipboard xclip   # opcional (clipboard)
```

---

## Uso

```bash
python3 mara.py
```

```
=== MARA SLIPSTREAM ===
1) Enviar transacao
2) Consultar transacao
3) Consultar taxas atuais
0) Sair
```

### 1) Enviar transação

Cole o HEX assinado e pressione `Ctrl+D`. Antes de enviar, o script mostra as taxas:

```
Taxa minima aceita agora: 2 sat/vB (mineravel: 6 sat/vB)
Sua tx tem 615 vB -> precisa pagar pelo menos 1230 sats de taxa.
Se o HEX pagar menos que isso, a Mara recusa o envio.
```

E depois do envio:

```
TXID copiavel:
abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789
(TXID copiado para a area de transferencia via wl-copy)
```

> O script **não assina** nada: ele apenas envia um HEX que você já assinou
> (gelowallet, Sparrow, Electrum, etc.). Enviar duas vezes a mesma transação ou
> HEXes conflitantes é responsabilidade sua.

### 2) Consultar transação

Digite/cole o TXID e o JSON de status é exibido.

### 3) Consultar taxas

```
=== TAXAS MARA SLIPSTREAM ===
Altura do bloco      : 973714
Taxa de mercado      : 3 sat/vB
Multiplicador        : 2x
Taxa mineravel       : 6 sat/vB
Taxa MINIMA p/ envio : 2 sat/vB

Transacao com fee rate abaixo de 2 sat/vB e recusada pela Mara.
```

### Modo não interativo

```bash
python3 mara.py taxas     # imprime as taxas e sai (código 0; 1 em caso de erro)
python3 mara.py --help
```

Enviar HEX por pipe (o `1` escolhe a opção de envio no menu):

```bash
{ echo 1; cat minha_tx.hex; } | python3 mara.py
```

Exemplo de monitoramento da taxa mínima:

```bash
while true; do
  python3 mara.py taxas | grep 'MINIMA'
  sleep 300
done
```

---

## Como as taxas são lidas

O script usa os mesmos endpoints públicos do site da Slipstream:

| Endpoint | Para que serve |
| --- | --- |
| `GET /api/rates` | Taxas atuais (mínima, minerável, mercado, multiplicador) |
| `GET /api/block-info` | Altura do bloco atual (exibida junto das taxas) |
| `POST /api/transactions` | Envio do HEX assinado |
| `GET /api/transactions/status?tx_id=...` | Status de um TXID |

Resposta de `/api/rates`:

```json
{
  "market_rate": 3.0,
  "multiplier": 2.0,
  "multiplier_discount_percent": 0,
  "discounted_multiplier": 2.0,
  "slipstream_rate": 6.0,
  "effective_rate": 6.0,
  "submit_fee_rate": 2.0
}
```

| Campo | Significado |
| --- | --- |
| `submit_fee_rate` | **Taxa mínima aceita no envio** (sat/vB). É o valor que muda e derruba envios. |
| `effective_rate` | Taxa efetiva/minerável atual (o que a Mara espera receber na prática). |
| `market_rate` | Taxa de mercado (mempool) usada como referência. |
| `multiplier` / `discounted_multiplier` | Multiplicador aplicado e o multiplicador com desconto. |
| `multiplier_discount_percent` | Desconto (%) sobre o multiplicador, se houver. |
| `slipstream_rate` | Taxa cheia da Slipstream, antes do desconto. |

`/api/rates` aceita `?client_code=...` (opcional) — o script já suporta isso na
função `obter_taxas()`, mas o menu usa o código padrão.

---

## Limitações

- **Não é possível verificar, antes do envio, se o seu HEX paga o mínimo.** Isso
  exigiria os valores dos UTXOs gastos, e o proxy `/mempool/api/tx/` da Mara
  responde 403/timeout fora do navegador. O script mostra a mínima em sat/vB e em
  sats (para o `vsize` da sua transação) para você comparar com a taxa que a
  carteira mostrou.
- **Endpoints não documentados oficialmente.** Foram obtidos do bundle JS do
  `slipstream.mara.com` e testados em outubro/2026. Se a Mara mudar a API, o script
  quebra — a consulta de taxas é a parte mais frágil, por isso o envio continua
  funcionando (com aviso) se `/api/rates` falhar.
- **Sem autenticação e sem chaves.** O script não guarda seed, WIF nem senha; ele
  só transporta HEX já assinado.
- **Clipboard** depende de ferramenta do sistema e de sessão gráfica
  (`WAYLAND_DISPLAY`/`DISPLAY`). Em SSH/headless, o TXID é apenas exibido.

---

## Estrutura do código

| Função | Papel |
| --- | --- |
| `obter_taxas()` | Consulta `/api/rates` e devolve o dict de taxas |
| `obter_altura_bloco()` | Consulta `/api/block-info` (falha silenciosa) |
| `mostrar_taxas()` | Formata a tabela de taxas no terminal |
| `consultar_taxas()` | Opção 3 do menu |
| `enviar_transacao()` | Opção 1: HEX, checagem de taxa mínima, POST e TXID |
| `consultar_transacao()` | Opção 2: status por TXID |
| `estimar_vsize()` | Calcula vB via `embit` (opcional) |
| `copiar_para_area_transferencia()` | Copia o TXID (`wl-copy`/`xclip`/`xsel`/`pyperclip`) |
| `pausar()` / `sem_ctrl_c()` | Pausa segura: Ctrl+C não fecha a tela |
| `read_hex_input()` | Lê o HEX do terminal ou de um pipe |

---

## Aviso

Ferramenta pessoal, sem vínculo com a MARA. Use por sua conta e risco; confira o
TXID e o valor da taxa antes de confiar em transações de valor alto.

---

## Licença

Distribuído sob a **licença MIT** — veja o arquivo [LICENSE](LICENSE) para o texto completo.

```
MIT License

Copyright (c) 2026 Tadeu Cadilhe

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Em resumo: você pode usar, copiar, modificar, publicar, distribuir, sublicenciar e
vender o software, desde que mantenha o aviso de copyright e esta licença. O
software é fornecido **sem garantias** de qualquer tipo.
