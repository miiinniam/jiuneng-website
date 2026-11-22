/**
 * /quote 报价工具的页面壳语言包（页头 / 步骤条 / 向导三步 / 成本参数）。
 *
 * 与 `strings.ts` 分工：那边管助手窗与工作台卡片，这边管向导与页面骨架。
 * 语言来源一致：`detectLang()`（?lang= → localStorage:jiuneng-lang → 浏览器 → zh）。
 */
import type { Lang } from './strings';

type Cond = { label: string; desc: string };

type Dict = {
  app: {
    stepAria: string;
    /** 公开版步骤名（5 步：路线 → 货物分类 → 重量与明细 → 车型 → 提交确认），下标即 QuoteApp 的 STEP_KEYS 键 */
    stepLabels: [string, string, string, string, string];
    /** 内部版步骤名（6 步：公开版基础上，提交确认前多一步成本参数） */
    stepLabelsInternal: [string, string, string, string, string, string];
    internalTag: string;
    publicTag: string;
    keyLoaded: string;
    keyNeeded: string;
    aiBtn: string;
    titleInternal: string;
    titlePublic: string;
    ledeInternal: string;
    ledePublic: string;
    footNote: string;
    prev: string;
    next: string;
    submitInternal: string;
    submitPublic: string;
    /** 最后一步（提交确认页）的按钮文案：公开/内部统一叫「提交测算」 */
    submitFinal: string;
    submitting: string;
    reset: string;
    busyNote: string;
    failTag: string;
    retry: string;
    errSubmit: string;
    stepMissing: string;
    refFail: string;
    resultPublic: string;
    resultInternal: string;
    editCond: string;
    badResult: string;
    batchLoading: string;
  };
  route: {
    origin: string;
    dest: string;
    required: string;
    searchOrigin: string;
    searchDest: string;
    originPh: string;
    destPh: string;
    lat: string;
    lon: string;
    waypoints: (n: number) => string;
    addWaypoint: string;
    waypointNote: string;
    waypointNo: (n: string) => string;
    removeWaypoint: (n: number) => string;
    remove: string;
    searchWaypoint: (n: number) => string;
    waypointPh: string;
    mapPick: string;
  };
  cargo: {
    types: { normal: string; cold_chain: string; hazardous: string; oversized: string; heavy_equipment: string; other: string };
    weight: string;
    weightPhTon: string;
    weightPhKg: string;
    unitTon: string;
    unitKg: string;
    unitHintTon: string;
    unitHintKg: string;
    volume: string;
    volumePhRequired: string;
    volumePhOptional: string;
    type: string;
    typeCount: (n: number) => string;
    loading: string;
    typePh: string;
    typePhLoading: string;
    value: string;
    valueHint: string;
    valuePh: string;
    items: (n: number) => string;
    addItem: string;
    itemsHint: string;
    itemNo: (n: string) => string;
    removeItem: (n: number) => string;
    remove: string;
    name: string;
    namePh: string;
    qty: string;
    length: string;
    width: string;
    height: string;
    itemWeight: string;
    stack: string;
    stackable: string;
    unstackable: string;
    unstackableDesc: string;
  };
  vehicle: {
    mode: string;
    full: string;
    fullHint: string;
    consolidated: string;
    consolidatedHint: string;
    type: string;
    typeCount: (n: number) => string;
    refLoading: string;
    fleetEmpty: string;
    fleetLoading: string;
    fits: string;
    load: (t: string) => string;
    volume: (v: string) => string;
    consolidatedMode: string;
    noWeight: string;
    noVolume: string;
    consolidatedNote: string;
    condLabel: string;
    conds: {
      returnEmpty: Cond;
      loading: Cond;
      avoidRestricted: Cond;
      avoidConstruction: Cond;
      mountain: Cond;
    };
  };
  cost: {
    intro: string;
    fuel: string;
    wage: string;
    toll: string;
    misc: string;
    phDefault: string;
    phZero: string;
    footNote: string;
  };
};

const ZH: Dict = {
  app: {
    stepAria: '报价步骤',
    stepLabels: ['路线', '货物分类', '重量与明细', '车型', '提交测算'],
    stepLabelsInternal: ['路线', '货物分类', '重量与明细', '车型', '成本参数', '提交测算'],
    internalTag: '内部报价 · 成本测算',
    publicTag: '在线报价 · 路线估算',
    keyLoaded: '口令已加载',
    keyNeeded: '需内部口令',
    aiBtn: 'AI 助手',
    titleInternal: '内部报价测算',
    titlePublic: '填五步，拿到可执行的运价与交期',
    ledeInternal: '内部版：多一步成本参数，出结果含全量分项成本与吨公里口径，供项目经理定价与复核。',
    ledePublic: '系统按真实配车口径测算：先配车，再判许可档位与办证天数，最后出运价区间。',
    footNote: '报价工具与订单系统同源；口径与车型库由玖能国际统一维护。',
    prev: '← 上一步',
    next: '下一步 →',
    submitInternal: '开始测算（内部口径）',
    submitPublic: '开始测算',
    submitFinal: '提交测算',
    submitting: '测算中…',
    reset: '清空重填',
    busyNote: '测算中，首次可能需 30–60 秒（引擎冷启动）',
    failTag: '测算失败',
    retry: '重试',
    errSubmit: '测算失败，请稍后重试',
    stepMissing: '请把本步必填项补全',
    refFail: '参考数据（车型库 / 货物类型）加载失败，刷新页面后重试。',
    resultPublic: '公开口径 · 里程与参考价',
    resultInternal: '内部口径 · 成本分项',
    editCond: '修改条件 →',
    badResult: '结果格式无法识别，请重试或联系技术维护。',
    batchLoading: '批量面板加载中…',
  },
  route: {
    origin: '起点',
    dest: '终点',
    required: '必填',
    searchOrigin: '搜索起点地址',
    searchDest: '搜索终点地址',
    originPh: '城市或地址，如 河内 还剑郡',
    destPh: '城市或地址，如 广西 凭祥 友谊关',
    lat: '纬度',
    lon: '经度',
    waypoints: (n) => `途经点 · ${n}`,
    addWaypoint: '+ 添加途经点',
    waypointNote: '不填则按直达计算；口岸、装卸点若需固定，请在此加入。',
    waypointNo: (n) => `途经 ${n}`,
    removeWaypoint: (n) => `删除途经点 ${n}`,
    remove: '删除',
    searchWaypoint: (n) => `搜索途经点 ${n}`,
    waypointPh: '途经城市或口岸',
    mapPick: '地图选点',
  },
  cargo: {
    types: { normal: '普通货物', cold_chain: '冷链 / 易腐', hazardous: '危险品', oversized: '超大件', heavy_equipment: '重型设备', other: '其他' },
    weight: '货物重量',
    weightPhTon: '如 25',
    weightPhKg: '如 25000',
    unitTon: '吨',
    unitKg: '公斤',
    unitHintTon: '单位：吨（提交时换算为 kg）',
    unitHintKg: '单位：公斤',
    volume: '体积',
    volumePhRequired: '拼货必填',
    volumePhOptional: '可选',
    type: '货物类型',
    typeCount: (n) => `${n} 类`,
    loading: '加载中',
    typePh: '请选择',
    typePhLoading: '参考数据加载中…',
    value: '货值',
    valueHint: 'VND · 可选',
    valuePh: '用于保险估算',
    items: (n) => `单件明细 · ${n}`,
    addItem: '+ 添加单件',
    itemsHint: '长件 / 超宽 / 不可堆叠时填写，用于精确计算车辆数；不填则按重量与体积估算。',
    itemNo: (n) => `单件 ${n}`,
    removeItem: (n) => `删除单件 ${n}`,
    remove: '删除',
    name: '名称',
    namePh: '如 变压器 / 钢梁',
    qty: '件数',
    length: '长',
    width: '宽',
    height: '高',
    itemWeight: '单件重量',
    stack: '堆叠',
    stackable: '可堆叠',
    unstackable: '不可堆叠',
    unstackableDesc: '按地板面积计',
  },
  vehicle: {
    mode: '运输模式',
    full: '整车',
    fullHint: '指定车型，单独一台车承运',
    consolidated: '拼货',
    consolidatedHint: '系统按体积/重量配最省的车型',
    type: '车型',
    typeCount: (n) => `${n} 款`,
    refLoading: '参考数据加载中',
    fleetEmpty: '车型库为空，请刷新页面或联系项目经理。',
    fleetLoading: '车型库加载中…',
    fits: '适配本货型',
    load: (t) => `载重 ${t} t`,
    volume: (v) => `容积 ${v}`,
    consolidatedMode: '拼货模式',
    noWeight: '未填重量',
    noVolume: '未填体积',
    consolidatedNote: '系统会在装得下这批货的车型里，自动挑总价最低的一款，不用手动选车型。',
    condLabel: '运输条件',
    conds: {
      returnEmpty: { label: '空车返回', desc: '目的地无回程货，按回程距离计费' },
      loading: { label: '需要装卸', desc: '含装卸工时与机械费' },
      avoidRestricted: { label: '避开限行区', desc: '市区限行 / 限重路段绕行' },
      avoidConstruction: { label: '避开施工路段', desc: '封闭施工路段绕行' },
      mountain: { label: '经山区道路', desc: '坡陡弯急，按特种路段加价' },
    },
  },
  cost: {
    intro: '内部口径：这四项会覆盖引擎默认成本参数，只影响成本分项，不改变里程与车数。',
    fuel: '柴油价',
    wage: '司机时薪',
    toll: '过路费率',
    misc: '杂费',
    phDefault: '留空用默认',
    phZero: '留空按 0',
    footNote: '留空则用引擎默认：油价取参考数据里的实时油价，时薪与过路费率取车型库内置值。',
  },
};

const VI: Dict = {
  app: {
    stepAria: 'Các bước báo giá',
    stepLabels: ['Tuyến', 'Phân loại hàng', 'Trọng lượng & chi tiết', 'Loại xe', 'Gửi tính toán'],
    stepLabelsInternal: ['Tuyến', 'Phân loại hàng', 'Trọng lượng & chi tiết', 'Loại xe', 'Thông số chi phí', 'Gửi tính toán'],
    internalTag: 'Báo giá nội bộ · Tính chi phí',
    publicTag: 'Báo giá trực tuyến · Ước tính tuyến',
    keyLoaded: 'Đã nạp mật lệnh',
    keyNeeded: 'Cần mật lệnh nội bộ',
    aiBtn: 'Trợ lý AI',
    titleInternal: 'Tính báo giá nội bộ',
    titlePublic: 'Điền năm bước, nhận giá và thời gian giao thực thi',
    ledeInternal: 'Bản nội bộ: thêm một bước thông số chi phí, kết quả gồm toàn bộ chi phí từng mục và cách tính tấn-km, phục vụ quản lý dự án định giá và kiểm tra.',
    ledePublic: 'Hệ thống tính theo phương án xếp xe thực tế: xếp xe trước, rồi xác định mức giấy phép và số ngày làm thủ tục, cuối cùng ra khoảng giá.',
    footNote: 'Công cụ báo giá cùng nguồn với hệ thống đơn hàng; cách tính và danh mục xe do JIUNENG quản lý thống nhất.',
    prev: '← Bước trước',
    next: 'Bước tiếp →',
    submitInternal: 'Bắt đầu tính (cách tính nội bộ)',
    submitPublic: 'Bắt đầu tính',
    submitFinal: 'Gửi tính toán',
    submitting: 'Đang tính…',
    reset: 'Xóa và nhập lại',
    busyNote: 'Đang tính, lần đầu có thể mất 30–60 giây (khởi động công cụ)',
    failTag: 'Tính thất bại',
    retry: 'Thử lại',
    errSubmit: 'Tính toán thất bại, vui lòng thử lại sau',
    stepMissing: 'Vui lòng điền đủ các mục bắt buộc của bước này',
    refFail: 'Tải dữ liệu tham khảo (danh mục xe / loại hàng) thất bại, vui lòng làm mới trang và thử lại.',
    resultPublic: 'Cách tính công khai · Số km và giá tham khảo',
    resultInternal: 'Cách tính nội bộ · Chi phí từng mục',
    editCond: 'Sửa điều kiện →',
    badResult: 'Không nhận dạng được định dạng kết quả, vui lòng thử lại hoặc liên hệ bộ phận kỹ thuật.',
    batchLoading: 'Đang tải bảng hàng loạt…',
  },
  route: {
    origin: 'Điểm đi',
    dest: 'Điểm đến',
    required: 'Bắt buộc',
    searchOrigin: 'Tìm địa chỉ điểm đi',
    searchDest: 'Tìm địa chỉ điểm đến',
    originPh: 'Thành phố hoặc địa chỉ, VD Hà Nội Quận Hoàn Kiếm',
    destPh: 'Thành phố hoặc địa chỉ, VD Quảng Tây Bằng Tường Hữu Nghị Quan',
    lat: 'Vĩ độ',
    lon: 'Kinh độ',
    waypoints: (n) => `Điểm dừng · ${n}`,
    addWaypoint: '+ Thêm điểm dừng',
    waypointNote: 'Để trống thì tính tuyến trực tiếp; nếu cần cố định cửa khẩu, điểm xếp dỡ thì thêm ở đây.',
    waypointNo: (n) => `Đi qua ${n}`,
    removeWaypoint: (n) => `Xóa điểm dừng ${n}`,
    remove: 'Xóa',
    searchWaypoint: (n) => `Tìm điểm dừng ${n}`,
    waypointPh: 'Thành phố hoặc cửa khẩu đi qua',
    mapPick: 'Chọn trên bản đồ',
  },
  cargo: {
    types: { normal: 'Hàng thường', cold_chain: 'Chuỗi lạnh / dễ hỏng', hazardous: 'Hàng nguy hiểm', oversized: 'Hàng quá khổ', heavy_equipment: 'Thiết bị hạng nặng', other: 'Khác' },
    weight: 'Trọng lượng hàng',
    weightPhTon: 'VD 25',
    weightPhKg: 'VD 25000',
    unitTon: 'tấn',
    unitKg: 'kg',
    unitHintTon: 'Đơn vị: tấn (khi gửi đổi sang kg)',
    unitHintKg: 'Đơn vị: kg',
    volume: 'Thể tích',
    volumePhRequired: 'Bắt buộc khi ghép hàng',
    volumePhOptional: 'Tùy chọn',
    type: 'Loại hàng',
    typeCount: (n) => `${n} loại`,
    loading: 'Đang tải',
    typePh: 'Vui lòng chọn',
    typePhLoading: 'Đang tải dữ liệu tham khảo…',
    value: 'Giá trị hàng',
    valueHint: 'VND · Tùy chọn',
    valuePh: 'Dùng để ước tính bảo hiểm',
    items: (n) => `Chi tiết từng kiện · ${n}`,
    addItem: '+ Thêm một kiện',
    itemsHint: 'Điền khi hàng dài / quá rộng / không xếp chồng, để tính chính xác số xe; bỏ trống thì ước theo trọng lượng và thể tích.',
    itemNo: (n) => `Kiện ${n}`,
    removeItem: (n) => `Xóa kiện ${n}`,
    remove: 'Xóa',
    name: 'Tên',
    namePh: 'VD máy biến áp / dầm thép',
    qty: 'Số kiện',
    length: 'Dài',
    width: 'Rộng',
    height: 'Cao',
    itemWeight: 'Trọng lượng mỗi kiện',
    stack: 'Xếp chồng',
    stackable: 'Xếp chồng được',
    unstackable: 'Không xếp chồng',
    unstackableDesc: 'Tính theo diện tích sàn',
  },
  vehicle: {
    mode: 'Phương thức vận chuyển',
    full: 'Nguyên xe',
    fullHint: 'Chỉ định loại xe, một xe chở riêng',
    consolidated: 'Ghép hàng',
    consolidatedHint: 'Hệ thống chọn loại xe tiết kiệm nhất theo thể tích/trọng lượng',
    type: 'Loại xe',
    typeCount: (n) => `${n} loại`,
    refLoading: 'Đang tải dữ liệu tham khảo',
    fleetEmpty: 'Danh mục xe trống, vui lòng làm mới trang hoặc liên hệ quản lý dự án.',
    fleetLoading: 'Đang tải danh mục xe…',
    fits: 'Phù hợp loại hàng này',
    load: (t) => `Tải trọng ${t} t`,
    volume: (v) => `Dung tích ${v}`,
    consolidatedMode: 'Chế độ ghép hàng',
    noWeight: 'Chưa nhập trọng lượng',
    noVolume: 'Chưa nhập thể tích',
    consolidatedNote: 'Hệ thống tự chọn loại xe có tổng giá thấp nhất trong số xe chở được lô hàng, không cần chọn thủ công.',
    condLabel: 'Điều kiện vận chuyển',
    conds: {
      returnEmpty: { label: 'Xe về rỗng', desc: 'Điểm đến không có hàng về, tính theo quãng đường về' },
      loading: { label: 'Cần xếp dỡ', desc: 'Gồm giờ công xếp dỡ và chi phí máy' },
      avoidRestricted: { label: 'Tránh khu hạn chế', desc: 'Đi vòng qua đoạn hạn chế giờ / tải trọng nội đô' },
      avoidConstruction: { label: 'Tránh đoạn thi công', desc: 'Đi vòng qua đoạn thi công đang đóng' },
      mountain: { label: 'Qua đường núi', desc: 'Dốc cao cua gấp, tính giá đoạn đặc biệt' },
    },
  },
  cost: {
    intro: 'Cách tính nội bộ: bốn mục này ghi đè thông số chi phí mặc định của công cụ, chỉ ảnh hưởng chi phí từng mục, không đổi số km và số xe.',
    fuel: 'Giá dầu diesel',
    wage: 'Lương giờ tài xế',
    toll: 'Mức phí đường',
    misc: 'Chi phí khác',
    phDefault: 'Để trống dùng mặc định',
    phZero: 'Để trống tính 0',
    footNote: 'Để trống thì dùng mặc định của công cụ: giá dầu lấy theo giá thời gian thực trong dữ liệu tham khảo, lương giờ và phí đường lấy theo giá trị có sẵn trong danh mục xe.',
  },
};

const EN: Dict = {
  app: {
    stepAria: 'Quote steps',
    stepLabels: ['Route', 'Cargo class', 'Weight & details', 'Vehicle', 'Submit estimate'],
    stepLabelsInternal: ['Route', 'Cargo class', 'Weight & details', 'Vehicle', 'Cost parameters', 'Submit estimate'],
    internalTag: 'Internal quote · Cost estimate',
    publicTag: 'Online quote · Route estimate',
    keyLoaded: 'Passphrase loaded',
    keyNeeded: 'Internal passphrase required',
    aiBtn: 'AI assistant',
    titleInternal: 'Internal quote estimate',
    titlePublic: 'Five steps to an executable rate and schedule',
    ledeInternal: 'Internal version: one extra cost-parameter step; results include the full itemised cost and the ton-kilometre basis for project managers to price and review.',
    ledePublic: 'Calculated on real fleet matching: match vehicles first, then determine the permit tier and processing days, and finally the price range.',
    footNote: 'The quote tool shares its source with the order system; definitions and the vehicle library are maintained centrally by JIUNENG.',
    prev: '← Previous',
    next: 'Next →',
    submitInternal: 'Start estimate (internal basis)',
    submitPublic: 'Start estimate',
    submitFinal: 'Submit estimate',
    submitting: 'Estimating…',
    reset: 'Clear and restart',
    busyNote: 'Estimating; the first run may take 30–60 seconds (engine cold start)',
    failTag: 'Estimate failed',
    retry: 'Retry',
    errSubmit: 'Estimate failed, please retry shortly',
    stepMissing: 'Please complete the required fields in this step',
    refFail: 'Could not load reference data (vehicle library / cargo types). Refresh the page and retry.',
    resultPublic: 'Public basis · Distance and reference price',
    resultInternal: 'Internal basis · Cost breakdown',
    editCond: 'Edit conditions →',
    badResult: 'Unrecognised result format. Please retry or contact technical support.',
    batchLoading: 'Loading batch panel…',
  },
  route: {
    origin: 'Origin',
    dest: 'Destination',
    required: 'Required',
    searchOrigin: 'Search origin address',
    searchDest: 'Search destination address',
    originPh: 'City or address, e.g. Hanoi Hoan Kiem',
    destPh: 'City or address, e.g. Guangxi Pingxiang Friendship Pass',
    lat: 'Latitude',
    lon: 'Longitude',
    waypoints: (n) => `Waypoints · ${n}`,
    addWaypoint: '+ Add waypoint',
    waypointNote: 'Leave empty for a direct route; add border gates or loading points here if they must be fixed.',
    waypointNo: (n) => `Via ${n}`,
    removeWaypoint: (n) => `Remove waypoint ${n}`,
    remove: 'Remove',
    searchWaypoint: (n) => `Search waypoint ${n}`,
    waypointPh: 'City or border gate on the way',
    mapPick: 'Pick on map',
  },
  cargo: {
    types: { normal: 'General cargo', cold_chain: 'Cold chain / perishable', hazardous: 'Hazardous', oversized: 'Oversize', heavy_equipment: 'Heavy equipment', other: 'Other' },
    weight: 'Cargo weight',
    weightPhTon: 'e.g. 25',
    weightPhKg: 'e.g. 25000',
    unitTon: 'tonnes',
    unitKg: 'kg',
    unitHintTon: 'Unit: tonnes (converted to kg on submit)',
    unitHintKg: 'Unit: kg',
    volume: 'Volume',
    volumePhRequired: 'Required for consolidated',
    volumePhOptional: 'Optional',
    type: 'Cargo type',
    typeCount: (n) => `${n} types`,
    loading: 'Loading',
    typePh: 'Please select',
    typePhLoading: 'Loading reference data…',
    value: 'Cargo value',
    valueHint: 'VND · Optional',
    valuePh: 'Used for insurance estimates',
    items: (n) => `Per-piece details · ${n}`,
    addItem: '+ Add a piece',
    itemsHint: 'Fill in for long / over-width / non-stackable pieces to get an exact vehicle count; otherwise it is estimated from weight and volume.',
    itemNo: (n) => `Piece ${n}`,
    removeItem: (n) => `Remove piece ${n}`,
    remove: 'Remove',
    name: 'Name',
    namePh: 'e.g. transformer / steel beam',
    qty: 'Pieces',
    length: 'Length',
    width: 'Width',
    height: 'Height',
    itemWeight: 'Weight per piece',
    stack: 'Stacking',
    stackable: 'Stackable',
    unstackable: 'Not stackable',
    unstackableDesc: 'Charged by floor area',
  },
  vehicle: {
    mode: 'Transport mode',
    full: 'Full truck',
    fullHint: 'Specify a vehicle type; one dedicated vehicle',
    consolidated: 'Consolidated',
    consolidatedHint: 'The system picks the most economical vehicle by volume/weight',
    type: 'Vehicle type',
    typeCount: (n) => `${n} types`,
    refLoading: 'Loading reference data',
    fleetEmpty: 'The vehicle library is empty. Refresh the page or contact a project manager.',
    fleetLoading: 'Loading vehicle library…',
    fits: 'Fits this cargo',
    load: (t) => `Payload ${t} t`,
    volume: (v) => `Capacity ${v}`,
    consolidatedMode: 'Consolidated mode',
    noWeight: 'No weight entered',
    noVolume: 'No volume entered',
    consolidatedNote: 'Among vehicles that fit this cargo, the system automatically picks the one with the lowest total price — no manual selection needed.',
    condLabel: 'Transport conditions',
    conds: {
      returnEmpty: { label: 'Empty return', desc: 'No return cargo; charged by return distance' },
      loading: { label: 'Loading/unloading', desc: 'Includes labour hours and machinery cost' },
      avoidRestricted: { label: 'Avoid restricted zones', desc: 'Detour around city time/weight limits' },
      avoidConstruction: { label: 'Avoid roadworks', desc: 'Detour around closed construction sections' },
      mountain: { label: 'Mountain roads', desc: 'Steep and winding; special-section surcharge' },
    },
  },
  cost: {
    intro: 'Internal basis: these four fields override the engine’s default cost parameters. They affect cost items only — not distance or vehicle count.',
    fuel: 'Diesel price',
    wage: 'Driver hourly wage',
    toll: 'Toll rate',
    misc: 'Miscellaneous',
    phDefault: 'Blank = default',
    phZero: 'Blank = 0',
    footNote: 'Left blank, the engine defaults apply: diesel uses the live price in the reference data, and wage and toll rate use the values built into the vehicle library.',
  },
};

export function shell(lang: Lang): Dict {
  if (lang === 'vi') return VI;
  if (lang === 'en') return EN;
  return ZH;
}

/** 车型大类名（向导"车型"步的分组标题；与引擎 category 键一致）。 */
const VEHICLE_KINDS: Record<Lang, Record<string, string>> = {
  zh: { small_box: '小卡车', flatbed: '平板车', high_side: '高栏车', container: '集装箱车', cold_chain: '冷链车' },
  vi: { small_box: 'Xe tải nhỏ', flatbed: 'Xe sàn phẳng', high_side: 'Xe thành cao', container: 'Xe container', cold_chain: 'Xe lạnh' },
  en: { small_box: 'Light truck', flatbed: 'Flatbed', high_side: 'High-side', container: 'Container truck', cold_chain: 'Refrigerated truck' },
};

export function vehicleKind(lang: Lang, key: string): string {
  return VEHICLE_KINDS[lang][key] ?? key;
}
