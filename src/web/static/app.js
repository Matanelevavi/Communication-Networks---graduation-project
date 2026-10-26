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
    tab_lab: "Protocol lab",
    lab_title: "Break the network, watch the protocol",
    lab_lede: "Send the same file through a simulated network, with the loss, delay and receive buffer you choose. The RUDP sender is this project's real code; the TCP side is a Reno model on the same link.",
    lab_presets: "Scenarios",
    preset_clean: "Clean link", preset_wifi: "Flaky Wi-Fi", preset_congested: "Congested",
    preset_slow: "Slow receiver", preset_sat: "Satellite",
    lab_loss: "Packet loss", lab_delay: "One-way delay", lab_size: "File size", lab_buffer: "Receive buffer",
    lab_seed: "Seed", lab_shuffle: "New seed", lab_unit_packets: "packets",
    lab_run: "Run the transfer", lab_replay: "Replay", lab_share: "Copy link to this experiment",
    lab_copied: "Link copied",
    lab_chart_rudp: "RUDP, this project's own code", lab_chart_tcp: "TCP Reno, a model",
    lab_axis_time: "time (s)", lab_axis_cwnd: "packets",
    lab_legend_cwnd: "congestion window", lab_legend_ssthresh: "ssthresh",
    lab_legend_rwnd: "receive buffer limit", lab_legend_loss: "packet lost",
    lab_legend_timeout: "timeout", lab_legend_fast: "fast retransmit",
    lab_gave_up_at: (s) => `gave up at ${s} s`,
    lab_table_title: "Result",
    m_status: "Outcome", m_time: "Time", m_goodput: "Throughput", m_sent: "Packets sent",
    m_retx: "Retransmissions", m_timeouts: "Timeouts", m_fast: "Fast retransmits", m_verified: "Data intact",
    m_done: "Finished", m_gaveup: "Gave up", m_yes: "Yes, byte for byte", m_no: "No",
    lab_name_rudp: "RUDP", lab_name_tcp: "The TCP model",
    lab_same: "Both finished in about the same time.",
    lab_faster: (a, b, x) => `${a} finished ${x} times faster than ${b}.`,
    lab_gaveup: (who, s) => `${who} gave up after ${s} s: it timed out several times in a row and nothing came back.`,
    lab_both_failed: "Neither finished: the network was too bad.",
    lab_error: "The lab could not run that experiment.",
    lab_notes_title: "How to read this",
    lab_notes: [
      "Slow start: the window doubles every round trip until it reaches ssthresh, then grows by one packet per round trip.",
      "A timeout means nothing came back for a full second: the window falls to 1 and ssthresh is halved. Three duplicate ACKs trigger a fast retransmit instead: the window is only halved.",
      "The receive buffer caps the window. The receiver says how much room it has (flow control), and the sender obeys the smaller of that and its own window.",
      "RUDP gives up after 4 timeouts in a row, by design. The Reno model keeps trying much longer. That is a real difference between the two, not a drawing choice.",
      "Time is virtual: a minute of simulated network takes milliseconds to compute, and one seed gives both protocols exactly the same loss pattern.",
    ],
    lab_honesty: "The TCP line is a model of TCP Reno, not your operating system's TCP, which cannot be placed on a lossy virtual link. The RUDP line is the real sender and receiver from src/rudp, unchanged.",
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
    tab_lab: "מעבדת פרוטוקולים",
    lab_title: "מקלקלים את הרשת, ורואים מה הפרוטוקול עושה",
    lab_lede: "שולחים את אותו קובץ ברשת מדומה, עם אובדן חבילות, השהיה וגודל באפר לפי בחירתכם. השולח של RUDP הוא הקוד האמיתי של הפרויקט; צד ה-TCP הוא מודל של Reno על אותו קו.",
    lab_presets: "תרחישים",
    preset_clean: "קו נקי", preset_wifi: "Wi-Fi לא יציב", preset_congested: "עומס",
    preset_slow: "מקבל איטי", preset_sat: "לוויין",
    lab_loss: "אובדן חבילות", lab_delay: "השהיה בכיוון אחד", lab_size: "גודל קובץ", lab_buffer: "באפר קבלה",
    lab_seed: "זרע", lab_shuffle: "זרע חדש", lab_unit_packets: "חבילות",
    lab_run: "הרצת ההעברה", lab_replay: "הפעלה חוזרת", lab_share: "העתקת קישור לניסוי",
    lab_copied: "הקישור הועתק",
    lab_chart_rudp: "RUDP, הקוד של הפרויקט", lab_chart_tcp: "TCP Reno, מודל",
    lab_axis_time: "זמן (שניות)", lab_axis_cwnd: "חבילות",
    lab_legend_cwnd: "חלון עומס", lab_legend_ssthresh: "ssthresh",
    lab_legend_rwnd: "גבול באפר הקבלה", lab_legend_loss: "חבילה אבדה",
    lab_legend_timeout: "תם הזמן (timeout)", lab_legend_fast: "שליחה חוזרת מהירה",
    lab_gave_up_at: (s) => `ויתר אחרי ${s} שניות`,
    lab_table_title: "תוצאה",
    m_status: "תוצאה", m_time: "זמן", m_goodput: "תפוקה", m_sent: "חבילות שנשלחו",
    m_retx: "שליחות חוזרות", m_timeouts: "תם הזמן", m_fast: "שליחות חוזרות מהירות", m_verified: "הנתונים שלמים",
    m_done: "הסתיים", m_gaveup: "ויתר", m_yes: "כן, בייט אחרי בייט", m_no: "לא",
    lab_name_rudp: "RUDP", lab_name_tcp: "מודל ה-TCP",
    lab_same: "שניהם הסתיימו בערך באותו זמן.",
    lab_faster: (a, b, x) => `${a} הסתיים פי ${x} מהר יותר מ${b}.`,
    lab_gaveup: (who, s) => `${who} ויתר אחרי ${s} שניות: נגמר לו הזמן כמה פעמים ברצף ושום דבר לא חזר.`,
    lab_both_failed: "אף אחד לא הסתיים: הרשת הייתה גרועה מדי.",
    lab_error: "המעבדה לא הצליחה להריץ את הניסוי.",
    lab_notes_title: "איך קוראים את זה",
    lab_notes: [
      "Slow start: החלון מוכפל בכל הלוך-חזור עד ש-ssthresh, ומשם גדל בחבילה אחת לכל הלוך-חזור.",
      "Timeout אומר שלא חזר כלום שנייה שלמה: החלון יורד ל-1 וה-ssthresh מתחלק בשניים. שלושה אישורים כפולים מפעילים שליחה חוזרת מהירה במקום זה: החלון רק מתחלק בשניים.",
      "באפר הקבלה מגביל את החלון. המקבל אומר כמה מקום יש לו (בקרת זרימה), והשולח מציית לקטן מבין זה לבין החלון שלו.",
      "RUDP מוותר אחרי 4 פעמים ברצף שלא חזרה תשובה, בכוונה. מודל Reno ממשיך לנסות הרבה יותר זמן. זה הבדל אמיתי בין השניים, לא בחירה בציור.",
      "הזמן וירטואלי: דקה של רשת מדומה מחושבת באלפיות שנייה, וזרע אחד נותן לשני הפרוטוקולים בדיוק אותו דפוס אובדן.",
    ],
    lab_honesty: "קו ה-TCP הוא מודל של TCP Reno, לא ה-TCP של מערכת ההפעלה, שאי אפשר להניח על קו וירטואלי עם אובדן. קו ה-RUDP הוא השולח והמקבל האמיתיים מ-src/rudp, בלי שינוי.",
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
  renderLabPresets();
  renderLabNotes();
  renderLabLegend();
  updateLabOutputs();
  if (labState.result) renderLabResult();
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
  if (id === "tab-lab") openLab();
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

// -------------------------------------------------------------------- lab
// Every number drawn here comes back from /api/lab: the real RUDP sender and
// a Reno model, run over a simulated link. Nothing on this page is scripted.
const SVG_NS = "http://www.w3.org/2000/svg";
const PRESETS = {
  clean:     { loss: 0,  delay: 40,  size: 64,  buffer: 8, seed: 1 },
  wifi:      { loss: 5,  delay: 40,  size: 64,  buffer: 8, seed: 1 },
  congested: { loss: 15, delay: 80,  size: 64,  buffer: 8, seed: 2 },
  slow:      { loss: 0,  delay: 40,  size: 64,  buffer: 2, seed: 1 },
  sat:       { loss: 1,  delay: 300, size: 128, buffer: 16, seed: 1 },
};
const LAB_FIELDS = ["loss", "delay", "size", "buffer"];
const labState = { result: null, frame: null, preset: null, ran: false };

function svgEl(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

function labParams() {
  return {
    loss: Number($("#lab-loss").value) / 100,
    delay_ms: Number($("#lab-delay").value),
    size_kb: Number($("#lab-size").value),
    buffer: Number($("#lab-buffer").value),
    seed: Math.max(0, Math.min(2147483647, Math.trunc(Number($("#lab-seed").value) || 0))),
  };
}

function setLabControls(values) {
  $("#lab-loss").value = values.loss;
  $("#lab-delay").value = values.delay;
  $("#lab-size").value = values.size;
  $("#lab-buffer").value = values.buffer;
  if (values.seed !== undefined) $("#lab-seed").value = values.seed;
  updateLabOutputs();
}

function updateLabOutputs() {
  $("#lab-loss-out").textContent = `${$("#lab-loss").value}%`;
  $("#lab-delay-out").textContent = `${$("#lab-delay").value} ms`;
  $("#lab-size-out").textContent = `${$("#lab-size").value} KB`;
  $("#lab-buffer-out").textContent = `${$("#lab-buffer").value} ${t("lab_unit_packets")}`;
}

function renderLabPresets() {
  const box = $("#lab-presets");
  box.replaceChildren();
  for (const key of Object.keys(PRESETS)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.textContent = t(`preset_${key}`);
    button.setAttribute("aria-pressed", String(labState.preset === key));
    button.addEventListener("click", () => {
      labState.preset = key;
      setLabControls(PRESETS[key]);
      renderLabPresets();
      runLab();
    });
    box.append(button);
  }
}

function renderLabNotes() {
  $("#lab-notes").replaceChildren(...t("lab_notes").map((line) => {
    const item = document.createElement("li");
    item.textContent = line;
    return item;
  }));
}

function renderLabLegend() {
  const legend = $("#lab-legend");
  const items = [
    ["line--rudp", "lab_legend_cwnd", "solid"], ["line--ssthresh", "lab_legend_ssthresh", "dashed"],
    ["line--rwnd", "lab_legend_rwnd", "dotted"], ["mark--loss", "lab_legend_loss", "solid"],
    ["mark--timeout", "lab_legend_timeout", "solid"], ["mark--fast", "lab_legend_fast", "dashed"],
  ];
  const sample = { "line--rudp": "var(--brand)", "line--ssthresh": "var(--ink-faint)",
                   "line--rwnd": "var(--success)", "mark--loss": "var(--danger)",
                   "mark--timeout": "var(--danger)", "mark--fast": "var(--warm)" };
  legend.replaceChildren(...items.map(([cls, key, style]) => {
    const span = document.createElement("span");
    const swatch = document.createElement("i");
    swatch.style.borderTopColor = sample[cls];
    swatch.style.borderTopStyle = style;
    span.append(swatch, document.createTextNode(t(key)));
    return span;
  }));
}

async function runLab() {
  const button = $("#lab-run");
  button.disabled = true;
  button.classList.add("is-loading");
  $("#lab-error").hidden = true;
  try {
    const params = labParams();
    const body = await api("api/lab", { method: "POST", body: JSON.stringify(params) });
    labState.result = body;
    labState.ran = true;
    writeLabHash(params);
    renderLabResult();
    playLab();
  } catch (failure) {
    const box = $("#lab-error");
    box.textContent = failure.message || t("lab_error");
    box.hidden = false;
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
  }
}

// ----- the chart
function niceStep(max, wanted) {
  const raw = max / wanted;
  const power = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 5, 10]) if (m * power >= raw) return m * power;
  return 10 * power;
}

const GEOMETRY = { w: 640, h: 220, left: 46, right: 12, top: 12, bottom: 34 };

function drawChart(svg, run, scale, upTo, kind, buffer) {
  const g = GEOMETRY;
  const plotW = g.w - g.left - g.right;
  const plotH = g.h - g.top - g.bottom;
  const x = (ms) => g.left + (ms / scale.xMax) * plotW;
  const y = (v) => g.top + plotH - (v / scale.yMax) * plotH;
  const parts = [];

  // grid and axes
  const yStep = niceStep(scale.yMax, 5);
  for (let v = 0; v <= scale.yMax; v += yStep) {
    parts.push(svgEl("line", { class: v === 0 ? "axis" : "grid-line", x1: g.left, x2: g.w - g.right, y1: y(v), y2: y(v) }));
    parts.push(svgEl("text", { class: "tick-label", x: g.left - 6, y: y(v) + 4, "text-anchor": "end" }, String(v)));
  }
  const xStep = niceStep(scale.xMax / 1000, 6);
  for (let s = 0; s * 1000 <= scale.xMax; s += xStep) {
    parts.push(svgEl("line", { class: "axis", x1: x(s * 1000), x2: x(s * 1000), y1: y(0), y2: y(0) + 4 }));
    parts.push(svgEl("text", { class: "tick-label", x: x(s * 1000), y: y(0) + 17, "text-anchor": "middle" }, String(Math.round(s * 100) / 100)));
  }
  parts.push(svgEl("text", { class: "axis-title", x: g.left + plotW / 2, y: g.h - 4, "text-anchor": "middle" }, t("lab_axis_time")));
  parts.push(svgEl("text", { class: "axis-title", x: 4, y: 10 }, t("lab_axis_cwnd")));

  // the receiver's limit
  if (buffer <= scale.yMax) {
    parts.push(svgEl("line", { class: "line line--rwnd", x1: g.left, x2: g.w - g.right, y1: y(buffer), y2: y(buffer) }));
  }

  // events up to now: losses along the floor, timeouts and fast retransmits as verticals
  for (const mark of run.marks) {
    if (mark.t > upTo) break;
    if (mark.kind === "loss" || mark.kind === "ack_loss") {
      parts.push(svgEl("line", { class: mark.kind === "loss" ? "mark--loss" : "mark--ackloss",
        x1: x(mark.t), x2: x(mark.t), y1: y(0), y2: y(0) - 9 }));
    } else if (mark.kind === "timeout" || mark.kind === "fast_retransmit") {
      parts.push(svgEl("line", { class: mark.kind === "timeout" ? "mark--timeout" : "mark--fast",
        x1: x(mark.t), x2: x(mark.t), y1: y(0), y2: g.top }));
    }
  }

  // ssthresh, then the window on top of it
  const visible = run.series.filter((p) => p.t <= upTo);
  if (visible.length) {
    parts.push(svgEl("polyline", { class: "line line--ssthresh",
      points: visible.map((p) => `${x(p.t).toFixed(1)},${y(Math.min(p.ssthresh, scale.yMax)).toFixed(1)}`).join(" ") }));
    parts.push(svgEl("polyline", { class: `line line--${kind}`,
      points: visible.map((p) => `${x(p.t).toFixed(1)},${y(p.cwnd).toFixed(1)}`).join(" ") }));
    const head = visible[visible.length - 1];
    parts.push(svgEl("circle", { class: `head-dot--${kind}`, cx: x(head.t), cy: y(head.cwnd), r: 4 }));
  }
  if (!run.completed && upTo >= run.duration_ms) {
    const label = t("lab_gave_up_at", (run.duration_ms / 1000).toFixed(1));
    const atX = x(run.duration_ms);
    const flip = atX > g.w * 0.7;
    parts.push(svgEl("text", { class: "chart-note", x: flip ? atX - 6 : atX + 6, y: g.top + 14,
      "text-anchor": flip ? "end" : "start" }, label));
  }
  svg.replaceChildren(...parts);
}

function chartScale(runs) {
  const list = Object.values(runs);
  const xMax = Math.max(...list.map((r) => r.duration_ms), 100);
  const yMax = Math.max(22, ...list.flatMap((r) => r.series.map((p) => p.cwnd)));
  return { xMax: xMax * 1.02, yMax: Math.ceil(yMax / 2) * 2 };
}

function drawAll(upTo) {
  const { runs, params } = labState.result;
  const scale = chartScale(runs);
  if (runs.RUDP) drawChart($("#chart-rudp"), runs.RUDP, scale, upTo, "rudp", params.buffer);
  if (runs.TCP) drawChart($("#chart-tcp"), runs.TCP, scale, upTo, "tcp", params.buffer);
  return scale.xMax;
}

function playLab() {
  cancelAnimationFrame(labState.frame);
  const { runs } = labState.result;
  const total = chartScale(runs).xMax;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) { drawAll(total); return; }

  const duration = 3200;
  const started = performance.now();
  const step = (now) => {
    const progress = Math.min(1, (now - started) / duration);
    drawAll(total * progress);
    if (progress < 1) labState.frame = requestAnimationFrame(step);
  };
  labState.frame = requestAnimationFrame(step);
}

// ----- the numbers
function fmtSeconds(ms) { return `${(ms / 1000).toFixed(ms >= 10000 ? 1 : 2)} s`; }

function labSummary(runs) {
  const rudp = runs.RUDP, tcp = runs.TCP;
  if (!rudp || !tcp) return "";
  const gaveUp = (run, who) => t("lab_gaveup", who, (run.duration_ms / 1000).toFixed(1));

  if (rudp.completed && tcp.completed) {
    const ratio = tcp.duration_ms / rudp.duration_ms;
    if (Math.abs(ratio - 1) < 0.03) return t("lab_same");
    const [fast, slow, nf, ns, x] = ratio > 1
      ? [rudp, tcp, "lab_name_rudp", "lab_name_tcp", ratio]
      : [tcp, rudp, "lab_name_tcp", "lab_name_rudp", 1 / ratio];
    return t("lab_faster", t(nf), t(ns), x.toFixed(2));
  }
  if (!rudp.completed && !tcp.completed) return t("lab_both_failed");
  return !rudp.completed ? gaveUp(rudp, t("lab_name_rudp")) : gaveUp(tcp, t("lab_name_tcp"));
}

function renderLabResult() {
  if (!labState.result) return;
  const { runs } = labState.result;
  $("#lab-charts").hidden = false;
  $("#lab-table-card").hidden = false;
  $("#lab-summary").textContent = labSummary(runs);

  $("#chart-rudp-title").textContent = t("lab_chart_rudp");
  $("#chart-tcp-title").textContent = t("lab_chart_tcp");
  const summary = labSummary(runs);
  for (const key of ["rudp", "tcp"]) {
    $(`#chart-${key}`).setAttribute("aria-label", `${t(`lab_chart_${key}`)}. ${summary}`);
  }

  const table = $("#lab-table");
  const rows = [
    ["m_status", (r) => t(r.completed ? "m_done" : "m_gaveup"), (r) => (r.completed ? "" : "bad")],
    ["m_time", (r) => fmtSeconds(r.duration_ms), null, "duration_ms", "min"],
    ["m_goodput", (r) => `${r.goodput_kbps} kbit/s`, null, "goodput_kbps", "max"],
    ["m_sent", (r) => r.packets_sent],
    ["m_retx", (r) => r.retransmissions],
    ["m_timeouts", (r) => r.timeouts],
    ["m_fast", (r) => r.fast_retransmits],
    ["m_verified", (r) => (r.verified ? t("m_yes") : t("m_no")), (r) => (r.verified ? "" : "bad")],
  ];
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const label of ["", "RUDP", "TCP Reno (model)"]) {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    headRow.append(th);
  }
  head.append(headRow);

  const body = document.createElement("tbody");
  for (const [labelKey, format, tone, field, better] of rows) {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.scope = "row";
    th.textContent = t(labelKey);
    tr.append(th);

    let best = null;
    if (field && runs.RUDP?.completed && runs.TCP?.completed) {
      const a = runs.RUDP[field], b = runs.TCP[field];
      if (a !== b) best = (better === "min" ? a < b : a > b) ? "RUDP" : "TCP";
    }
    for (const protocol of ["RUDP", "TCP"]) {
      const run = runs[protocol];
      const td = document.createElement("td");
      td.className = `num ${tone ? tone(run) : ""} ${best === protocol ? "best" : ""}`.trim();
      td.textContent = run ? String(format(run)) : "--";
      tr.append(td);
    }
    body.append(tr);
  }
  table.replaceChildren(head, body);
  drawAll(chartScale(runs).xMax);
}

// ----- sharing an experiment as a link
function writeLabHash(params) {
  const query = new URLSearchParams({
    loss: Math.round(params.loss * 100), delay: params.delay_ms, size: params.size_kb,
    buffer: params.buffer, seed: params.seed,
  });
  try { history.replaceState(null, "", `#lab?${query}`); } catch { /* ignore */ }
}

function readLabHash() {
  if (!location.hash.startsWith("#lab")) return null;
  const query = new URLSearchParams(location.hash.split("?")[1] || "");
  const pick = (name, low, high, fallback) => {
    const value = Number(query.get(name));
    return query.has(name) && Number.isFinite(value) ? Math.min(high, Math.max(low, Math.trunc(value))) : fallback;
  };
  return {
    loss: pick("loss", 0, 50, 5), delay: pick("delay", 1, 400, 40), size: pick("size", 1, 256, 64),
    buffer: pick("buffer", 1, 64, 8), seed: pick("seed", 0, 2147483647, 1),
  };
}

async function copyLabLink() {
  try {
    await navigator.clipboard.writeText(location.href);
    const button = $("#lab-link");
    button.textContent = t("lab_copied");
    setTimeout(() => { button.textContent = t("lab_share"); }, 1600);
  } catch { /* clipboard blocked */ }
}

function openLab() {
  if (labState.ran) return;
  const fromLink = readLabHash();
  if (fromLink) setLabControls(fromLink);
  else { labState.preset = "wifi"; setLabControls(PRESETS.wifi); renderLabPresets(); }
  runLab();
}

function startLab() {
  renderLabLegend();
  renderLabNotes();
  renderLabPresets();
  updateLabOutputs();

  $("#lab-form").addEventListener("submit", (event) => { event.preventDefault(); labState.preset = null; renderLabPresets(); runLab(); });
  for (const name of LAB_FIELDS) {
    const input = $(`#lab-${name}`);
    input.addEventListener("input", updateLabOutputs);
    // run when the slider is released, not on every pixel of the drag
    input.addEventListener("change", () => { labState.preset = null; renderLabPresets(); runLab(); });
  }
  $("#lab-seed").addEventListener("change", runLab);
  $("#lab-shuffle").addEventListener("click", () => {
    $("#lab-seed").value = Math.floor(Math.random() * 1000000);
    runLab();
  });
  $("#lab-replay").addEventListener("click", () => { if (labState.result) playLab(); });
  $("#lab-link").addEventListener("click", copyLabLink);

  // A shared link opened in a tab that is already loaded changes only the
  // hash, which does not reload the page: follow it.
  window.addEventListener("hashchange", () => {
    const link = readLabHash();
    if (!link) return;
    setLabControls(link);
    labState.preset = null;
    renderLabPresets();
    selectTab("tab-lab");
    if (labState.ran) runLab();
  });

  if (location.hash.startsWith("#lab")) selectTab("tab-lab");
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
  startLab();
}

start();
