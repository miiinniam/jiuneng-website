/**
 * 助手界面文案（中 / 越 / 英）。
 *
 * 为什么自己写而不用站点 i18n：/quote 是独立入口（quote.html），
 * 但语言来源要和官网一致 —— 统一走 `detectLang()`（?lang= → localStorage:jiuneng-lang → 浏览器语言 → zh）。
 * 这里只管助手窗、工作台卡片、货类名这三块，页面其余文案仍由站点自己管。
 *
 * 新增语种：在 LANGS 里加一种，补一份同结构对象即可（缺的键会回落到中文）。
 */
export type Lang = 'zh' | 'vi' | 'en';

type Dict = {
  header: { title: string; online: string; newChat: string; close: string };
  welcome: {
    title: string;
    lede: string;
    /** 一句话说明「本助手 vs 官网咨询助手」的分工 */
    vs: string;
    quick: string;
    note: string;
    entries: { n: string; t: string; s: string; q: string }[];
  };
  role: { you: string; assistant: string };
  composer: { placeholder: string; send: string; stop: string; clear: string; thinking: string };
  msg: { copy: string; copied: string; empty: string; failed: string };
  ws: {
    plan: string; computed: string; from: string; to: string; km: string; hours: string;
    vehicle: string; count: string; cargo: string; weight: string; viewMap: string; editRoute: string;
    cost: string; item: string; amount: string; total: string; editDetail: string; addFee: string;
    done: string; undo: string; modified: string; costTotal: string; internalOnly: string;
    estimate: string; pending: string; pendingMsg: string; perVehicle: string; rate: string;
    recalc: string; changeVehicle: string; copyQuote: string; requestQuote: string;
    noticePublic: string[]; noticeInternal: string[]; contactPublicT: string; contactPublicD: string;
    contactInternalT: string; contactInternalD: string; contactCtaPublic: string; contactCtaInternal: string;
    baseNote: string; drift: (sum: string, diff: string) => string; scopePending: string; scopeEstimate: string; scopeCost: string;
    /** 说明块标题 */
    noticeTitle: string; noticeTitleInternal: string;
    pendingDetail: string; publicNote: string; internalNote: string;
  };
  /** 费用行名（按引擎 breakdown 的 key） */
  costLabels: Record<string, string>;
  cargo: Record<string, string>;
};

const zh: Dict = {
  header: { title: '报价助手', online: 'AI · 报价测算', newChat: '新建对话', close: '关闭助手' },
  welcome: {
    title: '您好，欢迎使用玖能在线物流咨询。',
    lede: '告诉我们货物、起运地、目的地与运输要求，助手会给出初步方案与费用参考；确认路线后还会把里程、车型直接算出来。',
    vs: '这是报价助手：只做运输测算（里程／车型／车数／费用参考）；服务咨询、流程与单证问题请用官网右下角的「咨询助手」。',
    quick: '先了解我能做什么',
    note: 'AI 给出的费用为初步参考，最终以正式确认为准。',
    entries: [
      { n: '01', t: '这个助手能做什么', s: '支持哪些运输方式、能算出什么', q: '这个报价助手能帮我做什么？支持哪些运输方式的测算？' },
      { n: '02', t: '报价需要哪些信息', s: '起终点、货物、车型要填到什么程度', q: '用这个助手做报价，我需要提供哪些信息？' },
      { n: '03', t: '结果怎么用', s: '算出来的是不是正式报价，下一步怎么走', q: '算出来的里程和费用是正式报价吗？下一步该怎么走？' },
    ],
  },
  role: { you: '你', assistant: '助手' },
  composer: { placeholder: 'Enter 发送，Shift + Enter 换行', send: '发送', stop: '停止', clear: '清空对话', thinking: '正在整理…' },
  msg: { copy: '复制', copied: '已复制', empty: '（这一轮没有返回内容，可以换个问法再试）', failed: 'AI 助手暂时不可用，请稍后再试' },
  ws: {
    plan: '01 · 运输方案', computed: '已计算', from: '起运地', to: '目的地', km: '运输距离', hours: '预计时长',
    vehicle: '车型', count: '车辆数', cargo: '货物', weight: '重量', viewMap: '查看路线图', editRoute: '修改起终点',
    cost: '02 · 费用明细', item: '费用项目', amount: '金额', total: '合计', editDetail: '编辑明细',
    addFee: '新增费用', done: '完成', undo: '撤销修改', modified: '已修改 · 未回写引擎',
    costTotal: '03 · 成本合计', internalOnly: '内部口径', estimate: '预估', pending: '待核定',
    pendingMsg: '参考价区间需项目经理核定', perVehicle: '单车', rate: '汇率',
    recalc: '重新计算', changeVehicle: '更换车型', copyQuote: '复制报价', requestQuote: '提交询价',
    noticeTitle: '03 · 重要说明', noticeTitleInternal: '04 · 口径说明',
    pendingDetail: '里程与车数已算出，售价系数尚未录入系统。把需求发给我们，按车型与口岸情况直接给价。',
    publicNote: '初步测算 · 非正式报价 · 非时效承诺。',
    internalNote: '成本口径，仅内部可见。人工修改只在本页生效，不会回写引擎。',
    noticePublic: [
      '以上为初步估算，不含报关、口岸操作、保险与特种作业费用。',
      '大件/超限货物可能需要额外许可与吊装方案，费用另计。',
      '最终报价与运输安排以项目经理书面确认为准。',
    ],
    noticeInternal: [
      '本页金额为成本口径，不含利润与对客加价。',
      '人工修改只在本页生效，不写回引擎，刷新即恢复。',
      '对外报价须走项目经理核定，不要把本页数字直接发给客户。',
    ],
    contactPublicT: '需要正式报价？',
    contactPublicD: '把需求发给我们的物流团队，按车型、口岸与装卸方案出一份正式报价单。',
    contactInternalT: '需要对外正式报价？',
    contactInternalD: '把这份成本交给项目经理，按客户口径出一份正式报价单。',
    contactCtaPublic: '提交正式询价 →',
    contactCtaInternal: '转项目经理 →',
    baseNote: '本卡片数字由路线与报价引擎计算；若与上方对话中的估算不一致，以本卡片为准。',
    drift: (sum, diff) => `分项合计 ${sum}，与引擎合计相差 ${diff}（引擎按车型/车数做了合并折算，以合计为准）。`,
    scopePending: '参考运费', scopeEstimate: '参考运费', scopeCost: '成本合计',
  },
  costLabels: {
    cost_distance: '距离运费', cost_time: '人工工时', cost_fuel: '燃油', cost_fixed: '固定调度费',
    cost_body_surcharge: '车型附加', cost_toll: '路桥费', cost_loading: '装卸', cost_insurance: '保险',
    cost_port: '口岸操作', cost_restricted_zone: '限行区', cost_construction_zone: '施工绕行',
    cost_mountain_road: '山路附加', cost_misc: '杂费',
  },
  cargo: {
    normal: '普通货物', cold_chain: '冷链', hazardous: '危险品', oversized: '超限货',
    heavy_equipment: '工程机械', other: '其他',
  },
};

const vi: Dict = {
  header: { title: 'Trợ lý báo giá', online: 'AI · tính cước', newChat: 'Cuộc trò chuyện mới', close: 'Đóng' },
  welcome: {
    title: 'Xin chào, đây là trợ lý logistics của JIUNENG.',
    lede: 'Cho chúng tôi biết loại hàng, điểm đi, điểm đến và yêu cầu vận chuyển. Trợ lý sẽ đưa ra phương án sơ bộ và chi phí tham khảo; khi xác định được tuyến, quãng đường và loại xe sẽ được tính trực tiếp.',
    vs: 'Đây là trợ lý báo giá: chỉ tính vận tải (quãng đường / loại xe / số xe / chi phí tham khảo). Câu hỏi về dịch vụ, quy trình, chứng từ xin dùng «Trợ lý tư vấn» ở góc phải website.',
    quick: 'Trợ lý này làm được gì',
    note: 'Chi phí do AI đưa ra chỉ để tham khảo, giá trị cuối cùng theo xác nhận chính thức.',
    entries: [
      { n: '01', t: 'Trợ lý này làm được gì', s: 'Hỗ trợ những loại vận tải nào, tính được gì', q: 'Trợ lý báo giá này giúp tôi được những gì? Hỗ trợ tính cước cho những loại vận tải nào?' },
      { n: '02', t: 'Cần cung cấp thông tin gì', s: 'Điểm đi/đến, hàng hoá, loại xe cần rõ đến đâu', q: 'Để báo giá bằng trợ lý này, tôi cần cung cấp những thông tin gì?' },
      { n: '03', t: 'Kết quả dùng thế nào', s: 'Có phải báo giá chính thức không, bước tiếp theo', q: 'Quãng đường và chi phí tính ra có phải báo giá chính thức không? Bước tiếp theo là gì?' },
    ],
  },
  role: { you: 'Bạn', assistant: 'Trợ lý' },
  composer: { placeholder: 'Enter để gửi, Shift + Enter để xuống dòng', send: 'Gửi', stop: 'Dừng', clear: 'Xoá hội thoại', thinking: 'Đang tổng hợp…' },
  msg: { copy: 'Sao chép', copied: 'Đã sao chép', empty: '（Lượt này không có nội dung, bạn thử hỏi cách khác nhé）', failed: 'Trợ lý tạm thời không khả dụng, vui lòng thử lại sau' },
  ws: {
    plan: '01 · Phương án vận chuyển', computed: 'Đã tính', from: 'Điểm đi', to: 'Điểm đến', km: 'Quãng đường', hours: 'Thời gian dự kiến',
    vehicle: 'Loại xe', count: 'Số xe', cargo: 'Hàng hoá', weight: 'Khối lượng', viewMap: 'Xem tuyến đường', editRoute: 'Sửa điểm đi/đến',
    cost: '02 · Chi tiết chi phí', item: 'Khoản mục', amount: 'Số tiền', total: 'Tổng', editDetail: 'Sửa chi tiết',
    addFee: 'Thêm khoản', done: 'Xong', undo: 'Hoàn tác', modified: 'Đã sửa · chưa ghi lại vào hệ thống',
    costTotal: '03 · Tổng chi phí', internalOnly: 'Nội bộ', estimate: 'Ước tính', pending: 'Chờ xác nhận',
    pendingMsg: 'Khoảng giá tham khảo cần quản lý dự án xác nhận', perVehicle: 'Mỗi xe', rate: 'Tỷ giá',
    recalc: 'Tính lại', changeVehicle: 'Đổi loại xe', copyQuote: 'Sao chép báo giá', requestQuote: 'Gửi yêu cầu báo giá',
    noticeTitle: '03 · Lưu ý quan trọng', noticeTitleInternal: '04 · Ghi chú nội bộ',
    pendingDetail: 'Đã tính được quãng đường và số xe, hệ số giá bán chưa được nhập vào hệ thống. Hãy gửi yêu cầu, chúng tôi báo giá trực tiếp theo loại xe và cửa khẩu.',
    publicNote: 'Tính toán sơ bộ · không phải báo giá chính thức · không cam kết thời gian.',
    internalNote: 'Giá thành, chỉ nội bộ. Chỉnh sửa chỉ có hiệu lực trên trang này, không ghi lại vào hệ thống.',
    noticePublic: [
      'Trên đây là ước tính sơ bộ, chưa gồm thủ tục hải quan, phí cửa khẩu, bảo hiểm và xếp dỡ đặc biệt.',
      'Hàng quá khổ có thể cần giấy phép và phương án cẩu hạ riêng, chi phí tính thêm.',
      'Báo giá và phương án cuối cùng theo xác nhận bằng văn bản của quản lý dự án.',
    ],
    noticeInternal: [
      'Số liệu trên là giá thành, chưa gồm lợi nhuận và giá bán cho khách.',
      'Chỉnh sửa chỉ có hiệu lực trên trang này, không ghi lại vào hệ thống.',
      'Báo giá ra ngoài phải qua quản lý dự án xác nhận.',
    ],
    contactPublicT: 'Cần báo giá chính thức?',
    contactPublicD: 'Gửi yêu cầu cho đội logistics, chúng tôi sẽ lập báo giá chính thức theo loại xe, cửa khẩu và phương án xếp dỡ.',
    contactInternalT: 'Cần báo giá ra ngoài?',
    contactInternalD: 'Chuyển bảng giá thành này cho quản lý dự án để lập báo giá chính thức.',
    contactCtaPublic: 'Gửi yêu cầu chính thức →',
    contactCtaInternal: 'Chuyển quản lý dự án →',
    baseNote: 'Số liệu trong thẻ do công cụ tuyến đường và báo giá tính; nếu khác với ước tính trong hội thoại, lấy thẻ này làm chuẩn.',
    drift: (sum, diff) => `Tổng các khoản ${sum}, lệch ${diff} so với tổng của hệ thống (hệ thống đã gộp theo loại xe/số xe, lấy tổng làm chuẩn).`,
    scopePending: 'Cước tham khảo', scopeEstimate: 'Cước tham khảo', scopeCost: 'Tổng chi phí',
  },
  costLabels: {
    cost_distance: 'Cước theo quãng đường', cost_time: 'Nhân công / giờ lái', cost_fuel: 'Nhiên liệu',
    cost_fixed: 'Phí điều xe cố định', cost_body_surcharge: 'Phụ phí loại xe', cost_toll: 'Phí cầu đường',
    cost_loading: 'Xếp dỡ', cost_insurance: 'Bảo hiểm', cost_port: 'Phí cửa khẩu',
    cost_restricted_zone: 'Vùng hạn chế', cost_construction_zone: 'Đường tránh thi công',
    cost_mountain_road: 'Phụ phí đường đèo', cost_misc: 'Chi phí khác',
  },
  cargo: {
    normal: 'Hàng thường', cold_chain: 'Hàng lạnh', hazardous: 'Hàng nguy hiểm', oversized: 'Hàng quá khổ',
    heavy_equipment: 'Máy công trình', other: 'Khác',
  },
};

const en: Dict = {
  header: { title: 'Quotation Assistant', online: 'AI · quote engine', newChat: 'New chat', close: 'Close' },
  welcome: {
    title: 'Welcome to JIUNENG logistics support.',
    lede: 'Tell us the cargo, origin, destination and requirements. The assistant will outline a preliminary plan and cost reference; once the route is confirmed, distance and vehicle type are calculated directly.',
    vs: 'This is the quotation assistant: transport calculations only (distance / vehicle / fleet size / cost reference). For service, process or document questions use the Consulting Assistant at the bottom-right of the site.',
    quick: 'What I can do',
    note: 'AI estimates are for reference only and subject to formal confirmation.',
    entries: [
      { n: '01', t: 'What this assistant does', s: 'Which transport modes and outputs it covers', q: 'What can this quotation assistant do? Which transport modes can it calculate?' },
      { n: '02', t: 'What to provide', s: 'How detailed origin, cargo and vehicle inputs must be', q: 'What information do I need to provide to get a quote here?' },
      { n: '03', t: 'How to use the result', s: 'Whether it is a formal quote and what comes next', q: 'Is the distance and cost calculated here a formal quotation? What is the next step?' },
    ],
  },
  role: { you: 'You', assistant: 'Assistant' },
  composer: { placeholder: 'Enter to send, Shift + Enter for a new line', send: 'Send', stop: 'Stop', clear: 'Clear chat', thinking: 'Putting it together…' },
  msg: { copy: 'Copy', copied: 'Copied', empty: '(No content this turn — try rephrasing)', failed: 'The assistant is temporarily unavailable, please try again later' },
  ws: {
    plan: '01 · Transport plan', computed: 'Calculated', from: 'Origin', to: 'Destination', km: 'Distance', hours: 'Est. time',
    vehicle: 'Vehicle', count: 'Vehicles', cargo: 'Cargo', weight: 'Weight', viewMap: 'View route', editRoute: 'Edit route',
    cost: '02 · Cost breakdown', item: 'Item', amount: 'Amount', total: 'Total', editDetail: 'Edit details',
    addFee: 'Add item', done: 'Done', undo: 'Undo changes', modified: 'Edited · not written back',
    costTotal: '03 · Total cost', internalOnly: 'Internal', estimate: 'Estimate', pending: 'Pending',
    pendingMsg: 'The reference price range needs project manager confirmation', perVehicle: 'Per vehicle', rate: 'Rate',
    recalc: 'Recalculate', changeVehicle: 'Change vehicle', copyQuote: 'Copy quotation', requestQuote: 'Request quotation',
    noticeTitle: '03 · Important notes', noticeTitleInternal: '04 · Scope notes',
    pendingDetail: 'Distance and vehicle count are computed; the selling-rate factor is not configured yet. Send us the requirement and we will price it directly by vehicle and border gate.',
    publicNote: 'Preliminary calculation · not a formal quotation · no transit-time commitment.',
    internalNote: 'Cost basis, internal only. Edits apply to this page only and are not written back to the engine.',
    noticePublic: [
      'Preliminary estimate only — excludes customs, border handling, insurance and special operations.',
      'Oversized cargo may require additional permits and lifting plans, priced separately.',
      'Final pricing and arrangements are subject to written confirmation by the project manager.',
    ],
    noticeInternal: [
      'Amounts on this page are cost basis, excluding margin and customer pricing.',
      'Manual edits apply to this page only and are not written back to the engine.',
      'Outbound quotations must be confirmed by the project manager.',
    ],
    contactPublicT: 'Need a formal quotation?',
    contactPublicD: 'Send the requirement to our logistics team for a formal quotation based on vehicle, border crossing and handling.',
    contactInternalT: 'Need an outbound quotation?',
    contactInternalD: 'Hand this cost sheet to the project manager to issue a formal customer quotation.',
    contactCtaPublic: 'Request formal quotation →',
    contactCtaInternal: 'Send to project manager →',
    baseNote: 'Figures in this card come from the routing and pricing engine; if they differ from the chat estimate, this card prevails.',
    drift: (sum, diff) => `Items sum to ${sum}, ${diff} off the engine total (the engine consolidates vehicle/quantity terms; the total prevails).`,
    scopePending: 'Reference freight', scopeEstimate: 'Reference freight', scopeCost: 'Total cost',
  },
  costLabels: {
    cost_distance: 'Distance freight', cost_time: 'Labour hours', cost_fuel: 'Fuel',
    cost_fixed: 'Fixed dispatch', cost_body_surcharge: 'Vehicle surcharge', cost_toll: 'Tolls',
    cost_loading: 'Loading / unloading', cost_insurance: 'Insurance', cost_port: 'Border handling',
    cost_restricted_zone: 'Restricted zones', cost_construction_zone: 'Construction detour',
    cost_mountain_road: 'Mountain road', cost_misc: 'Miscellaneous',
  },
  cargo: {
    normal: 'General cargo', cold_chain: 'Cold chain', hazardous: 'Hazardous', oversized: 'Oversized',
    heavy_equipment: 'Heavy equipment', other: 'Other',
  },
};

const ALL: Record<Lang, Dict> = { zh, vi, en };

export function strings(lang: Lang): Dict {
  return ALL[lang] ?? zh;
}

/** 货类中文化名（未知键原样返回） */
export function cargoName(lang: Lang, key: string): string {
  const d = strings(lang);
  return d.cargo[key] ?? key;
}
