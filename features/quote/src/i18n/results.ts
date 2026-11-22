/** /quote 结果面板文案：公开口径（客户可见）与内部口径（成本分项）。 */
import type { Lang } from './strings';

type Dict = {
  public: {
    kicker: string;
    distance: string;
    duration: string;
    vehicles: string;
    vehicle: string;
    autoMatch: string;
    payload: (t: string) => string;
    unitVehicles: string;
    priceRange: string;
    price: string;
    toAria: string;
    priceNote: string;
    pendingRange: string;
    pendingRangeBody: string;
    submitInquiry: string;
    withLoading: (h: string) => string;
    withRest: (h: string) => string;
    footNote: string;
  };
  internal: {
    kicker: string;
    transport: string;
    extra: string;
    totals: string;
    items: {
      distance: string;
      time: string;
      fuel: string;
      loading: string;
      insurance: string;
      toll: string;
      misc: string;
      body: string;
      restricted: string;
      construction: string;
      mountain: string;
      port: string;
      fixed: string;
      total: string;
      perKm: string;
      perTonKm: string;
      perVehicle: string;
      utilisation: string;
      vehicles: string;
      matched: string;
    };
    unitVehicles: (n: string) => string;
    tableCap: string;
    thItem: string;
    thValue: string;
    footNote: string;
  };
};

const ZH: Dict = {
  public: {
    kicker: '测算结果 · 参考',
    distance: '里程',
    duration: '时长',
    vehicles: '车辆数',
    vehicle: '车型',
    autoMatch: '系统自动匹配',
    payload: (t) => `· 载重 ${t} t`,
    unitVehicles: '辆',
    priceRange: '参考运费区间',
    price: '参考运费',
    toAria: '至',
    priceNote: '含燃油、路桥与司机成本；不含装卸、口岸操作、保险与特殊作业。最终以项目经理核定为准。',
    pendingRange: '参考价区间需项目经理核定',
    pendingRangeBody: '该线路的售价系数尚未录入系统，里程与车数已算出。把需求发给我们，项目经理按车辆与口岸情况直接给价。',
    submitInquiry: '提交询价 →',
    withLoading: (h) => `时长已含装卸 ${h} h`,
    withRest: (h) => ` · 司机休息 ${h} h`,
    footNote: '里程与时长为路线引擎估算值，实际受口岸通关、路况与天气影响。',
  },
  internal: {
    kicker: '测算结果 · 内部成本口径',
    transport: '运输成本',
    extra: '附加与绕行',
    totals: '合计与指标',
    items: {
      distance: '距离成本',
      time: '时间成本',
      fuel: '油耗成本',
      loading: '装卸费',
      insurance: '保险费',
      toll: '路桥费',
      misc: '其他杂费',
      body: '车身附加',
      restricted: '限行绕行',
      construction: '施工绕行',
      mountain: '山区路段',
      port: '口岸附加',
      fixed: '固定费',
      total: '总成本',
      perKm: '每公里成本',
      perTonKm: '吨公里成本',
      perVehicle: '单车成本',
      utilisation: '运力占用',
      vehicles: '车辆数',
      matched: '匹配车型',
    },
    unitVehicles: (n) => `${n} 辆`,
    tableCap: '分项成本（VND，引擎直出）',
    thItem: '项目',
    thValue: '数值',
    footNote: '成本口径为引擎直出，不含毛利与销售加价；对外报价请按公司售价系数另算，不要直接转发本页。',
  },
};

const VI: Dict = {
  public: {
    kicker: 'Kết quả tính · Tham khảo',
    distance: 'Số km',
    duration: 'Thời gian',
    vehicles: 'Số xe',
    vehicle: 'Loại xe',
    autoMatch: 'Hệ thống tự khớp',
    payload: (t) => `· Tải trọng ${t} t`,
    unitVehicles: 'xe',
    priceRange: 'Khoảng cước tham khảo',
    price: 'Cước tham khảo',
    toAria: 'đến',
    priceNote: 'Đã gồm nhiên liệu, phí đường và chi phí tài xế; chưa gồm xếp dỡ, thao tác cửa khẩu, bảo hiểm và công tác đặc biệt. Giá cuối cùng do quản lý dự án xác nhận.',
    pendingRange: 'Khoảng giá tham khảo cần quản lý dự án xác nhận',
    pendingRangeBody: 'Hệ số giá bán của tuyến này chưa được nhập vào hệ thống; số km và số xe đã tính xong. Hãy gửi nhu cầu, quản lý dự án sẽ báo giá trực tiếp theo tình hình xe và cửa khẩu.',
    submitInquiry: 'Gửi yêu cầu báo giá →',
    withLoading: (h) => `Thời gian đã gồm xếp dỡ ${h} h`,
    withRest: (h) => ` · Tài xế nghỉ ${h} h`,
    footNote: 'Số km và thời gian là giá trị ước tính của công cụ tuyến; thực tế phụ thuộc thông quan cửa khẩu, tình trạng đường và thời tiết.',
  },
  internal: {
    kicker: 'Kết quả tính · Cách tính chi phí nội bộ',
    transport: 'Chi phí vận chuyển',
    extra: 'Phụ phí và đường vòng',
    totals: 'Tổng hợp và chỉ số',
    items: {
      distance: 'Chi phí quãng đường',
      time: 'Chi phí thời gian',
      fuel: 'Chi phí nhiên liệu',
      loading: 'Phí xếp dỡ',
      insurance: 'Phí bảo hiểm',
      toll: 'Phí đường',
      misc: 'Chi phí khác',
      body: 'Phụ phí thùng xe',
      restricted: 'Đường vòng khu hạn chế',
      construction: 'Đường vòng đoạn thi công',
      mountain: 'Đoạn đường núi',
      port: 'Phụ phí cửa khẩu',
      fixed: 'Phí cố định',
      total: 'Tổng chi phí',
      perKm: 'Chi phí mỗi km',
      perTonKm: 'Chi phí tấn-km',
      perVehicle: 'Chi phí mỗi xe',
      utilisation: 'Mức sử dụng tải',
      vehicles: 'Số xe',
      matched: 'Loại xe khớp',
    },
    unitVehicles: (n) => `${n} xe`,
    tableCap: 'Chi phí từng mục (VND, công cụ xuất trực tiếp)',
    thItem: 'Mục',
    thValue: 'Giá trị',
    footNote: 'Cách tính chi phí do công cụ xuất trực tiếp, chưa gồm lợi nhuận và giá bán; báo giá đối ngoại phải tính thêm hệ số giá bán của công ty, không chuyển tiếp trang này.',
  },
};

const EN: Dict = {
  public: {
    kicker: 'Estimate result · Reference',
    distance: 'Distance',
    duration: 'Duration',
    vehicles: 'Vehicles',
    vehicle: 'Vehicle type',
    autoMatch: 'Auto-matched by system',
    payload: (t) => `· Payload ${t} t`,
    unitVehicles: 'vehicles',
    priceRange: 'Reference freight range',
    price: 'Reference freight',
    toAria: 'to',
    priceNote: 'Includes fuel, tolls and driver cost; excludes loading, border-gate handling, insurance and special operations. Final figures are confirmed by a project manager.',
    pendingRange: 'Reference range requires project-manager confirmation',
    pendingRangeBody: 'The selling-price coefficient for this route has not been entered into the system; distance and vehicle count are already calculated. Send us the requirement and a project manager will quote directly based on vehicles and border conditions.',
    submitInquiry: 'Submit inquiry →',
    withLoading: (h) => `Duration includes loading ${h} h`,
    withRest: (h) => ` · driver rest ${h} h`,
    footNote: 'Distance and duration are route-engine estimates; actual figures depend on border clearance, road conditions and weather.',
  },
  internal: {
    kicker: 'Estimate result · Internal cost basis',
    transport: 'Transport cost',
    extra: 'Surcharges and detours',
    totals: 'Totals and metrics',
    items: {
      distance: 'Distance cost',
      time: 'Time cost',
      fuel: 'Fuel cost',
      loading: 'Loading fee',
      insurance: 'Insurance',
      toll: 'Tolls',
      misc: 'Other costs',
      body: 'Body surcharge',
      restricted: 'Restricted-zone detour',
      construction: 'Roadworks detour',
      mountain: 'Mountain section',
      port: 'Border surcharge',
      fixed: 'Fixed fee',
      total: 'Total cost',
      perKm: 'Cost per km',
      perTonKm: 'Cost per ton-km',
      perVehicle: 'Cost per vehicle',
      utilisation: 'Capacity utilisation',
      vehicles: 'Vehicles',
      matched: 'Matched vehicle type',
    },
    unitVehicles: (n) => `${n} vehicles`,
    tableCap: 'Itemised cost (VND, direct from engine)',
    thItem: 'Item',
    thValue: 'Amount',
    footNote: 'Costs come directly from the engine and exclude margin and selling mark-up; external quotes must apply the company selling coefficient — do not forward this page as-is.',
  },
};

export function resultsText(lang: Lang): Dict {
  if (lang === 'vi') return VI;
  if (lang === 'en') return EN;
  return ZH;
}
