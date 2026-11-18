import {heading} from '../components/common/header.js';
import {esc,fmt,time} from '../utils/format.js';
import {TRIAL_STATUSES,TRIAL_DECISIONS} from '../constants/enums.js';

const pct=v=>v===null||v===undefined?'—':(v*100).toFixed(2)+'%';
const alpha=v=>v===null||v===undefined?'—':Number(v).toPrecision(4);
const quota=v=>v===null||v===undefined?'—':(Math.round(Number(v)*1e8)/1e8).toString();
const pvalue=v=>v===null||v===undefined?'—':(Number(v)<1e-4?Number(v).toExponential(2):Number(v).toFixed(4));
const stages=['pending','running','stopped'];
const stageLabel={pending:'待开试',running:'进行中',stopped:'已停止'};
const stageOrder={pending:0,running:1,stopped:2};

function pipeline(t){
 if(t.status==='cancelled'){
  return `<ol class="trial-pipeline"><li class="off"><span>待开试</span></li><li class="off"><span>进行中</span></li><li class="off"><span>已停止</span></li><li class="current cancelled"><span>已取消（额度不返还）</span></li></ol>`;
 }
 const index=stageOrder[t.status]??0;
 return `<ol class="trial-pipeline">${stages.map((s,i)=>`<li class="${i<index?'done':i===index?'current':'off'}"><span>${stageLabel[s]}</span></li>`).join('')}</ol>`;
}

function ledgerRows(processes){
 if(!processes.length)return '<p class="empty">尚无工艺登记。开试前先登记工艺与总误报上限；额度一旦登记不可改写。</p>';
 return '<div class="table-wrap"><table><thead><tr><th>工艺</th><th>总误报上限</th><th>已登记预留</th><th>进行中预留</th><th>剩余可登记额度</th><th>试验数</th></tr></thead><tbody>'+processes.map(p=>`<tr><td>${esc(p.name)}</td><td>${quota(p.alpha_cap)}</td><td>${quota(p.allocated)}</td><td>${quota(p.active)}</td><td><b>${quota(p.remaining)}</b></td><td>${p.trial_count}</td></tr>`).join('')+'</tbody></table></div>';
}

function trialCard(t,selected){
 const status=TRIAL_STATUSES[t.status]||esc(t.status);
 const decision=TRIAL_DECISIONS[t.decision]||esc(t.decision);
 const evidence=Number(t.evidence||0);
 return `<article class="trial-card ${t.id===selected?'active':''}">
  <header><div><span class="trial-status ${esc(t.status)}">${status}</span><span class="trial-decision">${decision}</span></div><button class="select-trial" data-id="${t.id}">查看</button></header>
  <h3>${esc(t.name)}</h3>
  <p class="trial-meta">工艺 ${esc(t.process)} · 对照 ${esc(t.control_line)} → 试验 ${esc(t.experiment_line)} · 口径 ${esc(t.policy_version)}</p>
  <div class="trial-meters">
   <div><small>对照良率</small><strong>${pct(t.control_rate)}</strong></div>
   <div><small>试验良率</small><strong>${pct(t.experiment_rate)}</strong></div>
   <div><small>证据强度</small><strong>${pct(evidence)}</strong><span class="meter"><i style="width:${(evidence*100).toFixed(1)}%"></i></span></div>
   <div><small>本试验预留额度</small><strong>${quota(t.alpha_reserved)}</strong></div>
  </div>
  <p class="trial-foot">批次 ${t.batch_count} · 查看 ${t.look_count} 次 · 工艺剩余额度 ${quota(t.process_remaining)}${t.stop_reason?' · '+esc(t.stop_reason):''}</p>
 </article>`;
}

function trialDetail(detail){
 if(!detail)return '<p class="empty">选择一项试验查看批次、查看历史与证据强度。</p>';
 const t=detail.trial||detail;
 const looks=t.looks||[];
 const batches=t.batches||[];
 return `<section class="report trial-detail">
  <div class="report-top"><div><span class="trial-status ${esc(t.status)}">${TRIAL_STATUSES[t.status]||esc(t.status)}</span><h2>${esc(t.name)}</h2></div><strong class="trial-decision">${TRIAL_DECISIONS[t.decision]||esc(t.decision)}</strong></div>
  ${pipeline(t)}
  <p>工艺 ${esc(t.process)} · 对照线 ${esc(t.control_line)} · 试验线 ${esc(t.experiment_line)} · 冻结口径 ${esc(t.policy_version)} · 期间 ${esc(t.period||'全部')}</p>
  <div class="metrics">
   <div><small>对照良率</small><strong>${pct(t.control_rate)}</strong></div>
   <div><small>试验良率</small><strong>${pct(t.experiment_rate)}</strong></div>
   <div><small>证据强度</small><strong>${pct(t.evidence)}</strong></div>
   <div><small>本试验预留额度</small><strong>${quota(t.alpha_reserved)}</strong></div>
   <div><small>工艺剩余可登记额度</small><strong>${quota(t.process_remaining)}</strong></div>
   <div><small>累计批次 / 查看</small><strong>${t.batch_count} / ${t.look_count}</strong></div>
  </div>
  <p class="method">以完整批次为观察单位（同一日期+班次对照线与试验线均有有效记录）。每次纳入新批次即一次序贯查看；mSPRT 单侧检验，预登记先验尺度 τ=${t.tau}。随时查看与提前停试都不会放大误报概率，同一工艺多项并行试验的误报总概率仍受登记上限约束。额度在登记时即占用，取消或重开不返还。</p>
  <h3>查看历史</h3>
  ${looks.length?`<div class="table-wrap"><table><thead><tr><th>查看</th><th>新增批次</th><th>累计批次</th><th>对照良率</th><th>试验良率</th><th>z</th><th>p</th><th>证据强度</th><th>本试验额度</th><th>判定</th><th>时间</th></tr></thead><tbody>${looks.map(l=>`<tr><td>${l.look_index}</td><td>${l.batches_added}</td><td>${l.batch_total}</td><td>${pct(l.control_rate)}</td><td>${pct(l.experiment_rate)}</td><td>${fmt(l.z)}</td><td>${pvalue(l.p_value)}</td><td>${pct(l.evidence)}</td><td>${quota(l.nominal_alpha)}</td><td>${TRIAL_DECISIONS[l.decision]||esc(l.decision)}</td><td>${time(l.created)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="empty">尚无查看记录。开试后纳入完整批次即产生第一次查看。</p>'}
  <h3>已纳入批次（保留纳入时原值）</h3>
  ${batches.length?`<div class="table-wrap"><table><thead><tr><th>批次</th><th>查看</th><th>对照投入</th><th>对照分母</th><th>对照良率</th><th>试验投入</th><th>试验分母</th><th>试验良率</th></tr></thead><tbody>${batches.map(b=>`<tr><td>${esc(b.batch_key)}</td><td>${b.look_index}</td><td>${b.control_input}</td><td>${b.control_den}</td><td>${pct(b.control_rate)}</td><td>${b.experiment_input}</td><td>${b.experiment_den}</td><td>${pct(b.experiment_rate)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="empty">尚未纳入批次。</p>'}
 </section>`;
}

export function trials(c,d,selected,detail,role){
 const canWrite=role!=='viewer';
 const processes=d.processes||[], items=d.trials||[];
 const chosen=detail||items.find(x=>x.id===selected)||items[0]||null;
 const policies=d.policies||[];
 return heading('CONTINUOUS CONTROL / 07','连续对照试验','开试前登记对照线、试验线、冻结口径与总误报上限；以完整批次为观察单位，随时查看与提前停试都不放大误报概率。')
  +(canWrite?`<form id="process-form" class="inline-form"><label>工艺名称<input name="process" value="涂布工序" required></label><label>工艺总误报上限（0–1）<input name="alpha_cap" type="number" step="0.000001" min="0.000001" max="1" value="0.05" required></label><button>登记工艺额度</button></form>`:'<p class="method">业务阅读者只读：可查看额度账本、批次与证据强度，不能登记或推进试验。</p>')
  +'<h2>工艺额度账本</h2>'+ledgerRows(processes)
  +(canWrite?`<form id="trial-form" class="inline-form"><label>试验名称<input name="name" value="十一月涂布对照" required></label><label>所属工艺<select name="process">${processes.map(p=>`<option value="${esc(p.name)}">${esc(p.name)}（剩 ${quota(p.remaining)}）</option>`).join('')}</select></label><label>对照线<input name="control_line" value="试制线A" required></label><label>试验线<input name="experiment_line" value="试制线B" required></label><label>冻结口径<select name="policy_id">${policies.map(p=>`<option value="${p.id}">${esc(p.version)}</option>`).join('')}</select></label><label>期间<select name="period"><option>全部</option>${(d.periods||[]).map(p=>`<option>${esc(p.name)}</option>`).join('')}</select></label><label>本试验预留额度（0–1）<input name="alpha" type="number" step="0.000001" min="0.000001" max="1" value="0.02" required></label><button>登记试验</button></form>`:'')
  +`<div class="trial-layout"><aside class="trial-list">${items.length?items.map(t=>trialCard(t,chosen?.id)).join(''):'<p class="empty">尚无试验。先登记工艺额度，再登记对照线、试验线、口径与预留额度。</p>'}</aside><div>${trialDetail(chosen)}${chosen&&canWrite?`<div class="report-actions trial-actions">
    <button class="trial-start" data-id="${chosen.id}" ${chosen.status==='pending'?'':'disabled'}>开试</button>
    <button class="trial-advance" data-id="${chosen.id}" ${chosen.status==='running'?'':'disabled'}>纳入新完整批次并查看</button>
    <form id="stop-form" data-id="${chosen.id}"><label>提前停试说明<input name="reason" placeholder="随时停试；预留额度不返还" maxlength="200"></label><button ${chosen.status==='running'?'':'disabled'}>提前停试</button></form>
    <button class="trial-cancel" data-id="${chosen.id}" ${['stopped','cancelled'].includes(chosen.status)?'disabled':''}>取消试验</button>
    <button class="trial-reopen" data-id="${chosen.id}" ${['stopped','cancelled'].includes(chosen.status)?'':'disabled'}>重开（沿用原额度）</button>
  </div>`:''}</div></div>`;
}
