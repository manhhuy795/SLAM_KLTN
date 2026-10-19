import { useCallback, useEffect, useRef, useState } from 'react';
import { deleteSavedMap, getSavedMaps, getSelectedMap, selectSavedMap, uploadSavedMap } from '../services/api';
import { subscribeRealtime, subscribeRealtimeStatus } from '../services/realtime';

export default function SavedMapControls({ mode, onModeChange, map, onMapChange, locked = false, onBusyChange }) {
  const [maps, setMaps] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    if (locked) return;
    const version = ++generation.current;
    const [items, selected] = await Promise.all([getSavedMaps(), getSelectedMap()]);
    if (!mounted.current || version !== generation.current) return;
    setMaps(items);
    onMapChange(selected);
  }, [onMapChange, locked]);

  useEffect(() => {
    mounted.current = true;
    const reload = () => refresh().catch((err) => {
      if (mounted.current) setError(err.message);
    });
    reload();
    const unsubscribe = subscribeRealtime((message) => {
      if (message.type === 'SAVED_MAPS_UPDATED') reload();
    });
    const unsubscribeStatus = subscribeRealtimeStatus((online, reconnect) => {
      if (online && reconnect) reload();
    });
    return () => {
      mounted.current = false;
      generation.current += 1;
      unsubscribe();
      unsubscribeStatus();
    };
  }, [refresh]);

  async function run(operation) {
    generation.current += 1;
    setBusy(true);
    onBusyChange(true);
    setError('');
    try {
      await operation();
      await refresh();
    } catch (err) {
      if (mounted.current) setError(err.message);
    } finally {
      onBusyChange(false);
      if (mounted.current) setBusy(false);
    }
  }

  function upload(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    run(async () => {
      const created = await uploadSavedMap(data);
      const selected = await selectSavedMap(created.id);
      if (mounted.current) {
        onMapChange(selected);
        onModeChange('saved');
        form.reset();
      }
    });
  }

  return (
    <fieldset disabled={locked} className="saved-map-controls" aria-label="Map sources and import">
      <div className="saved-map-row">
        <button type="button" disabled={busy} aria-pressed={mode === 'live'}
          onClick={() => onModeChange('live')}>Live Map (ROS 2)</button>
        <button type="button" disabled={busy} aria-pressed={mode === 'saved'}
          onClick={() => onModeChange('saved')}>Saved Map (server)</button>
        <label>Bản đồ đã lưu
          <select aria-label="Bản đồ đã lưu" disabled={busy || !maps.length}
            value={map?.id || ''} onChange={(event) => {
              const id = event.target.value;
              if (id) run(async () => {
                const selected = await selectSavedMap(id);
                if (mounted.current) { onMapChange(selected); onModeChange('saved'); }
              });
            }}>
            <option value="" disabled>Chọn bản đồ</option>
            {maps.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <button type="button" disabled={busy || !map} onClick={() => {
          if (window.confirm('Xóa bản đồ "' + map.name + '" khỏi server?')) {
            run(() => deleteSavedMap(map.id));
          }
        }}>Xóa bản đồ</button>
      </div>
      <form className="saved-map-row" onSubmit={upload}>
        <label>Tên bản đồ<input name="name" required maxLength={120} disabled={busy} /></label>
        <label>ROS YAML<input name="yaml_file" type="file" accept=".yaml,.yml" required disabled={busy} /></label>
        <label>Ảnh bản đồ<input name="image_file" type="file" accept=".pgm,.png" required disabled={busy} /></label>
        <button type="submit" disabled={busy}>{busy ? 'Đang xử lý…' : 'Upload Map'}</button>
      </form>
      <p>YAML ≤ 64 KiB · Ảnh 8-bit PGM/PNG ≤ 20 MiB · Tối đa 4 triệu ô.</p>
      {mode === 'saved' && <p>Bản đồ đang xem độc lập với Nav2. Chỉ nạp vào simulation khi xác nhận đúng môi trường.</p>}
      {error && <p role="alert" className="map-error">{error}</p>}
    </fieldset>
  );
}
