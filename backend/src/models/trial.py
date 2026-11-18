from sqlalchemy import Column,Integer,String,JSON,Float,UniqueConstraint
from src.config.database import Base
class TrialProcess(Base):
 __tablename__='trial_processes'
 id=Column(Integer,primary_key=True); name=Column(String(120),unique=True); alpha_cap=Column(Float); created=Column(Float)
class Trial(Base):
 __tablename__='yield_trials'
 __table_args__=(UniqueConstraint('process_id','name',name='uq_trial_process_name'),)
 id=Column(Integer,primary_key=True); name=Column(String(120)); process_id=Column(Integer); process=Column(String(120)); control_line=Column(String(100)); experiment_line=Column(String(100)); policy_id=Column(Integer); policy_version=Column(String(120)); policy_snapshot=Column(JSON); period=Column(String(100),default='全部'); alpha=Column(Float); status=Column(String(20),default='pending'); decision=Column(String(40),default='pending'); stop_reason=Column(String(240),default=''); look_count=Column(Integer,default=0); batch_count=Column(Integer,default=0); control_batches=Column(Integer,default=0); experiment_batches=Column(Integer,default=0); control_num=Column(Integer,default=0); control_den=Column(Integer,default=0); experiment_num=Column(Integer,default=0); experiment_den=Column(Integer,default=0); control_rate=Column(Float); experiment_rate=Column(Float); last_z=Column(Float); last_p=Column(Float); evidence=Column(Float); skipped_batches=Column(Integer,default=0); created=Column(Float); started=Column(Float); stopped=Column(Float); updated=Column(Float); version=Column(Integer,default=0)
class TrialObservation(Base):
 __tablename__='trial_observations'
 __table_args__=(UniqueConstraint('trial_id','batch_key',name='uq_trial_batch'),)
 id=Column(Integer,primary_key=True); trial_id=Column(Integer); batch_key=Column(String(160)); period=Column(String(100)); shift=Column(String(100)); control_input=Column(Integer); control_num=Column(Integer); control_den=Column(Integer); experiment_input=Column(Integer); experiment_num=Column(Integer); experiment_den=Column(Integer); control_snapshot=Column(JSON); experiment_snapshot=Column(JSON); look_index=Column(Integer); created=Column(Float)
class TrialLook(Base):
 __tablename__='trial_looks'
 __table_args__=(UniqueConstraint('trial_id','look_index',name='uq_trial_look'),)
 id=Column(Integer,primary_key=True); trial_id=Column(Integer); look_index=Column(Integer); batches_added=Column(Integer); batch_total=Column(Integer); control_batches=Column(Integer); experiment_batches=Column(Integer); control_num=Column(Integer); control_den=Column(Integer); experiment_num=Column(Integer); experiment_den=Column(Integer); control_rate=Column(Float); experiment_rate=Column(Float); z=Column(Float); p_value=Column(Float); evidence=Column(Float); nominal_alpha=Column(Float); decision=Column(String(40)); skipped_batches=Column(Integer,default=0); created=Column(Float)
