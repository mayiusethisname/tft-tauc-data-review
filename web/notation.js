(function (root) {
  "use strict";
  const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const indexed = {Ci:["C","i"], εi:["ε","i"], ti:["t","i"], VGS:["V","GS"], VDS:["V","DS"], IDS:["I","DS"], VD:["V","D"], ID:["I","D"], Vth:["V","th"], μsat:["μ","sat"], Eg:["E","g"]};
  const variables = new Set(["W","L","E","α","λ","μ","hν"]);
  const keys = [...Object.keys(indexed), ...variables, "R²", "cm²", "(αhν)½", "(αhν)²", "(eV/cm)½", "(eV/cm)²"].sort((a,b) => b.length-a.length);
  const pattern = new RegExp(keys.map(s => s.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")).join("|"), "g");
  function render(value, svg = false) {
    const text = String(value), part = (s, type) => svg
      ? type === "var" ? '<tspan font-style="italic" font-family="serif">'+escape(s)+'</tspan>' : '<tspan font-style="normal" baseline-shift="'+(type === "sub" ? "sub" : "super")+'" font-size="75%">'+escape(s)+'</tspan>'
      : '<'+type+'>'+escape(s)+'</'+type+'>';
    let result = "", end = 0;
    for (const match of text.matchAll(pattern)) {
      const token = match[0], index = match.index;
      if (/[A-Za-z0-9_]/.test(text[index-1] || "") || /[A-Za-z0-9_]/.test(text[index+token.length] || "")) continue;
      result += escape(text.slice(end,index));
      let formatted;
      if (indexed[token]) formatted = part(indexed[token][0],"var")+part(indexed[token][1],"sub");
      else if (variables.has(token)) formatted = part(token,"var");
      else if (token === "R²") formatted = part("R","var")+part("2","sup");
      else if (token === "cm²") formatted = "cm"+part("2","sup");
      else {
        const power = token.endsWith("½") ? "1/2" : "2";
        formatted = token.startsWith("(α") ? "("+part("αhν","var")+")"+part(power,"sup") : "(eV/cm)"+part(power,"sup");
      }
      result += svg ? formatted : '<span class="math-symbol">'+formatted+'</span>';
      end = index + token.length;
    }
    return result + escape(text.slice(end));
  }
  function enhance(container) {
    if (!container) return;
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT), nodes = [];
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.parentElement.closest('svg,script,style,code,pre,textarea,input,var,sub,sup,[data-math],.help-trigger,.source-detail') || !node.textContent.trim()) continue;
      nodes.push(node);
    }
    for (const node of nodes) {
      const html = render(node.textContent);
      if (html === escape(node.textContent)) continue;
      const span = document.createElement("span");
      span.dataset.math = ""; span.innerHTML = html; node.replaceWith(span);
    }
  }
  root.MeasurementNotation = {html:value => render(value), svg:value => render(value,true), enhance};
})(typeof window !== "undefined" ? window : globalThis);
