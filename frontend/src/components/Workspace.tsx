'use client';
import { useState } from 'react';
import Login from '@/modules/Login';
import Dashboard from '@/modules/Dashboard';
import Management from '@/modules/Management';
import Reports from '@/modules/Reports';
import { api } from '@/lib/api';
import type { Role, Staff } from '@/lib/types';
const owners: Record<string,string> = {Patients: 'Janani', Appointments: 'Shankuka', Consultations: 'Devindi', Billing: 'Lasanthan'};
export default function Workspace() {
 const [staff,setStaff]=useState<Staff|null>(null);
 const [preview,setPreview]=useState(false);
 const [page,setPage]=useState('Dashboard');
 const [error,setError]=useState('');
 function enter(user:Staff,isPreview:boolean) {setStaff(user);setPreview(isPreview);setPage('Dashboard');setError('');}
 async function leave() {try {if(!preview) await api('logout/','POST',{});setStaff(null);setError('');}catch(e){setError((e as Error).message);}}
 if(!staff) return <Login onLogin={enter}/>;
 const pages = staff.role === 'Branch Manager' ? ['Dashboard','Patients','Appointments','Consultations','Billing','Management','Reports'] : staff.role === 'Doctor' ? ['Dashboard','Consultations'] : ['Dashboard','Patients','Appointments','Consultations','Billing'];
 return <div className="workspace"><aside><div className="brand">✚ CATMS<span>Clinic workspace</span></div><nav aria-label="Main navigation">{pages.map(name=><button key={name} className={page===name?'active':''} aria-current={page===name?'page':undefined} onClick={()=>setPage(name)}>{name}</button>)}</nav><div className="profile"><strong>{staff.full_name}</strong><small>{staff.role}</small><button onClick={leave}>{preview?'Exit preview':'Sign out'}</button></div></aside><main><header><div><small>CLINIC OPERATIONS</small><h1>{page}</h1></div><span className="badge">{staff.role}</span></header>{preview&&<p className="notice">Design preview · No patient data loaded. Nothing is saved to Aiven.</p>}{error&&<p role="alert">{error}</p>}{page==='Dashboard'?<Dashboard/>:page==='Management'?<Management/>:page==='Reports'?<Reports/>:<section className="panel"><h2>{page} module</h2><p>{owners[page]} will add this module in a separate commit.</p><p>The shared layout is ready. This page does not access patient records yet.</p></section>}</main></div>;
}
