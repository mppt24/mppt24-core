# Encerramento — observer-ssh 1.0.0

**Data:** 18 de julho de 2026\
**Estado:** Concluído e validado

## Resultado

O primeiro Observer funcional da MPPT24 CORE foi concluído.

Produz 18 factos SSH em JSON, separa categorias de eventos, distingue zero de dados desconhecidos e funciona sem privilégios administrativos.

A saída é validada e gravada atomicamente em:

`data/observer/observer-ssh.json`

Foram testados o funcionamento normal, falha do `systemctl`, falha do journal, falha simultânea, estados inválidos e confiança fora do intervalo.

A configuração efetiva via `sshd -T` e o Fail2Ban permanecem fora do módulo porque exigem privilégios adicionais. As permissões do servidor não foram enfraquecidas.

**Conclusão:** `observer-ssh 1.0.0` aprovado.
