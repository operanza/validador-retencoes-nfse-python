"""Modelos de dados e configuração para validação de retenções de NFS-e."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


class StatusValidacao(str, Enum):
    """Status individual de conferência de um campo ou alíquota."""

    OK = "OK"
    DIVERGENTE = "DIVERGENTE"
    ALERTA = "ALERTA"


@dataclass(frozen=True)
class AliquotasConfig:
    """Parâmetros padrão de alíquotas (em %) e limites de dispensa (em R$).

    As alíquotas devem ser informadas em pontos percentuais (ex.: ``1.50`` para
    1,50% e ``5.00`` para 5,00%). As regras variam conforme código do serviço,
    município e regime tributário; ajuste os valores para o seu caso concreto.
    """

    # RIR/2018 (Decreto nº 9.580/2018), art. 714 (serviços profissionais;
    # outros serviços como limpeza e vigilância possuem alíquota distinta, ex.: 1%).
    irrf: Decimal = Decimal("1.50")
    # Lei nº 10.833/2003, art. 30 e 31 (CSRF total de 4,65%).
    pis: Decimal = Decimal("0.65")
    cofins: Decimal = Decimal("3.00")
    csll: Decimal = Decimal("1.00")
    # Lei nº 8.212/1991, art. 31 (cessão de mão de obra ou empreitada).
    inss: Decimal = Decimal("11.00")
    # Lei nº 9.430/1996, art. 67.
    piso_dispensa_irrf: Decimal = Decimal("10.00")
    # Lei nº 10.833/2003, art. 31, § 3º (redação dada pela Lei nº 13.137/2015).
    piso_dispensa_csrf: Decimal = Decimal("10.00")
    # Lei Complementar nº 116/2003 (faixa geral municipal de 2% a 5%).
    iss_aliquota_min: Decimal = Decimal("2.00")
    iss_aliquota_max: Decimal = Decimal("5.00")
    # Tolerância padrão para diferenças de arredondamento por tributo.
    tolerancia: Decimal = Decimal("0.01")


@dataclass(frozen=True)
class ItemValidacao:
    """Resultado da conferência de um campo específico da NFS-e."""

    campo: str
    informado: Decimal
    esperado: Decimal | None
    diferenca: Decimal | None
    status: StatusValidacao
    mensagem: str

    def to_dict(self) -> dict[str, Any]:
        """Serializa o item com valores decimais formatados como string."""
        return {
            "campo": self.campo,
            "informado": f"{self.informado:.2f}",
            "esperado": f"{self.esperado:.2f}" if self.esperado is not None else None,
            "diferenca": f"{self.diferenca:.2f}" if self.diferenca is not None else None,
            "status": self.status.value,
            "mensagem": self.mensagem,
        }


@dataclass(frozen=True)
class RelatorioValidacao:
    """Relatório consolidado da conferência técnica da NFS-e."""

    valido: bool
    possui_alertas: bool
    valor_servicos: Decimal
    deducoes: Decimal
    base_iss: Decimal
    total_retido_informado: Decimal
    total_retido_esperado: Decimal
    valor_liquido_informado: Decimal
    valor_liquido_esperado: Decimal
    itens: list[ItemValidacao]

    def to_dict(self) -> dict[str, Any]:
        """Serializa o relatório completo para dicionário compatível com JSON."""
        raw = asdict(self)
        raw["valor_servicos"] = f"{self.valor_servicos:.2f}"
        raw["deducoes"] = f"{self.deducoes:.2f}"
        raw["base_iss"] = f"{self.base_iss:.2f}"
        raw["total_retido_informado"] = f"{self.total_retido_informado:.2f}"
        raw["total_retido_esperado"] = f"{self.total_retido_esperado:.2f}"
        raw["valor_liquido_informado"] = f"{self.valor_liquido_informado:.2f}"
        raw["valor_liquido_esperado"] = f"{self.valor_liquido_esperado:.2f}"
        raw["itens"] = [item.to_dict() for item in self.itens]
        return raw
