import os
import time
import json
import pandas as pd

from pathlib import Path
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

- Comece preferencialmente por historico_cliente para compreender quais
  sinalizações determinísticas existem.

- Utilize operacoes_do_dia somente quando houver uma data sinalizada que
  precise ser aprofundada.

- Utilize perfil_canal somente quando a distribuição por canais for relevante
  para esclarecer ou contextualizar a sinalização identificada.

- Não utilize perfil_canal apenas para complementar o parecer quando o
  histórico e as operações sinalizadas já forem suficientes.

- Não chame todas as ferramentas automaticamente. A ausência de chamada de
  uma ferramenta é esperada quando ela não acrescenta informação relevante
  ao caso.

- Diferencie fatos observados de hipóteses que exigem investigação adicional.

- Não presuma intenção criminosa, origem dos recursos ou relação entre partes.

- Uma sinalização representa necessidade de análise humana, não prova de
  lavagem de dinheiro.

- Caso uma ferramenta revele uma data relevante, você pode utilizar
  operacoes_do_dia para investigar aquele evento específico.

- Ao descrever operações sinalizadas, utilize as flags retornadas pelas ferramentas
  e não refaça comparações entre valores e limites ou estatísticas.

- Não mencione origem, destino ou compatibilidade com o perfil econômico do
  cliente como fatos quando essas informações não estiverem disponíveis.
  Esses elementos podem ser indicados apenas como informações adicionais
  que uma análise humana poderia solicitar.
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


def executar_lote(
    clientes: list[str],
    max_tentativas: int = 3,
    pausa_entre_clientes: float = 3.0,
) -> list[dict]:
    """Executa o agente em lote com retry e salvamento incremental."""

    resultados = []

    caminho_saida = (
        Path(__file__).resolve().parent.parent
        / "outputs"
        / "pareceres_agente.json"
    )

    for indice, cliente_id in enumerate(clientes, start=1):
        print(
            f"\n[{indice}/{len(clientes)}] "
            f"Analisando {cliente_id}..."
        )

        resultado = None

        for tentativa in range(1, max_tentativas + 1):
            resultado = analisar_cliente(cliente_id)

            if resultado["status"] == "sucesso":
                print(
                    f"Sucesso em {resultado['metricas']['latencia_segundos']}s"
                )
                break

            print(
                f"Tentativa {tentativa}/{max_tentativas} falhou: "
                f"{resultado.get('status')}"
            )

            if tentativa < max_tentativas:
                espera = tentativa * 10

                print(
                    f"Aguardando {espera}s antes de tentar novamente..."
                )

                time.sleep(espera)

        resultados.append(resultado)

        # Salva após cada cliente para não perder execuções já concluídas.
        with caminho_saida.open(
            "w",
            encoding="utf-8"
        ) as arquivo:
            json.dump(
                resultados,
                arquivo,
                ensure_ascii=False,
                indent=2
            )

        if indice < len(clientes):
            time.sleep(pausa_entre_clientes)

    return resultados

def consolidar_metricas(resultados: list[dict]) -> pd.DataFrame:
    """Consolida métricas das execuções bem-sucedidas em um DataFrame."""

    registros = []

    for resultado in resultados:
        if resultado.get("status") != "sucesso":
            continue

        metricas = resultado["metricas"]

        registros.append({
            "cliente_id": resultado["cliente_id"],
            "nivel_risco": resultado["parecer"]["nivel_risco"],
            "latencia_segundos": metricas["latencia_segundos"],
            "tokens_entrada": metricas["tokens_entrada"],
            "tokens_saida": metricas["tokens_saida"],
            "tokens_raciocinio": metricas["tokens_raciocinio"],
            "tokens_totais": metricas["tokens_totais"],
            "qtd_chamadas_ferramentas": len(
                resultado["ferramentas_usadas"]
            ),
        })

    return pd.DataFrame(registros)

if __name__ == "__main__":
    caminho_ranking = (
        Path(__file__).resolve().parent.parent
        / "outputs"
        / "ranking_top10.csv"
    )

    ranking = pd.read_csv(caminho_ranking)

    clientes_top10 = (
        ranking["cliente_id"]
        .head(10)
        .tolist()
    )

    print("Clientes selecionados para o lote:")
    print(clientes_top10)

    resultados = executar_lote(clientes_top10)

    metricas_df = consolidar_metricas(resultados)

    caminho_metricas = (
        Path(__file__).resolve().parent.parent
        / "outputs"
        / "metricas_agente.csv"
    )

    metricas_df.to_csv(
        caminho_metricas,
        index=False
    )

    print("\n--- Métricas do lote ---")
    print(metricas_df.to_string(index=False))

    if not metricas_df.empty:
        print("\nResumo:")
        print(
            f"Latência média: "
            f"{metricas_df['latencia_segundos'].mean():.2f}s"
        )

        print(
            f"Tokens totais consumidos: "
            f"{metricas_df['tokens_totais'].sum():.0f}"
        )

        print(
            f"Chamadas de ferramentas: "
            f"{metricas_df['qtd_chamadas_ferramentas'].sum()}"
        )