// Run with a Playwright page against the existing dev server. No user data is written.
async (page) => {
  const check = (value, message) => { if (!value) throw new Error(message); };
  await page.route('**/api/v1/auth/session', route => route.fulfill({ json: {
    user: { id: 'controls-preview', email: 'preview@example.invalid', full_name: 'Preview', is_admin: false },
    settings: { user_id: 'controls-preview', interface_locale: 'fr', content_locale: 'fr', furigana_display_mode: 'always', romaji_enabled: false, furigana_helper_enabled: false }
  } }));
  await page.route('**/api/v1/lessons/controls-preview**', route => route.fulfill({ json: {
    lesson: { id: 'controls-preview', title: 'Kanji', completed_steps: 1, total_steps: 3 },
    revision: 1, cursor: 1, viewing: 1, correct: 0, answered: 0, feedback: null, next_lesson_id: null,
    step: { id: 'kanji-preview', kind: 'kanji', title: 'Kanji', character: '男', meaning: 'homme', onyomi: ['ダン'], kunyomi: ['おとこ'], lines: [] }
  } }));
  await page.goto('http://localhost:3000/study/lessons/controls-preview');
  const player = page.getByRole('region', { name: 'Ordre des traits' });
  const controls = player.locator('[data-kanji-controls]');
  const play = controls.locator('button.play');
  const slider = controls.getByRole('slider');
  await slider.waitFor();
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    const button = await play.boundingBox();
    const speed = await slider.locator('..').boundingBox();
    const canvas = await player.locator('svg[role=img]').boundingBox();
    check(speed.x >= button.x + button.width + 12, 'Speed must sit to the right of play');
    check(Math.abs(speed.y - button.y) < 2, 'Primary controls must align');
    check(button.y - canvas.y - canvas.height >= 20, 'Drawing needs breathing room');
    check(await slider.evaluate(el => getComputedStyle(el).webkitAppearance === 'none'), 'Native slider appearance leaked');
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile overflow');
    const icons = await controls.locator('.tool svg').evaluateAll(nodes => nodes.every(el =>
      el.getAttribute('fill') === 'none' && el.getAttribute('stroke') === 'currentColor' && getComputedStyle(el).fill === 'none'));
    check(icons, 'Secondary icons must remain outlined');
  }
  await slider.focus();
  await page.keyboard.press('End');
  check(await slider.inputValue() === '1.5', 'Maximum speed');
  await page.keyboard.press('Home');
  check(await slider.inputValue() === '0.5', 'Minimum speed');
  await play.click();
  check(await play.getAttribute('aria-pressed') === 'true', 'Play');
  await play.click();
  check(await play.getAttribute('aria-pressed') === 'false', 'Pause');
  await controls.getByRole('button', { name: 'Recommencer le tracé' }).click();
  check(await player.locator('path[data-stroke][visibility=visible]').count() === 0, 'Reset');
  await controls.getByRole('button', { name: 'Trait suivant' }).click();
  check(await player.locator('path[data-stroke][visibility=visible]').count() === 1, 'Next stroke');
  await controls.getByRole('button', { name: 'Trait précédent' }).click();
  check(await player.locator('path[data-stroke][visibility=visible]').count() === 0, 'Previous stroke');
  await controls.getByRole('button', { name: 'Afficher les numéros' }).click();
  check(await player.locator('svg text').count() > 0, 'Stroke numbers');
};
