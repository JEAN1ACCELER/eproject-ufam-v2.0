# E-project UFAM

Sistema local de demonstração para organizar projetos acadêmicos, atividades, participantes e compromissos relacionados a programas como PIBIC e PACE.

> **Importante:** este protótipo não é um sistema oficial da UFAM. Não possui login, controle de acesso nem hospedagem multiusuário. O servidor só aceita conexões do próprio computador.

## Requisitos

- Python 3.11 ou superior, com o módulo SQLite padrão.
- Nenhum pacote Python, framework web, banco de dados ou ferramenta Node precisa ser instalado.

## Executar no Windows

Abra o PowerShell nesta pasta e inicie o servidor:

```powershell
python --version
python server.py
```

Abra <http://127.0.0.1:8000>. Mantenha o terminal aberto enquanto utiliza o sistema. Para encerrar, pressione `Ctrl+C`.

Não abra `index.html` diretamente: o salvamento permanente e a API requerem o servidor local.

## Funcionalidades

- **Visão geral:** indicadores, projetos em destaque, próximas atividades e compromissos.
- **Projetos:** cadastro, edição, situação, programa, coordenação, período e progresso.
- **Atividades:** prazos, responsáveis, situação e associação a um projeto.
- **Participantes:** cadastro de docentes, estudantes e voluntários; o mesmo e-mail não pode ser cadastrado duas vezes.
- **Agenda:** calendário mensal ou em lista, criação e edição de compromissos, filtros por projeto e tipo e vínculo com atividades.
- **Equipes de eventos:** vincule responsáveis e convide participantes para cada compromisso.
- **Lembretes:** notificações opcionais do navegador, mediante autorização. O navegador e o sistema precisam permanecer abertos para que sejam enviados.
- **Exportações:** relatórios CSV, compromissos no formato `.ics`, relatórios imprimíveis e backup do banco SQLite.
- **Busca, filtros e exclusões confirmadas** nas telas aplicáveis.

## Arquitetura

```text
Navegador (HTML, CSS e JavaScript)
            │ API JSON local
            ▼
Servidor HTTP e validações (Python padrão)
            │ consultas SQL parametrizadas
            ▼
Banco de dados relacional SQLite
```

- [`index.html`](./index.html): estrutura da interface.
- [`styles.css`](./styles.css): estilos e layout responsivo.
- [`app.js`](./app.js): interface, calendário, validações no navegador e consumo da API.
- [`server.py`](./server.py): servidor local, API JSON, validações e operações do banco.
- [`database.sql`](./database.sql): esquema, restrições de integridade e índices.
- [`tests/`](./tests/): testes automatizados da API e do SQLite.

## Banco de dados

O SQLite é inicializado automaticamente quando o servidor começa:

```text
data/eproject.sqlite3
```

O arquivo do banco é local e está excluído do Git. As tabelas são:

| Tabela | Finalidade |
|---|---|
| `projects` | Programa, coordenação, unidade, datas, situação e progresso dos projetos. |
| `participants` | Docentes, estudantes e voluntários, com e-mail e vínculo opcional a um projeto. |
| `activities` | Atividades, tipo, prazo, situação, projeto e responsável. |
| `calendar_events` | Compromissos, horários, local, situação, projeto, atividade e lembrete. |
| `calendar_event_participants` | Relação entre compromissos e os participantes convidados. |

O esquema utiliza chaves estrangeiras, índices, restrições de situação, validação de períodos e e-mail único. Registros relacionados recebem atualizações ou exclusões compatíveis com essas relações.

### Primeira execução e dados da versão anterior

Se o banco estiver vazio, o sistema o inicializa com registros **de demonstração**. Dados da versão anterior, caso ainda estejam salvos no navegador, são importados apenas nessa primeira inicialização. O banco já inicializado é a fonte permanente dos dados nas próximas visitas.

### Backup e restauração

1. Na página **Relatórios**, escolha **Backup SQLite** para baixar `eproject-backup.sqlite3`.
2. Guarde o arquivo em local seguro.
3. Para restaurá-lo, encerre o servidor e substitua `data/eproject.sqlite3` pela cópia desejada.
4. Inicie o servidor novamente.

## API local

Todas as rotas estão disponíveis somente em `127.0.0.1:8000`:

| Rota | Método | Operação |
|---|---|---|
| `/api/bootstrap` | `GET` | Carrega projetos, participantes, atividades e agenda. |
| `/api/events?from=AAAA-MM-DD&to=AAAA-MM-DD` | `GET` | Lista compromissos em um intervalo. |
| `/api/projects` | `POST` | Cria um projeto. |
| `/api/projects/{id}` | `PUT`, `DELETE` | Atualiza ou exclui um projeto. |
| `/api/people` | `POST` | Cria um participante. |
| `/api/people/{id}` | `PUT`, `DELETE` | Atualiza ou exclui um participante. |
| `/api/activities` | `POST` | Cria uma atividade. |
| `/api/activities/{id}` | `PUT`, `DELETE` | Atualiza ou exclui uma atividade. |
| `/api/events` | `POST` | Agenda um compromisso. |
| `/api/events/{id}` | `PUT`, `DELETE` | Atualiza ou exclui um compromisso. |
| `/api/backup` | `GET` | Baixa uma cópia consistente do SQLite. |

Erros de validação retornam mensagens JSON com um código HTTP apropriado. A importação inicial é aceita somente quando o banco ainda está vazio.

## Testes

Execute no PowerShell a partir da pasta do projeto:

```powershell
python -m unittest discover -s tests -v
```

Os testes utilizam bancos temporários e verificam importação atômica, persistência, operações CRUD, relacionamentos, conflitos, horários inválidos, backup e bloqueio de acesso HTTP direto ao arquivo do banco.

## Implantação, privacidade e contribuições

Esta versão é adequada para demonstração e desenvolvimento **local**. Não a exponha à rede, não a use com dados pessoais reais e não a considere um serviço oficial. Para uma implantação institucional, planeje autenticação integrada, autorização por perfil, HTTPS, logs, backups protegidos, proteção de dados pessoais, testes e revisão de segurança.

O repositório é público, mas o banco de dados e cópias de backup não devem ser enviados ao GitHub.
