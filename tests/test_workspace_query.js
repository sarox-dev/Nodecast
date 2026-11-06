const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const template = fs.readFileSync('app/templates/base.html', 'utf8');
assert.doesNotMatch(template, /id="ask-diagnostics-toggle"/);
assert.doesNotMatch(template, />Personal recall</i);
assert.doesNotMatch(template, /Answers and evidence from information you intentionally saved/);

function element() {
  return { hidden: false, value: '', textContent: '', dataset: {}, listeners: {},
    classList: { add() {}, remove() {}, toggle() {} },
    addEventListener(type, fn) { this.listeners[type] = fn; },
    focus() {}, setAttribute() {}, getClientRects() { return []; } };
}
const ids = Object.fromEntries(['search-form','query','content-view','constellation-stage','workspace-view-title',
  'workspace-results-query-form','workspace-results-query','workspace-view-eyebrow','workspace-view-description',
  'results-container','workspace-results-close','loading-indicator','settings-overlay'].map(id => [id, element()]));
const shell = element();
const document = { getElementById: id => ids[id] || null, querySelector: () => shell,
  querySelectorAll: () => [], addEventListener() {} };
let ready;
const window = { webMode: false, addEventListener: (event, fn) => { if (event === 'DOMContentLoaded') ready = fn; },
  setTimeout() {}, setWebMode() {} };
const storage = { getItem: () => null, setItem() {} };
const context = { document, window, localStorage: storage, HTMLInputElement: class {}, HTMLTextAreaElement: class {}, HTMLSelectElement: class {}, Event: class {} };
vm.runInNewContext(fs.readFileSync('app/static/js/workspace-controller.js', 'utf8'), context);
ready();
let submits = 0;
ids['search-form'].requestSubmit = () => { submits++; ids['search-form'].listeners.submit(); };
ids.query.value = 'Pirmais jautājums';
ids['search-form'].listeners.submit();
assert.equal(ids['workspace-results-query'].value, 'Pirmais jautājums');
assert.equal(ids['workspace-view-title'].hidden, true);
assert.equal(ids['workspace-results-query-form'].hidden, false);
ids['workspace-results-query'].value = 'Jauns jautājums';
ids['workspace-results-query-form'].listeners.submit({ preventDefault() {} });
assert.equal(ids.query.value, 'Jauns jautājums');
assert.equal(submits, 1);
assert.equal(ids['content-view'].hidden, false);
ids['workspace-results-query'].value = '  ';
ids['workspace-results-query-form'].listeners.submit({ preventDefault() {} });
assert.equal(submits, 1);
console.log('Workspace result query checks passed');
