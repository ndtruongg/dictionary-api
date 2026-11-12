"use strict";

const form = document.querySelector("#lookup-form");
const input = document.querySelector("#word");
const submit = document.querySelector("#submit-button");
const clearButton = document.querySelector("#clear-button");
const quickSearch = document.querySelector("#quick-search");
const emptyState = document.querySelector("#empty-state");
const statusLine = document.querySelector("#status");
const results = document.querySelector("#results");
let currentAudio = null;
let currentAudioButton = null;
let audioTimeout = null;

function element(tag, text, className, lang) {
  const node = document.createElement(tag);
  if (text !== null && text !== undefined) node.textContent = text;
  if (className) node.className = className;
  if (lang) node.lang = lang;
  return node;
}

function icon(name) {
  const paths = {
    volume: ["m11 5-6 4H2v6h3l6 4V5Z", "M15 8a6 6 0 0 1 0 8", "M18 5a10 10 0 0 1 0 14"],
    pause: ["M8 5v14M16 5v14"],
    loading: ["M20 12a8 8 0 1 1-5-7.4"],
  };
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.7", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", class: "icon"})) svg.setAttribute(key, value);
  for (const value of paths[name]) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", value);
    svg.append(path);
  }
  return svg;
}

function showStatus(message, error = false, quiet = false) {
  statusLine.textContent = message;
  statusLine.classList.toggle("error", error);
  statusLine.classList.toggle("is-quiet", quiet && !error);
}

function paintAudio(button, state) {
  button.replaceChildren(icon(state === "playing" ? "pause" : state === "loading" ? "loading" : "volume"),
    element("span", state === "loading" ? "Đang tải" : button.dataset.label));
  button.disabled = state === "loading";
  button.setAttribute("aria-pressed", String(state === "playing"));
}

function stopAudio() {
  clearTimeout(audioTimeout);
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.removeAttribute("src");
    currentAudio.load();
  }
  if (currentAudioButton) paintAudio(currentAudioButton, "idle");
  currentAudio = null;
  currentAudioButton = null;
}

function audioLabel(labels, index) {
  if (labels.some(label => ["UK", "Received-Pronunciation", "Âm thanh (Anh)"].includes(label))) return "UK";
  if (labels.some(label => ["US", "Mỹ", "General-American", "Âm thanh (Mỹ)"].includes(label))) return "US";
  return labels.join(" · ") || `Bản ${index + 1}`;
}

function audioButton(clip, headword, index) {
  const label = audioLabel(clip.labels || [], index);
  const button = element("button", null, "audio-button");
  button.type = "button";
  button.dataset.label = label;
  button.setAttribute("aria-label", `Nghe phát âm ${headword}, ${label}`);
  button.title = clip.labels?.join(" · ") || "Nghe phát âm";
  paintAudio(button, "idle");
  button.addEventListener("click", async () => {
    if (currentAudioButton === button) { stopAudio(); return; }
    stopAudio();
    let url;
    try { url = new URL(clip.url); } catch { return; }
    if (url.protocol !== "https:" || !["upload.wikimedia.org", "commons.wikimedia.org"].includes(url.hostname)
        || url.username || url.password || (url.port && url.port !== "443")) return;
    const audio = new Audio();
    audio.preload = "none";
    currentAudio = audio;
    currentAudioButton = button;
    paintAudio(button, "loading");
    const failed = () => {
      if (currentAudio !== audio) return;
      stopAudio();
      showStatus("Chưa phát được âm thanh. Bạn có thể thử bản phát âm khác.", true);
    };
    audio.addEventListener("error", failed, {once: true});
    audio.addEventListener("ended", () => {
      if (currentAudio !== audio) return;
      stopAudio();
      showStatus(`Đã phát xong ${label}.`, false, true);
    }, {once: true});
    audioTimeout = setTimeout(failed, 15000);
    audio.src = url.href;
    try {
      await audio.play();
      if (currentAudio !== audio) return;
      clearTimeout(audioTimeout);
      paintAudio(button, "playing");
      showStatus(`Đang phát âm ${label} cho “${headword}”.`, false, true);
    } catch { failed(); }
  });
  return button;
}

function unique(items, getKey) {
  const seen = new Set();
  return items.filter(item => {
    const key = getKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function renderPronunciations(entries, headword, header) {
  const pronunciations = unique(entries.flatMap(entry => entry.pronunciations || []), item => `${item.ipa}|${(item.labels || []).join("|")}`);
  const clips = unique(entries.flatMap(entry => entry.audio || []), item => `${item.url}|${(item.labels || []).join("|")}`);
  const primary = pronunciations.find(item => item.ipa.startsWith("/")) || pronunciations[0];
  const bar = element("div", null, "pronunciation-bar");
  if (primary) bar.append(element("span", primary.ipa, "primary-ipa", "en"));
  if (clips.length) {
    const controls = element("div", null, "audio-controls");
    controls.setAttribute("role", "group");
    controls.setAttribute("aria-label", `Phát âm ${headword}`);
    clips.forEach((clip, index) => controls.append(audioButton(clip, headword, index)));
    bar.append(controls);
  }
  if (bar.childElementCount) header.append(bar);
  const alternatives = pronunciations.filter(item => item !== primary);
  if (alternatives.length) {
    const details = element("details", null, "pronunciation-details");
    details.append(element("summary", "Phiên âm khác"));
    const list = element("div", null, "pronunciation-list");
    for (const item of alternatives) {
      const line = element("div", null, "pronunciation");
      if (item.labels?.length) line.append(element("strong", item.labels.join(" · ")));
      line.append(element("span", item.ipa, null, "en"));
      list.append(line);
    }
    details.append(list);
    header.append(details);
  }
}

function renderExample(example) {
  const block = element("div", null, "example");
  if (example.english) block.append(element("p", example.english, "english", "en"));
  if (example.vietnamese) block.append(element("p", example.vietnamese, "translation", "vi"));
  if (example.reference) block.append(element("p", example.reference, "labels"));
  return block;
}

function renderEntry(entry) {
  const section = element("article", null, "entry");
  section.append(element("h3", entry.part_of_speech || entry.pos || "Mục từ"));
  const list = element("ol", null, "sense-list");
  for (const sense of entry.senses || []) {
    const item = element("li");
    const glosses = sense.glosses || [];
    glosses.forEach((gloss, index) => item.append(element("p", gloss, index === glosses.length - 1 ? "definition" : "gloss-context", "vi")));
    const labels = [...(sense.labels || []), ...(sense.topics || [])];
    if (labels.length) item.append(element("p", labels.join(" · "), "labels"));
    const examples = sense.examples || [];
    examples.slice(0, 2).forEach(example => item.append(renderExample(example)));
    if (examples.length > 2) {
      const details = element("details", null, "more-examples");
      details.append(element("summary", `Xem thêm ${examples.length - 2} ví dụ`));
      examples.slice(2).forEach(example => details.append(renderExample(example)));
      item.append(details);
    }
    list.append(item);
  }
  section.append(list);
  return section;
}

function renderResult(data) {
  const entries = data.entries || [];
  const headword = data.headword || data.normalized_word || data.word;
  const header = element("div", null, "result-header");
  const title = element("div", null, "word-heading");
  title.append(element("h2", headword, null, "en"));
  const senses = entries.reduce((total, entry) => total + (entry.senses?.length || 0), 0);
  title.append(element("span", `${entries.length > 1 ? `${entries.length} mục từ · ` : ""}${senses} nghĩa`, "word-summary"));
  header.append(title);
  renderPronunciations(entries, headword, header);
  results.append(header);
  const sections = entries.map(entry => ({label: entry.part_of_speech || entry.pos || "Mục từ", node: renderEntry(entry)}));
  const labels = [...new Set(sections.map(section => section.label))];
  if (labels.length > 1) {
    const filters = element("div", null, "entry-filters");
    filters.setAttribute("role", "group");
    filters.setAttribute("aria-label", "Lọc theo loại từ");
    for (const label of [null, ...labels]) {
      const button = element("button", label || "Tất cả", "filter-button");
      button.type = "button";
      button.setAttribute("aria-pressed", String(label === null));
      button.addEventListener("click", () => {
        for (const section of sections) section.node.hidden = label !== null && section.label !== label;
        for (const sibling of filters.children) sibling.setAttribute("aria-pressed", String(sibling === button));
      });
      filters.append(button);
    }
    results.append(filters);
  }
  sections.forEach(section => results.append(section.node));
  results.hidden = false;
}

function updateClearButton() { clearButton.hidden = !input.value; }
input.addEventListener("input", updateClearButton);
clearButton.addEventListener("click", () => { input.value = ""; updateClearButton(); input.focus(); });
quickSearch.querySelectorAll("button").forEach(button => button.addEventListener("click", () => {
  if (submit.disabled) return;
  input.value = button.dataset.word;
  updateClearButton();
  form.requestSubmit();
}));

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (submit.disabled) return;
  const word = input.value.trim();
  stopAudio();
  updateClearButton();
  results.replaceChildren();
  results.hidden = true;
  emptyState.hidden = true;
  quickSearch.hidden = true;
  input.removeAttribute("aria-invalid");
  input.removeAttribute("aria-describedby");
  submit.disabled = true;
  submit.textContent = "Đang tra…";
  form.setAttribute("aria-busy", "true");
  showStatus("Đang tra từ…");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 35000);
  try {
    const response = await fetch(`/api/dictionary?${new URLSearchParams({word})}`, {signal: controller.signal, cache: "no-store"});
    const data = await response.json();
    if (!response.ok) {
      const message = data.code === "WORD_NOT_FOUND" ? `Chưa có “${word}” trong từ điển. Hãy kiểm tra chính tả hoặc thử từ khác.`
        : data.code === "INVALID_INPUT" ? "Hãy nhập từ tiếng Anh, có thể dùng dấu nháy hoặc gạch nối."
        : "Chưa thể tra cứu lúc này. Vui lòng thử lại sau.";
      showStatus(message, true);
      quickSearch.hidden = false;
      input.setAttribute("aria-describedby", "status");
      if (data.code === "INVALID_INPUT") input.setAttribute("aria-invalid", "true");
      return;
    }
    renderResult(data);
    showStatus(`Đã tìm thấy ${data.entries?.length || 0} mục từ cho “${data.headword || word}”.`, false, true);
  } catch (error) {
    showStatus(error.name === "AbortError" ? "Thời gian chờ đã hết. Vui lòng thử lại." : "Không kết nối được. Hãy kiểm tra kết nối và thử lại.", true);
    quickSearch.hidden = false;
  } finally {
    clearTimeout(timer);
    submit.disabled = false;
    submit.textContent = "Tra từ";
    form.removeAttribute("aria-busy");
  }
});
