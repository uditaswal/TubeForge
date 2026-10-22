"""Reference-inspired shell for the real Creator Studio dashboard.

The dashboard prototype is a visual reference only. This shell moves existing
API-backed controls into navigable sections without replacing their handlers.
"""

STUDIO_CSS = r"""
:root{color-scheme:dark;--bg:#0b111b;--panel:#131d2b;--muted:#a8b8cd;--line:#2b3a4e;--cyan:#a4f0cc;--good:#a4f0cc;--warn:#f3ce87;--bad:#ffa6a6;--studio-input:#101926;--studio-sidebar:#0e1521;--studio-panel-alt:#182434;--studio-purple:#c0b6fa}
*{box-sizing:border-box}
html{scrollbar-color:#3e5168 var(--bg)}
body{background:var(--bg);color:#edf3fb;font:14px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
::selection{background:#375e53;color:#fff}
button,input,select,textarea{font:inherit}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:2px solid var(--cyan);outline-offset:3px}
button:disabled{cursor:not-allowed;opacity:.52}
input:not([type=checkbox]),textarea,select{background:var(--studio-input);color:#edf3fb;border:1px solid #35465c;border-radius:9px;padding:11px 12px}
input::placeholder,textarea::placeholder{color:#95a7bf;opacity:1}
input:not([type=checkbox]):hover,textarea:hover,select:hover{border-color:#60758c}
button{background:var(--cyan);color:#103528;border:1px solid transparent;border-radius:9px;padding:10px 14px;transition:background-color .18s ease,border-color .18s ease,transform .18s ease;box-shadow:none}
button:hover:not(:disabled){background:#c5f8df;transform:translateY(-1px)}
button.secondary{background:#223346;color:#eaf4ff;border:1px solid #3c5067}
button.secondary:hover:not(:disabled){background:#2d4258;border-color:#60758c}
button.danger{background:#432b31;color:#ffd6d6;border:1px solid #74505a}
button.danger:hover:not(:disabled){background:#56323c}
button.small{padding:8px 11px;font-size:12px}
.studio-sidebar{position:fixed;inset:0 auto 0 0;width:228px;background:var(--studio-sidebar);border-right:1px solid var(--line);display:flex;flex-direction:column;padding:24px 15px 16px;z-index:35;overflow-y:auto}
.studio-brand{display:flex;align-items:center;gap:10px;padding:0 8px 26px;font-size:19px;font-weight:760;letter-spacing:-.025em;line-height:1.1}
.studio-brand small{display:block;margin-top:4px;color:var(--muted);font-size:10px;font-weight:500;letter-spacing:.02em}
.studio-brand-mark{display:grid;place-items:center;width:34px;height:34px;flex:none;border-radius:10px;background:var(--cyan);color:#103528;font-size:13px;letter-spacing:-.02em}
.studio-workspace{margin:0 2px 23px;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:var(--panel);color:#dbe8f6;font-size:11px;font-weight:650;letter-spacing:.02em}
.studio-nav-label{padding:0 12px;margin:0 0 8px;color:var(--muted);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase}
.studio-nav{display:grid;gap:4px}
.studio-nav button{position:relative;width:100%;min-height:42px;margin:0;padding:10px 12px;text-align:left;background:transparent;color:var(--muted);border:1px solid transparent;border-radius:8px;font-size:12px;font-weight:560;box-shadow:none}
.studio-nav button:hover:not(:disabled){background:var(--panel);color:#edf3fb;transform:none}
.studio-nav button[aria-current=page]{background:#20332e;border-color:#344b40;color:var(--cyan)}
.studio-nav button[aria-current=page]::after{content:"";position:absolute;right:12px;top:50%;width:5px;height:5px;border-radius:50%;background:var(--cyan);transform:translateY(-50%)}
.studio-sidebar-foot{margin-top:auto;padding:17px 10px 3px;color:var(--muted);font-size:11px;line-height:1.5;border-top:1px solid var(--line)}
.studio-main{margin-left:228px;min-width:0;min-height:100vh}
.studio-topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;height:70px;padding:0 30px;border-bottom:1px solid var(--line);background:var(--bg);margin:0}
.studio-crumb{min-width:0;color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.studio-crumb strong{color:#edf3fb;font-weight:650}
.studio-topbar #connection{margin-left:auto;flex:none;padding:5px 10px;border:1px solid var(--line);border-radius:8px;background:var(--panel);font-size:11px}
.studio-menu{display:none;width:auto;margin:0;padding:7px 10px;background:var(--panel);color:#edf3fb;border:1px solid var(--line)}
.studio-menu:hover:not(:disabled){background:var(--studio-panel-alt);color:#fff}
.studio-backdrop{display:none}
.shell{max-width:1550px;margin:0 auto;padding:30px 34px 60px;min-width:0}
.studio-page{min-width:0}
.studio-page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:24px}
.studio-page-head h1{margin:0;font-size:27px;font-weight:700;letter-spacing:-.025em;line-height:1.15}
.studio-page-head p{margin:8px 0 0;color:var(--muted);font-size:12px;max-width:68ch}
.grid{grid-template-columns:minmax(300px,390px) minmax(0,1fr);gap:19px;align-items:start}
.grid>section{min-width:0}
.panel,.job{background:var(--panel);border:1px solid var(--line);border-radius:15px;box-shadow:none}
.panel{padding:22px;min-width:0}
.job{padding:17px}
.studio-page>.panel{margin-top:0!important;max-width:980px}
h2{font-size:17px;font-weight:680;letter-spacing:-.015em}
h3{font-size:14px;font-weight:650}
.sub,.muted{color:var(--muted)}
label{color:#d5e0ee;font-size:12px;font-weight:540}
.notice{margin-top:9px;font-size:12px;line-height:1.5}
.toolbar{margin:1px 0 15px;align-items:flex-end}
.toolbar h2{font-size:18px}
.toolbar select{min-width:160px;background:var(--studio-input)}
.badge{background:#243c38;color:#c6f7dd}
.badge.pending{background:#403624;color:#f6dfad}
.badge.failed{background:#4b3037;color:#ffd1d4}
.badge.ready{background:#214333;color:#c3f6d5}
.failure{border-left:1px solid var(--bad);background:#362830;color:#ffe3e3}
.failure.pending{border-color:var(--warn);background:#3a3325;color:#ffe6ae}
.event{background:var(--studio-panel-alt);border-color:var(--line);border-radius:10px}
.actions{gap:8px}
fieldset{min-width:0}
details summary{cursor:pointer}
dialog{max-width:min(860px,calc(100vw - 28px));max-height:calc(100dvh - 28px);background:var(--panel);color:#edf3fb;border:1px solid var(--line);border-radius:15px;box-shadow:0 24px 70px #0009}
dialog::backdrop{background:#030912b8}
.modal-body{max-height:calc(100dvh - 125px);overflow:auto}
@media(max-width:1120px){.grid{grid-template-columns:1fr}.grid>.panel{max-width:760px}.studio-page>.panel{max-width:100%}}
@media(max-width:760px){
 .studio-sidebar{transform:translateX(-100%);width:min(270px,84vw);transition:transform .2s cubic-bezier(.2,.8,.2,1)}
 .studio-sidebar.open{transform:translateX(0)}
 .studio-backdrop.open{display:block;position:fixed;inset:0;z-index:30;border:0;border-radius:0;background:#030912a6;width:100%;height:100%;margin:0;padding:0;box-shadow:none}
 .studio-main{margin-left:0}
 .studio-topbar{height:60px;padding:0 16px;gap:10px}
 .studio-menu{display:inline-flex;align-items:center;justify-content:center}
 .studio-topbar #connection{max-width:39vw;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .shell{padding:22px 16px 44px}
 .studio-page-head{margin-bottom:19px}
 .studio-page-head h1{font-size:24px}
 .panel{padding:18px}
 .grid{gap:22px}
 .toolbar{align-items:stretch;flex-direction:column;gap:11px}
 .toolbar select{width:100%}
 .actions button{max-width:100%}
 .jobhead{flex-wrap:wrap}
}
@media(max-width:420px){.studio-topbar #connection{font-size:10px;padding:5px 7px}.studio-crumb{font-size:11px}.shell{padding-inline:13px}.panel{padding:16px}.studio-page-head h1{font-size:22px}}
@media(prefers-reduced-motion:reduce){button,.studio-sidebar{transition:none!important}button:hover:not(:disabled){transform:none}}
"""

STUDIO_SCRIPT = r"""<script>
(() => {
  const shell=document.querySelector('.shell'), grid=shell?.querySelector('.grid');
  if(!shell||!grid)return;
  const header=shell.querySelector('.top');
  const connection=header?.querySelector('#connection');
  const publishing=shell.querySelector('#publishVideo')?.closest('.panel');
  const accounts=shell.querySelector('#accountProfileForm')?.closest('.panel');
  const scheduling=shell.querySelector('#bulkTopics')?.closest('.panel');
  if(!header||!connection||!publishing||!accounts||!scheduling)return;
  const labels={studio:['Studio','Create, review and track local video generations.'],publishing:['Publishing','Prepare exact video and destination drafts for review.'],accounts:['Accounts','Manage local account profiles and verified connections.'],scheduling:['Scheduling','Choose an account to manage its topic queue and generation schedules.']};
  const sidebar=document.createElement('aside');sidebar.className='studio-sidebar';sidebar.id='studioSidebar';sidebar.setAttribute('aria-label','Workspace navigation');
  sidebar.innerHTML='<div class="studio-brand"><span class="studio-brand-mark">TF</span><span>TubeForge<small>Creator Studio</small></span></div><div class="studio-workspace">Local workspace</div><p class="studio-nav-label">Workspace</p><nav class="studio-nav" aria-label="Studio sections"><button type="button" data-studio-nav="studio">Studio</button><button type="button" data-studio-nav="publishing">Publishing</button><button type="button" data-studio-nav="accounts">Accounts</button><button type="button" data-studio-nav="scheduling">Scheduling</button></nav><p class="studio-sidebar-foot">Account plans remain local until a destination is verified and a separate draft is reviewed.</p>';
  const backdrop=document.createElement('button');backdrop.type='button';backdrop.className='studio-backdrop';backdrop.setAttribute('aria-label','Close navigation');backdrop.hidden=true;
  const main=document.createElement('div');main.className='studio-main';
  document.body.insertBefore(sidebar,shell);document.body.insertBefore(backdrop,shell);document.body.insertBefore(main,shell);
  main.append(header,shell);
  header.className='studio-topbar';
  const menu=document.createElement('button');menu.type='button';menu.className='studio-menu';menu.textContent='Menu';menu.setAttribute('aria-controls','studioSidebar');menu.setAttribute('aria-expanded','false');
  const crumb=document.createElement('div');crumb.className='studio-crumb';crumb.id='studioBreadcrumb';
  header.replaceChildren(menu,crumb,connection);
  const pages={};
  for(const [key,[title,description]] of Object.entries(labels)){
    const page=document.createElement('section');page.className='studio-page';page.dataset.studioPage=key;page.id='studio-'+key;
    const head=document.createElement('div');head.className='studio-page-head';
    const heading=document.createElement('div');const h1=document.createElement('h1');h1.textContent=title;const p=document.createElement('p');p.textContent=description;heading.append(h1,p);head.append(heading);page.append(head);pages[key]=page;shell.append(page);
  }
  pages.studio.append(grid);pages.publishing.append(publishing);pages.accounts.append(accounts);pages.scheduling.append(scheduling);
  function syncMenu(){sidebar.inert=window.matchMedia('(max-width:760px)').matches&&!sidebar.classList.contains('open');}
  function closeMenu(restoreFocus=false){sidebar.classList.remove('open');backdrop.classList.remove('open');backdrop.hidden=true;menu.setAttribute('aria-expanded','false');if(restoreFocus)menu.focus();syncMenu();}
  function showPage(){const key=Object.hasOwn(pages,location.hash.slice(1))?location.hash.slice(1):'studio';const transferFocus=sidebar.contains(document.activeElement);for(const [name,page] of Object.entries(pages))page.hidden=name!==key;for(const button of sidebar.querySelectorAll('[data-studio-nav]')){if(button.dataset.studioNav===key)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}crumb.replaceChildren(document.createTextNode('Workspace / '));const strong=document.createElement('strong');strong.textContent=labels[key][0];crumb.append(strong);closeMenu();if(transferFocus){const heading=pages[key].querySelector('h1');heading.tabIndex=-1;heading.focus({preventScroll:true});}window.scrollTo(0,0);}
  sidebar.querySelectorAll('[data-studio-nav]').forEach(button=>button.addEventListener('click',()=>{const key=button.dataset.studioNav;if(location.hash==='#'+key)showPage();else location.hash=key;}));
  menu.addEventListener('click',()=>{const open=!sidebar.classList.contains('open');sidebar.classList.toggle('open',open);backdrop.classList.toggle('open',open);backdrop.hidden=!open;menu.setAttribute('aria-expanded',String(open));syncMenu();if(open)sidebar.querySelector('[aria-current=page]')?.focus();});
  backdrop.addEventListener('click',()=>closeMenu(true));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&sidebar.classList.contains('open'))closeMenu(true);});
  window.addEventListener('hashchange',showPage);window.addEventListener('resize',syncMenu);showPage();
})();
</script>"""
