import { useEffect, useRef, useState } from 'react';

export default function UsbCameraPreview() {
  const video = useRef(null);
  const stream = useRef(null);
  const request = useRef(0);
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState('');
  const [error, setError] = useState('');
  const [active, setActive] = useState(false);

  function stop() {
    request.current += 1;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    if (video.current) video.current.srcObject = null;
    setActive(false);
  }

  useEffect(() => () => {
    request.current += 1;
    stream.current?.getTracks().forEach((track) => track.stop());
  }, []);

  async function open(selectedId = '') {
    stop();
    const currentRequest = request.current;
    setError('');
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Camera của trình duyệt không khả dụng. Hãy dùng localhost hoặc HTTPS.');
      return;
    }
    try {
      const next = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: selectedId ? { deviceId: { exact: selectedId } } : true,
      });
      if (currentRequest !== request.current) {
        next.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = next;
      next.getVideoTracks()[0]?.addEventListener('ended', () => {
        if (stream.current === next) {
          stream.current = null;
          if (video.current) video.current.srcObject = null;
          setActive(false);
        }
      }, { once: true });
      if (video.current) video.current.srcObject = next;
      setActive(true);
      const cameras = await navigator.mediaDevices.enumerateDevices();
      if (currentRequest !== request.current) return;
      setDevices(cameras.filter((device) => device.kind === 'videoinput'));
      setDeviceId(next.getVideoTracks()[0]?.getSettings().deviceId ?? selectedId);
    } catch (cause) {
      if (currentRequest === request.current) setError(`Không thể mở camera: ${cause.message}`);
    }
  }

  return (
    <div className="agv-camera-preview">
      <p>Camera USB trên máy đang mở trang này. Chọn đúng webcam trước khi dùng hình ảnh làm bằng chứng.</p>
      <p role="status">Camera: {active ? 'ONLINE' : 'OFFLINE'}</p>
      <video ref={video} autoPlay muted playsInline aria-label="Xem trực tiếp camera USB" style={{ display: active ? 'block' : 'none', width: '100%', maxHeight: 280, objectFit: 'contain', background: '#111' }} />
      {!active && <p>Chưa có hình ảnh trực tiếp.</p>}
      {error && <p role="alert">{error}</p>}
      {devices.length > 1 && (
        <label>Camera <select value={deviceId} onChange={(event) => open(event.target.value)}>
          {devices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}
        </select></label>
      )}
      <button type="button" onClick={active ? stop : () => open()}>{active ? 'Tắt camera' : 'Mở camera USB'}</button>
    </div>
  );
}
