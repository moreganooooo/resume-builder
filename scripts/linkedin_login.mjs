import { chromium } from 'playwright';

async function run() {
  let browser;
  try {
    browser = await chromium.launch({
      headless: false,
      args: ['--window-size=1000,800', '--no-sandbox']
    });

    const context = await browser.newContext({
      viewport: { width: 1000, height: 800 }
    });

    const page = await context.newPage();

    page.on('close', () => {
      // If cookie was already captured, we don't treat it as error
      process.exit(0);
    });

    await page.goto('https://www.linkedin.com/login');

    let liAtCookie = null;
    for (let i = 0; i < 180; i++) {
      try {
        const cookies = await context.cookies();
        const found = cookies.find(c => c.name === 'li_at');
        if (found) {
          liAtCookie = found.value;
          break;
        }
      } catch (err) {
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    if (liAtCookie) {
      console.log(JSON.stringify({ success: true, cookie: liAtCookie }));
    } else {
      console.log(JSON.stringify({ success: false, error: 'Authentication timeout' }));
    }
  } catch (err) {
    console.log(JSON.stringify({ success: false, error: err.message }));
  } finally {
    if (browser) {
      try {
        await browser.close();
      } catch (e) {
        // browser already closed or killed
      }
    }
  }
}

run();
