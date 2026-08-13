let drawingId = null;
const drawingFile = document.querySelector("#drawingFile");
const normFile = document.querySelector("#normFile");
const reviewButton = document.querySelector("#reviewButton");
const statusEl = document.querySelector("#status");
const drawingSummary = document.querySelector("#drawingSummary");
const normSummary = document.querySelector("#normSummary");
const normQuery = document.querySelector("#normQuery");
const issuesEl = document.querySelector("#issues");
const downloadsEl = document.querySelector("#downloads");
const taskSummary = document.querySelector("#taskSummary");
const eventsEl = document.querySelector("#events");

function setStatus(text) {
  statusEl.textContent = text;
}

async function uploadFile(url, file) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "X-Filename": encodeURIComponent(file.name) },
    body: file,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

drawingFile.addEventListener("change", async () => {
  if (!drawingFile.files.length) return;
  setStatus("Uploading drawing");
  try {
    const result = await uploadFile("/api/drawings", drawingFile.files[0]);
    drawingId = result.drawing_id;
    drawingSummary.textContent = JSON.stringify(result.summary, null, 2);
    reviewButton.disabled = false;
    setStatus("Drawing ready");
  } catch (error) {
    setStatus("Upload failed");
    drawingSummary.textContent = error.message;
  }
});

normFile.addEventListener("change", async () => {
  if (!normFile.files.length) return;
  setStatus("Uploading standards");
  try {
    const result = await uploadFile("/api/norms", normFile.files[0]);
    normSummary.textContent = JSON.stringify(result, null, 2);
    setStatus("Standards ready");
  } catch (error) {
    setStatus("Upload failed");
    normSummary.textContent = error.message;
  }
});

reviewButton.addEventListener("click", async () => {
  if (!drawingId) return;
  setStatus("Agent running");
  reviewButton.disabled = true;
  issuesEl.innerHTML = "";
  downloadsEl.innerHTML = "";
  eventsEl.innerHTML = "";
  taskSummary.textContent = "Creating task...";

  try {
    const response = await fetch("/api/tasks/async", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        drawing_id: drawingId,
        norm_query: normQuery.value,
        objective: "Review the CAD drawing against the uploaded standards, run tool calls, track state, apply safe auto-repairs, generate reports, and evaluate the Agent run.",
      }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || response.statusText);
    }
    const task = await response.json();
    renderTask(task);
    streamTask(task.task_id);
  } catch (error) {
    issuesEl.textContent = error.message;
    setStatus("Agent failed");
  }
});

function renderReview(result) {
  if (!result) return;
  const links = [
    ["HTML Report", result.downloads.html],
    ["JSON", result.downloads.json],
    ["Repaired DXF", result.downloads.fixed_dxf],
  ];
  downloadsEl.innerHTML = links.map(([label, href]) => `<a href="${href}" target="_blank">${label}</a>`).join("");

  if (!result.issues.length) {
    issuesEl.innerHTML = `<div class="issue low"><div class="issue-title">No issues found</div></div>`;
    return;
  }

  issuesEl.innerHTML = result.issues
    .map((issue) => {
      const evidence = issue.evidence.map(escapeHtml).join("<br>");
      const fix = issue.auto_fix ? "Auto-fixable" : issue.requires_confirmation ? "Needs review" : "Recommendation only";
      return `<article class="issue ${escapeHtml(issue.severity)}">
        <div class="issue-title">
          <span>${escapeHtml(issue.issue_id)} · ${escapeHtml(issue.title)}</span>
          <span>${escapeHtml(issue.severity)}</span>
        </div>
        <div class="issue-meta">${escapeHtml(issue.category)} · ${fix}</div>
        <p>${evidence}</p>
        <p>${escapeHtml(issue.suggestion)}</p>
      </article>`;
    })
    .join("");
}

function renderTask(task) {
  taskSummary.textContent = JSON.stringify(
    {
      task_id: task.task_id,
      status: task.status,
      steps: task.plan?.map((step) => ({
        name: step.name,
        tool: step.tool_name,
        status: step.status,
      })),
      evaluation: task.result?.evaluation,
    },
    null,
    2
  );
}

function renderEvents(events) {
  eventsEl.innerHTML = events
    .map((event) => {
      return `<div class="event">
        <strong>${escapeHtml(event.type)}</strong>
        <span>${escapeHtml(event.message)}</span>
      </div>`;
    })
    .join("");
}

function appendEvent(event) {
  const node = document.createElement("div");
  node.className = "event";
  node.innerHTML = `<strong>${escapeHtml(event.type)}</strong><span>${escapeHtml(event.message)}</span>`;
  eventsEl.appendChild(node);
  eventsEl.scrollTop = eventsEl.scrollHeight;
}

function streamTask(taskId) {
  const stream = new EventSource(`/api/tasks/${taskId}/events`);
  stream.onmessage = () => {};
  [
    "task.created",
    "task.started",
    "plan.created",
    "step.started",
    "tool.started",
    "tool.finished",
    "step.finished",
    "memory.written",
    "evaluation.finished",
    "task.finished",
    "task.failed",
  ].forEach((eventType) => {
    stream.addEventListener(eventType, async (message) => {
      const event = JSON.parse(message.data);
      appendEvent(event);
      if (eventType === "task.finished" || eventType === "task.failed") {
        stream.close();
        const response = await fetch(`/api/tasks/${taskId}`);
        const task = await response.json();
        renderTask(task);
        if (task.result) {
          renderReview(task.result);
          setStatus(`Done: ${task.result.issue_count || 0} issues`);
        } else {
          setStatus("Agent failed");
        }
        reviewButton.disabled = false;
      }
    });
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
