#!/usr/bin/env node
// SVG -> PNG с прозрачным фоном через Chromium (Playwright).
// node content/tools/svg2png.js jobs.json   где jobs.json = [{"svg": "path.svg", "png": "path.png"}, ...]
// Один запуск браузера на все файлы. Размер PNG берётся из width/height SVG.
const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  for (const job of jobs) {
    const svg = fs.readFileSync(job.svg, 'utf8');
    const w = Number(/width="(\d+)"/.exec(svg)[1]);
    const h = Number(/height="(\d+)"/.exec(svg)[1]);
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(
      `<html><body style="margin:0;background:transparent">${svg}</body></html>`,
      { waitUntil: 'load' });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: job.png, omitBackground: true, clip: { x: 0, y: 0, width: w, height: h } });
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
