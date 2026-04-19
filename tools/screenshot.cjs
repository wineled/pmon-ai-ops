const puppeteer = require('puppeteer-core');
const path = require('path');

const delay = ms => new Promise(res => setTimeout(res, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
      '--no-proxy-server',
      '--proxy-server=direct://',
      '--ignore-certificate-errors'
    ]
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  // Block external fonts
  await page.setRequestInterception(true);
  page.on('request', req => {
    const url = req.url();
    if (url.includes('fonts.googleapis.com') || url.includes('fonts.gstatic.com')) {
      req.abort();
    } else {
      req.continue();
    }
  });

  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });

  try {
    // Test HTTPS external domain
    await page.goto('https://22mj4798in35.vicp.fun', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await delay(4000);

    const screenshotPath = path.join('F:\\CodingProjects\\电源监控日志实时分析系统', 'screenshot-https.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log('SUCCESS:', screenshotPath);
    if (errors.length > 0) {
      console.log('Console errors:', errors.slice(0, 5).join('\n'));
    }
  } catch (err) {
    console.error('Error:', err.message);
    try {
      const screenshotPath = path.join('F:\\CodingProjects\\电源监控日志实时分析系统', 'screenshot-error.png');
      await page.screenshot({ path: screenshotPath, fullPage: true });
      console.log('Fallback:', screenshotPath);
    } catch (e) {}
  }

  await browser.close();
})();
