/* TOPIK Simulator web UI — vanilla JS, no external assets.
   Talks to the JSON API in topik_sim/web/app.py. All DOM is built with
   el()/textContent, never innerHTML with server data. */

"use strict";

/* ------------------------------------------------------------ utilities */

const $view = () => document.getElementById("view");

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(child));
  }
  return node;
}

let toastTimer = null;
function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 3200);
}

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `${response.status} ${response.statusText}`);
    error.status = response.status;
    throw error;
  }
  return data;
}

const GRAMMAR_LEGEND = "Pattern shorthand: N = noun · V = verb stem · A = descriptive-verb stem · (으) = added after a final consonant";

const state = {
  tts: { enabled: false, volume: 1 },
  views: new Map(),      // activity id -> last view payload
  courseFlow: null,      // {packId, courseId, lesson, step}
  deck: null,            // pending card deck {title, cards, kind, onDone}
  cleanups: [],
};

function onCleanup(fn) { state.cleanups.push(fn); }

/* ---------------------------------------------------------------- audio */

const player = new Audio();
function playerVolume() { return Math.max(0, Math.min(1, state.tts.volume || 1)); }

async function playUrls(urls) {
  player.pause();
  for (const url of urls) {
    const ok = await new Promise((resolve) => {
      player.src = url;
      player.volume = playerVolume();
      player.onended = () => resolve(true);
      player.onerror = () => resolve(false);
      player.play().catch(() => resolve(false));
    });
    if (!ok) return false;
  }
  return true;
}

function say(text) {
  if (!text) return;
  playUrls([`/api/say?text=${encodeURIComponent(text)}`]).then((ok) => {
    if (!ok) toast("Audio unavailable — check TTS in Settings.");
  });
}

function speakButton(text, label = "🔊") {
  return el("button", { class: "ghost", title: "Speak", onclick: (e) => { e.stopPropagation(); say(text); } }, label);
}

function selfGrade(slot, { model, also, question, onYes, onNo }) {
  // A self-rating must be a deliberate choice: neither button is focused (so a
  // stray Enter cannot silently mark a wrong answer correct) and y/n keys work.
  const keyHandler = (event) => {
    const tag = event.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === "y" || event.key === "Y") { event.preventDefault(); finish(true); }
    else if (event.key === "n" || event.key === "N") { event.preventDefault(); finish(false); }
  };
  const finish = (ok) => {
    document.removeEventListener("keydown", keyHandler);
    (ok ? onYes : onNo)();
  };
  document.addEventListener("keydown", keyHandler);
  onCleanup(() => document.removeEventListener("keydown", keyHandler));
  slot.replaceChildren(
    el("p", {}, "Model: ", el("strong", { class: "ko", text: model }), speakButton(model)),
    also && also.length ? el("p", { class: "small muted ko", text: "Also fine: " + also.join(" / ") }) : null,
    el("p", { class: "muted", text: `${question}  (y / n)` }),
    el("div", { class: "row" },
      el("button", { text: "Yes — I had it right (y)", onclick: () => finish(true) }),
      el("button", { text: "No — count it wrong (n)", onclick: () => finish(false) })));
}

/* --------------------------------------------------------------- router */

function go(hash) {
  // Setting an unchanged hash fires no hashchange event, which left in-place
  // runners (compose, dialogue) with dead Stop/finish buttons — route directly.
  if (location.hash === hash) { route(); return; }
  location.hash = hash;
}

const routes = [
  [/^#?\/?$/, () => homeView()],
  [/^#\/study$/, () => studyPathView()],
  [/^#\/take$/, () => takeView()],
  [/^#\/exam\/([\w-]+)$/, (m) => examView(m[1])],
  [/^#\/drill\/([\w-]+)$/, (m) => drillView(m[1])],
  [/^#\/practice$/, () => practiceView()],
  [/^#\/practice\/([\w-]+)$/, (m) => practiceConfigView(m[1])],
  [/^#\/cards$/, () => cardsView()],
  [/^#\/courses$/, () => coursesView()],
  [/^#\/lesson\/([\w.@-]+)\/([\w-]+)$/, (m) => lessonView(m[1], m[2])],
  [/^#\/progress$/, () => progressView()],
  [/^#\/report\/([\w.@-]+)$/, (m) => reportView(m[1])],
  [/^#\/settings$/, () => settingsView()],
];

async function route() {
  for (const fn of state.cleanups.splice(0)) { try { fn(); } catch {} }
  player.pause();
  const hash = location.hash || "#/";
  for (const [pattern, handler] of routes) {
    const match = hash.match(pattern);
    if (match) {
      document.querySelectorAll("#side a").forEach((a) => {
        const key = a.dataset.nav;
        const active = (key === "home" && (hash === "#/" || hash === "")) ||
          (key !== "home" && hash.startsWith(`#/${key}`)) ||
          (key === "take" && hash.startsWith("#/exam")) ||
          (key === "practice" && (hash.startsWith("#/drill") || hash.startsWith("#/cards"))) ||
          (key === "courses" && hash.startsWith("#/lesson")) ||
          (key === "progress" && hash.startsWith("#/report"));
        a.classList.toggle("active", Boolean(active));
      });
      try {
        await handler(match);
      } catch (error) {
        renderError(error);
      }
      return;
    }
  }
  go("#/");
}

function render(...nodes) {
  const view = $view();
  view.replaceChildren(...nodes.filter(Boolean));
  view.classList.remove("view-enter");
  void view.offsetWidth; // restart the entrance animation
  view.classList.add("view-enter");
  view.scrollTop = 0;
  window.scrollTo(0, 0);
}

function renderError(error) {
  render(
    el("h1", { text: "Something went wrong" }),
    el("p", { class: "sub", text: error.message || String(error) }),
    el("button", { onclick: () => go("#/"), text: "Back to home" }),
  );
}

function header(title, subtitle) {
  const nodes = [el("h1", { text: title })];
  if (subtitle) nodes.push(el("p", { class: "sub", text: subtitle }));
  return nodes;
}

/* ----------------------------------------------------------------- home */

function nextLessonInfo(coursePacks) {
  // The teacher's pointer: first unfinished lesson anywhere; if a lesson is
  // finished but its homework is not, the homework comes first.
  for (const pack of coursePacks || []) {
    for (const lesson of pack.lessons) {
      if (lesson.done && !lesson.homework) {
        return { pack, lesson, kind: "homework" };
      }
      if (!lesson.done) return { pack, lesson, kind: "study" };
    }
  }
  return null;
}

function todayStep(number, koLabel, enLabel, body) {
  return el("div", { class: "today-step" },
    el("div", { class: "step-badge", text: String(number) }),
    el("div", { class: "step-main" },
      el("div", { class: "step-title" }, el("span", { class: "ko", text: koLabel }), ` · ${enLabel}`),
      body));
}

async function homeView() {
  const data = await api("GET", "/api/state");
  state.tts = data.tts;
  updateTtsPill();

  const inProgress = data.attempts.filter((a) => a.status !== "completed");
  const dueByPack = Object.entries(data.review_due || {});
  const dueTotal = dueByPack.reduce((sum, [, n]) => sum + n, 0);
  const next = nextLessonInfo(data.courses);

  // --- Step 1: spaced review first — the highest-value minutes of the day.
  const vocabDue = data.vocab_due || 0;
  const reviewRows = dueByPack.slice(0, 3).map(([packId, count]) =>
    el("div", { class: "spread" },
      el("span", { class: "small" }, el("strong", { text: String(count) }), ` question(s) · ${packId}`),
      el("button", { class: "primary", text: "Review", onclick: () => startExam({ pack: packId }, "/api/exam/review") })));
  if (vocabDue) {
    reviewRows.unshift(el("div", { class: "spread" },
      el("span", { class: "small" }, el("strong", { text: String(vocabDue) }), " vocabulary word(s) due"),
      el("button", { class: "primary", text: "Review vocab", onclick: () => startVocab() })));
  }
  const reviewBody = reviewRows.length
    ? el("div", { class: "stack" }, ...reviewRows)
    : el("p", { class: "small muted", text: "Nothing due — your review queue is clear. ✓ Start new vocab with the button below." });

  // --- Step 2: unfinished business before anything new.
  const continueBody = inProgress.length
    ? el("div", { class: "stack" }, ...inProgress.slice(0, 3).map((a) =>
        el("div", { class: "spread" },
          el("span", { class: "small" }, el("strong", { text: a.pack_id }), ` · ${a.activity} · ${a.progress[0]}/${a.progress[1]} answered`),
          el("button", { text: "Resume", onclick: () => resumeAttempt(a.file) }))))
    : el("p", { class: "small muted", text: "No test in progress." });

  // --- Step 3: the next lesson (or its unvalidated homework).
  let learnBody;
  if (next && next.kind === "homework") {
    learnBody = el("div", { class: "spread" },
      el("span", { class: "small" }, "Lesson ", el("strong", { text: `${next.lesson.order}. ${next.lesson.title}` }),
        " is done but not validated yet."),
      el("button", { class: "primary", text: "Do the homework", onclick: () => startHomework(next.pack.pack_id, next.lesson.id) }));
  } else if (next) {
    learnBody = el("div", { class: "spread" },
      el("span", { class: "small" }, "Next: ", el("strong", { text: `${next.lesson.order}. ${next.lesson.title}` }),
        el("span", { class: "muted", text: ` · ${next.pack.title}` })),
      el("button", { class: "primary", text: "Study", onclick: () => go(`#/lesson/${next.pack.pack_id}/${next.lesson.id}`) }));
  } else if ((data.courses || []).length) {
    learnBody = el("p", { class: "small muted", text: "Every lesson and its homework is complete. 축하합니다!" });
  } else {
    learnBody = el("p", { class: "small muted", text: "No courses found — import the bundled packs (topik-sim setup)." });
  }

  // --- Step 4: short daily output practice — weak items first when any exist.
  const weak = (data.practice && data.practice.weak) || [];
  const practiceBody = el("div", { class: "row" },
    weak.length ? el("button", {
      class: "primary", text: `Drill your ${weak.length} weak item(s)`,
      onclick: () => startMissesDrill(),
    }) : null,
    el("button", { text: "Dictation (듣기)", onclick: () => go("#/practice/dictation") }),
    el("button", { text: "Vocab recall (쓰기)", onclick: () => go("#/practice/recall") }),
    el("button", { class: "ghost", text: "All practice tools →", onclick: () => go("#/practice") }));

  // --- Course progress overview.
  const courseRows = (data.courses || []).map((pack) => {
    const done = pack.lessons.filter((l) => l.done).length;
    const validated = pack.lessons.filter((l) => l.homework).length;
    return el("div", { class: "spread course-row" },
      el("span", { class: "small" }, el("strong", { text: pack.title }),
        el("span", { class: "muted", text: ` · ${done}/${pack.lessons.length} lessons · ${validated} homework done` })),
      el("div", { class: "row" },
        el("div", { class: "progressbar slim", role: "img", "aria-label": `${done} of ${pack.lessons.length} lessons` },
          el("div", { style: `width:${(done / Math.max(1, pack.lessons.length)) * 100}%` })),
        el("button", { class: "ghost", text: "Open", onclick: () => go("#/courses") })));
  });

  const packCards = data.packs.map((pack) => {
    const best = pack.progress && pack.progress.best;
    return el("div", { class: "card stack" },
      el("div", { class: "spread" },
        el("strong", { text: pack.title || pack.pack_id }),
        el("span", { class: "pill", text: `${pack.question_count ?? "?"} q` })),
      el("div", { class: "small muted", text: [pack.pack_id, pack.difficulty].filter(Boolean).join(" · ") }),
      el("div", { class: "row" },
        el("button", { onclick: () => startExam({ pack: pack.pack_id }), text: "Take" }),
        best ? el("span", { class: "pill good", text: `best ${best[0]}/${best[1]}` }) : null,
      ));
  });

  // A true beginner (nothing attempted, nothing studied) needs to learn to
  // read before any card makes sense.
  const brandNew = !data.attempts.length &&
    !(data.courses || []).some((pack) => pack.lessons.some((lesson) => lesson.done));

  render(
    ...header("오늘의 학습 — today's study", "Review first, finish what you started, learn the next lesson, then practice."),
    brandNew ? el("div", { class: "card spread" },
      el("span", {}, el("strong", { text: "New to Korean? " }),
        "Learn to read Hangul first — 15 minutes, and every flashcard after it makes sense."),
      el("button", { class: "primary", text: "한글 Start here", onclick: () => go("#/practice/hangul") })) : null,
    el("div", { class: "card stack" },
      todayStep(1, "복습", "Review", reviewBody),
      todayStep(2, "이어하기", "Continue", continueBody),
      todayStep(3, "학습", "Learn", learnBody),
      todayStep(4, "연습", "Practice", practiceBody)),
    courseRows.length ? el("div", { class: "card stack" },
      el("h2", { text: "Course progress" }), ...courseRows) : null,
    el("h2", { text: "Mock exams — your weekly checkpoint" }),
    el("p", { class: "small muted", text: "Sit a full timed exam about once a week to measure progress; study through courses and practice the rest of the time." }),
    data.packs.length ? el("div", { class: "grid" }, packCards)
      : el("div", { class: "card spread" },
          el("span", { text: "No exams imported yet. The simulator ships six original TOPIK I mock exams." }),
          el("button", {
            class: "primary", text: "Import the bundled exams",
            onclick: async (event) => {
              event.target.disabled = true;
              try {
                const result = await api("POST", "/api/setup");
                toast(`Imported ${result.imported.length} pack(s).`);
                homeView();
              } catch (error) { toast(error.message); event.target.disabled = false; }
            },
          })),
  );
}

/* ------------------------------------------------------------ take/exam */

async function startComposeById(structureId) {
  const data = await api("GET", "/api/compose/lessons").catch(() => null);
  const lesson = data && data.lessons.find((l) => l.id === structureId);
  if (lesson) runCompose(lesson);
  else go("#/practice/compose");
}

async function startDrill(body) {
  try {
    const view = await api("POST", "/api/drill/start", body);
    state.views.set(view.id, view);
    go(`#/drill/${view.id}`);
  } catch (error) { toast(error.message); }
}

const LEVEL_LABELS = { 0: "Start here", 1: "Level 1 · 1급", 2: "Level 2 · 2급" };
const STATE_PILLS = {
  done: ["✓ done", "good"], started: ["◐ in progress", "on"],
  practiced: ["◐ practiced", "on"], new: ["not started", ""],
};

function vocabBand(unit) {
  const strip = el("div", { class: "vocab-band-strip" },
    ...unit.vocabulary.map((w) => el("span", { class: "vocab-pair" },
      el("span", { class: "ko", text: w.ko }),
      el("span", { class: "gloss", text: w.en }))));
  let expanded = false;
  const toggle = el("button", {
    class: "vocab-band-toggle", title: "Show every word in this stage",
    text: `단어 ${unit.vocabulary.length} ▸`,
    onclick: () => {
      expanded = !expanded;
      strip.classList.toggle("wrapped", expanded);
      toggle.textContent = `단어 ${unit.vocabulary.length} ${expanded ? "▾" : "▸"}`;
    },
  });
  return el("div", { class: "vocab-band" }, toggle, strip);
}

async function studyPathView() {
  const data = await api("GET", "/api/path");
  if (!data.units.length) {
    render(...header("Study path", ""), el("p", { class: "muted", text: "No curriculum found (content/curriculum)." }));
    return;
  }
  const nodes = [...header("Study path — TOPIK I",
    "A textbook-style scope and sequence: each stage names what you learn, and links straight to the lessons, homework, writing, and drills that teach it.")];
  let currentLevel = null;
  for (const unit of data.units) {
    if (unit.level !== currentLevel) {
      currentLevel = unit.level;
      nodes.push(el("h2", { text: LEVEL_LABELS[currentLevel] || `Level ${currentLevel}` }));
    }
    const [stateText, stateClass] = STATE_PILLS[unit.status.state] || STATE_PILLS.new;
    const buttons = [];
    const course = unit.courses[0];
    if (course) {
      buttons.push(el("button", { class: "primary", text: `Study lesson`, onclick: () => go(`#/lesson/${course.pack_id}/${course.course_id}`) }));
      buttons.push(el("button", { text: "Homework", onclick: () => startHomework(course.pack_id, course.course_id) }));
    }
    for (const dialogueId of unit.dialogues) {
      buttons.push(el("button", { text: `Talk: ${dialogueId}`, onclick: async () => {
        const dialogues = await api("GET", "/api/dialogues");
        const found = dialogues.dialogues.find((d) => d.id === dialogueId);
        if (found) runDialogue(found); else go("#/practice/dialogue");
      } }));
    }
    if (unit.compose_structures.length) {
      buttons.push(el("button", { text: "Write", onclick: () => startComposeById(unit.compose_structures[0].id) }));
    }
    for (const form of unit.conjugation.slice(0, 2)) {
      buttons.push(el("button", { class: "ghost", text: `Conjugate ${form.form}`, onclick: () => startDrill({ mode: "conjugate", form: form.form }) }));
    }
    if ((unit.vocabulary || []).length) {
      buttons.push(el("button", { class: "ghost", text: `단어 Cards (${unit.vocabulary.length})`, onclick: async () => {
        const deck = await api("GET", `/api/deck/flashcards?unit=${encodeURIComponent(unit.id)}`);
        state.deck = {
          title: `Vocabulary — ${unit.title}`, kind: "vocab",
          cards: deck.cards.map((c) => ({ front: c.ko, back: c.en, example: c.note || "", speech: c.ko })),
        };
        go("#/cards");
      } }));
      buttons.push(el("button", { class: "ghost", text: "단어 Recall", onclick: () => startDrill({ mode: "recall", unit: unit.id }) }));
    }
    for (const drill of (unit.drills || []).slice(0, 3)) {
      if (drill.mode === "hangul") buttons.push(el("button", { class: "ghost", text: "Read Hangul", onclick: () => go("#/practice/hangul") }));
      else if (drill.mode === "sounds") buttons.push(el("button", { class: "ghost", text: "Sound changes", onclick: () => go("#/practice/sounds") }));
      else if (drill.mode === "typing") buttons.push(el("button", { class: "ghost", text: "Typing", onclick: () => go("#/practice/typing") }));
      else if (drill.mode !== "conjugate") {
        buttons.push(el("button", { class: "ghost", text: drill.label || drill.mode,
          onclick: () => startDrill({ mode: drill.mode, category: drill.category, form: drill.form }) }));
      }
    }
    const progress = unit.status.lessons_total
      ? `${unit.status.lessons_done}/${unit.status.lessons_total} lessons · ${unit.status.homework_done}/${unit.status.lessons_total} homework`
      : "";
    nodes.push(el("div", { class: "card stack" },
      el("div", { class: "spread" },
        el("div", {}, el("strong", { text: `${unit.order}. ${unit.title}` }),
          unit.title_ko ? el("span", { class: "muted ko", text: `  ${unit.title_ko}` }) : null),
        el("div", { class: "row" },
          progress ? el("span", { class: "small muted", text: progress }) : null,
          el("span", { class: `pill ${stateClass}`, text: stateText }))),
      el("p", { class: "small muted", text: unit.scope }),
      unit.grammar.length ? el("div", { class: "chips" },
        ...unit.grammar.map((g) => el("span", { class: "chip ko", text: g }))) : null,
      el("div", { class: "row" }, ...buttons),
      // The stage's new words, printed along the bottom of the page the way a
      // textbook does. Collapsed by default so the band stays one line.
      (unit.vocabulary || []).length ? vocabBand(unit) : null));
  }
  render(...nodes);
}

async function takeView() {
  const [packsData, due] = await Promise.all([api("GET", "/api/packs"), api("GET", "/api/review/due")]);
  const packs = packsData.packs;
  const packSelect = el("select", {}, ...packs.map((p) => el("option", { value: p.pack_id, text: `${p.title || p.pack_id}` })));
  const sectionSelect = el("select", {}, el("option", { value: "", text: "Whole exam" }));
  const limitInput = el("input", { type: "number", min: "1", placeholder: "all" });

  // The sections belong to the chosen pack, so the list follows the selection.
  const loadSections = async () => {
    const chosen = sectionSelect.value;
    sectionSelect.replaceChildren(el("option", { value: "", text: "Whole exam" }));
    if (!packSelect.value) return;
    let sections = [];
    try { sections = (await api("GET", `/api/packs/${encodeURIComponent(packSelect.value)}/sections`)).sections; }
    catch { return; }  // leave "Whole exam" as the only choice
    for (const s of sections) {
      const minutes = s.time_limit_minutes ? `, ${s.time_limit_minutes} min` : "";
      sectionSelect.append(el("option", {
        value: s.section_id,
        text: `${s.title || s.section_id} — ${s.count} questions${minutes}`,
      }));
    }
    if ([...sectionSelect.options].some((o) => o.value === chosen)) sectionSelect.value = chosen;
  };
  packSelect.addEventListener("change", loadSections);
  loadSections();

  const dueRows = Object.entries(due.due || {}).map(([packId, count]) =>
    el("div", { class: "spread" },
      el("span", {}, el("strong", { text: packId }), ` — ${count} due`),
      el("button", { onclick: () => startExam({ pack: packId }, "/api/exam/review"), text: "Review" })));

  render(
    ...header("Take a test", "A full timed exam, one section, or a short untimed slice."),
    el("div", { class: "card stack" },
      el("label", { class: "field" }, "Exam pack", packSelect),
      el("div", { class: "row" },
        el("label", { class: "field" }, "Section", sectionSelect),
        el("label", { class: "field" }, "Question limit", limitInput)),
      el("div", { class: "row" },
        el("button", {
          class: "primary",
          onclick: () => startExam({
            pack: packSelect.value,
            section: sectionSelect.value || undefined,
            limit: limitInput.value ? Number(limitInput.value) : undefined,
          }),
          text: "Start",
        }),
        el("span", { class: "small muted", text: "Limited runs are untimed — good for a quick session." })),
    ),
    el("h2", { text: "Spaced review" }),
    dueRows.length ? el("div", { class: "card stack" }, dueRows)
      : el("p", { class: "muted", text: "Nothing is due for review. Misses from exams land here automatically." }),
  );
}

async function startExam(body, endpoint = "/api/exam/start") {
  try {
    const view = await api("POST", endpoint, body);
    state.views.set(view.id, view);
    go(`#/exam/${view.id}`);
  } catch (error) { toast(error.message); }
}

async function resumeAttempt(file) {
  try {
    const view = await api("POST", "/api/exam/resume", { file });
    state.views.set(view.id, view);
    go(`#/exam/${view.id}`);
  } catch (error) { toast(error.message); }
}

function formatClock(seconds) {
  const total = Math.max(0, Math.round(Math.abs(seconds)));
  const minutes = Math.floor(total / 60);
  const rest = String(total % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
}

async function examView(id) {
  let view = state.views.get(id);
  if (!view || view.done) view = await api("GET", `/api/activity/${id}`);
  state.views.set(id, view);

  const meta = el("div", { class: "exam-meta" },
    el("strong", { text: view.pack_title }),
    el("span", { text: view.activity }),
    el("span", { text: `Q ${Math.min(view.progress[0] + 1, view.progress[1])}/${view.progress[1]}` }),
    el("span", { text: `score ${view.score[0]}/${view.score[1]}` }),
  );
  let timerNode = null;
  if (view.remaining_seconds !== null && view.remaining_seconds !== undefined) {
    timerNode = el("span", { class: "timer" });
    let remaining = view.remaining_seconds;
    const paint = () => {
      timerNode.textContent = remaining >= 0 ? `${formatClock(remaining)} left` : `over by ${formatClock(remaining)}`;
      timerNode.classList.toggle("over", remaining < 0);
    };
    paint();
    const interval = setInterval(() => { remaining -= 1; paint(); }, 1000);
    onCleanup(() => clearInterval(interval));
    meta.append(timerNode);
  }

  const question = view.question;
  const body = el("div", { class: "card qcard stack" });
  const pauseButton = el("button", {
    class: "ghost", text: "⏸ Pause & save",
    onclick: async () => { await api("POST", `/api/activity/${id}/pause`).catch(() => {}); toast("Saved. Resume from Home."); go("#/"); },
  });

  render(el("div", { class: "spread" }, meta, pauseButton), body);

  if (!question) {
    body.append(el("p", { text: "This attempt has no open question." }),
      el("button", { onclick: () => go("#/"), text: "Home" }));
    return;
  }

  body.append(
    el("div", { class: "qnum", text: `Question ${question.number} of ${question.total} · ${question.skill || ""} · ${question.points} pt` }),
    el("p", { class: "prompt ko", text: question.prompt }),
  );

  if (question.has_image) {
    body.append(el("img", {
      class: "question-image",
      src: `/api/activity/${id}/image?qid=${encodeURIComponent(question.question_id || question.number)}`,
      alt: "문제 그림",
    }));
  }

  const transcriptSlot = el("div");
  body.append(transcriptSlot);
  if (question.passage) {
    transcriptSlot.append(el("div", { class: "passage ko", text: question.passage }));
  }

  if (question.listening && question.audio_parts > 0) {
    const urls = Array.from({ length: question.audio_parts }, (_, i) => `/api/activity/${id}/audio?part=${i}`);
    const status = el("span", { class: "small muted", text: "" });
    const playAll = async () => {
      status.textContent = "generating audio…";
      const ok = await playUrls(urls);
      status.textContent = "";
      if (!ok) {
        toast("Audio failed — transcript shown instead.");
        const data = await api("POST", `/api/activity/${id}/transcript`).catch(() => null);
        if (data) transcriptSlot.replaceChildren(el("div", { class: "passage ko", text: data.transcript }));
      }
    };
    body.append(el("div", { class: "audio-row row" },
      el("button", { onclick: playAll, text: "▶ Play audio" }),
      el("button", {
        title: "Play again at 3/4 speed", text: "🐢 Slower",
        onclick: () => playUrls(urls.map((u) => `${u}&slow=1`)),
      }),
      el("button", {
        class: "ghost", text: "Show transcript",
        onclick: async (e) => {
          const data = await api("POST", `/api/activity/${id}/transcript`);
          transcriptSlot.replaceChildren(el("div", { class: "passage ko", text: data.transcript }));
          e.target.remove();
        },
      }),
      status));
    playAll();
  }

  const hintSlot = el("div", { class: "stack hints" });
  const hintButton = el("button", {
    class: "ghost", text: "💡 Hint",
    onclick: async () => {
      const data = await api("POST", `/api/activity/${id}/hint`).catch((e) => ({ hint: null, message: e.message }));
      if (!data.hint) { toast(data.message || "No hints."); hintButton.disabled = true; return; }
      hintSlot.append(el("p", { class: "hint-line ko", text: `Hint ${data.shown}/${data.total}: ${data.hint}` }));
      if (data.shown >= data.total) hintButton.disabled = true;
    },
  });
  const inputArea = el("div", { class: "stack" });
  const feedbackSlot = el("div", { class: "stack" });
  body.append(el("div", { class: "row" }, hintButton), hintSlot, inputArea, feedbackSlot);
  let answered = false;
  const optionButtons = new Map();

  const submit = async (value) => {
    if (answered) return;
    let result;
    try { result = await api("POST", `/api/activity/${id}/answer`, { value }); }
    catch (error) { toast(error.message); return; }
    answered = true;
    hintButton.disabled = true;
    state.views.delete(id);
    // Error analysis in place: keep the options on screen, mark what was
    // picked and what was right, then teach below.
    for (const [optionId, button] of optionButtons) {
      button.disabled = true;
      if (result.correct_option_id && optionId === result.correct_option_id) button.classList.add("is-correct");
      else if (optionId === value && !result.correct) button.classList.add("is-picked-wrong");
    }
    const skipRow = inputArea.querySelector(".skip-row");
    if (skipRow) skipRow.remove();
    inputArea.querySelectorAll("textarea, .answer-actions button").forEach((n) => { n.disabled = true; });
    renderExamFeedback(id, view, question, result, feedbackSlot);
  };

  if (question.options && question.options.length) {
    inputArea.append(el("div", { class: "options" },
      ...question.options.map((option, index) => {
        const showKeyHint = String(option.id) !== String(index + 1);
        const button = el("button", { onclick: () => submit(option.id) },
          el("span", { class: "opt-id", text: option.id }),
          el("span", { class: "ko opt-text", text: option.text }),
          showKeyHint ? el("span", { class: "opt-key small muted", text: String(index + 1) }) : null);
        optionButtons.set(option.id, button);
        return button;
      })));
    inputArea.append(el("div", { class: "row skip-row" },
      el("button", { class: "ghost", onclick: () => submit(""), text: "Skip (counts as wrong)" })));

    // Answer from the keyboard: 1–9 by position, or the option letter itself.
    const keyHandler = (event) => {
      if (answered || event.metaKey || event.ctrlKey || event.altKey) return;
      const tag = event.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      const byNumber = Number(event.key);
      if (byNumber >= 1 && byNumber <= question.options.length) {
        submit(question.options[byNumber - 1].id);
        return;
      }
      const byLetter = question.options.find((o) => String(o.id).toLowerCase() === event.key.toLowerCase());
      if (byLetter) submit(byLetter.id);
    };
    document.addEventListener("keydown", keyHandler);
    onCleanup(() => document.removeEventListener("keydown", keyHandler));
  } else {
    const box = el("textarea", { placeholder: "Type your answer in Korean…", lang: "ko" });
    inputArea.append(box, el("div", { class: "row answer-actions" },
      el("button", { class: "primary", onclick: () => submit(box.value), text: "Submit" }),
      el("button", { class: "ghost", onclick: () => submit(""), text: "Skip" })));
    box.focus();
  }
}

function explanationNodes(explanation) {
  const nodes = [];
  if (explanation.summary) nodes.push(el("h3", { text: "Why" }), el("p", { class: "ko", text: explanation.summary }));
  if ((explanation.teaching_points || []).length) {
    nodes.push(el("h3", { text: "Teaching points" }),
      el("ul", { class: "tight" }, ...explanation.teaching_points.map((t) => el("li", { class: "ko", text: t }))));
  }
  if ((explanation.vocabulary || []).length) {
    nodes.push(el("h3", { text: "Vocabulary" }), el("table", { class: "vocab-table" },
      ...explanation.vocabulary.map((v) => el("tr", {},
        el("td", { class: "ko", text: v.ko }),
        el("td", { text: v.en + (v.note ? ` — ${v.note}` : "") }),
        el("td", {}, speakButton(v.ko))))));
  }
  if ((explanation.grammar || []).length) {
    nodes.push(el("h3", { text: "Grammar" }),
      ...explanation.grammar.map((g) => el("p", {},
        el("strong", { class: "ko", text: g.pattern }), ` — ${g.explanation || ""} `,
        g.example ? el("span", { class: "muted ko" }, `(${g.example})`, speakButton(g.example)) : null)));
  }
  if ((explanation.common_mistakes || []).length) {
    nodes.push(el("h3", { text: "Common mistakes" }),
      el("ul", { class: "tight" }, ...explanation.common_mistakes.map((m) => el("li", { class: "ko", text: m }))));
  }
  return nodes;
}

function renderExamFeedback(id, view, question, result, container) {
  const verdict = result.needs_review
    ? el("div", { class: "verdict", text: "✍ Saved for manual review" })
    : el("div", { class: `verdict ${result.correct ? "ok" : "no"}` },
        result.correct ? "✓ Correct" : "✗ Incorrect",
        el("span", { class: "pill", text: `${result.points[0]}/${result.points[1]} pt` }));

  const feedback = el("div", { class: "feedback stack" }, verdict);
  if (!result.correct) feedback.append(el("p", {}, "Correct answer: ", el("strong", { class: "ko", text: result.correct_answer })));
  if (result.transcript) {
    feedback.append(el("h3", { text: "Transcript" }),
      el("div", { class: "passage ko" }, result.transcript, speakButton(result.transcript)));
  }
  feedback.append(...explanationNodes(result.explanation || {}));

  if (result.finished) {
    const summary = result.summary || {};
    feedback.append(el("h3", { text: "Attempt complete" }),
      el("div", { class: "tiles" },
        el("div", { class: "tile" }, el("div", { class: "n", text: `${summary.score[0]}/${summary.score[1]}` }), el("div", { class: "t", text: "score" })),
        el("div", { class: "tile" }, el("div", { class: "n", text: String(summary.missed) }), el("div", { class: "t", text: "missed" })),
      ),
      el("div", { class: "row" },
        summary.missed ? el("button", {
          class: "primary", text: "Drill the misses",
          onclick: async () => {
            const drill = await api("POST", "/api/exam/drill", { file: summary.attempt_file });
            state.views.set(drill.id, drill);
            go(`#/exam/${drill.id}`);
          },
        }) : null,
        el("a", { class: "btn", href: `#/report/${summary.attempt_file}`, text: "Study report" }),
        state.courseFlow && summary.activity === "course"
          ? el("button", { class: "primary", text: "Finish lesson →", onclick: () => lessonComplete() })
          : el("button", { text: "Home", onclick: () => go("#/") }),
      ));
    if (summary.review_due) feedback.append(el("p", { class: "small muted", text: `${summary.review_due} item(s) now waiting in spaced review.` }));
  } else {
    feedback.append(el("div", { class: "row" },
      el("button", { class: "primary", text: "Continue →", onclick: () => examView(id) })));
  }
  container.replaceChildren(feedback);
  const btn = feedback.querySelector("button.primary, .btn");
  if (btn) btn.focus();
}

/* -------------------------------------------------------------- practice */

const PRACTICE_MODES = [
  { key: "hangul", name: "Read Hangul · 한글", desc: "Start here: every letter's sound and how blocks compose.", pack: "none" },
  { key: "sounds", name: "Sound changes · 발음", desc: "Why speech differs from spelling: 연음, 경음화, and more — with a drill.", pack: "none" },
  { key: "flashcards", name: "Flashcards", desc: "Vocabulary cards from a pack's teaching notes.", pack: "required" },
  { key: "grammar", name: "Grammar cards", desc: "Pattern on the front, what it does on the back.", pack: "optional" },
  { key: "vocab", name: "Vocabulary review (SRS)", desc: "Spaced repetition: due words plus a few new, scheduled by your answers. Pick a pack to review just that exam's words.", pack: "optional" },
  { key: "recall", name: "Vocab recall", desc: "See the English, type the Korean.", pack: "optional" },
  { key: "conjugate", name: "Conjugation", desc: "Conjugate verbs across tenses, connectives & modals; irregulars handled.", pack: "optional" },
  { key: "typing", name: "Typing", desc: "Korean keyboard trainer: jamo → syllables → words.", pack: "optional" },
  { key: "numbers", name: "Numbers", desc: "Sino & native numbers: dates, money, time, math — no digits.", pack: "none" },
  { key: "colors", name: "Colors · 색깔", desc: "See a color and name it in Korean, plus 빨간 사과 modifier forms.", pack: "none" },
  { key: "dictation", name: "Dictation", desc: "Listen and type what you hear.", pack: "required" },
  { key: "dialogue", name: "Conversation · 대화", desc: "Play a real-life scene and produce your own lines.", pack: "none" },
  { key: "compose", name: "Sentence writing", desc: "Learn a grammar structure, then write with it.", pack: "none" },
  { key: "facts", name: "Korea facts", desc: "Culture, history, food — with a Korean phrase.", pack: "none" },
];

async function practiceView() {
  // "What was that word again?" — search everything the packs teach.
  const searchInput = el("input", { type: "text", lang: "ko", placeholder: "Look something up: 학생, weather, 에서 …" });
  const resultsSlot = el("div", { class: "stack" });
  let searchTimer = null;
  const runLookup = async () => {
    const query = searchInput.value.trim();
    if (!query) { resultsSlot.replaceChildren(); return; }
    const data = await api("GET", `/api/lookup?q=${encodeURIComponent(query)}`).catch(() => null);
    if (!data) return;
    const nodes = [];
    for (const card of data.vocabulary) {
      nodes.push(el("div", { class: "spread lookup-row" },
        el("span", {}, el("strong", { class: "ko", text: card.ko }), `  ${card.en}${card.note ? " — " + card.note : ""}`,
          el("span", { class: "small muted", text: `  · ${card.pack_id}` })),
        speakButton(card.ko)));
    }
    for (const point of data.grammar) {
      nodes.push(el("div", { class: "lookup-row" },
        el("div", {}, el("strong", { class: "ko", text: point.pattern }), `  ${point.explanation}`,
          el("span", { class: "small muted", text: `  · ${point.pack_id}` })),
        point.example ? el("div", { class: "small muted ko" }, `예: ${point.example}`, speakButton(point.example)) : null));
    }
    resultsSlot.replaceChildren(nodes.length ? el("div", { class: "card stack" }, ...nodes)
      : el("p", { class: "small muted", text: "Nothing taught in your packs matches that." }));
  };
  searchInput.addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(runLookup, 250); });

  render(
    ...header("Practice", "Short focused tools around the same content as the exams."),
    searchInput, resultsSlot,
    el("div", { class: "grid" }, ...PRACTICE_MODES.map((mode) =>
      el("div", { class: "card stack" },
        el("strong", { text: mode.name }),
        el("span", { class: "small muted", text: mode.desc }),
        el("button", { onclick: () => go(`#/practice/${mode.key}`), text: "Start" })))),
  );
  searchInput.focus();
}

const NUMBER_CATEGORIES = ["mix", "sino", "native", "count", "money", "date", "time", "math", "phone", "ordinal"];
const COLOR_CATEGORIES = ["mix", "swatch", "word", "modifier", "shade", "object", "sino"];

async function hangulView() {
  const data = await api("GET", "/api/hangul");
  const jamoRow = (row) => el("div", { class: "spread lookup-row" },
    el("span", {}, el("strong", { class: "ko jamo-big", text: row.jamo }),
      row.name ? el("span", { class: "muted ko", text: `  ${row.name}` }) : null,
      `  ${row.sound}`));
  render(
    ...header("Read Hangul — 한글 읽기", "The from-zero on-ramp: sounds, blocks, and reading practice."),
    el("div", { class: "card stack" }, el("p", { text: data.how_blocks_work })),
    el("div", { class: "card stack" }, el("h2", { text: "Sounding out blocks" }),
      ...data.walkthroughs.map((example) => el("div", { class: "lookup-row" },
        el("div", { class: "row" },
          el("strong", { class: "ko jamo-big", text: example.word }),
          el("span", { class: "muted", text: `${example.parts}  →  ${example.reading}` }),
          speakButton(example.word)),
        el("div", { class: "small muted", text: example.note })))),
    el("div", { class: "card stack" }, el("h2", { text: "Consonants" }), ...data.consonants.map(jamoRow),
      el("h2", { text: "Tense consonants" }), ...data.tense_consonants.map(jamoRow)),
    el("div", { class: "card stack" }, el("h2", { text: "Vowels" }), ...data.vowels.map(jamoRow),
      el("h2", { text: "Compound vowels" }),
      el("p", { class: "ko", text: data.compound_vowels.map((v) => `${v.jamo} ${v.sound}`).join(" · ") })),
    el("div", { class: "card stack" },
      el("h2", { text: "Reading practice — click a block to hear it" }),
      el("div", { class: "syllable-grid" },
        ...data.syllable_grid.rows.flat().map((syllable) =>
          el("button", { class: "syllable-cell ko", text: syllable, onclick: () => say(syllable) }))),
      el("p", { class: "small muted", text: data.batchim }),
      el("p", { class: "small muted", text: data.romanization })),
    el("div", { class: "row" },
      el("button", { class: "primary", text: "Practice typing these →", onclick: () => go("#/practice/typing") }),
      el("button", { text: "Back to practice", onclick: () => go("#/practice") })),
  );
}

async function soundsView() {
  const data = await api("GET", "/api/sounds");
  render(
    ...header("Sound changes — 발음 규칙", "Learn these and native speech gets much clearer."),
    el("div", { class: "card stack" }, el("p", { text: data.intro }),
      el("div", { class: "row" },
        el("button", { class: "primary", text: "Practice all", onclick: () => startSoundsDrill() }))),
    ...data.rules.map((r) => el("div", { class: "card stack" },
      el("div", { class: "spread" },
        el("h2", { text: r.name }),
        el("button", { class: "ghost", text: "Drill this", onclick: () => startSoundsDrill(r.id) })),
      el("p", { class: "small muted", text: r.explain }),
      ...r.examples.map((ex) => el("div", { class: "spread lookup-row" },
        el("span", { class: "ko" }, el("strong", { text: ex.written }), " → ",
          el("span", { class: "muted", text: `[${ex.spoken}]` }), `  ${ex.gloss}`),
        speakButton(ex.spoken))))),
  );
}

async function startSoundsDrill(rule) {
  try {
    const view = await api("POST", "/api/drill/start", { mode: "sounds", rule });
    state.views.set(view.id, view);
    go(`#/drill/${view.id}`);
  } catch (error) { toast(error.message); }
}

function dialogueNormalize(text) {
  return text.normalize("NFC").split(/\s+/).join(" ").trim().replace(/[.?!~]+$/, "").trim();
}

async function dialogueView() {
  const data = await api("GET", "/api/dialogues");
  if (!data.dialogues.length) {
    render(...header("Conversations", "Situational speaking-into-writing practice."),
      el("p", { class: "muted", text: "No conversations found (content/dialogues)." }));
    return;
  }
  render(
    ...header("Conversations — 대화", "Play a real-life scene; the partner speaks, you produce your lines."),
    ...data.dialogues.map((d) => el("div", { class: "card spread" },
      el("div", {},
        el("div", {}, el("strong", { text: d.title }),
          d.title_ko ? el("span", { class: "muted ko", text: `  ${d.title_ko}` }) : null,
          d.level ? el("span", { class: "pill", text: `TOPIK ${d.level}` }) : null),
        el("div", { class: "small muted", text: d.situation || "" })),
      el("button", { class: "primary", text: "Start", onclick: () => runDialogue(d) }))),
  );
}

function runDialogue(dialogue) {
  const turns = dialogue.turns;
  const learnerTotal = turns.filter((t) => t.accepted || t.learner).length;
  let index = 0;
  let hits = 0;
  const log = el("div", { class: "stack dialogue-log" });
  const active = el("div", { class: "stack" });
  render(
    el("div", { class: "spread" },
      el("strong", {}, dialogue.title, dialogue.title_ko ? el("span", { class: "muted ko", text: `  ${dialogue.title_ko}` }) : null),
      el("button", { class: "ghost", text: "Stop", onclick: () => go("#/practice/dialogue") })),
    el("p", { class: "small muted", text: dialogue.situation || "" }),
    log, active,
  );

  function bubble(speaker, ko, en, mine) {
    return el("div", { class: `bubble ${mine ? "mine" : "theirs"}` },
      el("div", { class: "bubble-speaker", text: speaker || (mine ? "You" : "") }),
      el("div", { class: "ko bubble-ko" }, ko, speakButton(ko)),
      en ? el("div", { class: "small muted", text: en }) : null);
  }

  function step() {
    if (index >= turns.length) {
      active.replaceChildren(el("div", { class: "card stack" },
        el("h2", { text: "Conversation complete" }),
        el("p", {}, el("strong", { text: `${hits}/${learnerTotal}` }), " of your lines correct."),
        el("div", { class: "row" },
          el("button", { class: "primary", text: "Another conversation", onclick: () => go("#/practice/dialogue") }))));
      return;
    }
    const turn = turns[index];
    const mine = Boolean(turn.accepted || turn.learner);
    if (!mine) {
      log.append(bubble(turn.speaker, turn.ko, turn.en, false));
      if (state.tts.enabled) playUrls([`/api/say?text=${encodeURIComponent(turn.ko)}`]);
      index += 1;
      step();
      return;
    }
    const input = el("input", { type: "text", lang: "ko", placeholder: "Type your line in Korean…" });
    const slot = el("div", { class: "stack" });
    active.replaceChildren(el("div", { class: "card stack" },
      el("div", { class: "your-turn" }, el("strong", { text: `${turn.speaker || "You"} — your line` }),
        el("div", { class: "prompt", text: turn.en })),
      el("div", { class: "answer-row" }, input, el("button", { class: "primary", text: "Say it", onclick: check })),
      slot));
    input.focus();
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") check(); });

    function check() {
      const typed = dialogueNormalize(input.value);
      if (!typed) return;
      const accepted = (turn.accepted && turn.accepted.length ? turn.accepted : [turn.ko]);
      const exact = accepted.some((a) => dialogueNormalize(a) === typed);
      input.disabled = true;
      if (exact) {
        hits += 1;
        log.append(bubble(turn.speaker, turn.ko, null, true));
        active.replaceChildren();
        index += 1;
        step();
      } else {
        selfGrade(slot, {
          model: turn.ko,
          also: accepted.slice(1),
          question: "Was your line right?",
          onYes: () => { hits += 1; accept(); },
          onNo: accept,
        });
      }
      function accept() {
        log.append(bubble(turn.speaker, turn.ko, null, true));
        active.replaceChildren();
        index += 1;
        step();
      }
    }
  }
  step();
}

async function practiceConfigView(mode) {
  if (mode === "hangul") return hangulView();
  if (mode === "sounds") return soundsView();
  if (mode === "dialogue") return dialogueView();
  if (mode === "compose") return composeView();
  if (mode === "facts") return factsView();
  const spec = PRACTICE_MODES.find((m) => m.key === mode);
  if (!spec) { go("#/practice"); return; }

  const packs = (await api("GET", "/api/packs")).packs;
  // Vocabulary modes can also draw on a study-path stage's own word set, so
  // those are offered here rather than only on the study path itself.
  const unitScoped = mode === "recall" || mode === "vocab" || mode === "flashcards";
  let unitOptions = [];
  if (unitScoped) {
    try {
      unitOptions = (await api("GET", "/api/path")).units
        .filter((u) => (u.vocabulary || []).length)
        .map((u) => el("option", {
          value: `unit:${u.id}`,
          text: `${u.order}. ${u.title} — ${u.vocabulary.length} words`,
        }));
    } catch { unitOptions = []; }
  }
  const packSelect = el("select", {},
    spec.pack !== "required" ? el("option", { value: "", text: "every imported pack" }) : null,
    ...packs.map((p) => el("option", { value: p.pack_id, text: p.title || p.pack_id })),
    ...(unitOptions.length
      ? [el("optgroup", { label: "Study-path stages" }, ...unitOptions)]
      : []));
  const countInput = el("input", { type: "number", min: "1", placeholder: "default" });
  const categories = mode === "numbers" ? NUMBER_CATEGORIES : mode === "colors" ? COLOR_CATEGORIES : null;
  const categorySelect = categories
    ? el("select", {}, ...categories.map((c) => el("option", { value: c, text: c }))) : null;
  const advancedCheck = mode === "typing" ? el("input", { type: "checkbox" }) : null;
  let formSelect = null;
  if (mode === "conjugate") {
    const forms = (await api("GET", "/api/conjugation/forms")).forms;
    formSelect = el("select", {}, ...forms.map((f) => el("option", { value: f.key, text: f.display })));
  }

  const start = async () => {
    const chosen = packSelect.value || "";
    const unitValue = chosen.startsWith("unit:") ? chosen.slice(5) : undefined;
    const packValue = unitValue ? undefined : (chosen || undefined);
    try {
      if (mode === "flashcards") {
        const query = unitValue ? `unit=${encodeURIComponent(unitValue)}`
          : `pack=${encodeURIComponent(packValue)}`;
        const deck = await api("GET", `/api/deck/flashcards?${query}`);
        state.deck = {
          title: `Flashcards — ${deck.title}`, kind: "vocab",
          cards: deck.cards.map((c) => ({ front: c.ko, back: c.en, example: c.note || "", speech: c.ko })),
        };
        go("#/cards");
      } else if (mode === "grammar") {
        const query = packValue ? `?pack=${encodeURIComponent(packValue)}&count=${countInput.value || 20}` : `?count=${countInput.value || 20}`;
        const deck = await api("GET", `/api/deck/grammar${query}`);
        state.deck = {
          title: `Grammar — ${deck.title}`, kind: "grammar",
          cards: deck.cards.map((c) => ({ front: c.front, back: c.back, example: c.example || "", speech: c.speech || c.example })),
        };
        go("#/cards");
      } else {
        const view = await api("POST", "/api/drill/start", {
          mode, pack: packValue, unit: unitValue,
          count: countInput.value ? Number(countInput.value) : undefined,
          category: categorySelect && categorySelect.value !== "mix" ? categorySelect.value : undefined,
          advanced: advancedCheck && advancedCheck.checked ? true : undefined,
          form: formSelect ? formSelect.value : undefined,
        });
        state.views.set(view.id, view);
        go(`#/drill/${view.id}`);
      }
    } catch (error) { toast(error.message); }
  };

  const extras = [];
  if (mode === "colors") {
    // Learn before being drilled: every color with its modifier and 한자어 form.
    const sheetSlot = el("div");
    extras.push(el("div", { class: "row" },
      el("button", {
        text: "🎨 Learn the color words first",
        onclick: async (event) => {
          const sheet = await api("GET", "/api/colors/guide");
          event.target.remove();
          sheetSlot.replaceChildren(el("div", { class: "card stack" },
            el("h2", { text: "Colors" }),
            el("div", { class: "color-grid" }, ...sheet.colors.map((c) => el("div", { class: "color-chip" },
              el("div", { class: "color-chip-swatch", style: `background:${c.hex}` }),
              el("div", {},
                el("div", { class: "ko", text: c.ko }),
                el("div", { class: "small muted", text: c.en }),
                c.modifier ? el("div", { class: "small muted ko", text: `+명사: ${c.modifier}` }) : null,
                c.sino ? el("div", { class: "small muted ko", text: `한자어: ${c.sino}` }) : null)))),
            el("h2", { text: "ㅎ-irregular adjectives — the ㅎ drops before -ㄴ" }),
            el("p", { class: "ko", text: sheet.irregulars.map((r) => `${r.adjective} → ${r.modifier}`).join(" · ") }),
            el("h2", { text: "How to use them" }),
            el("table", { class: "list" }, ...sheet.usage.map((row) => el("tr", {},
              el("td", { text: row.context }),
              el("td", { class: "ko" }, el("span", { class: "pill on", text: row.example })),
              el("td", { class: "small muted", text: row.note }))))));
        },
      })), sheetSlot);
  }
  if (mode === "numbers") {
    // Learn before being drilled: both systems as tables, on demand.
    const sheetSlot = el("div");
    extras.push(el("div", { class: "row" },
      el("button", {
        text: "📖 Learn the two systems first",
        onclick: async (event) => {
          const sheet = await api("GET", "/api/numbers/guide");
          event.target.remove();
          sheetSlot.replaceChildren(el("div", { class: "card stack" },
            el("h2", { text: "Sino-Korean (일 이 삼 …) — dates, money, minutes, phone, math" }),
            el("p", { class: "ko", text: sheet.sino.map((r) => `${r.n.toLocaleString()} ${r.reading}`).join(" · ") }),
            el("h2", { text: "Native Korean (하나 둘 셋 …) — counting, age, the hour (1–99)" }),
            el("p", { class: "ko", text: sheet.native.map((r) => `${r.n} ${r.reading}`).join(" · ") }),
            el("p", { class: "small muted ko", text: "Before a counter: " + sheet.native.filter((r) => r.counter_form).map((r) => `${r.reading} → ${r.counter_form}`).join(" · ") }),
            el("h2", { text: "Common counters" }),
            el("p", { class: "ko", text: sheet.counters.map((c) => `${c.counter} ${c.meaning}`).join(" · ") }),
            el("h2", { text: "Which system?" }),
            el("table", { class: "list" }, ...sheet.usage.map((row) => el("tr", {},
              el("td", { text: row.context }),
              el("td", {}, el("span", { class: "pill on", text: row.system })),
              el("td", { class: "small muted ko", text: row.example }))))));
        },
      })), sheetSlot);
  }

  render(
    ...header(spec.name, spec.desc),
    el("div", { class: "card stack" },
      spec.pack !== "none" ? el("label", { class: "field" }, "Pack", packSelect) : null,
      mode !== "flashcards" ? el("label", { class: "field" }, "How many", countInput) : null,
      categorySelect ? el("label", { class: "field" }, "Category", categorySelect) : null,
      formSelect ? el("label", { class: "field" }, "Speech level", formSelect) : null,
      advancedCheck ? el("label", { class: "row" }, advancedCheck,
        " Advanced — real words and sentences only, meanings revealed after typing") : null,
      el("div", { class: "row" }, el("button", { class: "primary", onclick: start, text: "Start" }))),
    ...extras,
  );
}

/* --- server-graded drills (typing, numbers, recall, dictation, homework) */

async function drillView(id) {
  let view = state.views.get(id);
  if (!view) {
    try { view = await api("GET", `/api/activity/${id}`); }
    catch { toast("That practice session ended."); go("#/practice"); return; }
  }
  state.views.set(id, view);

  const total = view.progress[1];
  const done = view.progress[0];
  const barFill = el("div", { style: `width:${(done / total) * 100}%` });
  const container = el("div", { class: "card stack" });

  const headerRow = el("div", { class: "spread" },
    el("strong", { text: view.meta.lesson_title ? `${view.label} — ${view.meta.lesson_title}` : view.label }),
    el("div", { class: "row" },
      el("span", { class: "pill", text: `${done}/${total} · ${view.hits} ✓` }),
      el("button", {
        class: "ghost", text: "Stop",
        onclick: async () => { await api("POST", `/api/activity/${id}/pause`).catch(() => {}); go("#/practice"); },
      })));

  render(headerRow, el("div", { class: "progressbar" }, barFill), container);

  if (view.done || !view.item) {
    container.append(el("p", { text: "Session finished." }), el("button", { onclick: () => go("#/practice"), text: "Back to practice" }));
    return;
  }

  const item = view.item;
  if (view.meta.objectives && item.index === 1) {
    container.append(el("ul", { class: "tight small muted" }, ...view.meta.objectives.map((o) => el("li", { text: o }))));
  }
  container.append(el("div", { class: "drill-show ko", text: item.show }));
  if (item.swatch) {
    container.append(el("div", {
      class: `color-swatch${item.swatch_dark ? " on-dark" : ""}`,
      style: `background:${item.swatch}`,
      title: item.swatch,
    }));
  }
  if (item.audio) {
    container.append(el("div", { class: "row" },
      el("button", { onclick: () => playUrls([`/api/activity/${id}/audio`]), text: "▶ Play" }),
      item.dictation ? el("button", {
        title: "Play again at 3/4 speed", text: "🐢 Slower",
        onclick: () => playUrls([`/api/activity/${id}/audio?slow=1`]),
      }) : null,
      item.dictation ? el("span", { class: "small muted", text: "Listen, then type what you heard." }) : null));
    if (item.dictation) playUrls([`/api/activity/${id}/audio`]);
  }
  if (item.kind === "pattern") {
    container.append(el("p", { class: "small muted", text: GRAMMAR_LEGEND }));
  }

  const input = el("input", { type: "text", lang: "ko", placeholder: item.options ? "Type the number of your choice (or the answer)" : "Type your answer…" });
  const feedbackSlot = el("div", { class: "feedback-line stack" });

  const submit = async (value) => {
    if (!value.trim()) return;
    let result;
    try { result = await api("POST", `/api/activity/${id}/answer`, { value }); }
    catch (error) { toast(error.message); return; }
    if (result.retry) {
      feedbackSlot.replaceChildren(el("p", { class: "muted", text: result.message }));
      input.value = ""; input.focus();
      return;
    }
    state.views.delete(id);
    input.disabled = true;
    container.querySelectorAll(".drill-options button, .answer-row button").forEach((b) => { b.disabled = true; });

    const nodes = [];
    nodes.push(el("div", { class: `verdict ${result.correct ? "ok" : "no"}` },
      result.correct ? "✓ Correct" : "✗ Incorrect"));
    if (!result.correct || item.dictation) {
      nodes.push(el("p", {}, "Answer: ", el("span", { class: "expected ko", text: result.expected })));
    }
    if (result.accuracy !== undefined) nodes.push(el("p", { class: "small muted", text: `Accuracy ${(result.accuracy * 100).toFixed(0)}%` }));
    if (result.feedback) nodes.push(el("div", { class: "diff", text: result.feedback.join("\n") }));
    if (result.meaning) nodes.push(el("p", { class: "muted ko", text: result.meaning }));
    if (result.speech) nodes.push(el("div", { class: "row" }, speakButton(result.speech, "🔊 Hear it")));
    if (result.keys) nodes.push(el("p", { class: "keys", text: result.keys }));

    if (result.finished) {
      const summary = result.summary;
      nodes.push(el("h3", { text: "Done" }),
        el("p", {}, el("strong", { text: `${summary.hits}/${summary.total}` }), " correct."));
      if (summary.missed.length) {
        nodes.push(el("div", { class: "chips" }, ...summary.missed.map((m) => el("span", { class: "chip ko", text: m }))));
      }
      if (summary.homework) {
        nodes.push(el("p", { class: "small muted", text: `Homework saved — best ${summary.homework.best_correct}/${summary.homework.best_total} over ${summary.homework.runs} run(s).` }));
      }
      const again = view.meta.course_id
        ? el("button", { class: "primary", text: "Back to the course", onclick: () => go("#/courses") })
        : el("button", { class: "primary", text: "Back to practice", onclick: () => go("#/practice") });
      nodes.push(el("div", { class: "row" }, again));
    } else {
      const next = el("button", { class: "primary", text: "Next →", onclick: () => drillView(id) });
      nodes.push(el("div", { class: "row" }, next));
      setTimeout(() => next.focus(), 0);
    }
    feedbackSlot.replaceChildren(...nodes);
  };

  if (item.options) {
    container.append(el("div", { class: "drill-options options" },
      ...item.options.map((option, index) => el("button", { onclick: () => submit(String(index + 1)) },
        el("span", { class: "opt-id", text: String(index + 1) }), el("span", { class: "ko", text: option })))));
  }
  container.append(
    el("div", { class: "answer-row" }, input,
      el("button", { class: "primary", onclick: () => submit(input.value), text: "Answer" }),
      item.audio && !item.dictation ? speakButton(null) : null),
    feedbackSlot,
  );
  if (item.audio && !item.dictation) {
    const speak = container.querySelector(".answer-row button.ghost");
    if (speak) speak.onclick = () => playUrls([`/api/activity/${id}/say`]);
  }
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") submit(input.value); });
  input.focus();
}

/* -------------------------------------------------- client-side card runs */

function cardsView() {
  const deck = state.deck;
  if (!deck || !deck.cards.length) { go("#/practice"); return; }
  let index = 0;
  let known = 0;
  const missed = [];

  const container = el("div", { class: "stack" });
  render(
    el("div", { class: "spread" },
      el("strong", { text: deck.title }),
      el("button", { class: "ghost", text: "Stop", onclick: () => finish(true) })),
    deck.kind === "grammar" ? el("p", { class: "small muted", text: GRAMMAR_LEGEND }) : null,
    container,
  );

  function showCard() {
    const card = deck.cards[index];
    let flipped = false;
    // Two physical faces; flipping rotates the inner wrapper in 3D.
    const face = el("div", { class: "flashcard card" },
      el("div", { class: "flip-inner" },
        el("div", { class: "flip-face flip-front" },
          el("div", {},
            el("div", { class: "front ko", text: card.front }),
            el("div", { class: "flip-hint", text: "click or press Enter to flip" }))),
        el("div", { class: "flip-face flip-back" },
          el("div", {},
            el("div", { class: "front ko", text: card.front }),
            el("div", { class: "back-main", text: card.back }),
            card.example ? el("div", { class: "example ko", text: card.example }) : null))));
    const controls = el("div", { class: "row" },
      el("span", { class: "pill", text: `${index + 1}/${deck.cards.length}` }),
      speakButton(card.speech, "🔊 Speak"));

    const flip = () => {
      if (flipped) return;
      flipped = true;
      face.classList.add("flipped");
      controls.append(
        el("button", { class: "primary", text: "✓ Knew it (y)", onclick: () => gradeCard(true) }),
        el("button", { text: "✗ Again (n)", onclick: () => gradeCard(false) }));
    };
    face.addEventListener("click", flip);

    const keyHandler = (event) => {
      if (event.target.tagName === "INPUT" || event.target.tagName === "TEXTAREA") return;
      if (event.key === "Enter" && !flipped) flip();
      else if (flipped && (event.key === "y" || event.key === "Y")) gradeCard(true);
      else if (flipped && (event.key === "n" || event.key === "N")) gradeCard(false);
    };
    document.addEventListener("keydown", keyHandler);
    onCleanup(() => document.removeEventListener("keydown", keyHandler));

    function gradeCard(ok) {
      document.removeEventListener("keydown", keyHandler);
      if (ok) known += 1; else missed.push(card.front);
      index += 1;
      if (index >= deck.cards.length) finish(false); else showCard();
    }
    container.replaceChildren(face, controls);
  }

  function finish(early) {
    const done = index;
    container.replaceChildren(el("div", { class: "card stack" },
      el("h2", { text: early ? `Stopped after ${done}/${deck.cards.length}` : "Deck finished" }),
      done ? el("p", {}, el("strong", { text: `${known}/${done}` }), " known.") : null,
      missed.length ? el("div", { class: "chips" }, ...missed.map((m) => el("span", { class: "chip ko", text: m }))) : null,
      el("div", { class: "row" },
        state.deck && state.deck.onDone
          ? el("button", { class: "primary", text: "Continue →", onclick: () => { const cb = state.deck.onDone; state.deck = null; cb(); } })
          : el("button", { class: "primary", text: "Back to practice", onclick: () => { state.deck = null; go("#/practice"); } })),
    ));
  }
  showCard();
}

/* --------------------------------------------------------------- compose */

async function composeView() {
  const data = await api("GET", "/api/compose/lessons");
  const search = el("input", { type: "text", placeholder: "Filter: 싶, past, -고 …" });
  const listSlot = el("div", { class: "stack" });

  const paint = () => {
    const query = search.value.trim().toLowerCase();
    const lessons = data.lessons.filter((l) =>
      !query || `${l.id} ${l.pattern} ${l.meaning}`.toLowerCase().includes(query));
    listSlot.replaceChildren(...lessons.slice(0, 40).map((lesson) =>
      el("div", { class: "lesson-row" },
        el("div", { class: "lesson-main" },
          el("div", { class: "lesson-title ko", text: `${lesson.pattern} — ${lesson.meaning}` }),
          el("div", { class: "small muted ko", text: lesson.example || "" })),
        el("button", { text: "Write", onclick: () => runCompose(lesson) }))));
  };
  search.addEventListener("input", paint);
  render(...header("Sentence writing", "Pick a grammar structure; it is taught first, then you write with it."),
    el("div", { class: "card stack" }, search, listSlot));
  paint();
}

function composeNormalize(text) {
  return text.normalize("NFC").split(/\s+/).join(" ").trim().replace(/[.?!]+$/, "").trim();
}

function runCompose(lesson) {
  const sentences = [...lesson.sentences];
  let index = 0;
  let hits = 0;
  const container = el("div", { class: "stack" });
  render(
    el("div", { class: "spread" },
      el("strong", { class: "ko", text: `Writing — ${lesson.pattern}` }),
      el("button", { class: "ghost", text: "Stop", onclick: () => go("#/practice/compose") })),
    el("div", { class: "card stack" },
      el("p", { class: "ko" }, el("strong", { text: lesson.pattern }), ` — ${lesson.meaning}`),
      lesson.example ? el("p", { class: "muted ko" }, lesson.example, lesson.example_en ? ` (${lesson.example_en})` : "", speakButton(lesson.example)) : null,
      lesson.note ? el("p", { class: "small muted", text: lesson.note.replace(/\*\*/g, "") }) : null),
    container);

  function ask() {
    if (index >= sentences.length) {
      container.replaceChildren(el("div", { class: "card stack" },
        el("h2", { text: "Done" }), el("p", {}, el("strong", { text: `${hits}/${sentences.length}` }), " right."),
        el("button", { class: "primary", text: "Pick another structure", onclick: () => go("#/practice/compose") })));
      return;
    }
    const sentence = sentences[index];
    const input = el("input", { type: "text", lang: "ko", placeholder: "Write it in Korean…" });
    const slot = el("div", { class: "stack" });
    container.replaceChildren(el("div", { class: "card stack" },
      el("span", { class: "pill", text: `${index + 1}/${sentences.length}` }),
      el("p", { class: "prompt", text: sentence.english }),
      el("div", { class: "answer-row" }, input, el("button", { class: "primary", text: "Check", onclick: check })),
      slot));
    input.focus();
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") check(); });

    function check() {
      if (input.disabled) return;
      const typed = composeNormalize(input.value);
      if (!typed) return;
      const accepted = (sentence.accepted && sentence.accepted.length ? sentence.accepted : [sentence.korean]);
      const exact = accepted.some((a) => composeNormalize(a) === typed);
      input.disabled = true;
      if (exact) {
        hits += 1;
        const next = el("button", { class: "primary", text: "Next →", onclick: () => { index += 1; ask(); } });
        slot.replaceChildren(
          el("div", { class: "verdict ok", text: "✓ Correct" },),
          el("p", { class: "ko" }, sentence.korean, speakButton(sentence.korean)),
          next);
        next.focus();
      } else {
        // Self-grade must be a deliberate choice: no button is focused (a
        // stray Enter must not silently mark it correct) and the promised
        // y/n keys work.
        selfGrade(slot, {
          model: sentence.korean,
          also: accepted.slice(1),
          question: "Was your sentence right?",
          onYes: () => { hits += 1; index += 1; ask(); },
          onNo: () => { index += 1; ask(); },
        });
      }
    }
  }
  ask();
}

/* ----------------------------------------------------------------- facts */

async function factsView() {
  const data = await api("GET", "/api/facts");
  const categories = [...new Set(data.facts.map((f) => f.category))].sort();
  const select = el("select", {}, el("option", { value: "", text: "any category" }),
    ...categories.map((c) => el("option", { value: c, text: c })));
  const slot = el("div");

  const pick = () => {
    const pool = data.facts.filter((f) => !select.value || f.category === select.value);
    if (!pool.length) { slot.replaceChildren(el("p", { class: "muted", text: "No facts in that category." })); return; }
    const fact = pool[Math.floor(Math.random() * pool.length)];
    slot.replaceChildren(el("div", { class: "card stack" },
      el("span", { class: "pill", text: fact.category }),
      el("h2", { text: fact.title }),
      el("p", { text: fact.fact }),
      fact.korean ? el("p", { class: "ko" }, el("strong", { text: fact.korean }), ` — ${fact.korean_en || ""}`, speakButton(fact.korean)) : null,
      (fact.vocabulary || []).length ? el("table", { class: "vocab-table" },
        ...fact.vocabulary.map((v) => el("tr", {}, el("td", { class: "ko", text: v.ko }), el("td", { text: v.en }), el("td", {}, speakButton(v.ko))))) : null,
      fact.note ? el("p", { class: "small muted", text: fact.note }) : null,
    ));
  };
  render(...header("Korea facts", "A quick cultural break — with the Korean to go with it."),
    el("div", { class: "row" }, select, el("button", { class: "primary", text: "Another fact", onclick: pick })), slot);
  pick();
}

/* --------------------------------------------------------------- courses */

async function coursesView() {
  const data = await api("GET", "/api/courses");
  if (!data.packs.length) {
    render(...header("Courses", "Guided lessons over the bundled packs."),
      el("p", { class: "muted", text: "No courses found — import the bundled packs first (topik-sim setup)." }));
    return;
  }
  render(
    ...header("Courses", "Each lesson teaches vocabulary and grammar, runs its exam questions, then homework validates it."),
    ...data.packs.map((pack) => el("div", { class: "card" },
      el("h2", { text: pack.title }),
      ...pack.lessons.map((lesson) => el("div", { class: "lesson-row" },
        el("div", { class: "lesson-mark", text: lesson.done ? "✓" : "" }),
        el("div", { class: "lesson-main" },
          el("div", { class: "lesson-title" }, `${lesson.order}. ${lesson.title} `,
            lesson.title_ko ? el("span", { class: "muted ko", text: lesson.title_ko }) : null),
          el("div", { class: "small muted", text: `${lesson.counts.vocabulary} words · ${lesson.counts.grammar} grammar · ${lesson.counts.questions} questions` })),
        lesson.homework
          ? el("span", { class: "pill good", text: `homework ${lesson.homework.best_correct}/${lesson.homework.best_total}` })
          : el("span", { class: "pill", text: "homework –" }),
        el("button", { text: lesson.done ? "Redo" : "Study", onclick: () => go(`#/lesson/${pack.pack_id}/${lesson.id}`) }),
        el("button", {
          class: "ghost", text: "Homework",
          onclick: () => startHomework(pack.pack_id, lesson.id),
        }))))),
  );
}

async function startHomework(packId, courseId) {
  try {
    const view = await api("POST", "/api/drill/start", { mode: "homework", pack: packId, course_id: courseId });
    state.views.set(view.id, view);
    go(`#/drill/${view.id}`);
  } catch (error) { toast(error.message); }
}

async function startMissesDrill() {
  try {
    const view = await api("POST", "/api/drill/start", { mode: "misses" });
    state.views.set(view.id, view);
    go(`#/drill/${view.id}`);
  } catch (error) { toast(error.message); }
}

async function startVocab() {
  try {
    const view = await api("POST", "/api/drill/start", { mode: "vocab" });
    state.views.set(view.id, view);
    go(`#/drill/${view.id}`);
  } catch (error) { toast(error.message); }
}

async function lessonView(packId, courseId) {
  const data = await api("GET", `/api/courses/lesson/${courseId}?pack=${encodeURIComponent(packId)}`);
  const lesson = data.lesson;
  state.courseFlow = { packId, courseId, lesson };

  render(
    ...header(`Lesson ${lesson.order}: ${lesson.title}`, lesson.title_ko || ""),
    el("div", { class: "card stack" },
      el("ul", { class: "tight" }, ...(lesson.objectives || []).map((o) => el("li", { text: o }))),
      el("p", { class: "small muted", text: `1. Vocabulary (${(lesson.new_vocabulary || []).length}) → 2. Grammar (${(lesson.new_grammar || []).length}) → 3. Exam questions (${(lesson.question_ids || []).length}) → 4. Homework` }),
      el("div", { class: "row" },
        el("button", { class: "primary", text: "Start lesson", onclick: () => lessonVocabStep() }),
        el("button", { text: "Skip to homework", onclick: () => startHomework(packId, courseId) }),
        el("button", { class: "ghost", text: "Back", onclick: () => go("#/courses") }))),
  );
}

function lessonVocabStep() {
  const flow = state.courseFlow;
  const vocab = flow.lesson.new_vocabulary || [];
  if (!vocab.length) return lessonGrammarStep();
  state.deck = {
    title: `Vocabulary — ${flow.lesson.title}`, kind: "vocab",
    cards: vocab.map((v) => ({ front: v.ko, back: v.en, example: "", speech: v.ko })),
    onDone: () => lessonGrammarStep(),
  };
  go("#/cards");
}

function lessonGrammarStep() {
  const flow = state.courseFlow;
  const grammar = flow.lesson.new_grammar || [];
  if (!grammar.length) return lessonExamStep();
  state.deck = {
    title: `Grammar — ${flow.lesson.title}`, kind: "grammar",
    cards: grammar.map((g) => ({ front: g.pattern, back: g.explanation, example: g.example || "", speech: g.example || g.pattern })),
    onDone: () => lessonExamStep(),
  };
  go("#/cards");
}

async function lessonExamStep() {
  const flow = state.courseFlow;
  try {
    const view = await api("POST", "/api/exam/course", { pack: flow.packId, course_id: flow.courseId });
    state.views.set(view.id, view);
    go(`#/exam/${view.id}`);
  } catch (error) { toast(error.message); go("#/courses"); }
}

function lessonComplete() {
  const flow = state.courseFlow;
  state.courseFlow = null;
  render(
    ...header("Lesson complete ✓", flow.lesson.title),
    el("div", { class: "card stack" },
      flow.lesson.review ? el("p", { text: flow.lesson.review }) : null,
      el("p", { class: "muted", text: "Solidify it: the homework validates this lesson's vocabulary and grammar." }),
      el("div", { class: "row" },
        el("button", { class: "primary", text: "Do the homework", onclick: () => startHomework(flow.packId, flow.courseId) }),
        el("button", { text: "Back to courses", onclick: () => go("#/courses") }))),
  );
}

/* -------------------------------------------------------------- progress */

async function progressView() {
  const [stats, attemptsData, practice, coursesData] = await Promise.all([
    api("GET", "/api/stats"),
    api("GET", "/api/attempts"),
    api("GET", "/api/practice/log"),
    api("GET", "/api/courses"),
  ]);
  const attempts = attemptsData.attempts;

  const skillRows = Object.entries(stats.skills || {}).map(([skill, s]) => {
    const pct = s.total ? Math.round((s.correct / s.total) * 100) : 0;
    return el("div", { class: "meter-row" },
      el("span", { class: "small", text: skill }),
      el("div", { class: "meter", role: "img", "aria-label": `${skill} accuracy ${pct}%` }, el("div", { style: `width:${pct}%` })),
      el("span", { class: "val", text: `${pct}%` }));
  });

  const trend = (stats.trend || []).slice(-12);
  const maxScore = Math.max(1, ...trend.map((t) => t.max_score || 1));
  const trendBars = trend.map((t) => {
    const pct = t.max_score ? Math.round((t.score / t.max_score) * 100) : 0;
    return el("div", {
      class: "bar",
      style: `height:${Math.max(4, (t.score / maxScore) * 100)}%`,
      title: `${t.pack_ref} · ${t.score}/${t.max_score} (${pct}%) · ${String(t.completed_at || "").slice(0, 10)}`,
      role: "img", "aria-label": `${t.pack_ref}: ${t.score} of ${t.max_score}`,
    });
  });

  const attemptRows = attempts.slice(0, 20).map((a) => el("tr", {},
    el("td", { text: a.pack_id }),
    el("td", { text: a.activity }),
    el("td", { text: `${a.progress[0]}/${a.progress[1]}` }),
    el("td", {}, el("span", { class: `pill ${a.status === "completed" ? "good" : "on"}`, text: a.status })),
    el("td", {}, el("div", { class: "row" },
      a.status !== "completed" ? el("button", { class: "ghost", text: "Resume", onclick: () => resumeAttempt(a.file) }) : null,
      a.status === "completed" ? el("button", {
        class: "ghost", text: "Drill",
        onclick: async () => {
          try {
            const drill = await api("POST", "/api/exam/drill", { file: a.file });
            state.views.set(drill.id, drill); go(`#/exam/${drill.id}`);
          } catch (error) { toast(error.message); }
        },
      }) : null,
      a.status === "completed" ? el("a", { class: "btn ghost", href: `#/report/${a.file}`, text: "Report" }) : null,
    ))));

  // --- Course & homework ledger: what has been taught vs. validated.
  const courseLedger = (coursesData.packs || []).map((pack) => {
    const done = pack.lessons.filter((l) => l.done).length;
    const withHw = pack.lessons.filter((l) => l.homework);
    const hwNote = withHw.length
      ? `${withHw.length} homework · avg best ${Math.round(
          (withHw.reduce((s, l) => s + l.homework.best_correct / Math.max(1, l.homework.best_total), 0) / withHw.length) * 100)}%`
      : "no homework yet";
    return el("div", { class: "meter-row" },
      el("span", { class: "small", text: pack.title }),
      el("div", { class: "meter", role: "img", "aria-label": `${done} of ${pack.lessons.length} lessons finished` },
        el("div", { style: `width:${(done / Math.max(1, pack.lessons.length)) * 100}%` })),
      el("span", { class: "val", text: `${done}/${pack.lessons.length}` }),
      el("span", { class: "small muted", text: hwNote }));
  });

  // --- Practice ledger: the runs that used to vanish.
  const practiceSummary = practice.summary || {};
  const practiceRows = (practice.runs || []).slice(0, 12).map((run) => el("tr", {},
    el("td", { text: (run.at || "").slice(0, 10) }),
    el("td", { text: run.label }),
    el("td", { text: `${run.hits}/${run.total}` }),
    el("td", { class: "small muted ko", text: (run.missed || []).slice(0, 4).join(" · ") })));

  const weakChips = (practice.weak || []).map((entry) =>
    el("span", { class: "chip ko", title: `missed ${entry.count}×`, text: `${entry.item} ×${entry.count}` }));

  render(
    ...header("Progress", "Exams, courses, homework, and practice — the whole ledger, kept locally."),
    el("div", { class: "tiles" },
      el("div", { class: "tile" }, el("div", { class: "n", text: String(stats.attempt_count || 0) }), el("div", { class: "t", text: "completed attempts" })),
      el("div", { class: "tile" }, el("div", { class: "n", text: String(practiceSummary.runs || 0) }), el("div", { class: "t", text: "practice runs" })),
      practiceSummary.accuracy !== null && practiceSummary.accuracy !== undefined
        ? el("div", { class: "tile" }, el("div", { class: "n", text: `${Math.round(practiceSummary.accuracy * 100)}%` }), el("div", { class: "t", text: "practice accuracy" })) : null,
      ...Object.entries(stats.packs || {}).slice(0, 2).map(([packId, p]) =>
        el("div", { class: "tile" }, el("div", { class: "n", text: `${p.best[0]}/${p.best[1]}` }), el("div", { class: "t", text: `best · ${packId}` }))),
    ),
    skillRows.length ? el("div", { class: "card" }, el("h2", { text: "Accuracy by skill" }), ...skillRows) : null,
    courseLedger.length ? el("div", { class: "card" }, el("h2", { text: "Courses & homework" }), ...courseLedger) : null,
    (practice.weak || []).length ? el("div", { class: "card stack" },
      el("div", { class: "spread" },
        el("h2", { text: "Weak items — 자주 틀리는 것" }),
        el("button", { class: "primary", text: "Drill these now", onclick: () => startMissesDrill() })),
      el("div", { class: "chips" }, ...weakChips),
      el("p", { class: "small muted", text: "Counted from your recent practice misses. Items drop off once you stop missing them." })) : null,
    trend.length ? el("div", { class: "card" },
      el("h2", { text: "Recent attempts (score)" }),
      el("div", { class: "trend" }, ...trendBars),
      el("p", { class: "small muted", text: "Hover a bar for the pack and date. Full detail in the table below." })) : null,
    practiceRows.length ? el("div", { class: "card" },
      el("h2", { text: "Practice history" }),
      el("table", { class: "list" },
        el("tr", {}, el("th", { text: "when" }), el("th", { text: "what" }), el("th", { text: "score" }), el("th", { text: "missed" })),
        ...practiceRows)) : null,
    el("h2", { text: "Attempts" }),
    attempts.length ? el("table", { class: "list" },
      el("tr", {}, el("th", { text: "pack" }), el("th", { text: "activity" }), el("th", { text: "progress" }), el("th", { text: "status" }), el("th", { text: "" })),
      ...attemptRows)
      : el("p", { class: "muted", text: "No attempts yet — take a test first." }),
  );
}

async function reportView(file) {
  const data = await api("GET", `/api/report?file=${encodeURIComponent(file)}`);
  render(
    el("div", { class: "spread" },
      el("h1", { text: "Study report" }),
      el("div", { class: "row" },
        el("button", {
          text: "⬇ Download .md",
          onclick: () => {
            const blob = new Blob([data.markdown], { type: "text/markdown" });
            const link = el("a", { href: URL.createObjectURL(blob), download: `report-${file.replace(".json", "")}.md` });
            link.click();
          },
        }),
        el("button", { class: "ghost", text: "Back", onclick: () => history.back() }))),
    el("div", { class: "card report-md", text: data.markdown }),
  );
}

/* -------------------------------------------------------------- settings */

function updateTtsPill() {
  const pill = document.getElementById("tts-pill");
  const on = state.tts.enabled && !state.tts.failed;
  pill.textContent = on ? `TTS ${state.tts.provider || "on"}` : "TTS off";
  pill.classList.toggle("on", Boolean(on));
}

async function settingsView() {
  const [tts, doctor, keyboard] = await Promise.all([
    api("GET", "/api/tts"), api("GET", "/api/doctor"), api("GET", "/api/keyboard")]);
  state.tts = tts;
  updateTtsPill();

  const keyboardRows = keyboard.rows.map((row) => el("div", { class: "kbd-row" },
    ...row.map((cell) => cell === null
      ? el("span", { class: "kbd-gap" })
      : el("span", { class: "keycap" },
          el("span", { class: "keycap-jamo ko", text: cell.jamo }),
          cell.shift ? el("span", { class: "keycap-shift ko", text: cell.shift }) : null,
          el("span", { class: "keycap-key", text: cell.key })))));

  const enabled = el("input", { type: "checkbox" });
  enabled.checked = tts.enabled;
  const volume = el("input", { type: "range", min: "0.1", max: "1.5", step: "0.05", value: String(tts.volume) });
  const speed = el("input", { type: "range", min: "0.5", max: "1.5", step: "0.05", value: String(tts.speed) });
  const voice = el("input", { type: "text", value: tts.voice || "", placeholder: "e.g. F1, M1" });
  const sayBox = el("input", { type: "text", lang: "ko", placeholder: "안녕하세요 — type anything, hear it spoken" });

  const apply = async () => {
    try {
      state.tts = await api("POST", "/api/tts", {
        enabled: enabled.checked,
        volume: Number(volume.value),
        speed: Number(speed.value),
        voice: voice.value.trim() || undefined,
      });
      updateTtsPill();
      toast("Speech settings updated.");
    } catch (error) { toast(error.message); }
  };

  render(
    ...header("Settings", "Speech and environment. Everything else lives in topik.config.json."),
    el("div", { class: "card stack" },
      el("h2", { text: "Korean speech (TTS)" }),
      el("label", { class: "row" }, enabled, " Speech enabled"),
      el("label", { class: "field" }, `Volume`, volume),
      el("label", { class: "field" }, `Speed`, speed),
      el("label", { class: "field" }, "Voice preset", voice),
      el("div", { class: "row" }, el("button", { class: "primary", onclick: apply, text: "Apply" })),
      el("div", { class: "answer-row" }, sayBox, el("button", { text: "🔊 Speak", onclick: () => say(sayBox.value) }))),
    el("div", { class: "card stack" },
      el("h2", { text: "Korean keyboard (두벌식)" }),
      el("p", { class: "small muted", text: "The standard Dubeolsik layout — top-right jamo need Shift. macOS: add the '2-Set Korean' input source to type Hangul." }),
      el("div", { class: "kbd" }, ...keyboardRows)),
    el("div", { class: "card stack" },
      el("div", { class: "spread" },
        el("h2", { text: "Environment check" }),
        el("span", { class: "pill", text: `topik-sim v${doctor.version || "?"}` })),
      el("table", { class: "list" }, ...doctor.checks.map((check) => el("tr", {},
        el("td", {}, el("span", { class: `pill ${check.status === "PASS" ? "good" : check.status === "FAIL" ? "bad" : ""}`, text: check.status })),
        el("td", { text: check.name }),
        el("td", { class: "small muted", text: check.detail }))))),
  );
}

/* ----------------------------------------------------------------- boot */

document.getElementById("theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  const current = root.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  root.dataset.theme = current === "dark" ? "light" : "dark";
});

window.addEventListener("hashchange", route);
api("GET", "/api/tts").then((tts) => { state.tts = tts; updateTtsPill(); }).catch(() => {});
route();
