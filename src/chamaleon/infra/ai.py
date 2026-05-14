from __future__ import annotations

import json
from typing import Any

import requests

from chamaleon.config import Settings
from chamaleon.domain.types import ReportPayload


class ReportAIClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def generate_report(self, payload: ReportPayload) -> str:
        if not self.settings.openai_api_key:
            return self._fallback_report(payload)

        prompt = self._build_prompt(payload)
        response = requests.post(
            f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.openai_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um analista financeiro pessoal. Responda em portugues do Brasil, "
                            "com objetividade, sem prometer resultados e sem sugerir investimentos especificos."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
            },
            timeout=30,
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def _build_prompt(self, payload: ReportPayload) -> str:
        top_categories = [
            {"category": category, "amount": f"{amount:.2f}"}
            for category, amount in payload.summary.top_categories
        ]
        compact = {
            "periodo": payload.period_label,
            "salario": f"{payload.summary.salary:.2f}",
            "entradas": f"{payload.summary.income_total:.2f}",
            "gastos": f"{payload.summary.expense_total:.2f}",
            "saldo": f"{payload.summary.balance:.2f}",
            "top_categorias": top_categories,
            "transacoes_recentes": payload.recent_transactions[:8],
        }
        return (
            "Monte um relatorio com 5 secoes curtas: resumo, diagnostico, principal ajuste, novo cenario, "
            "e proximo passo. Trate inferencias como hipoteses.\n\n"
            f"Contexto JSON:\n{json.dumps(compact, ensure_ascii=False)}"
        )

    def _fallback_report(self, payload: ReportPayload) -> str:
        lines = [
            f"Relatorio financeiro de {payload.period_label}",
            "",
            f"Salario base: R$ {payload.summary.salary:.2f}",
            f"Entradas extras: R$ {payload.summary.income_total:.2f}",
            f"Gastos: R$ {payload.summary.expense_total:.2f}",
            f"Saldo estimado: R$ {payload.summary.balance:.2f}",
        ]
        if payload.summary.top_categories:
            lines.append("")
            lines.append("Categorias com maior peso:")
            for category, amount in payload.summary.top_categories[:3]:
                lines.append(f"- {category}: R$ {amount:.2f}")
        lines.extend(
            [
                "",
                "Leitura rapida:",
                "- priorize reduzir gastos variaveis antes de cortar itens essenciais.",
                "- acompanhe os maiores gastos recorrentes para decidir seu proximo ajuste.",
            ]
        )
        return "\n".join(lines)
