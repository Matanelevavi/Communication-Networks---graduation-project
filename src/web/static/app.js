/*
 * WeatherWear in the browser.
 *
 * Plain JavaScript, no build step. Everything the server sends is put on the
 * page with textContent, never innerHTML, so a city name or an archived file
 * can never become markup.
 */
"use strict";

// ---------------------------------------------------------------- strings
const STRINGS = {
  en: {
    skip: "Skip to content",
    tab_forecast: "Forecast", tab_archive: "Archive", tab_how: "How it works",
    hero_title: "What should everyone wear today?",
    hero_lede: "Live weather, and advice written for each person in your family.",
    city: "City", city_placeholder: "Tel Aviv, Haifa, London...",
    family: "Who is it for", family_hint: "Saved on this device only, never on the server.",
    add_person: "Add a person", name_placeholder: "Name", notes_placeholder: "Notes",
    remove_person: "Remove", age_label: "Age",
    age_adult: "Adult", age_child: "Child", age_baby: "Baby",
    transport: "Transport",
    protocol_hint_rudp: "RUDP: our own reliable protocol on top of UDP, with retransmission, congestion and flow control.",
    protocol_hint_tcp: "TCP: the operating system handles reliability; we only frame the messages.",
    submit: "Get my forecast", loading: "Checking the weather...",
    placeholder: "Pick a city to see the forecast and what to wear.",
    next_24: "Next 24 hours", now: "Now", low: "Low", high: "High", rain: "Rain",
    rain_none: "None", rain_from: "From",
    what_to_wear: "What to wear",
    source_ai: "Written by AI", source_local: "Written by local rules", cached: "cached weather",
    copy: "Copy", copied: "Copied", share: "Share",
    under_the_hood: "Under the hood",
    wire_protocol: "Protocol", wire_time: "Total time", wire_bytes: "Bytes", wire_chunks: "Chunks",
    wire_datagrams: "Datagrams", wire_duplicates: "Duplicates", wire_corrupted: "Corrupted",
    wire_note_rudp: "The answer arrived as numbered datagrams, each checked with CRC32 and acknowledged with the receiver's free window.",
    wire_note_tcp: "The answer arrived as one TCP stream; the end of the stream marks the end of the message.",
    err_city: "Please enter a city.", err_network: "The service is not reachable right now. Please try again in a moment.",
    err_busy: "Too many requests. Please wait a moment.",
    archive_title: "The archive",
    archive_lede: "Forecasts and hourly reports saved by the server, fetched FTP style over the transport you choose.",
    refresh: "Refresh", viewer_empty: "Choose a file", archive_empty: "The archive is empty. Ask for a forecast first.",
    files_count: (n) => `${n} files`,
    how_title: "How a forecast reaches you",
    how_lede: "This site is a host on a small simulated network. Each request takes the path a new machine takes when it joins one.",
    how_dhcp: "The site asks for an address: Discover, Offer, Request, Acknowledge. A backup server answers if the primary is down.",
    how_dns: "It resolves weatherwear.local through a local DNS server, and caches the answer for the TTL the server sets.",
    how_transport: "Your request travels over TCP, or over RUDP: sequence numbers, CRC32, retransmission, congestion control and flow control, written from scratch on top of UDP.",
    how_app_title: "App server",
    how_app: "The server fetches live weather from Open-Meteo, and writes advice for each person, with Gemini when a key is set and with local rules otherwise.",
    status_title: "Network status", status_joined: "Joined", status_ip: "Address from DHCP",
    status_server: "App server from DNS", status_domain: "Domain", yes: "Yes", no: "No",
    footer: "A computer networks graduation project.", api: "API", weather_credit: "Weather data: Open-Meteo",
    chips: ["Tel Aviv", "Jerusalem", "Haifa", "Ariel", "Beersheba", "Eilat"],
    lang_button: "עב", lang_label: "עברית", theme_label: "Switch theme",
  },
  he: {
    skip: "דלג לתוכן",
    tab_forecast: "תחזית", tab_archive: "ארכיון", tab_how: "איך זה עובד",
    hero_title: "מה כולם לובשים היום?",
    hero_lede: "מזג אוויר בזמן אמת, והמלצה שנכתבת לכל אחד במשפחה.",
    city: "עיר", city_placeholder: "תל אביב, חיפה, ירושלים...",
    family: "בשביל מי", family_hint: "נשמר רק במכשיר הזה, אף פעם לא בשרת.",
    add_person: "הוספת אדם", name_placeholder: "שם", notes_placeholder: "הערות",
    remove_person: "הסרה", age_label: "גיל",
    age_adult: "מבוגר", age_child: "ילד", age_baby: "תינוק",
    transport: "פרוטוקול תעבורה",
    protocol_hint_rudp: "RUDP: פרוטוקול אמין שכתבנו מעל UDP, עם שליחה חוזרת, בקרת עומס ובקרת זרימה.",
    protocol_hint_tcp: "TCP: מערכת ההפעלה דואגת לאמינות; אנחנו רק מסמנים איפה הודעה נגמרת.",
    submit: "לתחזית שלי", loading: "בודקים את מזג האוויר...",
    placeholder: "בחרו עיר כדי לראות את התחזית ומה ללבוש.",
    next_24: "24 השעות הקרובות", now: "עכשיו", low: "מינימום", high: "מקסימום", rain: "גשם",
    rain_none: "אין", rain_from: "החל מ-",
    what_to_wear: "מה ללבוש",
    source_ai: "נכתב על ידי AI", source_local: "נכתב לפי כללים מקומיים", cached: "מזג אוויר מהמטמון",
    copy: "העתקה", copied: "הועתק", share: "שיתוף",
    under_the_hood: "מאחורי הקלעים",
    wire_protocol: "פרוטוקול", wire_time: "זמן כולל", wire_bytes: "בייטים", wire_chunks: "חלקים",
    wire_datagrams: "דאטגרמות", wire_duplicates: "כפולות", wire_corrupted: "פגומות",
    wire_note_rudp: "התשובה הגיעה כדאטגרמות ממוספרות, כל אחת נבדקה ב-CRC32 ואושרה יחד עם החלון הפנוי של המקבל.",
    wire_note_tcp: "התשובה הגיעה כזרם TCP אחד; סוף הזרם מסמן את סוף ההודעה.",
    err_city: "נא להזין עיר.", err_network: "השירות לא זמין כרגע. נסו שוב בעוד רגע.",
    err_busy: "יותר מדי בקשות. חכו רגע ונסו שוב.",
    archive_title: "הארכיון",
    archive_lede: "תחזיות ודוחות שעתיים שהשרת שמר, נמשכים בסגנון FTP מעל הפרוטוקול שבחרתם.",
    refresh: "רענון", viewer_empty: "בחרו קובץ", archive_empty: "הארכיון ריק. בקשו קודם תחזית.",
    files_count: (n) => `${n} קבצים`,
    how_title: "איך תחזית מגיעה אליכם",
    how_lede: "האתר הזה הוא מחשב ברשת קטנה ומדומה. כל בקשה עוברת את הדרך שעובר מחשב חדש שמצטרף לרשת.",
    how_dhcp: "האתר מבקש כתובת: Discover,‏ Offer,‏ Request,‏ Acknowledge. שרת גיבוי עונה אם הראשי לא זמין.",
    how_dns: "הוא מתרגם את weatherwear.local דרך שרת DNS מקומי, ושומר את התשובה ל-TTL שהשרת קובע.",
    how_transport: "הבקשה שלכם עוברת ב-TCP, או ב-RUDP: מספרי רצף, CRC32, שליחה חוזרת, בקרת עומס ובקרת זרימה, שנכתבו מאפס מעל UDP.",
    how_app_title: "שרת האפליקציה",
    how_app: "השרת מביא מזג אוויר חי מ-Open-Meteo, וכותב המלצה לכל אחד, עם Gemini כשיש מפתח ועם כללים מקומיים בלעדיו.",
    status_title: "מצב הרשת", status_joined: "מחובר", status_ip: "כתובת מ-DHCP",
    status_server: "שרת האפליקציה מ-DNS", status_domain: "דומיין", yes: "כן", no: "לא",
    footer: "פרויקט גמר ברשתות תקשורת.", api: "API", weather_credit: "נתוני מזג אוויר: Open-Meteo",
    chips: ["תל אביב", "ירושלים", "חיפה", "אריאל", "באר שבע", "אילת"],
    lang_button: "EN", lang_label: "English", theme_label: "החלפת ערכת צבעים",
  },
};

const AGES = ["adult", "child", "baby"];
const NO_RAIN = "No rain expected";

// ---------------------------------------------------------------- storage
// Only conveniences live here, and every access is guarded: private windows
// and blocked storage must not break the page.
const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(`ww:${key}`);
      return raw === null ? fallback : JSON.parse(raw);
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`ww:${key}`, JSON.stringify(value)); } catch { /* ignore */ }
  },
};

const $ = (selector) => document.querySelector(selector);

const state = {
  lang: store.get("lang", navigator.language?.startsWith("he") ? "he" : "en"),
  people: store.get("people", null),
  lastCard: null,
};

function t(key, ...args) {
  const value = STRINGS[state.lang][key] ?? STRINGS.en[key] ?? key;
  return typeof value === "function" ? value(...args) : value;
}

// ------------------------------------------------------------- language
function applyLanguage() {
  const html = document.documentElement;
  html.lang = state.lang;
  html.dir = state.lang === "he" ? "rtl" : "ltr";

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  $("#city").placeholder = t("city_placeholder");
  $("#lang-toggle").textContent = t("lang_button");
  $("#lang-toggle").setAttribute("aria-label", t("lang_label"));
  $("#theme-toggle").setAttribute("aria-label", t("theme_label"));

  renderChips();
  renderPeople();
  updateProtocolHint();
  if (state.lastCard) renderForecast(state.lastCard.forecast, state.lastCard.transfer);
}

// ---------------------------------------------------------------- theme
function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

function toggleTheme() {
  const current = document.documentElement.dataset.theme
    || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  store.set("theme", next);
}

// ----------------------------------------------------------------- tabs
function selectTab(id) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const selected = tab.id === id;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute("aria-controls")).hidden = !selected;
  });
  if (id === "tab-archive") loadArchive();
  if (id === "tab-how") loadStatus();
}

function onTabKey(event) {
  const tabs = [...document.querySelectorAll(".tab")];
  const index = tabs.indexOf(event.target);
  const forward = state.lang === "he" ? "ArrowLeft" : "ArrowRight";
  const back = state.lang === "he" ? "ArrowRight" : "ArrowLeft";
  let next = null;
  if (event.key === forward) next = tabs[(index + 1) % tabs.length];
  if (event.key === back) next = tabs[(index - 1 + tabs.length) % tabs.length];
  if (next) { next.focus(); selectTab(next.id); event.preventDefault(); }
}

// ---------------------------------------------------------------- cities
function renderChips() {
  const box = $("#city-chips");
  box.replaceChildren();
  const recent = store.get("recent", []);
  const names = [...new Set([...recent, ...t("chips")])].slice(0, 8);
  for (const name of names) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = name;
    chip.dir = "auto";
    chip.addEventListener("click", () => { $("#city").value = name; submitForecast(); });
    box.append(chip);
  }
}

function remember(city) {
  const recent = store.get("recent", []).filter((c) => c.toLowerCase() !== city.toLowerCase());
  store.set("recent", [city, ...recent].slice(0, 4));
}

// ---------------------------------------------------------------- people
function defaultPeople() {
  return state.lang === "he"
    ? [{ name: "דנה", age_category: "adult", notes: "" },
       { name: "נועם", age_category: "baby", notes: "גן" }]
    : [{ name: "Dana", age_category: "adult", notes: "" },
       { name: "Noam", age_category: "baby", notes: "daycare" }];
}

function renderPeople() {
  if (state.people === null) state.people = defaultPeople();
  const list = $("#people");
  list.replaceChildren();

  state.people.forEach((person, index) => {
    const row = $("#person-template").content.firstElementChild.cloneNode(true);
    const name = row.querySelector(".person__name");
    const age = row.querySelector(".person__age");
    const notes = row.querySelector(".person__notes");
    const remove = row.querySelector(".person__remove");

    name.value = person.name;
    name.placeholder = t("name_placeholder");
    name.setAttribute("aria-label", t("name_placeholder"));
    notes.value = person.notes;
    notes.placeholder = t("notes_placeholder");
    notes.setAttribute("aria-label", t("notes_placeholder"));
    age.setAttribute("aria-label", t("age_label"));
    for (const value of AGES) {
      const option = new Option(t(`age_${value}`), value);
      age.append(option);
    }
    age.value = AGES.includes(person.age_category) ? person.age_category : "adult";
    remove.setAttribute("aria-label", `${t("remove_person")} ${person.name}`);

    const save = () => {
      state.people[index] = { name: name.value.trim(), age_category: age.value, notes: notes.value.trim() };
      store.set("people", state.people);
    };
    name.addEventListener("input", save);
    notes.addEventListener("input", save);
    age.addEventListener("change", save);
    remove.addEventListener("click", () => {
      state.people.splice(index, 1);
      store.set("people", state.people);
      renderPeople();
    });
    list.append(row);
  });
  $("#add-person").hidden = state.people.length >= 10;
}

function addPerson() {
  state.people.push({ name: "", age_category: "adult", notes: "" });
  store.set("people", state.people);
  renderPeople();
  $("#people").lastElementChild.querySelector(".person__name").focus();
}

// --------------------------------------------------------------- protocol
function protocol() {
  return document.querySelector("input[name=protocol]:checked").value;
}

function updateProtocolHint() {
  $("#protocol-hint").textContent = t(protocol() === "TCP" ? "protocol_hint_tcp" : "protocol_hint_rudp");
}

// ---------------------------------------------------------------- the api
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  } catch {
    throw new Error(t("err_network"));
  }
  let body = null;
  try { body = await response.json(); } catch { /* not JSON */ }
  if (response.status === 429) throw new Error(t("err_busy"));
  if (response.status === 503 || !body) throw new Error(t("err_network"));
  if (!response.ok) {
    const failure = new Error(body.error || t("err_network"));
    failure.transfer = body.transfer;
    throw failure;
  }
  return body;
}

// --------------------------------------------------------------- forecast
async function submitForecast(event) {
  event?.preventDefault();
  const city = $("#city").value.trim();
  if (!city) {
    showError(t("err_city"));
    $("#city").focus();
    return;
  }

  const button = $("#submit");
  button.disabled = true;
  button.classList.add("is-loading");
  button.lastElementChild.textContent = t("loading");
  hideError();

  try {
    const people = state.people.filter((p) => p.name)
      .map((p) => ({ ...p, age_category: t(`age_${p.age_category}`) }));
    const body = await api("api/forecast", {
      method: "POST",
      body: JSON.stringify({ city, profiles: people, protocol: protocol() }),
    });
    remember(city);
    renderChips();
    state.lastCard = body;
    renderForecast(body.forecast, body.transfer);
    revealResult();
  } catch (failure) {
    showError(failure.message);
    revealResult();
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    button.lastElementChild.textContent = t("submit");
  }
}

// On a phone the answer lands below the form, out of sight: bring it into view.
function revealResult() {
  if (!matchMedia("(max-width: 860px)").matches) return;
  const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  $("#result").scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "start" });
}

function degrees(value) {
  return typeof value === "number" ? `${Math.round(value * 10) / 10}°` : "--";
}

function weatherIcon(card) {
  const wet = card.rain && card.rain !== NO_RAIN;
  if (card.max_temp < 5) return "❄️";
  if (wet) return "🌧️";
  if (card.max_temp >= 27) return "☀️";
  if (card.max_temp >= 18) return "🌤️";
  return "⛅";
}

function rainHours(summary) {
  if (!summary || summary === NO_RAIN) return [];
  return summary.split(", ").map((entry) => entry.trim()).filter(Boolean);
}

function renderForecast(card, transfer) {
  $("#placeholder").hidden = true;
  $("#forecast").hidden = false;

  $("#fc-city").textContent = card.city;
  $("#fc-city").dir = "auto";
  $("#fc-icon").textContent = weatherIcon(card);
  $("#fc-now").textContent = degrees(card.current_temp);
  $("#fc-low").textContent = degrees(card.min_temp);
  $("#fc-high").textContent = degrees(card.max_temp);

  // Where today's range sits on a scale from -5° to 45°.
  const scale = (v) => Math.min(100, Math.max(0, ((v + 5) / 50) * 100));
  const fill = $("#fc-range");
  fill.style.insetInlineStart = `${scale(card.min_temp)}%`;
  fill.style.width = `${Math.max(4, scale(card.max_temp) - scale(card.min_temp))}%`;

  const hours = rainHours(card.rain);
  $("#fc-rain").textContent = hours.length ? `${t("rain_from")}${hours[0].split(" ")[0]}` : t("rain_none");
  $("#fc-rain").className = hours.length ? "cool" : "";
  const chips = $("#fc-rain-hours");
  chips.replaceChildren(...hours.slice(0, 12).map((hour) => {
    const span = document.createElement("span");
    span.textContent = hour;
    return span;
  }));

  $("#fc-advice").textContent = card.advice;
  $("#fc-source").textContent = `${t(card.source === "ai" ? "source_ai" : "source_local")}${card.cached ? ` · ${t("cached")}` : ""}`;

  renderTransfer(transfer);
}

function renderTransfer(transfer) {
  const grid = $("#wire-grid");
  const rows = [
    ["wire_protocol", transfer.protocol],
    ["wire_time", `${transfer.elapsed_ms} ms`],
    ["wire_bytes", transfer.bytes],
  ];
  if (transfer.protocol === "RUDP") {
    rows.push(["wire_chunks", transfer.chunks], ["wire_datagrams", transfer.datagrams],
              ["wire_duplicates", transfer.duplicates], ["wire_corrupted", transfer.corrupted]);
  }
  grid.replaceChildren(...rows.map(([key, value]) => definition(t(key), value)));
  $("#wire-note").textContent = t(transfer.protocol === "RUDP" ? "wire_note_rudp" : "wire_note_tcp");
}

function definition(term, value) {
  const wrap = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = value ?? "--";
  wrap.append(dt, dd);
  return wrap;
}

function showError(message) {
  const box = $("#error");
  box.textContent = message;
  box.hidden = false;
}

function hideError() { $("#error").hidden = true; }

async function copyAdvice() {
  const text = shareText();
  try {
    await navigator.clipboard.writeText(text);
    const button = $("#copy");
    button.textContent = t("copied");
    setTimeout(() => { button.textContent = t("copy"); }, 1600);
  } catch { /* clipboard blocked */ }
}

function shareText() {
  const card = state.lastCard?.forecast;
  if (!card) return "";
  return `${card.city}: ${degrees(card.min_temp)}–${degrees(card.max_temp)}\n${card.advice}\n${location.origin}${location.pathname}`;
}

async function shareAdvice() {
  const text = shareText();
  if (navigator.share) {
    try { await navigator.share({ title: "WeatherWear", text }); return; } catch { return; }
  }
  window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
}

// ---------------------------------------------------------------- archive
let archiveLoaded = false;

async function loadArchive(force = false) {
  if (archiveLoaded && !force) return;
  const list = $("#files");
  $("#archive-meta").textContent = t("loading");
  try {
    const body = await api(`api/archive?protocol=${protocol()}`);
    archiveLoaded = true;
    $("#archive-meta").textContent = `${t("files_count", body.files.length)} · ${body.transfer.protocol} · ${body.transfer.elapsed_ms} ms`;
    if (!body.files.length) {
      const empty = document.createElement("li");
      empty.className = "muted";
      empty.textContent = t("archive_empty");
      list.replaceChildren(empty);
      return;
    }
    list.replaceChildren(...body.files.map((file) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = file.name;
      const size = document.createElement("span");
      size.className = "size";
      size.textContent = file.size;
      button.append(name, size);
      button.addEventListener("click", () => openFile(file.name, button));
      item.append(button);
      return item;
    }));
  } catch (failure) {
    $("#archive-meta").textContent = failure.message;
  }
}

async function openFile(name, button) {
  document.querySelectorAll(".files button").forEach((b) => b.removeAttribute("aria-current"));
  button.setAttribute("aria-current", "true");
  $("#viewer-title").textContent = name;
  $("#viewer").textContent = t("loading");
  try {
    const body = await api(`api/archive/${encodeURIComponent(name)}?protocol=${protocol()}`);
    $("#viewer").textContent = body.content;
  } catch (failure) {
    $("#viewer").textContent = failure.message;
  }
}

// ----------------------------------------------------------------- status
async function loadStatus() {
  const grid = $("#status-grid");
  try {
    const body = await api("api/health");
    const net = body.network;
    grid.replaceChildren(
      definition(t("status_joined"), net.joined ? t("yes") : t("no")),
      definition(t("status_ip"), net.ip ?? "--"),
      definition(t("status_server"), net.app_server ?? "--"),
      definition(t("status_domain"), net.domain ?? "--"),
    );
  } catch (failure) {
    grid.replaceChildren(definition(t("status_joined"), failure.message));
  }
}

// ------------------------------------------------------------------ start
function start() {
  applyTheme(store.get("theme", null));
  $("#city").value = store.get("recent", [])[0] ?? "";

  $("#forecast-form").addEventListener("submit", submitForecast);
  $("#add-person").addEventListener("click", addPerson);
  $("#lang-toggle").addEventListener("click", () => {
    state.lang = state.lang === "he" ? "en" : "he";
    store.set("lang", state.lang);
    applyLanguage();
  });
  $("#theme-toggle").addEventListener("click", toggleTheme);
  document.querySelectorAll("input[name=protocol]").forEach((radio) =>
    radio.addEventListener("change", () => { updateProtocolHint(); archiveLoaded = false; }));
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => selectTab(tab.id));
    tab.addEventListener("keydown", onTabKey);
  });
  $("#archive-refresh").addEventListener("click", () => loadArchive(true));
  $("#copy").addEventListener("click", copyAdvice);
  $("#share").addEventListener("click", shareAdvice);

  applyLanguage();
}

start();
