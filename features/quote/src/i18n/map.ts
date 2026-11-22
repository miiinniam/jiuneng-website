/** /quote 地址搜索与地图选点文案（中 / 越 / 英）。语言来源同样走 detectLang()。 */
import type { Lang } from './strings';

type Dict = {
  addr: { searching: string; search: string; city: string; address: string; none: string };
  map: { pickDestNew: string; pickOrigin: string; pickDest: string; settled: string; loading: string; cancelReset: string; reset: string };
};

const ZH: Dict = {
  addr: { searching: '搜索中', search: '搜索', city: '城市', address: '地址', none: '没有匹配地址，换关键词或直接在地图上点选' },
  map: {
    pickDestNew: '点地图选择新终点',
    pickOrigin: '点地图选起点',
    pickDest: '点地图选终点',
    settled: '起终点已就位 · 要改终点请用「重设终点」',
    loading: '地图加载中…',
    cancelReset: '取消重设',
    reset: '重设终点',
  },
};

const VI: Dict = {
  addr: { searching: 'Đang tìm', search: 'Tìm', city: 'Thành phố', address: 'Địa chỉ', none: 'Không có địa chỉ khớp, hãy đổi từ khóa hoặc chọn trực tiếp trên bản đồ' },
  map: {
    pickDestNew: 'Nhấp bản đồ để chọn điểm đến mới',
    pickOrigin: 'Nhấp bản đồ để chọn điểm đi',
    pickDest: 'Nhấp bản đồ để chọn điểm đến',
    settled: 'Đã có điểm đi và điểm đến · muốn đổi điểm đến hãy dùng "Đặt lại điểm đến"',
    loading: 'Đang tải bản đồ…',
    cancelReset: 'Hủy đặt lại',
    reset: 'Đặt lại điểm đến',
  },
};

const EN: Dict = {
  addr: { searching: 'Searching', search: 'Search', city: 'City', address: 'Address', none: 'No matching address — try another keyword or click directly on the map' },
  map: {
    pickDestNew: 'Click the map to pick a new destination',
    pickOrigin: 'Click the map to set the origin',
    pickDest: 'Click the map to set the destination',
    settled: 'Origin and destination set · to change the destination use "Reset destination"',
    loading: 'Loading map…',
    cancelReset: 'Cancel reset',
    reset: 'Reset destination',
  },
};

export function mapText(lang: Lang): Dict {
  if (lang === 'vi') return VI;
  if (lang === 'en') return EN;
  return ZH;
}
