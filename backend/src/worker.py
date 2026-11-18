import time,json,traceback
from pathlib import Path
import redis
from src.config.database import Base,engine,Session
from src.config.settings import REDIS_URL
from src.models import identity,source,run,trial
from src.models.run import Run
from src.services.calculation import calculate
from src.services.delivery import tick
from src.services.trial import advance_running
Base.metadata.create_all(engine)
r=redis.Redis.from_url(REDIS_URL)
last_trial_tick=0.0
while True:
 Path('/tmp/worker-heartbeat').write_text(str(time.time()))
 try:
  item=r.lpop('report-jobs')
  if item:
   with Session() as db:
    job=db.get(Run,int(item))
    if job and job.status=='queued':
     job.status='running';db.commit()
     try: job.result=calculate(job.snapshot['sources'],job.snapshot['policy']);job.status='completed'
     except Exception as exc: job.status='failed';job.error=str(exc);traceback.print_exc()
     db.commit()
  with Session() as db: tick(db)
  # 连续对照试验：到期检查一次完整批次并推进；中断后重试按已落库批次续算，不重复采样。
  if time.time()-last_trial_tick>=5:
   last_trial_tick=time.time()
   with Session() as db: advance_running(db)
 except Exception: traceback.print_exc()
 time.sleep(1)
