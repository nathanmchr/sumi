async (page) => {
  // Requires an authenticated, disposable QA account with the French interface.
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  const items = await (await page.request.get('http://localhost:8000/api/v1/content/vocabulary?level=N5&locale=fr')).json();
  const word = items.find(item => item.romaji && item.furigana_segments.some(segment => segment.reading));
  const detail = `http://localhost:3000/study/vocabulary/${word.id}`;
  const open = async () => {
    await page.goto(detail);
    await page.locator('.detail-card__translation').waitFor();
  };
  const configure = async enabled => {
    await page.goto('http://localhost:3000/settings');
    const toggle = page.getByRole('switch', {name: 'Afficher les romaji', exact: true});
    if (await toggle.isChecked() !== enabled) {
      await toggle.setChecked(enabled);
      await page.getByRole('button', {name: 'Enregistrer', exact: true}).click();
      await page.getByText('Paramètres enregistrés', {exact: true}).waitFor();
    }
    await page.reload();
    assert(await page.getByRole('switch', {name: 'Afficher les romaji', exact: true}).isChecked() === enabled, 'Preference not persisted');
  };
  await configure(false);
  await open();
  assert(await page.locator('.detail-card__reading').count() === 0, 'Kana reading still duplicated');
  const rubyCount = await page.locator('.detail-card ruby').count();
  assert(rubyCount > 0, 'Furigana missing');
  await configure(true);
  await open();
  assert(await page.locator('.detail-card__reading[lang="ja-Latn"]').textContent() === word.romaji, 'Wrong display romaji');
  assert(await page.locator('.detail-card ruby').count() === rubyCount, 'Furigana changed');
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    await page.screenshot({path: `output/playwright/vocabulary-romaji-${width}.png`});
    assert(await page.locator('.detail-card__reading').isVisible(), 'Romaji not visible');
  }
  await page.goto('http://localhost:3000/study/vocabulary');
  await page.getByRole('button').filter({has: page.getByRole('heading', {name: 'N5', exact: true})}).click();
  await page.locator('.content-card [lang="ja-Latn"]').first().waitFor();
  await page.route(`**/content/vocabulary/${word.id}?*`, async route => {
    const response = await route.fetch();
    await route.fulfill({response, json: {...await response.json(), romaji: ''}});
  });
  await open();
  assert(await page.locator('.detail-card__reading').count() === 0, 'Empty romaji left a redundant line');
  await page.unroute(`**/content/vocabulary/${word.id}?*`);
  await configure(false);
  await open();
  assert(await page.locator('.detail-card__reading').count() === 0, 'Romaji stayed visible when disabled');
  assert(await page.locator('.detail-card ruby').count() === rubyCount, 'Furigana removed with romaji');
  return {word: word.japanese, romaji: word.romaji, passed: ['default hidden', 'furigana retained', 'settings persistence', 'catalog', 'mobile and desktop', 'missing romaji', 'disable']};
}
