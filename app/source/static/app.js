const marketPresets = {
  BTCUSDT: { open_price: "100.00", high_price: "110.00", low_price: "95.00", close_price: "108.00", volume: "250000.00" },
  ETHUSDT: { open_price: "2400.00", high_price: "2480.00", low_price: "2350.00", close_price: "2428.00", volume: "180000.00" },
  SOLUSDT: { open_price: "138.00", high_price: "144.00", low_price: "132.00", close_price: "134.50", volume: "92000.00" },
};

const state = {
  token: localStorage.getItem("ml_token") || "",
  pollTimers: new Map(),
  modelsByName: new Map(),
};

const authScreen = document.querySelector("#auth-screen");
const appScreen = document.querySelector("#app-screen");
const toast = document.querySelector("#toast");
const loginForm = document.querySelector("#login-form");
const registerForm = document.querySelector("#register-form");
const loginUsernameInput = loginForm.querySelector('input[name="username"]');
const loginPasswordInput = loginForm.querySelector('input[name="password"]');

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("is-visible");
  window.setTimeout(() => toast.classList.remove("is-visible"), 3200);
}

function headers() {
  return state.token ? { "X-Auth-Token": state.token } : {};
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...headers(),
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const details = data.details?.map((item) => item.message).join("; ");
    throw new Error(details || data.error || "Запрос не выполнен");
  }
  return data;
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function formatDate(value) {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusBadge(status) {
  const labels = { success: "Готово", failed: "Ошибка", waiting: "В очереди" };
  return `<span class="badge ${status}">${labels[status] || status}</span>`;
}

function showDashboard() {
  closeRegisterModal();
  authScreen.hidden = true;
  appScreen.hidden = false;
}

function showAuth() {
  appScreen.hidden = true;
  authScreen.hidden = false;
}

function openRegisterModal() {
  registerForm.hidden = false;
  document.body.classList.add("register-modal-open");
  registerForm.querySelector("input")?.focus();
}

function closeRegisterModal() {
  registerForm.hidden = true;
  document.body.classList.remove("register-modal-open");
}

function prepareRegisterModal() {
  const title = registerForm.querySelector("h2");
  if (!title) return;

  const header = document.createElement("div");
  header.className = "register-modal-head";

  const closeButton = document.createElement("button");
  closeButton.className = "close-button";
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", "Close");
  closeButton.textContent = "x";
  closeButton.addEventListener("click", closeRegisterModal);

  title.replaceWith(header);
  header.append(title, closeButton);
}

function modelLabel(modelName) {
  if (modelName === "trend-analyzer") return "Анализ";
  return modelName;
}

function renderCardResult(modelBox, task) {
  const target = modelBox.querySelector(".card-result");
  target.hidden = false;
  if (task.status === "waiting") {
    target.innerHTML = `${statusBadge(task.status)}<span>Прогноз на неделю. Задача #${task.task_id} отправлена в RabbitMQ</span>`;
    return;
  }

  if (!task.result) {
    target.innerHTML = `${statusBadge(task.status)}<span>${task.error_message || "Результат не получен"}</span>`;
    return;
  }

  target.innerHTML = `
    ${statusBadge(task.status)}
    <dl class="result-metrics">
      <div><dt>Направление</dt><dd>${task.result.direction}</dd></div>
      <div><dt>Вероятность</dt><dd>${task.result.probability}</dd></div>
      <div><dt>Период</dt><dd>Неделя</dd></div>
      <div><dt>Режим рынка</dt><dd>${task.result.market_regime}</dd></div>
      <div><dt>Воркер</dt><dd>${task.worker_id || "-"}</dd></div>
    </dl>
  `;
}

async function refreshProfile() {
  const user = await api("/users/me");
  document.querySelector("#user-name").textContent = user.username;
  document.querySelector("#balance-value").textContent = user.balance;
  showDashboard();
}

async function refreshBalance() {
  const balance = await api("/balance");
  document.querySelector("#balance-value").textContent = balance.balance;
}

async function loadModels() {
  const models = await api("/models");
  state.modelsByName = new Map(models.map((model) => [model.name, model]));
  document.querySelectorAll(".model-box").forEach((box) => {
    const model = state.modelsByName.get(box.dataset.model);
    const button = box.querySelector(".predict-button");
    button.textContent = model ? `${modelLabel(model.name)} · ${model.price_per_prediction}` : modelLabel(box.dataset.model);
    button.disabled = !model;
  });
}

async function refreshHistory() {
  if (!state.token) return;
  const [predictions, transactions] = await Promise.all([
    api("/history/predictions"),
    api("/history/transactions"),
  ]);

  document.querySelector("#prediction-history").innerHTML = predictions
    .map((item) => {
      const result = item.result ? `${item.result.direction}, ${item.result.probability}` : item.error_message || "-";
      return `
        <tr>
          <td>${formatDate(item.created_at)}</td>
          <td>${item.asset_symbol}</td>
          <td>${statusBadge(item.status)}</td>
          <td>${item.worker_id || "-"}</td>
          <td>${result}</td>
        </tr>
      `;
    })
    .join("");

  document.querySelector("#transaction-history").innerHTML = transactions
    .map(
      (item) => `
        <tr>
          <td>${formatDate(item.created_at)}</td>
          <td>${item.transaction_type}</td>
          <td>${item.amount}</td>
          <td>${item.task_id || "-"}</td>
        </tr>
      `,
    )
    .join("");
}

function startPolling(modelBox, taskId) {
  window.clearInterval(state.pollTimers.get(taskId));
  const timer = window.setInterval(async () => {
    try {
      const task = await api(`/predict/${taskId}`);
      renderCardResult(modelBox, task);
      await refreshBalance();
      if (task.status !== "waiting") {
        window.clearInterval(timer);
        state.pollTimers.delete(taskId);
        await refreshHistory();
      }
    } catch (error) {
      window.clearInterval(timer);
      state.pollTimers.delete(taskId);
      showToast(error.message);
    }
  }, 1400);
  state.pollTimers.set(taskId, timer);
}

prepareRegisterModal();

document.querySelector("#show-register").addEventListener("click", () => {
  openRegisterModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !registerForm.hidden) {
    closeRegisterModal();
  }
});

document.addEventListener("click", (event) => {
  const target = event.target;
  if (
    registerForm.hidden ||
    !(target instanceof Element) ||
    registerForm.contains(target) ||
    target.closest("#show-register")
  ) {
    return;
  }
  closeRegisterModal();
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    const credentials = formData(form);
    await api("/auth/register", {
      method: "POST",
      body: JSON.stringify(credentials),
    });
    loginUsernameInput.value = credentials.username;
    form.reset();
    closeRegisterModal();
    loginPasswordInput.focus();
    showToast("Аккаунт создан");
  } catch (error) {
    showToast(error.message);
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify(formData(event.currentTarget)),
    });
    state.token = data.token;
    localStorage.setItem("ml_token", state.token);
    await refreshProfile();
    await refreshHistory();
    showToast("Вход выполнен");
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector("#logout-button").addEventListener("click", () => {
  state.token = "";
  localStorage.removeItem("ml_token");
  state.pollTimers.forEach((timer) => window.clearInterval(timer));
  state.pollTimers.clear();
  showAuth();
});

document.querySelector("#top-up-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const data = await api("/balance/top-up", {
      method: "POST",
      body: JSON.stringify(formData(event.currentTarget)),
    });
    document.querySelector("#balance-value").textContent = data.balance;
    await refreshHistory();
    showToast("Баланс пополнен");
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector("#forecast-grid").addEventListener("click", async (event) => {
  const button = event.target.closest(".predict-button");
  if (!button) return;

  const card = button.closest(".forecast-card");
  const modelBox = button.closest(".model-box");
  const symbol = card.dataset.symbol;
  const model = state.modelsByName.get(modelBox.dataset.model);
  if (!model) {
    showToast(`Модель ${modelLabel(modelBox.dataset.model)} не найдена`);
    return;
  }

  const payload = {
    model_id: model.id,
    asset_symbol: symbol,
    timeframe: "1w",
    ...marketPresets[symbol],
  };

  button.disabled = true;
  const cardResult = modelBox.querySelector(".card-result");
  cardResult.hidden = false;
  cardResult.textContent = "Отправка задачи. Прогноз на неделю...";
  try {
    const task = await api("/predict", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderCardResult(modelBox, task);
    await refreshBalance();
    await refreshHistory();
    if (task.status === "waiting") startPolling(modelBox, task.task_id);
  } catch (error) {
    cardResult.textContent = "Запрос отклонён";
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

document.querySelector("#refresh-history").addEventListener("click", async () => {
  try {
    await refreshHistory();
    await refreshBalance();
  } catch (error) {
    showToast(error.message);
  }
});

async function boot() {
  try {
    await loadModels();
  } catch (error) {
    showToast(error.message);
  }

  if (state.token) {
    try {
      await refreshProfile();
      await refreshHistory();
    } catch {
      localStorage.removeItem("ml_token");
      state.token = "";
      showAuth();
    }
  } else {
    showAuth();
  }
}

boot();
