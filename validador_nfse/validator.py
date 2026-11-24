"""Lógica de recomputação e validação de retenções tributárias em NFS-e.

Este módulo realiza conferência técnica aritmética de retenções com base em
parâmetros configuráveis. As regras tributárias brasileiras variam por código de
serviço, município, regime do prestador e natureza da operação; este pacote não
substitui análise fiscal ou parecer contábil.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from validador_nfse.models import (
    AliquotasConfig,
    ItemValidacao,
    RelatorioValidacao,
    StatusValidacao,
)

_CENTAVOS = Decimal("0.01")
_CEM = Decimal("100")


def arredondar_centavos(valor: Decimal) -> Decimal:
    """Arredonda um ``Decimal`` para duas casas decimais com ``ROUND_HALF_UP``."""
    return valor.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def _to_decimal(valor: Any, campo: str, *, allow_negative: bool = False) -> Decimal:
    if isinstance(valor, bool):
        raise ValueError(f"Campo '{campo}' não aceita booleano.")
    try:
        dec = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Valor inválido para '{campo}': {valor!r}.") from exc
    if not dec.is_finite():
        raise ValueError(f"Valor não finito para '{campo}': {valor!r}.")
    if not allow_negative and dec < Decimal("0"):
        raise ValueError(f"Campo '{campo}' não pode ser negativo: {dec}.")
    return dec


def _to_bool(valor: Any, campo: str, *, default: bool = False) -> bool:
    if valor is None:
        return default
    if isinstance(valor, bool):
        return valor
    raise ValueError(f"Campo '{campo}' deve ser booleano (true/false), recebido: {valor!r}.")


def _aplicar_overrides(dados: Mapping[str, Any], base: AliquotasConfig) -> AliquotasConfig:
    overrides: dict[str, Decimal] = {}
    mapa_topo = {
        "aliquota_irrf": "irrf",
        "aliquota_pis": "pis",
        "aliquota_cofins": "cofins",
        "aliquota_csll": "csll",
        "aliquota_inss": "inss",
    }
    for chave_json, attr in mapa_topo.items():
        if chave_json in dados and dados[chave_json] is not None:
            overrides[attr] = _to_decimal(dados[chave_json], chave_json)

    bloco_aliquotas = dados.get("aliquotas")
    if bloco_aliquotas is not None:
        if not isinstance(bloco_aliquotas, Mapping):
            raise ValueError("Campo 'aliquotas' deve ser um objeto/dicionário.")
        for nome in ("irrf", "pis", "cofins", "csll", "inss"):
            if nome in bloco_aliquotas and bloco_aliquotas[nome] is not None:
                overrides[nome] = _to_decimal(bloco_aliquotas[nome], f"aliquotas.{nome}")

    return replace(base, **overrides) if overrides else base


def _avaliar_tributo(
    campo: str,
    informado: Decimal,
    esperado: Decimal,
    tolerancia: Decimal,
    mensagem_ok: str,
    mensagem_divergente: str,
) -> ItemValidacao:
    diferenca = arredondar_centavos(informado - esperado)
    if abs(diferenca) <= tolerancia:
        return ItemValidacao(
            campo=campo,
            informado=informado,
            esperado=esperado,
            diferenca=diferenca,
            status=StatusValidacao.OK,
            mensagem=mensagem_ok,
        )
    return ItemValidacao(
        campo=campo,
        informado=informado,
        esperado=esperado,
        diferenca=diferenca,
        status=StatusValidacao.DIVERGENTE,
        mensagem=mensagem_divergente,
    )


def validar_nfse(
    dados: Mapping[str, Any],
    *,
    config: AliquotasConfig | None = None,
    tolerancia: Decimal | str | int | float | None = None,
) -> RelatorioValidacao:
    """Valida as retenções de uma NFS-e recomputando os valores esperados.

    Parâmetros esperados em ``dados``:
      - ``valor_servicos`` (obrigatório): valor bruto dos serviços em R$.
      - ``deducoes`` (opcional, padrão 0): deduções permitidas na base do ISS.
      - ``aliquota_iss`` (obrigatório): alíquota do ISS em % (ex.: ``5.00`` = 5%).
      - ``iss_retido`` (opcional, padrão ``False``): indica se o ISS é retido.
      - ``optante_simples`` (opcional, padrão ``False``): flag de Simples Nacional.
      - ``inss_aplicavel`` (opcional, padrão ``False``): cessão de mão de obra/empreitada.
      - ``valor_iss``, ``valor_irrf``, ``valor_pis``, ``valor_cofins``,
        ``valor_csll``, ``valor_inss`` (opcionais, padrão ``0.00``).
      - ``aliquotas`` (opcional): dict com sobrescritas de ``irrf``, ``pis``,
        ``cofins``, ``csll`` e/ou ``inss`` em %.
    """
    if not isinstance(dados, Mapping):
        raise ValueError("A entrada da NFS-e deve ser um objeto JSON/dicionário.")

    if "valor_servicos" not in dados or dados["valor_servicos"] is None:
        raise ValueError("Campo obrigatório ausente: 'valor_servicos'.")
    if "aliquota_iss" not in dados or dados["aliquota_iss"] is None:
        raise ValueError("Campo obrigatório ausente: 'aliquota_iss'.")

    cfg = _aplicar_overrides(dados, config or AliquotasConfig())
    tol = cfg.tolerancia if tolerancia is None else _to_decimal(tolerancia, "tolerancia")

    valor_servicos = arredondar_centavos(_to_decimal(dados["valor_servicos"], "valor_servicos"))
    deducoes = arredondar_centavos(_to_decimal(dados.get("deducoes") or "0.00", "deducoes"))
    if deducoes > valor_servicos:
        raise ValueError("Campo 'deducoes' não pode ser maior que 'valor_servicos'.")

    base_iss = arredondar_centavos(valor_servicos - deducoes)
    aliquota_iss = _to_decimal(dados["aliquota_iss"], "aliquota_iss")
    iss_retido = _to_bool(dados.get("iss_retido"), "iss_retido", default=False)
    optante_simples = _to_bool(dados.get("optante_simples"), "optante_simples", default=False)
    inss_aplicavel = _to_bool(dados.get("inss_aplicavel"), "inss_aplicavel", default=False)

    informados = {
        campo: arredondar_centavos(_to_decimal(dados.get(campo) if dados.get(campo) is not None else "0.00", campo))
        for campo in ("valor_iss", "valor_irrf", "valor_pis", "valor_cofins", "valor_csll", "valor_inss")
    }

    itens: list[ItemValidacao] = []

    # 1. Verificação da faixa de alíquota do ISS (LC 116/2003: 2% a 5%).
    if aliquota_iss < cfg.iss_aliquota_min or aliquota_iss > cfg.iss_aliquota_max:
        itens.append(
            ItemValidacao(
                campo="aliquota_iss",
                informado=arredondar_centavos(aliquota_iss),
                esperado=None,
                diferenca=None,
                status=StatusValidacao.ALERTA,
                mensagem=(
                    f"Alíquota de ISS ({aliquota_iss:.2f}%) fora da faixa geral de "
                    f"{cfg.iss_aliquota_min:.2f}% a {cfg.iss_aliquota_max:.2f}% (LC 116/2003); "
                    "confirmar legislação municipal e enquadramento do serviço."
                ),
            )
        )

    # 2. ISS retido.
    if iss_retido:
        iss_esperado = arredondar_centavos(base_iss * aliquota_iss / _CEM)
        itens.append(
            _avaliar_tributo(
                campo="valor_iss",
                informado=informados["valor_iss"],
                esperado=iss_esperado,
                tolerancia=tol,
                mensagem_ok=f"ISS retido conferido ({aliquota_iss:.2f}% sobre base R$ {base_iss:.2f}).",
                mensagem_divergente=(
                    f"ISS retido divergente: esperado R$ {iss_esperado:.2f} "
                    f"({aliquota_iss:.2f}% sobre R$ {base_iss:.2f})."
                ),
            )
        )
    else:
        iss_esperado = Decimal("0.00")
        if abs(informados["valor_iss"]) <= tol:
            itens.append(
                ItemValidacao(
                    campo="valor_iss",
                    informado=informados["valor_iss"],
                    esperado=iss_esperado,
                    diferenca=arredondar_centavos(informados["valor_iss"] - iss_esperado),
                    status=StatusValidacao.OK,
                    mensagem="ISS não retido na fonte (iss_retido=false).",
                )
            )
        else:
            itens.append(
                ItemValidacao(
                    campo="valor_iss",
                    informado=informados["valor_iss"],
                    esperado=iss_esperado,
                    diferenca=informados["valor_iss"],
                    status=StatusValidacao.ALERTA,
                    mensagem=(
                        "iss_retido=false, porém valor_iss foi informado; confirme se trata-se "
                        "de ISS próprio do prestador (não descontar do líquido) ou erro de marcação."
                    ),
                )
            )

    # 3. IRRF (RIR/2018 art. 714 + dispensa Lei 9.430/1996 art. 67 + Simples Nacional).
    if optante_simples:
        irrf_esperado = Decimal("0.00")
        if abs(informados["valor_irrf"]) <= tol:
            itens.append(
                ItemValidacao(
                    campo="valor_irrf",
                    informado=informados["valor_irrf"],
                    esperado=irrf_esperado,
                    diferenca=arredondar_centavos(informados["valor_irrf"]),
                    status=StatusValidacao.ALERTA,
                    mensagem=(
                        "Não aplicável para optante pelo Simples Nacional "
                        "(IN RFB 765/2007 / contexto IN RFB 1.234/2012); confirmar com a contabilidade."
                    ),
                )
            )
        else:
            itens.append(
                ItemValidacao(
                    campo="valor_irrf",
                    informado=informados["valor_irrf"],
                    esperado=irrf_esperado,
                    diferenca=informados["valor_irrf"],
                    status=StatusValidacao.DIVERGENTE,
                    mensagem=(
                        "IRRF informado, porém em regra não aplicável para optante pelo Simples Nacional; "
                        "esperado R$ 0.00."
                    ),
                )
            )
    else:
        irrf_bruto = arredondar_centavos(valor_servicos * cfg.irrf / _CEM)
        if irrf_bruto <= cfg.piso_dispensa_irrf:
            irrf_esperado = Decimal("0.00")
            itens.append(
                _avaliar_tributo(
                    campo="valor_irrf",
                    informado=informados["valor_irrf"],
                    esperado=irrf_esperado,
                    tolerancia=tol,
                    mensagem_ok=(
                        f"Retenção de IRRF dispensada: valor calculado R$ {irrf_bruto:.2f} "
                        f"<= R$ {cfg.piso_dispensa_irrf:.2f} (Lei 9.430/1996, art. 67)."
                    ),
                    mensagem_divergente=(
                        f"IRRF informado (R$ {informados['valor_irrf']:.2f}), porém retenção seria "
                        f"dispensada (R$ {irrf_bruto:.2f} <= R$ {cfg.piso_dispensa_irrf:.2f}; Lei 9.430/1996, art. 67)."
                    ),
                )
            )
        else:
            irrf_esperado = irrf_bruto
            itens.append(
                _avaliar_tributo(
                    campo="valor_irrf",
                    informado=informados["valor_irrf"],
                    esperado=irrf_esperado,
                    tolerancia=tol,
                    mensagem_ok=f"IRRF conferido ({cfg.irrf:.2f}% sobre R$ {valor_servicos:.2f}).",
                    mensagem_divergente=(
                        f"IRRF divergente: esperado R$ {irrf_esperado:.2f} "
                        f"({cfg.irrf:.2f}% sobre R$ {valor_servicos:.2f})."
                    ),
                )
            )

    # 4. CSRF: PIS (0,65%), COFINS (3,00%), CSLL (1,00%) - Lei 10.833/2003 arts. 30 e 31.
    csrf_specs = (
        ("valor_pis", "PIS", cfg.pis),
        ("valor_cofins", "COFINS", cfg.cofins),
        ("valor_csll", "CSLL", cfg.csll),
    )
    csrf_esperados: dict[str, Decimal] = {}

    if optante_simples:
        for campo, sigla, _ in csrf_specs:
            csrf_esperados[campo] = Decimal("0.00")
            if abs(informados[campo]) <= tol:
                itens.append(
                    ItemValidacao(
                        campo=campo,
                        informado=informados[campo],
                        esperado=Decimal("0.00"),
                        diferenca=arredondar_centavos(informados[campo]),
                        status=StatusValidacao.ALERTA,
                        mensagem=(
                            f"{sigla} não aplicável para optante pelo Simples Nacional "
                            "(IN RFB 459/2004 / contexto IN RFB 1.234/2012); confirmar com a contabilidade."
                        ),
                    )
                )
            else:
                itens.append(
                    ItemValidacao(
                        campo=campo,
                        informado=informados[campo],
                        esperado=Decimal("0.00"),
                        diferenca=informados[campo],
                        status=StatusValidacao.DIVERGENTE,
                        mensagem=(
                            f"{sigla} informado, porém CSRF em regra não aplicável para optante pelo "
                            "Simples Nacional; esperado R$ 0.00."
                        ),
                    )
                )
    else:
        csrf_brutos = {
            campo: arredondar_centavos(valor_servicos * aliq / _CEM)
            for campo, _, aliq in csrf_specs
        }
        csrf_total_bruto = sum(csrf_brutos.values(), Decimal("0.00"))
        dispensado = csrf_total_bruto <= cfg.piso_dispensa_csrf

        for campo, sigla, aliq in csrf_specs:
            esperado = Decimal("0.00") if dispensado else csrf_brutos[campo]
            csrf_esperados[campo] = esperado
            if dispensado:
                itens.append(
                    _avaliar_tributo(
                        campo=campo,
                        informado=informados[campo],
                        esperado=esperado,
                        tolerancia=tol,
                        mensagem_ok=(
                            f"Retenção de {sigla}/CSRF dispensada: total CSRF R$ {csrf_total_bruto:.2f} "
                            f"<= R$ {cfg.piso_dispensa_csrf:.2f} (Lei 10.833/2003, art. 31, § 3º / Lei 13.137/2015)."
                        ),
                        mensagem_divergente=(
                            f"{sigla} informado (R$ {informados[campo]:.2f}), porém soma CSRF "
                            f"(R$ {csrf_total_bruto:.2f}) <= R$ {cfg.piso_dispensa_csrf:.2f} é dispensada."
                        ),
                    )
                )
            else:
                itens.append(
                    _avaliar_tributo(
                        campo=campo,
                        informado=informados[campo],
                        esperado=esperado,
                        tolerancia=tol,
                        mensagem_ok=f"{sigla} conferido ({aliq:.2f}% sobre R$ {valor_servicos:.2f}).",
                        mensagem_divergente=(
                            f"{sigla} divergente: esperado R$ {esperado:.2f} "
                            f"({aliq:.2f}% sobre R$ {valor_servicos:.2f})."
                        ),
                    )
                )

    # 5. INSS (Lei 8.212/1991, art. 31 - cessão de mão de obra ou empreitada).
    if inss_aplicavel:
        inss_esperado = arredondar_centavos(valor_servicos * cfg.inss / _CEM)
        itens.append(
            _avaliar_tributo(
                campo="valor_inss",
                informado=informados["valor_inss"],
                esperado=inss_esperado,
                tolerancia=tol,
                mensagem_ok=f"INSS retido conferido ({cfg.inss:.2f}% sobre R$ {valor_servicos:.2f}).",
                mensagem_divergente=(
                    f"INSS divergente: esperado R$ {inss_esperado:.2f} "
                    f"({cfg.inss:.2f}% sobre R$ {valor_servicos:.2f})."
                ),
            )
        )
    else:
        inss_esperado = Decimal("0.00")
        if abs(informados["valor_inss"]) <= tol:
            itens.append(
                ItemValidacao(
                    campo="valor_inss",
                    informado=informados["valor_inss"],
                    esperado=inss_esperado,
                    diferenca=arredondar_centavos(informados["valor_inss"]),
                    status=StatusValidacao.OK,
                    mensagem="INSS não marcado como aplicável (inss_aplicavel=false).",
                )
            )
        else:
            itens.append(
                ItemValidacao(
                    campo="valor_inss",
                    informado=informados["valor_inss"],
                    esperado=inss_esperado,
                    diferenca=informados["valor_inss"],
                    status=StatusValidacao.ALERTA,
                    mensagem=(
                        "valor_inss informado com inss_aplicavel=false; confirme se há cessão de "
                        "mão de obra ou empreitada (Lei 8.212/1991, art. 31)."
                    ),
                )
            )

    total_retido_informado = (
        (informados["valor_iss"] if iss_retido else Decimal("0.00"))
        + informados["valor_irrf"]
        + informados["valor_pis"]
        + informados["valor_cofins"]
        + informados["valor_csll"]
        + informados["valor_inss"]
    )
    total_retido_esperado = (
        iss_esperado
        + irrf_esperado
        + csrf_esperados["valor_pis"]
        + csrf_esperados["valor_cofins"]
        + csrf_esperados["valor_csll"]
        + inss_esperado
    )

    valido = not any(item.status == StatusValidacao.DIVERGENTE for item in itens)
    possui_alertas = any(item.status == StatusValidacao.ALERTA for item in itens)

    return RelatorioValidacao(
        valido=valido,
        possui_alertas=possui_alertas,
        valor_servicos=valor_servicos,
        deducoes=deducoes,
        base_iss=base_iss,
        total_retido_informado=arredondar_centavos(total_retido_informado),
        total_retido_esperado=arredondar_centavos(total_retido_esperado),
        valor_liquido_informado=arredondar_centavos(valor_servicos - total_retido_informado),
        valor_liquido_esperado=arredondar_centavos(valor_servicos - total_retido_esperado),
        itens=itens,
    )
