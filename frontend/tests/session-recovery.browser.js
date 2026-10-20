// Isolated regression: simulated auth and lesson responses; no real account writes.
async (page) => {
  const check = (value, message) => { if (!value) throw new Error(message); };
  const auth = {user:{id:'recovery-qa',email:'recovery@example.invalid',full_name:'Test session',is_admin:false},
    settings:{interface_locale:'fr',content_locale:'fr',furigana_display_mode:'always',romaji_enabled:false,furigana_helper_enabled:false}};
  let expired = false, refreshStatus = 200, refreshes = 0, answerAttempts = 0, saves = 0, logins = 0;
  const initial = () => ({lesson:{id:'recovery-test',unit_id:'test',unit_title:'Test',title:'Une longue leçon',goal:'Apprendre',position:1,minutes:30,
    total_steps:60,completed_steps:32,completed:false,recommended:true,vocabulary_count:6,grammar_count:1,kanji_count:1},
    revision:40,cursor:32,viewing:32,step:{id:'recall',kind:'recall',title:'Sans regarder',meaning:'chat',prompt:'Écris ce mot en kana ou en romaji.'},
    feedback:null,correct:10,answered:12,next_lesson_id:null});
  let state = initial();
  await page.route('**/api/v1/auth/session', route => route.fulfill(expired ? {status:401,json:{detail:'Expired'}} : {json:auth}));
  await page.route('**/api/v1/auth/refresh', route => {
    refreshes++;
    if (refreshStatus === 200) expired = false;
    return route.fulfill({status:refreshStatus,json:refreshStatus === 200 ? auth : {detail:'Refresh failed'}});
  });
  await page.route('**/api/v1/auth/login', route => {
    logins++;
    const credentials = route.request().postDataJSON();
    if (credentials.password !== 'correct-test-password') return route.fulfill({status:401,json:{detail:'Invalid credentials'}});
    check(credentials.email === auth.user.email, 'Reconnected wrong account');
    expired = false;
    return route.fulfill({json:auth});
  });
  await page.route('**/api/v1/auth/logout', route => {expired = true;refreshStatus = 401;return route.fulfill({json:{ok:true}});});
  await page.route('**/api/v1/lessons/recovery-test**', route => {
    if (route.request().method() === 'POST') answerAttempts++;
    if (expired) return route.fulfill({status:401,json:{detail:'Expired access'}});
    if (route.request().method() === 'POST') {
      const command = route.request().postDataJSON();
      check(command.step_id === 'recall' && command.revision === 40 && command.answer === 'ねこ', 'Lost original command');
      saves++;
      state = {...state,revision:41,correct:11,answered:13,feedback:{correct:true,answer:'ねこ',explanation:'',japanese:'猫',meaning:'chat',segments:[{surface:'猫',reading:'ねこ'}],romaji:'neko'}};
    }
    return route.fulfill({json:state});
  });
  const input = () => page.getByRole('textbox', {name:'Ta réponse',exact:true});
  const verify = () => page.getByRole('button', {name:/Vérifier/});
  const success = () => page.locator('[data-correct="true"]');
  const load = async () => {
    await page.goto('http://localhost:3000/study/lessons/recovery-test');
    await page.getByRole('heading', {name:'Sans regarder',exact:true}).waitFor();
  };
  await page.setViewportSize({width:1440,height:1000});await load();
  await input().fill('ねこ');expired = true;await verify().click();await success().waitFor();
  check(refreshes === 1 && answerAttempts === 2 && saves === 1, 'Automatic renewal/retry failed');
  check(page.url().includes('/lessons/recovery-test'), 'Navigated away after renewal');
  await page.reload();await success().waitFor();check(saves === 1, 'Reload duplicated answer');

  state = initial();await load();await input().fill('ねこ');expired = true;refreshStatus = 401;
  await verify().click();const dialog = page.getByRole('dialog');await dialog.waitFor();
  check(await input().inputValue() === 'ねこ', 'Input lost on expired session');
  check(page.url().includes('/lessons/recovery-test'), 'Redirected before reconnect');
  await dialog.getByLabel('Mot de passe', {exact:true}).fill('wrong');
  await dialog.getByRole('button', {name:'Se reconnecter',exact:true}).click();await dialog.getByRole('alert').waitFor();
  check(await input().inputValue() === 'ねこ', 'Wrong password cleared input');
  const previousRefreshes = refreshes;
  await page.setViewportSize({width:390,height:1000});
  await page.screenshot({path:'output/playwright/session-reconnect-mobile.png'});
  await dialog.getByLabel('Mot de passe', {exact:true}).fill('correct-test-password');
  await dialog.getByRole('button', {name:'Se reconnecter',exact:true}).click();await dialog.waitFor({state:'hidden'});
  check(logins === 2 && refreshes === previousRefreshes, 'Login triggered unwanted refresh');
  check(await input().inputValue() === 'ねこ', 'Input lost after reconnect');
  await verify().click();await success().waitFor();check(saves === 2, 'Cannot save after reconnect');

  state = initial();await load();await input().fill('ねこ');expired = true;refreshStatus = 503;
  await verify().click();await page.getByRole('alert').filter({hasText:"La réponse n'a pas pu"}).waitFor();
  check(await dialog.count() === 0 && await input().inputValue() === 'ねこ', 'Network failure signed out or lost input');
  refreshStatus = 200;await verify().click();await success().waitFor();check(saves === 3, 'Retry after network recovery failed');
  state = initial();expired = true;await load();check(!expired, 'Cold page did not renew session');
  check(await input().isVisible(), 'Lesson not restored on page load');
  const refreshBeforeLogout = refreshes;
  await page.getByRole('button', {name:'Se déconnecter',exact:true}).click();await page.waitForURL('**/login');
  check(refreshes === refreshBeforeLogout, 'Logout renewed session');
  return {automaticRenewal:true,sameCommand:true,noDuplicateSave:true,inlineReconnect:true,inputPreserved:true,networkRecovery:true,coldLoad:true,logout:true,saves};
}
