import {request} from './client.js';
export const loadAll=async()=>{
 const base=Object.fromEntries(await Promise.all(['sources','periods','policies','runs','schedules','deliveries','audits','trials'].map(async k=>[k,await request('/'+k)])));
 base.processes=await request('/trials/processes');
 return base;
};
export const saveSource=(data,id)=>request('/sources'+(id?'/'+id:''),id?'PUT':'POST',{data});
export const savePolicy=data=>request('/policies','POST',{data});
export const submitRun=data=>request('/runs','POST',data);
export const approveRun=(id,note)=>request('/runs/'+id+'/approve','POST',{note});
export const registerProcess=data=>request('/trials/processes','POST',data);
export const registerTrial=data=>request('/trials','POST',data);
export const startTrial=id=>request('/trials/'+id+'/start','POST',{});
export const advanceTrial=id=>request('/trials/'+id+'/advance','POST',{});
export const stopTrial=(id,reason)=>request('/trials/'+id+'/stop','POST',{reason});
export const cancelTrial=id=>request('/trials/'+id+'/cancel','POST',{});
export const reopenTrial=id=>request('/trials/'+id+'/reopen','POST',{});
export const trialStatus=id=>request('/trials/'+id+'/status');
