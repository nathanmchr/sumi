async (page) => {
  // Browser-only fixtures: no account, progress or catalog data is written.
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const errors = [];
  const onError = (error) => errors.push(error.message);
  page.on('pageerror', onError);
  let locale = 'fr';
  const common = { id: 'detail-qa', slug: 'detail-qa', jlpt_level_code: 'N5', mastery: 0.64, status: 'known', translation_locale: 'fr' };
  const fixtures = {
    vocabulary: {
      ...common, japanese: '学校', reading: 'がっこう', translation: 'école', part_of_speech: 'noun',
      furigana_segments: [{surface: '学校', reading: 'がっこう'}],
      example_sentences: [], kanji_links: [], audio_url: null, notes: null,
    },
    kanji: {
      ...common, character: '学', meanings: ['étudier', 'apprentissage'], onyomi: ['ガク'], kunyomi: ['まな.ぶ'],
      radicals: [], linked_vocabulary: [], mnemonic: null,
    },
    grammar: {
      ...common, title: 'だけ', explanation: 'seulement ; ne… que', structure: 'Nom + だけ',
      nuances: '', examples: [], counter_examples: [], exercisable: true,
    },
  };
  const mockApi = async (route) => {
    const path = route.request().url().split('/api/v1/')[1].split('?')[0];
    const body = path === 'auth/session' ? {
      user: { id: 'detail-qa-user', full_name: 'Vérification fiches', email: 'qa@example.invalid', is_admin: false },
      settings: {
        user_id: 'detail-qa-user', interface_locale: locale, content_locale: locale,
        furigana_display_mode: 'always', furigana_helper_enabled: false, daily_goal_minutes: 10,
        vocabulary_level_code: 'N5', vocabulary_min_level_code: 'N5',
        grammar_level_code: 'N5', grammar_min_level_code: 'N5', kanji_level_code: 'N5', kanji_min_level_code: 'N5',
      },
    } : fixtures[path.split('/')[1]];
    await route.fulfill({ status: body ? 200 : 404, contentType: 'application/json', body: JSON.stringify(body ?? {}) });
  };
  await page.route('**/api/v1/**', mockApi);
  const checks = [];
  try {
    for (const language of ['fr', 'en']) {
      locale = language;
      const titles = language === 'fr'
        ? {vocabulary: 'Vocabulaire', grammar: 'Grammaire', kanji: 'Kanjis'}
        : {vocabulary: 'Vocabulary', grammar: 'Grammar', kanji: 'Kanji'};
      for (const category of ['vocabulary', 'kanji', 'grammar']) {
        await page.goto(`http://localhost:3000/study/${category}/detail-qa`);
        await page.getByRole('heading', {level: 1, name: titles[category], exact: true}).waitFor();
        const header = page.locator('.page-header');
        await header.getByText('64%', {exact: true}).waitFor();
        assert(await header.getByText('JLPT N5', {exact: true}).count() === 1, 'Missing JLPT badge');
        assert(await header.getByText(language === 'fr' ? 'Acquis' : 'Known', {exact: true}).count() === 1, 'Untranslated status');
        assert(await page.getByRole('heading', {level: 1}).count() === 1, 'Duplicate page title');
        assert(await header.locator('a').getAttribute('href') === `/study/${category}`, 'Incorrect parent link');
        assert(await page.locator('.detail-card').getByText(language === 'fr' ? 'Maîtrise' : 'Mastery', {exact: true}).count() === 0, 'Mastery still repeated below');
        for (const width of [1440, 390, 320]) {
          await page.setViewportSize({width, height: 1000});
          const layout = await page.evaluate(() => {
            const header = document.querySelector('.page-header').getBoundingClientRect();
            const content = document.querySelector('.detail-card').getBoundingClientRect();
            const meta = document.querySelector('.detail-header__meta');
            return {
              overflow: document.documentElement.scrollWidth > innerWidth,
              headerAbove: header.bottom <= content.top,
              metaWraps: getComputedStyle(meta).flexWrap === 'wrap',
              metaFits: meta.scrollWidth <= meta.clientWidth,
            };
          });
          assert(!layout.overflow && layout.headerAbove && layout.metaFits && layout.metaWraps, `${language}/${category}/${width}: ${JSON.stringify(layout)}`);
        }
        checks.push(`${language}/${category}: title, JLPT, mastery, parent link, 1440/390/320 px`);
      }
    }
    locale = 'fr';
    const sections = ['Exemples', 'Contre-exemples', 'Nuances'];
    const cases = [
      { name: 'empty arrays', examples: [], counter_examples: [], nuances: '', visible: [] },
      { name: 'blank entries', examples: [{}, {text: ' \n ', translation: '\t', note: ' '}], counter_examples: [{}, {title: ' ', text: '\n', explanation: ' '}], nuances: ' \n ', visible: [] },
      { name: 'populated', examples: [{text: '水だけ飲みます。', translation: 'Je ne bois que de l’eau.'}], counter_examples: [{text: '水だけをだけ飲みます。', explanation: 'Ne pas répéter だけ.'}], nuances: 'Exprime une limitation.', visible: sections },
      { name: 'partial content', examples: [{note: 'Note pédagogique seule.'}], counter_examples: [{title: 'Cas à éviter'}], nuances: '', visible: ['Exemples', 'Contre-exemples'] },
      { name: 'nuances only', examples: [], counter_examples: [], nuances: 'Nuance seule.', visible: ['Nuances'] },
    ];
    for (const scenario of cases) {
      Object.assign(fixtures.grammar, scenario, {structure: ' \n '});
      await page.goto('http://localhost:3000/study/grammar/detail-qa');
      await page.getByRole('heading', {level: 1, name: 'Grammaire', exact: true}).waitFor();
      await page.locator('.detail-card h2').waitFor();
      for (const title of sections) {
        assert(await page.getByRole('heading', {name: title, exact: true}).count() === Number(scenario.visible.includes(title)), `${scenario.name}: incorrect ${title} section`);
      }
      assert(await page.getByRole('heading', {name: 'Structure', exact: true}).count() === 0, 'Empty structure heading');
      assert(await page.locator('.example-block').evaluateAll(blocks => blocks.every(block => block.textContent.trim())), 'Empty example block');
      if (scenario.name === 'partial content') {
        assert(await page.getByText('Note pédagogique seule.', {exact: true}).count() === 1, 'Lost example note');
        assert(await page.getByText('Cas à éviter', {exact: true}).count() === 1, 'Lost counter-example title');
      }
      checks.push(`grammar: ${scenario.name}`);
    }
    Object.assign(fixtures.grammar, {mastery: 0, status: 'new', structure: 'Nom + だけ', nuances: '', examples: [], counter_examples: []});
    await page.goto('http://localhost:3000/study/grammar/detail-qa');
    await page.locator('.page-header').getByText('0%', {exact: true}).waitFor();
    await page.locator('.page-header').getByText('Nouveau', {exact: true}).waitFor();
    await page.screenshot({path: 'output/playwright/study-detail-mobile.png', fullPage: true});
    await page.setViewportSize({width: 1440, height: 1000});
    await page.screenshot({path: 'output/playwright/study-detail-desktop.png', fullPage: true});
    assert(errors.length === 0, `Browser errors: ${errors.join('; ')}`);
    return { checks, errors };
  } finally {
    await page.unroute('**/api/v1/**', mockApi);
    page.off('pageerror', onError);
  }
}
