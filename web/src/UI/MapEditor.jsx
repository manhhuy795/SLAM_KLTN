import { useEffect, useRef, useState } from 'react';
import SlamMap from './SlamMap';
import { getPlanning, savePlanning } from '../services/api';
import { subscribeRealtime, subscribeRealtimeStatus } from '../services/realtime';
import { worldToCanvas } from '../services/slamMap';
import {
  TYPES, SYMBOLS, newId, clientToWorld, footprint, localToWorld, worldToLocal,
  polygonObject, objectIssues, objectPayload, svgPoints,
} from '../services/planning';

const TOOLS = [['SELECT','Select / Move'],['PAN','Pan'],['RACK','Add Rack'],
  ['HOME','Add Home'],['PICKUP','Add Pickup'],['DELIVERY','Add Delivery'],
  ['CHARGING','Add Charging'],['NO_GO','Draw No-Go Zone']];

export default function MapEditor({ map, onEditingChange, sourceBusy, pose, goal, path }) {
  const [layer,setLayer]=useState(null), [objects,setObjects]=useState([]);
  const [editing,setEditing]=useState(false), [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false), [error,setError]=useState(''), [notice,setNotice]=useState('');
  const [tool,setTool]=useState('SELECT'), [selected,setSelected]=useState(null), [drawing,setDrawing]=useState([]);
  const [size,setSize]=useState({width:1,height:1});
  const [view,setView]=useState({zoom:1,x:0,y:0});
  const viewport=useRef(null), scene=useRef(null), drag=useRef(null), mounted=useRef(true);
  const editingRef=useRef(false), generation=useRef(0);
  const selectedObject=objects.find(o=>o.id===selected);
  const fit=Math.min(size.width/map.width,size.height/map.height);
  const sceneWidth=fit*map.width,sceneHeight=fit*map.height;
  const issues=objects.map(o=>({obj:o,...objectIssues(map,o)}));
  const invalid=issues.some(i=>i.errors.length);
  const marker=Math.max(.2,Math.min(map.width,map.height)/45);

  async function reload() {
    const version=++generation.current;
    const data=await getPlanning(map.id);
    if (!mounted.current || version!==generation.current) return;
    setLayer(data);setObjects(data.objects);setDirty(false);setError('');setNotice('');
  }

  useEffect(()=>{
    mounted.current=true;
    reload().catch(e=>{if(mounted.current)setError(e.message);});
    const observer=new ResizeObserver(entries=>{
      const r=entries[0].contentRect;
      setSize({width:r.width,height:r.height});
    });
    observer.observe(viewport.current);
    const element=viewport.current;
    const preventScroll=event=>event.preventDefault();
    element.addEventListener("wheel",preventScroll,{passive:false});
    const update=message=>{
      if(message && (message.type!=='PLANNING_UPDATED' || message.data.map_id!==map.id))return;
      if(editingRef.current) setNotice('Dữ liệu trên server có thể đã thay đổi. Bản nháp được giữ; Save kiểm tra phiên bản.');
      else reload().catch(e=>{if(mounted.current)setError(e.message);});
    };
    const unsubscribe=subscribeRealtime(update);
    const reconnect=subscribeRealtimeStatus((online,reconnected)=>{if(online&&reconnected)update();});
    return ()=>{mounted.current=false;generation.current++;observer.disconnect();element.removeEventListener("wheel",preventScroll);unsubscribe();reconnect();onEditingChange(false);};
  },[map.id, onEditingChange]);

  useEffect(()=>{
    const leave=event=>{if(editing && (dirty || drawing.length)){event.preventDefault();event.returnValue='';}};
    const navigate=event=>{
      if(editing && (dirty || drawing.length) && !window.confirm('Rời trang và bỏ các thay đổi quy hoạch chưa lưu?')) event.preventDefault();
    };
    window.addEventListener('beforeunload',leave);
    window.addEventListener('planning:before-leave',navigate);
    return ()=>{
      window.removeEventListener('beforeunload',leave);
      window.removeEventListener('planning:before-leave',navigate);
    };
  },[editing,dirty,drawing.length]);

  function edit(value) {
    if(value) generation.current++;
    editingRef.current=value;setEditing(value);onEditingChange(value);
    setTool('SELECT');setDrawing([]);setSelected(null);
  }
  function change(next) {setObjects(next);setDirty(true);setError('');}
  function updateObject(id,patch) {change(objects.map(o=>o.id===id?{...o,...patch}:o));}
  function world(event) {
    return clientToWorld(map,scene.current.getBoundingClientRect(),event.clientX,event.clientY);
  }
  function canvasPoint(point) {return worldToCanvas(map,point.x,point.y,map.width,map.height);}
  function zoom(factor, anchor={x:size.width/2,y:size.height/2}) {
    setView(current=>{
      const next=Math.max(.5,Math.min(12,current.zoom*factor)), ratio=next/current.zoom;
      return {zoom:next,
        x:anchor.x-(size.width-sceneWidth)/2-(anchor.x-(size.width-sceneWidth)/2-current.x)*ratio,
        y:anchor.y-(size.height-sceneHeight)/2-(anchor.y-(size.height-sceneHeight)/2-current.y)*ratio};
    });
  }

  function pointerDown(event) {
    if(busy || (event.button!==0 && event.button!==1))return;
    const point=world(event);
    const hit=event.target.closest('[data-object-id]');
    const id=hit?.getAttribute('data-object-id');
    const obj=objects.find(o=>o.id===id);
    const handle=event.target.getAttribute('data-vertex');
    if(event.button===1 || tool==='PAN' || !editing || (tool==='SELECT'&&!obj)) {
      if(tool!=='PAN' && event.button!==1) {
        if(obj)setSelected(id);else setSelected(null);
      }
      drag.current={kind:'pan',clientX:event.clientX,clientY:event.clientY,view};
    } else if(tool==='SELECT' && obj) {
      setSelected(id);
      drag.current={kind:handle!==null?'vertex':'object',index:Number(handle),start:point,object:obj};
    } else if(tool==='NO_GO') {
      if(drawing.length>=128){setError('Tối đa 128 đỉnh.');return;}
      setDrawing([...drawing,point]);return;
    } else if(TYPES.includes(tool)) {
      const span=Math.min(map.width,map.height)*map.resolution;
      const obj={id:newId(),type:tool,name:tool+' '+(objects.filter(o=>o.type===tool).length+1),
        ...point,yaw:map.origin?.yaw||0,width:tool==='RACK'?span*.12:null,
        height:tool==='RACK'?span*.08:null,vertices:[]};
      change([...objects,obj]);setSelected(obj.id);setTool('SELECT');return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function pointerMove(event) {
    const d=drag.current;if(!d)return;
    if(d.kind==='pan') {
      setView({...d.view,x:d.view.x+event.clientX-d.clientX,y:d.view.y+event.clientY-d.clientY});return;
    }
    const point=world(event);
    if(d.kind==='vertex') {
      const vertices=d.object.vertices.map((p,i)=>i===d.index?worldToLocal(d.object,point):p);
      updateObject(d.object.id,{vertices});
    } else updateObject(d.object.id,{x:d.object.x+point.x-d.start.x,y:d.object.y+point.y-d.start.y});
  }
  function finishPolygon() {
    if(drawing.length<3)return;
    const obj=polygonObject(drawing,'NO-GO '+(objects.filter(o=>o.type==='NO_GO').length+1));
    change([...objects,obj]);setSelected(obj.id);setDrawing([]);setTool('SELECT');
  }
  async function save() {
    setBusy(true);setError('');
    try {
      const result=await savePlanning(map.id,{revision:layer.revision,objects:objects.map(objectPayload)});
      if(!mounted.current)return;
      setLayer(result);setObjects(result.objects);setDirty(false);setNotice('Đã lưu quy hoạch.');edit(false);
    } catch(e) {if(mounted.current)setError(e.message);}
    finally {if(mounted.current)setBusy(false);}
  }
  async function cancel() {
    if((dirty || drawing.length) && !window.confirm('Hủy các thay đổi quy hoạch chưa lưu?'))return;
    setBusy(true);
    try {await reload();if(mounted.current)edit(false);}
    catch(e){if(mounted.current)setError(e.message);}
    finally{if(mounted.current)setBusy(false);}
  }
  function numeric(event) {return event.target.value===''?NaN:Number(event.target.value);}

  return <div className="planning-editor">
    <div className="planning-toolbar">
      {!editing ? <button disabled={!layer || busy || sourceBusy} onClick={()=>edit(true)}>Chỉnh sửa bản đồ</button> : <>
        {TOOLS.map(([value,label])=><button key={value} disabled={busy} aria-pressed={tool===value}
          onClick={()=>{setTool(value);setDrawing([]);}}>{label}</button>)}
        <button disabled={!selectedObject||busy} onClick={()=>{change(objects.filter(o=>o.id!==selected));setSelected(null);}}>Delete</button>
        <button disabled={busy||invalid||drawing.length>0} onClick={save}>Save</button>
        <button disabled={busy} onClick={cancel}>Cancel</button>
      </>}
      <button aria-label="Phóng to" onClick={()=>zoom(1.25)}>+</button>
      <button aria-label="Thu nhỏ" onClick={()=>zoom(.8)}>−</button>
      <button onClick={()=>setView({zoom:1,x:0,y:0})}>Fit map</button>
      <span>{Math.round(view.zoom*100)}% · {objects.length} đối tượng {dirty?'· Chưa lưu':''}</span>
    </div>
    <p className="planning-help">Chỉnh sửa chỉ thay đổi Planning Layer. Lưu rồi bấm Áp dụng vùng cấm để cập nhật Nav2; ô trống chưa đủ xác nhận an toàn.</p>
    {editing && <p className="planning-help">Chọn công cụ rồi bấm trên bản đồ. Select / Move: kéo đối tượng; kéo nền hoặc dùng Pan để dịch khung nhìn. Cuộn chuột để zoom. Yaw tính bằng radian.</p>}
    {tool==='NO_GO' && editing && <div className="planning-toolbar">
      <span>Bấm từng đỉnh polygon ({drawing.length}/128).</span>
      <button disabled={drawing.length<3} onClick={finishPolygon}>Hoàn tất vùng cấm</button>
      <button onClick={()=>setDrawing(drawing.slice(0,-1))} disabled={!drawing.length}>Bỏ đỉnh cuối</button>
    </div>}
    {error && <p role="alert" className="map-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="planning-layout">
      <div ref={viewport} className="planning-viewport" aria-label="Khung quy hoạch bản đồ"
        onWheel={event=>{const r=event.currentTarget.getBoundingClientRect();zoom(event.deltaY<0?1.1:1/1.1,{x:event.clientX-r.left,y:event.clientY-r.top});}}
        onPointerDown={pointerDown} onPointerMove={pointerMove}
        onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}
        onContextMenu={event=>event.preventDefault()}>
        <div className="planning-scene" ref={scene} style={{width:sceneWidth,height:sceneHeight,
          left:(size.width-sceneWidth)/2,top:(size.height-sceneHeight)/2,
          transform:`translate(${view.x}px,${view.y}px) scale(${view.zoom})`}}>
          <SlamMap map={map} pose={pose} goal={goal} path={path} overlay={<svg className="planning-overlay" viewBox={`0 0 ${map.width} ${map.height}`}
            aria-label="Planning Layer">
            {objects.map(obj=>{
              const p=canvasPoint(obj), color=obj.type==='NO_GO'?'#ef4444':obj.type==='RACK'?'#38bdf8':'#fbbf24';
              const points=footprint(obj);
              const bad=objectIssues(map,obj).errors.length>0;
              if(![p.x,p.y,obj.yaw,...points.flatMap(v=>[v.x,v.y])].every(Number.isFinite))return null;
              return <g key={obj.id} data-object-id={obj.id} aria-label={obj.type+': '+obj.name}
                className="planning-object" stroke={selected===obj.id?'#fff':color} strokeWidth={marker*.16}>
                {obj.type==='RACK'||obj.type==='NO_GO'
                  ? <polygon points={svgPoints(map,points)} fill={color} fillOpacity={obj.type==='NO_GO'?.3:.45} strokeDasharray={bad?marker*.4:undefined}/>
                  : <><circle cx={p.x} cy={p.y} r={marker} fill="#111827"/>
                    <text x={p.x} y={p.y+marker*.38} textAnchor="middle" fontSize={marker*1.5} stroke="none" fill={color}>{SYMBOLS[obj.type]}</text>
                    <line x1={p.x} y1={p.y} x2={p.x+Math.cos(obj.yaw-(map.origin?.yaw||0))*marker*2}
                      y2={p.y-Math.sin(obj.yaw-(map.origin?.yaw||0))*marker*2}/></>}
                <text x={p.x+marker*1.2} y={p.y-marker} fontSize={marker*1.1} stroke="none" fill={bad?'#f87171':'#fff'}>{obj.name}</text>
                {editing && selected===obj.id && obj.type==='NO_GO' && obj.vertices.map((v,i)=>{
                  const q=canvasPoint(localToWorld(obj,v));
                  return <circle key={i} data-vertex={i} cx={q.x} cy={q.y} r={marker*.55} fill="#fff" stroke="#ef4444"/>;
                })}
              </g>;
            })}
            {drawing.length>0 && <polyline points={svgPoints(map,drawing)} fill="none" stroke="#ef4444" strokeWidth={marker*.2}/>}
            {drawing.map((p,i)=>{const q=canvasPoint(p);return <circle key={i} cx={q.x} cy={q.y} r={marker*.4} fill="#ef4444"/>;})}
          </svg>}/>
        </div>
      </div>
      <aside className="planning-properties">
        <label>Đối tượng<select aria-label="Đối tượng quy hoạch" value={selected||''} onChange={e=>setSelected(e.target.value||null)}>
          <option value="">Chọn đối tượng</option>
          {objects.map(o=><option key={o.id} value={o.id}>{o.type} · {o.name}</option>)}
        </select></label>
        {selectedObject ? <fieldset disabled={!editing||busy}>
          <legend>{selectedObject.type}</legend>
          <label>Tên đối tượng<input maxLength={120} value={selectedObject.name}
            onChange={e=>updateObject(selected,{name:e.target.value})}/></label>
          {['x','y','yaw',...(selectedObject.type==='RACK'?['width','height']:[])].map(key=><label key={key}>
            {{x:'X (m)',y:'Y (m)',yaw:'Yaw (rad)',width:'Rộng (m)',height:'Dài (m)'}[key]}
            <input type="number" step="any" value={Number.isFinite(selectedObject[key])?selectedObject[key]:''}
              onChange={e=>updateObject(selected,{[key]:numeric(e)})}/></label>)}
          {selectedObject.type==='NO_GO' && <div className="planning-vertices">
            <p>Đỉnh theo mét cục bộ, xoay theo Yaw. Kéo các nút trắng hoặc sửa tọa độ để đổi hình/kích thước.</p>
            {selectedObject.vertices.map((p,i)=><div key={i}>
              {['x','y'].map(axis=><label key={axis}>Đỉnh {i+1} {axis.toUpperCase()}
                <input type="number" step="any" value={Number.isFinite(p[axis])?p[axis]:''}
                  onChange={e=>updateObject(selected,{vertices:selectedObject.vertices.map((v,j)=>j===i?{...v,[axis]:numeric(e)}:v)})}/>
              </label>)}
            </div>)}
          </div>}
        </fieldset> : <p>Chọn đối tượng trên bản đồ hoặc danh sách để xem thông tin.</p>}
        {selectedObject && <small>ID: {selectedObject.id}<br/>Tạo: {selectedObject.created_at||'Chưa lưu'}<br/>Sửa: {selectedObject.updated_at||'Chưa lưu'}</small>}
      </aside>
    </div>
    <p className="planning-help">{map.name} · {map.width} × {map.height} · {map.resolution} m/cell · origin [{map.origin.x}, {map.origin.y}, {map.origin.yaw}]</p>
    {issues.some(i=>i.errors.length||i.warnings.length) && <ul className="planning-issues" aria-label="Kiểm tra quy hoạch">
      {issues.map(i=>[...i.errors,...i.warnings].map((text,n)=><li key={i.obj.id+n}>{i.obj.name}: {text}</li>))}
    </ul>}
  </div>;
}
