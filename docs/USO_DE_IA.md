# Uso de IA no desenvolvimento

Durante o desenvolvimento deste desafio, utilizei ferramentas de IA generativa
como apoio à implementação, revisão e depuração da solução.

## Ferramentas utilizadas

- **ChatGPT (OpenAI):** utilizado como apoio durante o desenvolvimento;
- **Gemini API (Google):** utilizada como componente da solução agentic do
  Nível 2.

## Como o ChatGPT foi utilizado

O ChatGPT foi utilizado principalmente para:

- discutir alternativas de arquitetura;
- auxiliar na estruturação do código Python;
- revisar implementações com pandas;
- auxiliar na criação e revisão das ferramentas utilizadas pelo agente;
- discutir a separação entre regras determinísticas e responsabilidades da LLM;
- auxiliar na implementação do planejamento dinâmico de ferramentas;
- interpretar mensagens de erro da API e apoiar a depuração;
- sugerir formas de instrumentar latência, tokens e chamadas de ferramentas;
- auxiliar na estruturação da execução em lote e do mecanismo de retry;
- revisar a lógica do confronto entre regras e agente;
- auxiliar na organização e redação da documentação.

As sugestões geradas por IA foram revisadas e testadas durante o
desenvolvimento. A execução dos scripts, análise dos resultados e decisões
sobre quais abordagens manter no projeto foram realizadas de forma iterativa.

## Uso de LLM na solução

Além do uso de IA como ferramenta de apoio ao desenvolvimento, o próprio
projeto utiliza uma LLM como parte da solução do Nível 2.

O agente recebe informações previamente processadas por código determinístico
e utiliza ferramentas para investigar clientes sinalizados e produzir um
parecer estruturado de triagem.

Os cálculos financeiros, limpeza dos dados, aplicação das regras, ranking e
métricas derivadas dos dados permanecem implementados de forma determinística
com Python e pandas.

A LLM é responsável pela seleção dos aprofundamentos necessários e pela
interpretação contextual dos resultados, sem substituir as regras
determinísticas.

## Limitações observadas

Durante o desenvolvimento foram observadas algumas limitações no uso de LLMs:

- variação de latência entre execuções;
- indisponibilidade temporária da API;
- limites de quota;
- respostas ocasionalmente incompatíveis com o schema esperado;
- possibilidade de chamadas redundantes de ferramentas;
- variação na interpretação e classificação de risco entre execuções.

Essas limitações motivaram a utilização de validação estruturada, retries,
instrumentação de métricas, restrição dinâmica das ferramentas disponíveis e
separação explícita entre cálculos determinísticos e interpretação pela LLM.

## Responsabilidade sobre a entrega

A IA foi utilizada como ferramenta de apoio ao desenvolvimento, e não como
substituta da validação da solução.

O código e os resultados utilizados na entrega foram executados, inspecionados
e ajustados ao longo do desenvolvimento. As decisões consideradas relevantes
para a implementação estão documentadas em `docs/DECISOES.md`.