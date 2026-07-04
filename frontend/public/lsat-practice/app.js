/* LSAT Practice — static edition (spec 025).
 *
 * Zero-dependency vanilla app. One fetch of ./data/content.json, hash-routed
 * views, client-side grading, localStorage progress. Interaction and a11y
 * patterns are ported from the Lab's LsatLab.tsx: radiogroup semantics,
 * A–E/Enter keyboard drilling (modifier-safe), aria-live verdicts.
 */
'use strict';

// --------------------------------------------------------------------------
// State + storage
// --------------------------------------------------------------------------

const STORE_KEY = 'lsat-practice.attempts.v1';
const MAX_ATTEMPTS = 5000;

/** @type {{sections:any[],concepts:any[],passages:any[],questions:any[],counts:any,generated_at:string}|null} */
let CONTENT = null;

function loadAttempts() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function saveAttempt(attempt) {
  const attempts = loadAttempts();
  attempts.push(attempt);
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(attempts.slice(-MAX_ATTEMPTS)));
  } catch {
    /* storage full/blocked — practice still works, stats just won't persist */
  }
}

function resetAttempts() {
  try {
    localStorage.removeItem(STORE_KEY);
  } catch {
    /* ignore */
  }
}

// --------------------------------------------------------------------------
// Small DOM helpers (no innerHTML with content — everything via textContent)
// --------------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') {
      node.addEventListener(k.slice(2), v);
    } else node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function announce(text) {
  const region = document.getElementById('announcer');
  if (region) {
    region.textContent = '';
    // Re-set on the next frame so repeat verdicts are re-announced.
    requestAnimationFrame(() => {
      region.textContent = text;
    });
  }
}

function shuffle(list) {
  const arr = list.slice();
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

const pct = (num, den) => (den ? Math.round((num / den) * 100) + '%' : '—');

// --------------------------------------------------------------------------
// Question card (shared by drill + passage views)
// --------------------------------------------------------------------------

function questionCard(question, { onGraded, onNext } = {}) {
  let selected = null;
  let graded = false;

  const meta = el(
    'div',
    { class: 'qmeta' },
    el('span', { class: 'qid', text: question.id }),
    el('span', { text: question.section }),
    el('span', { class: `pill ${question.difficulty}`, text: question.difficulty }),
    (question.concepts || []).slice(0, 3).map((c) => el('span', { text: c })),
  );

  const stem = el('p', { class: 'stem', text: question.stem });

  const LABELS = question.choices.map((c) => c.label);
  const choiceButtons = new Map();
  const choicesEl = el(
    'ul',
    { class: 'choices', role: 'radiogroup', 'aria-label': `Answer choices for ${question.id}` },
  );
  for (const [i, choice] of question.choices.entries()) {
    const btn = el(
      'button',
      {
        class: 'choice',
        type: 'button',
        role: 'radio',
        'aria-checked': 'false',
        // APG radio-group: roving tabindex — one Tab stop for the whole group.
        tabindex: i === 0 ? '0' : '-1',
        onclick: () => select(choice.label),
      },
      el('span', { class: 'label', text: choice.label }),
      el('span', { text: choice.text }),
    );
    choiceButtons.set(choice.label, btn);
    choicesEl.append(el('li', {}, btn));
  }

  const submitBtn = el('button', {
    class: 'btn primary',
    type: 'button',
    text: 'Submit',
    disabled: true,
    onclick: submit,
  });
  const actions = el('div', { class: 'actions' }, submitBtn);

  const card = el(
    'article',
    { class: 'qcard', tabindex: '-1', onkeydown: handleKeys },
    meta,
    stem,
    choicesEl,
    el(
      'p',
      { class: 'kbd-hint' },
      'Keyboard: ',
      el('kbd', { text: 'A' }),
      '–',
      el('kbd', { text: 'E' }),
      ' to choose · ',
      el('kbd', { text: 'Enter' }),
      ' to submit',
    ),
    actions,
  );

  function select(label, { focus = false } = {}) {
    if (graded) return;
    selected = label;
    for (const [l, btn] of choiceButtons) {
      btn.setAttribute('aria-checked', l === label ? 'true' : 'false');
      // Selection follows focus: the checked radio owns the group's Tab stop.
      btn.setAttribute('tabindex', l === label ? '0' : '-1');
    }
    if (focus) choiceButtons.get(label).focus();
    submitBtn.disabled = false;
  }

  function handleKeys(event) {
    if (graded) return;
    // Let modified shortcuts (Ctrl/⌘/Alt — e.g. Select All) reach the browser.
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const tag = event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;

    const key = event.key.toUpperCase();
    if (['A', 'B', 'C', 'D', 'E'].includes(key) && choiceButtons.has(key)) {
      event.preventDefault();
      select(key, { focus: true });
      return;
    }

    // APG radio-group arrows: move + select (selection follows focus).
    const ARROWS = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 };
    if (event.key in ARROWS && event.target.closest('.choices')) {
      event.preventDefault();
      const from = LABELS.indexOf(selected ?? LABELS[0]);
      const base = selected === null ? (ARROWS[event.key] > 0 ? -1 : 1) : from;
      const next = LABELS[(base + ARROWS[event.key] + LABELS.length) % LABELS.length];
      select(next, { focus: true });
      return;
    }

    if (event.key === 'Enter') {
      const choiceBtn = event.target.closest ? event.target.closest('.choice') : null;
      if (choiceBtn) {
        // Enter on an unselected choice selects it (native click); on the
        // already-selected choice it submits. Never submit a non-focused pick.
        const label = choiceBtn.querySelector('.label').textContent;
        if (label === selected) {
          event.preventDefault();
          submit();
        }
        return;
      }
      if (selected) {
        event.preventDefault();
        submit();
      }
    }
  }

  function submit() {
    if (!selected || graded) return;
    graded = true;
    const correct = selected === question.correct;

    for (const [label, btn] of choiceButtons) {
      btn.disabled = true;
      if (label === question.correct) btn.classList.add('correct');
      else if (label === selected) btn.classList.add('wrong');
    }

    submitBtn.remove();
    actions.prepend(
      el('span', {
        class: `verdict ${correct ? 'ok' : 'no'}`,
        text: correct ? 'Correct' : `Incorrect — answer was ${question.correct}`,
      }),
    );
    let nextBtn = null;
    if (onNext) {
      nextBtn = el('button', { class: 'btn', type: 'button', text: 'Next →', onclick: onNext });
      actions.append(nextBtn);
    }

    const explain = el(
      'div',
      { class: 'explain' },
      el('h4', { text: 'Explanation' }),
      el('p', { text: question.explanation }),
    );
    const refs = (question.references || []).filter((r) => r.url);
    if (refs.length) {
      explain.append(
        el(
          'div',
          { class: 'refs' },
          refs.map((r) => el('a', { href: r.url, rel: 'noreferrer', text: `↗ ${r.title}` })),
        ),
      );
    }
    card.append(explain);

    // The focused control was just removed/disabled — restore focus so
    // keyboard users land on the natural continuation (WCAG 2.4.3).
    (nextBtn || card).focus();

    announce(correct ? 'Correct.' : `Incorrect. The correct answer was ${question.correct}.`);
    saveAttempt({
      qid: question.id,
      section: question.section,
      choice: selected,
      correct,
      ts: Date.now(),
    });
    if (onGraded) onGraded(correct);
  }

  return card;
}

// --------------------------------------------------------------------------
// Views
// --------------------------------------------------------------------------

function viewHome() {
  const bySection = { LR: [], RC: [], LG: [] };
  for (const q of CONTENT.questions) bySection[q.section]?.push(q);
  const attempts = loadAttempts();
  const correct = attempts.filter((a) => a.correct).length;

  const cards = CONTENT.sections.map((s) => {
    const count = (bySection[s.code] || []).length;
    const href =
      s.code === 'LR' ? '#/drill/LR' : s.code === 'RC' ? '#/passages/RC' : '#/passages/LG';
    return el(
      'div',
      { class: 'card' },
      el('h3', {}, s.name, el('span', { class: 'pill', text: `${count} questions` })),
      el('p', { class: 'muted', text: s.description }),
      el('p', { class: 'faint', text: `${s.format} · ${s.timing}` }),
      el('p', {}, el('a', { href, text: 'Practice →' })),
    );
  });

  return el(
    'section',
    {},
    el('h2', { text: 'Practice the LSAT, no account, no server' }),
    el('p', { class: 'muted' },
      'Every question was authored for this project (CC0) and reviewed before release. ',
      'Grading happens in your browser; your progress stays on this device.'),
    el('div', { class: 'grid' }, cards),
    el(
      'p',
      { class: 'muted', style: 'margin-top:1.2rem' },
      attempts.length
        ? `Your record so far: ${correct}/${attempts.length} (${pct(correct, attempts.length)}) · `
        : 'No attempts yet · ',
      el('a', { href: '#/stats', text: 'view stats' }),
    ),
  );
}

function viewDrill() {
  const pool = CONTENT.questions.filter((q) => q.section === 'LR');
  let difficulty = 'any';
  let queue = shuffle(pool);
  let index = 0;
  let sessionAttempts = 0;
  let sessionCorrect = 0;

  const counter = el('span', { class: 'muted' });
  const holder = el('div', {});

  function filtered() {
    return difficulty === 'any' ? queue : queue.filter((q) => q.difficulty === difficulty);
  }

  function updateCounter(total) {
    counter.textContent = `Question ${(index % total) + 1} of ${total}` +
      (sessionAttempts ? ` · session ${sessionCorrect}/${sessionAttempts}` : '');
  }

  function renderCurrent() {
    const list = filtered();
    holder.replaceChildren();
    if (!list.length) {
      holder.append(el('p', { class: 'empty', text: 'No questions at this difficulty yet.' }));
      counter.textContent = '';
      return;
    }
    const q = list[index % list.length];
    updateCounter(list.length);
    holder.append(
      questionCard(q, {
        onGraded: (ok) => {
          sessionAttempts += 1;
          if (ok) sessionCorrect += 1;
          updateCounter(list.length);
        },
        onNext: () => {
          index += 1;
          renderCurrent();
          const nextCard = holder.querySelector('.qcard');
          if (nextCard) nextCard.focus();
        },
      }),
    );
  }

  const seg = el(
    'div',
    { class: 'seg', role: 'group', 'aria-label': 'Difficulty filter' },
    ['any', 'easy', 'med', 'hard'].map((d) =>
      el('button', {
        type: 'button',
        text: d === 'any' ? 'Any' : d,
        'aria-pressed': d === difficulty ? 'true' : 'false',
        onclick: (event) => {
          difficulty = d;
          index = 0;
          for (const b of seg.querySelectorAll('button')) b.setAttribute('aria-pressed', 'false');
          event.currentTarget.setAttribute('aria-pressed', 'true');
          renderCurrent();
        },
      }),
    ),
  );

  renderCurrent();
  return el(
    'section',
    {},
    el('h2', { text: 'Logical Reasoning drill' }),
    el(
      'div',
      { class: 'toolbar' },
      seg,
      el('button', {
        class: 'btn subtle',
        type: 'button',
        text: '↻ Reshuffle',
        onclick: () => {
          queue = shuffle(pool);
          index = 0;
          renderCurrent();
        },
      }),
      el('span', { class: 'spacer' }),
      counter,
    ),
    holder,
  );
}

function viewPassageList(section) {
  const passages = CONTENT.passages.filter((p) => p.section === section);
  const title = section === 'RC' ? 'Reading Comprehension' : 'Logic Games';
  const noun = section === 'RC' ? 'passage' : 'game';
  if (!passages.length) {
    return el('section', {}, el('h2', { text: title }), el('p', { class: 'empty', text: `No ${noun}s yet.` }));
  }
  const cards = passages.map((p) => {
    const count = CONTENT.questions.filter((q) => q.passage_id === p.id).length;
    return el(
      'div',
      { class: 'card' },
      el('h3', {}, p.title, el('span', { class: 'pill', text: `${count} questions` })),
      el('p', { class: 'muted', text: p.summary || '' }),
      el('p', {}, el('a', { href: `#/passage/${p.id}`, text: `Open ${noun} →` })),
    );
  });
  return el('section', {}, el('h2', { text: title }), el('div', { class: 'grid' }, cards));
}

function viewPassage(passageId) {
  const passage = CONTENT.passages.find((p) => p.id === passageId);
  if (!passage) {
    return el('section', {}, el('p', { class: 'empty', text: 'Unknown passage.' }));
  }
  const questions = CONTENT.questions.filter((q) => q.passage_id === passageId);

  const context = el(
    'div',
    { class: 'context' },
    el('h3', { text: passage.title }),
    passage.passage ? el('p', { class: 'body', text: passage.passage }) : null,
    passage.setup ? el('p', { class: 'body', text: passage.setup }) : null,
    passage.rules && passage.rules.length
      ? el('ol', {}, passage.rules.map((r) => el('li', { text: r.replace(/^\d+\.\s*/, '') })))
      : null,
  );

  const stack = el('div', {}, questions.map((q) => questionCard(q)));
  const back = passage.section === 'RC' ? '#/passages/RC' : '#/passages/LG';

  return el(
    'section',
    {},
    el('p', {}, el('a', { href: back, text: '← All ' + (passage.section === 'RC' ? 'passages' : 'games') })),
    el('div', { class: 'split' }, context, stack),
  );
}

function viewConcepts() {
  const list = el('div', {});

  function render(filter) {
    const needle = filter.trim().toLowerCase();
    const rows = CONTENT.concepts.filter(
      (c) =>
        !needle ||
        c.name.toLowerCase().includes(needle) ||
        (c.summary || '').toLowerCase().includes(needle) ||
        c.id.includes(needle),
    );
    const nodes = rows.length
      ? rows.map((c) =>
          el(
            'details',
            { class: 'concept' },
            el(
              'summary',
              {},
              c.name,
              el('span', { class: 'muted', text: ` — ${c.summary}` }),
            ),
            el(
              'div',
              { class: 'detail' },
              c.detail ? el('p', { text: c.detail }) : null,
              c.examples && c.examples.length
                ? el('ul', {}, c.examples.map((x) => el('li', { text: x })))
                : null,
              c.see_also && c.see_also.length
                ? el('p', { class: 'faint', text: 'See also: ' + c.see_also.join(', ') })
                : null,
            ),
          ),
        )
      : [el('p', { class: 'empty', text: 'No concepts match.' })];
    // replaceChildren is variadic — an un-spread array would be stringified.
    list.replaceChildren(...nodes);
  }

  render('');
  return el(
    'section',
    {},
    el('h2', { text: `Concept catalog (${CONTENT.concepts.length})` }),
    el('input', {
      class: 'search',
      type: 'search',
      placeholder: 'Search concepts…',
      'aria-label': 'Search concepts',
      oninput: (event) => render(event.target.value),
    }),
    list,
  );
}

function viewStats() {
  const attempts = loadAttempts();
  const correct = attempts.filter((a) => a.correct).length;
  const perSection = { LR: [0, 0], RC: [0, 0], LG: [0, 0] };
  for (const a of attempts) {
    if (!perSection[a.section]) perSection[a.section] = [0, 0];
    perSection[a.section][0] += 1;
    if (a.correct) perSection[a.section][1] += 1;
  }

  const table = el(
    'table',
    { class: 'stats' },
    el('thead', {}, el('tr', {},
      el('th', { text: 'Section' }), el('th', { text: 'Attempts' }),
      el('th', { text: 'Correct' }), el('th', { text: 'Accuracy' }))),
    el('tbody', {},
      Object.entries(perSection).map(([sec, [att, ok]]) =>
        el('tr', {},
          el('td', { text: sec }), el('td', { text: String(att) }),
          el('td', { text: String(ok) }), el('td', { text: pct(ok, att) })))),
  );

  return el(
    'section',
    {},
    el('h2', { text: 'Your practice record' }),
    el('p', {}, el('span', { class: 'big', text: pct(correct, attempts.length) }),
      el('span', { class: 'muted', text: `  ${correct} correct of ${attempts.length} attempts (all time, this browser)` })),
    table,
    el('button', {
      class: 'btn danger',
      type: 'button',
      text: 'Reset all progress',
      onclick: () => {
        if (window.confirm('Delete all locally stored attempts? This cannot be undone.')) {
          resetAttempts();
          route();
        }
      },
    }),
  );
}

// --------------------------------------------------------------------------
// Router
// --------------------------------------------------------------------------

const ROUTES = [
  { pattern: /^#?\/?$|^#\/home$/, nav: 'home', render: () => viewHome() },
  { pattern: /^#\/drill\/LR$/, nav: 'drill', render: () => viewDrill() },
  { pattern: /^#\/passages\/RC$/, nav: 'rc', render: () => viewPassageList('RC') },
  { pattern: /^#\/passages\/LG$/, nav: 'lg', render: () => viewPassageList('LG') },
  { pattern: /^#\/passage\/(.+)$/, nav: null, render: (m) => viewPassage(m[1]) },
  { pattern: /^#\/concepts$/, nav: 'concepts', render: () => viewConcepts() },
  { pattern: /^#\/stats$/, nav: 'stats', render: () => viewStats() },
];

let firstRoute = true;

function setNav(nav) {
  for (const link of document.querySelectorAll('[data-nav]')) {
    if (nav && link.getAttribute('data-nav') === nav) {
      link.setAttribute('aria-current', 'page');
    } else {
      link.removeAttribute('aria-current');
    }
  }
}

function afterRoute(view) {
  // SPA route change: the focused link was just detached, so move focus to
  // the new view and announce it (WCAG 2.4.3; silent-navigation fix). The
  // initial page load keeps the browser's default focus behavior.
  if (firstRoute) {
    firstRoute = false;
    return;
  }
  view.focus();
  const heading = view.querySelector('h2');
  if (heading) announce(heading.textContent);
}

function route() {
  if (!CONTENT) return;
  const hash = window.location.hash || '#/home';
  const view = document.getElementById('view');
  for (const r of ROUTES) {
    const match = hash.match(r.pattern);
    if (match) {
      // Passage detail highlights its section tab; unknown ids highlight none.
      let nav = r.nav;
      if (!nav && match[1]) {
        const p = CONTENT.passages.find((x) => x.id === match[1]);
        nav = p ? (p.section === 'RC' ? 'rc' : 'lg') : null;
      }
      setNav(nav);
      view.replaceChildren(r.render(match));
      afterRoute(view);
      return;
    }
  }
  setNav(null);
  view.replaceChildren(el('p', { class: 'empty', text: 'Page not found.' }),
    el('p', {}, el('a', { href: '#/home', text: '← Home' })));
  afterRoute(view);
}

// --------------------------------------------------------------------------
// Boot
// --------------------------------------------------------------------------

async function boot() {
  const view = document.getElementById('view');
  try {
    const resp = await fetch('./data/content.json');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    CONTENT = await resp.json();
  } catch (err) {
    view.replaceChildren(
      el('p', { class: 'empty' },
        'Could not load the question bank (', String(err), '). ',
        'If you are running locally, regenerate it with "make lsat-export".'),
    );
    return;
  }
  const meta = document.getElementById('footer-meta');
  if (meta) {
    const when = (CONTENT.generated_at || '').slice(0, 10);
    meta.textContent = `${CONTENT.counts.total} questions · content built ${when}`;
  }
  window.addEventListener('hashchange', route);
  route();
}

boot();
