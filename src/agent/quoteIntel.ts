/**
 * 报价问答的三块「真材料」：报价要准备什么资料 / 报价包含哪些费用 / 客服联系方式。
 *
 * 为什么单独成文件：
 *  这三条是官网助手的**默认问题**，客户点一下就会问。答案必须是业务口径，不能靠模型临场编。
 *  放在这里而不是塞进 content.ts 的大对象，是为了让「改口径」只改一个文件、三语并排看得见。
 *
 * 红线：
 *  - 只写**构成**与**资料清单**，不写任何金额（金额只能来自测算引擎的区间或项目经理）。
 *  - 越南侧表述统一「越南本地合作代理网络」，不宣称自营报关/仓储/全境网点。
 */
import type { Lang } from './content';

export type QuoteIntel = {
  docs: {
    title: string;
    intro: string;
    items: { label: string; detail: string }[];
    extra: string;
    note: string;
  };
  fees: {
    title: string;
    intro: string;
    groups: { label: string; items: string[] }[];
    extra: string;
    note: string;
  };
};

const zh: QuoteIntel = {
  docs: {
    title: '报价需要准备的资料',
    intro: '工程设备与大型货物的报价，先看设备本身的信息。按下面几项准备，报价能一次做准：',
    items: [
      { label: '设备名称', detail: '设备的正式叫法，不要只写「机器」' },
      { label: '设备说明', detail: '一句话讲清它是什么、用来做什么' },
      { label: '用途', detail: '在项目里承担什么工作，是否用于生产/施工' },
      { label: '品牌', detail: '制造商或品牌名' },
      { label: '型号', detail: '铭牌或出厂资料上的型号' },
      { label: '货物上张贴的铭牌', detail: '拍铭牌照片，型号、功率、重量常印在铭牌上' },
    ],
    extra: '机器设备与电器类，另需：功率、电压、工作原理、功能说明。',
    note: '另需：件数、单件尺寸与重量、起运地与目的地、期望出运时间 —— 缺这几项无法出正式报价。',
  },
  fees: {
    title: '报价包含的费用',
    intro: '玖能的报价按「中国端 + 跨境干线 + 越南端」分段列，费用构成如下：',
    groups: [
      { label: '运费', items: ['中越干线运输（按车型/车数/里程）', '中国境内段提货运输', '越南境内段派送运输'] },
      { label: '中国端', items: ['报关', '堆场', '换车（换装）', '装卸', '杂费'] },
      { label: '越南端', items: ['清关（经越南本地合作代理网络办理）', '口岸', '堆场', '换车', '装卸', '查验、滞留、吊装按实际情况计'] },
    ],
    extra: '关税、增值税、保险是否包含，按贸易条款（EXW / DAP / DDP）确定，报价单会逐项写明包含与不含。',
    note: '具体金额需按车型、车数、箱型、滞留天数、吊装吨位等参数测算；正式报价由项目经理复核后出具。',
  },
};

const en: QuoteIntel = {
  docs: {
    title: 'What to prepare for a quotation',
    intro: 'For engineering equipment and oversized cargo, the quotation starts from the equipment itself. Prepare these so we can quote accurately in one pass:',
    items: [
      { label: 'Equipment name', detail: 'The proper name, not just “machine”' },
      { label: 'Description', detail: 'One line on what it is and what it does' },
      { label: 'Application', detail: 'Its role on the project — production, construction or otherwise' },
      { label: 'Brand', detail: 'Manufacturer or brand name' },
      { label: 'Model', detail: 'Model as printed on the nameplate or factory documents' },
      { label: 'Nameplate photo', detail: 'Photograph the plate on the cargo — model, power and weight are usually printed there' },
    ],
    extra: 'For machinery and electrical equipment, also provide: power rating, voltage, working principle and functions.',
    note: 'Also needed: number of pieces, dimensions and weight per piece, origin and destination, target shipping window — without these a formal quotation cannot be issued.',
  },
  fees: {
    title: 'What the quotation covers',
    intro: 'JIUNENG quotes in three parts — China side, cross-border leg and Vietnam side:',
    groups: [
      { label: 'Freight', items: ['China–Vietnam line haul (by vehicle type, count, mileage)', 'China inland pickup', 'Vietnam inland delivery'] },
      { label: 'China side', items: ['Export declaration', 'Yard', 'Transloading', 'Loading and unloading', 'Sundries'] },
      { label: 'Vietnam side', items: ['Import clearance (via our local partner agency network)', 'Border port', 'Yard', 'Transloading', 'Loading and unloading', 'Inspection, detention and heavy lift as applicable'] },
    ],
    extra: 'Whether duty, VAT and insurance are included depends on the trade term (EXW / DAP / DDP); the quotation states included and excluded items line by line.',
    note: 'Amounts are calculated from parameters such as vehicle type, vehicle count, container type, detention days and lifting tonnage; the formal quotation is reviewed and issued by a project manager.',
  },
};

const vi: QuoteIntel = {
  docs: {
    title: 'Hồ sơ cần chuẩn bị để báo giá',
    intro: 'Với thiết bị công trình và hàng quá khổ, báo giá bắt đầu từ thông tin thiết bị. Chuẩn bị các mục sau để báo giá chính xác ngay lần đầu:',
    items: [
      { label: 'Tên thiết bị', detail: 'Tên chính thức, không chỉ ghi “máy”' },
      { label: 'Mô tả thiết bị', detail: 'Một câu nêu rõ là gì, dùng để làm gì' },
      { label: 'Mục đích sử dụng', detail: 'Vai trò trong dự án: sản xuất, thi công…' },
      { label: 'Thương hiệu', detail: 'Nhà sản xuất hoặc tên thương hiệu' },
      { label: 'Model', detail: 'Model theo tem nhãn hoặc hồ sơ xuất xưởng' },
      { label: 'Ảnh tem nhãn trên hàng', detail: 'Chụp tem nhãn — model, công suất, trọng lượng thường in ở đó' },
    ],
    extra: 'Với máy móc và thiết bị điện, cần thêm: công suất, điện áp, nguyên lý hoạt động và chức năng.',
    note: 'Ngoài ra cần: số kiện, kích thước và trọng lượng từng kiện, điểm đi – điểm đến, thời gian dự kiến xuất hàng — thiếu các mục này không thể ra báo giá chính thức.',
  },
  fees: {
    title: 'Báo giá bao gồm những khoản nào',
    intro: 'Báo giá của JIUNENG chia ba phần — phía Trung Quốc, chặng xuyên biên giới và phía Việt Nam:',
    groups: [
      { label: 'Cước vận tải', items: ['Vận tải tuyến Trung–Việt (theo loại xe, số xe, số km)', 'Vận tải nội địa Trung Quốc', 'Giao hàng nội địa Việt Nam'] },
      { label: 'Phía Trung Quốc', items: ['Khai báo xuất khẩu', 'Bãi', 'Sang tải / đổi xe', 'Bốc xếp', 'Chi phí lặt vặt'] },
      { label: 'Phía Việt Nam', items: ['Thông quan nhập khẩu (qua mạng đại lý đối tác tại Việt Nam)', 'Cửa khẩu', 'Bãi', 'Sang tải', 'Bốc xếp', 'Kiểm hóa, lưu bãi, nâng hạ tùy thực tế'] },
    ],
    extra: 'Thuế, VAT và bảo hiểm có bao gồm hay không tùy điều kiện giao hàng (EXW / DAP / DDP); báo giá ghi rõ từng khoản bao gồm và không bao gồm.',
    note: 'Số tiền cụ thể được tính theo loại xe, số xe, loại container, số ngày lưu bãi, tấn nâng hạ…; báo giá chính thức do quản lý dự án thẩm định và phát hành.',
  },
};

export const quoteIntel: Record<Lang, QuoteIntel> = { zh, en, vi };
