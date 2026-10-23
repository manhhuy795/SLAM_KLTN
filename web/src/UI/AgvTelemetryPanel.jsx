import { useEffect, useState } from "react";
import { getAgvState, sendAgvCommand, exportAgvLogs } from "../services/agv";
import { subscribeRealtime } from "../services/realtime";

const STATIONS = [{id:"A",x:0,y:0},{id:"B",x:0,y:1.51},{id:"C",x:1.54,y:1.51},{id:"D",x:1.54,y:0}];
const ACTIONS = [
  ["start","Chạy chặng"],["stop","DỪNG"],["auto_loop_on","Vòng lặp A-B-C-D"],
  ["auto_loop_off","Tắt vòng lặp"],["turn_left_90","Trái 90°"],["turn_right_90","Phải 90°"],
  ["turn_180","Quay 180°"],["calibrate_gyro","Hiệu chuẩn gyro"],["reset_odom","Đặt lại gốc"],
];
const svgX = (x) => 50 + x/1.54*340;
const svgY = (y) => 40 + y/1.51*290;

export default function AgvTelemetryPanel() {
  const [state,setState] = useState(null);
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const load = () => getAgvState().then(setState).catch(e=>setError(e.message));
  useEffect(()=>{
    load();
    const timer = window.setInterval(load,1000);
    const unsubscribe = subscribeRealtime(msg=>{
      if(msg.type==="AGV_TELEMETRY_UPDATED" && msg.data?.robot_code==="LINE-01") setState(msg.data);
    });
    return ()=>{window.clearInterval(timer);unsubscribe();};
  },[]);
  async function command(action,mission_id) {
    setBusy(true);setError("");
    try {await sendAgvCommand(action,mission_id);await load();}
    catch(e){setError(e.message);}
    finally {setBusy(false);}
  }
  const data = state?.telemetry;
  const connected = !!state?.connected;
  const allowed = connected && state?.commands_enabled;
  const mask = data?.line_mask ?? 0;
  return <section aria-label="AGV telemetry" style={{background:"#17212e",color:"#e9f2fc",padding:20,borderRadius:12,marginBottom:18}}>
    <h2 style={{fontSize:20,marginBottom:12}}>AGV LINE-01 · Giám sát phần cứng</h2>
    <p style={{marginBottom:12}}>{connected ? "🟢 Đang truyền telemetry" : "🔴 Offline / dữ liệu đã cũ"} · {state?.last_seen_age_ms == null ? "Chưa có dữ liệu" : `Cập nhật ${state.last_seen_age_ms} ms trước`}</p>
    {error && <p role="alert" style={{color:"#ff9e9e"}}>{error}</p>}
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(260px,1fr))",gap:18}}>
      <div>
        <svg viewBox="0 0 440 380" role="img" aria-label="Bản đồ AGV A B C D độc lập với bản đồ SLAM" style={{width:"100%",background:"#0b1522",borderRadius:8}}>
          <polyline points={STATIONS.map(p=>`${svgX(p.x)},${svgY(p.y)}`).join(" ") + " 50,40"} fill="none" stroke="#4da8ff" strokeWidth="4" />
          {STATIONS.map(p=><g key={p.id}><circle cx={svgX(p.x)} cy={svgY(p.y)} r="7" fill="#f6ba48"/><text x={svgX(p.x)+10} y={svgY(p.y)-10} fill="white" fontSize="16">{p.id}</text></g>)}
          {state?.trail?.length>1 && <polyline points={state.trail.map(p=>`${svgX(p[0])},${svgY(p[1])}`).join(" ")} fill="none" stroke="#4dedb8" strokeWidth="2" />}
          {data && <g transform={`translate(${svgX(data.x)} ${svgY(data.y)}) rotate(${data.yaw})`}>
            <circle r="9" fill="#ff873a"/><path d="M0 0 L22 0" stroke="white" strokeWidth="3"/>
          </g>}
        </svg>
        <p style={{fontSize:12,color:"#a8b9d0"}}>Hệ tọa độ sa bàn AGV 1.54 × 1.51 m · +Y xuống · Không thay thế pose Nav2.</p>
      </div>
      <div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8}}>
          {[
            ["X",data?.x,"m"],["Y",data?.y,"m"],["Yaw",data?.yaw,"°"],
            ["Tốc độ",data?.speed,"cm/s"],["Quãng đường",data?.dist,"m"],
            ["Line error",data?.line_err,""],["Encoder L",data?.ticks_l,""],["Encoder R",data?.ticks_r,""],
            ["PWM L",data?.pwm_l,""],["PWM R",data?.pwm_r,""],
          ].map(([label,value,unit])=><div key={label} style={{background:"#233345",padding:10,borderRadius:6}}>
            <small>{label}</small><div style={{fontSize:17,fontWeight:700}}>{value ?? "—"} {value==null?"":unit}</div>
          </div>)}
        </div>
        <p style={{marginTop:12}}>TCRT5000: {["L2","L1","C","R1","R2"].map((label,i)=><span key={label} style={{display:"inline-block",padding:"5px 8px",margin:2,borderRadius:5,background:mask&(1<<(4-i))?"#bb4169":"#34495c"}}>{label}</span>)}</p>
        <p>Trạng thái: <strong>{data?.state ?? "Chưa có"}</strong> · ACK: {state?.last_ack_id ?? 0}</p>
        <p>Lệnh: {state?.pending_command?.cmd ?? state?.last_command ?? "Không có"} ({state?.command_status ?? "NONE"})</p>
      </div>
    </div>
    <h3 style={{margin:"15px 0 8px"}}>Điều khiển AGV</h3>
    <p style={{fontSize:12,opacity:0.8}}>Chỉ dùng khi kiểm soát được robot thật. Nút STOP được phép yêu cầu ngay cả khi offline; xác nhận API không chứng minh robot đã dừng.</p>
    <div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:10}}>
      {ACTIONS.map(([action,label])=><button key={action} type="button" disabled={busy || !state?.commands_enabled || (action!=="stop" && !allowed)}
        onClick={()=>command(action)} style={{padding:"9px 12px",background:action==="stop"?"#b91c1c":"#235482",color:"white",border:0,borderRadius:6,cursor:"pointer"}}>
        {label}
      </button>)}
    </div>
    <div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:10}}>
      {["M1","M2","M3","M4"].map(id=><button key={id} disabled={busy||!allowed} type="button" onClick={()=>command("mission",id)} style={{padding:9}}>{id}</button>)}
      <button type="button" onClick={exportAgvLogs}>Xuất telemetry CSV</button>
    </div>
  </section>;
}
