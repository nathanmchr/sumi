// Run against the existing dev server with a Playwright page; no real user data.
async (page) => {
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  let locale = 'fr';
  await page.route('**/api/v1/auth/session', r => r.fulfill({json:{
    user:{id:'counts-preview',full_name:'Preview'}, settings:{interface_locale:locale,content_locale:locale}
  }}));
  const base = {unit_id:'first',unit_title:'Faire connaissance',goal:'Se présenter.',position:1,minutes:8,
    total_steps:20,completed_steps:0,completed:false,recommended:false};
  await page.route('**/api/v1/lessons?**', r => r.fulfill({json:[
    {...base,id:'one',title:'Partie 1',vocabulary_count:6,grammar_count:1,kanji_count:2},
    {...base,id:'two',title:'Partie 2',vocabulary_count:7,grammar_count:2,kanji_count:3},
    {...base,id:'first-recap',title:'Bilan cumulatif',is_recap:true,locked:true,vocabulary_count:0,grammar_count:0,kanji_count:0},
    {...base,id:'three',unit_id:'second',unit_title:'Les nombres',title:'Partie 3',vocabulary_count:4,grammar_count:1,kanji_count:0}
  ]}));
  for (locale of ['fr','en']) {
    await page.goto('http://localhost:3000/study/lessons');
    const stats = page.getByText(locale === 'fr'
      ? '13 mots · 3 points de grammaire · 5 kanjis'
      : '13 words · 3 grammar points · 5 kanji', {exact:true});
    await stats.waitFor();
    const unit = page.locator('section').filter({has:page.getByRole('heading',{name:'Faire connaissance',exact:true})});
    const finalRow = unit.locator('ol > li').last();
    check(await finalRow.getByText('Bilan cumulatif',{exact:true}).isVisible(), 'Recap is the final lesson');
    check(await finalRow.getByRole('link').count() === 0, 'Locked recap is not a link');
    check(await finalRow.locator('[aria-disabled=true]').count() === 1, 'Locked recap semantics');
    check(await page.getByText(locale === 'fr'
      ? '4 mots · 1 point de grammaire · 0 kanjis'
      : '4 words · 1 grammar point · 0 kanji', {exact:true}).isVisible(), 'Separate unit, singular and zero counts');
    for (const width of [1440,390,320]) {
      await page.setViewportSize({width,height:1000});
      check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No overflow');
      const title = await page.getByRole('heading',{name:'Faire connaissance',exact:true}).boundingBox();
      const counts = await stats.boundingBox();
      check(counts.y >= title.y + title.height, 'Counts below title');
      await unit.screenshot({path:`output/playwright/theme-final-${locale}-${width}.png`});
    }
  }
};
