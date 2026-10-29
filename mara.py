#!/usr/bin/env python3
import contextlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys

import requests

SEND_URL = "https://slipstream.mara.com/api/transactions"
STATUS_URL = "https://slipstream.mara.com/api/transactions/status"
RATES_URL = "https://slipstream.mara.com/api/rates"
BLOCK_INFO_URL = "https://slipstream.mara.com/api/block-info"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "origin": "https://slipstream.mara.com",
    "referer": "https://slipstream.mara.com/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
    "dnt": "1",
}


def obter_taxas(client_code=""):
    """Consulta /api/rates e devolve as taxas atuais da Slipstream.

    Campos relevantes:
      submit_fee_rate -> taxa MINIMA (sat/vB) aceita no envio; muda ao longo do dia.
      effective_rate  -> taxa "mineravel" que a Mara espera receber agora.
      market_rate     -> taxa de mercado (mempool) usada de referencia.
    """
    params = None
    if client_code:
        params = {"client_code": client_code}
    r = requests.get(RATES_URL, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("resposta inesperada de /api/rates")
    return data


def obter_altura_bloco():
    try:
        r = requests.get(BLOCK_INFO_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
        altura = r.json().get("block_height")
    except Exception:
        return None
    return altura if isinstance(altura, int) else None


def formatar_taxa(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return "?"
    texto = ("%.2f" % valor).rstrip("0").rstrip(".")
    return texto


def mostrar_taxas(taxas, altura=None):
    submit = taxas.get("submit_fee_rate")
    efetiva = taxas.get("effective_rate")
    mercado = taxas.get("market_rate")
    multiplicador = taxas.get("multiplier")
    mult_desc = taxas.get("discounted_multiplier")
    desconto = taxas.get("multiplier_discount_percent")

    print("=== TAXAS MARA SLIPSTREAM ===")
    if altura:
        print("Altura do bloco      : %d" % altura)
    print("Taxa de mercado      : %s sat/vB" % formatar_taxa(mercado))

    if isinstance(multiplicador, (int, float)) and not isinstance(multiplicador, bool):
        linha = "Multiplicador        : %sx" % formatar_taxa(multiplicador)
        if isinstance(desconto, (int, float)) and desconto:
            linha += " (desconto de %s%%, aplicado: %sx)" % (
                formatar_taxa(desconto),
                formatar_taxa(mult_desc),
            )
        print(linha)

    print("Taxa mineravel       : %s sat/vB" % formatar_taxa(efetiva))
    print("Taxa MINIMA p/ envio : %s sat/vB" % formatar_taxa(submit))
    if isinstance(submit, (int, float)) and not isinstance(submit, bool):
        print()
        print("Transacao com fee rate abaixo de %s sat/vB e recusada pela Mara." % formatar_taxa(submit))
    print()


@contextlib.contextmanager
def sem_ctrl_c():
    """Ignora Ctrl+C durante a pausa, para dar tempo de copiar o resultado.

    Sem isso, selecionar o TXID/JSON com o mouse e apertar Ctrl+C derrubava o
    programa (o Ctrl+C virava KeyboardInterrupt em vez de copiar o texto).
    """
    anterior = None
    try:
        anterior = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (ValueError, OSError):
        anterior = None
    try:
        yield
    finally:
        if anterior is not None:
            try:
                signal.signal(signal.SIGINT, anterior)
            except (ValueError, OSError):
                pass


def copiar_para_area_transferencia(texto):
    """Copia o texto para a area de transferencia e devolve o nome da ferramenta usada."""
    if not texto:
        return None

    comandos = []
    if os.environ.get("WAYLAND_DISPLAY"):
        comandos.append(["wl-copy"])
    comandos.append(["xclip", "-selection", "clipboard"])
    comandos.append(["xsel", "--clipboard", "--input"])
    comandos.append(["wl-copy"])

    for comando in comandos:
        if shutil.which(comando[0]) is None:
            continue
        try:
            processo = subprocess.run(
                comando,
                input=texto.encode(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except Exception:
            continue
        if processo.returncode == 0:
            return comando[0]

    try:
        import pyperclip

        pyperclip.copy(texto)
        return "pyperclip"
    except Exception:
        return None


def pausar(mensagem="\nPressione ENTER para continuar..."):
    """Pede ENTER so no modo interativo (com HEX vindo de pipe nao ha teclado)."""
    if not sys.stdin.isatty():
        return
    with sem_ctrl_c():
        try:
            input(mensagem)
        except (EOFError, KeyboardInterrupt):
            print()


def consultar_taxas():
    print("\nConsultando taxas da Mara...\n")
    try:
        taxas = obter_taxas()
    except Exception as e:
        print("Erro ao consultar as taxas: %s" % e, file=sys.stderr)
        pausar("\nPressione ENTER para voltar ao menu...")
        return
    mostrar_taxas(taxas, obter_altura_bloco())
    pausar("\nPressione ENTER para voltar ao menu...")


def read_hex_input():
    raw = None
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
        except Exception as e:
            print("Erro ao ler stdin: %s" % e, file=sys.stderr)
            return None
    else:
        try:
            sys.stderr.write("Cole o RAW hex assinado e pressione Ctrl+D para enviar (ou Ctrl+C para voltar):\n")
            sys.stderr.flush()
            raw = sys.stdin.read()
        except EOFError:
            pass
        except KeyboardInterrupt:
            print()
            return None

    if not raw or not str(raw).strip():
        return None

    hex_tx = "".join(str(raw).strip().split())
    if not hex_tx:
        return None
    return hex_tx


def estimar_vsize(hex_tx):
    """Tamanho virtual (vB) da transacao, para conferir a taxa minima.

    Usa a embit se estiver instalada; se nao estiver (ou o HEX for invalido),
    devolve None e o aviso de taxa minima segue so com o valor em sat/vB.
    """
    try:
        from embit import transaction
        from embit.script import Script
    except Exception:
        return None

    try:
        tx = transaction.Transaction.from_string(hex_tx)
        sem_testemunha = transaction.Transaction.from_string(hex_tx)
        for vin in sem_testemunha.vin:
            vin.witness = Script(b"")
        peso = len(sem_testemunha.serialize()) * 3 + len(tx.serialize())
    except Exception:
        return None

    return (peso + 3) // 4


def enviar_transacao():
    while True:
        hex_tx = read_hex_input()
        if hex_tx is None:
            print("\nVoltando ao menu...\n")
            return

        payload = {"tx_hex": hex_tx}

        try:
            taxas = obter_taxas()
        except Exception:
            taxas = None

        if taxas:
            minimo = taxas.get("submit_fee_rate")
            if isinstance(minimo, (int, float)) and not isinstance(minimo, bool):
                print(
                    "Taxa minima aceita agora: %s sat/vB (mineravel: %s sat/vB)"
                    % (formatar_taxa(minimo), formatar_taxa(taxas.get("effective_rate")))
                )
                vsize = estimar_vsize(hex_tx)
                if vsize:
                    minimo_sats = math.ceil(round(vsize * minimo, 6))
                    print(
                        "Sua tx tem %d vB -> precisa pagar pelo menos %d sats de taxa."
                        % (vsize, minimo_sats)
                    )
                print("Se o HEX pagar menos que isso, a Mara recusa o envio.\n")
            else:
                mostrar_taxas(taxas)
        else:
            print("Aviso: nao foi possivel consultar as taxas atuais da Mara.\n", file=sys.stderr)

        try:
            r = requests.post(SEND_URL, headers=HEADERS, json=payload, timeout=30)
            try:
                data = r.json()
            except Exception:
                print(r.text)
                pausar()
                return

            print(json.dumps(data, ensure_ascii=False, indent=2))

            if r.ok and isinstance(data, dict) and data.get("status") == "success":
                txid = data.get("message") or data.get("txid") or data.get("tx_hash")
                if txid:
                    print("\nTXID copiavel:")
                    print(txid)
                    ferramenta = copiar_para_area_transferencia(str(txid))
                    if ferramenta:
                        print("(TXID copiado para a area de transferencia via %s)" % ferramenta)
                    else:
                        print(
                            "(selecione o TXID acima com o mouse e copie com Ctrl+Shift+C;"
                            " Ctrl+C aqui nao fecha o programa)"
                        )
            pausar("\nPressione ENTER para voltar ao menu...")
            return
        except Exception as e:
            print("Erro: %s" % e, file=sys.stderr)
            pausar()
            return


def consultar_transacao():
    while True:
        print("Digite ou cole o TXID (ou pressione ENTER para voltar):")
        txid = ""
        if sys.stdin.isatty():
            try:
                txid = input().strip()
            except EOFError:
                print("\nVoltando ao menu...\n")
                return
            except KeyboardInterrupt:
                print("\nVoltando ao menu...\n")
                return
        else:
            try:
                txid = sys.stdin.read().strip()
            except Exception:
                txid = ""
            if not txid:
                print("\nVoltando ao menu...\n")
                return
        txid = txid.replace("\n", "").replace("\r", "").strip()
        if not txid:
            print("\nVoltando ao menu...\n")
            return

        try:
            params = {"tx_id": txid}
            r = requests.get(STATUS_URL, headers=HEADERS, params=params, timeout=30)
            try:
                data = r.json()
            except Exception:
                print(r.text)
                pausar("\nPressione ENTER para voltar ao menu...")
                return

            print(json.dumps(data, ensure_ascii=False, indent=2))
            pausar("\nPressione ENTER para voltar ao menu...")
            return
        except Exception as e:
            print("Erro: %s" % e, file=sys.stderr)
            pausar()
            return


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip().lower()
        if arg in ("taxas", "taxa", "rates", "-t", "--rates"):
            try:
                taxas = obter_taxas()
            except Exception as e:
                print("Erro ao consultar as taxas: %s" % e, file=sys.stderr)
                return 1
            mostrar_taxas(taxas, obter_altura_bloco())
            return 0
        if arg in ("-h", "--help", "help", "ajuda"):
            print("Uso: %s [taxas]" % sys.argv[0])
            print("  (sem argumento)  abre o menu interativo")
            print("  taxas            mostra as taxas atuais da Mara e sai")
            return 0

    while True:
        print("=== MARA SLIPSTREAM ===")
        print("1) Enviar transacao")
        print("2) Consultar transacao")
        print("3) Consultar taxas atuais")
        print("0) Sair")
        print()
        try:
            opcao = input("Escolha uma opcao: ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            print("\nSaindo...")
            break

        if opcao == "1":
            enviar_transacao()
        elif opcao == "2":
            consultar_transacao()
        elif opcao == "3":
            consultar_taxas()
        elif opcao == "0":
            print("Saindo...")
            break
        else:
            print("Opcao invalida\n")
            continue


if __name__ == "__main__":
    sys.exit(main())

