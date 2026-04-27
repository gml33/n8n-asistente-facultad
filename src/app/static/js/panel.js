// Estado global del panel para filtros, datos y componentes UI.
const estado = {
  filtro: "pendientes",
  entregas: [],
  materias: [],
  calendario: null,
  modal: null,
  modalMateria: null,
  modalDetalleCalendario: null,
  entregaSeleccionadaCalendario: null,
};

// Convierte timestamp ISO a objeto Date.
function parsearFecha(valor) {
  return new Date(valor);
}

// Wrapper para obtener "ahora" y facilitar futuras pruebas/mocks.
function ahora() {
  return new Date();
}

// Define si una entrega es pendiente y todavía no venció.
function esFuturaPendiente(entrega) {
  return entrega.estado !== "entregado" && parsearFecha(entrega.fecha_entrega) >= ahora();
}

// Define si una entrega ya quedó en el pasado.
function esAnterior(entrega) {
  return parsearFecha(entrega.fecha_entrega) < ahora();
}

// Define si una entrega sigue pendiente (futura o vencida).
function esPendiente(entrega) {
  return entrega.estado !== "entregado";
}

// Aplica filtro activo seleccionado por el usuario.
function obtenerEntregasFiltradas() {
  if (estado.filtro === "pendientes") return estado.entregas.filter(esPendiente);
  if (estado.filtro === "futuras") return estado.entregas.filter(esFuturaPendiente);
  if (estado.filtro === "anteriores") return estado.entregas.filter(esAnterior);
  if (estado.filtro === "entregadas") return estado.entregas.filter((entrega) => entrega.estado === "entregado");
  return estado.entregas;
}

// Recalcula métricas superiores del dashboard.
function actualizarMetricas() {
  const futuras = estado.entregas.filter(esFuturaPendiente).length;
  const vencidas = estado.entregas.filter(
    (entrega) => entrega.estado !== "entregado" && parsearFecha(entrega.fecha_entrega) < ahora(),
  ).length;
  const entregadas = estado.entregas.filter((entrega) => entrega.estado === "entregado").length;
  const campus = estado.entregas.filter((entrega) => entrega.origen === "campus").length;

  document.getElementById("metrica-futuras").textContent = futuras;
  document.getElementById("metrica-vencidas").textContent = vencidas;
  document.getElementById("metrica-entregadas").textContent = entregadas;
  document.getElementById("metrica-campus").textContent = campus;
}

// Mapea estado de negocio a clase visual del badge.
function badgeEstadoClase(estadoEntrega) {
  return estadoEntrega === "entregado" ? "estado-entregado" : "estado-pendiente";
}

// Define color de evento en calendario según prioridad/estado.
function colorEvento(entrega) {
  if (entrega.estado === "entregado") return "#61c796";
  if (entrega.prioridad === "alta") return "#dc3545";
  if (entrega.prioridad === "media") return "#44a3a8";
  return "#2f6488";
}

// Muestra modal con detalle de la entrega clickeada en calendario.
function abrirDetalleCalendario(entrega) {
  if (!entrega) return;

  // Fallback defensivo: si el modal Bootstrap no está listo, muestra SweetAlert.
  if (!estado.modalDetalleCalendario) {
    Swal.fire({
      title: entrega.titulo || "Detalle de entrega",
      html: `
        <div style="text-align:left">
          <p><strong>Materia:</strong> ${entrega.materia || "-"}</p>
          <p><strong>Tipo:</strong> ${entrega.tipo || "-"}</p>
          <p><strong>Fecha:</strong> ${new Date(entrega.fecha_entrega).toLocaleString("es-AR")}</p>
          <p><strong>Prioridad:</strong> ${entrega.prioridad || "-"}</p>
          <p><strong>Estado:</strong> ${entrega.estado || "-"}</p>
          <p><strong>Origen:</strong> ${entrega.origen || "-"}</p>
          <p><strong>Nota:</strong> ${entrega.nota ?? "-"}</p>
          <p><strong>Detalle:</strong> ${entrega.detalle || "Sin detalle cargado."}</p>
        </div>
      `,
      icon: "info",
    });
    return;
  }

  estado.entregaSeleccionadaCalendario = entrega;
  document.getElementById("detalle-cal-titulo").textContent = entrega.titulo || "-";
  document.getElementById("detalle-cal-materia").textContent = entrega.materia || "-";
  document.getElementById("detalle-cal-tipo").textContent = entrega.tipo || "-";
  document.getElementById("detalle-cal-fecha").textContent = new Date(entrega.fecha_entrega).toLocaleString("es-AR");
  document.getElementById("detalle-cal-prioridad").textContent = entrega.prioridad || "-";
  document.getElementById("detalle-cal-estado").textContent = entrega.estado || "-";
  document.getElementById("detalle-cal-origen").textContent = entrega.origen || "-";
  document.getElementById("detalle-cal-nota").textContent = entrega.nota ?? "-";
  document.getElementById("detalle-cal-detalle").textContent = entrega.detalle || "Sin detalle cargado.";

  estado.modalDetalleCalendario.show();
}

// Renderiza o refresca FullCalendar con entregas actuales.
function renderizarCalendario() {
  const eventos = estado.entregas.map((entrega) => ({
    id: String(entrega.id),
    title: `${entrega.materia} · ${entrega.titulo}`,
    start: entrega.fecha_entrega,
    allDay: false,
    backgroundColor: colorEvento(entrega),
    borderColor: colorEvento(entrega),
    extendedProps: { entregaId: String(entrega.id), entrega },
  }));

  if (!estado.calendario) {
    estado.calendario = new FullCalendar.Calendar(document.getElementById("calendario-entregas"), {
      locale: "es",
      initialView: "dayGridMonth",
      height: "auto",
      headerToolbar: {
        left: "prev,next today",
        center: "title",
        right: "dayGridMonth,timeGridWeek,listWeek",
      },
      events: eventos,
      eventDidMount: (info) => {
        info.el.style.cursor = "pointer";
      },
      eventClick: (info) => {
        info.jsEvent?.preventDefault();

        const entregaDesdeEvento = info.event.extendedProps?.entrega;
        const entregaId = info.event.extendedProps?.entregaId || info.event.id;
        let entrega =
          entregaDesdeEvento ||
          estado.entregas.find((item) => String(item.id) === String(entregaId));

        // Fallback por fecha+título cuando el ID no coincide.
        if (!entrega) {
          const inicioEvento = info.event.start ? new Date(info.event.start).getTime() : null;
          entrega = estado.entregas.find((item) => {
            const mismoTitulo = `${item.materia} · ${item.titulo}` === info.event.title;
            const mismaFecha =
              inicioEvento !== null &&
              Math.abs(new Date(item.fecha_entrega).getTime() - inicioEvento) < 60 * 1000;
            return mismoTitulo || mismaFecha;
          });
        }

        if (entrega) abrirDetalleCalendario(entrega);
      },
    });
    estado.calendario.render();
    return;
  }

  estado.calendario.removeAllEvents();
  eventos.forEach((evento) => estado.calendario.addEvent(evento));
}

// Limpia todos los campos del modal para un alta nueva.
function limpiarFormulario() {
  document.getElementById("campo-id").value = "";
  document.getElementById("campo-materia").value = estado.materias[0]?.nombre || "";
  document.getElementById("campo-titulo").value = "";
  document.getElementById("campo-tipo").value = "trabajo practico";
  document.getElementById("campo-fecha").value = "";
  document.getElementById("campo-hora").value = "23:59";
  document.getElementById("campo-prioridad").value = "media";
  document.getElementById("campo-estado").value = "pendiente";
  document.getElementById("campo-detalle").value = "";
  document.getElementById("campo-nota").value = "";
}

// Asigna valor evitando null/undefined en inputs.
function setValor(id, valor) {
  document.getElementById(id).value = valor ?? "";
}

// Fetch JSON con manejo de sesión expirada.
async function fetchJson(url, options) {
  const respuesta = await fetch(url, options);
  if (respuesta.status === 401) {
    window.location.href = "/login";
    throw new Error("Sesión expirada.");
  }
  const data = await respuesta.json();
  return { respuesta, data };
}

// Abre modal de alta, validando que existan materias.
function abrirModalCrear() {
  if (!estado.modal) return;
  if (!estado.materias.length) {
    Swal.fire({
      icon: "info",
      title: "Sin materias",
      text: "Primero cargá materias desde Telegram o la API para crear una entrega.",
    });
    return;
  }
  limpiarFormulario();
  document.getElementById("titulo-modal-entrega").textContent = "Nueva entrega";
  estado.modal.show();
}

// Abre modal en modo edición y precarga datos de la entrega.
function abrirModalEditar(entrega) {
  if (!estado.modal) return;
  const fecha = parsearFecha(entrega.fecha_entrega);
  setValor("campo-id", entrega.id);
  if (!estado.materias.some((materia) => materia.nombre === entrega.materia)) {
    estado.materias.push({ nombre: entrega.materia });
    poblarSelectMaterias();
  }
  setValor("campo-materia", entrega.materia);
  setValor("campo-titulo", entrega.titulo);
  setValor("campo-tipo", entrega.tipo);
  setValor("campo-fecha", fecha.toISOString().slice(0, 10));
  setValor("campo-hora", `${String(fecha.getHours()).padStart(2, "0")}:${String(fecha.getMinutes()).padStart(2, "0")}`);
  setValor("campo-prioridad", entrega.prioridad);
  setValor("campo-estado", entrega.estado);
  setValor("campo-detalle", entrega.detalle || "");
  setValor("campo-nota", entrega.nota ?? "");
  document.getElementById("titulo-modal-entrega").textContent = `Editar entrega #${entrega.id}`;
  estado.modal.show();
}

// Construye payload JSON desde formulario con validaciones mínimas.
function obtenerPayloadFormulario() {
  const fecha = document.getElementById("campo-fecha").value;
  const hora = document.getElementById("campo-hora").value;
  if (!fecha || !hora) throw new Error("Completá fecha y hora.");

  const fechaEntrega = new Date(`${fecha}T${hora}:00`);
  if (Number.isNaN(fechaEntrega.getTime())) throw new Error("Fecha u hora inválida.");

  const notaRaw = document.getElementById("campo-nota").value.trim();
  return {
    materia: document.getElementById("campo-materia").value,
    titulo: document.getElementById("campo-titulo").value.trim(),
    tipo: document.getElementById("campo-tipo").value,
    fecha_entrega: fechaEntrega.toISOString().slice(0, 19),
    prioridad: document.getElementById("campo-prioridad").value,
    estado: document.getElementById("campo-estado").value,
    detalle: document.getElementById("campo-detalle").value.trim() || null,
    nota: notaRaw ? Number(notaRaw) : null,
  };
}

// Crea o actualiza entrega según presencia de ID oculto.
async function guardarEntrega(evento) {
  evento.preventDefault();
  if (!estado.modal) return;
  try {
    const id = document.getElementById("campo-id").value;
    const payload = obtenerPayloadFormulario();
    const url = id ? `/api/entregas/${id}` : "/api/entregas";
    const metodo = id ? "PUT" : "POST";

    const { respuesta, data } = await fetchJson(url, {
      method: metodo,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!respuesta.ok) throw new Error(data.error || "No se pudo guardar la entrega.");

    estado.modal.hide();
    await cargarEntregas();
    Swal.fire({
      icon: "success",
      title: id ? "Entrega actualizada" : "Entrega creada",
      timer: 1300,
      showConfirmButton: false,
    });
  } catch (error) {
    Swal.fire({
      icon: "error",
      title: "No se pudo guardar",
      text: error.message || "Error inesperado.",
    });
  }
}

// Crea materia desde modal y refresca selector de entregas.
async function guardarMateria(evento) {
  evento.preventDefault();
  if (!estado.modalMateria) return;

  const campo = document.getElementById("campo-materia-nueva");
  const nombre = (campo.value || "").trim();
  if (!nombre) {
    Swal.fire({ icon: "warning", title: "Nombre requerido", text: "Ingresá un nombre de materia válido." });
    return;
  }

  const { respuesta, data } = await fetchJson("/api/materias", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nombre }),
  });
  if (!respuesta.ok) {
    Swal.fire({ icon: "error", title: "No se pudo crear", text: data.error || "Error al guardar materia." });
    return;
  }

  campo.value = "";
  estado.modalMateria.hide();
  await cargarMaterias();
  document.getElementById("campo-materia").value = data.nombre;
  Swal.fire({ icon: "success", title: "Materia creada", timer: 1200, showConfirmButton: false });
}

// Elimina entrega tras confirmación explícita del usuario.
async function eliminarEntrega(id) {
  const confirmacion = await Swal.fire({
    icon: "warning",
    title: "Eliminar entrega",
    text: "Esta acción no se puede deshacer.",
    showCancelButton: true,
    confirmButtonText: "Sí, eliminar",
    cancelButtonText: "Cancelar",
    confirmButtonColor: "#dc3545",
  });

  if (!confirmacion.isConfirmed) return;

  const { respuesta, data } = await fetchJson(`/api/entregas/${id}`, { method: "DELETE" });
  if (!respuesta.ok) throw new Error(data.error || "No se pudo eliminar.");
}

// Dibuja tarjetas Bootstrap en base al filtro activo.
function renderizarTarjetas() {
  const contenedor = document.getElementById("contenedor-entregas");
  const template = document.getElementById("template-entrega");
  contenedor.innerHTML = "";

  const items = obtenerEntregasFiltradas().sort(
    (a, b) => parsearFecha(a.fecha_entrega) - parsearFecha(b.fecha_entrega),
  );

  if (!items.length) {
    contenedor.innerHTML =
      '<div class="col-12"><div class="alert alert-light border mb-0">Sin entregas para este filtro.</div></div>';
    return;
  }

  items.forEach((entrega) => {
    const nodo = template.content.cloneNode(true);
    nodo.querySelector(".titulo-entrega").textContent = entrega.titulo;
    nodo.querySelector(".materia-entrega").textContent = entrega.materia;
    nodo.querySelector(".tipo-entrega").textContent = `Tipo: ${entrega.tipo}`;
    nodo.querySelector(".fecha-entrega").textContent =
      `Entrega: ${new Date(entrega.fecha_entrega).toLocaleString("es-AR")}`;
    nodo.querySelector(".prioridad-entrega").textContent = `Prioridad: ${entrega.prioridad}`;
    nodo.querySelector(".origen-entrega").textContent = `Origen: ${entrega.origen}`;

    const badgeEstado = nodo.querySelector(".badge-estado");
    badgeEstado.textContent = entrega.estado;
    badgeEstado.classList.add(badgeEstadoClase(entrega.estado));

    const detalle = nodo.querySelector(".detalle-entrega");
    detalle.textContent = entrega.detalle || "Sin detalle cargado.";
    detalle.classList.remove("d-none");

    const tarjeta = nodo.querySelector(".tarjeta-entrega");
    tarjeta.classList.add(`prioridad-${entrega.prioridad}`);

    const botonEditar = nodo.querySelector(".boton-editar");
    botonEditar.addEventListener("click", () => abrirModalEditar(entrega));

    const botonEliminar = nodo.querySelector(".boton-eliminar");
    botonEliminar.addEventListener("click", async () => {
      try {
        await eliminarEntrega(entrega.id);
        await cargarEntregas();
        Swal.fire({ icon: "success", title: "Entrega eliminada", timer: 1200, showConfirmButton: false });
      } catch (error) {
        Swal.fire({ icon: "error", title: "Error al eliminar", text: error.message || "Error inesperado." });
      }
    });

    contenedor.appendChild(nodo);
  });
}

// Obtiene entregas desde API y refresca todas las vistas dependientes.
async function cargarEntregas() {
  const { respuesta, data } = await fetchJson("/api/entregas");
  if (!respuesta.ok) throw new Error(data.error || "No se pudo cargar entregas");
  estado.entregas = data;
  actualizarMetricas();
  renderizarTarjetas();
  renderizarCalendario();
}

// Obtiene materias para poblar selector del modal.
async function cargarMaterias() {
  const { respuesta, data } = await fetchJson("/api/materias");
  if (!respuesta.ok) throw new Error(data.error || "No se pudo cargar materias");
  estado.materias = data;
  poblarSelectMaterias();
}

// Garantiza que el select de zona horaria acepte valores persistidos no listados.
function seleccionarZonaHoraria(valorZona) {
  const select = document.getElementById("cfg-zona-horaria");
  if (!select) return;

  const valor = (valorZona || "America/Argentina/Buenos_Aires").trim();
  const existe = Array.from(select.options).some((opcion) => opcion.value === valor);
  if (!existe) {
    const opcion = document.createElement("option");
    opcion.value = valor;
    opcion.textContent = valor;
    select.appendChild(opcion);
  }
  select.value = valor;
}

// Carga configuración global editable desde el panel.
async function cargarConfiguracionSistema() {
  const { respuesta, data: config } = await fetchJson("/api/configuracion/sistema");
  if (!respuesta.ok) throw new Error(config.error || "No se pudo cargar la configuración del sistema");
  document.getElementById("cfg-token-telegram").value = config.telegram_bot_token || "";
  document.getElementById("cfg-chat-id").value = config.telegram_chat_id || "";
  document.getElementById("cfg-notif-activas").value = String(config.notificaciones_activas);
  document.getElementById("cfg-notif-hora").value = config.notificacion_hora || "08:00";
  document.getElementById("cfg-notif-frecuencia-horas").value = config.notificacion_frecuencia_horas || 24;
  document.getElementById("cfg-notif-ventana").value = config.notificacion_ventana_dias || 7;
  seleccionarZonaHoraria(config.zona_horaria || "America/Argentina/Buenos_Aires");
  document.getElementById("cfg-modo-bot").value = config.modo_bot || "long_polling";
  document.getElementById("cfg-sync-activa").value = String(config.sincronizacion_campus_activa);
  document.getElementById("cfg-sync-minutos").value = config.minutos_sincronizacion_campus || 30;
  document.getElementById("cfg-campus-url").value = config.campus_calendario_url || "";
  await cargarEstadoVinculacionTelegram();
}

async function cargarEstadoVinculacionTelegram() {
  const caja = document.getElementById("estado-vinculacion-telegram");
  const { respuesta, data } = await fetchJson("/api/telegram/vinculacion");
  if (!respuesta.ok) {
    caja.textContent = "Telegram: no se pudo verificar estado.";
    return;
  }
  if (data.telegram_vinculado) {
    caja.textContent = `Telegram vinculado. Chat ID: ${data.telegram_chat_id}`;
    return;
  }
  if (data.telegram_codigo_pendiente && data.telegram_codigo_expira_en) {
    caja.textContent = `Telegram no vinculado. Código pendiente: ${data.telegram_codigo_pendiente} (expira ${new Date(data.telegram_codigo_expira_en).toLocaleString("es-AR")})`;
    return;
  }
  caja.textContent = "Telegram no vinculado. Generá un código y enviá /vincular CODIGO en el bot.";
}

async function cargarUsuariosAdmin() {
  const tabla = document.getElementById("tabla-usuarios-admin");
  if (!tabla) return;
  const { respuesta, data } = await fetchJson("/api/admin/usuarios");
  if (!respuesta.ok) {
    tabla.innerHTML = '<tr><td colspan="5" class="text-danger">No se pudo cargar usuarios.</td></tr>';
    return;
  }
  if (!data.length) {
    tabla.innerHTML = '<tr><td colspan="5" class="text-secondary">Sin usuarios.</td></tr>';
    return;
  }

  tabla.innerHTML = "";
  data.forEach((usuario) => {
    const tr = document.createElement("tr");
    const telegram = usuario.telegram_vinculado ? "Vinculado" : "No vinculado";
    const estado = usuario.activo ? "Habilitado" : "Pendiente";
    const accion = usuario.activo ? "Deshabilitar" : "Habilitar";

    tr.innerHTML = `
      <td>${usuario.email}</td>
      <td>${usuario.origen_registro || "-"}</td>
      <td>${estado}</td>
      <td>${telegram}</td>
      <td><button class="btn btn-outline-success btn-sm" data-id="${usuario.id}" data-activo="${usuario.activo}">${accion}</button></td>
    `;
    tabla.appendChild(tr);
  });

  tabla.querySelectorAll("button[data-id]").forEach((boton) => {
    boton.addEventListener("click", async () => {
      const id = Number(boton.dataset.id);
      const activoActual = boton.dataset.activo === "true";
      const { respuesta, data } = await fetchJson(`/api/admin/usuarios/${id}/estado`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ activo: !activoActual }),
      });
      if (!respuesta.ok) {
        Swal.fire({ icon: "error", title: "Error", text: data.error || "No se pudo actualizar usuario." });
        return;
      }
      await cargarUsuariosAdmin();
    });
  });
}

// Rellena el select de materias con contenido de API.
function poblarSelectMaterias() {
  const select = document.getElementById("campo-materia");
  select.innerHTML = "";

  if (!estado.materias.length) {
    const opcion = document.createElement("option");
    opcion.value = "";
    opcion.textContent = "No hay materias cargadas";
    select.appendChild(opcion);
    return;
  }

  estado.materias
    .slice()
    .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"))
    .forEach((materia) => {
      const opcion = document.createElement("option");
      opcion.value = materia.nombre;
      opcion.textContent = materia.nombre;
      select.appendChild(opcion);
    });
}

// Conecta botones de filtro con re-render de tarjetas.
function activarFiltros() {
  document.querySelectorAll("[data-filtro]").forEach((boton) => {
    boton.addEventListener("click", () => {
      document.querySelectorAll("[data-filtro]").forEach((x) => x.classList.remove("active"));
      boton.classList.add("active");
      estado.filtro = boton.dataset.filtro;
      renderizarTarjetas();
    });
  });
}

// Conecta acción manual "Actualizar" del panel.
function activarActualizar() {
  document.getElementById("boton-refrescar").addEventListener("click", async () => {
    try {
      await cargarEntregas();
      Swal.fire({
        icon: "success",
        title: "Panel actualizado",
        text: "Los datos se recargaron correctamente.",
        timer: 1400,
        showConfirmButton: false,
      });
    } catch (error) {
      Swal.fire({
        icon: "error",
        title: "Error al actualizar",
        text: error.message || "No se pudo actualizar el panel.",
      });
    }
  });
}

// Inicializa modal Bootstrap y submit del formulario.
function activarModal() {
  const modalEntregaEl = document.getElementById("modal-entrega");
  const modalMateriaEl = document.getElementById("modal-materia");
  const modalDetalleEl = document.getElementById("modal-detalle-calendario");
  const botonEditarCalendario = document.getElementById("boton-editar-desde-calendario");
  const botonAgregar = document.getElementById("boton-agregar");
  const botonAgregarMateria = document.getElementById("boton-agregar-materia");
  const formEntrega = document.getElementById("form-entrega");
  const formMateria = document.getElementById("form-materia");

  if (modalEntregaEl) {
    estado.modal = new bootstrap.Modal(modalEntregaEl);
  }
  if (modalMateriaEl) {
    estado.modalMateria = new bootstrap.Modal(modalMateriaEl);
  }
  if (modalDetalleEl) {
    estado.modalDetalleCalendario = new bootstrap.Modal(modalDetalleEl);
  }

  if (botonEditarCalendario && estado.modalDetalleCalendario) {
    botonEditarCalendario.addEventListener("click", () => {
      if (!estado.entregaSeleccionadaCalendario) return;
      estado.modalDetalleCalendario.hide();
      abrirModalEditar(estado.entregaSeleccionadaCalendario);
    });
  }

  if (botonAgregar && formEntrega && estado.modal) {
    botonAgregar.addEventListener("click", async () => {
      await cargarMaterias();
      abrirModalCrear();
    });
    formEntrega.addEventListener("submit", guardarEntrega);
  }

  if (botonAgregarMateria && formMateria && estado.modalMateria) {
    botonAgregarMateria.addEventListener("click", () => {
      document.getElementById("campo-materia-nueva").value = "";
      estado.modalMateria.show();
    });
    formMateria.addEventListener("submit", guardarMateria);
  }
}

// Activa menú para cambiar entre vista de entregas y configuración.
function activarMenuVistas() {
  const vistaEntregas = document.getElementById("vista-entregas");
  const vistaConfiguracion = document.getElementById("vista-configuracion");
  const botonEntregas = document.getElementById("menu-entregas");
  const botonConfiguracion = document.getElementById("menu-configuracion");

  function mostrar(vista) {
    const esEntregas = vista === "entregas";
    vistaEntregas.classList.toggle("d-none", !esEntregas);
    vistaConfiguracion.classList.toggle("d-none", esEntregas);
    botonEntregas.classList.toggle("btn-success", esEntregas);
    botonEntregas.classList.toggle("btn-outline-success", !esEntregas);
    botonConfiguracion.classList.toggle("btn-success", !esEntregas);
    botonConfiguracion.classList.toggle("btn-outline-success", esEntregas);
  }

  botonEntregas.addEventListener("click", () => mostrar("entregas"));
  botonConfiguracion.addEventListener("click", async () => {
    mostrar("configuracion");
    try {
      await cargarConfiguracionSistema();
    } catch (error) {
      Swal.fire({ icon: "error", title: "Error", text: error.message || "No se pudo cargar configuración." });
    }
  });
}

// Fuerza tarjetas colapsadas al cargar y controla texto del botón.
function activarColapsoTarjetas() {
  const contenedorColapsable = document.getElementById("tarjetas-entregas-collapse");
  const botonToggle = document.getElementById("boton-toggle-tarjetas");
  if (!contenedorColapsable || !botonToggle || !window.bootstrap?.Collapse) return;

  const instancia = bootstrap.Collapse.getOrCreateInstance(contenedorColapsable, { toggle: false });
  instancia.hide();

  const actualizarTexto = () => {
    const abierto = contenedorColapsable.classList.contains("show");
    botonToggle.textContent = abierto ? "Ocultar tarjetas" : "Mostrar tarjetas";
    botonToggle.setAttribute("aria-expanded", abierto ? "true" : "false");
  };

  contenedorColapsable.addEventListener("shown.bs.collapse", actualizarTexto);
  contenedorColapsable.addEventListener("hidden.bs.collapse", actualizarTexto);
  actualizarTexto();
}

// Maneja guardado de configuración del sistema.
function activarFormularioConfiguracion() {
  const form = document.getElementById("form-configuracion-sistema");
  form.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const payload = {
      telegram_bot_token: document.getElementById("cfg-token-telegram").value.trim(),
      telegram_chat_id: document.getElementById("cfg-chat-id").value.trim(),
      notificaciones_activas: document.getElementById("cfg-notif-activas").value === "true",
      notificacion_hora: document.getElementById("cfg-notif-hora").value,
      notificacion_frecuencia_horas: Number(document.getElementById("cfg-notif-frecuencia-horas").value || 24),
      notificacion_ventana_dias: Number(document.getElementById("cfg-notif-ventana").value || 7),
      zona_horaria: document.getElementById("cfg-zona-horaria").value,
      modo_bot: document.getElementById("cfg-modo-bot").value,
      sincronizacion_campus_activa: document.getElementById("cfg-sync-activa").value === "true",
      minutos_sincronizacion_campus: Number(document.getElementById("cfg-sync-minutos").value || 30),
      campus_calendario_url: document.getElementById("cfg-campus-url").value.trim(),
    };
    const { respuesta, data } = await fetchJson("/api/configuracion/sistema", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!respuesta.ok) {
      Swal.fire({ icon: "error", title: "Error", text: data.error || "No se pudo guardar." });
      return;
    }
    await cargarConfiguracionSistema();
    Swal.fire({ icon: "success", title: "Configuración guardada", timer: 1200, showConfirmButton: false });
  });

  document.getElementById("boton-probar-notificacion").addEventListener("click", async () => {
    const { respuesta, data } = await fetchJson("/api/configuracion/notificaciones/probar", { method: "POST" });
    if (!respuesta.ok) {
      Swal.fire({
        icon: "warning",
        title: "No se pudo enviar",
        text: data.detalle?.description || data.motivo || "Configurá token/chat ID y probá de nuevo.",
      });
      return;
    }
    Swal.fire({ icon: "success", title: "Notificación enviada", text: `Entregas incluidas: ${data.total_entregas}` });
  });

  document.getElementById("boton-generar-vinculacion-telegram").addEventListener("click", async () => {
    const { respuesta, data } = await fetchJson("/api/telegram/vinculacion/generar", { method: "POST" });
    if (!respuesta.ok) {
      Swal.fire({ icon: "error", title: "Error", text: data.error || "No se pudo generar código." });
      return;
    }
    await cargarEstadoVinculacionTelegram();
    Swal.fire({
      icon: "info",
      title: "Código de vinculación",
      html: `<p><strong>${data.codigo}</strong></p><p>${data.instruccion}</p>`,
    });
  });

  const botonRecargar = document.getElementById("boton-recargar-usuarios-admin");
  if (botonRecargar) {
    botonRecargar.addEventListener("click", cargarUsuariosAdmin);
  }

  document.getElementById("boton-sincronizar-campus").addEventListener("click", async () => {
    const { respuesta, data } = await fetchJson("/api/sincronizacion/campus", { method: "POST" });
    if (!respuesta.ok) {
      Swal.fire({
        icon: "warning",
        title: "No se pudo sincronizar",
        text: data.error || "Revisá URL del calendario y configuración.",
      });
      return;
    }
    await cargarEntregas();
    Swal.fire({
      icon: "success",
      title: "Sincronización finalizada",
      text: `Importados: ${data.importados}, actualizados: ${data.actualizados}.`,
    });
  });
}

// Punto de entrada frontend: bind de eventos + carga inicial.
document.addEventListener("DOMContentLoaded", async () => {
  activarColapsoTarjetas();
  activarMenuVistas();
  activarFiltros();
  activarActualizar();
  activarModal();
  activarFormularioConfiguracion();
  try {
    await cargarMaterias();
    await cargarEntregas();
    await cargarUsuariosAdmin();
  } catch (error) {
    Swal.fire({
      icon: "error",
      title: "No se pudo cargar el panel",
      text: error.message || "Error inesperado al cargar entregas.",
    });
  }
});
