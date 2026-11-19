"""Reference-inspired shell for the real Creator Studio dashboard.

The dashboard prototype is a visual reference only. This shell moves existing
API-backed controls into navigable sections without replacing their handlers.
"""
import html

from tubeforge.api.design_system import design_head, render_app_shell, render_sidebar, standalone_style


STUDIO_NAV_ITEMS = [
    ("references", "/references", "Reference videos"),
    ("long-form", "/long-form", "Long-form scripts"),
    ("batch", "/batch", "Batch plans"),
    ("clips", "/clips", "Clips"),
    ("studio", "/#studio", "Studio"),
    ("generations", "/#generations", "Generations"),
    ("scheduling", "/#scheduling", "Scheduling"),
    ("accounts", "/#accounts", "Accounts"),
    ("media", "/#media", "Media tools"),
    ("publishing", "/#publishing", "Publishing"),
    ("settings", "/settings", "Settings"),
]


def render_studio_sidebar(active: str) -> str:
    """Sidebar for standalone pages (Batch plans, Day review, ...). Shared with the design system."""
    return render_sidebar(active, STUDIO_NAV_ITEMS)


def wrap_studio_page(active: str, username: str | None, breadcrumb: str, main_html: str, components: str = "") -> str:
    """Design-system chrome (sidebar, top bar) around a standalone page's main content.

    Design tags come first. The page's component styles follow the config: Tailwind's Play CDN only
    applies @apply rules that are inside the body after the config script (a head style is read too early).
    """
    return (
        design_head()
        + standalone_style(components)
        + render_app_shell(active, STUDIO_NAV_ITEMS, breadcrumb, username)
        + main_html
        + "</div></div>"
    )


STUDIO_STATIC_MENU_SCRIPT = r"""
document.querySelectorAll('#signOutButton').forEach(button=>button.addEventListener('click',async()=>{button.disabled=true;try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');await fetch('/logout',{method:'POST',headers:{'x-csrf-token':csrf}});}catch(_){}finally{location.assign('/login');}}));
"""


STUDIO_SCRIPT = r"""<script>
(() => {
  const shell=document.querySelector('.shell'), grid=shell?.querySelector('.studio-grid');
  if(!shell||!grid)return;
  const header=document.querySelector('#spaTopbar');
  const connection=document.querySelector('#connection');
  const authInfo=document.querySelector('#authInfo');
  const crumb=document.querySelector('#studioBreadcrumb');
  const nav=document.querySelector('aside[data-nav]');
  const backdrop=document.querySelector('.tf-nav-backdrop');
  const publishing=shell.querySelector('#publishVideo')?.closest('.panel');
  const accounts=shell.querySelector('#accountProfileForm')?.closest('.panel');
  const scheduling=shell.querySelector('#bulkTopics')?.closest('.panel');
  if(!header||!connection||!authInfo||!crumb||!nav||!backdrop||!publishing||!accounts||!scheduling)return;
  const labels={studio:['Studio','See current work and create a video.'],generations:['Generations','Review saved videos, inputs, scripts and activity.'],scheduling:['Scheduling','Choose an account to manage its topic queue and generation schedules.'],accounts:['Accounts','Manage local account profiles and verified connections.'],media:['Media tools','Clip an existing source or add licensed music.'],publishing:['Publishing','Prepare exact video and destination drafts for review.']};
  if(authInfo){
    const username=authInfo.dataset.username||'';
    authInfo.replaceChildren();
    const label=document.createElement('span');label.className='hidden whitespace-nowrap sm:inline';label.textContent=username?('Signed in as '+username):'Local access';authInfo.append(label);
    if(username){
      const signOut=document.createElement('button');signOut.type='button';signOut.id='signOutButton';signOut.className='inline-flex h-8 items-center whitespace-nowrap rounded-md border border-tf-line-strong bg-tf-raised px-3 text-sm font-medium text-tf-text hover:border-tf-muted';signOut.textContent='Sign out';
      signOut.addEventListener('click',async()=>{signOut.disabled=true;try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');await fetch('/logout',{method:'POST',headers:{'x-csrf-token':csrf}});}catch(_){}finally{location.assign('/login');}});
      authInfo.append(signOut);
    }
  }
  const pages={};
  for(const [key,[title,description]] of Object.entries(labels)){
    const page=document.createElement('section');page.className='studio-page';page.dataset.studioPage=key;page.id='studio-'+key;
    const head=document.createElement('div');head.className='studio-page-head';
    const heading=document.createElement('div');const h1=document.createElement('h1');h1.textContent=title;const p=document.createElement('p');p.textContent=description;heading.append(h1,p);head.append(heading);page.append(head);pages[key]=page;shell.append(page);
  }
  const overview=document.createElement('section');overview.className='panel studio-overview';overview.innerHTML='<h2>Work in progress</h2><p class="sub">Queued topics and saved generation states across accounts.</p><div id="studioOverviewStatus" class="sub" role="status">Loading queue…</div><div id="studioOverviewList" class="studio-overview-list"></div><p><a href="#scheduling">Open account queues and schedules</a></p>';
  const createPanel=grid.children[0],generationList=grid.children[1];createPanel.id='createPanel';generationList.classList.add('generation-list');pages.studio.append(overview,createPanel);pages.generations.append(generationList);grid.remove();pages.publishing.append(publishing);pages.accounts.append(accounts);pages.scheduling.append(scheduling);
  const clipPanel=shell.querySelector('#clipsLink'),musicPanel=shell.querySelector('#musicUpload')?.closest('fieldset');if(clipPanel)pages.media.append(clipPanel);if(musicPanel)pages.media.append(musicPanel);
  async function refreshOverview(){try{const responses=await Promise.all(['/api/topics','/api/jobs','/api/schedules','/api/social-accounts'].map(url=>fetch(url)));if(responses.some(response=>!response.ok))throw Error('API unavailable');const [topics,jobs,schedules,accounts]=await Promise.all(responses.map(response=>response.json()));const byJob=new Map(jobs.map(job=>[job.id,job])),byAccount=new Map(accounts.map(account=>[account.id,account]));const queued=topics.filter(topic=>topic.status==='ready'),active=topics.filter(topic=>topic.status==='generating');overview.querySelector('#studioOverviewStatus').textContent=queued.length+' queued · '+active.length+' generating · '+schedules.filter(schedule=>schedule.enabled).length+' enabled schedules';const list=overview.querySelector('#studioOverviewList');list.replaceChildren();for(const topic of [...active,...queued].slice(0,8)){const item=document.createElement('div');item.className='studio-overview-item';const title=document.createElement('strong');title.textContent=topic.title;const detail=document.createElement('span'),job=byJob.get(topic.generation_job_id),account=byAccount.get(topic.account_id);detail.textContent=(account?account.display_name+' · '+account.platform:'Unassigned')+' · '+(job?job.state.replaceAll('_',' ')+(job.latest_event?' · '+(job.latest_event.stage||job.latest_event.event_type).replaceAll('_',' '):''):'Queued');item.append(title,detail);if(topic.generation_job_id){const link=document.createElement('a');link.href='#generations';link.textContent='Open generation';link.onclick=()=>sessionStorage.setItem('tubeforge:focus-job',topic.generation_job_id);item.append(link);}list.append(item);}if(!queued.length&&!active.length){const empty=document.createElement('p');empty.className='sub';empty.textContent='No topics are queued or generating. Add topics under an account in Scheduling.';list.append(empty);}}catch(_){overview.querySelector('#studioOverviewStatus').textContent='Could not refresh queue; showing last known items.';}}
  refreshOverview();setInterval(refreshOverview,10000);
  function closeMenu(restoreFocus=false){nav.dataset.open='false';backdrop.hidden=true;const menu=document.querySelector('[data-nav-open]');if(menu){menu.setAttribute('aria-expanded','false');if(restoreFocus)menu.focus();}}
  function showPage(){const key=Object.hasOwn(pages,location.hash.slice(1))?location.hash.slice(1):'studio';const transferFocus=nav.contains(document.activeElement);for(const [name,page] of Object.entries(pages))page.hidden=name!==key;for(const link of nav.querySelectorAll('a[href^="/#"]')){if(link.getAttribute('href')==='/#'+key)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}crumb.replaceChildren(document.createTextNode('Workspace / '));const strong=document.createElement('strong');strong.className='font-semibold text-tf-text';strong.textContent=labels[key][0];crumb.append(strong);closeMenu();if(transferFocus){const heading=pages[key].querySelector('h1');heading.tabIndex=-1;heading.focus({preventScroll:true});}window.scrollTo(0,0);}
  backdrop.addEventListener('click',()=>closeMenu(true));
  window.addEventListener('hashchange',showPage);showPage();
})();
</script>"""
