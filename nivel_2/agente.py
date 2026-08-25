import os
import time

from typing import Literal
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import (
    historico_cliente,
    operacoes_do_dia,
    perfil_canal,
)


# Carrega a chave da API armazenada no arquivo .env.
load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    raise ValueError(
        "GOOGLE_API_KEY não encontrada. "
        "Configure a variável no arquivo .env."
    )

client = genai.Client(api_key=API_KEY)

MODELO = "gemini-3.5-flash-lite"

class ParecerAgente(BaseModel):
    nivel_risco: Literal["baixo", "médio", "alto"]
    tipologia_suspeita: str
    red_flags: list[str]
    justificativa: str


FERRAMENTAS = [
    historico_cliente,
    operacoes_do_dia,
    perfil_canal,
]

CONFIG_AGENTE = types.GenerateContentConfig(
    temperature=0.2,
    tools=FERRAMENTAS,
    response_mime_type="application/json",
    response_schema=ParecerAgente,

    automatic_function_calling=types.AutomaticFunctionCallingConfig(
        maximum_remote_calls=6,
        ignore_call_history=False,
    ),

    system_instruction="""
Você atua como agente de triagem de Prevenção à Lavagem de Dinheiro (PLD).

Seu objetivo é investigar clientes previamente sinalizados por regras
determinísticas e produzir um parecer para apoiar análise humana.

Regras obrigatórias:

- Utilize apenas informações fornecidas no caso ou obtidas pelas ferramentas.

- Não refaça cálculos determinísticos.

- Nunca realize somas, médias, medianas, percentuais, proporções ou
  comparações numéricas por conta própria.

- Utilize somente métricas numéricas explicitamente retornadas pelas
  ferramentas.

- Se uma métrica não estiver disponível nas ferramentas, não tente calculá-la.

- Não altere nem questione as flags calculadas pelo pandas.

- Escolha somente as ferramentas necessárias para investigar cada caso.

- Não chame todas as ferramentas automaticamente.

- Diferencie fatos observados de hipóteses que exigem investigação adicional.

- Não presuma intenção criminosa, origem dos recursos ou relação entre partes.

- Uma sinalização representa necessidade de análise humana, não prova de
  lavagem de dinheiro.

- Caso uma ferramenta revele uma data relevante, você pode utilizar
  operacoes_do_dia para investigar aquele evento específico.

- Ao descrever operações sinalizadas, utilize as flags retornadas pelas ferramentas
  e não refaça comparações entre valores e limites ou estatísticas.
"""
)


def analisar_cliente(cliente_id: str) -> dict:
    """Executa o agente de PLD para um cliente e registra sua execução."""

    prompt = f"""
Analise o cliente {cliente_id}.

O cliente já foi selecionado pelas regras determinísticas do processo.

Investigue o caso utilizando somente as ferramentas que considerar
necessárias.

Produza o parecer final conforme a estrutura solicitada.

Baseie a análise exclusivamente nos dados disponíveis e nas métricas
retornadas pelas ferramentas.
"""

    chat = client.chats.create(
        model=MODELO,
        config=CONFIG_AGENTE,
    )

    inicio = time.perf_counter()

    try:
        response = chat.send_message(prompt)

        latencia = time.perf_counter() - inicio

        # Valida a resposta final conforme o schema definido.
        parecer = ParecerAgente.model_validate_json(
            response.text
        )

        # Recupera as ferramentas realmente escolhidas pelo agente.
        ferramentas_usadas = []

        for conteudo in chat.get_history():
            for parte in conteudo.parts or []:
                if parte.function_call:
                    ferramentas_usadas.append(
                        parte.function_call.name
                    )

        # Recupera métricas da chamada.
        uso = response.usage_metadata

        metricas = {
            "latencia_segundos": round(
                latencia,
                2
            ),

            "tokens_entrada": (
                getattr(
                    uso,
                    "prompt_token_count",
                    None
                )
                if uso
                else None
            ),

            "tokens_saida": (
                getattr(
                    uso,
                    "candidates_token_count",
                    None
                )
                if uso
                else None
            ),

            "tokens_ferramentas": (
                getattr(
                    uso,
                    "tool_use_prompt_token_count",
                    None
                )
                if uso
                else None
            ),

            "tokens_raciocinio": (
                getattr(
                    uso,
                    "thoughts_token_count",
                    None
                )
                if uso
                else None
            ),

            "tokens_totais": (
                getattr(
                    uso,
                    "total_token_count",
                    None
                )
                if uso
                else None
            ),
        }

        return {
            "cliente_id": cliente_id,
            "status": "sucesso",
            "parecer": parecer.model_dump(),
            "ferramentas_usadas": ferramentas_usadas,
            "metricas": metricas,
        }

    except (ValidationError, ValueError) as erro:
        latencia = time.perf_counter() - inicio

        return {
            "cliente_id": cliente_id,
            "status": "erro_validacao",
            "erro": str(erro),
            "latencia_segundos": round(
                latencia,
                2
            ),
        }

    except Exception as erro:
        latencia = time.perf_counter() - inicio

        return {
            "cliente_id": cliente_id,
            "status": "erro_api",
            "erro": str(erro),
            "latencia_segundos": round(
                latencia,
                2
            ),
        }

if __name__ == "__main__":
    resultado = analisar_cliente("CLI-029")

    print("\n--- Resultado do agente ---")
    print(resultado)