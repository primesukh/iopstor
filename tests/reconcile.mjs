/* The shared document, exercised against the real Yjs. Run by pytest (test_two_people_in_one
   _paragraph_keep_both_sets_of_words) and standalone with `node tests/reconcile.mjs`.

   It loads the editor's OWN code -- the "shared document" section is cut straight out of
   static/admin.js -- so this cannot drift into testing a copy. The stubs are the smallest set that
   lets that section move: MODEL, and the three canvas calls it dispatches to. */
import * as Yns from '../iopstor/static/vendor/yjs.mjs'
import { QuillBinding } from '../iopstor/static/vendor/y-quill.mjs'
import fs from 'node:fs'
import path from 'node:path'
import url from 'node:url'
import vm from 'node:vm'

const here = path.dirname(url.fileURLToPath(import.meta.url))
const js = fs.readFileSync(path.join(here, '..', 'iopstor', 'static', 'admin.js'), 'utf8')
const from = js.indexOf('  /* ---- the shared document ---')
const to = js.indexOf('  function seedFor(type) {')
if (from < 0 || to < 0) { console.log('FAIL  cannot find the shared-document section in admin.js'); process.exit(1) }

let MODEL = [], repaints = 0, sections = []
const ctx = vm.createContext({
  window: { crypto: 1, IOPY: { Y: Yns, QuillBinding } },
  // no rt.url == no channel == single player, so initShared seeds immediately rather than waiting
  // for a roster that will never arrive. The deferred path gets its own case at the bottom.
  SPEC: { rt: {} },
  crypto: { randomUUID: () => 'id-' + Math.random().toString(36).slice(2, 12) },
  console, setTimeout, clearTimeout,
  atob: s => Buffer.from(s, 'base64').toString('binary'),
  btoa: s => Buffer.from(s, 'binary').toString('base64'),
  say: () => {},
  get MODEL () { return MODEL }, set MODEL (v) { MODEL = v },
  cdoc: () => null,                       // no canvas in here, so focus-wins never holds anything back
  canvasFull: () => { repaints += 1 },
  canvasBlock: p => { sections.push(p) },
  blockAt: p => {
    let list = MODEL, q = String(p).split('.')
    while (q.length > 1) list = list[+q.shift()].data.cols[+q.shift()]
    return list[+q[0]]
  }
})
vm.runInContext(js.slice(from, to) + `
this.API = { stampIds, reconcileOut, initShared, pathOfId, idOf, eachBlock, yState, SCALARS,
             seedDoc, dedupe, fromY, shareQuill, shareWaiting,
             set canWrite (v) { canWrite = v },
             set shareOut (v) { shareOut = v },
             get BINDS () { return BINDS }, get WAITING () { return WAITING },
             get YB () { return YB }, get YDOC () { return YDOC } };`, ctx)
const API = ctx.API
;['url', 'media_id', 'align', 'tone', '_id', '_rich', 'widths', 'fx'].forEach(k => { API.SCALARS[k] = 1 })

let bad = 0
const ok = (label, cond) => { if (!cond) bad += 1; console.log((cond ? 'PASS  ' : 'FAIL  ') + label) }
const settle = () => new Promise(r => setTimeout(r, 250))     // reconcileOut debounces at 120ms

MODEL = [{ type: 'hero', data: { heading: 'IOPSTOR', align: 'center' } },
         { type: 'rich_text', data: { html: '<p>Hi</p>', _rich: true } },
         { type: 'columns', data: { cols: [[{ type: 'rich_text', data: { html: '<p>Inside</p>', _rich: true } }], []] } }]
API.initShared('')

const names = []
API.eachBlock(MODEL, b => names.push(API.idOf(b)))
ok('every section, nested ones included, is named', names.length === 4 && names.every(Boolean))
ok('a setting stays a plain value', typeof API.YB.get(0).get('data').get('align') === 'string')
ok('a heading becomes a shared text type', API.YB.get(0).get('data').get('heading') instanceof Yns.Text)
ok('a rich block\'s html is left to y-quill', API.YB.get(1).get('data').get('html') === undefined)

/* THE ACCEPTANCE TEST FOR THE WHOLE PROGRAMME. Two people type into one field at the same moment,
   neither having seen the other, and both sets of words are there afterwards -- which is the thing
   a string in a map cannot do however it is transported. */
const mine = API.YB.get(0).get('data').get('heading')
const peer = new Yns.Doc()
Yns.applyUpdate(peer, Yns.encodeStateAsUpdate(API.YDOC))
const theirs = peer.getArray('blocks').get(0).get('data').get('heading')
mine.insert(7, ' storage')
theirs.insert(0, 'The ')
const a = Yns.encodeStateAsUpdate(API.YDOC), b = Yns.encodeStateAsUpdate(peer)
Yns.applyUpdate(API.YDOC, b, 'remote'); Yns.applyUpdate(peer, a)
ok('two people in one paragraph keep both sets of words: ' + JSON.stringify(mine.toString()),
   mine.toString() === theirs.toString() && mine.toString() === 'The IOPSTOR storage')

/* A newcomer who loads a stale state and then hears the next delta holds that delta as PENDING,
   because its base is missing, and those words never appear. This is why the writer re-sends the
   whole state whenever somebody joins rather than trusting what the server had. */
const late = new Yns.Doc()
Yns.applyUpdate(late, Yns.diffUpdate(Yns.encodeStateAsUpdate(API.YDOC), Yns.encodeStateVector(peer)))
ok('a bare delta with no base renders nothing -- hence the state broadcast on join',
   late.getArray('blocks').length === 0)

repaints = 0; sections = []
const p1 = new Yns.Doc(); Yns.applyUpdate(p1, Yns.encodeStateAsUpdate(API.YDOC))
p1.getArray('blocks').get(0).get('data').set('align', 'left')
Yns.applyUpdate(API.YDOC, Yns.encodeStateAsUpdate(p1), 'remote')
ok('a peer changing a setting repaints one section, not the page', repaints === 0 && sections.length === 1)
ok('...and it reaches MODEL', MODEL[0].data.align === 'left')

repaints = 0
const p2 = new Yns.Doc(); Yns.applyUpdate(p2, Yns.encodeStateAsUpdate(API.YDOC))
const m = new Yns.Map(); p2.getArray('blocks').insert(1, [m])
m.set('type', 'divider'); m.set('data', new Yns.Map()); m.get('data').set('_id', 'from-a-peer')
Yns.applyUpdate(API.YDOC, Yns.encodeStateAsUpdate(p2), 'remote')
ok('a peer adding a section lands it in the right place', repaints === 1 && MODEL[1].type === 'divider')

repaints = 0; sections = []
MODEL[0].data.align = 'right'
API.reconcileOut(); await settle()
ok('our own write does not echo back as somebody else\'s', repaints === 0 && sections.length === 0)
ok('...and it reaches the document', API.YB.get(0).get('data').get('align') === 'right')

/* The reason the draft is stored unpruned: prune() drops an empty paragraph, and with it the name
   that says which section a remote edit belongs to. */
MODEL.push({ type: 'rich_text', data: { html: '', _rich: true } })
API.stampIds(MODEL)
const openParagraph = API.idOf(MODEL[MODEL.length - 1])
API.reconcileOut(); await settle()
MODEL.splice(MODEL.length - 1, 0, { type: 'divider', data: {} })
API.stampIds(MODEL); API.reconcileOut(); await settle()
ok('a section added above an empty paragraph does not steal its name',
   API.pathOfId(openParagraph) === String(MODEL.length - 1))

MODEL.splice(1, 1); API.reconcileOut(); await settle()
ok('a delete reaches the document',
   API.YB.toJSON().map(x => x.data._id).join() === MODEL.map(API.idOf).join())
MODEL.splice(0, 0, MODEL.splice(2, 1)[0]); API.reconcileOut(); await settle()
ok('a move reaches the document in the right order',
   API.YB.toJSON().map(x => x.data._id).join() === MODEL.map(API.idOf).join())

const restored = new Yns.Doc()
Yns.applyUpdate(restored, Buffer.from(API.yState(), 'base64'))
ok('the stored state restores the same document',
   JSON.stringify(restored.getArray('blocks').toJSON()) === JSON.stringify(API.YB.toJSON()))

/* Two browsers that each seed a document from the same blocks give Yjs two independent histories,
   and merging them shows every section twice -- which is what a page with no stored state does on
   every single load. Seeding waits for the roster; this is the repair for the instant where both
   see an empty one. */
const twinA = new Yns.Doc(), twinB = new Yns.Doc()
const shared = [{ type: 'rich_text', data: { _id: 'same-name', _rich: true, html: '<p>One</p>' } }]
for (const [doc, mark] of [[twinA, 'A'], [twinB, 'B']]) {
  const bm = new Yns.Map(); doc.getArray('blocks').insert(0, [bm])
  bm.set('type', shared[0].type)
  bm.set('data', new Yns.Map())
  bm.get('data').set('_id', 'same-name'); bm.get('data').set('_rich', true); bm.get('data').set('seededBy', mark)
}
Yns.applyUpdate(twinA, Yns.encodeStateAsUpdate(twinB))
ok('two independent seeds really do duplicate -- this is the fault, not a theory',
   twinA.getArray('blocks').length === 2)

MODEL = []
API.initShared(Buffer.from(Yns.encodeStateAsUpdate(twinA)).toString('base64'))
ok('...and a document that loads one is repaired to one section per name',
   (API.dedupe(), API.YB.length === 1 && API.YB.get(0).get('data').get('_id') === 'same-name'))

/* seedDoc is called from the roster, from a timeout and from the single-player path, so it has to
   be safe to call at any of them more than once. */
const before = API.YB.length
API.seedDoc(); API.seedDoc()
ok('seeding a document that already has one does nothing', API.YB.length === before)

/* ---- when the editor actually binds to the shared text -------------------------------------
   The smallest Quill that QuillBinding will accept. Not a mock of Quill's behaviour -- the BINDING
   is real, and so is the Y.Text; this only has to hold a delta and emit editor-change the way Quill
   does, because the fault being tested is about WHEN binding happens, not what it does. */
function fakeQuill (text) {
  const listeners = []
  const q = {
    ops: text ? [{ insert: text }] : [],
    root: { isConnected: true },
    getModule: () => null,
    getSelection: () => null,
    getContents () { return { ops: this.ops.slice() } },
    setContents (delta) { this.ops = (delta.ops || delta).slice(); return delta },
    updateContents (delta) {                       // honour the retain, or an insert at 0 lands at the end
      let text = this.ops[0]?.insert || '', at = 0
      for (const op of (delta.ops || delta)) {
        if (op.retain !== undefined) at += op.retain
        else if (op.insert !== undefined) { text = text.slice(0, at) + op.insert + text.slice(at); at += op.insert.length }
        else if (op.delete !== undefined) text = text.slice(0, at) + text.slice(at + op.delete)
      }
      this.ops = text ? [{ insert: text }] : []
      return delta
    },
    on (ev, fn) { listeners.push([ev, fn]) },
    off (ev, fn) { const i = listeners.findIndex(l => l[1] === fn); if (i > -1) listeners.splice(i, 1) },
    // somebody typing: what Quill emits, with source "user"
    type (more) {
      const at = this.ops[0]?.insert?.length || 0
      this.ops = [{ insert: (this.ops[0]?.insert || '') + more }]
      const delta = { ops: at ? [{ retain: at }, { insert: more }] : [{ insert: more }] }
      listeners.filter(l => l[0] === 'editor-change').forEach(l => l[1]('text-change', delta, null, 'user'))
    }
  }
  return q
}

MODEL = [{ type: 'rich_text', data: { _id: 'para', _rich: true, html: '<p>Hello</p>' } }]
API.canWrite = () => false          // exactly the state of the page's FIRST paint: no channel yet
API.initShared('')
API.seedDoc()
const editor = fakeQuill('Hello')
API.shareQuill({ getAttribute: () => '0' }, null, editor, 'html')
ok('an editor mounted before there is a channel is queued, not abandoned',
   API.WAITING.length === 1 && API.BINDS.length === 0)

editor.type(' world')               // typed during the gap, with nothing listening
API.canWrite = () => true           // the channel subscribes and this browser is elected
API.shareWaiting()
ok('...and binds once the answer is knowable', API.WAITING.length === 0 && API.BINDS.length === 1)

const para = API.YB.get(0).get('data').get('html')
ok('...keeping what was typed while it waited: ' + JSON.stringify(para.toString()),
   para instanceof Yns.Text && para.toString() === 'Hello world')

editor.type('!')
ok('typing now reaches the shared document', para.toString() === 'Hello world!')

const far = new Yns.Doc()
Yns.applyUpdate(far, Yns.encodeStateAsUpdate(API.YDOC))
far.getArray('blocks').get(0).get('data').get('html').insert(0, 'Oh, ')
Yns.applyUpdate(API.YDOC, Yns.encodeStateAsUpdate(far), 'remote')
ok('and a peer\'s words reach this editor: ' + JSON.stringify(editor.ops[0]?.insert || ''),
   (editor.ops[0]?.insert || '').startsWith('Oh, '))

/* canvasBlock() replaces one section's node without going through wireDoc(), so its old binding is
   left feeding an editor whose DOM is gone -- and that editor writes the delta back. */
editor.root.isConnected = false
API.shareQuill({ getAttribute: () => '0' }, null, fakeQuill(para.toString()), 'html')
ok('a replaced section does not leave a second binding on the same text', API.BINDS.length === 1)

/* ---- the document actually reaches the wire ------------------------------------------------
   The check that would have caught the worst of these: initShared grew early exits above the line
   that hooks up `update`, so a page WITH a stored state -- every page after its first save -- never
   broadcast a keystroke. Nothing threw. Asserted behaviourally, on the exact path that broke:
   a document restored from stored state, then edited. */
const sent = []
MODEL = [{ type: 'rich_text', data: { _id: 'wire', _rich: true, html: '<p>x</p>' } }]
API.initShared('')
API.seedDoc()
const savedState = API.yState()

MODEL = [{ type: 'rich_text', data: { _id: 'wire', _rich: true, html: '<p>x</p>' } }]
API.initShared(savedState)                 // the path that was silent
API.shareOut = (delta, origin) => sent.push(origin)
ok('a document restored from stored state still has its sections', API.YB.length === 1)

API.YB.get(0).get('data').set('align', 'center')
ok('...and a local edit reaches the wire', sent.length === 1)

sent.length = 0
Yns.applyUpdate(API.YDOC, Yns.encodeStateAsUpdate(new Yns.Doc()), 'remote')
API.YB.get(0).get('data').set('tone', 'dark')
ok('...while what a peer sent is not echoed back to them',
   sent.filter(o => o === 'remote').length === 0 && sent.length === 1)

console.log(bad ? bad + ' FAILED' : 'all passed')
process.exit(bad ? 1 : 0)
