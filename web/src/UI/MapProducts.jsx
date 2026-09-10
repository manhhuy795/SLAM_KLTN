import { useEffect, useState } from 'react';
import {
  MapPin,
  PackagePlus,
  Pencil,
  Plus,
  Trash2,
  X,
} from 'lucide-react';

import {
  createLocation,
  createProduct,
  deleteLocation,
  deleteProduct,
  getLocations,
  getProducts,
  updateLocation,
  updateProduct,
} from '../services/api';

import WarehouseMap from './WarehouseMap';


export default function MapProducts() {
  const [tab, setTab] = useState('map');

  const [locations, setLocations] = useState([]);
  const [products, setProducts] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [productForm, setProductForm] = useState(null);
  const [locationForm, setLocationForm] = useState(null);


  async function loadData() {
    try {
      setLoading(true);
      const [locationData, productData] = await Promise.all([
        getLocations(),
        getProducts(),
      ]);
      setLocations(locationData);
      setProducts(productData);
      setError(null);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }


  useEffect(() => {
    loadData();
  }, []);


  async function handleProductDelete(product) {
    if (!window.confirm(`Xóa sản phẩm ${product.product_code}?`)) {
      return;
    }

    try {
      await deleteProduct(product.id);
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  }


  async function handleLocationDelete(location) {
    if (!window.confirm(`Xóa vị trí ${location.code}?`)) {
      return;
    }

    try {
      await deleteLocation(location.id);
      await loadData();
    } catch (err) {
      setError(err.message);
    }
  }


  return (
    <div className="page-shell map-products-page">
      <div className="page-heading">
        <div>
          <span className="page-eyebrow">
            WRMS / BẢN ĐỒ & SẢN PHẨM
          </span>

          <h1>
            Bản đồ kho và quản lý sản phẩm
          </h1>

          <p>
            Quản lý vị trí, kệ hàng,
            khu vực vận hành và sản phẩm
            trong kho thử nghiệm.
          </p>
        </div>
      </div>


      <div
        className="page-tabs"
        role="tablist"
        aria-label="Bản đồ và sản phẩm"
      >
        <PageTab
          active={tab === 'map'}
          onClick={() => setTab('map')}
        >
          Bản đồ kho
        </PageTab>

        <PageTab
          active={tab === 'locations'}
          onClick={() => setTab('locations')}
        >
          Vị trí
        </PageTab>

        <PageTab
          active={tab === 'products'}
          onClick={() => setTab('products')}
        >
          Sản phẩm
        </PageTab>
      </div>


      {error && (
        <section className="panel">
          Không thể tải dữ liệu: {error}
        </section>
      )}


      <div className="map-products-content">
        {tab === 'map' && (
          <div className="map-products-map">
            <WarehouseMap />
          </div>
        )}


        {tab === 'locations' && (
          <LocationsTable
            locations={locations}
            loading={loading}
            onAdd={() => setLocationForm({})}
            onEdit={setLocationForm}
            onDelete={handleLocationDelete}
          />
        )}


        {tab === 'products' && (
          <ProductsTable
            products={products}
            loading={loading}
            onAdd={() => setProductForm({})}
            onEdit={setProductForm}
            onDelete={handleProductDelete}
          />
        )}
      </div>


      {productForm && (
        <ProductForm
          product={productForm.id ? productForm : null}
          locations={locations}
          onClose={() => setProductForm(null)}
          onSaved={async (data) => {
            if (productForm.id) {
              await updateProduct(productForm.id, data);
            } else {
              await createProduct(data);
            }
            setProductForm(null);
            await loadData();
          }}
        />
      )}


      {locationForm && (
        <LocationForm
          location={locationForm.id ? locationForm : null}
          onClose={() => setLocationForm(null)}
          onSaved={async (data) => {
            if (locationForm.id) {
              await updateLocation(locationForm.id, data);
            } else {
              await createLocation(data);
            }
            setLocationForm(null);
            await loadData();
          }}
        />
      )}
    </div>
  );
}


function LocationsTable({
  locations,
  loading,
  onAdd,
  onEdit,
  onDelete,
}) {
  return (
    <section className="panel management-panel">
      <div className="management-toolbar">
        <div className="management-toolbar-copy">
          <h2>VỊ TRÍ TRONG KHO</h2>

          <span>
            {locations.length} vị trí đã cấu hình
          </span>
        </div>


        <button
          className="primary-button management-add-button"
          type="button"
          onClick={onAdd}
        >
          <Plus size={15} />
          <span>Thêm vị trí</span>
        </button>
      </div>


      <div className="management-table-wrapper">
        <table className="management-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Loại / Tên vị trí</th>
              <th>X</th>
              <th>Y</th>
              <th>Yaw</th>
              <th>Trạng thái</th>
              <th>Thao tác</th>
            </tr>
          </thead>


          <tbody>
            {loading && (
              <tr>
                <td colSpan="7">
                  Đang tải vị trí...
                </td>
              </tr>
            )}


            {!loading &&
              locations.length === 0 && (
                <tr>
                  <td colSpan="7">
                    Chưa có vị trí.
                  </td>
                </tr>
              )}


            {!loading &&
              locations.map((location) => (
                <tr key={location.id}>
                  <td>
                    <strong className="text-orange mono">
                      {location.code}
                    </strong>
                  </td>


                  <td>
                    <span className="table-location">
                      <MapPin size={13} />

                      {location.name}
                    </span>

                    <small>
                      {getLocationTypeLabel(
                        location.location_type
                      )}
                    </small>
                  </td>


                  <td className="mono">
                    {formatCoordinate(location.x)} m
                  </td>


                  <td className="mono">
                    {formatCoordinate(location.y)} m
                  </td>


                  <td className="mono">
                    {formatYaw(location.yaw)}
                  </td>


                  <td>
                    <span
                      className={
                        location.is_active
                          ? 'location-status location-status--active'
                          : 'location-status location-status--inactive'
                      }
                    >
                      <span
                        className={
                          location.is_active
                            ? 'status-dot status-dot--green'
                            : 'status-dot'
                        }
                      />

                      {location.is_active
                        ? 'ĐANG SỬ DỤNG'
                        : 'TẠM NGƯNG'}
                    </span>
                  </td>


                  <td>
                    <button
                      className="icon-action"
                      type="button"
                      onClick={() => onEdit(location)}
                      aria-label={
                        `Chỉnh sửa ${location.name}`
                      }
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      className="icon-action"
                      type="button"
                      onClick={() => onDelete(location)}
                      aria-label={`Xóa ${location.name}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}


function ProductsTable({
  products,
  loading,
  onAdd,
  onEdit,
  onDelete,
}) {
  return (
    <section className="panel management-panel">
      <div className="management-toolbar">
        <div className="management-toolbar-copy">
          <h2>SẢN PHẨM</h2>

          <span>
            {products.length} sản phẩm đã đăng ký
          </span>
        </div>


        <button
          className="primary-button management-add-button"
          type="button"
          onClick={onAdd}
        >
          <PackagePlus size={15} />
          <span>Thêm sản phẩm</span>
        </button>
      </div>


      <div className="management-table-wrapper">
        <table className="management-table">
          <thead>
            <tr>
              <th>Mã sản phẩm</th>
              <th>Tên sản phẩm</th>
              <th>Kệ mặc định</th>
              <th>Trạng thái</th>
              <th>Thao tác</th>
            </tr>
          </thead>


          <tbody>
            {loading && (
              <tr>
                <td colSpan="5">
                  Đang tải sản phẩm...
                </td>
              </tr>
            )}


            {!loading &&
              products.length === 0 && (
                <tr>
                  <td colSpan="5">
                    Chưa có sản phẩm.
                  </td>
                </tr>
              )}


            {!loading &&
              products.map((product) => (
                <tr key={product.id}>
                  <td>
                    <strong className="text-orange mono">
                      {product.product_code}
                    </strong>
                  </td>


                  <td>
                    <strong className="product-name">
                      {product.name}
                    </strong>
                  </td>


                  <td>
                    <span className="table-location">
                      <MapPin size={13} />

                      {product.default_rack_name ??
                        product.default_rack_code}
                    </span>
                  </td>


                  <td>
                    <span className="product-status">
                      <span
                        className={
                          product.status === 'AVAILABLE'
                            ? 'status-dot status-dot--green'
                            : 'status-dot'
                        }
                      />

                      {getProductStatusLabel(
                        product.status
                      )}
                    </span>
                  </td>


                  <td>
                    <button
                      className="secondary-button table-button"
                      type="button"
                      onClick={() => onEdit(product)}
                      aria-label={
                        `Chỉnh sửa ${product.name}`
                      }
                    >
                      <Pencil size={13} />
                      <span>Chỉnh sửa</span>
                    </button>
                    <button
                      className="icon-action"
                      type="button"
                      onClick={() => onDelete(product)}
                      aria-label={`Xóa ${product.name}`}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}


function PageTab({
  active,
  children,
  onClick,
}) {
  return (
    <button
      className={
        `page-tab ${
          active
            ? 'page-tab--active'
            : ''
        }`
      }
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
    >
      {children}
    </button>
  );
}


function getLocationTypeLabel(type) {
  const labels = {
    HOME: 'Vị trí chờ robot',
    RACK: 'Kệ hàng',
    PICKUP: 'Điểm nhận hàng',
    DELIVERY: 'Điểm giao hàng',
    CHARGING: 'Trạm sạc',
  };

  return labels[type] ?? type;
}


function getProductStatusLabel(status) {
  const labels = {
    AVAILABLE: 'Có sẵn',
    UNAVAILABLE: 'Không khả dụng',
  };

  return labels[status] ?? status;
}


function formatCoordinate(value) {
  if (
    value === null ||
    value === undefined
  ) {
    return '—';
  }

  return Number(value).toFixed(1);
}


function formatYaw(value) {
  if (
    value === null ||
    value === undefined
  ) {
    return '—';
  }

  return `${Number(value).toFixed(2)} rad`;
}


function ProductForm({
  product,
  locations,
  onClose,
  onSaved,
}) {
  const racks = locations.filter(
    (location) =>
      location.location_type === 'RACK' &&
      location.is_active
  );
  const [form, setForm] = useState({
    product_code: product?.product_code ?? '',
    name: product?.name ?? '',
    image_path: product?.image_path ?? '',
    status: product?.status ?? 'AVAILABLE',
    default_rack_id: String(product?.default_rack_id ?? racks[0]?.id ?? ''),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    try {
      setSaving(true);
      setError(null);
      await onSaved({
        ...form,
        image_path: form.image_path || null,
        default_rack_id: Number(form.default_rack_id),
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <form className="create-task-modal" onSubmit={submit}>
        <div className="modal-header">
          <div><PackagePlus size={17} /><strong>{product ? 'Sửa sản phẩm' : 'Thêm sản phẩm'}</strong></div>
          <button type="button" onClick={onClose} aria-label="Đóng"><X size={17} /></button>
        </div>
        <div className="create-task-form">
          <label><span>Mã sản phẩm</span><input value={form.product_code} onChange={(e) => setForm({ ...form, product_code: e.target.value })} required /></label>
          <label><span>Tên sản phẩm</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
          <label><span>Kệ mặc định</span><select value={form.default_rack_id} onChange={(e) => setForm({ ...form, default_rack_id: e.target.value })} required>{racks.map((rack) => <option key={rack.id} value={rack.id}>{rack.name} — {rack.code}</option>)}</select></label>
          <label><span>Trạng thái</span><select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}><option value="AVAILABLE">Có sẵn</option><option value="UNAVAILABLE">Không khả dụng</option></select></label>
          <label><span>Image path</span><input value={form.image_path} onChange={(e) => setForm({ ...form, image_path: e.target.value })} /></label>
          {error && <div className="create-task-note">{error}</div>}
        </div>
        <div className="modal-actions"><button className="secondary-button" type="button" onClick={onClose}>Hủy</button><button className="primary-button" type="submit" disabled={saving || !form.default_rack_id}>{saving ? 'Đang lưu...' : 'Lưu'}</button></div>
      </form>
    </div>
  );
}


function LocationForm({ location, onClose, onSaved }) {
  const [form, setForm] = useState({
    code: location?.code ?? '',
    name: location?.name ?? '',
    location_type: location?.location_type ?? 'RACK',
    x: location?.x ?? 0,
    y: location?.y ?? 0,
    yaw: location?.yaw ?? 0,
    is_active: location?.is_active ?? true,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function submit(event) {
    event.preventDefault();
    try {
      setSaving(true);
      setError(null);
      await onSaved({ ...form, x: Number(form.x), y: Number(form.y), yaw: Number(form.yaw) });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <form className="create-task-modal" onSubmit={submit}>
        <div className="modal-header">
          <div><MapPin size={17} /><strong>{location ? 'Sửa vị trí' : 'Thêm vị trí'}</strong></div>
          <button type="button" onClick={onClose} aria-label="Đóng"><X size={17} /></button>
        </div>
        <div className="create-task-form">
          <label><span>Mã vị trí</span><input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required /></label>
          <label><span>Tên vị trí</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
          <label><span>Loại</span><select value={form.location_type} onChange={(e) => setForm({ ...form, location_type: e.target.value })}><option value="RACK">Kệ hàng</option><option value="HOME">HOME</option><option value="PICKUP">Điểm nhận</option><option value="DELIVERY">Điểm giao</option><option value="CHARGING">Trạm sạc</option></select></label>
          <label><span>X</span><input type="number" step="0.1" value={form.x} onChange={(e) => setForm({ ...form, x: e.target.value })} required /></label>
          <label><span>Y</span><input type="number" step="0.1" value={form.y} onChange={(e) => setForm({ ...form, y: e.target.value })} required /></label>
          <label><span>Yaw</span><input type="number" step="0.01" value={form.yaw} onChange={(e) => setForm({ ...form, yaw: e.target.value })} required /></label>
          <label><span>Trạng thái</span><select value={String(form.is_active)} onChange={(e) => setForm({ ...form, is_active: e.target.value === 'true' })}><option value="true">Đang sử dụng</option><option value="false">Tạm ngưng</option></select></label>
          {error && <div className="create-task-note">{error}</div>}
        </div>
        <div className="modal-actions"><button className="secondary-button" type="button" onClick={onClose}>Hủy</button><button className="primary-button" type="submit" disabled={saving}>{saving ? 'Đang lưu...' : 'Lưu'}</button></div>
      </form>
    </div>
  );
}
