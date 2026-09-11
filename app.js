'use strict';
const $ = id => document.getElementById(id);
const state = {key: sessionStorage.getItem('legallens_access') || '', dossiers: [], templates: [], template: null, page: 0, activeDossier: null};
const titles = {dashboard:'Overzicht', dossiers:'Dossiers', analyze:'Nieuwe analyse', analyses:'Analysegeschiedenis', documents:'Documenten', sources:'Juridische bronnen', settings:'Instellingen'};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = value => {const d = new Date(value?.includes('T') ? value : (value || '').replace(' ', 'T') + 'Z'); return isNaN(d) ? '' : d.toLocaleDateString('nl-NL');};
function notice(text, error = false) { $('notice').textContent = text; $('notice').className = error ? 'error' : ''; $('notice').hidden = false; }
function fail(error) { const message = error.message || 'Er ging iets mis. Probeer het opnieuw.'; notice(message, true); if ($('dossier-dialog').open) { $('dialog-error').textContent = message; $('dialog-error').hidden = false; } }
async function api(path, options = {}, raw = false) {
  const headers = new Headers(options.headers || {});
  headers.set('X-API-Key', state.key);
  if (options.body && !(options.body instanceof FormData)) { headers.set('Content-Type','application/json'); options.body = JSON.stringify(options.body); }
  let response;
  try { response = await fetch(path, {...options, headers}); } catch { throw new Error('Geen verbinding met de server. Controleer je internetverbinding en probeer opnieuw.'); }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { $('connection').textContent = 'Sleutel controleren'; }
    const detail = Array.isArray(data.detail) ? data.detail.map(x => `${x.loc?.slice(1).join('.') || 'Invoer'}: ${x.msg}`).join('\n') : data.detail;
    throw new Error(typeof detail === 'string' ? detail : `Aanvraag mislukt (${response.status}).`);
  }
  return raw ? response : response.json();
}
async function busy(form, action) {
  const button = form.querySelector('[type=submit]');
  if(button?.disabled) return;
  if(button) button.disabled = true;
  try { await action(); } catch(error) { fail(error); } finally { if(button) button.disabled = false; }
}
function options(select, first = 'Zonder dossier') {
  const value = select.value;
  select.innerHTML = `<option value="">${first}</option>` + state.dossiers.map(d => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join('');
  select.value = value;
}
async function loadDossiers() {
  state.dossiers = (await api('/api/dossiers')).dossiers;
  document.querySelectorAll('.dossier-select').forEach(select => options(select, select.id === 'history-dossier' ? 'Alle dossiers' : 'Zonder dossier'));
  renderDossiers();
}
function dossierCard(d) {
  return `<article class="card"><span class="tag">${esc({active:'Actief',archived:'Gearchiveerd',closed:'Gesloten'}[d.status] || d.status)}</span><h3>${esc(d.name)}</h3><p>${esc(d.client || 'Geen cliënt ingevuld')} · ${esc(d.type || 'Algemeen')}</p><p>${d.file_count || 0} bestanden · ${d.analysis_count || 0} analyses</p><button class="secondary" data-action="dossier" data-id="${esc(d.id)}">Dossier openen</button></article>`;
}
function renderDossiers() {
  const q = $('dossier-search').value.toLocaleLowerCase();
  const items = state.dossiers.filter(d => `${d.name} ${d.client || ''}`.toLocaleLowerCase().includes(q));
  $('dossier-list').innerHTML = items.map(dossierCard).join('') || '<p class="empty">Geen dossiers gevonden. Maak een nieuw dossier aan.</p>';
  $('recent-dossiers').innerHTML = state.dossiers.slice(0,4).map(d => `<div class="row"><div><strong>${esc(d.name)}</strong><p>${esc(d.client || d.type || 'Algemeen')}</p></div><button class="link" data-action="dossier" data-id="${esc(d.id)}">Openen →</button></div>`).join('') || '<p class="empty">Je hebt nog geen dossiers. Begin met een nieuw dossier.</p>';
}
async function dashboard() {
  const [stats] = await Promise.all([api('/api/stats'),loadDossiers()]);
  $('stats').innerHTML = [['Dossiers',stats.total_dossiers],['Analyses',stats.total_analyses],['Documenten',stats.total_documents],['Bestanden',stats.total_files]].map(([label,value]) => `<article><span>${label}</span><strong>${value}</strong></article>`).join('');
}
async function show(view) {
  view = titles[view] ? view : 'dashboard';
  document.querySelectorAll('[data-page]').forEach(el => el.hidden = el.dataset.page !== view);
  document.querySelectorAll('[data-view]').forEach(el => {el.classList.toggle('active',el.dataset.view === view); if(el.dataset.view === view) el.setAttribute('aria-current','page'); else el.removeAttribute('aria-current');});
  $('page-title').textContent = titles[view];
  $('sidebar').classList.remove('open'); $('menu').setAttribute('aria-expanded','false');
  history.replaceState(null, '', '#' + view);
  if (!state.key && view !== 'settings') { notice('Verbind eerst je werkruimte via Instellingen.'); return; }
  try {
    if(view === 'dashboard') await dashboard();
    if(view === 'dossiers' || view === 'analyze' || view === 'analyses' || view === 'documents') await loadDossiers();
    if(view === 'analyses') await loadHistory();
    if(view === 'documents') await loadDocuments();
    if(view === 'settings' && state.key) await status();
  } catch(error) { fail(error); }
}
async function status() {
  const s = await api('/api/status');
  $('connection').textContent = 'Verbonden';
  $('storage-warning').hidden = s.storage_mode === 'persistent';
  $('service-status').innerHTML = `<div class="status-grid"><p>AI-analyse: <strong>${s.ai_configured ? 'sleutel ingesteld' : 'niet ingesteld'}</strong></p><p>Rechtspraak Open Data: <strong>rechtstreekse ECLI-koppeling, geen extra sleutel nodig</strong></p><p>Tavily zoeken: <strong>${s.search_configured ? 'sleutel ingesteld' : 'niet ingesteld'}</strong></p><p>Bestanden: maximaal ${s.max_upload_mb} MB · ${s.max_text_chars.toLocaleString('nl-NL')} tekens</p><p class="muted">Dit controleert de configuratie. Een geslaagde aanvraag bevestigt de externe verbinding. Opslagmodus: ${s.storage_mode === 'persistent' ? 'permanent ingesteld (disk zelf controleren)' : 'tijdelijk'}.</p></div>`;
  $('file-hint').textContent = `PDF, Word of TXT · maximaal ${s.max_upload_mb} MB · leesbare tekst vereist`;
  $('analysis-text').maxLength = s.max_text_chars;
  state.maxBytes = s.max_upload_mb * 1024 * 1024;
}
function openDossierForm(d = null) {
  $('dialog-error').hidden = true;
  $('edit-dossier-id').value = d?.id || '';
  $('dossier-dialog-title').textContent = d ? 'Dossier bewerken' : 'Nieuw dossier';
  $('dossier-name').value = d?.name || ''; $('dossier-client').value = d?.client || '';
  $('dossier-type').value = d?.type || ''; $('dossier-status').value = d?.status || 'active';
  $('dossier-dialog').showModal();
}
async function dossierDetail(id) {
  await show('dossiers');
  const d = await api('/api/dossiers/' + encodeURIComponent(id));
  state.activeDossier = d;
  $('dossier-detail').hidden = false;
  $('dossier-detail').innerHTML = `<div class="panel-heading"><h2>${esc(d.name)}</h2><div class="actions"><button class="secondary" data-action="edit-dossier">Bewerken</button><button class="danger" data-action="delete-dossier" data-id="${esc(d.id)}">Verwijderen</button></div></div><p>${esc(d.client || '')} · ${esc(d.type || '')}</p><h3>Bestanden</h3><form id="dossier-upload"><label>Bestand toevoegen<input type="file" id="dossier-upload-file" accept=".pdf,.docx,.txt" required></label><button type="submit">Bestand opslaan</button></form><div class="list">${d.files.map(f => `<div class="row"><div><strong>${esc(f.original_name)}</strong><p>${(f.size/1024).toFixed(1)} KB</p></div><div class="actions"><button class="link" data-action="file-download" data-id="${esc(f.id)}" data-name="${esc(f.original_name)}">Download</button><button class="link" data-action="file-analyze" data-id="${esc(f.id)}" data-name="${esc(f.original_name)}">Analyseren</button><button class="link" data-action="file-delete" data-id="${esc(f.id)}">Verwijderen</button></div></div>`).join('') || '<p class="empty">Nog geen bestanden toegevoegd.</p>'}</div><h3>Analyses in dit dossier</h3>${d.analyses.map(analysisRow).join('') || '<p class="empty">Nog geen analyses aan dit dossier gekoppeld.</p>'}`;
  $('dossier-detail').scrollIntoView({block:'start',behavior:'smooth'});
  $('dossier-upload').addEventListener('submit', event => { event.preventDefault(); busy(event.currentTarget, async () => {
    const data = new FormData(); data.append('file', $('dossier-upload-file').files[0]);
    await api(`/api/dossiers/${encodeURIComponent(id)}/files`,{method:'POST',body:data});
    await dossierDetail(id); notice('Bestand opgeslagen.');
  }); });
}
function objectHtml(value) {
  if (value === null || value === undefined || value === '') return '<p>Niet vastgesteld.</p>';
  if (Array.isArray(value)) return value.length ? '<ul>' + value.map(v => '<li>' + objectHtml(v) + '</li>').join('') + '</ul>' : '<p>Geen bevindingen.</p>';
  if (typeof value === 'object') return Object.keys(value).length ? '<dl>' + Object.entries(value).map(([k,v]) => `<dt>${esc(k.replaceAll('_',' '))}</dt><dd>${objectHtml(v)}</dd>`).join('') + '</dl>' : '<p>Niet vastgesteld.</p>';
  return `<span class="prose">${esc(value)}</span>`;
}
function analysisHtml(a) {
  return `<span class="eyebrow">ANALYSERESULTAAT</span><h2>${esc(a.contract_type)}</h2><p class="callout">AI-analyse op basis van je document. Controleer citaten, juridische verwijzingen en aanbevelingen voordat je handelt.</p><h3>Samenvatting</h3><p class="prose">${esc(a.summary)}</p><h3>Partijen</h3>${objectHtml(a.parties_involved)}<h3>Belangrijke datums</h3>${objectHtml(a.key_dates)}<h3>Risico's en aanbevelingen</h3>${(a.risks || []).map(r => `<div class="risk ${['low','medium','high','critical'].includes(r.severity) ? r.severity : ''}"><span class="tag">${esc(r.severity)}</span><h3>${esc(r.clause_type)}</h3><p>${esc(r.description)}</p>${r.clause_quote ? `<blockquote>${esc(r.clause_quote)}</blockquote>` : ''}<strong>Aanbeveling</strong><p>${esc(r.recommendation)}</p>${r.legal_reference ? `<button class="link" data-action="reference" data-article="${esc(r.legal_reference)}">${esc(r.legal_reference)} — bron opzoeken</button>` : ''}</div>`).join('') || '<p>Geen risico’s gerapporteerd; dit is geen garantie dat er geen risico’s zijn.</p>'}<h3>Algemeen advies</h3><p class="prose">${esc(a.overall_advice)}</p><h3>Actieplan</h3>${objectHtml(a.action_plan)}<h3>Onderhandelingsstrategie</h3>${objectHtml(a.negotiation_strategy)}<h3>Due diligence</h3>${objectHtml(a.due_diligence_findings)}<h3>Documenttoon</h3><p>Modelinschatting: ${Math.round((a.sentiment_score || 0)*100)} / 100. Dit is geen maat voor juridische kwaliteit of kans op succes.</p><div class="actions"><button class="secondary" data-action="print">Afdrukken / bewaren als PDF</button><button class="secondary" data-action="analysis-json" data-id="${esc(a.document_id)}">Download JSON</button></div>`;
}
function analysisRow(a) {return `<div class="row"><div><strong>${esc(a.contract_type)}</strong><p>${date(a.created_at)} · ${(a.risks || []).length} risico's</p><p>${esc(a.summary.slice(0,180))}</p></div><div class="actions"><button class="secondary" data-action="analysis" data-id="${esc(a.document_id)}">Bekijken</button><button class="link" data-action="analysis-delete" data-id="${esc(a.document_id)}">Verwijderen</button></div></div>`;}
async function loadHistory() {
  const query = new URLSearchParams({q:$('history-query').value,limit:'20',offset:String(state.page * 20)});
  if($('history-dossier').value) query.set('dossier_id',$('history-dossier').value);
  const data = await api('/api/analyses?' + query);
  $('history-list').innerHTML = data.analyses.map(analysisRow).join('') || '<p class="empty">Geen analyses gevonden.</p>';
  $('history-prev').disabled = state.page === 0; $('history-next').disabled = data.analyses.length < 20;
  $('history-page').textContent = `Pagina ${state.page + 1}`;
}
async function loadDocuments() {
  const [templates,docs] = await Promise.all([api('/api/templates'),api('/api/documents')]);
  state.templates = templates.templates;
  $('template-list').innerHTML = state.templates.map(t => `<article class="card"><span class="tag">${esc(t.category)}</span><h3>${esc(t.name)}</h3><p>${esc(t.description)}</p><button class="secondary" data-action="template" data-id="${esc(t.id)}">Concept invullen</button></article>`).join('');
  state.documents = docs.documents;
  $('document-list').innerHTML = docs.documents.map(d => `<div class="row"><div><strong>${esc(d.title)}</strong><p>${date(d.created_at)}</p></div><div class="actions"><button class="secondary" data-action="document" data-id="${esc(d.id)}">Openen</button><button class="link" data-action="document-delete" data-id="${esc(d.id)}">Verwijderen</button></div></div>`).join('') || '<p class="empty">Je hebt nog geen documenten gemaakt.</p>';
}
function documentDetail(d) {
  $('document-detail').hidden = false;
  $('document-detail').innerHTML = `<h3>${esc(d.title)}</h3><div class="prose">${esc(d.content)}</div><div class="actions">${['docx','pdf','txt'].map(f => `<button class="secondary" data-action="document-download" data-format="${f}" data-id="${esc(d.id || d.document_id)}">${f === 'docx' ? 'Word' : f.toUpperCase()}</button>`).join('')}</div>`;
  $('document-detail').scrollIntoView({block:'start',behavior:'smooth'});
}
function downloadBlob(blob, name) {const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);}
async function download(path, name) { const r = await api(path,{},true); downloadBlob(await r.blob(),name); }
async function action(button) {
  const id = button.dataset.id;
  switch(button.dataset.action) {
    case 'dossier': return dossierDetail(id);
    case 'edit-dossier': return openDossierForm(state.activeDossier);
    case 'delete-dossier':
      if(!confirm('Dit dossier en de bijbehorende bestanden verwijderen? Analyses en gemaakte documenten blijven bewaard zonder dossierkoppeling.')) return;
      await api('/api/dossiers/'+encodeURIComponent(id),{method:'DELETE'}); $('dossier-detail').hidden = true; state.activeDossier = null; await loadDossiers(); return notice('Dossier verwijderd.');
    case 'file-download': return download('/api/files/'+encodeURIComponent(id),button.dataset.name);
    case 'file-delete':
      if(!confirm('Dit bestand definitief verwijderen?')) return;
      await api('/api/files/'+encodeURIComponent(id),{method:'DELETE'}); return dossierDetail(state.activeDossier.id);
    case 'file-analyze': {
      const r = await api('/api/files/'+encodeURIComponent(id),{},true); const blob = await r.blob();
      const file = new File([blob],button.dataset.name); const transfer = new DataTransfer(); transfer.items.add(file);
      await show('analyze'); $('analysis-file').files = transfer.files; $('analysis-file').dispatchEvent(new Event('change')); $('analysis-dossier').value = state.activeDossier.id; return;
    }
    case 'analysis': {
      const a = await api('/api/analyses/'+encodeURIComponent(id)); await show('analyses');
      $('history-detail').innerHTML = analysisHtml(a); $('history-detail').hidden = false; $('history-detail').scrollIntoView({behavior:'smooth'}); return;
    }
    case 'analysis-delete':
      if(!confirm('Deze analyse definitief verwijderen?')) return;
      await api('/api/analyses/'+encodeURIComponent(id),{method:'DELETE'}); $('history-detail').hidden = true; if (location.hash === '#dossiers' && state.activeDossier) return dossierDetail(state.activeDossier.id); return loadHistory();
    case 'analysis-json': return downloadBlob(new Blob([JSON.stringify(await api('/api/analyses/'+encodeURIComponent(id)),null,2)],{type:'application/json'}),'analyse.json');
    case 'print': return window.print();
    case 'reference': await show('sources'); $('source-query').value = button.dataset.article.slice(0,150); $('source-query').focus(); return;
    case 'template': {
      state.template = state.templates.find(t => t.id === id); $('template-title').textContent = state.template.name;
      $('template-fields').innerHTML = state.template.fields.map(f => `<label>${esc(f.replaceAll('_',' '))}${f === 'beschrijving' ? `<textarea required name="${esc(f)}" rows="5"></textarea>` : `<input required name="${esc(f)}" maxlength="2000">`}</label>`).join('');
      $('document-form').hidden = false; $('document-detail').hidden = true; $('document-form').scrollIntoView({behavior:'smooth'}); return;
    }
    case 'document': return documentDetail(state.documents.find(d => d.id === id));
    case 'document-download': return download(`/api/documents/${encodeURIComponent(id)}/download?format=${button.dataset.format}`,`document.${button.dataset.format}`);
    case 'document-delete':
      if(!confirm('Dit conceptdocument definitief verwijderen?')) return;
      await api('/api/documents/'+encodeURIComponent(id),{method:'DELETE'}); $('document-detail').hidden = true; return loadDocuments();
  }
}
document.addEventListener('click',async event => {
  const nav = event.target.closest('[data-view]'); if(nav) { event.preventDefault(); await show(nav.dataset.view); return; }
  const button = event.target.closest('[data-action]'); if(button && !button.disabled) {button.disabled=true; try{await action(button);}catch(error){fail(error);}finally{button.disabled=false;}}
});
$('menu').addEventListener('click',() => {$('sidebar').classList.toggle('open'); $('menu').setAttribute('aria-expanded',String($('sidebar').classList.contains('open')));});
$('close-menu').addEventListener('click',() => {$('sidebar').classList.remove('open'); $('menu').setAttribute('aria-expanded','false');});
document.addEventListener('keydown',e => {if(e.key === 'Escape') {$('sidebar').classList.remove('open'); $('menu').setAttribute('aria-expanded','false');}});
$('new-dossier').addEventListener('click',() => openDossierForm());
$('close-dialog').addEventListener('click',() => $('dossier-dialog').close());
$('dossier-search').addEventListener('input',renderDossiers);
$('dossier-form').addEventListener('submit',event => {event.preventDefault(); busy(event.currentTarget,async () => {
  const id = $('edit-dossier-id').value;
  const d = await api('/api/dossiers'+(id ? '/'+encodeURIComponent(id) : ''),{method:id?'PUT':'POST',body:{name:$('dossier-name').value,client:$('dossier-client').value,type:$('dossier-type').value,status:$('dossier-status').value}});
  $('dossier-dialog').close(); await dossierDetail(d.id); notice('Dossier opgeslagen.');
});});
$('settings-form').addEventListener('submit',event => {event.preventDefault(); busy(event.currentTarget,async () => {
  state.key = $('access-key').value.trim();
  try {await status();} catch(error){state.key = ''; sessionStorage.removeItem('legallens_access'); throw error;}
  sessionStorage.setItem('legallens_access',state.key); $('access-key').value=''; notice('Verbonden met je werkruimte.'); await show('dashboard');
});});
$('logout').addEventListener('click',() => {sessionStorage.removeItem('legallens_access'); location.replace(location.pathname+'#settings'); location.reload();});
$('analysis-file').addEventListener('change',() => {const file = $('analysis-file').files[0]; $('analysis-text').disabled = !!file; if(file) $('analysis-text').value='';});
$('clear-file').addEventListener('click',() => {$('analysis-file').value=''; $('analysis-text').disabled=false;});
$('analysis-form').addEventListener('reset',() => {$('analysis-text').disabled=false; $('analysis-result').hidden=true;});
$('analysis-form').addEventListener('submit',event => {event.preventDefault(); busy(event.currentTarget,async () => {
  const file = $('analysis-file').files[0], text = $('analysis-text').value.trim();
  if(file && file.size > (state.maxBytes || 10*1024*1024)) throw new Error('Het bestand overschrijdt de uploadlimiet.');
  if(!file && text.length < 50) throw new Error('Plak minimaal 50 tekens of selecteer een bestand.');
  const dossier = $('analysis-dossier').value, mode = $('analysis-mode').value, type = $('analysis-type').value;
  let body, path;
  if(file) {body = new FormData(); body.append('file',file); body.append('mode',mode); body.append('analysis_type',type); if(dossier) body.append('dossier_id',dossier); path='/api/analyze-file';}
  else {body={text,mode,analysis_type:type,dossier_id:dossier || null}; path='/api/analyze-text';}
  $('analysis-progress').textContent='Analyse wordt uitgevoerd…'; $('analysis-result').hidden=true;
  try {const a = await api(path,{method:'POST',body}); $('analysis-result').innerHTML=analysisHtml(a); $('analysis-result').hidden=false; notice('Analyse voltooid en opgeslagen.'); $('analysis-result').scrollIntoView({behavior:'smooth'});}
  finally {$('analysis-progress').textContent='';}
});});
$('history-form').addEventListener('submit',event => {event.preventDefault(); state.page=0; busy(event.currentTarget,loadHistory);});
$('history-prev').addEventListener('click',() => {state.page=Math.max(0,state.page-1); loadHistory().catch(fail);});
$('history-next').addEventListener('click',() => {state.page++; loadHistory().catch(fail);});
$('document-form').addEventListener('submit',event => {event.preventDefault(); busy(event.currentTarget,async () => {
  const custom_fields = Object.fromEntries(new FormData(event.target));
  const d = await api('/api/templates/generate',{method:'POST',body:{template_id:state.template.id,dossier_id:$('document-dossier').value || null,custom_fields}});
  await loadDocuments(); documentDetail(d); notice('Conceptdocument opgeslagen.');
});});
function sourceCards(items) {return items.map(s => {
  let url; try {url = new URL(s.url); if(url.protocol !== 'https:') return '';}catch{return '';}
  const official = s.provider === 'rechtspraak_open_data';
  return `<article class="risk"><span class="tag">${official ? 'Rechtspraak Open Data' : 'Tavily-zoekfragment'}</span><h3>${esc(s.title || s.ecli || 'Bron')}</h3>${official ? `<p>${esc([s.ecli,s.court,s.date].filter(Boolean).join(' · '))}</p>` : ''}<p class="prose">${esc(s.content || s.summary)}</p>${s.notice ? `<p class="muted">${esc(s.notice)}</p>` : ''}${s.full_text_available ? `<details><summary>Gepubliceerde uitspraaktekst bekijken</summary><div class="prose judgment">${esc(s.full_text)}</div></details>` : ''}<a class="source-link" href="${esc(url.href)}" target="_blank" rel="noopener noreferrer">Officiële bron openen ↗</a></article>`;
}).join('') || '<p>Geen passende bronnen gevonden.</p>';}
$('source-form').addEventListener('submit',event => {event.preventDefault(); busy(event.currentTarget,async () => {
  $('source-progress').textContent='Bronnen en commentaar worden opgehaald…'; $('source-result').hidden=true;
  try {const r = await api('/api/legal-commentary',{method:'POST',body:{article:$('source-query').value}});
    $('source-result').innerHTML=`<h2>${esc(r.title)}</h2><p class="callout">${esc(r.notice)}</p><h3>Toelichting</h3><p class="prose">${esc(r.commentary)}</p>${(r.warnings || []).map(w => `<p class="callout">${esc(w)}</p>`).join('')}${r.text_kind === 'official_case' ? '' : `<h3>Wetgeving — zoekfragmenten</h3>${sourceCards(r.sources || [])}`}<h3>Jurisprudentie</h3>${sourceCards(r.jurisprudence || [])}`; $('source-result').hidden=false;
  }finally{$('source-progress').textContent='';}
});});
$('legacy-export').addEventListener('click',() => {const data = {exported_at:new Date().toISOString(),dossiers:localStorage.getItem('legallens_dossiers'),analyses:localStorage.getItem('legallens_analyses')}; downloadBlob(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}),'legallens-oude-browsergegevens.json'); notice('Reservekopie gedownload. De oorspronkelijke browsergegevens blijven staan.');});
if(state.key) status().then(() => show(location.hash.slice(1) || 'dashboard')).catch(error => {fail(error); show('settings');});
else show('settings');
