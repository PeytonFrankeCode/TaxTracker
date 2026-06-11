/* TaxTracker web UI. Data lives in localStorage using the same JSON schema
   as the CLI's data file, so export/import round-trips between the two. */
"use strict";

/* ---------- tax constants (2025 federal rules, mirrors taxtracker/tax.py) */
const BRACKETS = {
  single: [[11925,.10],[48475,.12],[103350,.22],[197300,.24],[250525,.32],[626350,.35],[Infinity,.37]],
  married:[[23850,.10],[96950,.12],[206700,.22],[394600,.24],[501050,.32],[751600,.35],[Infinity,.37]],
};
const STD_DEDUCTION = { single: 15000, married: 30000 };
const SE = { factor: .9235, ss: .124, medicare: .029, wageBase: 176100 };
const SE_TYPES = new Set(["saas", "freelance", "business"]);
const STATE_RATES = {
  AL:.05,AK:0,AZ:.025,AR:.039,CA:.093,CO:.044,CT:.055,DE:.066,DC:.085,FL:0,
  GA:.0539,HI:.0825,ID:.05695,IL:.0495,IN:.03,IA:.038,KS:.0558,KY:.04,LA:.03,
  ME:.0715,MD:.0575,MA:.05,MI:.0425,MN:.0785,MS:.044,MO:.047,MT:.059,NE:.052,
  NV:0,NH:0,NJ:.0637,NM:.059,NY:.0685,NC:.0425,ND:.025,OH:.035,OK:.0475,
  OR:.099,PA:.0307,RI:.0599,SC:.062,SD:0,TN:0,TX:0,UT:.0455,VT:.076,VA:.0575,
  WA:0,WV:.0482,WI:.0627,WY:0,
};
/* Economic nexus: [sales $, transactions|null, bothRequired]; null = no sales tax. */
const NEXUS = {
  AL:[250000,null,false],AK:[100000,null,false],AZ:[100000,null,false],
  AR:[100000,200,false],CA:[500000,null,false],CO:[100000,null,false],
  CT:[100000,200,true],DE:null,DC:[100000,200,false],FL:[100000,null,false],
  GA:[100000,200,false],HI:[100000,200,false],ID:[100000,null,false],
  IL:[100000,200,false],IN:[100000,null,false],IA:[100000,null,false],
  KS:[100000,null,false],KY:[100000,200,false],LA:[100000,null,false],
  ME:[100000,null,false],MD:[100000,200,false],MA:[100000,null,false],
  MI:[100000,200,false],MN:[100000,200,false],MS:[250000,null,false],
  MO:[100000,null,false],MT:null,NE:[100000,200,false],NV:[100000,200,false],
  NH:null,NJ:[100000,200,false],NM:[100000,null,false],NY:[500000,100,true],
  NC:[100000,null,false],ND:[100000,null,false],OH:[100000,200,false],
  OK:[100000,null,false],OR:null,PA:[100000,null,false],RI:[100000,200,false],
  SC:[100000,null,false],SD:[100000,null,false],TN:[100000,null,false],
  TX:[500000,null,false],UT:[100000,200,false],VT:[100000,200,false],
  VA:[100000,200,false],WA:[100000,null,false],WV:[100000,200,false],
  WI:[100000,null,false],WY:[100000,null,false],
};
const APPROACHING = 0.8;
/* Where each product type is *generally* subject to sales tax (coarse). */
const NO_SALES_TAX = new Set(["DE", "MT", "NH", "OR"]);
const ALL_TAX_STATES = Object.keys(NEXUS).filter(s => NEXUS[s] !== null);
const TAXABILITY = {
  saas: new Set(["AZ","CT","DC","HI","IA","KY","LA","MA","MS","NM","NY","OH",
                 "PA","RI","SC","SD","TN","TX","UT","VT","WA","WV"]),
  digital: new Set(["AL","AR","AZ","CO","CT","DC","GA","HI","IA","ID","IN","KS",
                    "KY","LA","ME","MD","MN","MS","NC","NE","NJ","NM","NY","OH",
                    "PA","RI","SD","TN","TX","UT","VT","WA","WI","WV","WY"]),
  physical: new Set(ALL_TAX_STATES),
  services: new Set(["HI","NM","SD","WV"]),
  mixed: new Set(ALL_TAX_STATES),
};
const PRODUCT_LABELS = {
  saas: "SaaS / cloud software", digital: "downloadable digital products",
  physical: "physical goods", services: "services", mixed: "a mix of products",
};
/* Square-tile cartogram coordinates: state -> [column, row]. */
const TILES = {
  AK:[1,1],ME:[12,1],WI:[6,2],VT:[10,2],NH:[11,2],
  WA:[1,3],ID:[2,3],MT:[3,3],ND:[4,3],MN:[5,3],IL:[6,3],MI:[7,3],NY:[9,3],MA:[10,3],RI:[11,3],
  OR:[1,4],NV:[2,4],WY:[3,4],SD:[4,4],IA:[5,4],IN:[6,4],OH:[7,4],PA:[8,4],NJ:[9,4],CT:[10,4],
  CA:[1,5],UT:[2,5],CO:[3,5],NE:[4,5],MO:[5,5],KY:[6,5],WV:[7,5],VA:[8,5],MD:[9,5],DE:[10,5],
  AZ:[2,6],NM:[3,6],KS:[4,6],AR:[5,6],TN:[6,6],NC:[7,6],SC:[8,6],DC:[9,6],
  OK:[4,7],LA:[5,7],MS:[6,7],AL:[7,7],GA:[8,7],
  HI:[1,8],TX:[4,8],FL:[9,8],
};

/* ---------- storage ---------- */
const KEY = "taxtracker";
let activeYear = new Date().getFullYear();

function loadAll() { return JSON.parse(localStorage.getItem(KEY) || "{}"); }
function saveAll(all) { localStorage.setItem(KEY, JSON.stringify(all)); }
function emptyLedger(year) {
  return { year, filing_status: "single", state: "", state_rate: null,
           sales_mode: "online", product_type: "",
           incomes: [], expenses: [], payments: [], sales: [] };
}
function ledger() {
  const all = loadAll();
  return Object.assign(emptyLedger(activeYear), all[activeYear]);
}
function saveLedger(l) { const all = loadAll(); all[l.year] = l; saveAll(all); }

/* ---------- calculations (mirror the Python modules) ---------- */
function incomeTax(taxable, status) {
  let tax = 0, lower = 0;
  for (const [upper, rate] of BRACKETS[status]) {
    if (taxable <= lower) break;
    tax += (Math.min(taxable, upper) - lower) * rate;
    lower = upper;
  }
  return tax;
}
function seTax(profit) {
  if (profit <= 0) return 0;
  const net = profit * SE.factor;
  return Math.min(net, SE.wageBase) * SE.ss + net * SE.medicare;
}
function estimate(l) {
  const seGross = l.incomes.filter(i => SE_TYPES.has(i.type)).reduce((s, i) => s + i.amount, 0);
  const otherIncome = l.incomes.filter(i => !SE_TYPES.has(i.type)).reduce((s, i) => s + i.amount, 0);
  const expenses = l.expenses.reduce((s, e) => s + e.amount, 0);
  const seProfit = Math.max(0, seGross - expenses);
  const se = seTax(seProfit);
  const agi = seProfit + otherIncome - se / 2;
  const taxable = Math.max(0, agi - STD_DEDUCTION[l.filing_status]);
  const fed = incomeTax(taxable, l.filing_status);
  const stateRate = l.state_rate != null ? l.state_rate : (STATE_RATES[l.state] || 0);
  const stateTax = taxable * stateRate;
  const fedPaid = l.payments.filter(p => p.jurisdiction === "federal").reduce((s, p) => s + p.amount, 0);
  const statePaid = l.payments.filter(p => p.jurisdiction !== "federal").reduce((s, p) => s + p.amount, 0);
  const total = fed + se + stateTax;
  return { seGross, expenses, seProfit, otherIncome, agi, taxable, fed, se,
           stateRate, stateTax, total, fedPaid, statePaid,
           paid: fedPaid + statePaid, balance: total - fedPaid - statePaid };
}
function deadlines(year) {
  return [["Q1", new Date(year, 3, 15)], ["Q2", new Date(year, 5, 15)],
          ["Q3", new Date(year, 8, 15)], ["Q4", new Date(year + 1, 0, 15)]];
}
function upcomingDeadlines(year) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  return deadlines(year).filter(([, d]) => d >= today);
}
function nexusReport(l) {
  const totals = {};
  for (const s of l.sales) {
    totals[s.state] = totals[s.state] || { sales: 0, txns: 0 };
    totals[s.state].sales += s.amount;
    totals[s.state].txns += s.transactions || 1;
  }
  const out = {};
  for (const [state, t] of Object.entries(totals)) {
    const th = NEXUS[state];
    if (th === null) { out[state] = { ...t, status: "notax", progress: 0 }; continue; }
    if (!th) { out[state] = { ...t, status: "ok", progress: 0 }; continue; }
    const [amt, txnLimit, both] = th;
    const fr = [t.sales / amt];
    if (txnLimit) fr.push(t.txns / txnLimit);
    const progress = both ? Math.min(...fr) : Math.max(...fr);
    out[state] = { ...t, progress,
      status: progress >= 1 ? "hit" : progress >= APPROACHING ? "warn" : "ok" };
  }
  return out;
}
function nexusWarnings(l) {
  const msgs = [];
  for (const [state, n] of Object.entries(nexusReport(l))) {
    const th = NEXUS[state];
    if (n.status === "warn")
      msgs.push({ level: "warn", text: `Approaching economic nexus in ${state}: ` +
        `${fmt(n.sales)} of $${th[0].toLocaleString()} (${Math.round(n.progress * 100)}% of the threshold). ` +
        `Consult a tax advisor before continuing to sell into ${state}.` });
    if (n.status === "hit")
      msgs.push({ level: "reached", text: `Economic nexus threshold REACHED in ${state}: ` +
        `${fmt(n.sales)} of $${th[0].toLocaleString()}. You may be required to register and ` +
        `collect sales tax there — consult a tax advisor now.` });
  }
  return msgs;
}

/* ---------- personalized guide (mirrors taxtracker/guidance.py) ---------- */
function productTaxableIn(product, state) {
  if (!product || !state) return null;
  if (NO_SALES_TAX.has(state)) return false;
  return TAXABILITY[product].has(state);
}

function buildGuide(l) {
  const e = estimate(l);
  const sections = [];
  const hasSE = l.incomes.some(i => SE_TYPES.has(i.type));
  const hasW2 = l.incomes.some(i => i.type === "w2");
  const nextYear = l.year + 1;

  let lines = [];
  const totalIncome = e.seGross + e.otherIncome;
  if (totalIncome > 0) {
    lines.push(`Based on the <strong>${fmt(totalIncome)}</strong> of income you've recorded for ${l.year}, ` +
      `your estimated total tax is <strong>${fmt(e.total)}</strong>: ` +
      `${fmt(e.fed)} federal income tax` +
      (e.se ? `, ${fmt(e.se)} self-employment tax (Social Security + Medicare on your business profit)` : "") +
      (l.state ? `, and ${fmt(e.stateTax)} ${l.state} state income tax` : "") + ".");
    lines.push(`You've recorded ${fmt(e.paid)} in payments, leaving ` +
      `<strong>${fmt(Math.abs(e.balance))}</strong> ${e.balance >= 0 ? "still to pay" : "overpaid"}.`);
    const up = upcomingDeadlines(l.year);
    if (up.length && e.balance > 0)
      lines.push(`To stay on track, pay about <strong>${fmt(e.balance / up.length)}</strong> by ` +
        `${up[0][1].toLocaleDateString()} (${up[0][0]} deadline).`);
  } else {
    lines.push("No income recorded yet. Add income (or import Stripe payouts) and this " +
      "section will show exactly what you owe and when.");
  }
  sections.push(["What you owe right now", lines]);

  lines = [];
  if (hasSE || !l.incomes.length) {
    lines.push(`<strong>Form 1040</strong> with <strong>Schedule C</strong> (business profit & loss) and ` +
      `<strong>Schedule SE</strong> (self-employment tax) — due April 15, ${nextYear}.`);
    lines.push(`<strong>Form 1040-ES</strong> quarterly estimated payments — due ` +
      deadlines(l.year).map(([, d]) => d.toLocaleDateString()).join(", ") +
      `. The IRS expects you to pay as you earn; underpaying can mean penalties.`);
    lines.push(`Pay online at IRS Direct Pay, then record each payment here so your balance stays accurate.`);
  }
  if (hasW2 && !hasSE)
    lines.push(`<strong>Form 1040</strong> — due April 15, ${nextYear}. With W-2 income only, your ` +
      `employer's withholding usually covers you; check it roughly matches the estimate above.`);
  sections.push(["What to file: federal", lines]);

  lines = [];
  if (!l.state) {
    lines.push("Set your home state (Setup or Settings) and this section will tell you " +
      "whether you owe a state return.");
  } else if ((STATE_RATES[l.state] || 0) === 0 && l.state_rate == null) {
    lines.push(`${l.state} has no state income tax — no state income tax return to file. Lucky you.`);
  } else {
    lines.push(`<strong>${l.state} state income tax return</strong> — also due around April 15, ${nextYear}. ` +
      `Most states piggyback on your federal numbers.`);
    lines.push(`Many states also expect quarterly estimated payments; record them with jurisdiction "state".`);
  }
  sections.push(["What to file: state income tax", lines]);

  lines = [];
  const product = l.product_type;
  if (!product) {
    lines.push(`Tell us what you sell (run <strong>Setup</strong>, top right) and this section ` +
      `will explain where sales tax applies to you.`);
  } else {
    const label = PRODUCT_LABELS[product];
    if (l.state) {
      if (NO_SALES_TAX.has(l.state))
        lines.push(`${l.state} has no statewide sales tax, so in-state sales of ${label} aren't taxed.`);
      else if (productTaxableIn(product, l.state))
        lines.push(`${l.state} generally <strong>DOES tax ${label}</strong>. Selling to ${l.state} customers ` +
          `usually means registering for a sales tax permit, collecting tax, and filing returns ` +
          `(the state assigns a monthly or quarterly schedule).`);
      else
        lines.push(`${l.state} generally does <strong>NOT</strong> tax ${label}, so in-state sales are ` +
          `likely exempt — but verify, exemptions have fine print.`);
    }
    if (l.sales_mode === "online") {
      const report = nexusReport(l);
      const hot = Object.entries(report).filter(([, n]) => n.status === "warn" || n.status === "hit");
      if (hot.length) {
        for (const [state, n] of hot) {
          const prefix = n.status === "hit"
            ? `You've <strong>crossed ${state}'s economic nexus threshold</strong> (${fmt(n.sales)} in sales).`
            : `You're at <strong>${Math.round(n.progress * 100)}%</strong> of ${state}'s economic nexus threshold.`;
          lines.push(productTaxableIn(product, state)
            ? `${prefix} ${state} generally taxes ${label} — you may need to register and collect there. ` +
              `<strong>Talk to a tax advisor before your next sale into ${state}.</strong>`
            : `${prefix} The good news: ${state} generally does not tax ${label}, so you may have no ` +
              `collection duty even with nexus — confirm with a tax advisor.`);
        }
      } else {
        lines.push(`You sell online: each state's sales-tax duty only kicks in after you cross its economic ` +
          `nexus threshold (usually $100k/200 transactions per year). Keep recording sales and watch the ` +
          `Nexus Map — we'll warn you at 80%.`);
      }
    } else {
      lines.push(`You sell in person, so sales tax is generally just your home state's rules above — ` +
        `no multi-state tracking needed unless you start selling remotely.`);
    }
    lines.push(`Note: sales tax is collected from the buyer and passed through — it's not part of the ` +
      `income-tax numbers above.`);
  }
  sections.push(["Sales tax: where it applies to you", lines]);

  sections.push(["The fine print", [
    "This guidance assumes a sole proprietor or single-member LLC. Corporations, partnerships, and " +
      "S-corp owner-employees have different filings.",
    "Taxability rules and nexus thresholds are approximations and change constantly. Before registering " +
      "anywhere or filing anything, confirm with a licensed tax professional.",
  ]]);
  return sections;
}

function renderGuide(l) {
  $("#guide-content").innerHTML = buildGuide(l).map(([title, lines]) =>
    `<div class="panel guide-section"><h2>${title}</h2><ul>` +
    lines.map(li => `<li>${li}</li>`).join("") + `</ul></div>`).join("");
}

/* ---------- setup wizard ---------- */
const WIZ_STEPS = [
  {
    q: "Which state do you live or operate in?",
    render(l) {
      const opts = Object.keys(NEXUS).sort().map(s =>
        `<option value="${s}" ${l.state === s ? "selected" : ""}>${s}</option>`).join("");
      return `<select id="wiz-input">${opts}</select><button id="wiz-next">Next</button>`;
    },
    save(l) { l.state = $("#wiz-input").value; },
  },
  {
    q: "What do you mainly sell?",
    choices: [["saas", "SaaS — software customers access online"],
              ["digital", "Digital downloads — apps, media, e-books"],
              ["physical", "Physical goods — things you ship or hand over"],
              ["services", "Services — consulting, design, development…"],
              ["mixed", "A mix of the above"]],
    save(l, v) { l.product_type = v; },
  },
  {
    q: "How do you sell?",
    choices: [["online", "Online — customers can be anywhere"],
              ["in-person", "In person — local, face-to-face sales"]],
    save(l, v) { l.sales_mode = v; },
  },
  {
    q: "What's your tax filing status?",
    choices: [["single", "Single"], ["married", "Married filing jointly"]],
    save(l, v) { l.filing_status = v; },
  },
];

function startWizard() {
  let step = 0;
  const l = ledger();
  const show = () => {
    const s = WIZ_STEPS[step];
    $("#wiz-title").textContent = step === 0 ? "Welcome to TaxTracker" : "Quick setup";
    $("#wiz-question").textContent = s.q;
    $("#wiz-step").textContent = `Question ${step + 1} of ${WIZ_STEPS.length}`;
    const box = $("#wiz-options");
    if (s.choices) {
      box.innerHTML = s.choices.map(([v, label]) =>
        `<button data-v="${v}">${label}</button>`).join("");
      box.querySelectorAll("button").forEach(b =>
        b.addEventListener("click", () => { s.save(l, b.dataset.v); advance(); }));
    } else {
      box.innerHTML = s.render(l);
      $("#wiz-next").addEventListener("click", () => { s.save(l); advance(); });
    }
  };
  const advance = () => {
    step += 1;
    if (step < WIZ_STEPS.length) { show(); return; }
    saveLedger(l);
    localStorage.setItem(KEY + ":setup", "done");
    $("#wizard").classList.add("hidden");
    renderAll();
    document.querySelector('nav button[data-tab="guide"]').click();
  };
  $("#wizard").classList.remove("hidden");
  show();
}

/* ---------- rendering ---------- */
const $ = (sel) => document.querySelector(sel);
const fmt = (n) => "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const today = () => new Date().toISOString().slice(0, 10);

function renderAlerts(l) {
  $("#alerts").innerHTML = nexusWarnings(l)
    .map(m => `<div class="alert ${m.level}">⚠ ${m.text}</div>`).join("");
}

function renderDashboard(l) {
  const e = estimate(l);
  $("#d-total").textContent = fmt(e.total);
  $("#d-paid").textContent = fmt(e.paid);
  const card = $("#d-balance-card");
  card.className = "card " + (e.balance >= 0 ? "due" : "over");
  $("#d-balance-label").textContent = e.balance >= 0 ? "Balance due" : "Overpaid";
  $("#d-balance").textContent = fmt(Math.abs(e.balance));
  const up = upcomingDeadlines(l.year);
  $("#d-deadline").textContent = up.length
    ? `${up[0][0]} · ${up[0][1].toLocaleDateString()}` : "All passed";

  const rows = [
    ["Self-employment income", e.seGross], ["Business expenses", e.expenses],
    ["Net SE profit", e.seProfit], ["W-2 / other income", e.otherIncome],
    ["Standard deduction", STD_DEDUCTION[l.filing_status]],
    ["Taxable income", e.taxable], ["Federal income tax", e.fed],
    ["Self-employment tax", e.se],
  ];
  if (l.state || l.state_rate != null)
    rows.push([`${l.state || "State"} tax (${(e.stateRate * 100).toFixed(2)}%)`, e.stateTax]);
  rows.push(["Total estimated tax", e.total], ["Payments made", e.paid]);
  $("#d-breakdown").innerHTML = rows
    .map(([k, v]) => `<tr><td>${k}</td><td class="num">${fmt(v)}</td></tr>`).join("");

  const t = new Date(); t.setHours(0, 0, 0, 0);
  $("#d-deadlines").innerHTML = deadlines(l.year).map(([q, d]) => {
    const days = Math.round((d - t) / 864e5);
    const when = days < 0 ? "passed" : days === 0 ? "today" : `in ${days} days`;
    return `<tr><td>${q}</td><td>${d.toLocaleDateString()}</td><td>${when}</td></tr>`;
  }).join("");
}

function renderMap(l) {
  const report = nexusReport(l);
  $("#usmap").innerHTML = Object.entries(TILES).map(([state, [col, row]]) => {
    const n = report[state];
    const cls = !n ? (NEXUS[state] === null ? "notax" : "none") : n.status;
    return `<button class="stile ${cls}" data-state="${state}"
      style="grid-column:${col};grid-row:${row}">${state}</button>`;
  }).join("");
  $("#usmap").querySelectorAll(".stile").forEach(el =>
    el.addEventListener("click", () => showStateDetail(el.dataset.state, l)));
}

function showStateDetail(state, l) {
  document.querySelectorAll(".stile").forEach(el =>
    el.classList.toggle("selected", el.dataset.state === state));
  const th = NEXUS[state];
  const n = nexusReport(l)[state];
  let html = `<h2>${state}</h2>`;
  if (th === null) {
    html += `<p>${state} has no statewide sales tax — no economic nexus threshold applies.</p>`;
  } else {
    const [amt, txns, both] = th;
    html += `<p>Economic nexus threshold: <strong>$${amt.toLocaleString()}</strong>` +
      (txns ? ` ${both ? "AND" : "or"} <strong>${txns} transactions</strong>` : "") + ` per year.</p>`;
  }
  if (n) {
    html += `<p>Your sales this year: <strong>${fmt(n.sales)}</strong> across ` +
      `<strong>${n.txns}</strong> transaction(s)` +
      (th ? ` — ${Math.round(n.progress * 100)}% of the threshold.` : ".") + `</p>`;
    if (n.status === "warn" || n.status === "hit")
      html += `<p><strong>⚠ Consult a tax advisor before continuing to sell into ${state}.</strong></p>`;
  } else {
    html += `<p>No sales recorded into ${state} this year.</p>`;
  }
  html += `<p class="hint">Thresholds are approximations and change often — verify with the state or a tax advisor.</p>`;
  const detail = $("#state-detail");
  detail.innerHTML = html;
  detail.classList.remove("hidden");
}

function recordTable(el, items, cols, onDelete) {
  if (!items.length) { el.innerHTML = "<tr><td class='hint'>(none)</td></tr>"; return; }
  el.innerHTML = items.map((it, idx) =>
    "<tr>" + cols.map(c => `<td class="${typeof it[c] === "number" && c === "amount" ? "num" : ""}">` +
      `${c === "amount" ? fmt(it[c]) : (it[c] ?? "")}</td>`).join("") +
    `<td><button class="del" data-i="${idx}">✕</button></td></tr>`).join("");
  el.querySelectorAll(".del").forEach(btn =>
    btn.addEventListener("click", () => onDelete(+btn.dataset.i)));
}

function renderRecords(l) {
  const remove = (list) => (i) => { l[list].splice(i, 1); saveLedger(l); renderAll(); };
  recordTable($("#r-income"), l.incomes, ["date", "amount", "type", "source", "note"], remove("incomes"));
  recordTable($("#r-expenses"), l.expenses, ["date", "amount", "category", "description"], remove("expenses"));
  recordTable($("#r-payments"), l.payments, ["date", "amount", "kind", "jurisdiction", "note"], remove("payments"));
  recordTable($("#r-sales"), l.sales, ["date", "amount", "state", "transactions", "note"], remove("sales"));
}

function renderSettings(l) {
  const f = $("#f-settings");
  f.year.value = l.year;
  f.filing_status.value = l.filing_status;
  f.state.value = l.state || "";
  f.state_rate.value = l.state_rate ?? "";
  f.sales_mode.value = l.sales_mode;
  f.product_type.value = l.product_type || "";
}

function renderHeader(l) {
  $("#year-label").textContent = `Tax year ${l.year} · ${l.filing_status}` +
    (l.state ? ` · ${l.state}` : "");
  $("#mode-badge").textContent = l.sales_mode;
  $("#sale-mode-hint").textContent = l.sales_mode === "in-person"
    ? `In-person mode: buyer's state defaults to your home state${l.state ? " (" + l.state + ")" : ""}.`
    : "Online mode: pick the state each sale shipped to.";
  if (l.sales_mode === "in-person" && l.state) $("#sale-state").value = l.state;
}

function renderAll() {
  const l = ledger();
  renderHeader(l); renderAlerts(l); renderDashboard(l);
  renderGuide(l); renderMap(l); renderRecords(l); renderSettings(l);
}

/* ---------- wiring ---------- */
function populateStates() {
  const opts = Object.keys(NEXUS).sort()
    .map(s => `<option value="${s}">${s}</option>`).join("");
  $("#sale-state").innerHTML = opts;
  $("#settings-state").innerHTML = `<option value="">(none)</option>` + opts;
}

function onSubmit(formSel, build) {
  $(formSel).addEventListener("submit", (ev) => {
    ev.preventDefault();
    const l = ledger();
    build(new FormData(ev.target), l);
    saveLedger(l);
    ev.target.reset();
    setDateDefaults();
    renderAll();
  });
}

function setDateDefaults() {
  document.querySelectorAll('input[type="date"]').forEach(i => { if (!i.value) i.value = today(); });
}

document.querySelectorAll("nav button").forEach(btn =>
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab").forEach(t =>
      t.classList.toggle("active", t.id === "tab-" + btn.dataset.tab));
  }));

onSubmit("#f-income", (d, l) => l.incomes.push({
  amount: +d.get("amount"), source: d.get("source"), type: d.get("type"),
  date: d.get("date"), note: "" }));
onSubmit("#f-expense", (d, l) => l.expenses.push({
  amount: +d.get("amount"), description: d.get("description"),
  category: "general", date: d.get("date") }));
onSubmit("#f-payment", (d, l) => l.payments.push({
  amount: +d.get("amount"), kind: d.get("kind"),
  jurisdiction: d.get("jurisdiction"), date: d.get("date"), note: "" }));
onSubmit("#f-sale", (d, l) => l.sales.push({
  amount: +d.get("amount"), state: d.get("state"),
  transactions: Math.max(1, +d.get("transactions") || 1),
  date: d.get("date"), note: "" }));

$("#f-settings").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const d = new FormData(ev.target);
  const newYear = +d.get("year");
  const all = loadAll();
  const l = Object.assign(emptyLedger(newYear), all[newYear]);
  l.filing_status = d.get("filing_status");
  l.state = d.get("state");
  l.state_rate = d.get("state_rate") === "" ? null : +d.get("state_rate");
  l.sales_mode = d.get("sales_mode");
  l.product_type = d.get("product_type");
  activeYear = newYear;
  saveLedger(l);
  renderAll();
});

$("#btn-export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(loadAll(), null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "taxtracker-data.json";
  a.click();
  URL.revokeObjectURL(a.href);
});
$("#btn-import").addEventListener("change", async (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    saveAll(data);
    renderAll();
    alert("Data imported.");
  } catch { alert("That file isn't valid TaxTracker JSON."); }
  ev.target.value = "";
});
$("#btn-wipe").addEventListener("click", () => {
  if (confirm("Delete ALL TaxTracker data stored in this browser? Export first if unsure.")) {
    localStorage.removeItem(KEY);
    renderAll();
  }
});

$("#btn-wizard").addEventListener("click", startWizard);

populateStates();
setDateDefaults();
renderAll();
/* First visit: walk new users through setup automatically. */
if (!localStorage.getItem(KEY + ":setup") && !ledger().incomes.length) startWizard();
