# validador-retencoes-nfse-python

Pacote Python (somente biblioteca padrão, Python 3.10+) e CLI para conferência técnica aritmética de retenções tributárias em Notas Fiscais de Serviços Eletrônicas (NFS-e): ISS, IRRF, PIS, COFINS, CSLL e INSS.

## O que faz

Dado um dicionário Python ou arquivo JSON com os dados da NFS-e (`valor_servicos`, `deducoes`, `aliquota_iss`, `iss_retido`, flags de enquadramento e valores retidos informados), o validador recalcula os valores esperados usando `decimal.Decimal` (`ROUND_HALF_UP` para centavos) e gera um relatório estruturado por campo com:

- `informado`, `esperado` e `diferenca`
- `status`: `OK`, `DIVERGENTE` ou `ALERTA`
- `mensagem` explicativa
- tolerância configurável por tributo (padrão: `R$ 0,01`)

## Início rápido

### Executando direto do repositório (CLI)

Requer Python 3.10 ou superior, sem dependências externas em tempo de execução:

```bash
python -m validador_nfse examples/nota_exemplo.json
```

Para saída estruturada em JSON ou ajuste de tolerância:

```bash
python -m validador_nfse examples/nota_exemplo.json --json --tolerancia 0.01
```

### Instalação local e testes

```bash
pip install -e ".[dev]"
pytest -v
```

### Uso como biblioteca Python

```python
from validador_nfse import validar_nfse

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
print(relatorio.valido)  # True
```

As alíquotas também podem ser sobrescritas por nota via chave `"aliquotas": {"irrf": "1.00"}` ou via `AliquotasConfig(...)`. Todas as alíquotas são expressas em pontos percentuais (ex.: `5.00` equivale a 5%).

## Regras e alíquotas padrão

| Tributo | Alíquota padrão | Base padrão | Referência e observações |
| --- | --- | --- | --- |
| **ISS** | Informada na nota (`2%` a `5%`) | `valor_servicos - deducoes` | LC 116/2003. Emite `ALERTA` se a alíquota estiver fora de 2%–5%. Só compõe o retido esperado quando `iss_retido=true`. |
| **IRRF** | `1,50%` (configurável) | `valor_servicos` | RIR/2018 (Decreto nº 9.580/2018), art. 714 (padrão genérico para serviços profissionais; serviços como limpeza e vigilância podem usar 1%). Dispensado quando `<= R$ 10,00` (Lei nº 9.430/1996, art. 67). |
| **CSRF (PIS / COFINS / CSLL)** | `0,65%` / `3,00%` / `1,00%` (`4,65%`) | `valor_servicos` | Lei nº 10.833/2003, art. 30 e 31. Retenção dispensada quando a soma de PIS + COFINS + CSLL for `<= R$ 10,00` (Lei nº 10.833/2003, art. 31, § 3º, redação da Lei nº 13.137/2015). |
| **INSS** | `11,00%` (quando `inss_aplicavel=true`) | `valor_servicos` | Lei nº 8.212/1991, art. 31 (aplicável em serviços mediante cessão de mão de obra ou empreitada). |
| **Simples Nacional** | Não aplicável (IRRF e CSRF) | — | Quando `optante_simples=true`, IRRF e CSRF assumem esperado `R$ 0,00` com `ALERTA` explicativo (contexto IN RFB nº 459/2004, IN RFB nº 765/2007 e IN RFB nº 1.234/2012). |

## Limitações e aviso legal

- **Conferência técnica, não consultoria tributária:** esta ferramenta realiza apenas verificação aritmética com base nos parâmetros informados e alíquotas padrão genéricas. Não constitui parecer fiscal, contábil ou jurídico.
- **Variação de regras na prática:** a incidência, a alíquota e a obrigatoriedade de retenção dependem do código do serviço (LC 116/2003), CNAE, legislação do município do prestador e do tomador, cadastro municipal (como CPOM/RANFS onde exigido), regime de tributação (Lucro Real, Presumido, Simples Nacional, MEI), desoneração de folha (INSS 3,5% vs 11%), retenções por órgãos públicos (IN RFB nº 1.234/2012) e deduções legais específicas (materiais/subempreitada).
- **Confirme sempre com a contabilidade:** valide divergências e alertas com a equipe fiscal ou contábil antes de aprovar pagamentos ou escriturar documentos.

## Sobre a Operanza

Este projeto é mantido pela [Operanza](https://www.operanza.com.br), empresa brasileira de automação financeira e operacional com IA.

Conteúdos relacionados:

- [OCR de Nota Fiscal (NFS-e) com IA](https://www.operanza.com.br/conteudos/ocr-nota-fiscal-nfse-com-ia)
- [Contas a Pagar Automático com IA](https://www.operanza.com.br/conteudos/contas-a-pagar-automatico-com-ia)
- [Automação Financeira e OCR de Notas Fiscais](https://www.operanza.com.br/automacao-financeira-ocr-notas-fiscais)

Contato: contato@operanza.com.br
