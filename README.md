# E-project UFAM

Plataforma local de apoio à gestão de projetos acadêmicos de pesquisa e extensão da Universidade Federal do Amazonas.

> O escopo segue o Documento de Especificação do Sistema E-Project, versão 1.0. Este MVP não é um sistema oficial da UFAM e não substitui E-campus, SEI ou os canais institucionais de protocolo.

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

- Cadastro, login e encerramento de sessão; as senhas são derivadas com `scrypt` e salt aleatório.
- Dashboard com projetos, tarefas, prazos e indicadores da conta autenticada.
- CRUD de projetos nos estados Planejado, Em andamento, Concluído, Suspenso e Cancelado, além dos estados antigos preservados; cada projeto tem proprietário e toda tarefa exige um projeto existente.
- Acesso aos projetos e dados relacionados limitado ao proprietário. A gestão de papéis e o compartilhamento institucional de projetos ainda não estão implementados.
- Cadastro auxiliar de participantes e agenda de compromissos, mantidos como recursos complementares do protótipo.
- Relatórios imprimíveis, exportação CSV/ICS e lembretes do navegador enquanto o app estiver aberto.

## Situação no Documento

| Requisito | Situação nesta versão |
|---|---|
| RF001–RF004: cadastro, autenticação e sessão | Implementado no MVP local. |
| RF005: dashboard | Implementado com indicadores disponíveis na base local. |
| RF006–RF007: criar e consultar projetos | Implementado com isolamento por proprietário. |
| RF008: atualizar projeto | Implementado para o proprietário. |
| RF009–RF010: criar e atualizar tarefas | Implementado; a tarefa precisa pertencer a um projeto. |
| RF011: filtros de tarefas | Busca e filtro por situação implementados; filtros avançados são parciais. |
| Editais, documentos, PDF, presença, gestão administrativa e sincronização | Planejados ou parciais; não apresentar como concluídos. |
| Integração E-campus/SEI | Fora do escopo; o app não protocola submissões. |

O app preserva agenda, participantes e exportações como funcionalidades auxiliares da implementação anterior; elas não ampliam o escopo oficial de MVP descrito no documento.

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
data/eproject-ufam.sqlite3
```

O arquivo do banco é local e está excluído do Git. As tabelas são:

| Tabela | Finalidade |
|---|---|
| `projects` | Programa, coordenação, unidade, datas, situação e progresso dos projetos. |
| `participants` | Docentes, estudantes e voluntários vinculados a um projeto. |
| `activities` | Tarefas, tipo, prazo, situação, projeto obrigatório e responsável. |
| `users` / `password_credentials` | Perfil, aceites, estado da conta e credencial derivada separada. |
| `calendar_events` | Compromissos, horários, local, situação, projeto, atividade e lembrete. |
| `calendar_event_participants` | Relação entre compromissos e os participantes convidados. |

O esquema utiliza chaves estrangeiras, índices, restrições de situação, validação de períodos e e-mail único. A versão do esquema é migrada automaticamente quando o servidor inicia.

### Cadastro e dados locais

- Não são criadas contas ou projetos de demonstração com senha conhecida.
- A primeira conta cadastrada recebe o perfil `ORIENTADOR`; os cadastros seguintes recebem `ORIENTANDO`. O auto cadastro não pode conceder perfil de coordenador ou administrador.
- A sessão usa um token em memória no servidor; reiniciar o servidor invalida os tokens existentes e exige novo login.
- Se houver dados da versão anterior em `localStorage` e o banco estiver vazio, o primeiro Orientador pode importá-los após autenticar. A chave antiga só é removida depois que a importação termina com sucesso.
- Na migração, projetos antigos sem proprietário são vinculados à primeira conta. Tarefas antigas sem projeto são preservadas sob um projeto de recuperação chamado **Tarefas sem projeto (dados legados)**.
- Contas demonstrativas antigas com identificadores e e-mails conhecidos são desativadas pela migração. Nenhum registro de projeto ou tarefa é descartado por essa operação.

O arquivo `data/eproject.sqlite3` já existente tem um esquema de outro sistema e é mantido intacto. O E-Project usa `data/eproject-ufam.sqlite3`, ignorado pelo Git. Para escolher outro caminho, defina `EPROJECT_DATABASE` antes de iniciar o servidor. Antes de migrar uma base E-Project antiga, encerre o servidor e faça uma cópia do arquivo correspondente.

### Backup e restauração

Para cópia local, encerre o servidor e copie `data/eproject-ufam.sqlite3` para um local protegido. A rota `/api/backup` exige perfil `ADMINISTRADOR`; a interface pública não oferece concessão desse papel no MVP. Para restaurar, encerre o servidor e substitua o arquivo pela cópia.

## API local

Todas as rotas estão disponíveis somente em `127.0.0.1:8000`:

| Rota | Método | Operação |
|---|---|---|
| `/api/register`, `/api/login` | `POST` | Cadastro público e autenticação. |
| `/api/session`, `/api/logout` | `GET`, `POST` | Consulta e encerra a sessão autenticada. |
| `/api/bootstrap` | `GET` | Carrega apenas dados acessíveis ao usuário; inclui `projects`, `tasks` e `activities` (alias legado). |
| `/api/projects` | `POST` | Cria projeto para o proprietário autenticado. |
| `/api/projects/{id}` | `PUT`, `DELETE` | Atualiza ou exclui projeto próprio. Tarefas vinculadas são removidas junto com o projeto. |
| `/api/tasks` | `POST` | Cria tarefa obrigatoriamente vinculada a projeto acessível. |
| `/api/tasks/{id}` | `PUT`, `DELETE` | Atualiza ou exclui tarefa própria. `/api/activities` continua como alias compatível. |
| `/api/people`, `/api/events` | `POST`, `PUT`, `DELETE` | Operações auxiliares autenticadas, limitadas aos projetos próprios. |
| `/api/events?from=AAAA-MM-DD&to=AAAA-MM-DD` | `GET` | Lista compromissos dos projetos próprios no intervalo. |
| `/api/backup` | `GET` | Backup SQLite restrito a `ADMINISTRADOR`. |
| `/api/import` | `POST` | Importação inicial restrita a `ORIENTADOR` ou `ADMINISTRADOR` e somente com banco vazio. |

Todas as rotas de dados exigem `Authorization: Bearer <token>`. Apenas cadastro e login são públicos. Erros de validação e autenticação retornam JSON com códigos HTTP apropriados; respostas de login inválido são genéricas.

## Testes

Execute no PowerShell a partir da pasta do projeto:

```powershell
python -m unittest discover -s tests -v
```

Os testes utilizam bancos temporários e verificam cadastro/login, sessão obrigatória, isolamento entre contas, importação única, CRUD, vínculo obrigatório das tarefas, migração de dados legados, horários inválidos, backup administrativo e bloqueio de acesso HTTP direto ao banco.

## Implantação, privacidade e contribuições

Esta versão é adequada para demonstração e desenvolvimento **local**. O servidor aceita conexões somente de `127.0.0.1`; não a exponha à rede nem use dados pessoais reais. A autenticação, o isolamento por proprietário e o hash de senha do MVP não substituem revisão de segurança para produção. Permanecem planejados: gestão institucional de papéis, compartilhamento de projetos, notificações remotas, documentos e relatórios PDF, presença, sincronização, observabilidade e integrações oficiais.

O repositório é público, mas o banco de dados e cópias de backup não devem ser enviados ao GitHub.
