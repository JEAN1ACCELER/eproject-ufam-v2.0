const today = new Date();
const dateOffset = (days) => {
  const date = new Date(today);
  date.setDate(date.getDate() + days);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
};
const localDateTime = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}T${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;

const seedData = {
  projects: [
    { id: "p1", name: "Monitoramento da qualidade da água no Alto Solimões", program: "PIBIC", coordinator: "Profa. Exemplo 1", unit: "Instituto de Ciências Exatas", start: "2026-03-01", end: "2027-02-28", status: "Em andamento", progress: 68, description: "Análise de parâmetros físico-químicos em comunidades ribeirinhas." },
    { id: "p2", name: "Saberes tradicionais e educação ambiental", program: "PACE", coordinator: "Prof. Exemplo 2", unit: "Faculdade de Educação", start: "2026-02-01", end: "2026-12-15", status: "Em andamento", progress: 42, description: "Ações de educação ambiental construídas com comunidades locais." },
    { id: "p3", name: "Acervo digital de narrativas amazônicas", program: "PIBIC", coordinator: "Profa. Exemplo 3", unit: "Instituto de Ciências Humanas", start: "2026-04-10", end: "2027-03-31", status: "Planejado", progress: 15, description: "Organização e preservação digital de narrativas da região." },
    { id: "p4", name: "Tecnologias sociais para agricultura familiar", program: "Extensão", coordinator: "Prof. Exemplo 4", unit: "Faculdade de Ciências Agrárias", start: "2025-08-01", end: "2026-07-30", status: "Em andamento", progress: 82, description: "Desenvolvimento participativo de soluções para agricultura familiar." }
  ],
  people: [
    { id: "u1", name: "Docente Demonstrativa 1", email: "docente1@example.invalid", role: "Professor(a)", unit: "Instituto de Ciências Exatas", projectId: "p1" },
    { id: "u2", name: "Estudante Demonstrativo 1", email: "estudante1@example.invalid", role: "Aluno(a)", unit: "Instituto de Ciências Exatas", projectId: "p1" },
    { id: "u3", name: "Voluntária Demonstrativa 1", email: "voluntaria1@example.invalid", role: "Voluntário(a)", unit: "Faculdade de Educação", projectId: "p2" },
    { id: "u4", name: "Docente Demonstrativo 2", email: "docente2@example.invalid", role: "Professor(a)", unit: "Faculdade de Educação", projectId: "p2" },
    { id: "u5", name: "Estudante Demonstrativo 2", email: "estudante2@example.invalid", role: "Aluno(a)", unit: "Instituto de Ciências Humanas", projectId: "p3" },
    { id: "u6", name: "Docente Demonstrativo 3", email: "docente3@example.invalid", role: "Professor(a)", unit: "Instituto de Ciências Humanas", projectId: "p3" }
  ],
  activities: [
    { id: "a1", title: "Coleta de amostras — comunidade do Lago", projectId: "p1", responsibleId: "u2", dueDate: dateOffset(2), status: "Em andamento", type: "Pesquisa", description: "Realizar coleta e registrar coordenadas das amostras." },
    { id: "a2", title: "Entrega do relatório parcial", projectId: "p1", responsibleId: "u1", dueDate: dateOffset(7), status: "Pendente", type: "Relatório", description: "Consolidar resultados e anexar evidências do período." },
    { id: "a3", title: "Oficina de educação ambiental", projectId: "p2", responsibleId: "u3", dueDate: dateOffset(12), status: "Pendente", type: "Extensão", description: "Preparar materiais para atividade com a comunidade." },
    { id: "a4", title: "Catalogação das entrevistas", projectId: "p3", responsibleId: "u5", dueDate: dateOffset(18), status: "Pendente", type: "Pesquisa", description: "Revisar metadados e organizar arquivos do acervo." },
    { id: "a5", title: "Reunião de acompanhamento", projectId: "p4", responsibleId: "u4", dueDate: dateOffset(-2), status: "Concluída", type: "Reunião", description: "Avaliar cronograma e próximos passos do projeto." }
  ],
  events: []
};

const state = {
  data: { projects: [], people: [], activities: [], events: [] },
  ready: false,
  view: "dashboard",
  calendarMonth: new Date(today.getFullYear(), today.getMonth(), 1),
  calendarMode: "month",
  search: "",
  filters: { projectStatus: "Todos", activityStatus: "Todos", personRole: "Todos", eventType: "Todos", eventProject: "Todos" }
};

const views = {
  dashboard: "Visão geral",
  projects: "Projetos",
  activities: "Atividades",
  people: "Participantes",
  calendar: "Agenda",
  reports: "Relatórios"
};

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
    body: options.body === undefined ? undefined : JSON.stringify(options.body)
  });
  let result = {};
  try {
    result = await response.json();
  } catch (error) {
    if (!response.ok) throw new Error(`O servidor respondeu com erro HTTP ${response.status}.`);
  }
  if (!response.ok) throw new Error(result.error || `A solicitação falhou (HTTP ${response.status}).`);
  return result;
}

function isApplicationData(value) {
  return value && ["projects", "people", "activities"].every((key) => Array.isArray(value[key]));
}

async function refreshData() {
  state.data = await apiRequest("/api/bootstrap");
  if (!Array.isArray(state.data.events)) state.data.events = [];
  if (state.ready) render();
}

async function startApplication() {
  try {
    const saved = await apiRequest("/api/bootstrap");
    const isEmpty = ["projects", "people", "activities", "events"].every((key) => saved[key]?.length === 0);
    if (isEmpty) {
      let legacy = null;
      try {
        const previous = localStorage.getItem("eproject-ufam-data-v1");
        if (previous) legacy = JSON.parse(previous);
      } catch (error) {
        console.error("Os dados locais da versão anterior não puderam ser lidos.", error);
      }
      const initialData = isApplicationData(legacy) ? { ...legacy, events: legacy.events || [] } : seedData;
      try {
        await apiRequest("/api/import", { method: "POST", body: initialData });
        localStorage.removeItem("eproject-ufam-data-v1");
        toast(isApplicationData(legacy)
          ? "Seus cadastros anteriores foram migrados para o banco de dados."
          : "Banco criado com dados de demonstração. Você já pode cadastrar seus projetos.");
      } catch (error) {
        const latest = await apiRequest("/api/bootstrap");
        const remainsEmpty = ["projects", "people", "activities", "events"].every((key) => latest[key]?.length === 0);
        if (remainsEmpty) throw error;
      }
    }
    await refreshData();
    state.ready = true;
    render();
    checkReminders();
    window.setInterval(checkReminders, 60_000);
  } catch (error) {
    console.error("Não foi possível inicializar a aplicação.", error);
    document.getElementById("page-content").innerHTML = `<section class="panel"><div class="panel-body">${emptyState("Não foi possível conectar ao banco de dados", "Inicie o servidor local com python server.py e atualize a página.")}<p class="database-error">${escapeHtml(error.message)}</p><button class="primary-button" data-action="retry-connection">Tentar novamente</button></div></section>`;
    toast(`Erro ao conectar: ${error.message}`, true);
  }
}

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat("pt-BR").format(date);
}

function projectById(id) { return state.data.projects.find((item) => item.id === id); }
function personById(id) { return state.data.people.find((item) => item.id === id); }

function matchesSearch(...values) {
  const query = state.search.trim().toLocaleLowerCase("pt-BR");
  return !query || values.some((value) => String(value || "").toLocaleLowerCase("pt-BR").includes(query));
}

function statusClass(status) {
  const classes = {
    "Em andamento": "em-andamento",
    "Concluída": "concluida",
    "Pendente": "pendente",
    "Planejado": "planejado",
    "Pausado": "pausado",
    "Encerrado": "encerrado",
    "Atrasada": "atrasada",
    "Realizado": "concluida",
    "Cancelado": "cancelado"
  };
  return `status-${classes[status] || "planejado"}`;
}

function statusPill(status) {
  return `<span class="status-pill ${statusClass(status)}">${escapeHtml(status)}</span>`;
}

function projectOptions(selected = "") {
  return state.data.projects.map((project) =>
    `<option value="${escapeHtml(project.id)}" ${project.id === selected ? "selected" : ""}>${escapeHtml(project.name)}</option>`
  ).join("");
}

function personOptions(selected = "") {
  return state.data.people.map((person) =>
    `<option value="${escapeHtml(person.id)}" ${person.id === selected ? "selected" : ""}>${escapeHtml(person.name)} — ${escapeHtml(person.role)}</option>`
  ).join("");
}

function render() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });
  document.getElementById("breadcrumb-current").textContent = views[state.view];
  document.getElementById("project-nav-count").textContent = state.data.projects.length;
  const page = document.getElementById("page-content");
  if (!state.ready) {
    page.innerHTML = '<section class="panel"><div class="panel-body"><div class="empty-state"><strong>Conectando ao banco de dados</strong>Carregando os projetos e a agenda.</div></div></section>';
    return;
  }
  page.innerHTML = ({
    dashboard: renderDashboard,
    projects: renderProjects,
    activities: renderActivities,
    people: renderPeople,
    calendar: renderCalendar,
    reports: renderReports
  })[state.view]();
  page.querySelectorAll("[data-filter]").forEach((select) => {
    select.value = state.filters[select.dataset.filter];
  });
}

function renderDashboard() {
  const activeProjects = state.data.projects.filter((project) => project.status === "Em andamento").length;
  const pendingActivities = state.data.activities.filter((item) => item.status !== "Concluída").length;
  const peopleCount = state.data.people.length;
  const completed = state.data.activities.filter((item) => item.status === "Concluída").length;
  const completionRate = state.data.activities.length ? Math.round(completed / state.data.activities.length * 100) : 0;
  const upcoming = [...state.data.activities]
    .filter((item) => item.status !== "Concluída")
    .sort((a, b) => a.dueDate.localeCompare(b.dueDate))
    .slice(0, 4);
  const projects = [...state.data.projects].slice(0, 4);
  const upcomingEvents = state.data.events
    .filter((event) => event.status === "Agendado" && event.startAt >= localDateTime(today))
    .sort((a, b) => a.startAt.localeCompare(b.startAt))
    .slice(0, 3);
  const dashboardDate = new Intl.DateTimeFormat("pt-BR", {
    weekday: "long", day: "2-digit", month: "long", year: "numeric"
  }).format(today).toLocaleUpperCase("pt-BR");
  return `
    <div class="page-heading">
      <div><p class="eyebrow">${escapeHtml(dashboardDate)}</p>
        <h1>Olá, equipe acadêmica</h1><p class="heading-subtitle">Acompanhe o andamento das atividades e projetos da UFAM.</p></div>
      <div class="button-row"><button class="secondary-button" data-action="export-summary">↧ Exportar resumo</button><button class="primary-button" data-action="add-project"><span class="plus">＋</span>Novo projeto</button></div>
    </div>
    <div class="stats-grid">
      ${statCard("Projetos ativos", activeProjects, `de ${state.data.projects.length} projetos cadastrados`, "▤")}
      ${statCard("Atividades pendentes", pendingActivities, "Acompanhe prazos e entregas", "◷")}
      ${statCard("Participantes", peopleCount, "Professores, alunos e voluntários", "◎")}
      ${statCard("Atividades concluídas", `${completionRate}%`, `${completed} de ${state.data.activities.length} atividades`, "✓")}
    </div>
    <div class="dashboard-grid">
      <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Projetos em destaque</h2><p class="panel-subtitle">Visão rápida do andamento dos projetos</p></div><button class="text-button" data-view="projects">Ver todos →</button></div>
        <div class="panel-body"><div class="project-list">${projects.length ? projects.map((project) => `
          <div class="project-row"><div><div class="project-name">${escapeHtml(project.name)}</div><div class="project-meta">${escapeHtml(project.program)} · ${escapeHtml(project.coordinator)}</div></div>
            <div class="progress-wrap"><div class="progress-track"><div class="progress-fill" style="width:${Math.max(0, Math.min(100, Number(project.progress) || 0))}%"></div></div><span class="progress-value">${escapeHtml(project.progress)}%</span></div>${statusPill(project.status)}</div>`).join("") : emptyState("Nenhum projeto cadastrado", "Cadastre um projeto para acompanhar seu progresso.")}</div></div>
      </section>
      <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Próximas atividades</h2><p class="panel-subtitle">Prazos e compromissos da equipe</p></div><button class="text-button" data-view="calendar">Abrir agenda →</button></div>
        <div class="panel-body"><div class="activity-list">${upcoming.length ? upcoming.map(activityRow).join("") : emptyState("Tudo em dia!", "Não há atividades pendentes.")}</div>
          <div class="dashboard-events-heading"><h3 class="panel-title">Compromissos agendados</h3><button class="text-button" data-action="add-event">Agendar</button></div>
          <div class="activity-list">${upcomingEvents.length ? upcomingEvents.map(eventDashboardRow).join("") : emptyState("Sem compromissos próximos", "Adicione uma reunião ou uma atividade de campo.")}</div>
        </div>
      </section>
    </div>`;
}

function statCard(label, value, note, icon) {
  return `<article class="stat-card"><div class="stat-top"><span>${escapeHtml(label)}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${escapeHtml(value)}</div><div class="stat-note">${escapeHtml(note)}</div></article>`;
}

function emptyState(title, message) {
  return `<div class="empty-state"><strong>${escapeHtml(title)}</strong>${escapeHtml(message)}</div>`;
}

function activityRow(activity) {
  const project = projectById(activity.projectId);
  const date = activity.dueDate ? new Date(`${activity.dueDate}T12:00:00`) : null;
  return `<div class="activity-row"><div class="date-tile"><strong>${date ? date.getDate() : "—"}</strong><small>${date ? new Intl.DateTimeFormat("pt-BR", { month: "short" }).format(date).replace(".", "") : "—"}</small></div>
    <div><div class="activity-name">${escapeHtml(activity.title)}</div><div class="activity-project">${escapeHtml(project?.program || "Projeto removido")}</div></div>${statusPill(activity.status)}</div>`;
}

function eventDashboardRow(event) {
  const date = new Date(event.startAt);
  const time = new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(date);
  return `<div class="activity-row"><div class="date-tile"><strong>${date.getDate()}</strong><small>${escapeHtml(new Intl.DateTimeFormat("pt-BR", { month: "short" }).format(date).replace(".", ""))}</small></div>
    <div><div class="activity-name">${escapeHtml(event.title)}</div><div class="activity-project">${time} · ${escapeHtml(event.location || event.type)}</div></div>${statusPill(event.status)}</div>`;
}

function renderCalendar() {
  const month = new Date(state.calendarMonth.getFullYear(), state.calendarMonth.getMonth(), 1);
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const monthLabel = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(month);
  const firstOffset = (month.getDay() + 6) % 7;
  const daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
  const weekCount = Math.ceil((firstOffset + daysInMonth) / 7);
  const events = state.data.events.filter((event) => {
    const eventDate = event.startAt.slice(0, 10);
    return eventDate.startsWith(`${year}-${String(monthIndex + 1).padStart(2, "0")}`) &&
      (state.filters.eventType === "Todos" || event.type === state.filters.eventType) &&
      (state.filters.eventProject === "Todos" || event.projectId === state.filters.eventProject) &&
      matchesSearch(event.title, event.type, event.location, projectById(event.projectId)?.name, personById(event.responsibleId)?.name);
  });
  const monthStart = `${year}-${String(monthIndex + 1).padStart(2, "0")}-01`;
  const monthEnd = `${year}-${String(monthIndex + 1).padStart(2, "0")}-${String(daysInMonth).padStart(2, "0")}`;
  const activities = state.data.activities.filter((activity) =>
    activity.dueDate >= monthStart && activity.dueDate <= monthEnd &&
    (state.filters.eventProject === "Todos" || activity.projectId === state.filters.eventProject) &&
    matchesSearch(activity.title, activity.type, projectById(activity.projectId)?.name, personById(activity.responsibleId)?.name)
  );
  const days = Array.from({ length: weekCount * 7 }, (_, index) => {
    const day = index - firstOffset + 1;
    if (day < 1 || day > daysInMonth) return '<div class="calendar-day outside-month" aria-hidden="true"></div>';
    const key = `${year}-${String(monthIndex + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const dayEvents = events.filter((event) => event.startAt.slice(0, 10) === key);
    const dayActivities = activities.filter((activity) => activity.dueDate === key);
    const items = [
      ...dayEvents.map((event) => ({ kind: "event", id: event.id, title: event.title, time: event.startAt.slice(11, 16), status: event.status })),
      ...dayActivities.map((activity) => ({ kind: "activity", id: activity.id, title: activity.title, time: "", status: activity.status }))
    ].slice(0, 3);
    const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    return `<article class="calendar-day ${key === todayKey ? "today" : ""}"><button class="calendar-day-number" data-action="add-event-date" data-date="${key}" aria-label="Agendar em ${formatDate(key)}">${day}</button>
      ${items.map((item) => `<button class="calendar-chip ${item.kind === "activity" ? "activity-chip" : ""} ${statusClass(item.status)}" data-action="${item.kind === "event" ? "edit-event" : "edit-activity"}" data-id="${escapeHtml(item.id)}" title="${escapeHtml(item.title)}">${item.time ? `<span>${item.time}</span> ` : ""}${escapeHtml(item.title)}</button>`).join("")}
      ${dayEvents.length + dayActivities.length > 3 ? `<span class="calendar-overflow">+${dayEvents.length + dayActivities.length - 3} itens</span>` : ""}
    </article>`;
  }).join("");
  const list = [...events.map((event) => ({ ...event, kind: "event" })), ...activities.map((activity) => ({ ...activity, kind: "activity", startAt: `${activity.dueDate}T00:00` }))]
    .sort((a, b) => a.startAt.localeCompare(b.startAt));
  return `<div class="page-heading"><div><p class="eyebrow">PRAZOS, REUNIÕES E ATIVIDADES DE CAMPO</p><h1>Agenda acadêmica</h1><p class="heading-subtitle">Agende reuniões, acompanhe entregas e organize as equipes dos projetos.</p></div><div class="button-row"><button class="secondary-button" data-action="export-calendar">Exportar .ics</button><button class="primary-button" data-action="add-event"><span class="plus">＋</span>Novo compromisso</button></div></div>
    <section class="panel calendar-panel">
      <div class="calendar-toolbar"><div class="calendar-month-navigation"><button class="calendar-nav-button" data-action="calendar-prev" aria-label="Mês anterior">‹</button><h2>${escapeHtml(monthLabel)}</h2><button class="calendar-nav-button" data-action="calendar-next" aria-label="Próximo mês">›</button><button class="secondary-button" data-action="calendar-today">Hoje</button></div>
        <div class="calendar-toolbar-actions"><select class="filter-select" data-filter="eventProject" aria-label="Filtrar por projeto"><option value="Todos">Todos os projetos</option>${projectOptions()}</select><select class="filter-select" data-filter="eventType" aria-label="Filtrar por tipo de compromisso"><option>Todos</option>${["Reunião", "Orientação", "Atividade de campo", "Apresentação", "Entrega", "Outro"].map((type) => `<option>${type}</option>`).join("")}</select><div class="calendar-mode-switch"><button class="${state.calendarMode === "month" ? "selected" : ""}" data-action="calendar-mode" data-mode="month">Mês</button><button class="${state.calendarMode === "list" ? "selected" : ""}" data-action="calendar-mode" data-mode="list">Lista</button></div></div>
      </div>
      ${state.calendarMode === "month" ? `<div class="calendar-grid"><div class="calendar-weekday">Seg</div><div class="calendar-weekday">Ter</div><div class="calendar-weekday">Qua</div><div class="calendar-weekday">Qui</div><div class="calendar-weekday">Sex</div><div class="calendar-weekday">Sáb</div><div class="calendar-weekday">Dom</div>${days}</div>` :
      `<div class="agenda-list">${list.length ? list.map((item) => item.kind === "event" ? eventListRow(item) : activityListRow(item)).join("") : emptyState("Nenhum compromisso ou prazo neste mês", "Use “Novo compromisso” para agendar uma reunião, orientação ou atividade.")}</div>`}
      <div class="calendar-footer">${events.length} ${events.length === 1 ? "compromisso" : "compromissos"} e ${activities.length} ${activities.length === 1 ? "prazo de atividade" : "prazos de atividades"} neste mês · Os lembretes do navegador funcionam enquanto a aplicação estiver aberta.</div>
    </section>`;
}

function eventListRow(event) {
  const date = new Date(event.startAt);
  const time = `${new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(date)}–${new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date(event.endAt))}`;
  const participants = (event.participantIds || []).map((id) => personById(id)?.name).filter(Boolean).join(", ");
  return `<div class="agenda-list-row"><div class="agenda-list-date">${escapeHtml(new Intl.DateTimeFormat("pt-BR", { weekday: "short", day: "2-digit", month: "short" }).format(date))}</div><div class="agenda-list-content"><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.type)} · ${escapeHtml(projectById(event.projectId)?.name || "Sem projeto")} · ${time}${event.location ? ` · ${escapeHtml(event.location)}` : ""}${participants ? ` · ${escapeHtml(participants)}` : ""}</small></div>${statusPill(event.status)}<button class="small-action" data-action="edit-event" data-id="${escapeHtml(event.id)}">Editar</button></div>`;
}

function activityListRow(activity) {
  const date = new Date(`${activity.dueDate}T12:00:00`);
  return `<div class="agenda-list-row"><div class="agenda-list-date">${escapeHtml(new Intl.DateTimeFormat("pt-BR", { weekday: "short", day: "2-digit", month: "short" }).format(date))}</div><div class="agenda-list-content"><strong>${escapeHtml(activity.title)}</strong><small>Prazo · ${escapeHtml(projectById(activity.projectId)?.name || "Sem projeto")} · ${escapeHtml(personById(activity.responsibleId)?.name || "Sem responsável")}</small></div>${statusPill(activity.status)}<button class="small-action" data-action="edit-activity" data-id="${escapeHtml(activity.id)}">Ver</button></div>`;
}

function renderProjects() {
  const projects = state.data.projects.filter((project) =>
    (state.filters.projectStatus === "Todos" || project.status === state.filters.projectStatus) &&
    matchesSearch(project.name, project.program, project.coordinator, project.unit, project.status)
  );
  return `<div class="page-heading"><div><p class="eyebrow">PESQUISA, EXTENSÃO E INOVAÇÃO</p><h1>Projetos acadêmicos</h1><p class="heading-subtitle">Organize iniciativas como PIBIC, PACE e projetos de extensão.</p></div><button class="primary-button" data-action="add-project"><span class="plus">＋</span>Novo projeto</button></div>
    <div class="toolbar"><select class="filter-select" data-filter="projectStatus" aria-label="Filtrar por situação"><option>Todos</option><option>Em andamento</option><option>Planejado</option><option>Encerrado</option><option>Pausado</option></select><span class="toolbar-spacer"></span><span class="heading-subtitle">${projects.length} ${projects.length === 1 ? "projeto" : "projetos"}</span></div>
    <div class="content-card table-wrap"><table><thead><tr><th>Projeto</th><th>Programa</th><th>Coordenação</th><th>Período</th><th>Progresso</th><th>Situação</th><th></th></tr></thead><tbody>
      ${projects.length ? projects.map((project) => `<tr><td><strong>${escapeHtml(project.name)}</strong><small>${escapeHtml(project.unit)}</small></td><td>${escapeHtml(project.program)}</td><td>${escapeHtml(project.coordinator)}</td><td>${formatDate(project.start)} – ${formatDate(project.end)}</td><td><div class="progress-wrap"><div class="progress-track"><div class="progress-fill" style="width:${Math.max(0, Math.min(100, Number(project.progress) || 0))}%"></div></div><span class="progress-value">${escapeHtml(project.progress)}%</span></div></td><td>${statusPill(project.status)}</td><td><div class="table-actions"><button class="small-action" data-action="edit-project" data-id="${escapeHtml(project.id)}">Editar</button><button class="small-action delete" data-action="delete-project" data-id="${escapeHtml(project.id)}">Excluir</button></div></td></tr>`).join("") : `<tr><td colspan="7" class="table-empty"><strong>Nenhum projeto encontrado</strong><span>Ajuste a busca ou cadastre um novo projeto.</span></td></tr>`}
    </tbody></table></div>`;
}

function renderActivities() {
  const activities = state.data.activities.filter((activity) =>
    (state.filters.activityStatus === "Todos" || activity.status === state.filters.activityStatus) &&
    matchesSearch(activity.title, activity.type, activity.status, projectById(activity.projectId)?.name, personById(activity.responsibleId)?.name)
  ).sort((a, b) => a.dueDate.localeCompare(b.dueDate));
  return `<div class="page-heading"><div><p class="eyebrow">CRONOGRAMA E ENTREGAS</p><h1>Atividades</h1><p class="heading-subtitle">Distribua responsabilidades e acompanhe os prazos dos projetos.</p></div><button class="primary-button" data-action="add-activity"><span class="plus">＋</span>Nova atividade</button></div>
    <div class="toolbar"><select class="filter-select" data-filter="activityStatus" aria-label="Filtrar por situação"><option>Todos</option><option>Pendente</option><option>Em andamento</option><option>Concluída</option></select><span class="toolbar-spacer"></span><span class="heading-subtitle">${activities.length} ${activities.length === 1 ? "atividade" : "atividades"}</span></div>
    <div class="content-card table-wrap"><table><thead><tr><th>Atividade</th><th>Projeto</th><th>Responsável</th><th>Tipo</th><th>Prazo</th><th>Situação</th><th></th></tr></thead><tbody>
      ${activities.length ? activities.map((activity) => `<tr><td><strong>${escapeHtml(activity.title)}</strong><small>${escapeHtml(activity.description || "")}</small></td><td>${escapeHtml(projectById(activity.projectId)?.name || "Projeto removido")}</td><td>${escapeHtml(personById(activity.responsibleId)?.name || "Não atribuído")}</td><td>${escapeHtml(activity.type)}</td><td>${formatDate(activity.dueDate)}</td><td>${statusPill(activity.status)}</td><td><div class="table-actions"><button class="small-action" data-action="edit-activity" data-id="${escapeHtml(activity.id)}">Editar</button><button class="small-action delete" data-action="delete-activity" data-id="${escapeHtml(activity.id)}">Excluir</button></div></td></tr>`).join("") : `<tr><td colspan="7" class="table-empty"><strong>Nenhuma atividade encontrada</strong><span>Ajuste a busca ou cadastre uma nova atividade.</span></td></tr>`}
    </tbody></table></div>`;
}

function renderPeople() {
  const people = state.data.people.filter((person) =>
    (state.filters.personRole === "Todos" || person.role === state.filters.personRole) &&
    matchesSearch(person.name, person.email, person.role, person.unit, projectById(person.projectId)?.name)
  );
  return `<div class="page-heading"><div><p class="eyebrow">EQUIPE DOS PROJETOS</p><h1>Participantes</h1><p class="heading-subtitle">Professores, alunos e voluntários envolvidos nas iniciativas.</p></div><button class="primary-button" data-action="add-person"><span class="plus">＋</span>Novo participante</button></div>
    <div class="toolbar"><select class="filter-select" data-filter="personRole" aria-label="Filtrar por perfil"><option>Todos</option><option>Professor(a)</option><option>Aluno(a)</option><option>Voluntário(a)</option></select><span class="toolbar-spacer"></span><span class="heading-subtitle">${people.length} ${people.length === 1 ? "participante" : "participantes"}</span></div>
    <div class="content-card table-wrap"><table><thead><tr><th>Nome</th><th>Perfil</th><th>E-mail</th><th>Unidade acadêmica</th><th>Projeto</th><th></th></tr></thead><tbody>
      ${people.length ? people.map((person) => `<tr><td><strong>${escapeHtml(person.name)}</strong></td><td>${escapeHtml(person.role)}</td><td>${escapeHtml(person.email)}</td><td>${escapeHtml(person.unit)}</td><td>${escapeHtml(projectById(person.projectId)?.name || "—")}</td><td><div class="table-actions"><button class="small-action" data-action="edit-person" data-id="${escapeHtml(person.id)}">Editar</button><button class="small-action delete" data-action="delete-person" data-id="${escapeHtml(person.id)}">Excluir</button></div></td></tr>`).join("") : `<tr><td colspan="6" class="table-empty"><strong>Nenhum participante encontrado</strong><span>Ajuste a busca ou cadastre um novo participante.</span></td></tr>`}
    </tbody></table></div>`;
}

function renderReports() {
  const projects = state.data.projects;
  const activities = state.data.activities;
  const completed = activities.filter((activity) => activity.status === "Concluída").length;
  const overdue = activities.filter((activity) => activity.status !== "Concluída" && activity.dueDate < dateOffset(0)).length;
  const programs = [...new Set(projects.map((project) => project.program))];
  const programCounts = programs.map((name) => ({ name, count: projects.filter((project) => project.program === name).length }));
  const maxProgram = Math.max(1, ...programCounts.map((item) => item.count));
  const roles = ["Professor(a)", "Aluno(a)", "Voluntário(a)"];
  return `<div class="page-heading"><div><p class="eyebrow">ACOMPANHAMENTO E PRESTAÇÃO DE CONTAS</p><h1>Relatórios</h1><p class="heading-subtitle">Resumo da execução dos projetos e das atividades cadastradas.</p></div><div class="button-row"><button class="secondary-button" data-action="download-backup">Backup SQLite</button><button class="secondary-button" data-action="export-csv">↧ Exportar CSV</button><button class="primary-button" data-action="print-report">▤ Imprimir relatório</button></div></div>
    <div class="report-grid">
      ${reportMetric("Projetos cadastrados", projects.length, "Iniciativas acompanhadas na plataforma", "▤")}
      ${reportMetric("Atividades concluídas", `${completed} / ${activities.length}`, `${activities.length ? Math.round(completed / activities.length * 100) : 0}% das atividades registradas`, "✓")}
      ${reportMetric("Atividades em atraso", overdue, overdue ? "Verifique os prazos com as equipes" : "Nenhuma atividade vencida", "◷")}
    </div>
    <div class="report-bottom">
      <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Projetos por programa</h2><p class="panel-subtitle">Distribuição das iniciativas cadastradas</p></div></div><div class="panel-body"><div class="bar-chart">
        ${programCounts.length ? programCounts.map((item) => `<div class="bar-row"><span class="bar-label" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span><div class="bar-track"><span style="width:${Math.round(item.count / maxProgram * 100)}%"></span></div><span class="bar-number">${item.count}</span></div>`).join("") : emptyState("Sem projetos", "Cadastre projetos para gerar o relatório.")}
      </div></div></section>
      <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Composição das equipes</h2><p class="panel-subtitle">Participantes por perfil</p></div></div><div class="panel-body">
        ${roles.map((role) => `<div class="people-summary"><span>${escapeHtml(role)}</span><strong>${state.data.people.filter((person) => person.role === role).length}</strong></div>`).join("")}
        <div class="people-summary"><span>Total de participantes</span><strong>${state.data.people.length}</strong></div>
      </div></section>
    </div>
    <section class="panel" style="margin-top:16px"><div class="panel-header"><div><h2 class="panel-title">Situação dos projetos</h2><p class="panel-subtitle">Indicadores de andamento por projeto</p></div></div><div class="table-wrap"><table><thead><tr><th>Projeto</th><th>Programa</th><th>Coordenação</th><th>Período</th><th>Progresso</th><th>Situação</th></tr></thead><tbody>
      ${projects.length ? projects.map((project) => `<tr><td><strong>${escapeHtml(project.name)}</strong></td><td>${escapeHtml(project.program)}</td><td>${escapeHtml(project.coordinator)}</td><td>${formatDate(project.start)} – ${formatDate(project.end)}</td><td>${escapeHtml(project.progress)}%</td><td>${statusPill(project.status)}</td></tr>`).join("") : `<tr><td colspan="6" class="table-empty"><strong>Sem projetos para exibir</strong><span>Cadastre projetos para gerar os indicadores.</span></td></tr>`}
    </tbody></table></div></section>`;
}

function reportMetric(label, value, note, icon) {
  return `<article class="stat-card report-card"><div class="stat-top"><span>${escapeHtml(label)}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${escapeHtml(value)}</div><div class="stat-note">${escapeHtml(note)}</div></article>`;
}

function openModal({ title, subtitle, fields, values = {}, entity, id = "" }) {
  const fieldHtml = fields.map((field) => {
    const value = values[field.name] ?? field.default ?? "";
    let control;
    if (field.type === "multi") {
      const selected = Array.isArray(value) ? value : [];
      control = `<select id="field-${field.name}" name="${field.name}" multiple size="4">${state.data.people.map((person) =>
        `<option value="${escapeHtml(person.id)}" ${selected.includes(person.id) ? "selected" : ""}>${escapeHtml(person.name)} — ${escapeHtml(person.role)}</option>`
      ).join("")}</select><small class="field-help">Segure Ctrl (Windows) para selecionar mais de uma pessoa.</small>`;
    } else if (field.type === "select") {
      const options = field.options ? field.options.map((option) => {
        const optionValue = typeof option === "string" ? option : option.value;
        const label = typeof option === "string" ? option : option.label;
        return `<option value="${escapeHtml(optionValue)}" ${String(optionValue) === String(value) ? "selected" : ""}>${escapeHtml(label)}</option>`;
      }).join("") : field.name === "projectId" ? projectOptions(value) : personOptions(value);
      control = `<select id="field-${field.name}" name="${field.name}" ${field.required === false ? "" : "required"}>${field.required === false ? `<option value="" ${!value ? "selected" : ""}>${escapeHtml(field.placeholder || "Nenhum")}</option>` : ""}${options}</select>`;
    } else if (field.type === "textarea") {
      control = `<textarea id="field-${field.name}" name="${field.name}" placeholder="${escapeHtml(field.placeholder || "")}">${escapeHtml(value)}</textarea>`;
    } else {
      control = `<input id="field-${field.name}" name="${field.name}" type="${escapeHtml(field.type || "text")}" value="${escapeHtml(value)}" ${field.required === false ? "" : "required"} ${field.min !== undefined ? `min="${field.min}"` : ""} ${field.max !== undefined ? `max="${field.max}"` : ""} ${field.step ? `step="${field.step}"` : ""} placeholder="${escapeHtml(field.placeholder || "")}">`;
    }
    return `<div class="form-field ${field.full ? "full" : ""}"><label for="field-${field.name}">${escapeHtml(field.label)}</label>${control}</div>`;
  }).join("");
  document.getElementById("modal-root").innerHTML = `<div class="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><header class="modal-header"><div><h2 id="modal-title">${escapeHtml(title)}</h2><p>${escapeHtml(subtitle)}</p></div><button type="button" class="modal-close" data-action="close-modal" aria-label="Fechar">×</button></header>
    <form class="modal-form" data-entity="${escapeHtml(entity)}" data-id="${escapeHtml(id)}"><div class="form-grid">${fieldHtml}</div><div class="modal-actions">${entity === "events" && id ? `<button type="button" class="danger-button" data-action="delete-event" data-id="${escapeHtml(id)}">Excluir</button>` : ""}<button type="button" class="secondary-button" data-action="close-modal">Cancelar</button><button type="submit" class="primary-button">Salvar</button></div></form></section></div>`;
  const firstInput = document.querySelector(".modal-form input, .modal-form select");
  if (firstInput) firstInput.focus();
}

function projectFields() {
  return [
    { name: "name", label: "Nome do projeto", full: true, placeholder: "Título da iniciativa" },
    { name: "program", label: "Programa", type: "select", options: ["PIBIC", "PIBITI", "PACE", "Extensão", "PET", "Outro"] },
    { name: "status", label: "Situação", type: "select", options: ["Planejado", "Em andamento", "Pausado", "Encerrado"], default: "Planejado" },
    { name: "coordinator", label: "Professor(a) responsável" },
    { name: "unit", label: "Unidade acadêmica" },
    { name: "start", label: "Data de início", type: "date" },
    { name: "end", label: "Data de término", type: "date" },
    { name: "progress", label: "Progresso (%)", type: "number", min: 0, max: 100, default: 0 },
    { name: "description", label: "Descrição", type: "textarea", full: true, required: false, placeholder: "Objetivos, escopo ou observações do projeto" }
  ];
}

function activityFields() {
  return [
    { name: "title", label: "Nome da atividade", full: true, placeholder: "Ex.: Entrega do relatório parcial" },
    { name: "projectId", label: "Projeto", type: "select" },
    { name: "responsibleId", label: "Responsável", type: "select", required: false },
    { name: "type", label: "Tipo", type: "select", options: ["Pesquisa", "Extensão", "Relatório", "Reunião", "Formação", "Outro"] },
    { name: "status", label: "Situação", type: "select", options: ["Pendente", "Em andamento", "Concluída"], default: "Pendente" },
    { name: "dueDate", label: "Prazo", type: "date" },
    { name: "description", label: "Descrição", type: "textarea", full: true, required: false, placeholder: "Detalhes e entregáveis esperados" }
  ];
}

function personFields() {
  return [
    { name: "name", label: "Nome completo" },
    { name: "role", label: "Perfil", type: "select", options: ["Professor(a)", "Aluno(a)", "Voluntário(a)"] },
    { name: "email", label: "E-mail institucional", type: "email" },
    { name: "unit", label: "Unidade acadêmica" },
    { name: "projectId", label: "Projeto vinculado", type: "select", required: false },
  ];
}

function eventFields(values = {}) {
  const defaultStart = values.startAt || localDateTime(new Date(`${values.selectedDate || dateOffset(0)}T09:00:00`));
  const defaultEnd = values.endAt || localDateTime(new Date(new Date(defaultStart).getTime() + 60 * 60 * 1000));
  return [
    { name: "title", label: "Título do compromisso", full: true, placeholder: "Ex.: Reunião de orientação" },
    { name: "type", label: "Tipo", type: "select", options: ["Reunião", "Orientação", "Atividade de campo", "Apresentação", "Entrega", "Outro"], default: "Reunião" },
    { name: "status", label: "Situação", type: "select", options: ["Agendado", "Realizado", "Cancelado"], default: "Agendado" },
    { name: "startAt", label: "Início", type: "datetime-local", default: defaultStart },
    { name: "endAt", label: "Término", type: "datetime-local", default: defaultEnd },
    { name: "projectId", label: "Projeto relacionado", type: "select", required: false },
    { name: "activityId", label: "Atividade relacionada", type: "select", options: state.data.activities.map((activity) => ({ value: activity.id, label: activity.title })), required: false },
    { name: "responsibleId", label: "Responsável", type: "select", required: false },
    { name: "participantIds", label: "Participantes convidados", type: "multi", full: true, required: false },
    { name: "location", label: "Local ou link", full: true, placeholder: "Sala, campus ou endereço da reunião on-line", required: false },
    { name: "reminderMinutes", label: "Lembrete", type: "select", options: [{ value: "0", label: "Sem lembrete" }, { value: "10", label: "10 minutos antes" }, { value: "30", label: "30 minutos antes" }, { value: "60", label: "1 hora antes" }, { value: "1440", label: "1 dia antes" }], required: false },
    { name: "description", label: "Observações", type: "textarea", full: true, required: false, placeholder: "Pauta, preparação ou informações adicionais" }
  ];
}

function showEntityModal(entity, id = "") {
  const collection = state.data[entity];
  const current = id ? collection.find((item) => item.id === id) : null;
  const configs = {
    projects: { title: current ? "Editar projeto" : "Novo projeto", subtitle: "Preencha as informações para acompanhamento acadêmico.", fields: projectFields() },
    activities: { title: current ? "Editar atividade" : "Nova atividade", subtitle: "Defina o prazo, o projeto e a pessoa responsável.", fields: activityFields() },
    people: { title: current ? "Editar participante" : "Novo participante", subtitle: "Cadastre um integrante e vincule-o a um projeto.", fields: personFields() },
    events: { title: current ? "Editar compromisso" : "Novo compromisso", subtitle: "Agende reuniões, orientações e atividades dos projetos.", fields: eventFields(current || {}) }
  };
  const config = configs[entity];
  if (!config) return;
  openModal({ ...config, values: current || {}, entity, id });
}

function showEventModal(id = "", selectedDate = "") {
  const current = id ? state.data.events.find((event) => event.id === id) : null;
  openModal({
    title: current ? "Editar compromisso" : "Novo compromisso",
    subtitle: "Agende reuniões, orientações e atividades dos projetos.",
    fields: eventFields({ ...(current || {}), selectedDate }),
    values: current || { selectedDate },
    entity: "events",
    id
  });
}

function toast(message, error = false) {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const item = document.createElement("div");
  item.className = `toast${error ? " error" : ""}`;
  item.textContent = message;
  root.appendChild(item);
  setTimeout(() => item.remove(), 3600);
}

async function deleteRecord(entity, id) {
  const record = state.data[entity].find((item) => item.id === id);
  if (!record) return;
  const names = { projects: "projeto", activities: "atividade", people: "participante", events: "compromisso" };
  if (!window.confirm(`Deseja excluir ${names[entity]} "${record.name || record.title}"?`)) return;
  try {
    await apiRequest(`/api/${entity}/${encodeURIComponent(id)}`, { method: "DELETE" });
    document.getElementById("modal-root").innerHTML = "";
    await refreshData();
    toast(`${names[entity][0].toLocaleUpperCase("pt-BR") + names[entity].slice(1)} excluído(a).`);
  } catch (error) {
    toast(`Não foi possível excluir: ${error.message}`, true);
  }
}

function csvEscape(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function downloadCsv() {
  const rows = [
    ["Projeto", "Programa", "Coordenação", "Unidade", "Início", "Término", "Situação", "Progresso", "Atividades", "Concluídas", "Participantes"],
    ...state.data.projects.map((project) => {
      const activities = state.data.activities.filter((item) => item.projectId === project.id);
      const people = state.data.people.filter((item) => item.projectId === project.id);
      return [project.name, project.program, project.coordinator, project.unit, project.start, project.end, project.status, `${project.progress}%`, activities.length, activities.filter((item) => item.status === "Concluída").length, people.length];
    })
  ];
  const csv = "\uFEFF" + rows.map((row) => row.map(csvEscape).join(";")).join("\r\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  link.download = "relatorio-e-project-ufam.csv";
  link.click();
  URL.revokeObjectURL(link.href);
  toast("Relatório CSV exportado.");
}

function downloadSummary() {
  const lines = [
    ["Indicador", "Quantidade"],
    ["Projetos", state.data.projects.length],
    ["Projetos em andamento", state.data.projects.filter((item) => item.status === "Em andamento").length],
    ["Atividades", state.data.activities.length],
    ["Atividades concluídas", state.data.activities.filter((item) => item.status === "Concluída").length],
    ["Participantes", state.data.people.length],
    ["Compromissos agendados", state.data.events.filter((item) => item.status === "Agendado").length]
  ];
  const csv = "\uFEFF" + lines.map((row) => row.map(csvEscape).join(";")).join("\r\n");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  link.download = "resumo-e-project-ufam.csv";
  link.click();
  URL.revokeObjectURL(link.href);
  toast("Resumo exportado.");
}

function downloadCalendarIcs() {
  const month = new Date(state.calendarMonth);
  const monthStart = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}-01`;
  const monthEnd = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}-${String(new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()).padStart(2, "0")}`;
  const events = state.data.events.filter((event) =>
    event.startAt.slice(0, 10) >= monthStart && event.startAt.slice(0, 10) <= monthEnd &&
    event.status !== "Cancelado"
  );
  const escapeIcs = (value) => String(value || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
  const toIcsDate = (value) => value.replace(/[-:]/g, "").slice(0, 15) + "00";
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//E-project UFAM//Agenda//PT-BR", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"];
  for (const event of events) {
    lines.push(
      "BEGIN:VEVENT",
      `UID:${escapeIcs(event.id)}@eproject.local`,
      `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "")}`,
      `DTSTART:${toIcsDate(event.startAt)}`,
      `DTEND:${toIcsDate(event.endAt)}`,
      `SUMMARY:${escapeIcs(event.title)}`,
      `DESCRIPTION:${escapeIcs(event.description)}`,
      `LOCATION:${escapeIcs(event.location)}`,
      "END:VEVENT"
    );
  }
  lines.push("END:VCALENDAR");
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([lines.join("\r\n")], { type: "text/calendar;charset=utf-8" }));
  link.download = `e-project-agenda-${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}.ics`;
  link.click();
  URL.revokeObjectURL(link.href);
  toast(`${events.length} ${events.length === 1 ? "compromisso exportado" : "compromissos exportados"} para o calendário.`);
}

async function downloadDatabaseBackup() {
  try {
    const response = await fetch("/api/backup");
    if (!response.ok) {
      let message = `Não foi possível gerar o backup (HTTP ${response.status}).`;
      try {
        const result = await response.json();
        if (result.error) message = result.error;
      } catch (error) {
        console.error("O servidor retornou uma resposta de backup inválida.", error);
      }
      throw new Error(message);
    }
    const link = document.createElement("a");
    link.href = URL.createObjectURL(await response.blob());
    link.download = "eproject-backup.sqlite3";
    link.click();
    URL.revokeObjectURL(link.href);
    toast("Backup do banco SQLite baixado.");
  } catch (error) {
    toast(`Não foi possível baixar o backup: ${error.message}`, true);
  }
}

function enableReminders() {
  if (!("Notification" in window)) {
    toast("Este navegador não oferece suporte a notificações.", true);
    return;
  }
  Notification.requestPermission().then((permission) => {
    if (permission === "granted") {
      toast("Lembretes ativados. Mantenha a aplicação aberta para recebê-los.");
      checkReminders();
    } else {
      toast("Permita as notificações nas configurações do navegador para ativar os lembretes.", true);
    }
  }).catch((error) => toast(`Não foi possível ativar os lembretes: ${error.message}`, true));
}

function checkReminders() {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const now = Date.now();
  let notified;
  try {
    notified = JSON.parse(localStorage.getItem("eproject-notified-reminders") || "{}");
  } catch (error) {
    console.error("O histórico local de lembretes não pôde ser lido.", error);
    notified = {};
  }
  let changed = false;
  for (const event of state.data.events) {
    if (event.status !== "Agendado" || !event.reminderMinutes) continue;
    const startsAt = new Date(event.startAt).getTime();
    const reminderAt = startsAt - event.reminderMinutes * 60_000;
    const reminderKey = `${event.id}:${event.startAt}`;
    if (!Number.isFinite(startsAt) || reminderAt > now || reminderAt + 60_000 < now || notified[reminderKey]) continue;
    new Notification(`Lembrete: ${event.title}`, {
      body: `${formatDate(event.startAt.slice(0, 10))} às ${event.startAt.slice(11, 16)}${event.location ? ` · ${event.location}` : ""}`,
      tag: reminderKey
    });
    notified[reminderKey] = true;
    changed = true;
  }
  if (changed) localStorage.setItem("eproject-notified-reminders", JSON.stringify(notified));
}

document.addEventListener("click", (event) => {
  if (event.target.classList.contains("modal-backdrop")) {
    document.getElementById("modal-root").innerHTML = "";
    return;
  }
  const target = event.target.closest("[data-action], [data-view], .nav-item");
  if (!target) return;
  if (target.dataset.view) {
    state.view = target.dataset.view;
    document.getElementById("sidebar").classList.remove("open");
    render();
    return;
  }
  const { action, id } = target.dataset;
  if (action === "retry-connection") void startApplication();
  if (action === "add-project") showEntityModal("projects");
  else if (action === "add-activity") {
    if (!state.data.projects.length) return toast("Cadastre um projeto antes de adicionar atividades.", true);
    showEntityModal("activities");
  } else if (action === "add-person") showEntityModal("people");
  else if (action === "add-event") showEventModal();
  else if (action === "add-event-date") showEventModal("", target.dataset.date);
  else if (action === "edit-project") showEntityModal("projects", id);
  else if (action === "edit-activity") showEntityModal("activities", id);
  else if (action === "edit-person") showEntityModal("people", id);
  else if (action === "edit-event") showEventModal(id);
  else if (action === "delete-project") void deleteRecord("projects", id);
  else if (action === "delete-activity") void deleteRecord("activities", id);
  else if (action === "delete-person") void deleteRecord("people", id);
  else if (action === "delete-event") void deleteRecord("events", id);
  else if (action === "calendar-prev") { state.calendarMonth.setMonth(state.calendarMonth.getMonth() - 1); render(); }
  else if (action === "calendar-next") { state.calendarMonth.setMonth(state.calendarMonth.getMonth() + 1); render(); }
  else if (action === "calendar-today") { state.calendarMonth = new Date(today.getFullYear(), today.getMonth(), 1); render(); }
  else if (action === "calendar-mode") { state.calendarMode = target.dataset.mode; render(); }
  else if (action === "enable-reminders") enableReminders();
  else if (action === "close-modal" && (target.classList.contains("modal-close") || target.classList.contains("secondary-button"))) document.getElementById("modal-root").innerHTML = "";
  else if (action === "export-csv") downloadCsv();
  else if (action === "export-calendar") downloadCalendarIcs();
  else if (action === "download-backup") void downloadDatabaseBackup();
  else if (action === "export-summary") downloadSummary();
  else if (action === "print-report") window.print();
  else if (target.id === "mobile-menu") document.getElementById("sidebar").classList.toggle("open");
});

document.addEventListener("submit", (event) => {
  const form = event.target.closest(".modal-form");
  if (!form) return;
  event.preventDefault();
  const { entity, id } = form.dataset;
  const formData = new FormData(form);
  const values = Object.fromEntries(formData.entries());
  if (form.elements.participantIds) values.participantIds = formData.getAll("participantIds");
  if (entity === "projects") values.progress = Math.max(0, Math.min(100, Number(values.progress) || 0));
  if (entity === "events") values.reminderMinutes = Number(values.reminderMinutes || 0);
  const saveButton = form.querySelector('[type="submit"]');
  saveButton.disabled = true;
  const saveLabel = saveButton.textContent;
  saveButton.textContent = "Salvando...";
  const request = id
    ? apiRequest(`/api/${entity}/${encodeURIComponent(id)}`, { method: "PUT", body: values })
    : apiRequest(`/api/${entity}`, { method: "POST", body: values });
  request.then(refreshData).then(() => {
    document.getElementById("modal-root").innerHTML = "";
    render();
    toast(id ? "Alterações salvas com sucesso." : "Cadastro realizado com sucesso.");
  }).catch((error) => {
    toast(`Não foi possível salvar: ${error.message}`, true);
    saveButton.disabled = false;
    saveButton.textContent = saveLabel;
  });
});

document.addEventListener("change", (event) => {
  if (event.target.dataset.filter) {
    state.filters[event.target.dataset.filter] = event.target.value;
    render();
  }
});

document.getElementById("global-search").addEventListener("input", (event) => {
  state.search = event.target.value;
  render();
});

document.getElementById("mobile-menu").addEventListener("click", () => {
  document.getElementById("sidebar").classList.toggle("open");
});

render();
void startApplication();
