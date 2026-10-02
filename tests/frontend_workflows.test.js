const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
function section(start, end) {
  const offset = source.indexOf(start);
  assert.ok(offset >= 0, start);
  const limit = source.indexOf(end, offset + start.length);
  assert.ok(limit > offset, end);
  return source.slice(offset, limit);
}

function harness(extra = {}) {
  let nextTimer = 0;
  const timers = new Map();
  const notices = [];
  const context = vm.createContext({
    console,
    currentProjectPath: 'project',
    currentLanguage: 'en',
    enabledSkills: new Set(['a']),
    pendingSyncSummary: null,
    pendingSyncRequestId: 0,
    pendingSyncTimer: null,
    pendingSyncInFlight: false,
    pendingSyncQueued: false,
    updateStatistics() {},
    setTimeout(callback) { timers.set(++nextTimer, callback); return nextTimer; },
    clearTimeout(id) { timers.delete(id); },
    showToast(message, type) { notices.push({ message, type }); },
    ...extra,
  });
  return {
    context, notices,
    runTimers() {
      const callbacks = [...timers.values()];
      timers.clear();
      callbacks.forEach(callback => callback());
    },
    load(code) { vm.runInContext(code, context); },
  };
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const previewCode = section('async function refreshPendingSyncSummary()', 'function updateWorkspaceMode()');

test('rapid changes run one preview at a time and keep only the latest selection', async () => {
  const calls = [];
  const h = harness({ window: { pywebview: { api: {
    preview_sync(project, selection) {
      const request = deferred();
      calls.push({ project, selection: [...selection], ...request });
      return request.promise;
    },
  } } } });
  h.load(previewCode);
  h.context.queuePendingSyncSummary(); h.runTimers();
  h.context.enabledSkills.add('b');
  h.context.queuePendingSyncSummary(); h.runTimers();
  h.context.enabledSkills.delete('a');
  h.context.queuePendingSyncSummary(); h.runTimers();
  assert.equal(calls.length, 1);
  calls[0].resolve({ summary: { add: 99 } }); await settle();
  assert.equal(h.context.pendingSyncSummary, null);
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[1].selection, ['b']);
  calls[1].resolve({ summary: { add: 1 } }); await settle();
  assert.equal(h.context.pendingSyncSummary.add, 1);
  assert.equal(h.context.pendingSyncInFlight, false);
});

test('selection change invalidates a result before the debounce timer fires', async () => {
  const request = deferred();
  const h = harness({ window: { pywebview: { api: { preview_sync: () => request.promise } } } });
  h.load(previewCode);
  h.context.queuePendingSyncSummary(); h.runTimers();
  h.context.enabledSkills.add('b'); h.context.queuePendingSyncSummary();
  request.resolve({ summary: { add: 99 } }); await settle();
  assert.equal(h.context.pendingSyncSummary, null);
  assert.equal(h.context.pendingSyncInFlight, false);
});

test('a failed old preview still lets the latest project finish', async () => {
  const calls = [];
  const h = harness({ window: { pywebview: { api: {
    preview_sync(project) {
      const request = deferred(); calls.push({ project, ...request }); return request.promise;
    },
  } } } });
  h.load(previewCode);
  h.context.queuePendingSyncSummary(); h.runTimers();
  h.context.currentProjectPath = 'other';
  h.context.queuePendingSyncSummary(); h.runTimers();
  calls[0].reject(new Error('read failed')); await settle();
  assert.equal(calls.length, 2);
  assert.equal(calls[1].project, 'other');
  calls[1].resolve({ summary: { modify: 2 } }); await settle();
  assert.equal(h.context.pendingSyncSummary.modify, 2);
  assert.equal(h.context.pendingSyncInFlight, false);
});

test('leaving project mode suppresses old results and queued work', async () => {
  const request = deferred(); let calls = 0;
  const h = harness({ window: { pywebview: { api: {
    preview_sync() { calls++; return request.promise; },
  } } } });
  h.load(previewCode);
  h.context.queuePendingSyncSummary(); h.runTimers();
  h.context.queuePendingSyncSummary(); h.runTimers();
  h.context.currentProjectPath = null;
  request.resolve({ summary: { add: 1 } }); await settle();
  assert.equal(h.context.pendingSyncSummary, null);
  assert.equal(calls, 1);
});

function row(filename) {
  const status = { innerHTML: 'original' };
  const toggle = { checked: false, indeterminate: false };
  return {
    dataset: { filename }, status, toggle,
    querySelector(selector) {
      return selector === '.skill-row-status' ? status : toggle;
    },
  };
}

test('selection updates preserve row and checkbox identity, including collection partial state', () => {
  const a = { filename: 'a' }, b = { filename: 'b' };
  const member = filename => ({ filename, collection: { effective_enabled: true } });
  const collection = { filename: '@collection:kit', is_collection: true, collection_members: [member('c'), member('d')] };
  const rows = [row('a'), row('b'), row('@collection:kit')];
  const focusedCheckbox = rows[0].toggle;
  const messages = new Proxy({}, { get: (_target, key) => key });
  const h = harness({
    enabledSkills: new Set(),
    projects: [{ path: 'project', skills_status: { a: 'synced' }, managed_skills: ['a'] }],
    locales: { en: messages },
    escapeHtml: value => value,
    cardsGrid: { querySelectorAll: () => rows },
    displaySkillsByFilename: new Map([a, b, collection].map(skill => [skill.filename, skill])),
    syncBtn: { classList: { add() {} } },
    queuePendingSyncSummary() {},
    renderSkillsGrid() { throw new Error('Must not rebuild the list'); },
  });
  h.load(section('function resolveCollectionProjectState(', 'function renderSkillsGrid()'));
  h.load(section('function resolveCollectionMemberProjectState(', 'function openCollectionModal('));
  h.load(section('function handleToggleSkill(', 'function getCollectionDisplaySkill('));
  h.context.handleToggleSkill('a', true);
  assert.equal(rows[0].toggle, focusedCheckbox);
  assert.equal(focusedCheckbox.checked, true);
  assert.match(rows[0].status.innerHTML, /statusSynced/);
  assert.equal(rows[1].status.innerHTML, 'original');
  h.context.handleToggleSkill('a', false);
  assert.match(rows[0].status.innerHTML, /statusPendingUnmount/);
  h.context.handleToggleSkill('c', true);
  assert.equal(rows[2].toggle.indeterminate, true);
  assert.match(rows[2].status.innerHTML, /statusPartiallyEnabled/);
  h.context.handleToggleCollectionMount(collection, true);
  assert.equal(rows[2].toggle.indeterminate, false);
  assert.equal(rows[2].toggle.checked, true);
  h.context.handleToggleCollectionMount(collection, false);
  assert.equal(rows[2].toggle.checked, false);
  assert.equal(rows[2].toggle.indeterminate, false);
});

function refreshHarness(api) {
  const h = harness({
    window: { pywebview: { api } },
    document: { querySelector: () => null },
    locales: { en: { toastLoadFail: 'Load failed: ', toastProjectFail: 'Project failed: ', toastRefreshSuccess: 'refreshed' } },
    skills: [{ filename: 'old' }], projects: [{ path: 'project' }],
    renderCategoryFilterBar() {}, renderSkillsGrid() {}, renderProjectsList() {},
    _loadProjectState() {},
  });
  h.load(section('async function fetchSkills(', 'function updateStatistics()'));
  h.load(section('async function handleRefreshSkills()', '// Settings Modal Handlers'));
  return h;
}

test('refresh failures show one failure and never a success notice', async () => {
  for (const failure of ['skills', 'projects']) {
    const h = refreshHarness({
      async get_skills() { if (failure === 'skills') throw new Error('disk'); return []; },
      async get_projects() { if (failure === 'projects') throw new Error('disk'); return []; },
    });
    await h.context.handleRefreshSkills();
    assert.equal(h.notices.length, 1);
    assert.equal(h.notices[0].type, 'error');
  }
});

test('malformed refresh responses retain existing data and report failure', async () => {
  const h = refreshHarness({ async get_skills() { return { error: 'unavailable' }; } });
  assert.equal(await h.context.fetchSkills(), false);
  assert.equal(h.context.skills[0].filename, 'old');
  assert.equal(h.notices[0].type, 'error');
});

test('successful refresh replaces data and emits success', async () => {
  const h = refreshHarness({
    async get_skills() { return [{ filename: 'new' }]; },
    async get_projects() { return [{ path: 'project' }]; },
  });
  await h.context.handleRefreshSkills();
  assert.equal(h.context.skills[0].filename, 'new');
  assert.deepEqual(h.notices, [{ message: 'refreshed', type: 'success' }]);
});

test('late skill and project refreshes cannot replace newer state or show stale errors', async () => {
  for (const kind of ['skills', 'projects']) {
    const first = deferred(), second = deferred(); let calls = 0;
    const api = {[kind === 'skills' ? 'get_skills' : 'get_projects']: () => (++calls === 1 ? first.promise : second.promise)};
    const h = refreshHarness(api);
    const refresh = kind === 'skills' ? h.context.fetchSkills : h.context.fetchProjects;
    const a = refresh(), b = refresh();
    second.resolve(kind === 'skills' ? [{filename: 'new'}] : [{path: 'new'}]); await b;
    first.resolve(kind === 'skills' ? [{filename: 'old'}] : [{path: 'old'}]);
    assert.equal(await a, false);
    assert.equal(h.context[kind][0][kind === 'skills' ? 'filename' : 'path'], 'new');
    const old = deferred(); calls = 0;
    api[kind === 'skills' ? 'get_skills' : 'get_projects'] = () => (++calls === 1 ? old.promise : Promise.resolve([]));
    const c = refresh(), d = refresh(); await d;
    old.reject(new Error('stale failure')); await c;
    assert.equal(h.notices.length, 0);
  }
});

test('changing library identity invalidates an old list request', async () => {
  const request = deferred();
  const h = refreshHarness({get_skills: () => request.promise});
  h.context.skillsDirPath = {textContent: 'A'};
  const load = h.context.fetchSkills();
  h.context.skillsDirPath.textContent = 'B';
  request.resolve([{filename: 'from-A'}]);
  assert.equal(await load, false);
  assert.equal(h.context.skills[0].filename, 'old');
});

test('single-project refresh keeps unrelated project identity', async () => {
  const untouched = {path: 'other'};
  const h = refreshHarness({async get_project(path) {return {path, managed_skills: ['demo']};}});
  h.context.projects = [{path: 'project'}, untouched];
  assert.equal(await h.context.fetchProjects({projectPath: 'project'}), true);
  assert.equal(h.context.projects[1], untouched);
  assert.equal(h.context.projects[0].managed_skills[0], 'demo');
});

test('settings directory pickers stage choices and cancellation leaves backend library unchanged', async () => {
  const flags = [];
  const h = harness({
    settingsSkillsDir: {value: 'A'}, settingsScanDir: {value: 'old-scan'}, settingsModal: {},
    locales: {en: {toastPathUpdate: 'path'}}, deactivateModal() {},
    window: {pywebview: {api: {
      async change_skills_dir(apply) {flags.push(apply); return {skills_dir: 'B'};},
      async pick_default_scan_dir(apply) {flags.push(apply); return {default_scan_dir: 'new-scan'};},
    }}},
  });
  h.load(section('function closeSettingsModal()', 'async function handleSaveSettings()'));
  await h.context.handleSettingsPickSkillsDir();
  await h.context.handleSettingsPickScanDir();
  h.context.closeSettingsModal();
  assert.deepEqual(flags, [false, false]);
  assert.equal(h.context.settingsSkillsDir.value, 'B');
});

test('a second sync plan change never produces a success notice', async () => {
  let calls = 0;
  const preview = {plan_token: 'one', summary: {add: 1, adopt: 0, modify: 0, delete: 0, preserve: 0}, has_conflicts: false};
  const h = harness({
    locales: {en: new Proxy({}, {get: (_t, key) => key})},
    syncBtn: {innerHTML: 'Sync', setAttribute() {}, removeAttribute() {}, classList: {contains: () => true, add() {}, remove() {}}},
    lucide: {createIcons() {}}, buildSyncReview: p => p, showStructuredReview: async () => true,
    queuePendingSyncSummary() {},
    saveSyncResult() {throw new Error('Unapplied result cannot be saved');},
    window: {pywebview: {api: {
      async preview_sync() {return preview;},
      async sync_skills() {calls++; return {requires_confirmation: true, error: '', preview: {...preview, plan_token: String(calls)}};},
    }}},
  });
  h.load(section('async function handleSyncSkills()', 'function formatImportPreview('));
  await h.context.handleSyncSkills();
  assert.equal(calls, 2);
  assert.equal(h.notices.some(n => n.type === 'success'), false);
  assert.equal(h.notices[0].type, 'error');
});
