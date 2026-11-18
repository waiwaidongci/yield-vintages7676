import json,random,time
from src.config.database import Base,engine,Session
from src.config.settings import CONFIG
from src.models.identity import User
from src.models.source import Source,Policy,Period
from src.models import run,trial
from src.models.trial import TrialProcess,Trial
from src.utils.security import password_hash
from src.services.validation import validate_source

def demo_rows():
 rng=random.Random(42);rows=[]
 for i in range(240):
  n=rng.randint(100,1200);fp=int(n*rng.uniform(.7,.96));rw=rng.randint(0,n-fp);rows.append({'period':'2026-11-'+str(1+i%20).zfill(2),'department':['试制线A','试制线B','试制线C'][i%3],'shift':['早班','晚班'][i%2],'input':n,'first_pass':fp,'reworked_good':rw,'scrap':n-fp-rw})
 return rows

def seed():
 Base.metadata.create_all(engine)
 with Session() as db:
  for role in ('admin','analyst','viewer'):
   if not db.query(User).filter_by(email=role+'@demo.local').first():db.add(User(email=role+'@demo.local',role=role,password=password_hash('Demo2026!')))
  rows=demo_rows()
  for name in sorted(set(r['period'] for r in rows)):
   if not db.query(Period).filter_by(name=name).first():db.add(Period(name=name,description='合成演示业务期间，seed=42'))
  for i,data in enumerate(rows):
   validate_source(data);key='demo-'+str(i+1)
   if not db.query(Source).filter_by(natural_key=key).first():db.add(Source(natural_key=key,data=data))
  if not db.query(Policy).filter_by(version=CONFIG['policy']['version']).first():db.add(Policy(version=CONFIG['policy']['version'],data=CONFIG['policy']))
  db.flush()
  policy=db.query(Policy).filter_by(version=CONFIG['policy']['version']).first()
  process=db.query(TrialProcess).filter_by(name='涂布工序').first()
  if not process:
   process=TrialProcess(name='涂布工序',alpha_cap=0.05,created=time.time());db.add(process);db.flush()
  if process and not db.query(Trial).filter_by(process_id=process.id,name='十一月试制线A/B连续对照').first():
   db.add(Trial(name='十一月试制线A/B连续对照',process_id=process.id,process=process.name,control_line='试制线A',experiment_line='试制线B',policy_id=policy.id,policy_version=policy.version,policy_snapshot=policy.data,period='全部',alpha=0.02,status='pending',decision='pending',look_count=0,batch_count=0,control_batches=0,experiment_batches=0,control_num=0,control_den=0,experiment_num=0,experiment_den=0,skipped_batches=0,evidence=0.0,created=time.time(),updated=time.time(),version=0))
  db.commit();print(json.dumps({'users':db.query(User).count(),'sources':db.query(Source).count(),'policies':db.query(Policy).count(),'periods':db.query(Period).count(),'processes':db.query(TrialProcess).count(),'trials':db.query(Trial).count()},ensure_ascii=False))
if __name__=='__main__':seed()

