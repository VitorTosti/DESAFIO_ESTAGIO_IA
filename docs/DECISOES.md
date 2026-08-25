## Nível 2 — Critério de contagem das sinalizações

Para construir o ranking dos clientes mais sinalizados, foi necessário definir
como contabilizar ocorrências da regra de fracionamento.

A flag de fracionamento é associada às operações de um mesmo cliente e data.
Contar cada linha sinalizada como uma ocorrência independente faria um único
evento de fracionamento ser contabilizado várias vezes.

Por isso, adotei os seguintes critérios:

- **Fracionamento:** cada combinação única de `cliente_id` e `data` que atende
  à regra representa uma sinalização.
- **Valor atípico:** cada operação que atende à regra representa uma
  sinalização independente.
- **Desempate:** conforme definido no enunciado, clientes com o mesmo número
  de sinalizações são ordenados pelo maior volume total transacionado em BRL.

Essa escolha busca representar eventos de alerta, evitando que a quantidade de
operações envolvidas em um único episódio de fracionamento infle
artificialmente a posição do cliente no ranking.


## Nível 2 — Arquitetura do agente

### Planejamento dinâmico da investigação

A investigação foi estruturada em duas etapas.

Primeiro, `historico_cliente` fornece o contexto determinístico inicial do
cliente sinalizado. A partir desse histórico, uma etapa de planejamento com
LLM decide quais aprofundamentos são necessários.

As ferramentas adicionais são:

- `operacoes_do_dia`: aprofunda datas sinalizadas quando necessário;
- `perfil_canal`: analisa a distribuição dos canais somente quando essa
  informação acrescenta contexto relevante.

Com base no plano, somente as ferramentas consideradas necessárias são
disponibilizadas para a investigação.

Essa abordagem evita um fluxo rígido que execute todas as ferramentas para
todos os clientes e torna a decisão auditável pelos campos
`plano_investigacao`, `ferramentas_disponibilizadas` e `ferramentas_usadas`.


### Separação entre processamento determinístico e LLM

Os cálculos financeiros e as regras de sinalização permanecem sob
responsabilidade do pandas.

O agente recebe métricas e flags previamente calculadas e é instruído a não
refazer somas, médias, medianas, percentuais, limites ou comparações
determinísticas.

A LLM é utilizada para planejar a investigação, selecionar os aprofundamentos
necessários, interpretar os dados disponibilizados e produzir o parecer de
triagem.


### Modelo utilizado no Nível 2

O modelo inicialmente utilizado durante o desenvolvimento foi o
`gemini-3.6-flash`.

Durante os testes, a cota gratuita disponível para esse modelo foi atingida,
resultando em respostas `429 RESOURCE_EXHAUSTED`. Também foram observados
episódios temporários de indisponibilidade (`503 UNAVAILABLE`).

Para permitir a continuidade do desenvolvimento e da execução em lote dentro
das restrições disponíveis, foi adotado o `gemini-3.5-flash-lite`.

A troca foi uma decisão operacional decorrente da limitação de quota, e não
uma escolha inicial de arquitetura. O restante do fluxo de ferramentas,
validação estruturada e instrumentação foi preservado.


### Tratamento de falhas da API

A execução em lote utiliza um mecanismo simples de retry, com até três
tentativas por cliente e espera progressiva entre novas tentativas.

Os resultados concluídos são persistidos incrementalmente em
`outputs/pareceres_agente.json`, reduzindo o risco de perda das análises já
realizadas caso uma execução posterior falhe.

Na execução final, os 10 clientes foram processados com sucesso. Durante o lote, alguns casos exigiram novas tentativas devido a falhas temporárias da API ou respostas incompatíveis com o schema esperado. O mecanismo de retry permitiu concluir o processamento sem interromper todo o lote.


### Métricas e observabilidade

As métricas distinguem o consumo da etapa de planejamento do consumo da
investigação realizada pelo agente.

Na execução final dos 10 clientes foram registrados:

- **19.721 tokens** nas execuções finais bem-sucedidas;
- **14,60 segundos** de latência média;
- **28 chamadas de ferramentas**;
- **72,47 segundos** como maior latência individual, observada no `CLI-013`.

A execução também demonstrou a utilidade do mecanismo de retry: alguns clientes apresentaram falhas temporárias de API ou validação antes de concluírem com sucesso. Essas tentativas malsucedidas e os períodos de espera entre retries não estão incluídos na latência média nem no total consolidado de tokens.

As métricas consolidadas representam as execuções finais bem-sucedidas.
Tentativas encerradas com erro e períodos de espera entre retries não são
incorporados ao total consolidado de tokens nem à latência média.

## Nível 2 — Confronto entre regras e agente

Para permitir a comparação entre as regras determinísticas e o parecer do
agente, foi necessário converter as sinalizações em uma categoria de risco.

O critério adotado foi:

- **alto:** cliente com os dois tipos de alerta ou com 3 ou mais sinalizações;
- **médio:** cliente com 1 ou 2 sinalizações;
- **baixo:** cliente sem sinalizações.

O critério é propositalmente simples e funciona como uma referência
determinística para o confronto, não como uma classificação definitiva de
risco.

### Resultado

A taxa de concordância entre o risco derivado das regras e o risco atribuído
pelo agente foi de **90%**.

Houve uma única divergência, no cliente `CLI-014`:

- risco pelas regras: **alto**;
- risco pelo agente: **médio**.

O cliente recebeu três sinalizações de valor atípico, fazendo com que o
critério determinístico o classificasse automaticamente como risco alto.

O agente, por outro lado, manteve risco médio após analisar o contexto das
operações sinalizadas.

Essa divergência evidencia uma limitação do critério determinístico adotado:
a quantidade de alertas, isoladamente, não diferencia múltiplas ocorrências
de uma mesma tipologia da presença simultânea de diferentes padrões de risco.

Neste caso, considero a classificação do agente defensável, pois as três
sinalizações pertencem à mesma regra de valor atípico e não houve ocorrência
de fracionamento.

Em um cenário real, a divergência deveria ser encaminhada para análise humana,
em vez de considerar automaticamente uma das abordagens como correta.

Com mais tempo, o critério determinístico poderia incorporar pesos distintos
por tipologia, recorrência temporal e combinação de diferentes sinais, além
de ser calibrado sobre exemplos rotulados.