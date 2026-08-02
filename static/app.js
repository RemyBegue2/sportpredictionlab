const NULL_ELEMENTS = new Map();
function nullElement(selector){
  if(NULL_ELEMENTS.has(selector)) return NULL_ELEMENTS.get(selector);
  const noop=()=>{};
  const stub=new Proxy({
    classList:{add:noop,remove:noop,toggle:noop,contains:()=>false},
    options:[],
    value:'',
    hidden:false,
    disabled:false,
    addEventListener:noop,
    removeEventListener:noop,
    focus:noop,
  },{
    get(target,property){ return property in target ? target[property] : undefined; },
    set(){ return true; },
  });
  console.warn(`Élément d’interface absent: ${selector}`);
  NULL_ELEMENTS.set(selector,stub);
  return stub;
}
const $ = (s) => document.querySelector(s) || nullElement(s);
let CSRF_TOKEN = null;
const fmt = (p) => `${(100*p).toFixed(1)}%`;
const signed = (p) => `${p >= 0 ? '+' : ''}${(100*p).toFixed(1)}%`;
const esc = (v) => String(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

function toast(message){ const el=$('#toast'); el.textContent=message; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'),4200); }
function loading(target){ target.className='result-panel'; target.innerHTML='<div class="loader">Calcul en cours</div>'; }
function probRow(label,p){ return `<div class="prob-row"><div class="prob-label" title="${esc(label)}">${esc(label)}</div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(0,Math.min(100,p*100))}%"></div></div><div class="prob-value">${fmt(p)}</div></div>`; }
async function jsonFetch(url, options={}){
  const headers=new Headers(options.headers||{});
  const method=(options.method||'GET').toUpperCase();
  if(CSRF_TOKEN && ['POST','PUT','PATCH','DELETE'].includes(method) && url!=='/api/auth/login') headers.set('X-CSRF-Token',CSRF_TOKEN);
  const r=await fetch(url,{...options,headers,credentials:'same-origin'});
  let body={}; try{body=await r.json()}catch{}
  if(r.status===401 && url!=='/api/auth/login'){ window.location.assign('/login'); throw new Error('Authentification requise'); }
  if(!r.ok) throw new Error(Array.isArray(body.detail)?body.detail.map(x=>x.msg).join(', '):(body.detail || `Erreur HTTP ${r.status}`));
  return body;
}
function fill(selector, values, preferred){ const el=$(selector); el.innerHTML=values.map(v=>`<option ${v===preferred?'selected':''}>${esc(v)}</option>`).join(''); }
function syncDifferent(a,b){ $(a).addEventListener('change',()=>{ if($(a).value===$(b).value){ const alt=[...$(b).options].find(o=>o.value!==$(a).value); if(alt) $(b).value=alt.value; }}); }
function numberOrNull(selector){ const raw=$(selector).value.trim(); return raw ? Number(raw) : null; }
function isoOrNull(selector){ const raw=$(selector).value; return raw ? new Date(raw).toISOString() : null; }

function marketTable(analysis){
  if(!analysis) return '';
  const rows=analysis.selections.map(s=>`<tr><td><b>${esc(s.selection)}</b><small>${esc(s.status)}</small></td><td>${s.decimal_odds.toFixed(2)}</td><td>${fmt(s.model_probability)}</td><td>${fmt(s.market_probability)}</td><td>${signed(s.edge)}</td><td>${signed(s.robust_expected_return)}</td></tr>`).join('');
  const freshness=analysis.odds_age_minutes===null?'heure manquante':`${analysis.odds_age_minutes.toFixed(0)} min`;
  return `<div class="market-box"><div class="market-heading"><div><small>${esc(analysis.bookmaker)} · ${esc(analysis.market_type)}</small><b>Comparaison au marché</b></div><span class="market-margin">Marge ${(100*analysis.overround).toFixed(1)}% · ${freshness}</span></div><div class="table-scroll"><table class="market-table"><thead><tr><th>Sélection</th><th>Cote</th><th>Modèle</th><th>Marché</th><th>Edge</th><th>EV robuste</th></tr></thead><tbody>${rows}</tbody></table></div><div class="warning">${esc(analysis.warning)}</div></div>`;
}

function renderProviderStatus(data){
  const configured=Boolean(data.configured);
  $('#oddsApiState').textContent=configured?'prête':'inactive';
  $('#providerStatus').textContent=configured?'Clé configurée côté serveur':'Clé non configurée';
  const q=data.quota||{};
  $('#providerQuota').textContent=q.known?`Quota restant : ${q.remaining ?? '—'} · dernier coût : ${q.last_cost ?? '—'}`:'Quota connu après le premier appel';
  $('#loadLiveOdds').disabled=!configured; $('#loadTennisOdds').disabled=!configured;
  const db=data.database||{};
  $('#dbSnapshots').textContent=db.odds_snapshots ?? 0;
  $('#cloudDatabase').textContent=db.connected?'Connectée':'Indisponible';
  $('#cloudLastSync').textContent=db.last_sync_at?`Dernière synchronisation : ${new Date(db.last_sync_at).toLocaleString('fr-FR')}`:'Aucune synchronisation persistée.';
}

function renderCloud(auth, readiness){
  $('#cloudAuth').textContent=auth.auth_required?'Accès privé':'Mode local';
  $('#logoutButton').hidden=!auth.auth_required;
  $('#cloudReady').textContent=readiness.status==='ready'?'Prête':'À corriger';
  $('#cloudIssues').textContent=(readiness.issues||[]).length?(readiness.issues||[]).join(' · '):'Modèles, intégrité et stockage validés.';
  const db=readiness.database||{};
  $('#cloudDatabase').textContent=db.connected?'Connectée':'Indisponible';
  $('#dbSnapshots').textContent=db.odds_snapshots ?? 0;
}

function renderSystem(data){
  const release=data.release||{};
  const app=release.app||{};
  const model=release.football_model||{};
  const contract=data.deployment_contract||{};
  const issues=data.issues||[];
  $('#systemRelease').textContent=`v${app.version||'—'} · ${String(release.release_id||'—').slice(0,12)}`;
  $('#systemCommit').textContent=app.source_commit&&app.source_commit!=='unknown'?`Commit ${String(app.source_commit).slice(0,12)}${app.deployment_id?` · déploiement ${String(app.deployment_id).slice(0,10)}`:''}`:'Commit d’exécution inconnu.';
  $('#systemModel').textContent=model.model_version||'—';
  $('#systemDataset').textContent=model.dataset_cutoff?`Données jusqu’au ${new Date(model.dataset_cutoff).toLocaleDateString('fr-FR')} · ${model.dataset_rows??'—'} matchs`:'Cutoff dataset indisponible.';
  const checks=[contract.api_version_matches_manifest,contract.running_commit_known,contract.artifact_integrity_verified,contract.running_model_registered];
  const passed=checks.filter(Boolean).length;
  $('#systemIntegrity').textContent=data.status==='verified'?'Vérifié':'Dégradé';
  $('#systemContract').textContent=`${passed}/${checks.length} contrôles réussis · artefact ${model.artifact_sha256?String(model.artifact_sha256).slice(0,12):'inconnu'}`;
  $('#systemIssues').innerHTML=issues.length?`<b>À corriger :</b> ${issues.map(esc).join(' · ')}`:'<b>Contrat vérifié :</b> version API, commit, registre et intégrité des artefacts sont cohérents.';
  const models=data.models||[];
  $('#systemModels').innerHTML=models.map(row=>`<div class="history-row"><div><b>${esc(row.sport)}</b><small>${esc(row.model_id)}</small></div><div><b>v${esc(row.version)}</b><small>${row.trained_until?`entraîné jusqu’au ${new Date(row.trained_until).toLocaleDateString('fr-FR')}`:'cutoff inconnu'}</small></div><span class="history-decision">${esc(row.status)}</span><time class="history-time">${row.dataset_hash?esc(String(row.dataset_hash).slice(0,12)):'—'}</time></div>`).join('')||'<p>Aucun modèle enregistré.</p>';
}

async function refreshSystem(){
  try{ renderSystem(await jsonFetch('/api/system/status')); }
  catch(error){ toast(`Preuve opérationnelle indisponible : ${error.message}`); }
}

function renderHistory(data){
  const rows=data.predictions||[];
  $('#predictionHistory').innerHTML=rows.map(row=>{
    const f=row.fixture||{};
    const label=row.sport==='football'?`${f.home_team||'—'} — ${f.away_team||'—'}`:`${f.player_1||'—'} — ${f.player_2||'—'}`;
    return `<div class="history-row"><div><b>${esc(row.sport)}</b><small>v${esc(row.model_version)}</small></div><div><b>${esc(label)}</b><small>ID ${row.id}</small></div><span class="history-decision">${esc(row.decision)}</span><time class="history-time">${new Date(row.created_at).toLocaleString('fr-FR')}</time></div>`;
  }).join('')||'<p>Aucune prédiction journalisée.</p>';
  const db=data.database||{}; $('#dbSnapshots').textContent=db.odds_snapshots ?? 0;
}

async function refreshHistory(){ try{ renderHistory(await jsonFetch('/api/history/predictions?limit=20')); }catch(error){ toast(error.message); } }

function renderBenchmark(data){
  const summary=data.summary||{};
  const status=summary.status||'not_run';
  const labels={not_run:'Non exécuté',not_evaluable:'Non évaluable',exploratory:'Exploratoire',preliminary_go:'Signal préliminaire',no_go:'Aucun avantage robuste',unknown:'Inconnu'};
  $('#benchmarkVerdict').textContent=labels[status]||status;
  $('#benchmarkReason').textContent=summary.reason||data.required_next_step||'Aucun benchmark historique réel disponible.';
  $('#benchmarkRows').textContent=summary.evaluated_rows ?? 0;
  const delta=summary.model_vs_winamax_log_loss_delta;
  $('#benchmarkDelta').textContent=Number.isFinite(delta)?`${delta<0?'−':'+'}${Math.abs(delta).toFixed(4)}`:'—';
  const ci=Array.isArray(summary.ci95)?summary.ci95:[];
  const hasValidCi=ci.length===2 && ci.every(value=>Number.isFinite(value));
  $('#benchmarkCi').textContent=hasValidCi?`IC 95 % [${ci[0].toFixed(4)} ; ${ci[1].toFixed(4)}]`:'Intervalle de confiance indisponible.';
  const clv=summary.clv;
  $('#benchmarkClv').textContent=clv&&Number.isFinite(clv.mean_log_clv)?`${(100*clv.mean_log_clv).toFixed(2)} %`:'—';
}


function renderShadow(data, history){
  const summary=data.summary||{};
  const aggregate=summary.aggregate||{};
  const settled=aggregate.settled_predictions ?? 0;
  $('#shadowState').textContent=settled;
  $('#shadowTotal').textContent=summary.total_predictions ?? 0;
  $('#shadowSettled').textContent=settled;
  $('#shadowMaturity').textContent=`Échantillon ${aggregate.maturity?.label || 'anecdotique'}.`;
  $('#shadowLogLoss').textContent=Number.isFinite(aggregate.log_loss)?aggregate.log_loss.toFixed(4):'—';
  const unitReturn=aggregate.theoretical_unit_return;
  $('#shadowReturn').textContent=Number.isFinite(unitReturn)?`${unitReturn>=0?'+':''}${unitReturn.toFixed(2)} u`:'—';
  const cycle=data.latest_cycle;
  $('#shadowLastCycle').textContent=cycle?`${cycle.status} · ${new Date(cycle.finished_at||cycle.started_at).toLocaleString('fr-FR')}`:'Aucun cycle enregistré';
  const duration=Number.isFinite(cycle?.duration_ms)?`${(cycle.duration_ms/1000).toFixed(1)} s`:'—';
  const quotaBefore=cycle?.quota_before ?? '—';
  const quotaAfter=cycle?.quota_after ?? cycle?.quota_remaining ?? '—';
  $('#shadowCycleMeta').textContent=cycle?`Durée ${duration} · quota ${quotaBefore} → ${quotaAfter} · verrou ${cycle.lock_acquired===false?'non acquis':'acquis'}`:'Durée et quota indisponibles.';

  const diagnostics=cycle?.diagnostics||{};
  const labels={
    provider_events:'Événements fournisseur',events_considered:'Événements examinés',events_truncated:'Événements tronqués',
    in_play:'Déjà commencés',outside_shadow_horizon:'Hors jalons shadow',identity_uncovered:'Identités non couvertes',
    winamax_missing:'Winamax absent',market_incomplete:'Marchés incomplets',model_stale_veto:'Bloqués modèle obsolète',
    no_robust_edge:'Sans edge robuste',research_candidates:'Candidats recherche',shadow_created:'Prédictions créées',
    shadow_reused:'Prédictions déjà figées',results_synced:'Résultats synchronisés',result_errors:'Erreurs résultats',provider_errors:'Erreurs fournisseur'
  };
  const ordered=Object.keys(labels).filter(key=>Number.isFinite(diagnostics[key]));
  $('#shadowFunnel').innerHTML=ordered.map(key=>`<div class="funnel-item"><b>${diagnostics[key]}</b><small>${esc(labels[key])}</small></div>`).join('')||'<p>Aucun compteur disponible pour ce cycle.</p>';
  const blockers=[
    ['provider_errors','erreur du fournisseur de cotes'],['in_play','rencontres déjà commencées'],
    ['outside_shadow_horizon','rencontres hors des quatre jalons shadow'],['identity_uncovered','équipes non couvertes par le modèle'],
    ['winamax_missing','cotes Winamax absentes'],['market_incomplete','marchés Winamax incomplets'],
    ['model_stale_veto','modèle football trop ancien'],['no_robust_edge','aucun avantage robuste après prudence']
  ];
  if((cycle?.predictions_created??0)>0){
    $('#shadowZeroReason').textContent=`${cycle.predictions_created} nouvelle(s) prédiction(s) figée(s).`;
  }else{
    const dominant=blockers.map(([key,label])=>({key,label,value:Number(diagnostics[key]||0)})).sort((a,b)=>b.value-a.value)[0];
    $('#shadowZeroReason').textContent=dominant&&dominant.value>0?`${dominant.value} cas : ${dominant.label}.`:'Aucun événement compatible avec un jalon shadow lors de ce passage.';
  }

  const footballModel=(data.models||[]).find(model=>model.model_id==='football-1n2-shadow');
  const modelWarning=$('#shadowModelWarning');
  if(footballModel){
    const freshness=footballModel.metrics?.freshness||{};
    const age=Number.isFinite(freshness.age_days)?`${freshness.age_days} jours`:'âge inconnu';
    const rebuild=data.fresh_rebuild||{};
    const rebuildState=rebuild.promoted?'Candidat frais promu.':'Reconstruction fraîche non promue : lancer ou consulter le workflow GitHub.';
    modelWarning.innerHTML=`<b>Modèle football : ${esc(footballModel.status)}</b> · données arrêtées au ${footballModel.trained_until?new Date(footballModel.trained_until).toLocaleDateString('fr-FR'):'—'} · ${esc(age)}. ${footballModel.status==='degraded'?'Toute sélection opérationnelle est bloquée ; observation uniquement.':'Shadow mode actif.'} ${esc(rebuildState)}`;
  }
  const rows=history.predictions||[];
  $('#shadowHistory').innerHTML=rows.map(row=>{
    const f=row.fixture||{};
    const label=row.sport==='football'?`${f.home_team||'—'} — ${f.away_team||'—'}`:`${f.player_1||'—'} — ${f.player_2||'—'}`;
    const result=row.status==='settled'?`${row.home_score}–${row.away_score}`:row.status;
    return `<div class="history-row"><div><b>${esc(row.status)}</b><small>${esc(row.model_id)} · ${esc(row.horizon||'—')}</small></div><div><b>${esc(label)}</b><small>${new Date(row.commence_time).toLocaleString('fr-FR')}</small></div><span class="history-decision">${esc(row.decision)}</span><time class="history-time">${esc(result)}</time></div>`;
  }).join('')||'<p>Aucune prédiction shadow enregistrée.</p>';
}

async function refreshShadow(){
  try{
    const [summary,history]=await Promise.all([jsonFetch('/api/shadow/summary'),jsonFetch('/api/shadow/predictions?limit=20')]);
    renderShadow(summary,history);
  }catch(error){ toast(error.message); }
}

function renderLiveOdds(data){
  const events=data.events||[];
  const cards=events.map(event=>{
    const winamax=event.winamax;
    const model=event.model?.probabilities;
    const isFootball=Boolean(event.api_home_team);
    const apiA=isFootball?event.api_home_team:event.api_player_1;
    const apiB=isFootball?event.api_away_team:event.api_player_2;
    const labels=isFootball?[event.model_home_team,'N',event.model_away_team]:[event.model_player_1,event.model_player_2];
    const odds=winamax?(isFootball?[winamax.odds[apiA],winamax.odds.Draw,winamax.odds[apiB]]:[winamax.odds[apiA],winamax.odds[apiB]]):[];
    const probs=model?(isFootball?[model.home,model.draw,model.away]:[model.player_1,model.player_2]):[];
    const lines=winamax&&model?labels.map((label,i)=>`<div class="odds-line"><span>${esc(label)}</span><b>${odds[i]?.toFixed(2) ?? '—'} · modèle ${fmt(probs[i])}</b></div>`).join(''):'';
    const reasons=(event.reasons||[]).map(x=>`<li>${esc(x)}</li>`).join('');
    return `<article class="slate-card"><div class="slate-top"><span>${esc(event.sport_key)}</span><b class="decision ${esc(event.decision)}">${esc(event.decision)}</b></div><h3>${esc(apiA)} — ${esc(apiB)}</h3><p>${new Date(event.commence_time).toLocaleString('fr-FR')}</p>${lines}<ul>${reasons}</ul><small>${winamax?'Winamax détecté':'Winamax absent'} · consensus ${event.consensus?.bookmaker_count ?? 0} books</small></article>`;
  }).join('');
  $('#liveOddsResult').innerHTML=cards||'<div class="slate-card"><h3>Aucun événement disponible</h3><p>Le marché peut être fermé, hors saison ou absent du flux.</p></div>';
}

function renderDaily(data){
  $('#dailyCandidates').textContent=data.summary?.research_candidates ?? 0;
  const events=data.events || [];
  const cards=events.map(event=>{
    const reasons=(event.reasons||[]).map(x=>`<li>${esc(x)}</li>`).join('');
    return `<article class="slate-card"><div class="slate-top"><span>${esc(event.sport)} · ${esc(event.tour||'')}</span><b class="decision ${esc(event.decision)}">${esc(event.decision)}</b></div><h3>${esc(event.event)}</h3><p>${esc(event.competition)} · ${esc(event.market)}</p><ul>${reasons}</ul><small>${event.winamax_odds?'Cotes disponibles':'Cotes Winamax non vérifiées'}</small></article>`;
  }).join('');
  $('#dailySlate').innerHTML=cards || `<div class="slate-card"><h3>Aucune revue embarquée</h3><p>${esc(data.warning||'Saisissez des cotes fraîches dans les formulaires.')}</p></div>`;
}

async function init(){
  try{
    const health=await jsonFetch('/api/health');
    $('#health').textContent=`API ${health.status} · v${health.version}`;
    $('#health').classList.add('ok');
  }catch(e){
    $('#health').textContent='API indisponible';
    $('#health').classList.add('error');
    toast(e.message);
    return;
  }

  try{
    const auth=await jsonFetch('/api/auth/status'); CSRF_TOKEN=auth.csrf_token||null;
    const readyResponse=await fetch('/api/ready',{credentials:'same-origin'}); const readiness=await readyResponse.json(); renderCloud(auth,readiness);
    const cat=await jsonFetch('/api/catalog');
    $('#footballRows').textContent=cat.data.football_rows; $('#tennisRows').textContent=cat.data.tennis_rows;
    const today=new Date().toISOString().slice(0,10); $('#footballDate').value=today;
    const minDate=new Date(`${cat.data.football_cutoff}T00:00:00Z`); minDate.setUTCDate(minDate.getUTCDate()+1); $('#footballDate').min=minDate.toISOString().slice(0,10);
    fill('#homeTeam',cat.football_teams,'Arsenal'); fill('#awayTeam',cat.football_teams,'Man City');
    fill('#player1',cat.tennis_players,'Taylor Fritz'); fill('#player2',cat.tennis_players,'Alexander Zverev');
    syncDifferent('#homeTeam','#awayTeam'); syncDifferent('#player1','#player2');
    const requests={
      audit:jsonFetch('/api/metrics'),
      slate:jsonFetch('/api/bets/today'),
      provider:jsonFetch('/api/odds/status'),
      history:jsonFetch('/api/history/predictions?limit=20'),
      benchmark:jsonFetch('/api/benchmark/summary'),
      shadow:jsonFetch('/api/shadow/summary'),
      shadowHistory:jsonFetch('/api/shadow/predictions?limit=20'),
      system:jsonFetch('/api/system/status'),
    };
    const keys=Object.keys(requests);
    const settled=await Promise.allSettled(Object.values(requests));
    const loaded={};
    settled.forEach((result,index)=>{
      if(result.status==='fulfilled') loaded[keys[index]]=result.value;
      else toast(`${keys[index]} : ${result.reason?.message||'chargement impossible'}`);
    });
    if(loaded.audit) $('#metrics').textContent=JSON.stringify(loaded.audit,null,2);
    if(loaded.slate) renderDaily(loaded.slate);
    if(loaded.provider) renderProviderStatus(loaded.provider);
    if(loaded.history) renderHistory(loaded.history);
    if(loaded.benchmark) renderBenchmark(loaded.benchmark);
    if(loaded.shadow&&loaded.shadowHistory) renderShadow(loaded.shadow,loaded.shadowHistory);
    if(loaded.system) renderSystem(loaded.system);
    if(loaded.provider?.configured){ try{ const tennis=await jsonFetch('/api/odds/sports?group=Tennis'); const active=tennis.sports.filter(x=>x.active); $('#oddsTennisSport').innerHTML=active.map(x=>`<option value="${esc(x.key)}">${esc(x.title)} · ${esc(x.key)}</option>`).join('') || '<option value="">Aucun tournoi actif</option>'; }catch(e){ toast(e.message); } }
  }catch(e){
    toast(`Interface partiellement chargée : ${e.message}`);
  }
}

$('#footballForm').addEventListener('submit',async e=>{
  e.preventDefault(); const target=$('#footballResult'); loading(target);
  try{
    const odds=[numberOrNull('#footballHomeOdds'),numberOrNull('#footballDrawOdds'),numberOrNull('#footballAwayOdds')];
    const payload={home_team:$('#homeTeam').value,away_team:$('#awayTeam').value,date:$('#footballDate').value||null};
    if(odds.every(v=>v!==null)) Object.assign(payload,{winamax_home_odds:odds[0],winamax_draw_odds:odds[1],winamax_away_odds:odds[2],odds_observed_at:isoOrNull('#footballOddsTime')});
    else if(odds.some(v=>v!==null)) throw new Error('Saisissez les trois cotes 1N2.');
    const data=await jsonFetch('/api/football/predict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const p=data.probabilities; const scores=data.top_scores.map(s=>`<tr><td>${esc(s.score)}</td><td>${fmt(s.probability)}</td></tr>`).join('');
    target.innerHTML=`<h3>${esc(data.fixture.home_team)} — ${esc(data.fixture.away_team)}</h3><p class="result-subtitle">Distribution 1N2 calibrée</p>${probRow(data.fixture.home_team,p.home)}${probRow('Match nul',p.draw)}${probRow(data.fixture.away_team,p.away)}<div class="result-meta"><div><small>Buts attendus domicile</small><b>${data.expected_goals.home.toFixed(2)}</b></div><div><small>Buts attendus extérieur</small><b>${data.expected_goals.away.toFixed(2)}</b></div></div><table class="score-table"><thead><tr><th>Score probable</th><th>Probabilité</th></tr></thead><tbody>${scores}</tbody></table>${marketTable(data.market_analysis)}<div class="warning">${esc(data.warning)}</div>`; await refreshHistory();
  }catch(err){ target.className='result-panel empty'; target.innerHTML='<p>La prédiction a échoué.</p>'; toast(err.message); }
});

$('#tennisForm').addEventListener('submit',async e=>{
  e.preventDefault(); const target=$('#tennisResult'); loading(target);
  try{
    const odds=[numberOrNull('#tennisP1Odds'),numberOrNull('#tennisP2Odds')];
    const payload={player_1:$('#player1').value,player_2:$('#player2').value,surface:$('#surface').value};
    if(odds.every(v=>v!==null)) Object.assign(payload,{winamax_player_1_odds:odds[0],winamax_player_2_odds:odds[1],odds_observed_at:isoOrNull('#tennisOddsTime')});
    else if(odds.some(v=>v!==null)) throw new Error('Saisissez les deux cotes vainqueur.');
    const data=await jsonFetch('/api/tennis/predict',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const p=data.probabilities;
    target.innerHTML=`<h3>${esc(data.fixture.player_1)} — ${esc(data.fixture.player_2)}</h3><p class="result-subtitle">Surface : ${esc(data.fixture.surface)} · ${data.model_mode==='elo_only_uncalibrated'?'Elo non calibré':'modèle calibré'}</p>${probRow(data.fixture.player_1,p.player_1)}${probRow(data.fixture.player_2,p.player_2)}<div class="result-meta"><div><small>Somme des probabilités</small><b>${data.symmetry_check.toFixed(6)}</b></div><div><small>Contrôle d'ordre</small><b>Symétrique</b></div></div>${marketTable(data.market_analysis)}<div class="warning">${esc(data.warning)}</div>`; await refreshHistory();
  }catch(err){ target.className='result-panel empty'; target.innerHTML='<p>La prédiction a échoué.</p>'; toast(err.message); }
});


$('#loadLiveOdds').addEventListener('click',async()=>{
  const target=$('#liveOddsResult');
  target.innerHTML='<div class="slate-card loading-card"><div class="loader">Chargement des cotes</div></div>';
  try{
    const sport=encodeURIComponent($('#oddsSport').value);
    const data=await jsonFetch(`/api/odds/football/slate?sport_key=${sport}`);
    renderLiveOdds(data);
    const status=await jsonFetch('/api/odds/status'); renderProviderStatus(status);
  }catch(err){
    target.innerHTML=`<div class="slate-card provider-error"><h3>Flux indisponible</h3><p>${esc(err.message)}</p></div>`;
    toast(err.message);
  }
});

$('#loadTennisOdds').addEventListener('click',async()=>{
  const target=$('#liveOddsResult'); const key=$('#oddsTennisSport').value;
  if(!key){ toast('Aucun tournoi tennis actif sélectionné.'); return; }
  target.innerHTML='<div class="slate-card loading-card"><div class="loader">Chargement des cotes tennis</div></div>';
  try{
    const surface=encodeURIComponent($('#oddsTennisSurface').value);
    const data=await jsonFetch(`/api/odds/tennis/slate?sport_key=${encodeURIComponent(key)}&surface=${surface}`);
    renderLiveOdds(data);
    const status=await jsonFetch('/api/odds/status'); renderProviderStatus(status);
  }catch(err){ target.innerHTML=`<div class="slate-card provider-error"><h3>Flux indisponible</h3><p>${esc(err.message)}</p></div>`; toast(err.message); }
});


$('#refreshHistory').addEventListener('click',refreshHistory);
$('#refreshShadow').addEventListener('click',refreshShadow);
$('#refreshSystem').addEventListener('click',refreshSystem);
$('#logoutButton').addEventListener('click',async()=>{
  try{ await jsonFetch('/api/auth/logout',{method:'POST'}); window.location.assign('/login'); }catch(error){ toast(error.message); }
});

init();
