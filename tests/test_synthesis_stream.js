const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/atomic-view.js', 'utf8');
const part = (a, b) => source.slice(source.indexOf(a), source.indexOf(b, source.indexOf(a)));
const draft = {innerHTML: ''};
const context = {window: {currentMemoryBlocks: []}, resultsContainer: {querySelector: () => draft},
    allResults: [{id: 'a'}], escapeHtml: s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;')};
vm.createContext(context);
vm.runInContext(part('function renderCitationParts(', 'function renderMemoryView(') + part('function renderStreamingDraft(', 'function renderStreamingMemoryView('), context);
context.renderStreamingDraft('Summary\n\nDetails\nFallback');
assert.ok(draft.innerHTML.includes('Fallback'));
context.window.currentMemoryBlocks[0] = [{type: 'bullets', items: [{parts: [{text: 'Structured'}, {evidence_id: 'a'}]}]}];
context.renderStreamingDraft('Summary\n\nDetails\nFallback');
assert.ok(draft.innerHTML.includes('<ul'));
assert.ok(draft.innerHTML.includes('Structured'));
assert.ok(!draft.innerHTML.includes('Fallback'));
console.log('Structured streaming draft checks passed');
