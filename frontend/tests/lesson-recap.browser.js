// Isolated UI regression: all lesson/auth traffic is intercepted, no real progress writes.
async (page) => {
  const check = (value, message) => { if (!value) throw new Error(message); };
  const lesson = { id: 'recap-preview', title: 'Bilan cumulatif', is_recap: true, total_steps: 841, completed_steps: 839, completed: false };
  const question = { id: 'recap-preview-question', kind: 'choice', title: 'Bilan cumulatif · 838 / 838',
    recap: true, recap_category: 'kanji', recap_section_index: 86, recap_section_total: 86,
    source_lesson_title: 'Faire connaissance · 1', prompt: 'Quel kanji correspond à : soleil ?',
    options: [{id:'sun',label:'日'}, {id:'moon',label:'月'}, {id:'fire',label:'火'}, {id:'water',label:'水'}] };
  let state = { lesson, revision: 1, cursor: 839, viewing: 839, step: question, feedback: null,
    correct: 837, answered: 837, recap_total: 838, recap_correct: 837, recap_answered: 837, next_lesson_id: null };
  await page.route('**/api/v1/auth/session', r => r.fulfill({json:{
    user:{id:'preview',full_name:'Preview'}, settings:{interface_locale:'fr',content_locale:'fr',furigana_display_mode:'always'}
  }}));
  await page.route('**/api/v1/lessons/recap-preview**', async r => {
    if (r.request().method() === 'POST') {
      const payload = r.request().postDataJSON();
      if (payload.action === 'answer') state = {...state, revision:2, answered:838, recap_answered:838,
        feedback:{correct:false, answer:'日', explanation:'日 : soleil', correct_option_id:'sun', selected_option_id:payload.answer}};
      else state = {...state, revision:3, cursor:841, viewing:841, step:null, feedback:null,
        lesson:{...lesson, completed_steps:841, completed:true}};
    }
    await r.fulfill({json:state});
  });
  await page.goto('http://localhost:3000/study/lessons/recap-preview');
  await page.getByRole('heading', {name:'Bilan cumulatif · 838 / 838'}).waitFor();
  check(await page.getByText('Kanji · 86 / 86', {exact:true}).isVisible(), 'Section progress');
  check(await page.getByText('Vu dans Faire connaissance · 1').isVisible(), 'Source lesson');
  for (const width of [1440,390,320]) {
    await page.setViewportSize({width,height:1000});
    check(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No mobile overflow');
    await page.screenshot({path:`output/playwright/recap-${width}.png`});
  }
  await page.getByRole('button', {name:'月', exact:true}).click();
  await page.getByRole('status').filter({hasText:'soleil'}).waitFor();
  check(await page.getByRole('button', {name:/^日/}).getAttribute('data-result') === 'correct', 'Correct option green');
  await page.reload();
  await page.getByRole('status').filter({hasText:'soleil'}).waitFor();
  await page.getByRole('button', {name:/Continuer/}).click();
  await page.getByRole('heading', {name:'Thème terminé.'}).waitFor();
  check(await page.getByText('837 / 838 au bilan cumulatif').isVisible(), 'Final recap score');
};
