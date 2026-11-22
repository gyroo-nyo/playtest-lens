// Render every frame (60 fps) + the soundtrack, then: ffmpeg → lens-ident.mp4.  node export.mjs [gif]
import puppeteer from 'puppeteer';
import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
const GIF = process.argv[2] === 'gif', FPS = GIF ? 20 : 60, OUT = GIF ? 'frames-gif' : 'frames';
await mkdir(OUT, { recursive: true });
const browser = await puppeteer.launch({ headless: 'new', args: ['--use-gl=angle', '--ignore-gpu-blocklist'] });
const page = await browser.newPage();
page.on('pageerror', e => console.log('PAGEERROR', e.message));
await page.setViewport({ width: 1920, height: 1080 });
await page.goto(pathToFileURL('index.html').href + '?clean=1' + (GIF ? '&gif=1' : ''), { waitUntil: 'networkidle0' });
await page.waitForFunction('window.OPENER && window.OPENER.ready', { timeout: 60000 });
const D = await page.evaluate(() => window.OPENER.DURATION), n = Math.round(D * FPS);
if (!GIF) await writeFile('audio.wav', Buffer.from(await page.evaluate(() => window.OPENER.wav()), 'base64'));
for (let i = 0; i < n; i++) {
  await page.evaluate(t => window.OPENER.seek(t), i / FPS);
  await page.screenshot({ path: `${OUT}/f${String(i).padStart(5, '0')}.png`, clip: { x: 0, y: 0, width: 1920, height: 1080 } });
  if (i % FPS === 0) process.stdout.write(`\r${i}/${n}`);
}
console.log(`\n${n} frames in ${OUT}/`);
await browser.close();
