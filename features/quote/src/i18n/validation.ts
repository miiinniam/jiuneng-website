/** /quote 表单校验提示与地图标记文案（中 / 越 / 英）。 */
import type { Lang } from './strings';

type Dict = {
  originPin: string;
  destPin: string;
  weight: string;
  weightPositive: string;
  volumePositive: string;
  volumeRequired: string;
  cargoType: string;
  vehicle: string;
  items: string;
  fuel: string;
  wage: string;
  toll: string;
  misc: string;
  negative: (label: string) => string;
  pinOrigin: string;
  pinDest: string;
  pinWaypoint: (n: number) => string;
};

const ZH: Dict = {
  originPin: '请在地图上选择起点',
  destPin: '请在地图上选择终点',
  weight: '请填写货物重量',
  weightPositive: '重量需大于 0',
  volumePositive: '体积需大于 0',
  volumeRequired: '拼货模式需填写体积',
  cargoType: '请选择货物类型',
  vehicle: '请选择车型',
  items: '单件明细需同时填写长和宽，件数至少 1',
  fuel: '油价',
  wage: '时薪',
  toll: '过路费率',
  misc: '杂费',
  negative: (label) => `${label}不能为负数`,
  pinOrigin: '起',
  pinDest: '终',
  pinWaypoint: (n) => `途经点 ${n}`,
};

const VI: Dict = {
  originPin: 'Vui lòng chọn điểm đi trên bản đồ',
  destPin: 'Vui lòng chọn điểm đến trên bản đồ',
  weight: 'Vui lòng nhập trọng lượng hàng',
  weightPositive: 'Trọng lượng phải lớn hơn 0',
  volumePositive: 'Thể tích phải lớn hơn 0',
  volumeRequired: 'Chế độ ghép hàng cần nhập thể tích',
  cargoType: 'Vui lòng chọn loại hàng',
  vehicle: 'Vui lòng chọn loại xe',
  items: 'Chi tiết kiện cần điền cả dài và rộng, số kiện ít nhất 1',
  fuel: 'Giá dầu',
  wage: 'Lương giờ',
  toll: 'Phí đường',
  misc: 'Chi phí khác',
  negative: (label) => `${label} không được âm`,
  pinOrigin: 'A',
  pinDest: 'B',
  pinWaypoint: (n) => `Điểm dừng ${n}`,
};

const EN: Dict = {
  originPin: 'Please pick the origin on the map',
  destPin: 'Please pick the destination on the map',
  weight: 'Please enter the cargo weight',
  weightPositive: 'Weight must be greater than 0',
  volumePositive: 'Volume must be greater than 0',
  volumeRequired: 'Consolidated mode requires a volume',
  cargoType: 'Please select a cargo type',
  vehicle: 'Please select a vehicle type',
  items: 'Per-piece rows need both length and width, with at least 1 piece',
  fuel: 'Diesel price',
  wage: 'Hourly wage',
  toll: 'Toll rate',
  misc: 'Miscellaneous',
  negative: (label) => `${label} cannot be negative`,
  pinOrigin: 'A',
  pinDest: 'B',
  pinWaypoint: (n) => `Waypoint ${n}`,
};

export function validateText(lang: Lang): Dict {
  if (lang === 'vi') return VI;
  if (lang === 'en') return EN;
  return ZH;
}
