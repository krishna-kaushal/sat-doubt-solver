// Minimal markdown renderer (headings, bold, italic, lists, code, paragraphs)
function md(src) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) =>
    esc(s)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");
  const lines = src.split("\n");
  let html = "", inList = null;
  const closeList = () => { if (inList) { html += inList === "ul" ? "</ul>" : "</ol>"; inList = null; } };
  for (const line of lines) {
    const t = line.trim();
    if (/^#{1,3}\s/.test(t)) {
      closeList();
      html += `<h3>${inline(t.replace(/^#+\s*/, ""))}</h3>`;
    } else if (/^(\d+)[.)]\s/.test(t)) {
      if (inList !== "ol") { closeList(); html += "<ol>"; inList = "ol"; }
      html += `<li>${inline(t.replace(/^\d+[.)]\s*/, ""))}</li>`;
    } else if (/^[-*]\s/.test(t)) {
      if (inList !== "ul") { closeList(); html += "<ul>"; inList = "ul"; }
      html += `<li>${inline(t.replace(/^[-*]\s*/, ""))}</li>`;
    } else if (t === "") {
      closeList();
    } else {
      closeList();
      html += `<p>${inline(t)}</p>`;
    }
  }
  closeList();
  return html;
}

const $ = (id) => document.getElementById(id);
const els = {
  input: $("q-input"), photoInput: $("photo-input"), photoName: $("photo-name"),
  photoPreviewWrap: $("photo-preview-wrap"), photoPreview: $("photo-preview"),
  solveBtn: $("solve-btn"), loading: $("loading"), loadingText: $("loading-text"),
  errorCard: $("error-card"), errorText: $("error-text"),
  result: $("result"), subject: $("r-subject"), topic: $("r-topic"),
  explanation: $("r-explanation"), problems: $("r-problems"),
  inputCard: $("input-card"),
};
let photoDataUrl = "";

els.photoInput.addEventListener("change", () => {
  const f = els.photoInput.files[0];
  if (!f) return;
  if (f.size > 6 * 1024 * 1024) { showError("That photo is too large — please use one under 6 MB."); return; }
  const reader = new FileReader();
  reader.onload = () => {
    photoDataUrl = reader.result;
    els.photoName.textContent = f.name;
    els.photoPreview.src = photoDataUrl;
    els.photoPreviewWrap.classList.remove("hidden");
  };
  reader.readAsDataURL(f);
});
$("photo-clear").addEventListener("click", () => {
  photoDataUrl = ""; els.photoInput.value = "";
  els.photoName.textContent = "";
  els.photoPreviewWrap.classList.add("hidden");
});

function showError(msg) {
  els.errorText.textContent = msg;
  els.errorCard.classList.remove("hidden");
}
function hideError() { els.errorCard.classList.add("hidden"); }

const loadingLines = [
  "Reading your question…",
  "Working through the steps…",
  "Writing similar practice problems…",
];
let loadingTimer = null;

els.solveBtn.addEventListener("click", async () => {
  const text = els.input.value.trim();
  if (!text && !photoDataUrl) { showError("Paste a question or add a photo first."); return; }
  hideError();
  els.inputCard.classList.add("hidden");
  els.result.classList.add("hidden");
  els.loading.classList.remove("hidden");
  els.solveBtn.disabled = true;
  let li = 0;
  els.loadingText.textContent = loadingLines[0];
  loadingTimer = setInterval(() => {
    li = (li + 1) % loadingLines.length;
    els.loadingText.textContent = loadingLines[li];
  }, 3500);

  try {
    const res = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, image: photoDataUrl }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Something went wrong.");
    renderResult(data);
  } catch (e) {
    els.loading.classList.add("hidden");
    els.inputCard.classList.remove("hidden");
    showError(e.message || "Network error — please try again.");
  } finally {
    clearInterval(loadingTimer);
    els.solveBtn.disabled = false;
  }
});

function renderResult(data) {
  els.loading.classList.add("hidden");
  els.subject.textContent = data.subject || "SAT";
  els.topic.textContent = data.topic || "";
  els.explanation.innerHTML = md(data.explanation || "No explanation returned.");
  els.problems.innerHTML = "";
  (data.problems || []).forEach((p, i) => {
    const div = document.createElement("div");
    div.className = "problem";
    div.innerHTML = `
      <p class="q"><strong>Q${i + 1}.</strong> ${escapeHtml(p.question || "")}</p>
      ${p.hint ? `<p class="hint">Hint: ${escapeHtml(p.hint)}</p>` : ""}
      <button class="toggle" type="button">Show answer</button>
      <p class="answer">${escapeHtml(p.answer || "")}</p>`;
    const btn = div.querySelector(".toggle");
    const ans = div.querySelector(".answer");
    btn.addEventListener("click", () => {
      const show = ans.classList.toggle("show");
      btn.textContent = show ? "Hide answer" : "Show answer";
    });
    els.problems.appendChild(div);
  });
  els.result.classList.remove("hidden");
  els.result.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

$("again-btn").addEventListener("click", () => {
  els.result.classList.add("hidden");
  els.inputCard.classList.remove("hidden");
  els.input.value = "";
  $("photo-clear").click();
  window.scrollTo({ top: 0, behavior: "smooth" });
  els.input.focus();
});
