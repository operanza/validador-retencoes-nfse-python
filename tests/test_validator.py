"""Testes unitários e de CLI para o validador de retenções de NFS-e."""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from validador_nfse import StatusValidacao, arredondar_centavos, validar_nfse
from validador_nfse.cli import main as cli_main

REPO_ROOT = Path(__file__).resolve().parent.parent


def _itens_por_campo(relatorio):
    return {item.campo: item for item in relatorio.itens}


def test_nota_correta_passa_sem_alertas() -> None:
    nota = {
        "valor_servicos": "2500.00",
        "deducoes": "0.00",
        "aliquota_iss": "5.00",
        "iss_retido": True,
        "optante_simples": False,
        "inss_aplicavel": False,
        "valor_iss": "125.00",
        "valor_irrf": "37.50",
        "valor_pis": "16.25",
        "valor_cofins": "75.00",
        "valor_csll": "25.00",
        "valor_inss": "0.00",
    }

    relatorio = validar_nfse(nota)

    assert relatorio.valido is True
    assert relatorio.possui_alertas is False
    assert relatorio.total_retido_esperado == Decimal("278.75")
    assert relatorio.valor_liquido_esperado == Decimal("2221.25")
    assert all(item.status == StatusValidacao.OK for item in relatorio.itens)


def test_divergencia_irrf() -> None:
    nota = {
        "valor_servicos": "2000.00",
        "aliquota_iss": "5.00",
        "iss_retido": True,
        "valor_iss": "100.00",
        "valor_irrf": "20.00",  # esperado: 30.00 (1,5%)
        "valor_pis": "13.00",
        "valor_cofins": "60.00",
        "valor_csll": "20.00",
    }

    relatorio = validar_nfse(nota)
    itens = _itens_por_campo(relatorio)

    assert relatorio.valido is False
    assert itens["valor_irrf"].status == StatusValidacao.DIVERGENTE
    assert itens["valor_irrf"].esperado == Decimal("30.00")
    assert itens["valor_irrf"].diferenca == Decimal("-10.00")


def test_csrf_dispensada_quando_total_ate_10_reais() -> None:
    # 200.00 * 4,65% = 9.30 <= 10.00 (Lei 10.833/2003, art. 31, § 3º / Lei 13.137/2015)
    # 200.00 * 1,50% = 3.00 <= 10.00 (Lei 9.430/1996, art. 67)
    nota_dispensada = {
        "valor_servicos": "200.00",
        "aliquota_iss": "2.00",
        "iss_retido": True,
        "valor_iss": "4.00",
        "valor_irrf": "0.00",
        "valor_pis": "0.00",
        "valor_cofins": "0.00",
        "valor_csll": "0.00",
    }

    relatorio = validar_nfse(nota_dispensada)
    itens = _itens_por_campo(relatorio)

    assert relatorio.valido is True
    assert itens["valor_pis"].esperado == Decimal("0.00")
    assert itens["valor_cofins"].esperado == Decimal("0.00")
    assert itens["valor_csll"].esperado == Decimal("0.00")
    assert itens["valor_irrf"].esperado == Decimal("0.00")

    # Caso o prestador tenha retido indevidamente abaixo do piso de dispensa
    nota_retida_indevida = {
        **nota_dispensada,
        "valor_pis": "1.30",
        "valor_cofins": "6.00",
        "valor_csll": "2.00",
    }
    relatorio_indevido = validar_nfse(nota_retida_indevida)
    assert relatorio_indevido.valido is False
    assert _itens_por_campo(relatorio_indevido)["valor_cofins"].status == StatusValidacao.DIVERGENTE


def test_flag_optante_simples_nacional() -> None:
    nota_simples = {
        "valor_servicos": "3000.00",
        "aliquota_iss": "2.50",
        "iss_retido": True,
        "optante_simples": True,
        "valor_iss": "75.00",
        "valor_irrf": "0.00",
        "valor_pis": "0.00",
        "valor_cofins": "0.00",
        "valor_csll": "0.00",
    }

    relatorio = validar_nfse(nota_simples)
    itens = _itens_por_campo(relatorio)

    assert relatorio.valido is True
    assert relatorio.possui_alertas is True
    for campo in ("valor_irrf", "valor_pis", "valor_cofins", "valor_csll"):
        assert itens[campo].status == StatusValidacao.ALERTA
        assert itens[campo].esperado == Decimal("0.00")
        assert "não aplicável" in itens[campo].mensagem.lower()


@pytest.mark.parametrize("aliquota_fora", ["1.50", "6.00"])
def test_alerta_aliquota_iss_fora_da_faixa_lc116(aliquota_fora: str) -> None:
    nota = {
        "valor_servicos": "1000.00",
        "aliquota_iss": aliquota_fora,
        "iss_retido": False,
        "valor_irrf": "15.00",
        "valor_pis": "6.50",
        "valor_cofins": "30.00",
        "valor_csll": "10.00",
    }

    relatorio = validar_nfse(nota)
    itens = _itens_por_campo(relatorio)

    assert relatorio.valido is True
    assert relatorio.possui_alertas is True
    assert "aliquota_iss" in itens
    assert itens["aliquota_iss"].status == StatusValidacao.ALERTA


def test_arredondamento_decimal_round_half_up() -> None:
    # 0.005 deve arredondar para 0.01 (ROUND_HALF_UP), não 0.00 (ROUND_HALF_EVEN)
    assert arredondar_centavos(Decimal("0.005")) == Decimal("0.01")
    assert arredondar_centavos(Decimal("1.005")) == Decimal("1.01")

    # 100.33 * 5% = 5.0165 -> 5.02; deduções reduzem a base do ISS
    # 1000.33 - 100.00 = 900.33 * 5% = 45.0165 -> 45.02
    # IRRF: 1000.33 * 1.5% = 15.00495 -> 15.00
    # PIS: 1000.33 * 0.65% = 6.502145 -> 6.50
    # COFINS: 1000.33 * 3.00% = 30.0099 -> 30.01
    # CSLL: 1000.33 * 1.00% = 10.0033 -> 10.00
    nota = {
        "valor_servicos": "1000.33",
        "deducoes": "100.00",
        "aliquota_iss": "5.00",
        "iss_retido": True,
        "valor_iss": "45.02",
        "valor_irrf": "15.00",
        "valor_pis": "6.50",
        "valor_cofins": "30.01",
        "valor_csll": "10.00",
    }

    relatorio = validar_nfse(nota)
    assert relatorio.valido is True
    assert relatorio.base_iss == Decimal("900.33")


def test_sobrescrita_aliquota_inss_e_tolerancia() -> None:
    nota = {
        "valor_servicos": "1000.00",
        "aliquota_iss": "5.00",
        "iss_retido": True,
        "inss_aplicavel": True,
        "aliquotas": {"irrf": "1.00"},
        "valor_iss": "50.00",
        "valor_irrf": "0.00",  # 1% de 1000 = 10.00 <= 10.00 -> dispensado
        "valor_pis": "6.50",
        "valor_cofins": "30.00",
        "valor_csll": "10.00",
        "valor_inss": "110.01",  # 1 centavo de diferença -> passa com tolerância 0.01
    }

    relatorio = validar_nfse(nota)
    assert relatorio.valido is True
    assert _itens_por_campo(relatorio)["valor_inss"].status == StatusValidacao.OK


def test_cli_executa_exemplo_e_saida_json(capsys) -> None:
    exemplo = REPO_ROOT / "examples" / "nota_exemplo.json"
    codigo = cli_main([str(exemplo), "--json"])
    saida = capsys.readouterr().out
    payload = json.loads(saida)

    assert codigo == 0
    assert payload["valido"] is True
    assert payload["total_retido_esperado"] == "278.75"


def test_cli_modulo_subprocess() -> None:
    exemplo = REPO_ROOT / "examples" / "nota_exemplo.json"
    proc = subprocess.run(
        [sys.executable, "-m", "validador_nfse", str(exemplo)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "APROVADO" in proc.stdout
