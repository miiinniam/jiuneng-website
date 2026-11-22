/** /quote AI 工作台面板文案（中 / 越 / 英）。 */
import type { Lang } from './strings';

type Dict = {
  boardAria: string;
  unfilled: string;
  autoMatch: string;
  newFee: string;
  action: string;
  feeName: string;
  feeAmount: (label: string) => string;
  remove: string;
  unitVehicles: string;
  drift: (total: string, diff: string) => string;
  perVehicle: string;
  fx: (rate: string) => string;
  approxCny: (low: string, high: string) => string;
  fuelNote: string;
  copy: {
    header: string;
    km: (km: string, h: string) => string;
    vehicle: (name: string, count: number) => string;
    cargo: (label: string, weight: string) => string;
    costDetail: string;
    total: (total: string, cny: string) => string;
    priceRange: (low: string, high: string) => string;
    pricePending: string;
    disclaimer: string;
  };
};

const ZH: Dict = {
  boardAria: '报价工作台',
  unfilled: '未填',
  autoMatch: '系统自动匹配',
  newFee: '新增费用',
  action: '操作',
  feeName: '费用名称',
  feeAmount: (label) => `${label} 金额`,
  remove: '删除',
  unitVehicles: '辆',
  drift: (total, diff) => `分项合计 ${total}，与引擎合计相差 ${diff}（引擎按车型/车数做了合并折算，以合计为准）。`,
  perVehicle: '单车',
  fx: (rate) => ` · 汇率 1 CNY = ${rate} đ`,
  approxCny: (low, high) => `约 ¥${low} – ¥${high}`,
  fuelNote: '含燃油、路桥与司机成本',
  copy: {
    header: '【玖能报价参考】',
    km: (km, h) => `里程 ${km} km · 时长 ${h} h`,
    vehicle: (name, count) => `车型 ${name} × ${count} 辆`,
    cargo: (label, weight) => `货物 ${label}${weight ? ` ${weight} t` : ''}`,
    costDetail: '—— 成本明细 ——',
    total: (total, cny) => `合计\t${total} VND${cny ? `（约 ¥${cny}）` : ''}`,
    priceRange: (low, high) => `参考运费 ${low} – ${high} VND`,
    pricePending: '参考运费：需项目经理核定',
    disclaimer: '（初步测算，非正式报价）',
  },
};

const VI: Dict = {
  boardAria: 'Bàn làm việc báo giá',
  unfilled: 'Chưa điền',
  autoMatch: 'Hệ thống tự khớp',
  newFee: 'Thêm chi phí',
  action: 'Thao tác',
  feeName: 'Tên chi phí',
  feeAmount: (label) => `Số tiền ${label}`,
  remove: 'Xóa',
  unitVehicles: 'xe',
  drift: (total, diff) => `Tổng các mục ${total}, lệch so với tổng của công cụ ${diff} (công cụ đã gộp quy đổi theo loại xe/số xe, lấy tổng làm chuẩn).`,
  perVehicle: 'Mỗi xe',
  fx: (rate) => ` · Tỷ giá 1 CNY = ${rate} đ`,
  approxCny: (low, high) => `Khoảng ¥${low} – ¥${high}`,
  fuelNote: 'Đã gồm nhiên liệu, phí đường và chi phí tài xế',
  copy: {
    header: '[Tham khảo báo giá JIUNENG]',
    km: (km, h) => `Số km ${km} km · Thời gian ${h} h`,
    vehicle: (name, count) => `Loại xe ${name} × ${count} xe`,
    cargo: (label, weight) => `Hàng hóa ${label}${weight ? ` ${weight} t` : ''}`,
    costDetail: '—— Chi tiết chi phí ——',
    total: (total, cny) => `Tổng\t${total} VND${cny ? ` (khoảng ¥${cny})` : ''}`,
    priceRange: (low, high) => `Cước tham khảo ${low} – ${high} VND`,
    pricePending: 'Cước tham khảo: cần quản lý dự án xác nhận',
    disclaimer: '(Tính toán sơ bộ, không phải báo giá chính thức)',
  },
};

const EN: Dict = {
  boardAria: 'Quote workspace',
  unfilled: 'Not set',
  autoMatch: 'Auto-matched',
  newFee: 'Add cost',
  action: 'Action',
  feeName: 'Cost name',
  feeAmount: (label) => `${label} amount`,
  remove: 'Delete',
  unitVehicles: 'veh',
  drift: (total, diff) => `Itemised total ${total} differs from the engine total by ${diff} (the engine consolidates by vehicle type/count; the engine total is authoritative).`,
  perVehicle: 'Per vehicle',
  fx: (rate) => ` · Rate 1 CNY = ${rate} đ`,
  approxCny: (low, high) => `approx. ¥${low} – ¥${high}`,
  fuelNote: 'Includes fuel, tolls and driver cost',
  copy: {
    header: '[JIUNENG quote reference]',
    km: (km, h) => `Distance ${km} km · Duration ${h} h`,
    vehicle: (name, count) => `Vehicle ${name} × ${count}`,
    cargo: (label, weight) => `Cargo ${label}${weight ? ` ${weight} t` : ''}`,
    costDetail: '—— Cost detail ——',
    total: (total, cny) => `Total\t${total} VND${cny ? ` (approx. ¥${cny})` : ''}`,
    priceRange: (low, high) => `Reference freight ${low} – ${high} VND`,
    pricePending: 'Reference freight: requires project-manager confirmation',
    disclaimer: '(Preliminary estimate, not a formal quote)',
  },
};

export function workspaceText(lang: Lang): Dict {
  if (lang === 'vi') return VI;
  if (lang === 'en') return EN;
  return ZH;
}
