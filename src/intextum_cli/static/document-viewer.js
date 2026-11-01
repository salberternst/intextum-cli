const params = new URLSearchParams(location.search);
const query = new URLSearchParams({ file: params.get('file') || '', group: params.get('group') || '', key: params.get('key') || '' });
const content = document.querySelector('#content');
const status = document.querySelector('#status');
const error = document.querySelector('#error');
const MODES = ['content', 'elements', 'images'];
// Embedded in the review page, which owns the mode buttons.
if (params.get('embedded')) document.body.classList.add('embedded');
let mode = MODES.includes(params.get('mode')) ? params.get('mode') : 'content';
let selected = [];
let ready = false;
let table;
let images;
let unlocated;
let unlocatedItems = [];
let componentWarning = '';

function showMode(next) {
  mode = next;
  for (const name of ['content', 'elements', 'images']) {
    document.getElementById(name).hidden = name !== mode;
    document.querySelector(`[data-mode="${name}"]`).setAttribute('aria-pressed', String(name === mode));
  }
  applySelection();
}

function applySelection() {
  document.querySelector('#reset').hidden = selected.length === 0;
  if (!ready) return;
  table?.setAttribute('items', selected.join(', '));
  if (unlocated) unlocated.items = unlocatedItems.filter(item => !selected.length || selected.includes(item.self_ref));
  if (images) {
    images.setAttribute('items', selected.join(', '));
    images.toggleAttribute('backdrop', selected.length > 0);
  }
  const doc = content.contentDocument;
  if (doc) {
    doc.querySelectorAll('.evidence-selected').forEach(node => node.classList.remove('evidence-selected'));
    let first;
    for (const ref of selected) {
      const node = doc.querySelector(`[data-doc-ref="${CSS.escape(ref)}"]`);
      if (node) { node.classList.add('evidence-selected'); first ||= node; }
    }
    first?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    if (selected.length && mode === 'content' && !first) {
      status.textContent = 'This element is available in the Elements view.';
    } else {
      status.textContent = componentWarning || (selected.length ? 'Source element selected' : '');
    }
  }
}

function readSelection() {
  try {
    const value = JSON.parse(decodeURIComponent(location.hash.slice(1) || '%5B%5D'));
    selected = Array.isArray(value) ? value.filter(ref => typeof ref === 'string' && /^#\/[a-z_]+\/\d+$/.test(ref)) : [];
  } catch { selected = []; }
  applySelection();
}

// Review shortcuts belong to the surrounding page; pass them on when the
// viewer has focus. The sandboxed content frame runs no listeners, so focus
// inside the rendered text still keeps them.
const SHORTCUTS = ['Enter', 'ArrowUp', 'ArrowDown'];
function forwardShortcuts(target) {
  target.addEventListener('keydown', event => {
    if (!event.altKey || !SHORTCUTS.includes(event.key) || window.parent === window) return;
    event.preventDefault();
    for (const type of ['keydown', 'keyup']) {
      // NiceGUI only accepts events from the page's own KeyboardEvent class.
      window.parent.document.dispatchEvent(new window.parent.KeyboardEvent(type, { key: event.key, code: event.code, altKey: true, bubbles: true }));
    }
  });
}
forwardShortcuts(document);

window.addEventListener('message', event => {
  if (event.origin !== location.origin || event.source !== window.parent) return;
  const next = event.data?.intextumMode;
  if (MODES.includes(next)) showMode(next);
});

document.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => showMode(button.dataset.mode)));
document.querySelector('#reset').addEventListener('click', () => { location.hash = ''; });
window.addEventListener('hashchange', readSelection);
content.addEventListener('load', applySelection);
readSelection();
showMode(mode);

try {
  const response = await fetch(`/api/document/json?${query}`);
  if (!response.ok) throw new Error('The cached document is unavailable. Rebuild the document view.');
  const doc = await response.json();
  ready = true;
  content.src = `/api/document/html?${query}`;
  try {
    await import('/vendor/docling-components.js');
  } catch {
    document.querySelector('[data-mode="elements"]').disabled = true;
    componentWarning = 'Element components unavailable; showing document content.';
    status.textContent = componentWarning;
  }
  if (window.intextumDocling) {
    unlocatedItems = Array.from(window.intextumDocling.iterateDocumentItems(doc, { traversePictures: true }))
      .map(([item, level]) => ({ ...item, level })).filter(item => !item.prov?.length);
    table = document.createElement('docling-table');
    table.src = doc;
    // Content-only columns also work for Office/text inputs without page pixels.
    const column = document.createElement('docling-column');
    for (const tag of ['docling-item-text', 'docling-item-table']) column.append(document.createElement(tag));
    table.append(column);
    document.querySelector('#elements').append(table);
    // The package's table groups by physical provenance pages. Unpaginated
    // inputs use its public TablePage component directly, without fabricated
    // source pages or coordinates.
    if (unlocatedItems.length) {
      const container = document.createElement('table');
      container.className = 'component-table';
      unlocated = document.createElement('docling-table-page');
      // Item components require a rendering context even without provenance.
      // This context has neither an invented source page number nor a size.
      unlocated.page = {};
      unlocated.items = unlocatedItems;
      unlocated.columns = [column];
      container.append(unlocated);
      document.querySelector('#elements').append(container);
    }
    if (Object.values(doc.pages || {}).some(page => page.image?.uri)) {
      images = document.createElement('docling-img');
      images.src = doc;
      images.setAttribute('pagenumbers', '');
      images.append(document.createElement('docling-tooltip'));
      document.querySelector('#images').append(images);
      document.querySelector('[data-mode="images"]').hidden = false;
    }
  }
  status.textContent = componentWarning;
  applySelection();
} catch (exception) {
  error.textContent = exception.message;
  error.hidden = false;
  content.hidden = true;
  status.textContent = '';
}
