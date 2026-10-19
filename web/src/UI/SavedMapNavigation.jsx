import {useEffect,useState} from 'react';
import {getMapSession,applyNavMap,getPlanning,sendNavigationGoal,cancelNavigation} from '../services/api';
import {subscribeRealtime,subscribeRealtimeStatus} from '../services/realtime';

export default function SavedMapNavigation({map,disabled,navigation,onSession}) {
  const [layer,setLayer]=useState(null),[selected,setSelected]=useState("");
  const [session,setSession]=useState(null),[received,setReceived]=useState(0),[now,setNow]=useState(Date.now());
  const [confirmed,setConfirmed]=useState(false),[initialize,setInitialize]=useState(false);
  const [pose,setPose]=useState({x:'0',y:'0',yaw:'0'}),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{
    let live=true;
    const accept=data=>{if(live){setSession(data);setReceived(Date.now());onSession({...data,received_at:Date.now()});}};
    const refresh=()=>getMapSession().then(accept).catch(e=>{if(live)setError(e.message);});
    refresh();getPlanning(map.id).then(data=>{if(live)setLayer(data);}).catch(e=>setError(e.message));
    const off=subscribeRealtime(m=>{if(m.type==='MAP_SESSION_UPDATED')accept(m.data);
      if(m.type==='PLANNING_UPDATED'&&m.data.map_id===map.id)getPlanning(map.id).then(setLayer).catch(e=>setError(e.message));});
    const reconnect=subscribeRealtimeStatus((online,again)=>{if(online&&again)refresh();});
    const timer=setInterval(()=>setNow(Date.now()),1000);
    return ()=>{live=false;off();reconnect();clearInterval(timer);};
  },[]);
  const online=session?.enabled&&now-received<(session.state==='APPLYING'?65000:5000)&&session.state!=='OFFLINE';
  const same=session?.map_id===map.id&&session?.map_hash===map.map_hash;
  const active=['SENDING','NAVIGATING'].includes(navigation?.state);
  const points=(layer?.objects||[]).filter(p=>['HOME','PICKUP','DELIVERY','CHARGING'].includes(p.type));
  const target=points.find(p=>p.id===selected);
  async function navigate() {
    setBusy(true);setError('');
    try {await sendNavigationGoal({x:target.x,y:target.y,yaw:target.yaw,
      map_id:map.id,planning_point_id:target.id,planning_revision:layer.revision});}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function applyKeepouts() {
    setBusy(true);setError('');
    try {const result=await applyNavMap({map_id:map.id,operation:'APPLY_KEEPOUTS',planning_revision:layer.revision});
      setSession(result);setReceived(Date.now());}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function cancel() {
    try {await cancelNavigation();}catch(e){setError(e.message);}
  }
  async function load() {
    setBusy(true);setError('');
    try {
      const data={map_id:map.id,operation:'LOAD_MAP'};
      if(initialize)data.initial_pose=Object.fromEntries(Object.entries(pose).map(([k,v])=>[k,Number(v)]));
      const result=await applyNavMap(data);setSession(result);setReceived(Date.now());
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <section className="saved-map-navigation">
    <strong>Nav2 · Simulation</strong>
    <p>Đang xem: {map.name} · Map Nav2: {session?.map_id||'chưa xác nhận'}
      {' · '}{online?session.state:'OFFLINE'}{same?' · Khớp Saved Map':' · Khác bản đồ đang xem'}</p>
    <p>Map Server: {session?.map_server_active?'ACTIVE':'chưa sẵn sàng'} · Nav2: {session?.nav2_active?'ACTIVE':'chưa sẵn sàng'}
      {' · '}Localization: {session?.localization_valid?'hợp lệ':'chưa xác nhận'}</p>
    <fieldset disabled={disabled||busy||session?.state==='APPLYING'}>
      <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>
        Tôi đã đối chiếu bản đồ này với môi trường Gazebo đang chạy.</label>
      <label><input type="checkbox" checked={initialize} onChange={e=>setInitialize(e.target.checked)}/>
        Đặt initial pose đã biết trong simulation (m, rad)</label>
      {initialize&&<div className="planning-toolbar">{['x','y','yaw'].map(k=><label key={k}>Initial {k}
        <input aria-label={'Initial '+k} type="number" step="any" value={pose[k]} onChange={e=>setPose({...pose,[k]:e.target.value})}/></label>)}</div>}
      <button onClick={load} disabled={active||!online||!confirmed||Math.abs(map.origin.yaw)>1e-6||(initialize&&Object.values(pose).some(v=>v===''||!Number.isFinite(Number(v))))}>
        Nạp bản đồ vào Nav2</button>
    </fieldset>
    <p>NO-GO: {online&&session?.state==='READY'&&same&&session?.keepout_verified&&session?.planning_revision===layer?.revision
      ?'Đã áp dụng phiên bản '+session.planning_revision:'Chưa áp dụng phiên bản hiện tại'}</p>
    <button disabled={disabled||busy||active||session?.state==='APPLYING'||!online||!same||!layer
      ||!session?.map_verified||!session?.nav2_active||!session?.localization_valid} onClick={applyKeepouts}>
      Áp dụng vùng cấm</button>
    <p>Vùng cấm được mở rộng theo footprint robot; không sửa bản đồ SLAM gốc. Lưu chỉnh sửa rồi áp dụng trước khi đi.</p>
    <div className="planning-toolbar">
      <label>Điểm quy hoạch<select aria-label="Điểm quy hoạch" value={selected}
        disabled={disabled||busy||active} onChange={e=>setSelected(e.target.value)}>
        <option value="">Chọn điểm đích</option>
        {points.map(p=><option key={p.id} value={p.id}>{p.type} · {p.name}</option>)}
      </select></label>
      {target&&<span>X {target.x.toFixed(3)} · Y {target.y.toFixed(3)} · Yaw {target.yaw.toFixed(3)}</span>}
      <button disabled={disabled||busy||active||!online||!same||!session?.ready||session?.planning_revision!==layer?.revision||!target} onClick={navigate}>Đi tới điểm</button>
      <button disabled={!active} onClick={cancel}>Hủy điều hướng</button>
    </div>
    <p role="status">Điều hướng: {navigation?.state||'IDLE'} · Còn lại: {navigation?.distance_remaining?.toFixed(2)??'—'} m</p>
    {navigation?.error_message&&<p role="alert" className="map-error">{navigation.error_message}</p>}
    {Math.abs(map.origin.yaw)>1e-6&&<p className="map-error">Nav2 Jazzy yêu cầu origin yaw = 0. Bản đồ này chỉ xem/chỉnh quy hoạch, chưa thể nạp.</p>}
    {(error||session?.error)&&<p role="alert" className="map-error">{error||session.error}</p>}
  </section>;
}
