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


class PlanoInvestigacao(BaseModel):
    """Define quais aprofundamentos são necessários para o cliente."""

    consultar_operacoes_dia: bool
    consultar_perfil_canal: bool
    justificativa_plano: str


FERRAMENTAS = [
    historico_cliente,
    operacoes_do_dia,
    perfil_canal,
]


def planejar_investigacao(
    cliente_id: str,
    historico: dict,
) -> tuple[PlanoInvestigacao, dict]:
    """Decide quais ferramentas adicionais são necessárias para o caso."""

    config_planejamento = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=PlanoInvestigacao,
        system_instruction="""
Você atua como planejador de uma investigação de triagem de PLD.

Você receberá o histórico determinístico de um cliente já sinalizado.

Sua tarefa é decidir quais fontes adicionais são realmente necessárias.

Ferramentas possíveis:

1. operacoes_do_dia
   Use quando existirem datas de fracionamento ou de operações atípicas
   que precisem ser examinadas individualmente.

2. perfil_canal
   Use somente quando a distribuição entre PIX, TED, boleto ou cartão
   puder acrescentar contexto relevante à investigação.

Regras:

- Não solicite ferramentas apenas para complementar o parecer.
- Não solicite perfil_canal quando o histórico e as operações sinalizadas
  forem suficientes.
- Não realize cálculos.
- Não altere as flags determinísticas.
- Prefira a menor quantidade de ferramentas necessária.
"""
    )

    prompt = f"""
Cliente: {cliente_id}

Histórico determinístico:
{historico}

Decida quais aprofundamentos são necessários.
"""

    response = client.models.generate_content(
        model=MODELO,
        contents=prompt,
        config=config_planejamento,
    )

    plano = PlanoInvestigacao.model_validate_json(
        response.text
    )

    uso = response.usage_metadata

    metricas_planejamento = {
        "tokens_entrada": (
            getattr(uso, "prompt_token_count", None)
            if uso
            else None
        ),
        "tokens_saida": (
            getattr(uso, "candidates_token_count", None)
            if uso
            else None
        ),
        "tokens_raciocinio": (
            getattr(uso, "thoughts_token_count", None)
            if uso
            else None
        ),
        "tokens_totais": (
            getattr(uso, "total_token_count", None)
            if uso
            else None
        ),
    }

    return plano, metricas_planejamento


def analisar_cliente(cliente_id: str) -> dict:
    """Planeja e executa a investigação agentic de um cliente."""

    inicio = time.perf_counter()

    try:
        # O histórico funciona como contexto determinístico inicial.
        historico = historico_cliente(cliente_id)

        if "erro" in historico:
            raise ValueError(historico["erro"])

        # A LLM decide quais aprofundamentos realmente são necessários.
        plano, metricas_planejamento = planejar_investigacao(
            cliente_id=cliente_id,
            historico=historico,
        )

        ferramentas_disponiveis = []

        if plano.consultar_operacoes_dia:
            ferramentas_disponiveis.append(
                operacoes_do_dia
            )

        if plano.consultar_perfil_canal:
            ferramentas_disponiveis.append(
                perfil_canal
            )

        # A configuração do agente é construída dinamicamente.
        config_agente = types.GenerateContentConfig(
            temperature=0.2,
            tools=(
                ferramentas_disponiveis
                if ferramentas_disponiveis
                else None
            ),
            response_mime_type="application/json",
            response_schema=ParecerAgente,
            automatic_function_calling=(
                types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=6,
                    ignore_call_history=False,
                )
                if ferramentas_disponiveis
                else None
            ),
            system_instruction="""
Você atua como agente de triagem de Prevenção à Lavagem de Dinheiro (PLD).

Seu objetivo é investigar clientes previamente sinalizados por regras
determinísticas e produzir um parecer para apoiar análise humana.

Regras obrigatórias:

- Utilize apenas informações fornecidas no caso ou obtidas pelas ferramentas.

- Não refaça cálculos determinísticos.

- Não altere nem questione as flags calculadas pelo pandas.

- Utilize somente as ferramentas disponibilizadas pelo plano de investigação.

- Cada ferramenta deve ser chamada apenas quando necessária.

- Nunca consulte a mesma ferramenta mais de uma vez com os mesmos argumentos.

- Para operacoes_do_dia, consulte cada data relevante exatamente uma vez.

- Se uma data já foi consultada, utilize o resultado existente e não faça
  uma nova chamada para a mesma data.

- Não repita chamadas de ferramentas para confirmar informações que já foram
  retornadas anteriormente.

- Se existirem várias datas relevantes, consulte cada data uma única vez.

- Diferencie fatos observados de hipóteses que exigem investigação.

- Não presuma intenção criminosa, origem dos recursos ou relação entre partes.

- Uma sinalização representa necessidade de análise humana, não prova de
  lavagem de dinheiro.

- Produza o parecer somente após concluir as consultas necessárias.
"""
        )

        prompt = f"""
Analise o cliente {cliente_id}.

O cliente já foi selecionado pelas regras determinísticas.

Histórico determinístico do cliente:
{historico}

Plano de investigação:
{plano.model_dump()}

As ferramentas disponibilizadas nesta execução foram selecionadas
dinamicamente de acordo com esse plano.

Caso operacoes_do_dia esteja disponível, consulte somente datas sinalizadas
presentes no histórico que sejam relevantes para o parecer.

Caso perfil_canal esteja disponível, utilize-o somente se a informação de
canais acrescentar contexto relevante.

Produza o parecer final conforme a estrutura solicitada.
"""

        chat = client.chats.create(
            model=MODELO,
            config=config_agente,
        )

        response = chat.send_message(prompt)

        parecer = ParecerAgente.model_validate_json(
            response.text
        )

        # historico_cliente é o contexto determinístico inicial.
        ferramentas_usadas = [
            "historico_cliente"
        ]

        # Registra somente function calls realmente executadas.
        for conteudo in chat.get_history():
            for parte in conteudo.parts or []:
                if parte.function_call:
                    ferramentas_usadas.append(
                        parte.function_call.name
                    )

        latencia = time.perf_counter() - inicio

        uso = response.usage_metadata

        metricas_agente = {
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

        # Soma segura: None é tratado como zero apenas para consolidação.
        tokens_planejamento = (
            metricas_planejamento["tokens_totais"] or 0
        )

        tokens_agente = (
            metricas_agente["tokens_totais"] or 0
        )

        tokens_totais = (
            tokens_planejamento
            + tokens_agente
        )

        metricas = {
            "latencia_segundos": round(
                latencia,
                2
            ),
            "tokens_planejamento": (
                metricas_planejamento["tokens_totais"]
            ),
            "tokens_agente": (
                metricas_agente["tokens_totais"]
            ),
            "tokens_totais": tokens_totais,
            "detalhes_planejamento": metricas_planejamento,
            "detalhes_agente": metricas_agente,
        }

        return {
            "cliente_id": cliente_id,
            "status": "sucesso",

            # Permite auditar a decisão tomada antes da investigação.
            "plano_investigacao": plano.model_dump(),

            "parecer": parecer.model_dump(),

            # Ferramentas que o planejador permitiu ao agente utilizar.
            "ferramentas_disponibilizadas": [
                ferramenta.__name__
                for ferramenta in ferramentas_disponiveis
            ],

            # Ferramentas efetivamente executadas.
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

def consolidar_metricas(
    resultados: list[dict]
) -> pd.DataFrame:
    """Consolida métricas das execuções bem-sucedidas."""

    registros = []

    for resultado in resultados:
        if resultado.get("status") != "sucesso":
            continue

        metricas = resultado["metricas"]

        registros.append({
            "cliente_id": resultado["cliente_id"],
            "nivel_risco": (
                resultado["parecer"]["nivel_risco"]
            ),
            "latencia_segundos": (
                metricas["latencia_segundos"]
            ),
            "tokens_planejamento": (
                metricas["tokens_planejamento"]
            ),
            "tokens_agente": (
                metricas["tokens_agente"]
            ),
            "tokens_totais": (
                metricas["tokens_totais"]
            ),
            "qtd_ferramentas_disponibilizadas": len(
                resultado[
                    "ferramentas_disponibilizadas"
                ]
            ),
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