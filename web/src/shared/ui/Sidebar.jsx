import {
  BellRing,
  Bot,
  ClipboardList,
  History,
  LayoutDashboard,
  Map,
} from 'lucide-react';


const navItems = [
  {
    id: 'dashboard',
    label: 'Tổng quan',
    icon: LayoutDashboard,
  },
  {
    id: 'tasks',
    label: 'Nhiệm vụ',
    icon: ClipboardList,
  },
  {
    id: 'robots',
    label: 'Robot',
    icon: Bot,
  },
  {
    id: 'map-products',
    label: 'Bản đồ & Sản phẩm',
    icon: Map,
  },
  {
    id: 'alerts',
    label: 'Cảnh báo',
    icon: BellRing,
  },
  {
    id: 'history',
    label: 'Lịch sử',
    icon: History,
  },
];


export default function Sidebar({
  open,
  activePage,
  alertCount,
  onNavigate,
}) {
  return (
    <aside
      className={
        `sidebar ${
          open
            ? 'sidebar--open'
            : ''
        }`
      }
    >
      <div>
        <div className="sidebar-title">
          ĐIỀU HƯỚNG
        </div>


        <nav
          className="sidebar-nav"
          aria-label="Điều hướng chính"
        >
          {navItems.map((item) => {
            const Icon = item.icon;

            const active =
              activePage === item.id;

            const badge =
              item.id === 'alerts'
                ? alertCount
                : 0;


            return (
              <button
                key={item.id}
                type="button"
                className={
                  `sidebar-link ${
                    active
                      ? 'sidebar-link--active'
                      : ''
                  }`
                }
                onClick={() =>
                  onNavigate(item.id)
                }
              >
                <span className="sidebar-link-main">
                  <Icon size={17} />

                  <span>
                    {item.label}
                  </span>
                </span>


                {badge > 0 && (
                  <span className="alert-badge">
                    {badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}