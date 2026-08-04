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
const pct = (value) => Number.isFinite(Number(value)) ? `${(100 * Number(value)).toFixed(1)} %` : '—';
let RESEARCH_SIGNALS = [];
let RESEARCH_SIGNAL_FILTER = 'all';
let EXPERT_DATA_LOADED = false;
let EXPERT_DATA_PROMISE = null;
let FEATURE_LAB_DATA = null;
let CHALLENGER_FACTORY_DATA = null;
let EVIDENCE_ACCELERATION_DATA = null;
const INFLIGHT_GETS = new Map();
const ACTIVE_REQUESTS = new Set();
let TOAST_TIMER = null;
let SESSION_REQUESTS = 0;
let SESSION_ERRORS = 0;
const MAX_VISIBLE_CARDS = 8;
const REQUEST_TIMEOUT_MS = 12000;

function currentInterfaceMode(){
  try{ return localStorage.getItem('sports-lab-interface-mode')==='expert'?'expert':'simple'; }catch{ return 'simple'; }
}

function applyInterfaceMode(mode,{load=true}={}){
  const expert=mode==='expert';
  document.body.classList.toggle('expert-mode',expert);
  document.body.classList.toggle('simple-mode',!expert);
  const button=$('#interfaceMode');
  button.textContent=expert?'Vue simple':'Mode expert';
  button.setAttribute?.('aria-pressed',expert?'true':'false');
  try{ localStorage.setItem('sports-lab-interface-mode',expert?'expert':'simple'); }catch{}
  if(expert&&load) loadExpertData();
}

function currentSimplePanel(){
  try{
    const value=localStorage.getItem('sports-lab-simple-panel');
    return ['today','signals','learning'].includes(value)?value:'today';
  }catch{ return 'today'; }
}

function applySimplePanel(panel,{scroll=false}={}){
  const selected=['today','signals','learning'].includes(panel)?panel:'today';
  (document.querySelectorAll?.('[data-simple-panel]')||[]).forEach(section=>section.classList.toggle('is-active',section.dataset.simplePanel===selected));
  (document.querySelectorAll?.('[data-simple-target]')||[]).forEach(link=>link.classList.toggle('active',link.dataset.simpleTarget===selected));
  try{ localStorage.setItem('sports-lab-simple-panel',selected); }catch{}
  if(scroll&&currentInterfaceMode()==='simple'){
    const target=document.querySelector?.(`[data-simple-panel="${selected}"]`);
    target?.scrollIntoView?.({behavior:'smooth',block:'start'});
  }
}


function updateSessionStatus(){
  const el=$('#sessionStatus');
  if(!el || !el.classList) return;
  el.textContent=SESSION_ERRORS?`${SESSION_ERRORS} erreur(s) récupérée(s) · ${SESSION_REQUESTS} requête(s)`:`Stable · ${SESSION_REQUESTS} requête(s)`;
  el.className=`session-status ${SESSION_ERRORS?'attention':'ok'}`;
}
function toast(message){
  const el=$('#toast');
  el.textContent=message;
  el.classList.add('show');
  if(TOAST_TIMER && typeof clearTimeout==='function') clearTimeout(TOAST_TIMER);
  TOAST_TIMER=setTimeout(()=>el.classList.remove('show'),4200);
}

function loading(target){ target.className='result-panel'; target.innerHTML='<div class="loader">Calcul en cours</div>'; }
function probRow(label,p){ return `<div class="prob-row"><div class="prob-label" title="${esc(label)}">${esc(label)}</div><div class="bar-track"><div class="bar-fill" style="width:${Math.max(0,Math.min(100,p*100))}%"></div></div><div class="prob-value">${fmt(p)}</div></div>`; }
async function jsonFetch(url, options={}){
  const headers=new Headers(options.headers||{});
  const method=(options.method||'GET').toUpperCase();
  const dedupeKey=method==='GET'&&!options.noDedupe?`${method}:${url}`:null;
  if(dedupeKey&&INFLIGHT_GETS.has(dedupeKey)) return INFLIGHT_GETS.get(dedupeKey);
  if(CSRF_TOKEN && ['POST','PUT','PATCH','DELETE'].includes(method) && url!=='/api/auth/login') headers.set('X-CSRF-Token',CSRF_TOKEN);
  const controller=typeof AbortController!=='undefined'?new AbortController():null;
  const timeoutMs=Number(options.timeoutMs||REQUEST_TIMEOUT_MS);
  const timer=controller?setTimeout(()=>controller.abort(),timeoutMs):null;
  if(controller) ACTIVE_REQUESTS.add(controller);
  const request=(async()=>{
    SESSION_REQUESTS+=1; updateSessionStatus();
    try{
      const r=await fetch(url,{...options,headers,credentials:'same-origin',signal:controller?.signal||options.signal});
      let body={}; try{body=await r.json()}catch{}
      if(r.status===401 && url!=='/api/auth/login'){ window.location.assign('/login'); throw new Error('Authentification requise'); }
      if(!r.ok) throw new Error(Array.isArray(body.detail)?body.detail.map(x=>x.msg).join(', '):(body.detail || `Erreur HTTP ${r.status}`));
      return body;
    }catch(error){
      SESSION_ERRORS+=1; updateSessionStatus();
      if(error?.name==='AbortError') throw new Error(`Délai dépassé pour ${url}`);
      throw error;
    }finally{
      if(timer&&typeof clearTimeout==='function') clearTimeout(timer);
      if(controller) ACTIVE_REQUESTS.delete(controller);
      if(dedupeKey) INFLIGHT_GETS.delete(dedupeKey);
    }
  })();
  if(dedupeKey) INFLIGHT_GETS.set(dedupeKey,request);
  return request;
}

async function withBusy(selector, task){
  const button=$(selector);
  if(button.disabled) return null;
  const previous=button.textContent;
  button.disabled=true;
  button.setAttribute?.('aria-busy','true');
  try{ return await task(); }
  finally{ button.disabled=false; button.textContent=previous; button.setAttribute?.('aria-busy','false'); }
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
  const paidEnabled=Boolean(data.paid_calls_enabled);
  $('#oddsApiState').textContent=!configured?'inactive':(paidEnabled?'autorisée':'protégée');
  $('#providerStatus').textContent=!configured?'Clé non configurée':(paidEnabled?'Appels payants autorisés':'Pare-feu actif · appels payants désactivés');
  const q=data.quota||{};
  $('#providerQuota').textContent=paidEnabled?(q.known?`Quota restant : ${q.remaining ?? '—'} · dernier coût : ${q.last_cost ?? '—'} · plafond quotidien ${data.daily_credit_cap ?? 0}`:`Quota inconnu · plafond quotidien ${data.daily_credit_cap ?? 0}`):'0 crédit par défaut · activation explicite requise';
  $('#loadLiveOdds').disabled=!configured||!paidEnabled; $('#loadTennisOdds').disabled=!configured||!paidEnabled;
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

function renderControlCenter(data){
  const labels={ok:'Opérationnel',pending:'En attente de preuves',attention:'Action nécessaire',blocked:'Bloqué'};
  const overall=data.overall_status||'pending';
  $('#controlOverall').textContent=labels[overall]||overall;
  $('#controlOverall').className=`control-status ${esc(overall)}`;
  const summary=data.summary||{};
  $('#controlSummary').textContent=`${summary.ok||0} OK · ${summary.pending||0} en attente · ${summary.attention||0} attention · ${summary.blocked||0} bloqué`;
  $('#controlChecks').innerHTML=(data.checks||[]).map(check=>`<article class="control-check ${esc(check.status)}"><div><small>${esc(labels[check.status]||check.status)}</small><h3>${esc(check.label)}</h3></div><p>${esc(check.detail)}</p><footer><b>Action :</b> ${esc(check.action)}${check.workflow?`<code>${esc(check.workflow)}</code>`:''}</footer></article>`).join('')||'<p>Aucun contrôle disponible.</p>';
  $('#controlNextActions').innerHTML=(data.next_actions||[]).map(item=>`<article><span>${item.priority}</span><div><b>${esc(item.label)}</b><p>${esc(item.action)}</p>${item.workflow?`<code>Actions → ${esc(item.workflow)}</code>`:''}</div></article>`).join('')||'<article><span>✓</span><div><b>Aucune action urgente</b><p>Les contrôles cloud sont cohérents.</p></div></article>';
  const riskLabels={zero_credit:'Zéro crédit',read_only:'Lecture seule',controlled:'Contrôlé',consumes_api_credits:'Consomme des crédits API',read_only_production:'Lecture production',destructive:'Destructif'};
  $('#controlWorkflows').innerHTML=(data.workflows||[]).map(flow=>`<article class="workflow-card"><div><small>${esc(riskLabels[flow.risk]||flow.risk)}</small><h3>${esc(flow.name)}</h3></div><p>${esc(flow.purpose)}</p><code>${esc(flow.file)}</code>${flow.confirmation?`<span>Confirmation : ${esc(flow.confirmation)}</span>`:''}</article>`).join('')||'<p>Aucun workflow déclaré.</p>';
}

async function refreshControl(){
  try{ renderControlCenter(await jsonFetch('/api/control-center')); }
  catch(error){ toast(`Centre de contrôle indisponible : ${error.message}`); }
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


function renderEvidence(data){
  const report=data.report||data||{};
  const gate=report.quality_gate||{};
  const counts=report.counts||{};
  const rates=report.rates||{};
  const funnel=report.funnel||{};
  const gates=report.gates||{};
  const labels={not_run:'Non exécutée',needs_recompute:'Recalcul requis',blocked:'Bloquée',passed:'OK',available:'Disponible',insufficient:'Insuffisante',not_evaluable:'Non évaluable',not_evaluated:'Non évaluée',technical_validation:'Validation technique',pipeline_validation:'Validation du pipeline',exploratory:'Exploratoire',preliminary:'Préliminaire',analysis_ready:'Prête pour analyse'};
  const labelStatus=value=>labels[value]||String(value||'Non évaluée').replaceAll('_',' ');
  const setText=(selector,value)=>{ const node=$(selector); if(node) node.textContent=value; };

  setText('#evidenceGate',labelStatus(gate.status));
  setText('#evidenceReason',gate.reason||report.next_action||data.required_next_step||'Aucun rapport historique publié.');
  setText('#evidenceCoverage',pct(rates.provider_return_coverage??rates.event_coverage));
  setText('#evidenceWinamax',pct(rates.winamax_coverage));
  setText('#evidenceCredits',report.consumed_credits??0);
  setText('#evidencePlan',report.plan_request_id?`Plan ${report.plan_request_id}`:(report.plan_id?`Plan ${report.plan_id}`:'Aucun plan exécuté.'));
  setText('#evidenceCounts',`${funnel.provider_returned_event_snapshots??counts.events_with_odds??0}/${funnel.completed_event_snapshots??counts.planned_events??0} cibles retournées · ${counts.accepted_rows??0} lignes acceptées`);
  setText('#evidenceWinamaxDetail',`${funnel.winamax_ready_event_snapshots??counts.winamax_events??0}/${funnel.planned_event_snapshots??counts.planned_events??0} cibles avec marché Winamax complet.`);

  const gateCards=[
    ['#evidenceIntegrity','#evidenceIntegrityReason',gates.technical_integrity],
    ['#evidenceMatching','#evidenceMatchingReason',gates.result_matching],
    ['#evidenceConsensus','#evidenceConsensusReason',gates.consensus],
    ['#evidenceStatistical','#evidenceStatisticalReason',gates.statistical_evidence],
  ];
  gateCards.forEach(([titleSelector,reasonSelector,item])=>{
    setText(titleSelector,labelStatus((item||{}).status));
    setText(reasonSelector,(item||{}).reason||'Non évalué sur ce rapport.');
  });

  const funnelRows=[
    ['Événements découverts',funnel.discovered_events??counts.discovered_events??0],
    ['Demandés par le lot',funnel.requested_events??counts.requested_events??0],
    ['Sélectionnés avec le budget',funnel.selected_events??counts.selected_events??counts.planned_events??0],
    ['Écartés par limite d’échantillon',funnel.not_selected_sample_limit??0],
    ['Écartés par plafond de crédits',funnel.not_selected_budget_limit??0],
    ['Requêtes planifiées',funnel.planned_requests??0],
    ['Requêtes terminées',funnel.completed_requests??0],
    ['Cibles événement/snapshot exécutées',funnel.completed_event_snapshots??0],
    ['Cibles retournées par le fournisseur',funnel.provider_returned_event_snapshots??0],
    ['Événements acceptés',funnel.accepted_events??counts.events_with_odds??0],
    ['Événements rapprochés avec confiance',funnel.reliably_matched_events??0],
    ['Cibles avec consensus',funnel.consensus_ready_event_snapshots??counts.consensus_events??0],
    ['Cibles avec Winamax',funnel.winamax_ready_event_snapshots??counts.winamax_events??0],
  ];
  const funnelNode=$('#evidenceFunnel');
  if(funnelNode){
    funnelNode.innerHTML=`<table class="market-table"><thead><tr><th>Étape</th><th>Nombre</th></tr></thead><tbody>${funnelRows.map(([label,value])=>`<tr><td>${esc(label)}</td><td>${esc(String(value??0))}</td></tr>`).join('')}</tbody></table>`;
  }

  const bookmakerRows=Array.isArray(report.bookmaker_coverage)?report.bookmaker_coverage:[];
  const bookmakerNode=$('#evidenceBookmakers');
  if(bookmakerNode){
    bookmakerNode.innerHTML=bookmakerRows.length?`<table class="market-table"><thead><tr><th>Bookmaker</th><th>Cibles demandées</th><th>Marchés complets</th><th>Absents/incomplets</th><th>Couverture</th></tr></thead><tbody>${bookmakerRows.map(row=>`<tr><td>${esc(row.bookmaker_key||'—')}</td><td>${esc(String(row.requested_event_snapshots??0))}</td><td>${esc(String(row.complete_event_snapshots??0))}</td><td>${esc(String(row.missing_or_incomplete_event_snapshots??0))}</td><td>${esc(pct(row.coverage))}</td></tr>`).join('')}</tbody></table>`:'<p>Aucune matrice bookmaker publiée.</p>';
  }

  const items=[];
  (report.blockers||[]).forEach(value=>items.push({kind:'blocked',label:'Blocage',value}));
  (report.warnings||[]).forEach(value=>items.push({kind:'attention',label:'Avertissement',value}));
  const outcomes=report.event_outcome_counts||{};
  Object.entries(outcomes).filter(([status])=>status!=='accepted').forEach(([status,count])=>items.push({kind:'attention',label:`Événements : ${count}`,value:status}));
  if(!items.length) items.push({kind:'passed',label:'Contrôle',value:report.generated_at?'Aucune anomalie bloquante détectée.':'Aucun rapport publié.'});
  const issuesNode=$('#evidenceIssues');
  if(issuesNode){
    issuesNode.innerHTML=items.map(item=>`<article class="gate-card ${esc(item.kind)}"><small>${esc(item.label)}</small><h3>${esc(String(item.value).replaceAll('_',' '))}</h3><p>${esc(report.next_action||'Les détails sont conservés dans l’artefact GitHub V4.2.')}</p></article>`).join('');
  }
}

function renderPreflight(data){
  const report=(data||{}).report||{};
  const labels={VIABLE:'Viable',RISKY:'À confirmer',NOT_VIABLE:'Non viable',NOT_RUN:'Non exécuté'};
  const setText=(selector,value)=>{ const node=$(selector); if(node) node.textContent=value; };
  setText('#preflightDecision',labels[report.decision]||String(report.decision||'Non exécuté').replaceAll('_',' '));
  setText('#preflightReason',report.reason||data.required_next_step||'Aucun préflight publié.');
  setText('#preflightCoverage',pct(report.baseline_coverage));
  setText('#preflightInterval',`Intervalle Wilson diagnostique : ${pct(report.baseline_coverage_ci95_low)} à ${pct(report.baseline_coverage_ci95_high)}.`);
  setText('#preflightRecommended',report.recommended_selected_events??'—');
  setText('#preflightCapacity',report.candidate_campaign_plan?`Plan candidat ${report.candidate_campaign_plan.candidate_plan_id}.`:'Aucune campagne payante autorisée.');
  setText('#preflightCredits',report.preflight_credits??0);
  setText('#preflightBudget',`Plafond préflight : ${report.maximum_preflight_credits??0} crédits.`);
}

function renderCampaign(data){
  const report=(data||{}).report||{};
  const gate=report.scale_gate||{};
  const budget=report.budget||{};
  const labels={not_run:'Non lancée',hold_and_fix_data_quality:'Corriger la qualité',eligible_for_next_stage_review:'Éligible à une revue'};
  const setText=(selector,value)=>{ const node=$(selector); if(node) node.textContent=value; };
  setText('#campaignDecision',labels[report.decision]||String(report.decision||'Non lancée').replaceAll('_',' '));
  setText('#campaignReason',gate.reason||data.required_next_step||'Aucun rapport de campagne publié.');
  setText('#campaignCompleted',report.completed_stage??0);
  setText('#campaignNext',report.next_stage??30);
  setText('#campaignGate',gate.accepted?'Porte qualité franchie ; revue humaine avant le prochain stage.':'La campagne reste bloquée tant que les contrôles qualité ne passent pas.');
  setText('#campaignBudget',budget.maximum_credits??0);
  setText('#campaignCredits',`${budget.observed_consumed_credits??0} crédits observés · aucune promotion automatique.`);
}

async function refreshEvidence(){
  try{
    const [evidence,preflight,campaign]=await Promise.all([jsonFetch('/api/evidence'),jsonFetch('/api/coverage-preflight'),jsonFetch('/api/evidence-campaign')]);
    renderEvidence(evidence);
    renderPreflight(preflight);
    renderCampaign(campaign);
  }
  catch(error){ toast(`Rapport de preuve indisponible : ${error.message}`); }
}

function renderDecision(data){
  const decision=(data||{}).decision||{};
  const status=decision.status||'not_evaluable';
  const labels={not_evaluable:'Non évaluable',continue_shadow:'Continuer le shadow',promotion_review:'Revue de promotion',no_go:'NO-GO'};
  $('#decisionStatus').textContent=labels[status]||status;
  $('#decisionReason').textContent=decision.reason||'Aucune décision disponible.';
  $('#decisionChampion').textContent=decision.champion||'—';
  $('#decisionHistorical').textContent=decision.historical_predictions??0;
  $('#decisionLive').textContent=decision.live_shadow_predictions??0;
  const leaderboard=decision.leaderboard||[];
  $('#decisionLeaderboard').innerHTML=leaderboard.length?`<div class="table-scroll"><table class="market-table decision-score-table"><thead><tr><th>Contender</th><th>N</th><th>Log-loss</th><th>Brier</th><th>RPS</th><th>ECE</th><th>Δ consensus</th><th>IC 95 %</th></tr></thead><tbody>${leaderboard.map(row=>{
    const finite=value=>Number.isFinite(Number(value));
    const fmt4=value=>finite(value)?Number(value).toFixed(4):'—';
    const ci=finite(row.ci95_low)&&finite(row.ci95_high)?`[${Number(row.ci95_low).toFixed(4)} ; ${Number(row.ci95_high).toFixed(4)}]`:'—';
    return `<tr><td><b>${esc(row.contender||'—')}</b></td><td>${row.evaluated_rows??0}</td><td>${fmt4(row.log_loss)}</td><td>${fmt4(row.brier)}</td><td>${fmt4(row.rps)}</td><td>${fmt4(row.ece)}</td><td>${fmt4(row.model_minus_consensus_log_loss)}</td><td>${ci}</td></tr>`;
  }).join('')}</tbody></table></div>`:'<p>Aucun contender évalué.</p>';
  const gates=decision.gates||{};
  $('#decisionGates').innerHTML=Object.entries(gates).map(([name,gate])=>`<article class="gate-card ${gate.passed?'passed':'blocked'}"><small>${gate.passed?'PASS':'BLOCK'}</small><h3>${esc(name.replaceAll('_',' '))}</h3><p>${esc(JSON.stringify(gate))}</p></article>`).join('')||'<p>Aucune porte évaluée.</p>';
}

async function refreshDecision(){
  try{ renderDecision(await jsonFetch('/api/model-decision')); }
  catch(error){ toast(`Décision modèle indisponible : ${error.message}`); }
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
  const todayAction=$('#todayAction');
  const todayCount=Number(summary.fixtures_today??summary.events_reviewed??0);
  const insufficient=Number(summary.cold_start_predictions??0);
  if(todayCount>0){
    todayAction.className=`action-card ${insufficient?'attention':''}`.trim();
    todayAction.innerHTML=`<small>À RETENIR</small><h3>${todayCount} match(s) analysé(s)</h3><p>${insufficient?`${insufficient} rencontre(s) avec données limitées. Les probabilités restent exploratoires.`:'Les données disponibles permettent une lecture modèle complète.'}</p>`;
  }else{
    todayAction.className='action-card attention';
    todayAction.innerHTML=`<small>À RETENIR</small><h3>Aucun match couvert aujourd’hui</h3><p>${Number(summary.upcoming_predictions??0)} prochain(s) match(s) restent disponibles dans le calendrier replié.</p>`;
  }
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

function dailyProbabilityRows(event){
  const p=event.probabilities||{};
  const labels=event.sport==='football'
    ? [['1',p.home],['N',p.draw],['2',p.away]]
    : [['J1',p.player_1],['J2',p.player_2]];
  return labels.filter(([,value])=>Number.isFinite(Number(value))).map(([label,value])=>`<div class="odds-line"><span>${label}</span><b>${pct(value)}</b></div>`).join('');
}

function dailyCard(event,{upcoming=false}={}){
  const reasons=(event.reasons||[]).map(x=>`<li>${esc(x)}</li>`).join('');
  const time=event.commence_time?new Date(event.commence_time).toLocaleString('fr-FR'):(event.date||'date inconnue');
  const diagnostic=event.probability_diagnostics||{};
  const coldStart=event.coverage_mode==='cold_start_league_priors';
  const badge=diagnostic.valid===false?'probabilités invalides':(coldStart?'cold-start':(event.decision||'probabilités seulement'));
  return `<article class="slate-card"><div class="slate-top"><span>${esc(event.sport||'football')} · ${esc(event.competition||'')}</span><b class="decision ${esc(badge)}">${esc(badge)}</b></div><h3>${esc(event.event)}</h3><p>${esc(time)} · modèle ${esc(event.model_version||'—')}</p>${dailyProbabilityRows(event)}<ul>${reasons}</ul><small>${event.winamax_odds?'Marché enrichi':'Modèle seul · 0 crédit'}${coldStart?' · confiance réduite':''}${upcoming?' · à venir':''}</small></article>`;
}

function renderModelDiagnostics(data){
  const status=data.status||'blocked';
  const statusLabels={operational_research:'Opérationnel recherche',degraded:'Dégradé',blocked:'Bloqué'};
  $('#dailyModelStatus').textContent=statusLabels[status]||status;
  const metrics=data.metrics||{};
  const freshness=data.freshness||{};
  $('#dailyModelDetail').textContent=`${data.model_version||'version inconnue'} · test ${metrics.n_test??'—'} · log-loss ${Number.isFinite(Number(metrics.log_loss))?Number(metrics.log_loss).toFixed(3):'—'} · âge ${freshness.age_days??'—'} j`;
}

function renderDaily(data){
  const summary=data.summary||{};
  $('#dailyCandidates').textContent=summary.model_predictions ?? 0;
  $('#dailyPredictionCount').textContent=summary.model_predictions ?? 0;
  $('#dailyPredictionDetail').textContent=`${summary.fixtures_today??summary.events_reviewed??0} match(s) aujourd’hui · ${summary.upcoming_predictions??0} à venir · ${summary.cold_start_predictions??0} cold-start`;
  $('#dailyShortlistCount').textContent=summary.research_candidates ?? 0;
  $('#dailyShortlistDetail').textContent=(summary.research_candidates??0)>0?'Signaux de recherche uniquement':'Aucune sélection de marché forcée';
  $('#dailyCredits').textContent=summary.credits_consumed ?? 0;
  const firewall=data.credit_firewall||{};
  $('#dailyCreditDetail').textContent=firewall.daily_odds_enabled?`Cotes autorisées · plafond ${firewall.daily_odds_max_credits??0}`:'Modèle seul · appels payants bloqués';
  const noShortlist=data.no_shortlist_reasons||[];
  $('#dailyNoShortlist').innerHTML=`<b>Pourquoi aucune shortlist :</b> ${noShortlist.length?noShortlist.map(esc).join(' · '):'Une shortlist éventuelle reste expérimentale et soumise aux cotes fraîches.'}`;
  const events=data.events||[];
  const visibleEvents=events.slice(0,MAX_VISIBLE_CARDS);
  $('#dailySlate').innerHTML=visibleEvents.map(event=>dailyCard(event)).join('') || `<div class="slate-card"><h3>Aucun match couvert aujourd’hui</h3><p>${esc(data.warning||'Le calendrier ne contient aucun match couvert à cette date.')}</p></div>`;
  const dailyHidden=Math.max(0,events.length-visibleEvents.length);
  $('#dailyOverflow').hidden=dailyHidden===0;
  $('#dailyOverflow').textContent=dailyHidden?`${dailyHidden} match(s) supplémentaire(s) masqué(s) pour éviter une page trop lourde.`:'';
  const upcoming=data.upcoming_events||[];
  const visibleUpcoming=upcoming.slice(0,MAX_VISIBLE_CARDS);
  $('#upcomingSlate').innerHTML=visibleUpcoming.map(event=>dailyCard(event,{upcoming:true})).join('') || '<div class="slate-card"><h3>Aucun prochain match couvert</h3><p>Le calendrier gratuit peut être hors saison, indisponible ou contenir des équipes encore inconnues du modèle.</p></div>';
  const upcomingHidden=Math.max(0,upcoming.length-visibleUpcoming.length);
  $('#upcomingOverflow').hidden=upcomingHidden===0;
  $('#upcomingOverflow').textContent=upcomingHidden?`${upcomingHidden} prochain(s) match(s) masqué(s).`:'';
  if(data.model_diagnostics) renderModelDiagnostics(data.model_diagnostics);
}


function researchSignalCard(signal){
  const eventTime=signal.commence_time?new Date(signal.commence_time).toLocaleString('fr-FR'):'horaire inconnu';
  const edge=Number(signal.edge);
  const robust=Number(signal.robust_expected_return);
  const odds=Number(signal.decimal_odds);
  const meta=signal.meta_probability===null||signal.meta_probability===undefined?'':`<div class="odds-line"><span>Probabilité méta-modèle</span><b>${pct(signal.meta_probability)}</b></div>`;
  const source=signal.policy_source==='chronological_roi_policy'?'politique candidate évaluée chronologiquement':'seuils pré-enregistrés';
  return `<article class="slate-card"><div class="slate-top"><span>${esc(signal.sport||'sport')} · shadow</span><b class="decision candidat recherche">signal expérimental</b></div><h3>${esc(signal.event||'Événement')}</h3><p>${esc(eventTime)}</p><div class="odds-line"><span>Sélection</span><b>${esc(signal.selection||'—')}</b></div><div class="odds-line"><span>Cote</span><b>${Number.isFinite(odds)?odds.toFixed(2):'—'}</b></div><div class="odds-line"><span>Probabilité modèle</span><b>${pct(signal.model_probability)}</b></div>${meta}<div class="odds-line"><span>Probabilité marché</span><b>${pct(signal.market_probability)}</b></div><div class="odds-line"><span>Edge retenu</span><b>${Number.isFinite(edge)?signed(edge):'—'}</b></div><div class="odds-line"><span>EV robuste</span><b>${Number.isFinite(robust)?signed(robust):'—'}</b></div><small>${esc(source)} · recherche uniquement · aucune instruction de mise</small></article>`;
}

function renderFilteredResearchSignals(){
  const filtered=RESEARCH_SIGNAL_FILTER==='all'?RESEARCH_SIGNALS:RESEARCH_SIGNALS.filter(signal=>signal.sport===RESEARCH_SIGNAL_FILTER);
  const visible=filtered.slice(0,MAX_VISIBLE_CARDS);
  $('#researchSignals').innerHTML=visible.map(researchSignalCard).join('')||'<div class="slate-card"><h3>Aucun signal dans ce filtre</h3><p>L’abstention est conservée lorsque le marché, le modèle ou l’échantillon ne passent pas les portes.</p></div>';
  const overflow=$('#signalOverflow');
  const hidden=Math.max(0,filtered.length-visible.length);
  overflow.hidden=hidden===0;
  overflow.textContent=hidden?`${hidden} signal(s) supplémentaire(s) masqué(s) pour garder la vue stable. Passe au mode expert pour le détail.`:'';
}

function reliabilityLabel(value){
  const labels={HIGH_CONFIDENCE_RESEARCH:'élevée',MEDIUM_CONFIDENCE_RESEARCH:'moyenne',LOW_CONFIDENCE_RESEARCH:'faible',INSUFFICIENT_EVIDENCE:'données insuffisantes'};
  return labels[value]||'collecte';
}

function renderFeatureLab(data={}){
  FEATURE_LAB_DATA=data;
  const sports=data.sports||{};
  const football=sports.football||{};
  const tennis=sports.tennis||{};
  const strip=$('#featureReliability');
  const fLabel=reliabilityLabel(football.reliability);
  const tLabel=reliabilityLabel(tennis.reliability);
  strip.innerHTML=`<b>Fiabilité des probabilités</b><span>Football : ${esc(fLabel)} · Tennis : ${esc(tLabel)}</span>`;
  strip.className=`confidence-strip ${data.overall_reliability==='high'?'reliability-high':data.overall_reliability==='medium'?'reliability-medium':'reliability-low'}`;
  const rows=[['Football',football],['Tennis',tennis]];
  $('#featureLabDetails').innerHTML=rows.map(([label,row])=>`<article class="gate-card ${row.status==='candidate'?'passed':'blocked'}"><small>${esc(row.status||'collecting')}</small><h3>${esc(label)} · ${esc(reliabilityLabel(row.reliability))}</h3><p>${row.events??0} événement(s) réglé(s) · calibrateur ${esc(row.selected_calibrator||'identity')}<br>${row.holdout?`log-loss ${Number(row.holdout.log_loss).toFixed(3)} · ECE ${Number(row.holdout.ece).toFixed(3)}`:esc(row.reason||'collecte en cours')}</p></article>`).join('');
}

function simpleModelState(row={}){
  const labels={candidate:'Amélioration possible',development_candidate:'Amélioration possible',development_review:'Revue de développement',hold:'Le nouveau modèle est moins bon',hold_explained:'Le nouveau modèle est moins bon',collecting:'Pas assez de données',not_run:'Non exécuté',review_required:'Prêt pour revue humaine'};
  return labels[row.status]||row.status||'Collecte';
}

function renderChallengerFactory(data={}){
  CHALLENGER_FACTORY_DATA=data;
  const sports=data.sports||{};
  const football=sports.football||{};
  const tennis=sports.tennis||{};
  $('#learningFootballState').textContent=simpleModelState(football);
  $('#learningFootballDetail').textContent=football.challenger_id?`${football.challenger_id} · holdout ${football.partitions?.holdout??'—'}`:(football.reason||'Challenger non évalué.');
  $('#learningTennisState').textContent=simpleModelState(tennis);
  $('#learningTennisDetail').textContent=tennis.challenger_id?`${tennis.challenger_id} · surfaces ${Object.keys(tennis.surface_holdout||{}).length}`:(tennis.reason||'Historique multi-surface requis.');
  const rows=[['Football',football],['Tennis',tennis]];
  $('#challengerFactoryDetails').innerHTML=rows.map(([label,row])=>`<article class="gate-card ${row.status==='candidate'?'passed':'blocked'}"><small>${esc(row.status||'not_run')}</small><h3>${esc(label)} · ${esc(row.model_type||'aucun challenger')}</h3><p>${row.dataset?`${row.dataset.rows??0} lignes · ${row.dataset.distinct_dates??0} dates · ${esc(String(row.dataset.dataset_sha256||'').slice(0,12))}`:esc(row.reason||'non exécuté')}<br>${row.challenger?.holdout?`log-loss ${Number(row.challenger.holdout.log_loss).toFixed(3)} · ECE ${Number(row.challenger.holdout.ece).toFixed(3)}`:esc(row.reason||'collecte')}</p></article>`).join('');
}

function renderEvidenceAcceleration(data={}){
  EVIDENCE_ACCELERATION_DATA=data;
  const football=data.football||{};
  const tennis=data.tennis||{};
  const catalog=tennis.catalog||{};
  const readiness=catalog.readiness||{};
  const fDelta=Number(football.overall?.delta_log_loss);
  if(football.status){
    $('#learningFootballState').textContent=football.status==='hold_explained'?'Champion conservé':simpleModelState(football);
    $('#learningFootballDetail').textContent=Number.isFinite(fDelta)?`Hold expliqué · écart log-loss ${fDelta>=0?'+':''}${fDelta.toFixed(3)}`:(football.reason||'Analyse football en cours.');
  }
  if(catalog.dataset_id||readiness.status){
    $('#learningTennisState').textContent=readiness.status==='challenger_ready'?'Prêt challenger':readiness.status==='exploratory_ready'?'Prêt exploration':'Données insuffisantes';
    $('#learningTennisDetail').textContent=`${catalog.rows??readiness.rows??0} matchs · ${catalog.distinct_dates??readiness.distinct_dates??0} dates · ${readiness.status||'collecting'}`;
  }
  const breakdowns=football.breakdowns||{};
  const weak=[];
  for(const [group,rows] of Object.entries(breakdowns)){
    for(const [name,row] of Object.entries(rows||{})) if(Number(row.delta_log_loss)>0.02) weak.push(`${group}: ${name}`);
  }
  const holdout=tennis.holdout_generation||{};
  $('#evidenceAccelerationDetails').innerHTML=`<article class="gate-card ${football.status==='hold_explained'?'blocked':'passed'}"><small>FOOTBALL</small><h3>${esc(football.status||'not_run')}</h3><p>${esc(football.reason||'Analyse non exécutée')}<br>${weak.length?`Faiblesses principales : ${esc(weak.slice(0,4).join(' · '))}`:'Aucun sous-groupe critique publié.'}</p></article><article class="gate-card ${readiness.challenger_ready?'passed':'blocked'}"><small>TENNIS</small><h3>${esc(readiness.status||'collecting')}</h3><p>${catalog.rows??0} lignes · ${catalog.distinct_dates??0} dates · holdout ${esc(holdout.status||'ouvert')}<br>Lineage ${readiness.lineage_complete?'complète':'encore partielle'}</p></article>`;
  const learningAction=$('#learningAction');
  if(readiness.status==='collecting'&&learningAction){
    learningAction.className='action-card attention';
    learningAction.innerHTML='<small>PROCHAINE ÉTAPE</small><h3>Continuer la collecte tennis</h3><p>Le football est diagnostiqué. Le blocage prioritaire reste le volume tennis réel, multi-date et multi-surface.</p>';
  }
}

function renderControlledDecision(data={}){
  const football=data.football||{};
  const tennis=data.tennis||{};
  const progress=tennis.progress||{};
  const production=data.production_validation||{};
  const challengers=football.challengers||[];
  const passed=challengers.filter(row=>row.status==='development_candidate').length;
  $('#learningFootballState').textContent=passed?`${passed} amélioration(s) possible(s)`:'Champion conservé';
  $('#learningFootballDetail').textContent=`${challengers.length} challenger(s) borné(s) · holdout futur ${football.promotion_holdout_generation?.status||'à collecter'}`;
  const actualRows=Number(progress.exploratory_rows?.actual||0);
  const requiredRows=Number(progress.exploratory_rows?.required||500);
  $('#learningTennisState').textContent=`${actualRows} / ${requiredRows} matchs`;
  $('#learningTennisDetail').textContent=tennis.training_status==='exploratory_allowed'?'Exploration autorisée, promotion toujours bloquée.':'Pas assez de données multi-date et multi-surface.';
  $('#learningProofState').textContent=production.status==='passed'?'Validée':'Non prouvée';
  $('#learningProofDetail').textContent=production.status==='passed'?'Sessions simple et expert réussies.':'Exécuter les deux scénarios publics de 30 minutes.';
  const productionSimple=production.simple?.status||'not_run';
  const productionExpert=production.expert?.status||'not_run';
  $('#controlledDecisionDetails').innerHTML=`<article class="gate-card ${football.status==='development_review'?'passed':'blocked'}"><small>FOOTBALL</small><h3>${esc(simpleModelState(football))}</h3><p>${challengers.length} challenger(s) testés · promotion ${football.promotion_ready?'possible':'bloquée'}<br>${esc(football.reason||'Aucune décision')}</p></article><article class="gate-card ${tennis.training_status==='exploratory_allowed'?'passed':'blocked'}"><small>TENNIS</small><h3>${actualRows} / ${requiredRows}</h3><p>${esc(tennis.training_status||'collecting')} · ${progress.exploratory_dates?.actual??0} / ${progress.exploratory_dates?.required??50} dates</p></article><article class="gate-card ${production.status==='passed'?'passed':'blocked'}"><small>PRODUCTION</small><h3>${esc(production.status||'not_proven')}</h3><p>Simple : ${esc(productionSimple)} · Expert : ${esc(productionExpert)}</p></article>`;
  const action=$('#learningAction');
  if(action){
    action.className=`action-card ${production.status==='passed'?'attention':'blocked'}`;
    action.innerHTML=`<small>PROCHAINE ÉTAPE</small><h3>${production.status==='passed'?'Continuer la collecte future':'Valider les sessions longues publiques'}</h3><p>${esc(data.next_action||'Aucune action publiée.')}</p>`;
  }
}

function renderLearning(learning={},automation={}){
  const candidate=learning.candidate||{};
  const champion=learning.champion||{};
  const sports=candidate.sport_event_counts||{};
  const events=Number(candidate.settled_events||0);
  const required=Number(learning.gates?.minimum_total_events?.required||100);
  const progress=required>0?Math.min(100,100*events/required):0;
  $('#learningProofState').textContent=`${events} / ${required}`;
  $('#learningProofDetail').textContent=learning.status==='review_required'?'Revue humaine requise.':learning.status==='hold'?'Le champion reste actif.':'Continuer la collecte shadow.';
  $('#learningCostState').textContent=`${automation.credits_consumed??0} crédit(s)`;
  $('#learningCostDetail').textContent=`Plafond ${automation.daily_credit_cap??0} · entraînement challenger 0 crédit.`;
  $('#learningEvents').textContent=events;
  $('#learningSports').textContent=`Football ${sports.football??0} · Tennis ${sports.tennis??0}`;
  $('#learningChampion').textContent=champion.id||'Aucun';
  $('#learningChallenger').textContent=learning.status||'collecting';
  $('#learningCandidate').textContent=candidate.candidate_id?`${candidate.candidate_id} · ${candidate.holdout_bets??0} signal(s) holdout`:'Candidat non évaluable.';
  $('#learningBudget').textContent=`${automation.credits_consumed??0} / ${automation.daily_credit_cap??0}`;
  $('#learningAutomation').textContent=automation.enabled?`${automation.due_events??0} résultat(s) à régler · ${automation.credits_remaining??0} crédit(s) restant(s)`:'Automatisation désactivée';
  $('#learningProgressBar').style.width=`${progress.toFixed(1)}%`;
  $('#learningProgressText').textContent=`${events} / ${required} événements pour la porte globale (${progress.toFixed(0)} %).`;
  const action=$('#learningAction');
  const title=learning.status==='review_required'?'Challenger prêt pour revue humaine':learning.status==='hold'?'Conserver le champion actuel':'Continuer la collecte shadow';
  action.className=`action-card ${learning.status==='hold'?'blocked':learning.status==='review_required'?'':'attention'}`.trim();
  action.innerHTML=`<small>PROCHAINE ÉTAPE</small><h3>${esc(title)}</h3><p>${esc(learning.next_action||automation.next_action||'Aucune action requise.')}</p>`;
  const gates=Object.entries(learning.gates||{});
  $('#learningGates').innerHTML=gates.map(([name,gate])=>`<article class="gate-card ${gate.passed?'passed':'blocked'}"><small>${gate.passed?'PASS':'HOLD'}</small><h3>${esc(name.replaceAll('_',' '))}</h3><p>Actuel : ${esc(typeof gate.actual==='object'?JSON.stringify(gate.actual):String(gate.actual??'—'))}<br>Requis : ${esc(typeof gate.required==='object'?JSON.stringify(gate.required):String(gate.required??'—'))}</p></article>`).join('')||'<p>Aucune porte publiée.</p>';
}

function renderResearchLab(data){
  const summary=data.summary||{};
  $('#researchFootballCount').textContent=summary.football_matches??0;
  $('#researchFootballDetail').textContent=`${data.football?.summary?.research_candidates??0} candidat(s) recherche dans le snapshot football`;
  $('#researchTennisCount').textContent=summary.tennis_matches??0;
  $('#researchTennisDetail').textContent=`${data.tennis?.tournaments?.length??0} tournoi(s) capturé(s)`;
  $('#researchSignalCount').textContent=summary.experimental_signals??0;
  $('#researchSignalDetail').textContent=(summary.experimental_signals??0)>0?'Signaux shadow, non exécutables':'Aucun edge robuste retenu';
  const automation=data.automation||{};
  $('#researchCredits').textContent=automation.credits_consumed??summary.credits_consumed??0;
  const run=data.run||{};
  $('#researchRunDetail').textContent=run.id?`Run #${run.id} · ${run.status||'—'} · plafond ${automation.daily_credit_cap??0}`:'Aucune capture marché persistée';
  const signals=data.signals||[];
  RESEARCH_SIGNALS=signals;
  renderFilteredResearchSignals();
  const action=$('#researchAction');
  if((summary.experimental_signals??0)>0){
    action.className='action-card';
    action.innerHTML=`<small>ACTION DU JOUR</small><h3>${summary.experimental_signals} signal(s) expérimental(aux) à examiner</h3><p>Simulation uniquement : vérifier le sport, la fraîcheur du marché et la raison du signal.</p>`;
  }else if((summary.football_matches??0)+(summary.tennis_matches??0)>0){
    action.className='action-card attention';
    action.innerHTML='<small>ACTION DU JOUR</small><h3>Conserver l’abstention</h3><p>Des matchs ont été analysés, mais aucun edge robuste ne passe les portes actuelles.</p>';
  }else{
    action.className='action-card attention';
    action.innerHTML='<small>ACTION DU JOUR</small><h3>Aucun snapshot marché récent</h3><p>Le produit modèle seul continue de fonctionner. Ne dépense pas de crédit juste pour remplir l’écran.</p>';
  }

  const simulations=data.roi_lab?.simulations||[];
  const simulationRows=simulations.map(row=>`<tr><td>${Number(row.starting_bankroll).toFixed(0)}</td><td>${esc(row.strategy)}</td><td>${row.bets??0}</td><td>${Number(row.ending_bankroll).toFixed(2)}</td><td>${Number(row.profit).toFixed(2)}</td><td>${row.roi_on_turnover===null?'—':pct(row.roi_on_turnover)}</td><td>${pct(row.maximum_drawdown)}</td></tr>`).join('');
  $('#researchBankrolls').innerHTML=simulationRows?`<table class="market-table"><thead><tr><th>Bankroll</th><th>Stratégie simulée</th><th>Signaux simulés</th><th>Finale</th><th>Profit</th><th>ROI turnover</th><th>Drawdown max</th></tr></thead><tbody>${simulationRows}</tbody></table>`:'<p>Aucun résultat réglé : la simulation ne peut pas encore être évaluée.</p>';

  const optimisation=data.roi_lab?.optimisation||{};
  const meta=data.roi_lab?.meta_model||{};
  const policy=optimisation.policy||{};
  const holdout=optimisation.holdout||{};
  const status=optimisation.status||'not_evaluable';
  const metaHoldout=meta.holdout||{};
  $('#researchTraining').innerHTML=`<article class="gate-card"><small>STATUT POLITIQUE</small><h3>${esc(status)}</h3><p>${esc(optimisation.reason||'aucune optimisation')}</p></article><article class="gate-card"><small>ÉCHANTILLON</small><h3>${optimisation.settled_events??0}</h3><p>Événements marché réglés · politique min. 30 · méta-modèle min. 60</p></article><article class="gate-card"><small>POLITIQUE</small><h3>edge ${pct(policy.minimum_edge)}</h3><p>EV robuste ${pct(policy.minimum_robust_return)} · cote max ${policy.maximum_decimal_odds??'—'} · ${policy.maximum_bets_per_day??'—'} signal(s)/jour</p></article><article class="gate-card"><small>HOLDOUT ROI</small><h3>${holdout.bets??0} signal(s)</h3><p>ROI ${holdout.roi_on_turnover===null||holdout.roi_on_turnover===undefined?'—':pct(holdout.roi_on_turnover)} · drawdown ${holdout.maximum_drawdown===undefined?'—':pct(holdout.maximum_drawdown)}</p></article><article class="gate-card"><small>MÉTA-MODÈLE</small><h3>${esc(meta.status||'not_evaluable')}</h3><p>${metaHoldout.log_loss===undefined?'Pas assez de données':`log-loss holdout ${Number(metaHoldout.log_loss).toFixed(3)} · Brier ${Number(metaHoldout.brier).toFixed(3)}`}</p></article>`;
  renderLearning(data.learning||{},data.automation||{});
}

async function refreshResearchLab(){
  return withBusy('#refreshResearchLab',async()=>{
    try{
      const [research,challenger,evidenceAcceleration,controlled]=await Promise.all([jsonFetch('/api/research-lab',{noDedupe:true}),jsonFetch('/api/challenger-factory',{noDedupe:true}),jsonFetch('/api/evidence-acceleration',{noDedupe:true}),jsonFetch('/api/controlled-model-decision',{noDedupe:true})]);
      renderResearchLab(research); renderChallengerFactory(challenger); renderEvidenceAcceleration(evidenceAcceleration); renderControlledDecision(controlled);
    }catch(error){ toast(`Laboratoire indisponible : ${error.message}`); }
  });
}

async function loadExpertData(){
  if(EXPERT_DATA_LOADED) return;
  if(EXPERT_DATA_PROMISE) return EXPERT_DATA_PROMISE;
  EXPERT_DATA_PROMISE=(async()=>{
    const controlTask=refreshControl();
    const requests={
      audit:jsonFetch('/api/metrics'),
      provider:jsonFetch('/api/odds/status'),
      history:jsonFetch('/api/history/predictions?limit=20'),
      benchmark:jsonFetch('/api/benchmark/summary'),
      evidence:jsonFetch('/api/evidence'),
      preflight:jsonFetch('/api/coverage-preflight'),
      campaign:jsonFetch('/api/evidence-campaign'),
      decision:jsonFetch('/api/model-decision'),
      shadow:jsonFetch('/api/shadow/summary'),
      shadowHistory:jsonFetch('/api/shadow/predictions?limit=20'),
      system:jsonFetch('/api/system/status'),
    };
    const keys=Object.keys(requests);
    const settled=await Promise.allSettled(Object.values(requests));
    const loaded={}; const failed=[];
    settled.forEach((result,index)=>{
      if(result.status==='fulfilled') loaded[keys[index]]=result.value;
      else failed.push(keys[index]);
    });
    if(loaded.audit) $('#metrics').textContent=JSON.stringify(loaded.audit,null,2);
    if(loaded.provider) renderProviderStatus(loaded.provider);
    if(loaded.history) renderHistory(loaded.history);
    if(loaded.benchmark) renderBenchmark(loaded.benchmark);
    if(loaded.evidence) renderEvidence(loaded.evidence);
    if(loaded.preflight) renderPreflight(loaded.preflight);
    if(loaded.campaign) renderCampaign(loaded.campaign);
    if(loaded.decision) renderDecision(loaded.decision);
    if(loaded.shadow&&loaded.shadowHistory) renderShadow(loaded.shadow,loaded.shadowHistory);
    if(loaded.system) renderSystem(loaded.system);
    await controlTask;
    const paidOddsAvailable=Boolean(loaded.provider?.configured&&loaded.provider?.paid_calls_enabled);
    $('#loadLiveOdds').disabled=!paidOddsAvailable;
    $('#loadTennisOdds').disabled=!paidOddsAvailable;
    if(!paidOddsAvailable){
      $('#liveOddsResult').innerHTML='<div class="slate-card"><h3>Cotes payantes suspendues</h3><p>Le produit quotidien modèle seul reste disponible sans consommer de crédit.</p></div>';
    }else{
      try{ const tennis=await jsonFetch('/api/odds/sports?group=Tennis'); const active=tennis.sports.filter(x=>x.active); $('#oddsTennisSport').innerHTML=active.map(x=>`<option value="${esc(x.key)}">${esc(x.title)} · ${esc(x.key)}</option>`).join('') || '<option value="">Aucun tournoi actif</option>'; }catch{ failed.push('tennisSports'); }
    }
    if(failed.length) toast(`Mode expert partiel : ${failed.length} bloc(s) indisponible(s). Un nouvel essai sera possible.`);
    EXPERT_DATA_LOADED=failed.length===0;
  })();
  try{ await EXPERT_DATA_PROMISE; }
  finally{ EXPERT_DATA_PROMISE=null; }
}

async function init(){
  applyInterfaceMode(currentInterfaceMode(),{load:false});
  applySimplePanel(currentSimplePanel());
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

    const primary=await Promise.allSettled([
      jsonFetch('/api/daily/slate'),
      jsonFetch('/api/research-lab'),
      jsonFetch('/api/model-diagnostics'),
      jsonFetch('/api/feature-lab'),
      jsonFetch('/api/challenger-factory'),
      jsonFetch('/api/evidence-acceleration'),
      jsonFetch('/api/controlled-model-decision'),
    ]);
    if(primary[0].status==='fulfilled') renderDaily(primary[0].value); else toast(`daily : ${primary[0].reason?.message||'chargement impossible'}`);
    if(primary[1].status==='fulfilled') renderResearchLab(primary[1].value); else toast(`research : ${primary[1].reason?.message||'chargement impossible'}`);
    if(primary[2].status==='fulfilled') renderModelDiagnostics(primary[2].value);
    if(primary[3].status==='fulfilled') renderFeatureLab(primary[3].value);
    if(primary[4].status==='fulfilled') renderChallengerFactory(primary[4].value);
    if(primary[5].status==='fulfilled') renderEvidenceAcceleration(primary[5].value);
    if(primary[6].status==='fulfilled') renderControlledDecision(primary[6].value);
    if(currentInterfaceMode()==='expert') await loadExpertData();
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
$('#refreshControl').addEventListener('click',refreshControl);
$('#refreshDecision').addEventListener('click',refreshDecision);
$('#logoutButton').addEventListener('click',async()=>{
  try{ await jsonFetch('/api/auth/logout',{method:'POST'}); window.location.assign('/login'); }catch(error){ toast(error.message); }
});

$('#refreshResearchLab').addEventListener('click',refreshResearchLab);
$('#interfaceMode').addEventListener('click',()=>{ const next=currentInterfaceMode()==='expert'?'simple':'expert'; applyInterfaceMode(next); if(next==='simple') applySimplePanel(currentSimplePanel()); });
(document.querySelectorAll?.('[data-simple-target]')||[]).forEach(link=>link.addEventListener('click',event=>{ if(currentInterfaceMode()==='simple'){ event.preventDefault(); applySimplePanel(link.dataset.simpleTarget,{scroll:true}); } }));
(document.querySelectorAll?.('.signal-filter')||[]).forEach(button=>button.addEventListener('click',()=>{
  RESEARCH_SIGNAL_FILTER=button.dataset.sport||'all';
  (document.querySelectorAll?.('.signal-filter')||[]).forEach(item=>item.classList.toggle('active',item===button));
  renderFilteredResearchSignals();
}));

window.addEventListener?.('pagehide',()=>{ ACTIVE_REQUESTS.forEach(controller=>controller.abort?.()); ACTIVE_REQUESTS.clear(); INFLIGHT_GETS.clear(); });

init();

$('#refreshEvidence')?.addEventListener('click',refreshEvidence);
