async (page) => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const items = await (await page.request.get('http://localhost:8000/api/v1/content/kanji?level=N5&locale=fr')).json();
  const day = items.find(item => item.character === '日');
  const school = items.find(item => item.character === '学');
  const open = async item => {
    await page.goto(`http://localhost:3000/study/kanji/${item.id}`);
    await page.getByRole('heading', {name: 'Ordre des traits', exact: true}).waitFor();
  };
  const count = () => page.locator('path[data-stroke][visibility="visible"]').count();
  await open(day);
  assert(await count() === 4, 'Initial diagram incomplete');
  assert(await page.locator('svg[role="img"] text').count() === 0, 'Numbers should start hidden');
  await page.getByLabel('Afficher les numéros').check();
  assert(await page.locator('svg[role="img"] text').count() === 4, 'Numbers toggle failed');
  await page.getByRole('button', {name: 'Recommencer le tracé', exact: true}).click();
  assert(await count() === 0, 'Reset did not clear ink');
  assert(await page.getByRole('button', {name: 'Trait précédent', exact: true}).isDisabled(), 'Previous enabled at start');
  await page.getByRole('button', {name: 'Trait suivant', exact: true}).click();
  assert(await count() === 1, 'Next failed');
  await page.getByRole('button', {name: 'Trait suivant', exact: true}).focus();
  await page.keyboard.press('Enter');
  assert(await count() === 2, 'Keyboard step failed');
  await page.getByRole('button', {name: 'Trait précédent', exact: true}).click();
  assert(await count() === 1, 'Previous failed');
  await page.getByRole('button', {name: 'Recommencer le tracé', exact: true}).click();
  await page.getByRole('button', {name: 'Animer', exact: true}).click();
  await page.waitForFunction(() => {
    const value = Number(document.querySelector('[data-stroke="1"]').getAttribute('stroke-dashoffset'));
    return value > 0 && value < .8;
  });
  assert(await count() === 1, 'Concurrent strokes');
  await page.getByRole('button', {name: 'Pause', exact: true}).click();
  const paused = await page.locator('[data-stroke="1"]').getAttribute('stroke-dashoffset');
  // Measure that the animation remains frozen, not merely that the label changed.
  await page.waitForTimeout(200);
  assert(await page.locator('[data-stroke="1"]').getAttribute('stroke-dashoffset') === paused, 'Pause still animates');
  await page.getByLabel('Vitesse du tracé').selectOption('1.5');
  await page.getByRole('button', {name: 'Reprendre', exact: true}).click();
  await page.getByRole('button', {name: 'Animer', exact: true}).waitFor();
  assert(await count() === 4, 'Animation incomplete');
  assert(await page.locator('path[data-stroke]').evaluateAll(paths => paths.every(p => p.getTotalLength() > 0 && Number(p.getAttribute('stroke-dashoffset')) === 0)), 'Incomplete or invalid geometry');
  await page.getByRole('button', {name: 'Animer', exact: true}).click();
  await page.getByRole('button', {name: 'Recommencer le tracé', exact: true}).click();
  await page.waitForTimeout(200);
  assert(await count() === 0, 'Reset left a running frame');
  await page.getByRole('button', {name: 'Animer', exact: true}).click();
  await open(school);
  assert(await count() === 8, 'Navigation retained previous animation');
  await page.getByLabel('Afficher les numéros').check();
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    assert(!await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), `Overflow at ${width}`);
    await page.screenshot({path: `output/playwright/strokes-final-${width}.png`});
  }
  await page.emulateMedia({reducedMotion: 'reduce'});
  await page.getByText(/Mouvements réduits/).waitFor();
  await page.getByRole('button', {name: 'Recommencer le tracé', exact: true}).click();
  await page.getByRole('button', {name: 'Animer', exact: true}).click();
  await page.waitForFunction(() => document.querySelectorAll('path[data-stroke][visibility="visible"]').length === 1);
  assert(await page.locator('path[data-stroke]').evaluateAll(paths => paths.every(p => [0, 1].includes(Number(p.getAttribute('stroke-dashoffset'))))), 'Reduced motion interpolates');
  await page.getByRole('button', {name: 'Pause', exact: true}).click();
  assert(await page.getByText('Trait 1 sur 8', {exact: true}).isVisible(), 'Reduced-motion counter wrong');
  await page.getByRole('button', {name: 'Trait précédent', exact: true}).click();
  assert(await count() === 0, 'Reduced-motion previous did not remove the last visible stroke');
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await page.route('**/kanji-strokes/n5/*.json', route => route.fulfill({status: 503, body: 'Unavailable'}));
  await page.reload();
  await page.getByText(/Le tracé est temporairement indisponible/).waitFor();
  assert(await page.getByRole('heading', {name: '学', exact: true}).isVisible(), 'Unavailable asset hid the entry');
  await page.unroute('**/kanji-strokes/n5/*.json');
  await page.getByRole('button', {name: 'Réessayer', exact: true}).click();
  await page.getByRole('heading', {name: 'Ordre des traits', exact: true}).waitFor();
  // Preserve and exercise the extension to other levels already present in the project.
  const n4 = await (await page.request.get('http://localhost:8000/api/v1/content/kanji?level=N4')).json();
  await open(n4[0]);
  assert(await count() > 0, 'Other-level regression');
  assert(errors.length === 0, errors.join('\n'));
  return {n5: items.length, dayId: day.id, schoolId: school.id, passed: ['static view', 'numbers', 'manual and keyboard steps', 'progressive drawing', 'pause/resume/speed', 'reset', 'navigation', '1440/768/390/320', 'reduced motion', 'error/retry', 'N4 regression', 'no runtime errors']};
}
