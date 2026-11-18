import math
import time

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.models.source import Policy, Source
from src.models.trial import Trial, TrialLook, TrialObservation, TrialProcess
from src.services.audit import log
from src.services.validation import validate_policy, validate_source

# 预登记的混合先验尺度（mSPRT）。按约 5 个百分点的良率改善量级设定，与样本量无关。
# 单侧 mSPRT 的似然比在任意停时都是非负鞅，因此每纳入一个完整批次查看一次、随时查看、
# 提前停试都不会放大误报率；同一工艺多项并行试验再用并集界，总误报 ≤ Σ各试验预留额度。
MIX_TAU = 0.05
MIN_TRIAL_ALPHA = 1e-6
MAX_PROCESS_CAP = 0.5
MAX_TRIAL_ALPHA = 0.5
_EPS = 1e-9


def _text(value, label, maximum=120):
    if not isinstance(value, str) or not (1 <= len(value.strip()) <= maximum):
        raise ValueError(f'{label}不能为空且不超过{maximum}字')
    return value.strip()


def _alpha(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'{label}必须是大于0的有限数值')
    if value > MAX_PROCESS_CAP:
        raise ValueError(f'{label}不能超过{MAX_PROCESS_CAP}')
    return float(value)


def _process(db, name):
    process = db.query(TrialProcess).filter_by(name=name).first()
    if not process:
        raise HTTPException(422, f'工艺“{name}”尚未登记总误报上限，请先登记后再开试')
    return process


def process_ledger(db, process):
    """额度账本：登记即占用，取消或重开都不返还已用额度。remaining 为尚可登记的额度。"""
    cap = float(process.alpha_cap or 0)
    trials = db.query(Trial.alpha, Trial.status).filter(Trial.process_id == process.id).all()
    allocated = sum(float(x.alpha or 0) for x in trials)
    active = sum(float(x.alpha or 0) for x in trials if x.status in ('pending', 'running'))
    return {'id': process.id, 'name': process.name, 'alpha_cap': cap, 'allocated': allocated,
            'active': active, 'remaining': max(0.0, cap - allocated), 'trial_count': len(trials)}


def list_processes(db):
    return [process_ledger(db, x) for x in db.query(TrialProcess).order_by(TrialProcess.id).all()]


def create_process(db, actor, body):
    name = _text(body.process, '工艺名称')
    cap = _alpha(body.alpha_cap, '工艺总误报上限')
    if db.query(TrialProcess).filter_by(name=name).first():
        raise HTTPException(409, '该工艺已登记总误报上限，额度不可改写；如需扩大范围请另立工艺')
    obj = TrialProcess(name=name, alpha_cap=cap, created=time.time())
    db.add(obj)
    try:
        log(db, actor, 'trial.process', f'{name} 总误报上限={cap}')
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '该工艺已登记总误报上限，额度不可改写；如需扩大范围请另立工艺')
    return process_ledger(db, obj)


def _trial(body, policy, alpha):
    return Trial(name=_text(body.name, '试验名称'), control_line=_text(body.control_line, '对照线', 100),
                 experiment_line=_text(body.experiment_line, '试验线', 100), policy_id=policy.id,
                 policy_version=policy.version, policy_snapshot=policy.data,
                 period=(body.period or '全部').strip() or '全部', alpha=alpha,
                 status='pending', decision='pending', look_count=0,
                 batch_count=0, control_batches=0, experiment_batches=0, control_num=0, control_den=0,
                 experiment_num=0, experiment_den=0, skipped_batches=0, evidence=0.0,
                 created=time.time(), updated=time.time(), version=0)


def create_trial(db, actor, body):
    process_name = _text(body.process, '工艺名称')
    # 先按下标锁定工艺，避免两项并行登记各自看到旧账本而合计越界。
    db.query(TrialProcess).filter_by(name=process_name).with_for_update().first()
    process = _process(db, process_name)
    policy = db.get(Policy, body.policy_id)
    if not policy:
        raise HTTPException(404, '口径版本不存在')
    validate_policy(policy.data)
    alpha = _alpha(body.alpha, '本试验预留误报额度')
    if alpha < MIN_TRIAL_ALPHA:
        raise ValueError(f'本试验预留误报额度不得低于{MIN_TRIAL_ALPHA}')
    if alpha > MAX_TRIAL_ALPHA:
        raise ValueError(f'本试验预留误报额度不能超过{MAX_TRIAL_ALPHA}')
    obj = _trial(body, policy, alpha)
    if obj.control_line == obj.experiment_line:
        raise ValueError('对照线与试验线必须不同')
    ledger = process_ledger(db, process)
    if alpha > ledger['remaining'] + _EPS:
        raise HTTPException(422, f'越界试验拒绝启动：预留{alpha:g}超出工艺剩余额度{ledger["remaining"]:.6g}')
    if db.query(Trial).filter_by(process_id=process.id, name=obj.name).first():
        raise HTTPException(409, '同一工艺下试验名称不可重复')
    obj.process_id = process.id
    obj.process = process.name
    db.add(obj)
    try:
        log(db, actor, 'trial.register',
            f'{obj.name} / {process.name} / {obj.control_line}→{obj.experiment_line} / '
            f'口径{policy.version} / 预留{alpha:g}')
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '同一工艺下试验名称不可重复')
    return trial_payload(db, obj)


def arm_numbers(record, policy):
    num = record['first_pass'] if policy['numerator'] == 'first_pass' else record['first_pass'] + record['reworked_good']
    den = record['input'] if policy['denominator'] == 'input' else record['input'] - record['scrap']
    return int(num), int(den)


def evidence_stats(control_num, control_den, experiment_num, experiment_den, alpha, tau=MIX_TAU):
    stats = {'control_rate': None, 'experiment_rate': None, 'diff': None, 'z': 0.0,
             'p_value': 1.0, 'evidence': 0.0, 'decision': 'continue'}
    if control_den <= 0 or experiment_den <= 0:
        return stats
    pc = control_num / control_den
    pe = experiment_num / experiment_den
    variance = pc * (1 - pc) / control_den + pe * (1 - pe) / experiment_den
    stats.update({'control_rate': pc, 'experiment_rate': pe, 'diff': pe - pc})
    if variance <= 0:
        return stats
    z = (pe - pc) / math.sqrt(variance)
    stats['z'] = z
    # 只对“试验线更优”做上限检验；试验线更差时证据强度保持 0，不触发停试。
    if z <= 0:
        return stats
    t2 = tau * tau
    log_lambda = 0.5 * math.log(variance / (variance + t2)) + t2 * z * z / (2 * (variance + t2))
    lam = math.exp(min(log_lambda, 700.0))
    p_value = min(1.0, 1.0 / lam) if lam > 0 else 0.0
    stats['p_value'] = p_value
    stats['evidence'] = 1.0 - p_value
    if p_value <= alpha:
        stats['decision'] = 'efficacy'
    return stats


def complete_batches(db, trial):
    """以完整批次为观察单位：同一日期+班次且对照线、试验线都有有效记录才成批。"""
    grouped, invalid = {}, []
    for source in db.query(Source).order_by(Source.id).all():
        data = source.data
        if trial.period != '全部' and data.get('period') != trial.period:
            continue
        line = data.get('department')
        if line not in (trial.control_line, trial.experiment_line):
            continue
        try:
            validate_source(data)
        except ValueError:
            invalid.append(source.id)
            continue
        key = (data['period'], data['shift'])
        arm = 'control' if line == trial.control_line else 'experiment'
        grouped.setdefault(key, {'control': [], 'experiment': []})[arm].append((source.id, data))
    complete, incomplete = {}, []
    for key in sorted(grouped, key=lambda x: (str(x[0]), str(x[1]))):
        arms = grouped[key]
        if arms['control'] and arms['experiment']:
            complete[key] = arms
        else:
            incomplete.append(f'{key[0]}|{key[1]}')
    incomplete.extend(f'底稿#{i}(字段不合法)' for i in invalid)
    return complete, incomplete


def _aggregate(records, policy):
    total_input = total_num = total_den = 0
    snapshot = []
    for source_id, data in records:
        num, den = arm_numbers(data, policy)
        total_input += int(data['input'])
        total_num += num
        total_den += den
        snapshot.append(dict(data, source_id=source_id))
    return total_input, total_num, total_den, snapshot


def _pending_batches(db, trial, complete, taken, sampled, look_index):
    """批次按周期+班次去重，且同一条底稿记录至多采样一次。

    已纳入批次的聚合值随批次冻结，底稿后续更正不会回写；即使更正把记录挪到新的批次键下，
    该记录也不会被再次采样，只由真正新增的底稿构成后续新批次继续分析。
    """
    fresh, skipped = [], []
    for (period, shift), arms in complete.items():
        batch_key = f'{period}|{shift}'
        if batch_key in taken:
            continue
        control = [(sid, data) for sid, data in arms['control'] if sid not in sampled]
        experiment = [(sid, data) for sid, data in arms['experiment'] if sid not in sampled]
        if not control or not experiment:
            skipped.append(batch_key)
            continue
        c_input, c_num, c_den, c_snapshot = _aggregate(control, trial.policy_snapshot)
        e_input, e_num, e_den, e_snapshot = _aggregate(experiment, trial.policy_snapshot)
        if c_den <= 0 or e_den <= 0:
            skipped.append(batch_key)
            continue
        fresh.append(TrialObservation(trial_id=trial.id, batch_key=batch_key, period=period, shift=shift,
                                      control_input=c_input, control_num=c_num, control_den=c_den,
                                      experiment_input=e_input, experiment_num=e_num, experiment_den=e_den,
                                      control_snapshot=c_snapshot, experiment_snapshot=e_snapshot,
                                      look_index=look_index, created=time.time()))
    return fresh, skipped


def _totals(db, trial):
    observations = db.query(TrialObservation).filter_by(trial_id=trial.id).all()
    return {
        'batch_count': len(observations),
        'control_batches': sum(1 for x in observations if x.control_den > 0),
        'experiment_batches': sum(1 for x in observations if x.experiment_den > 0),
        'control_num': sum(int(x.control_num) for x in observations),
        'control_den': sum(int(x.control_den) for x in observations),
        'experiment_num': sum(int(x.experiment_num) for x in observations),
        'experiment_den': sum(int(x.experiment_den) for x in observations),
    }


def advance_trial(db, actor, trial_id):
    """纳入新完整批次并做一次序贯查看（幂等）。

    已完成批次有 (trial_id, batch_key) 唯一约束，重试不会重复采样；事务内 SELECT ... FOR UPDATE
    加版本号，使两名执行者抢同一试验时只推进一次。计算中断后回滚，重试从数据库现有批次继续。
    """
    for _ in range(3):
        trial = db.query(Trial).filter_by(id=trial_id).with_for_update().first()
        if not trial:
            raise HTTPException(404, '试验不存在')
        if trial.status != 'running':
            raise HTTPException(409, f'仅进行中的试验可纳入批次（当前状态：{trial.status}）')
        try:
            complete, incomplete = complete_batches(db, trial)
            observations = db.query(TrialObservation).filter_by(trial_id=trial.id).all()
            taken = {x.batch_key for x in observations}
            sampled = set()
            for x in observations:
                for record in (x.control_snapshot or []) + (x.experiment_snapshot or []):
                    if isinstance(record, dict) and record.get('source_id') is not None:
                        sampled.add(record['source_id'])
            look_index = int(trial.look_count or 0) + 1
            fresh, skipped = _pending_batches(db, trial, complete, taken, sampled, look_index)
            skipped_keys = incomplete + skipped
            trial.skipped_batches = len(skipped_keys)
            if not fresh:
                db.commit()
                return trial_payload(db, trial, advanced=False, reason='没有新的完整批次；未重复采样')
            db.add_all(fresh)
            db.flush()
            totals = _totals(db, trial)
            stats = evidence_stats(totals['control_num'], totals['control_den'],
                                   totals['experiment_num'], totals['experiment_den'], trial.alpha)
            look = TrialLook(trial_id=trial.id, look_index=look_index, batches_added=len(fresh),
                             batch_total=totals['batch_count'], control_batches=totals['control_batches'],
                             experiment_batches=totals['experiment_batches'], control_num=totals['control_num'],
                             control_den=totals['control_den'], experiment_num=totals['experiment_num'],
                             experiment_den=totals['experiment_den'], control_rate=stats['control_rate'],
                             experiment_rate=stats['experiment_rate'], z=stats['z'], p_value=stats['p_value'],
                             evidence=stats['evidence'], nominal_alpha=trial.alpha, decision=stats['decision'],
                             skipped_batches=len(skipped_keys), created=time.time())
            db.add(look)
            for key, value in totals.items():
                setattr(trial, key, value)
            trial.look_count = look_index
            trial.control_rate = stats['control_rate']
            trial.experiment_rate = stats['experiment_rate']
            trial.last_z = stats['z']
            trial.last_p = stats['p_value']
            trial.evidence = stats['evidence']
            trial.decision = stats['decision']
            trial.updated = time.time()
            trial.version = int(trial.version or 0) + 1
            if stats['decision'] == 'efficacy':
                trial.status = 'stopped'
                trial.stopped = time.time()
                trial.stop_reason = f'序贯证据达到预留额度：p={stats["p_value"]:.6g} ≤ α={trial.alpha:g}'
            log(db, actor, 'trial.advance',
                f'{trial.name} 第{look_index}次查看 新批次{len(fresh)} 总批次{totals["batch_count"]} '
                f'p={stats["p_value"]:.6g} 证据={stats["evidence"]:.4g}')
            db.commit()
            return trial_payload(db, trial)
        except IntegrityError:
            # 另一执行者已经提交同一批次：回滚后重新读取，不重复采样也不重复记查看。
            db.rollback()
            continue
        except Exception:
            db.rollback()
            raise
    trial = db.get(Trial, trial_id)
    if not trial:
        raise HTTPException(404, '试验不存在')
    return trial_payload(db, trial, advanced=False, reason='另一执行者已完成本次推进')


def advance_running(db):
    """worker 恢复/轮询用：逐个推进进行中的试验；中断后重试不会重复采样。"""
    results = []
    for trial_id, in db.query(Trial.id).filter_by(status='running').order_by(Trial.id).all():
        try:
            payload = advance_trial(db, 'worker', trial_id)
            results.append({'id': trial_id, 'advanced': payload.get('advanced')})
        except HTTPException as exc:
            db.rollback()
            results.append({'id': trial_id, 'error': exc.detail})
        except Exception as exc:  # noqa: BLE001 - worker 不因单项失败停摆
            db.rollback()
            results.append({'id': trial_id, 'error': str(exc)})
    return results


def _transition(db, actor, trial_id, allowed, action, mutate):
    trial = db.query(Trial).filter_by(id=trial_id).with_for_update().first()
    if not trial:
        raise HTTPException(404, '试验不存在')
    if trial.status not in allowed:
        raise HTTPException(409, f'当前状态 {trial.status} 不允许{action}')
    mutate(trial)
    trial.updated = time.time()
    trial.version = int(trial.version or 0) + 1
    log(db, actor, f'trial.{action}', trial.name)
    db.commit()
    return trial_payload(db, trial)


def start_trial(db, actor, trial_id):
    def mutate(trial):
        process = db.query(TrialProcess).filter_by(id=trial.process_id).with_for_update().first()
        if not process:
            raise HTTPException(422, '工艺登记不存在，无法开试')
        ledger = process_ledger(db, process)
        # 登记时已占用额度；开试前再按账本复核一次，越界一律拒绝启动。
        own = float(trial.alpha or 0)
        others = ledger['allocated'] - own
        if own <= 0 or others + own > ledger['alpha_cap'] + _EPS:
            raise HTTPException(422, '越界试验拒绝启动：本试验预留额度超出工艺总误报上限')
        trial.status = 'running'
        trial.decision = 'continue'
        trial.stop_reason = ''
        trial.started = time.time()
    return _transition(db, actor, trial_id, ('pending',), '开试', mutate)


def stop_trial(db, actor, trial_id, reason=''):
    def mutate(trial):
        trial.status = 'stopped'
        trial.decision = 'manual'
        trial.stopped = time.time()
        trial.stop_reason = (reason or '').strip()[:200] or '执行者提前停试；已用额度不返还'
    return _transition(db, actor, trial_id, ('running',), '停试', mutate)


def cancel_trial(db, actor, trial_id):
    def mutate(trial):
        trial.status = 'cancelled'
        trial.stopped = time.time()
        trial.stop_reason = trial.stop_reason or '试验取消；已用额度不返还'
    return _transition(db, actor, trial_id, ('pending', 'running', 'stopped'), '取消', mutate)


def reopen_trial(db, actor, trial_id):
    def mutate(trial):
        # 重开复用原预留额度，不新增也不返还；已记录批次与查看历史保留，后续新批次继续分析。
        trial.status = 'running'
        trial.decision = 'continue'
        trial.stop_reason = ''
        trial.stopped = None
        trial.started = trial.started or time.time()
    return _transition(db, actor, trial_id, ('cancelled', 'stopped'), '重开', mutate)


def live_view(db, trial):
    """随时查看：只读当前证据，不写入查看记录、不额外消耗额度。"""
    totals = _totals(db, trial)
    stats = evidence_stats(totals['control_num'], totals['control_den'],
                           totals['experiment_num'], totals['experiment_den'], trial.alpha)
    process = db.get(TrialProcess, trial.process_id)
    complete, incomplete = complete_batches(db, trial)
    taken = {r[0] for r in db.query(TrialObservation.batch_key).filter_by(trial_id=trial.id).all()}
    pending = sorted(f'{p}|{s}' for (p, s) in complete if f'{p}|{s}' not in taken)
    return {'trial': trial_payload(db, trial, with_details=False), 'live': stats, 'totals': totals,
            'process': process_ledger(db, process) if process else None, 'tau': MIX_TAU,
            'pending_batches': pending, 'incomplete_batches': sorted(incomplete)}


def _trial_row(trial):
    return {c.name: getattr(trial, c.name) for c in trial.__table__.columns}


def trial_payload(db, trial, with_details=True, advanced=True, reason=''):
    payload = _trial_row(trial)
    process = db.get(TrialProcess, trial.process_id)
    ledger = process_ledger(db, process) if process else {
        'alpha_cap': 0.0, 'allocated': 0.0, 'active': 0.0, 'remaining': 0.0, 'trial_count': 0}
    payload.update({'process_cap': ledger['alpha_cap'], 'process_allocated': ledger['allocated'],
                    'process_active': ledger['active'], 'process_remaining': ledger['remaining'],
                    'alpha_reserved': float(trial.alpha or 0),
                    'tau': MIX_TAU, 'advanced': advanced, 'reason': reason})
    if with_details:
        looks = db.query(TrialLook).filter_by(trial_id=trial.id).order_by(TrialLook.look_index).all()
        payload['looks'] = [{c.name: getattr(x, c.name) for c in x.__table__.columns} for x in looks]
        observations = db.query(TrialObservation).filter_by(trial_id=trial.id).order_by(TrialObservation.id).all()
        payload['batches'] = [{
            'batch_key': x.batch_key, 'period': x.period, 'shift': x.shift, 'look_index': x.look_index,
            'control_input': x.control_input, 'control_num': x.control_num, 'control_den': x.control_den,
            'experiment_input': x.experiment_input, 'experiment_num': x.experiment_num,
            'experiment_den': x.experiment_den,
            'control_rate': (x.control_num / x.control_den) if x.control_den else None,
            'experiment_rate': (x.experiment_num / x.experiment_den) if x.experiment_den else None,
        } for x in observations]
    return payload


def list_trials(db):
    return [trial_payload(db, x, with_details=False) for x in db.query(Trial).order_by(Trial.id.desc()).all()]
