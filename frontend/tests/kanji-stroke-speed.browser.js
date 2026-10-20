async (page) => {
  const assert = (ok, message) => { if (!ok) throw new Error(message); };
  // Run with an authenticated QA session using the English interface.
  await page.goto('http://localhost:3000/study/kanji/90e8e4e4-757b-46b6-9824-7b5babcac638');
  const speed = page.getByLabel('Drawing speed');
  await speed.waitFor();
  assert(await speed.inputValue() === '1', 'Default speed must be 1x');
  const dimensions = [];
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({width, height: 1000});
    // Isolate the control from an unrelated min-content overflow in English linked words.
    await page.getByRole('region', {name: 'Stroke order', exact: true}).evaluate((el, width) => {
      el.style.maxWidth = `${Math.min(310, width - 72)}px`;
    }, width);
    const control = await speed.evaluate(el => ({
      height: el.getBoundingClientRect().height,
      appearance: getComputedStyle(el).appearance,
      chevron: !!el.parentElement.querySelector('svg[aria-hidden="true"]'),
      overflow: el.parentElement.parentElement.scrollWidth > el.parentElement.parentElement.clientWidth,
    }));
    assert(control.height === 44 && control.appearance === 'none' && control.chevron, 'Incorrect select styling');
    assert(!control.overflow, `Overflow at ${width}px`);
    dimensions.push({width, ...control});
  }
  await speed.focus();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Shift+Tab');
  assert(await speed.evaluate(el => el.matches(':focus-visible') && getComputedStyle(el).outlineStyle === 'solid'), 'Missing keyboard focus');
  await page.screenshot({path: 'output/playwright/strokes-speed-mobile.png'});
  await page.setViewportSize({width: 1440, height: 1000});
  await page.getByRole('region', {name: 'Stroke order', exact: true}).evaluate(el => el.style.removeProperty('max-width'));
  await page.screenshot({path: 'output/playwright/strokes-speed-desktop.png'});

  // Advance browser frames deterministically instead of timing wall-clock clicks.
  await page.clock.install();
  const rates = [];
  for (const multiplier of [0.5, 1, 1.5]) {
    await page.getByRole('button', {name: 'Reset drawing', exact: true}).click();
    await speed.selectOption(String(multiplier));
    await page.getByRole('button', {name: 'Animate', exact: true}).click();
    await page.clock.runFor(1000);
    const progress = await page.locator('path[data-stroke][visibility="visible"]').evaluateAll(paths => {
      const last = paths.at(-1);
      return Number(last.dataset.stroke) - 1 + (1 - Number(last.getAttribute('stroke-dashoffset'))) * 0.82;
    });
    const expected = multiplier * 1.5;
    assert(Math.abs(progress - expected) < 0.08, `Wrong cadence at ${multiplier}x: ${progress}, expected ${expected}`);
    rates.push({multiplier, progressAfterOneSecond: progress, expected});
  }
  await page.getByRole('button', {name: 'Reset drawing', exact: true}).click();
  await page.clock.resume();
  return {dimensions, rates};
}
