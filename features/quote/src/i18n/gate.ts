/** /quote 内部口令门禁文案（中 / 越 / 英）。 */
import type { Lang } from './strings';

type Dict = {
  aria: string;
  kicker: string;
  title: string;
  body: string;
  placeholder: string;
  confirm: string;
  cancel: string;
  footNote: string;
};

const ZH: Dict = {
  aria: '内部口令',
  kicker: '内部访问',
  title: '输入内部口令',
  body: '内部版包含成本分项与批量测算，需要口令。口令只保存在当前浏览器会话。',
  placeholder: '内部口令',
  confirm: '确认并重试',
  cancel: '取消',
  footNote: '口令错误会再次提示；忘记口令请联系系统管理员。',
};

const VI: Dict = {
  aria: 'Mật lệnh nội bộ',
  kicker: 'Truy cập nội bộ',
  title: 'Nhập mật lệnh nội bộ',
  body: 'Bản nội bộ gồm chi phí từng mục và tính hàng loạt, cần mật lệnh. Mật lệnh chỉ lưu trong phiên trình duyệt hiện tại.',
  placeholder: 'Mật lệnh nội bộ',
  confirm: 'Xác nhận và thử lại',
  cancel: 'Hủy',
  footNote: 'Sai mật lệnh sẽ hiện lại nhắc; quên mật lệnh vui lòng liên hệ quản trị hệ thống.',
};

const EN: Dict = {
  aria: 'Internal passphrase',
  kicker: 'Internal access',
  title: 'Enter the internal passphrase',
  body: 'The internal version includes cost breakdowns and batch estimates, so it needs a passphrase. The passphrase is kept only in the current browser session.',
  placeholder: 'Internal passphrase',
  confirm: 'Confirm and retry',
  cancel: 'Cancel',
  footNote: 'A wrong passphrase prompts again; if you have forgotten it, contact the system administrator.',
};

export function gateText(lang: Lang): Dict {
  if (lang === 'vi') return VI;
  if (lang === 'en') return EN;
  return ZH;
}
