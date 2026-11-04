import { useEffect, useState } from 'react';
import { getLocations, getSavedMaps, selectSavedMap, updateAgvClassRackPolicy } from '../../../services/api';
import { getAgvMissionConfig, previewAgvMission, saveAgvMissionConfig } from './agv';

const STATIONS = ['HOME', 'PICKUP', 'RACK_A', 'RACK_B', 'RACK_C', 'RACK_D'];
const RACKS = STATIONS.slice(2);
const CLASSES = ['cylinder', 'rectangular_box', 'triangular_prism'];
const LABELS = {
  robot: 'LINE-01 hoạt động', backend: 'Backend khả dụng', telemetry: 'ESP32 telemetry mới',
  map: 'Saved Map đang chọn', HOME: 'Trạm HOME', PICKUP: 'Trạm PICKUP',
  racks: 'Các rack giao hàng', graph: 'Đồ thị trạm và tuyến',
  class_mapping: 'Phân loại → rack', vision: 'Vision / capture', dispatch: 'Dispatch thực',
};

export default function AgvMissionConfiguration({ robot, operatorId, agvState, onOpenMap }) {
  const [config, setConfig] = useState(null);
  const [maps, setMaps] = useState([]);
  const [locations, setLocations] = useState([]);
  const [mapChoice, setMapChoice] = useState('');
  const [bindings, setBindings] = useState({});
  const [graphText, setGraphText] = useState('');
  const [mapping, setMapping] = useState({});
  const [confidence, setConfidence] = useState('');
  const [margin, setMargin] = useState('');
  const [token, setToken] = useState('');
  const [cargoClass, setCargoClass] = useState('');
  const [returnStation, setReturnStation] = useState('HOME');
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function load() {
    try {
      const [next, savedMaps, knownLocations] = await Promise.all([
        getAgvMissionConfig(robot.robot_code), getSavedMaps(), getLocations(),
      ]);
      setConfig(next);
      setMaps(savedMaps);
      setLocations(knownLocations);
      setMapChoice(next.selected_map?.id ?? '');
      setBindings(next.station_location_ids ?? {});
      setGraphText(next.graph ? JSON.stringify(next.graph, null, 2) : '');
      setMapping(next.policy?.mapping ?? {});
      setConfidence(next.policy?.min_confidence ?? '');
      setMargin(next.policy?.min_margin ?? '');
      setPreview(null);
      setError('');
    } catch (cause) {
      setError(cause.message);
    }
  }

  useEffect(() => { load(); }, [robot.robot_code]);

  async function apply(action) {
    setBusy(true);
    setError('');
    try { await action(); await load(); }
    catch (cause) { setError(cause.message); }
    finally { setBusy(false); }
  }

  function saveStations() {
    return apply(() => {
      let graph = null;
      if (graphText.trim()) graph = JSON.parse(graphText);
      return saveAgvMissionConfig(robot.robot_code, {
        station_location_ids: Object.fromEntries(Object.entries(bindings)
          .filter(([, id]) => id !== '').map(([code, id]) => [code, Number(id)])),
        graph, expected_revision: config?.revision ?? null, operator_id: operatorId,
      }, token);
    });
  }

  function savePolicy() {
    return apply(() => updateAgvClassRackPolicy({
      map_id: config.selected_map.id, mapping, min_confidence: Number(confidence),
      min_margin: Number(margin), expected_revision: config.policy?.revision ?? null,
      operator_id: operatorId,
    }, token));
  }

  async function showPreview() {
    setError('');
    try { setPreview(await previewAgvMission(robot.robot_code, cargoClass, returnStation)); }
    catch (cause) { setError(cause.message); }
  }

  const canSave = !busy && operatorId != null && token && config?.selected_map;
  const checks = config?.checklist ?? [];
  const currentMap = config?.selected_map;

  return <section className="robot-info-section agv-mission-config" aria-label="AGV mission configuration">
    <h3>MISSION CONFIGURATION</h3>
    <p>Robot: <strong>{robot.robot_code}</strong> · Saved Map: <strong>{currentMap?.name ?? 'N/A'}</strong></p>
    <p className="agv-readiness">
      <strong>{config?.simulation_status ?? 'BLOCKED'}</strong>
      <strong>{config?.hardware_status ?? 'BLOCKED'} {config?.hardware_status === 'BLOCKED' ? '(hardware)' : ''}</strong>
    </p>
    <div className="agv-readiness-list">
      {checks.map((item) => {
        const check = item.id === 'telemetry'
          ? { ...item, ok: !!agvState?.connected, detail: 'Connect fresh ESP32 telemetry' }
          : item;
        return <div key={check.id} className="robot-info-row">
        <span>{LABELS[check.id] ?? check.id}</span>
        <strong>{check.ok ? 'OK' : `BLOCKED — ${check.detail}`}</strong>
        </div>;
      })}
    </div>
    {config?.errors?.length > 0 && <ul className="agv-config-errors">
      {config.errors.map((issue, index) => <li key={`${index}-${issue}`}>{issue}</li>)}
    </ul>}
    {config?.hardware_blockers?.length > 0 && <p>Hardware: {config.hardware_blockers.join('; ')}</p>}
    {error && <p role="alert">{error}</p>}

    <details>
      <summary>Chỉnh Saved Map, trạm, graph và class-to-rack</summary>
      <p>Saved Map là bản đồ chung với AMR. Trạm chỉ được chấp nhận khi tọa độ thuộc map đã chọn.</p>
      <div className="agv-config-row">
        <label>Active Saved Map <select value={mapChoice} onChange={(event) => setMapChoice(event.target.value)}>
          <option value="">Chưa chọn</option>
          {maps.map((map) => <option key={map.id} value={map.id}>{map.name}</option>)}
        </select></label>
        <button type="button" disabled={busy || !mapChoice || mapChoice === currentMap?.id}
          onClick={() => apply(() => selectSavedMap(mapChoice))}>Chọn map</button>
        <button type="button" onClick={onOpenMap}>Tạo/chỉnh vị trí trên bản đồ</button>
      </div>
      <p>Map ID: {currentMap?.id ?? 'N/A'} · Robot ID: {robot.id}. Nhập graph đo đạc thật; không có cạnh mặc định.</p>
      <div className="agv-config-grid">
        {STATIONS.map((code) => {
          const choice = locations.find((item) => item.id === Number(bindings[code]));
          return <label key={code}>{code}
            <select value={bindings[code] ?? ''} onChange={(event) => setBindings((current) => ({ ...current, [code]: event.target.value }))}>
              <option value="">Chưa cấu hình</option>
              {locations.filter((item) => item.is_active && item.code === code &&
                item.location_type === (RACKS.includes(code) ? 'RACK' : code)).map((item) =>
                <option key={item.id} value={item.id}>{item.name} ({item.x}, {item.y})</option>)}
            </select>
            {choice && <small>Tọa độ map: {choice.x}, {choice.y} m</small>}
          </label>;
        })}
      </div>
      <label>Station graph JSON
        <textarea value={graphText} onChange={(event) => setGraphText(event.target.value)} rows={8}
          placeholder='{"map_id":"...","robot_id":1,"version":"...","nodes":[],"edges":[],"junction_transitions":[]}' />
      </label>
      <p>Yêu cầu node HOME, PICKUP, RACK_A–D, các cạnh có hướng và tuyến về HOME/PICKUP.</p>
      <div className="agv-config-grid">
        {CLASSES.map((cargo) => <label key={cargo}>{cargo}
          <select value={mapping[cargo] ?? ''} onChange={(event) => setMapping((current) => ({ ...current, [cargo]: event.target.value }))}>
            <option value="">Chưa gán</option>
            {RACKS.filter((rack) => locations.some((item) => item.id === Number(bindings[rack])
              && item.code === rack && item.is_active)).map((rack) => <option key={rack} value={rack}>{rack}</option>)}
          </select>
        </label>)}
        <label>Min confidence <input type="number" min="0.01" max="1" step="0.01" value={confidence}
          onChange={(event) => setConfidence(event.target.value)} /></label>
        <label>Min margin <input type="number" min="0.01" max="1" step="0.01" value={margin}
          onChange={(event) => setMargin(event.target.value)} /></label>
      </div>
      <label>Policy token <input type="password" autoComplete="off" value={token}
        onChange={(event) => setToken(event.target.value)} /></label>
      <div className="agv-config-row">
        <button type="button" disabled={!canSave} onClick={saveStations}>Lưu trạm và graph</button>
        <button type="button" disabled={!canSave || CLASSES.some((cargo) => !mapping[cargo]) || !confidence || !margin}
          onClick={savePolicy}>Lưu class-to-rack</button>
        <button type="button" onClick={load}>Tải lại</button>
      </div>
      {!operatorId && <p>Cần operator hoạt động để lưu cấu hình.</p>}
    </details>

    <div className="agv-mission-preview">
      <h3>SIMULATED MISSION PREVIEW — chỉ đọc</h3>
      <div className="agv-config-row">
        <label>Cargo class <select value={cargoClass} onChange={(event) => setCargoClass(event.target.value)}>
          <option value="">Chọn class</option>
          {CLASSES.map((cargo) => <option key={cargo} value={cargo}>{cargo}</option>)}
        </select></label>
        <label>Return <select value={returnStation} onChange={(event) => setReturnStation(event.target.value)}>
          <option value="HOME">HOME</option><option value="PICKUP">PICKUP</option>
        </select></label>
        <button type="button" disabled={!cargoClass} onClick={showPreview}>Xem tuyến, không tạo task</button>
      </div>
      {preview && <div role="status">
        <p>{preview.validation.simulation_status} · {robot.robot_code} · HOME → PICKUP → CLASSIFY ({cargoClass}) → {preview.target_rack ?? 'N/A'} → {returnStation}</p>
        {preview.sequence.map((leg) => <p key={leg.stage}>{leg.stage}: {leg.stations.join(' → ')}</p>)}
        {preview.validation.errors.map((issue, index) => <p key={`${index}-${issue}`}>{issue}</p>)}
      </div>}
    </div>
  </section>;
}
