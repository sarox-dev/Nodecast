const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/atomic-view.js', 'utf8');
const start = source.indexOf('function renderCitationParts(');
const end = source.indexOf('function renderMemoryView(', start);
assert.ok(start >= 0 && end > start);
const context = {allResults:[{id:'abc123'}], escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const html = context.renderCitationParts([{text:'Before '},{evidence_id:'abc123'},{text:' after'}], '');
assert.ok(html.indexOf('Before ') < html.indexOf('data-evidence-id="abc123"'));
assert.ok(html.indexOf('data-evidence-id="abc123"') < html.indexOf(' after'));
assert.ok(!context.renderCitationParts([{evidence_id:'missing'}], '').includes('data-evidence-id'));
assert.ok(context.renderCitationParts(undefined, 'Text', ['abc123']).includes('data-evidence-id="abc123"'));
const item = {parts:[{text:'<unsafe>'},{evidence_id:'abc123'}]};
assert.ok(context.renderSynthesisBlock({type:'bullets', items:[item]}).includes('<ul'));
assert.ok(context.renderSynthesisBlock({type:'numbered', items:[item]}).includes('<ol'));
const table = context.renderSynthesisBlock({type:'table', columns:['<heading>', 'B'], rows:[[item, {missing:true}]]});
assert.ok(table.includes('&lt;heading>') && table.includes('&lt;unsafe>'));
assert.ok(table.includes('data-evidence-id="abc123"') && table.includes('Not found in saved sources'));
const markdown = context.memoryAnswerMarkdown({title:'Comparison', summary_parts:[{text:'Overview '},{evidence_id:'abc123'}], sections:[
    {title:'List', blocks:[{type:'bullets', items:[item]}]},
    {title:'Steps', blocks:[{type:'numbered', items:[{parts:[{text:'First'}]}]}]},
    {title:'Table', blocks:[{type:'table', columns:['App','Feature'], rows:[[{parts:[{text:'A|B'}]}, {missing:true}]]}]},
]});
assert.ok(markdown.includes('## Comparison') && markdown.includes('- <unsafe>') && markdown.includes('1. First'));
assert.ok(markdown.includes('| A\\|B | Not found in saved sources |'));
assert.ok(!markdown.includes('abc123') && !markdown.includes('data-evidence-id'));
console.log('Inline citation rendering checks passed');
