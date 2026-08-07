const state = {
  zone: "all",
  data: null,
  selectedEvent: null,
  series: "flow",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error(`请求失败：${response.status}`);
  return response.json();
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2200);
}

function setLoading(isLoading) {
  $(".main-content").classList.toggle("loading", isLoading);
}

async function loadOverview(zone = state.zone, notify = false) {
  setLoading(true);
  try {
    state.zone = zone;
    state.data = await fetchJSON(`/api/overview?zone=${encodeURIComponent(zone)}`);
    renderOverview();
    if (notify) showToast("运营数据已刷新");
  } catch (error) {
    showToast(error.message || "数据加载失败");
  } finally {
    setLoading(false);
  }
}

function renderOverview() {
  const { metrics, scope, summary, events, updated_at: updatedAt } = state.data;
  $("#scopeName").textContent = scope.name;
  $("#metricSupply").textContent = metrics.supply.value.toFixed(2);
  $("#metricLeakage").textContent = metrics.leakage.value.toFixed(1);
  $("#metricPressure").textContent = metrics.pressure.value.toFixed(2);
  $("#metricAlarms").textContent = metrics.alarms.value;
  $("#deltaSupply").textContent = Math.abs(metrics.supply.delta).toFixed(1);
  $("#deltaLeakage").textContent = Math.abs(metrics.leakage.delta).toFixed(1);
  $("#onlineRate").textContent = `${metrics.online_rate.value.toFixed(1)}%`;
  $("#leakageProgress").style.width = `${Math.min(metrics.leakage.value * 7, 100)}%`;
  $("#pressureMarker").style.left = `${Math.min(Math.max((metrics.pressure.value - .2) / .3 * 100, 0), 100)}%`;
  $("#pendingCount").textContent = summary.pending;
  $("#processingCount").textContent = summary.processing;
  $("#resolvedCount").textContent = summary.resolved;
  $("#navAlertCount").textContent = summary.pending + summary.processing;
  $("#sideUpdated").textContent = updatedAt.slice(-5);
  $("#zoneSelect").value = state.zone;
  $$(".zone-node").forEach((node) => node.classList.toggle("active", node.dataset.zone === state.zone));
  renderChart();
  renderEvents(events);
}

function renderEvents(events) {
  const list = $("#eventList");
  if (!events.length) {
    list.innerHTML = '<div class="empty-state"><span>✓</span><strong>当前片区无活动事件</strong><p>系统仍在持续监测</p></div>';
    $("#eventDetail").innerHTML = '<div class="empty-state"><span>✓</span><strong>运行正常</strong><p>没有需要处置的异常</p></div>';
    return;
  }
  list.innerHTML = events.map((event) => `
    <div class="event-row ${state.selectedEvent === event.id ? "active" : ""}" data-event-id="${event.id}" tabindex="0" role="button" aria-label="查看 ${event.type}">
      <span class="severity ${event.severity}">${event.severity_text}优先</span>
      <div class="event-primary"><strong>${event.type}</strong><small>${event.id}</small></div>
      <div class="event-location"><span>${event.location}</span><small>${event.description.slice(0, 22)}…</small></div>
      <span class="event-time">${event.occurred_at.slice(5)}</span>
      <span class="status-badge ${event.status}">${event.status_text}</span>
    </div>`).join("");

  $$(".event-row").forEach((row) => {
    const select = () => selectEvent(row.dataset.eventId);
    row.addEventListener("click", select);
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") select();
    });
  });

  const selectedStillVisible = events.some((event) => event.id === state.selectedEvent);
  selectEvent(selectedStillVisible ? state.selectedEvent : events[0].id, false);
}

function selectEvent(eventId, rerenderList = true) {
  const event = state.data.events.find((item) => item.id === eventId);
  if (!event) return;
  state.selectedEvent = eventId;
  if (rerenderList) {
    $$(".event-row").forEach((row) => row.classList.toggle("active", row.dataset.eventId === eventId));
  }
  const canAcknowledge = event.status === "pending";
  $("#eventDetail").innerHTML = `
    <div class="detail-top"><span class="severity ${event.severity}">${event.severity_text}优先</span><small>${event.occurred_at}</small></div>
    <h3>${event.type}</h3>
    <p class="detail-location">${event.location}</p>
    <p class="detail-description">${event.description}</p>
    <ol class="detail-steps"><li>核对监测点与相邻分区趋势</li><li>派发现场核查或调度任务</li><li>记录结果并关闭事件</li></ol>
    <button class="ack-button" type="button" ${canAcknowledge ? "" : "disabled"}>${canAcknowledge ? "确认并进入处置" : `${event.status_text}${event.ack_by ? ` · ${event.ack_by}` : ""}`}</button>`;
  if (canAcknowledge) $(".ack-button").addEventListener("click", () => acknowledgeEvent(event.id));
}

async function acknowledgeEvent(eventId) {
  try {
    const updated = await fetchJSON(`/api/events/${eventId}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ operator: "演示调度员" }),
    });
    const index = state.data.events.findIndex((event) => event.id === eventId);
    state.data.events[index] = updated;
    state.data.summary.pending -= 1;
    state.data.summary.processing += 1;
    renderOverview();
    state.selectedEvent = eventId;
    selectEvent(eventId);
    showToast(`${eventId} 已进入处置流程`);
  } catch (error) {
    showToast(error.message || "事件确认失败");
  }
}

function drawLineChart(canvas, labels, values, options) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);

  const pad = { top: 18, right: 15, bottom: 30, left: 39 };
  const chartW = width - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const min = Math.min(...values) * .92;
  const max = Math.max(...values) * 1.07;
  const x = (index) => pad.left + index * chartW / (values.length - 1);
  const y = (value) => pad.top + (max - value) / (max - min) * chartH;

  ctx.font = '9px "Segoe UI", sans-serif';
  ctx.strokeStyle = "rgba(79, 116, 128, .12)";
  ctx.fillStyle = "#8ca0a8";
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i += 1) {
    const gy = pad.top + i * chartH / 3;
    ctx.beginPath(); ctx.moveTo(pad.left, gy); ctx.lineTo(width - pad.right, gy); ctx.stroke();
    const label = max - i * (max - min) / 3;
    ctx.fillText(options.format(label), 2, gy + 3);
  }
  labels.forEach((label, index) => {
    if (index % 2 === 0 || index === labels.length - 1) ctx.fillText(label, x(index) - 12, height - 7);
  });

  const gradient = ctx.createLinearGradient(0, pad.top, 0, height - pad.bottom);
  gradient.addColorStop(0, options.fill);
  gradient.addColorStop(1, "rgba(26, 168, 159, 0)");
  ctx.beginPath();
  values.forEach((value, index) => index ? ctx.lineTo(x(index), y(value)) : ctx.moveTo(x(index), y(value)));
  ctx.lineTo(x(values.length - 1), height - pad.bottom);
  ctx.lineTo(x(0), height - pad.bottom);
  ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();

  ctx.beginPath();
  values.forEach((value, index) => index ? ctx.lineTo(x(index), y(value)) : ctx.moveTo(x(index), y(value)));
  ctx.strokeStyle = options.color; ctx.lineWidth = 2; ctx.stroke();
  values.forEach((value, index) => {
    ctx.beginPath(); ctx.arc(x(index), y(value), index === values.length - 1 ? 4 : 2.2, 0, Math.PI * 2);
    ctx.fillStyle = "#fff"; ctx.fill(); ctx.strokeStyle = options.color; ctx.lineWidth = 1.5; ctx.stroke();
  });
}

function renderChart() {
  const series = state.series;
  const values = state.data.trend[series];
  const isFlow = series === "flow";
  $("#trendLatest").textContent = values.at(-1);
  $("#trendUnit").textContent = isFlow ? "m³/h" : "MPa";
  $("#trendCaption").textContent = isFlow ? "当前瞬时流量" : "当前平均压力";
  $("#trendInsight").textContent = isFlow
    ? "当前流量处于模型基线范围，06:00 后进入用水爬坡阶段；东城片区夜间小流量偏高。"
    : "全域压力总体稳定，东城末梢压力接近关注线，建议结合阀门开度持续观察。";
  drawLineChart($("#trendChart"), state.data.trend.labels, values, {
    color: isFlow ? "#149d98" : "#7868d8",
    fill: isFlow ? "rgba(20, 157, 152, .18)" : "rgba(120, 104, 216, .16)",
    format: (value) => isFlow ? Math.round(value) : value.toFixed(2),
  });
}

$("#zoneSelect").addEventListener("change", (event) => loadOverview(event.target.value));
$("#refreshButton").addEventListener("click", () => loadOverview(state.zone, true));
$$(".zone-node").forEach((node) => node.addEventListener("click", () => loadOverview(node.dataset.zone)));
$$(".chart-toggle button").forEach((button) => button.addEventListener("click", () => {
  state.series = button.dataset.series;
  $$(".chart-toggle button").forEach((item) => item.classList.toggle("active", item === button));
  renderChart();
}));
$(".mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
window.addEventListener("resize", () => state.data && renderChart());

loadOverview();
