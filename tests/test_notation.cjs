"use strict";
const assert = require('node:assert/strict');
require('../web/notation.js');
const n = globalThis.MeasurementNotation;
for (const [text, base, index] of [['Ci','C','i'],['εi','ε','i'],['ti','t','i'],['VGS','V','GS'],['VDS','V','DS'],['IDS','I','DS'],['Vth','V','th'],['μsat','μ','sat'],['Eg','E','g']]) {
  assert.ok(n.html(text).includes('<var>'+base+'</var><sub>'+index+'</sub>'));
  assert.ok(n.svg(text).includes('baseline-shift="sub"'));
}
assert.ok(n.html('(αhν)½').includes('<sup>1/2</sup>'));
assert.ok(n.svg('(αhν)²').includes('baseline-shift="super"'));
for (const text of ['a-Si','a-IGZO','μm','nF','eV','MOBILITY','aIGZO_W20_L04_Mobility.csv','mu_sat_cm2_Vs']) assert.equal(n.html(text),text);
assert.equal(n.html('<img src=x onerror=alert(1)>'),'&lt;img src=x onerror=alert(1)&gt;');
assert.equal(n.svg('<script>'), '&lt;script&gt;');
console.log('NOTATION_CHECK_OK: indices, powers, Greek nu, chemical/unit/identifier preservation, escaping');
