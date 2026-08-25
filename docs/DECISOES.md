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
operações envolvidas em um único episódio de fracionamento infle artificialmente
a posição do cliente no ranking.