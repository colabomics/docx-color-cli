// Documentation-only browser screenshots, not a Word renderer or CLI feature.
// Dependencies: docx-preview 0.3.7 and playwright 1.56.1 (installed separately).
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const browser = await chromium.launch({
    ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {}),
    headless: true,
  });
  try {
    for (const [filename, label, subtitle, image] of [
      ['tracked.docx', 'Before · Tracked changes', 'Insertions underlined · deletions struck through', 'nature-before.png'],
      ['colored.docx', 'After · Accepted & colored', 'Inserted text in red · unchanged text in black', 'nature-after.png'],
    ]) {
      const page = await browser.newPage({ viewport: {width: 1000, height: 1400}, deviceScaleFactor: 1.5 });
      await page.route('**/*', route => route.abort()); // All document data stays local.
      await page.setContent(`<!doctype html><html><head><meta charset="utf-8"><style>
        * {box-sizing:border-box} body {margin:0;background:#edf0f3;color:#15202b}
        #capture {width:900px;margin:0 auto;padding:28px 32px 22px;background:#edf0f3}
        header {font-family:Arial,sans-serif;display:flex;justify-content:space-between;align-items:center;margin:0 0 20px}
        header strong {font-size:22px;letter-spacing:-.4px} header small {display:block;color:#536170;font-size:12px;margin-top:8px}
        .badge {font:11px Arial,sans-serif;letter-spacing:1px;color:#526373;border:1px solid #c4cdd5;border-radius:4px;padding:8px}
        .docx-wrapper {padding:0!important;background:transparent!important}
        .docx-wrapper>section.docx {margin:0!important;box-shadow:0 3px 15px #16253618!important}
        ins {color:#176636;text-decoration:underline;text-decoration-thickness:1px}
        del {color:#a12929;text-decoration:line-through}
        footer {font:11px Arial,sans-serif;color:#596777;margin-top:16px;display:flex;justify-content:space-between}
      </style></head><body><div id="capture"><header><div><strong>${label}</strong><small>${subtitle}</small></div><span class="badge">DOCX-COLOR-CLI</span></header><div id="doc"></div><footer><span>Synthetic manuscript · page 1</span><span>Browser preview · not Microsoft Word</span></footer></div></body></html>`);
      await page.addScriptTag({ path: require.resolve('jszip/dist/jszip.min.js') });
      await page.addScriptTag({ path: path.join(path.dirname(require.resolve('docx-preview')), 'docx-preview.min.js') });
      const data = fs.readFileSync(path.join(__dirname, filename)).toString('base64');
      await page.evaluate(async (data) => {
        const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
        await docx.renderAsync(bytes, document.getElementById('doc'), null, {
          renderChanges: true, renderHeaders: true, renderFooters: true,
          breakPages: true, ignoreLastRenderedPageBreak: true,
        });
        await document.fonts.ready;
      }, data);
      // Capture the real rendered first page only, without altering its content.
      const pages = page.locator('section.docx');
      const total = await pages.count();
      if (total < 2) throw new Error('Expected two manuscript pages');
      await pages.evaluateAll(nodes => nodes.slice(1).forEach(n => n.style.display = 'none'));
      const first = pages.first();
      const text = await first.innerText();
      if (!text.includes('Buffered signals') || !text.includes('Table 1')) throw new Error('Incomplete preview');
      if (filename === 'tracked.docx' && await first.locator('del').count() < 1) throw new Error('Missing revision rendering');
      if (filename === 'colored.docx' && await first.locator('ins, del').count()) throw new Error('Residual revisions in output');
      const overflow = await first.evaluate(n => n.scrollHeight > n.clientHeight + 2);
      if (overflow) throw new Error('First-page content overflows');
      await page.locator('#capture').screenshot({path: path.join(root, 'assets', image)});
      console.log(`${image}: ${total} document pages; first page captured`);
      await page.close();
    }
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
