const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const script = fs.readFileSync('app/static/js/atomic-view.js', 'utf8');
const from = script.indexOf('function groupEvidenceBySource(');
const to = script.indexOf('function renderSourceGroups(', from);
assert.ok(from >= 0 && to > from);
const scope = {};
vm.createContext(scope);
vm.runInContext(script.slice(from, to), scope);
const groups = scope.groupEvidenceBySource([
  {id:'a', source_id:'one', source_title:'One', excerpt:'Same text', excerpt_hash:'same'},
  {id:'b', source_id:'one', source_title:'One', excerpt:'Same text', excerpt_hash:'same'},
  {id:'c', source_id:'one', source_title:'One', excerpt:'Different', excerpt_hash:'different'},
  {id:'d', source_id:'two', source_title:'Two', excerpt:'Same text', excerpt_hash:'same'},
  {id:'e', source_id:'one', source_title:'One', excerpt:'Same text', excerpt_hash:'different-full-content'},
]);
assert.equal(groups.length, 2);
assert.equal(groups[0].fragments.length, 3);
assert.deepEqual(Array.from(groups[0].fragments[0].ids), ['a','b']);
assert.deepEqual(Array.from(groups[1].fragments[0].ids), ['d']);
console.log('Source grouping and evidence identity checks passed');
