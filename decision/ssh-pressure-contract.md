# Prevenção SSH em modo de observação

Este piloto é uma função de decisão local, sem recolha, serviço, timer,
Telegram ou ações administrativas. Não altera o Decision Engine nem o
registo de observadores em produção. Não classifica vulnerabilidades,
não declara intrusão e não bloqueia tráfego.

Cada janela fechada, alinhada em UTC, descreve o mesmo serviço, percurso
e intervalo: novas ligações observadas na rede, tentativas de autenticação
rejeitadas e resultado de uma verificação funcional pelo percurso legítimo
(como Tailscale). Estar em escuta não substitui essa verificação. As
contagens de rede e autenticação corroboram-se; nunca são somadas.
O futuro coletor deve validar a cobertura do sensor e do journal, evitar
duplicar eventos da mesma fonte e fornecer `None` quando não puder sustentar
um valor. Um zero significa que a janela foi medida.

A configuração é explícita e não tem valores de produção por defeito.
A amostra atual do ESCUDO não calibra limites: não mediu a taxa de novas
ligações, não confirmou perdas e não verificou disponibilidade pela VPN
sob pressão. Os números nos testes são apenas sintéticos.

Rede e autenticação acima dos limites em janelas consecutivas sinalizam
pressão sustentada. Uma medida temporária só é recomendada para avaliação
quando houver também impacto no percurso legítimo. Recuperação exige
janelas consecutivas completas, abaixo de ambos os limites, e serviço a
responder. Dados em falta ou atrasados quebram a sequência sem simular
recuperação. O histórico de avaliação deve incluir o início do episódio
pendente; um futuro coletor deverá persistir esse estado entre execuções.
Antes da implantação é necessário validar a recolha, calibrar as janelas
com tráfego real e rever as recomendações em modo de observação.
