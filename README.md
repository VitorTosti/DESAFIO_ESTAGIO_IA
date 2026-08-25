# Desafio Técnico — Estágio em Engenharia de Inteligência Artificial

Solução desenvolvida para o desafio técnico de Engenharia de Inteligência
Artificial, com foco em triagem de operações para Prevenção à Lavagem de
Dinheiro (PLD).

O projeto combina regras determinísticas implementadas com Python e pandas
com modelos de linguagem utilizados para interpretação e geração de pareceres.

## Estrutura do projeto

```text
DESAFIO_ESTAGIO_IA/
├── README.md
├── ENTREGA.yaml
├── requirements.txt
├── .env.example
├── dados/
│   ├── dados_nivel_1.json
│   └── dados_nivel_2.json
├── nivel_1/
│   └── nivel_1.ipynb
├── nivel_2/
│   ├── tools.py
│   ├── agente.py
│   └── confronto.py
├── outputs/
│   ├── ranking_top10.csv
│   ├── pareceres_agente.json
│   ├── metricas_agente.csv
│   └── confronto.csv
└── docs/
    ├── DECISOES.md
    └── USO_DE_IA.md
```

## Nível 1 — Dados e primeira análise com LLM

O Nível 1 realiza:

- carregamento e limpeza dos dados;
- remoção de operações duplicadas;
- tratamento de datas inválidas;
- normalização de valores em USD para BRL;
- agregações por cliente e canal;
- implementação das regras de fracionamento e valor atípico;
- validação das regras determinísticas;
- geração de parecer estruturado com LLM;
- validação da resposta da LLM;
- registro de tokens e latência;
- comparação entre duas versões de prompt.

O notebook está disponível em `nivel_1/nivel_1.ipynb`.

As células foram mantidas com suas saídas executadas para permitir a avaliação
dos resultados.

## Nível 2 — Escala e agente com ferramentas

No Nível 2, o tratamento e as regras determinísticas foram aplicados sobre a
base maior.

A solução gera um ranking dos 10 clientes mais sinalizados e disponibiliza
três ferramentas de investigação:

- `historico_cliente(cliente_id)`;
- `operacoes_do_dia(cliente_id, data)`;
- `perfil_canal(cliente_id)`.

O agente utiliza inicialmente o histórico determinístico do cliente e executa
uma etapa de planejamento para decidir quais ferramentas adicionais são
necessárias para cada investigação.

As ferramentas são disponibilizadas dinamicamente, evitando a execução
obrigatória de todas elas para todos os clientes.

Os pareceres possuem estrutura validada contendo:

- nível de risco;
- tipologia suspeita;
- red flags;
- justificativa.

## Execução em lote

O agente foi executado sobre os 10 clientes mais sinalizados.

A execução final registrou:

- 10 clientes processados com sucesso;
- 19.721 tokens nas execuções finais bem-sucedidas;
- 14,60 segundos de latência média;
- 28 chamadas de ferramentas.

O processamento possui mecanismo de retry para falhas temporárias da API e
respostas incompatíveis com o schema esperado.

## Confronto entre regras e agente

Foi realizada uma comparação entre o risco derivado das regras determinísticas
e o risco atribuído pelo agente.

A taxa de concordância obtida foi de 90%.

A única divergência ocorreu para o cliente `CLI-014`, classificado como risco
alto pelo critério determinístico de confronto e como risco médio pelo agente.

A análise dessa divergência está documentada em `docs/DECISOES.md`.

## Como executar

### 1. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar a API

Crie um arquivo `.env` na raiz do projeto a partir do `.env.example`:

```text
GOOGLE_API_KEY=sua_chave_aqui
```

O arquivo `.env` não deve ser versionado.

### 3. Executar o Nível 1

Abra `nivel_1/nivel_1.ipynb` e execute o notebook em um ambiente Jupyter.

### 4. Executar as regras e ferramentas do Nível 2

A partir da pasta `nivel_2`:

```bash
python tools.py
```

### 5. Executar o agente em lote

```bash
python agente.py
```

### 6. Executar o confronto

```bash
python confronto.py
```

Os resultados são gravados na pasta `outputs/`.

## Separação entre regras e LLM

Uma decisão central da solução foi manter cálculos e limites fora da LLM.

Python e pandas são responsáveis por limpeza, conversão monetária, contagens,
somas, médias, medianas, percentuais, aplicação das regras e flags.

A LLM é utilizada para planejamento da investigação, seleção de ferramentas,
interpretação contextual e produção do parecer.

## Documentação

As principais decisões, limitações e trade-offs estão documentados em
`docs/DECISOES.md`.

O uso de ferramentas de IA durante o desenvolvimento está documentado em
`docs/USO_DE_IA.md`.

## Observação

Todos os dados utilizados no projeto são fictícios e fazem parte do desafio
técnico.