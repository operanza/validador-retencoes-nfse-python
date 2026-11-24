"""Interface de linha de comando para o validador de retenções de NFS-e."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from validador_nfse.models import RelatorioValidacao
from validador_nfse.validator import validar_nfse


def _formatar_relatorio_texto(relatorio: RelatorioValidacao) -> str:
    linhas = [
        "=== Relatório de Conferência de Retenções (NFS-e) ===",
        f"Valor dos serviços : R$ {relatorio.valor_servicos:.2f}",
        f"Deduções           : R$ {relatorio.deducoes:.2f}",
        f"Base do ISS        : R$ {relatorio.base_iss:.2f}",
        f"Retido informado   : R$ {relatorio.total_retido_informado:.2f}",
        f"Retido esperado    : R$ {relatorio.total_retido_esperado:.2f}",
        f"Líquido informado  : R$ {relatorio.valor_liquido_informado:.2f}",
        f"Líquido esperado   : R$ {relatorio.valor_liquido_esperado:.2f}",
        f"Resultado          : {'APROVADO (sem divergências)' if relatorio.valido else 'DIVERGÊNCIAS ENCONTRADAS'}",
        "",
        f"{'Campo':<14} {'Informado':>10} {'Esperado':>10} {'Dif.':>9}  {'Status':<11} Mensagem",
        "-" * 92,
    ]
    for item in relatorio.itens:
        esp = f"{item.esperado:.2f}" if item.esperado is not None else "-"
        dif = f"{item.diferenca:+.2f}" if item.diferenca is not None else "-"
        linhas.append(
            f"{item.campo:<14} {item.informado:>10.2f} {esp:>10} {dif:>9}  {item.status.value:<11} {item.mensagem}"
        )
    return "\n".join(linhas)


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada da CLI ``python -m validador_nfse``."""
    parser = argparse.ArgumentParser(
        prog="validador_nfse",
        description="Conferência técnica de retenções tributárias em NFS-e (JSON).",
    )
    parser.add_argument("arquivo", type=Path, help="Caminho para o arquivo JSON da NFS-e.")
    parser.add_argument(
        "--tolerancia",
        default="0.01",
        help="Tolerância em R$ por tributo (padrão: 0.01).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="saida_json",
        help="Imprime o relatório estruturado em JSON.",
    )

    args = parser.parse_args(argv)

    try:
        conteudo = args.arquivo.read_text(encoding="utf-8")
        dados = json.loads(conteudo)
        relatorio = validar_nfse(dados, tolerancia=args.tolerancia)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    if args.saida_json:
        print(json.dumps(relatorio.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_formatar_relatorio_texto(relatorio))

    return 0 if relatorio.valido else 1
