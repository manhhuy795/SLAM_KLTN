import { mapCellToWorld, worldToCanvas, worldToMapCell } from './slamMap.js';

export const POINT_TYPES = ['HOME', 'PICKUP', 'DELIVERY', 'CHARGING'];
export const TYPES = ['RACK', ...POINT_TYPES, 'NO_GO'];
export const SYMBOLS = { HOME: '⌂', PICKUP: '↑', DELIVERY: '↓', CHARGING: 'ϟ' };

export function newId() {
  // randomUUID is unavailable on plain HTTP LAN addresses.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const h = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return [h.slice(0,8),h.slice(8,12),h.slice(12,16),h.slice(16,20),h.slice(20)].join('-');
}

export function canvasToWorld(map, x, y) {
  return mapCellToWorld(map, x - .5, map.height - y - .5);
}

export function clientToWorld(map, rect, x, y) {
  return canvasToWorld(map, (x-rect.left)*map.width/rect.width, (y-rect.top)*map.height/rect.height);
}

export function localToWorld(obj, p) {
  const c=Math.cos(obj.yaw), s=Math.sin(obj.yaw);
  return {x:obj.x+c*p.x-s*p.y, y:obj.y+s*p.x+c*p.y};
}

export function worldToLocal(obj, p) {
  const c=Math.cos(obj.yaw), s=Math.sin(obj.yaw), dx=p.x-obj.x, dy=p.y-obj.y;
  return {x:c*dx+s*dy,y:-s*dx+c*dy};
}

export function footprint(obj) {
  const local=obj.type==='RACK'
    ? [{x:-obj.width/2,y:-obj.height/2},{x:obj.width/2,y:-obj.height/2},
       {x:obj.width/2,y:obj.height/2},{x:-obj.width/2,y:obj.height/2}]
    : obj.type==='NO_GO' ? obj.vertices : [{x:0,y:0}];
  return local.map(p=>localToWorld(obj,p));
}

export function polygonObject(points, name) {
  const x=points.reduce((n,p)=>n+p.x,0)/points.length;
  const y=points.reduce((n,p)=>n+p.y,0)/points.length;
  return {id:newId(),type:'NO_GO',name,x,y,yaw:0,width:null,height:null,
    vertices:points.map(p=>({x:p.x-x,y:p.y-y}))};
}

export function polygonValid(points) {
  if (points.length<3 || points.length>128) return false;
  const cross=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  const on=(a,b,p)=>Math.min(a.x,b.x)-1e-9<=p.x && p.x<=Math.max(a.x,b.x)+1e-9
    && Math.min(a.y,b.y)-1e-9<=p.y && p.y<=Math.max(a.y,b.y)+1e-9;
  let area=0;
  for(let i=0;i<points.length;i++) {
    const a=points[i],b=points[(i+1)%points.length];
    if(points.some((p,j)=>j!==i && p.x===a.x && p.y===a.y)) return false;
    area+=a.x*b.y-b.x*a.y;
    for(let j=i+1;j<points.length;j++) {
      if(j===i+1 || (i===0 && j===points.length-1)) continue;
      const c=points[j],d=points[(j+1)%points.length];
      const v=[cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)];
      if((v[0]*v[1]<0 && v[2]*v[3]<0) ||
        [[v[0],a,b,c],[v[1],a,b,d],[v[2],c,d,a],[v[3],c,d,b]]
          .some(([n,p,q,r])=>Math.abs(n)<1e-9 && on(p,q,r))) return false;
    }
  }
  return Math.abs(area)>1e-9;
}

export function objectIssues(map, obj) {
  const errors=[],warnings=[];
  if (!obj.name.trim() || obj.name.length>120) errors.push('Tên cần từ 1–120 ký tự.');
  if (![obj.x,obj.y,obj.yaw].every(Number.isFinite)) errors.push('X/Y/Yaw phải là số hữu hạn.');
  if (obj.type==='RACK' && ![obj.width,obj.height].every(v=>Number.isFinite(v) && v>0)) errors.push('Kích thước kệ phải lớn hơn 0.');
  if (obj.type==='NO_GO' && (!obj.vertices.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)) || !polygonValid(obj.vertices))) errors.push('Polygon cần 3–128 đỉnh, không tự cắt hoặc trùng đỉnh.');
  const points=footprint(obj);
  if(points.some(p=>{
    const c=worldToMapCell(map,p.x,p.y);
    return !Number.isFinite(c.column) || !Number.isFinite(c.row) || c.column<0 || c.row<0 || c.column>=map.width || c.row>=map.height;
  })) errors.push('Đối tượng nằm ngoài phạm vi bản đồ.');
  if (POINT_TYPES.includes(obj.type) && !errors.length) {
    const c=worldToMapCell(map,obj.x,obj.y);
    const value=map.data[Math.floor(c.row)*map.width+Math.floor(c.column)];
    if(value<0) warnings.push('Ô chưa biết; chưa xác nhận có thể tiếp cận.');
    else if(value>0) warnings.push('Ô có xác suất bị chiếm dụng; chưa xác nhận có thể tiếp cận.');
  }
  return {errors,warnings};
}

export function objectPayload(obj) {
  return Object.fromEntries(['id','type','name','x','y','yaw','width','height','vertices'].map(key=>[key,obj[key]]));
}

export function svgPoints(map, points) {
  return points.map(p=>worldToCanvas(map,p.x,p.y,map.width,map.height)).map(p=>p.x+','+p.y).join(' ');
}
