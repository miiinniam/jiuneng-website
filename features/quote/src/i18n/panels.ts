/** /quote 模板条 / 批量面板 / AI 助手面板文案（中 / 越 / 英）。 */
import type { Lang } from './strings';

type Dict = {
  tpl: {
    loadFail: string;
    incomplete: string;
    applied: (name: string) => string;
    needName: string;
    limit: (n: number) => string;
    storageWrite: string;
    savedLocal: (name: string) => string;
    savedAs: (name: string) => string;
    saveFail: string;
    storageDelete: string;
    deleted: (name: string | null) => string;
    deleteFail: string;
    groupAria: string;
    labelTpl: string;
    labelLocal: string;
    selectAria: string;
    empty: string;
    selectPh: string;
    namePh: string;
    saving: string;
    save: string;
    cancel: string;
    saveAs: string;
    confirmDelete: string;
    del: string;
  };
  batch: {
    fail: string;
    aria: string;
    title: string;
    download: string;
    processing: string;
    choose: string;
    clear: string;
    hint: string;
    parsed: (n: number) => string;
    quoting: string;
    done: (ok: number, fail: number) => string;
    notSubmitted: (n: number) => string;
    thRow: string;
    thKm: string;
    thTrucks: string;
    thCost: string;
    thError: string;
    note: string;
  };
  chat: {
    emptyReply: string;
    unavailable: string;
    computing: string;
    done: string;
    failed: string;
    aborted: string;
    panelAria: string;
  };
};

const ZH: Dict = {
  tpl: {
    loadFail: '模板读取失败',
    incomplete: '这条模板的数据不完整，无法套用',
    applied: (name) => `已套用「${name}」`,
    needName: '给模板起个名字',
    limit: (n) => `本机最多存 ${n} 条模板，请先删除旧模板`,
    storageWrite: '本机存储写不进去（可能是隐私模式），模板没保存',
    savedLocal: (name) => `已存到本机：${name}`,
    savedAs: (name) => `已存为「${name}」`,
    saveFail: '模板保存失败',
    storageDelete: '本机存储写不进去，模板没删除',
    deleted: (name) => (name ? `已删除「${name}」` : '已删除'),
    deleteFail: '模板删除失败',
    groupAria: '报价模板',
    labelTpl: '模板',
    labelLocal: '本机模板',
    selectAria: '选择模板',
    empty: '（还没有模板）',
    selectPh: '选择模板…',
    namePh: '模板名称',
    saving: '保存中…',
    save: '保存',
    cancel: '取消',
    saveAs: '另存为',
    confirmDelete: '确认删除？',
    del: '删除',
  },
  batch: {
    fail: '批量测算失败，请检查文件后重试',
    aria: '批量测算',
    title: '批量测算（Excel）',
    download: '下载模板',
    processing: '处理中…',
    choose: '选择文件',
    clear: '清空',
    hint: '支持 .xlsx / .xls / .csv，表头必须是模板那一行（中文列名）。第一行表头，第二行起每行一趟货。',
    parsed: (n) => ` · 解析 ${n} 行`,
    quoting: ' · 测算中…',
    done: (ok, fail) => ` · 成功 ${ok} · 失败 ${fail}`,
    notSubmitted: (n) => `这些行没有提交（${n} 行）`,
    thRow: '行',
    thKm: '里程 km',
    thTrucks: '车数',
    thCost: '成本合计',
    thError: '错误',
    note: '列表里的「成本合计」是内部口径，只在这个页面出现，不进公开报价。',
  },
  chat: {
    emptyReply: '（这一轮没有返回内容，可以换个问法再试）',
    unavailable: 'AI 助手暂时不可用，请稍后再试',
    computing: '正在计算…',
    done: '已算完',
    failed: '没算出来',
    aborted: '已中止',
    panelAria: 'AI 报价助手',
  },
};

const VI: Dict = {
  tpl: {
    loadFail: 'Đọc mẫu thất bại',
    incomplete: 'Dữ liệu của mẫu này không đầy đủ, không thể áp dụng',
    applied: (name) => `Đã áp dụng "${name}"`,
    needName: 'Hãy đặt tên cho mẫu',
    limit: (n) => `Máy này chỉ lưu tối đa ${n} mẫu, vui lòng xóa mẫu cũ trước`,
    storageWrite: 'Không ghi được vào bộ nhớ máy (có thể do chế độ riêng tư), mẫu chưa được lưu',
    savedLocal: (name) => `Đã lưu vào máy: ${name}`,
    savedAs: (name) => `Đã lưu thành "${name}"`,
    saveFail: 'Lưu mẫu thất bại',
    storageDelete: 'Không ghi được vào bộ nhớ máy, mẫu chưa bị xóa',
    deleted: (name) => (name ? `Đã xóa "${name}"` : 'Đã xóa'),
    deleteFail: 'Xóa mẫu thất bại',
    groupAria: 'Mẫu báo giá',
    labelTpl: 'Mẫu',
    labelLocal: 'Mẫu trên máy',
    selectAria: 'Chọn mẫu',
    empty: '(chưa có mẫu)',
    selectPh: 'Chọn mẫu…',
    namePh: 'Tên mẫu',
    saving: 'Đang lưu…',
    save: 'Lưu',
    cancel: 'Hủy',
    saveAs: 'Lưu thành mẫu mới',
    confirmDelete: 'Xác nhận xóa?',
    del: 'Xóa',
  },
  batch: {
    fail: 'Tính hàng loạt thất bại, vui lòng kiểm tra tệp và thử lại',
    aria: 'Tính hàng loạt',
    title: 'Tính hàng loạt (Excel)',
    download: 'Tải mẫu',
    processing: 'Đang xử lý…',
    choose: 'Chọn tệp',
    clear: 'Xóa hết',
    hint: 'Hỗ trợ .xlsx / .xls / .csv, dòng tiêu đề phải đúng như mẫu (tên cột tiếng Trung). Dòng 1 là tiêu đề, từ dòng 2 mỗi dòng một chuyến hàng.',
    parsed: (n) => ` · Đã đọc ${n} dòng`,
    quoting: ' · Đang tính…',
    done: (ok, fail) => ` · Thành công ${ok} · Thất bại ${fail}`,
    notSubmitted: (n) => `Các dòng này chưa được gửi (${n} dòng)`,
    thRow: 'Dòng',
    thKm: 'Số km',
    thTrucks: 'Số xe',
    thCost: 'Tổng chi phí',
    thError: 'Lỗi',
    note: '"Tổng chi phí" trong danh sách là cách tính nội bộ, chỉ hiện trên trang này, không vào báo giá công khai.',
  },
  chat: {
    emptyReply: '(Lượt này không trả về nội dung, hãy đổi cách hỏi và thử lại)',
    unavailable: 'Trợ lý AI tạm thời không khả dụng, vui lòng thử lại sau',
    computing: 'Đang tính…',
    done: 'Đã tính xong',
    failed: 'Chưa tính ra',
    aborted: 'Đã dừng',
    panelAria: 'Trợ lý báo giá AI',
  },
};

const EN: Dict = {
  tpl: {
    loadFail: 'Could not load templates',
    incomplete: 'This template’s data is incomplete and cannot be applied',
    applied: (name) => `Applied "${name}"`,
    needName: 'Give the template a name',
    limit: (n) => `This device stores at most ${n} templates; delete an old one first`,
    storageWrite: 'Local storage is not writable (possibly private mode); the template was not saved',
    savedLocal: (name) => `Saved to this device: ${name}`,
    savedAs: (name) => `Saved as "${name}"`,
    saveFail: 'Could not save the template',
    storageDelete: 'Local storage is not writable; the template was not deleted',
    deleted: (name) => (name ? `Deleted "${name}"` : 'Deleted'),
    deleteFail: 'Could not delete the template',
    groupAria: 'Quote templates',
    labelTpl: 'Templates',
    labelLocal: 'Device templates',
    selectAria: 'Select template',
    empty: '(no templates yet)',
    selectPh: 'Select a template…',
    namePh: 'Template name',
    saving: 'Saving…',
    save: 'Save',
    cancel: 'Cancel',
    saveAs: 'Save as',
    confirmDelete: 'Confirm delete?',
    del: 'Delete',
  },
  batch: {
    fail: 'Batch estimate failed; check the file and retry',
    aria: 'Batch estimate',
    title: 'Batch estimate (Excel)',
    download: 'Download template',
    processing: 'Processing…',
    choose: 'Choose file',
    clear: 'Clear',
    hint: 'Supports .xlsx / .xls / .csv; the header row must match the template exactly (Chinese column names). Row 1 is the header, one shipment per row from row 2.',
    parsed: (n) => ` · parsed ${n} rows`,
    quoting: ' · estimating…',
    done: (ok, fail) => ` · ${ok} succeeded · ${fail} failed`,
    notSubmitted: (n) => `These rows were not submitted (${n} rows)`,
    thRow: 'Row',
    thKm: 'Distance km',
    thTrucks: 'Vehicles',
    thCost: 'Total cost',
    thError: 'Error',
    note: '"Total cost" in this list is the internal basis; it appears only on this page and never in a public quote.',
  },
  chat: {
    emptyReply: '(No content returned this turn — try rephrasing)',
    unavailable: 'The AI assistant is temporarily unavailable; please retry shortly',
    computing: 'Calculating…',
    done: 'Done',
    failed: 'No result',
    aborted: 'Stopped',
    panelAria: 'AI quoting assistant',
  },
};

export function panelsText(lang: Lang): Dict {
  if (lang === 'vi') return VI;
  if (lang === 'en') return EN;
  return ZH;
}
