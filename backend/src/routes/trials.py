from fastapi import APIRouter,Depends,HTTPException
from src.config.database import database
from src.controllers.auth import current,editor,admin
from src.models.trial import Trial
from src.schemas.requests import ProcessInput,TrialInput,StopInput
from src.services import trial as svc
router=APIRouter()
@router.get('/trials/processes')
def processes(db=Depends(database),u=Depends(current)): return svc.list_processes(db)
@router.post('/trials/processes')
def create_process(b:ProcessInput,db=Depends(database),u=Depends(admin)): return svc.create_process(db,u.email,b)
@router.get('/trials')
def trials(db=Depends(database),u=Depends(current)): return svc.list_trials(db)
@router.post('/trials')
def create_trial(b:TrialInput,db=Depends(database),u=Depends(editor)): return svc.create_trial(db,u.email,b)
@router.get('/trials/{id}')
def detail(id:int,db=Depends(database),u=Depends(current)):
 obj=db.get(Trial,id)
 if not obj: raise HTTPException(404,'试验不存在')
 return svc.trial_payload(db,obj)
@router.get('/trials/{id}/status')
def status(id:int,db=Depends(database),u=Depends(current)):
 obj=db.get(Trial,id)
 if not obj: raise HTTPException(404,'试验不存在')
 return svc.live_view(db,obj)
@router.post('/trials/{id}/start')
def start(id:int,db=Depends(database),u=Depends(editor)): return svc.start_trial(db,u.email,id)
@router.post('/trials/{id}/advance')
def advance(id:int,db=Depends(database),u=Depends(editor)): return svc.advance_trial(db,u.email,id)
@router.post('/trials/{id}/stop')
def stop(id:int,b:StopInput=StopInput(),db=Depends(database),u=Depends(editor)): return svc.stop_trial(db,u.email,id,b.reason)
@router.post('/trials/{id}/cancel')
def cancel(id:int,db=Depends(database),u=Depends(admin)): return svc.cancel_trial(db,u.email,id)
@router.post('/trials/{id}/reopen')
def reopen(id:int,db=Depends(database),u=Depends(admin)): return svc.reopen_trial(db,u.email,id)
